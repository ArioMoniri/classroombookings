"""The single hook point for booking-side mutations (booking enhancements wave 1).

Every booking / series / approval mutation calls :func:`publish_event` once, inside the transaction of the
change. It

1. appends the audit event (P7, :mod:`app.services.audit`; one row, or a parent plus one child per booking for
   bulk changes) -- the returned row is what ``POST /audit/{id}/undo`` targets;
2. forwards the legacy in-process event (``app.services.bookings_events``: e-mail notifications) when
   ``notify`` names one;
3. calls every subscriber registered with :func:`subscribe` (calendar sync, outgoing webhooks, ...).

Subscribers are ``async def handler(session, event: DomainEvent) -> None``. Like ``bookings_events`` they run
after the change is flushed and before the commit; a failing subscriber is logged, never propagated (a broken
webhook must not undo a booking). Subscribers that talk to the outside world should enqueue work (outbox
pattern) rather than call out from here.

Event names are the audit actions: ``booking.create``, ``booking.move``, ``booking.update``,
``booking.cancel``, ``booking.restore``, ``series.create``, ``approval.request``, ``approval.step``,
``approval.approve``, ``approval.reject``, ``approval.expire``, ``approval.withdraw``. ``subscribe("booking.*", h)``
matches a prefix.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, User
from app.services import audit
from app.services import bookings_events as legacy

log = logging.getLogger(__name__)

Item = tuple[Any, dict[str, Any] | None, dict[str, Any] | None]  # (entity id, before, after)


@dataclass
class DomainEvent:
    action: str
    entity_type: str
    entity_id: Any
    items: list[Item] = field(default_factory=list)
    actor_id: int | None = None
    reason: str | None = None
    term_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    audit_id: int | None = None

    item_type: str | None = None

    @property
    def booking_ids(self) -> list[int]:
        kind = self.item_type or self.entity_type
        return [int(i[0]) for i in self.items if kind == "booking" and str(i[0]).isdigit()]


Subscriber = Callable[[AsyncSession, DomainEvent], Awaitable[None]]
_subscribers: list[tuple[str, Subscriber]] = []


def subscribe(pattern: str, handler: Subscriber) -> Subscriber:
    """``pattern``: an exact action, ``prefix.*`` or ``*``."""
    if (pattern, handler) not in _subscribers:
        _subscribers.append((pattern, handler))
    return handler


def unsubscribe(pattern: str, handler: Subscriber) -> None:
    if (pattern, handler) in _subscribers:
        _subscribers.remove((pattern, handler))


def _matches(pattern: str, action: str) -> bool:
    if pattern == "*" or pattern == action:
        return True
    return pattern.endswith(".*") and action.startswith(pattern[:-1])


async def publish_event(
    session: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    items: list[Item] | None = None,
    actor: User | None = None,
    reason: str | None = None,
    term_id: int | None = None,
    reversible: bool = False,
    parent_after: dict[str, Any] | None = None,
    parent_entity_type: str | None = None,
    child_action: str | None = None,
    item_type: str | None = None,
    undo_of: int | None = None,
    notify: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """Audit + legacy notification + subscribers for one mutation. ``items`` makes it a bulk event: one child per
    entity (of ``item_type``, default ``entity_type``; action ``child_action``, default ``action``) under a parent
    ``entity_type``/``entity_id``; otherwise ``before``/``after`` describe ``entity_id``."""
    kw: dict[str, Any] = {"actor": actor, "reason": reason, "term_id": term_id, "reversible": reversible}
    if undo_of is not None:
        kw["undo_of"] = undo_of
    if items is not None:
        row = await audit.record_many(
            session,
            action,
            item_type or entity_type,
            items,
            parent_entity_id=entity_id,
            parent_after=parent_after,
            parent_entity_type=entity_type if item_type else parent_entity_type,
            child_action=child_action,
            **kw,
        )
    else:
        row = await audit.record(session, action, entity_type, entity_id, before=before, after=after, **kw)
        items = [(entity_id, before, after)]
    if notify is not None:
        await legacy.emit(session, notify, payload or {})
    ev = DomainEvent(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        items=items,
        item_type=item_type or entity_type,
        actor_id=actor.id if actor is not None else None,
        reason=reason,
        term_id=term_id,
        payload=payload or {},
        audit_id=row.id if row is not None else None,
    )
    for pattern, handler in list(_subscribers):
        if not _matches(pattern, action):
            continue
        try:
            await handler(session, ev)
        except Exception:  # noqa: BLE001 - subscribers never break the mutation that triggered them
            log.exception("event subscriber %s for %s failed", handler, action)
    return row
