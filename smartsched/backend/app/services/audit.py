"""P7 audit log (docs/product/booking-enhancements.md §4.6): the one helper every audited change goes through.

Two entry points, both writing ``audit_events`` rows inside the transaction of the change:

* :func:`record` -- explicit, meaningful actions with before/after snapshots (``booking.create``,
  ``booking.move``, ``booking.cancel``, ``room.features``, ``approval.approve`` ...). The booking, feature and
  approval services call it; booking actions are ``reversible`` (``POST /audit/{id}/undo``).
* :func:`track` -- the flush hook for the administration tables (users, roles, room ACL, rooms, room groups,
  custom fields, settings, schedules, periods, sessions, holidays, departments, translations ...): every row
  created, changed or deleted while an API request is being served becomes ``<entity>.create|update|delete``
  with only the changed fields. It runs only when the request context is set (``set_context``, done for every
  ``/api/v1`` request by ``app.api.v1.audit.audit_context``), so imports and background jobs stay silent.

Secrets never reach the log: password hashes, tokens and every ``is_secret`` setting are stored as ``"***"``.
The client address is kept only as an HMAC of its /24 (IPv4) or /48 (IPv6) network (KVKK data minimisation).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AuditEvent,
    BookingPeriod,
    BookingSchedule,
    Building,
    Holiday,
    Program,
    Role,
    RoomAcl,
    RoomCustomField,
    RoomCustomFieldOption,
    RoomGroup,
    Setting,
    Term,
    TermBookingSettings,
    TermSchedule,
    TimetableWeek,
    Translation,
    User,
    UserConstraint,
)
from app.models.catalog import Room

CTX_KEY = "audit_ctx"
PENDING_KEY = "audit_pending"
REDACTED = "***"
#: field names whose values are never written (any table)
SECRET_FIELDS = frozenset({"password", "password_hash", "calendar_token", "token", "token_hash", "api_key", "secret"})


@dataclass(frozen=True)
class AuditContext:
    actor_id: int | None = None
    actor_label: str | None = None
    actor_type: str = "anonymous"  # user | system | anonymous
    request_id: str | None = None
    ip_hash: str | None = None


def set_context(session: AsyncSession | Session, ctx: AuditContext) -> None:
    session.info[CTX_KEY] = ctx


def context(session: AsyncSession | Session) -> AuditContext | None:
    ctx = session.info.get(CTX_KEY)
    return ctx if isinstance(ctx, AuditContext) else None


def user_label(u: User | None) -> str | None:
    if u is None:
        return None
    return u.full_name or u.username or u.email or f"#{u.id}"


def hash_ip(address: str | None) -> str | None:
    """HMAC (APP_SECRET) of the network: /24 for IPv4, /48 for IPv6; the address itself is never stored."""
    if not address:
        return None
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return None
    net = ipaddress.ip_network(f"{ip}/{24 if ip.version == 4 else 48}", strict=False)
    key = get_settings().app_secret.encode()
    return hmac.new(key, str(net).encode(), hashlib.sha256).hexdigest()[:32]


# --------------------------------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------------------------------


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        items = [jsonable(v) for v in value]
        return sorted(items, key=str) if isinstance(value, set | frozenset) else items
    return str(value)


def redact(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {k: (REDACTED if k in SECRET_FIELDS and v not in (None, "") else jsonable(v)) for k, v in data.items()}


def diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    """``{field: [old, new]}`` for the fields that differ (only changed fields are stored)."""
    b, a = before or {}, after or {}
    return {k: [b.get(k), a.get(k)] for k in sorted(set(b) | set(a)) if b.get(k) != a.get(k)}


def snapshot(obj: Any, fields: Iterable[str] | None = None) -> dict[str, Any]:
    """Column values of an ORM object (or the listed attributes), JSON-safe."""
    if fields is None:
        fields = [c.key for c in inspect(obj).mapper.column_attrs]
    return {f: jsonable(getattr(obj, f, None)) for f in fields}


# --------------------------------------------------------------------------------------------------
# Explicit records
# --------------------------------------------------------------------------------------------------


async def record(
    session: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: Any,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor: User | None = None,
    reason: str | None = None,
    term_id: int | None = None,
    reversible: bool = False,
    parent_id: int | None = None,
    undo_of: int | None = None,
) -> AuditEvent:
    """Append one event (flushed, so its id can parent bulk children). ``actor`` defaults to the request's user."""
    ctx = context(session) or AuditContext(actor_type="system")
    if undo_of is None:
        undo_of = session.info.get("audit_undo_of")
    b, a = redact(before), redact(after)
    ev = AuditEvent(
        actor_type="user" if actor is not None else ctx.actor_type,
        actor_id=actor.id if actor is not None else ctx.actor_id,
        actor_label=user_label(actor) if actor is not None else ctx.actor_label,
        action=action[:64],
        entity_type=entity_type[:32],
        entity_id=str(entity_id) if entity_id is not None else None,
        term_id=term_id,
        before=b,
        after=a,
        diff=diff(b, a) if (b is not None and a is not None) else None,
        reason=reason,
        request_id=ctx.request_id,
        ip_hash=ctx.ip_hash,
        reversible=reversible,
        parent_id=parent_id,
        undo_of=undo_of,
    )
    session.add(ev)
    await session.flush()
    return ev


async def record_many(
    session: AsyncSession,
    action: str,
    entity_type: str,
    items: list[tuple[Any, dict[str, Any] | None, dict[str, Any] | None]],
    *,
    parent_entity_id: Any = None,
    parent_after: dict[str, Any] | None = None,
    **kw: Any,
) -> AuditEvent | None:
    """A bulk operation: one event when ``items`` has one entry, else a parent plus one child per entity
    (undo works on the parent). Returns the event an undo should target."""
    if not items:
        return None
    if len(items) == 1:
        eid, b, a = items[0]
        return await record(session, action, entity_type, eid, before=b, after=a, **kw)
    parent = await record(
        session,
        action,
        entity_type,
        parent_entity_id if parent_entity_id is not None else items[0][0],
        after={"count": len(items), "ids": [i[0] for i in items], **(parent_after or {})},
        **kw,
    )
    for eid, b, a in items:
        await record(session, action, entity_type, eid, before=b, after=a, parent_id=parent.id, **kw)
    return parent


# --------------------------------------------------------------------------------------------------
# Flush hook for the administration tables
# --------------------------------------------------------------------------------------------------

#: model -> (entity type, fields never logged as changes). Bookings, approvals and features are recorded
#: explicitly by their services (meaningful actions, undo), so they are not tracked here.
TRACKED: dict[type, tuple[str, frozenset[str]]] = {
    User: ("user", frozenset({"last_login_at", "token_version", "created_at"})),
    Role: ("role", frozenset({"created_at"})),
    UserConstraint: ("user_constraints", frozenset()),
    RoomAcl: ("room_acl", frozenset()),
    Room: ("room", frozenset({"created_at", "updated_at", "custom_fields"})),
    RoomGroup: ("room_group", frozenset()),
    RoomCustomField: ("room_field", frozenset()),
    RoomCustomFieldOption: ("room_field_option", frozenset()),
    Building: ("building", frozenset()),
    Setting: ("settings", frozenset({"updated_at"})),
    BookingSchedule: ("schedule", frozenset()),
    BookingPeriod: ("period", frozenset()),
    TermBookingSettings: ("session", frozenset()),
    TermSchedule: ("session_schedule", frozenset()),
    TimetableWeek: ("timetable_week", frozenset()),
    Holiday: ("holiday", frozenset()),
    Program: ("department", frozenset()),
    Translation: ("translation", frozenset()),
    Term: ("term", frozenset({"created_at", "updated_at"})),
}
#: collection relationships logged as {"added": [...], "removed": [...]}
COLLECTIONS: dict[type, dict[str, str]] = {Role: {"permissions": "name"}, RoomAcl: {"permissions": "name"}}


def _entity_id(obj: Any) -> str | None:
    ident = inspect(obj).identity
    if ident is None:
        return None
    return ":".join(str(i) for i in ident)


def _secret_setting(obj: Any) -> bool:
    return isinstance(obj, Setting) and bool(obj.is_secret)


def _clean(obj: Any, data: dict[str, Any]) -> dict[str, Any]:
    out = redact(data) or {}
    if _secret_setting(obj) and out.get("value") not in (None, ""):
        out["value"] = REDACTED
    return out


def _skip(obj: Any) -> bool:
    # per-user preference rows (``user.{id}.*``: recent searches, changelog seen) are not administration
    return isinstance(obj, Setting) and str(obj.key or "").startswith("user.")


def _changes(obj: Any, ignore: frozenset[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    insp = inspect(obj)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for attr in insp.mapper.column_attrs:
        if attr.key in ignore:
            continue
        hist = insp.attrs[attr.key].history
        if not hist.has_changes():
            continue
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        if jsonable(old) == jsonable(new):
            continue
        before[attr.key], after[attr.key] = old, new
    for rel, label in COLLECTIONS.get(type(obj), {}).items():
        hist = insp.attrs[rel].history
        added = sorted(str(getattr(x, label, x)) for x in hist.added or [])
        removed = sorted(str(getattr(x, label, x)) for x in hist.deleted or [])
        if added or removed:
            after[rel] = {"added": added, "removed": removed}
    return before, after


def _before_flush(session: Session, flush_context: Any, instances: Any) -> None:  # noqa: ARG001
    if context(session) is None:
        return
    pending: list[tuple[str, Any, dict[str, Any] | None, dict[str, Any] | None]] = session.info.setdefault(
        PENDING_KEY, []
    )
    for obj in list(session.new):
        if type(obj) in TRACKED and not _skip(obj):
            pending.append(("create", obj, None, None))
    for obj in list(session.dirty):
        spec = TRACKED.get(type(obj))
        if spec is None or _skip(obj) or not session.is_modified(obj, include_collections=True):
            continue
        before, after = _changes(obj, spec[1])
        if before or after:
            pending.append(("update", obj, before, after))
    for obj in list(session.deleted):
        spec = TRACKED.get(type(obj))
        if spec is not None and not _skip(obj):
            data = {k: v for k, v in snapshot(obj).items() if k not in spec[1]}
            pending.append(("delete", obj, data, None))


def _after_flush_postexec(session: Session, flush_context: Any) -> None:  # noqa: ARG001
    pending = session.info.pop(PENDING_KEY, None)
    ctx = context(session)
    if not pending or ctx is None:
        return
    for op, obj, before, after in pending:
        entity, ignore = TRACKED[type(obj)]
        if op == "create":
            after = {k: v for k, v in snapshot(obj).items() if k not in ignore}
            for rel, label in COLLECTIONS.get(type(obj), {}).items():
                after[rel] = sorted(str(getattr(x, label, x)) for x in getattr(obj, rel, []) or [])
        b = _clean(obj, before) if before is not None else None
        a = _clean(obj, after) if after is not None else None
        action = "settings.update" if entity == "settings" else f"{entity}.{op}"
        session.add(
            AuditEvent(
                actor_type=ctx.actor_type,
                actor_id=ctx.actor_id,
                actor_label=ctx.actor_label,
                action=action,
                entity_type=entity,
                entity_id=_entity_id(obj),
                before=b,
                after=a,
                diff=diff(b, a) if op == "update" else None,
                request_id=ctx.request_id,
                ip_hash=ctx.ip_hash,
                reversible=False,
            )
        )


def track() -> None:
    """Install the flush hook (idempotent; done when this module is imported)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
        event.listen(Session, "after_flush_postexec", _after_flush_postexec)


track()
