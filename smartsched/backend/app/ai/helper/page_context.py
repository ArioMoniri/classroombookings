"""The page the person has open, as the helper's model reads it (HB-D; ``POST /helper/turn`` ``context``).

The browser sends ``{route, entity_kind?, entity_id?}``. None of it is trusted:

* ``route`` must be a page path of the **feature index** (``features.yaml``) that the person may open
  (:func:`app.ai.helper.index.visible`). A query string and a trailing slash are ignored; a ``#section`` picks the
  section's entry when there is one. A path ending in a number (``/rooms/12``) falls back to its list page. Anything
  else is **dropped** (and with it the entity).
* ``entity_id`` must be something the person can read: a ``room`` among their visible rooms, a ``booking`` that is
  theirs (or one they may see the person of), an ``approval_request`` they made or decide. Otherwise the entity is
  dropped and the page stays.
* The result goes to the model as **one** spotlighted ``page_context`` block (database text cleaned first). It is
  never used for a permission: tools, actions and ids are checked by the registry as always.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper import cards
from app.ai.helper.index import FeatureEntry, get_index, visible
from app.services.bookings_perms import Access

EntityKind = Literal["room", "booking", "approval_request"]
ENTITY_KINDS: tuple[str, ...] = ("room", "booking", "approval_request")
_PATH = re.compile(r"^/[a-z0-9\-/]*$")
_HASH = re.compile(r"^[a-z0-9\-]{1,40}$")


@dataclass(frozen=True)
class PageContext:
    entry: FeatureEntry
    entity_kind: str | None = None
    entity_id: int | None = None
    #: cleaned database text ("A 102", "A 102 · 19.02.2026 08:40")
    entity_label: str | None = None

    def block(self) -> str:
        """The text inside the spotlighted block (English labels; titles in both languages)."""
        e = self.entry
        lines = [
            f"Page: {e.id} ({e.title.en} / {e.title.tr}); path: {' › '.join(e.path.en)}",
        ]
        if self.entity_kind and self.entity_id is not None:
            lines.append(f"Looking at: {self.entity_kind} {self.entity_id}, {self.entity_label or ''}".rstrip(", "))
        return "\n".join(lines)


def _split(route: str) -> tuple[str, str | None] | None:
    raw = (route or "").strip().lower()
    if not raw.startswith("/") or len(raw) > 200:
        return None
    path, _, rest = raw.partition("#")
    path = path.split("?", 1)[0]
    fragment = rest.split("?", 1)[0] or None
    path = path.rstrip("/") or "/"
    if not _PATH.match(path) or "//" in path or any(seg in (".", "..") for seg in path.split("/")):
        return None
    if fragment is not None and not _HASH.match(fragment):
        fragment = None
    return path, fragment


def match_route(route: str, perms: Any) -> FeatureEntry | None:
    """The index entry for ``route`` that the person may open, or ``None`` (dropped)."""
    parts = _split(route)
    if parts is None:
        return None
    path, fragment = parts
    entries = [e for e in get_index().entries if visible(e, perms)]

    def best(p: str) -> FeatureEntry | None:
        if fragment is not None:
            with_hash = [e for e in entries if e.route == f"{p}#{fragment}"]
            if with_hash:
                return with_hash[0]
        same = [e for e in entries if e.route == p]
        pages = [e for e in same if e.kind == "page"]
        found = pages or same
        return found[0] if found else None

    hit = best(path)
    if hit is None:
        head, _, tail = path.rpartition("/")
        if tail.isdigit() and head:
            hit = best(head)
    return hit


async def _room_label(session: AsyncSession, access: Access, room_id: int) -> str | None:
    from app.services import bookings as bsvc

    rooms = await bsvc.visible_rooms(session, access)
    room = next((r for r in rooms if r.id == room_id), None)
    return cards.clean(room.display_name, 80) if room is not None else None


async def _booking_label(session: AsyncSession, access: Access, booking_id: int) -> str | None:
    from app.models import Booking, BookingPeriod
    from app.models.catalog import Room
    from app.services import bookings as bsvc

    b = await session.get(Booking, booking_id)
    if b is None:
        return None
    room = await session.get(Room, b.room_id)
    if room is None or not access.can_view_room(room):
        return None
    if access.user_id not in (b.user_id, b.created_by) and not bsvc.can_view_user(access, b, room):
        return None
    period = await session.get(BookingPeriod, b.period_id)
    when = b.date.strftime("%d.%m.%Y")
    if period is not None:
        when += f" {period.time_start.strftime('%H:%M')}"
    return cards.clean(f"{room.display_name} · {when}", 120)


async def _request_label(session: AsyncSession, access: Access, request_id: int) -> str | None:
    from app.models import ApprovalRequest
    from app.models.catalog import Room
    from app.services import approvals as asvc

    req = await session.get(ApprovalRequest, request_id)
    if req is None:
        return None
    room = await session.get(Room, req.room_id)
    if room is None:
        return None
    if req.requested_by != access.user_id:
        if not access.can(asvc.DECIDE):
            return None
        approvers = await asvc.step_approvers(session, room, req.rule_snapshot or {}, req.step)
        if access.user not in approvers:
            return None
    return cards.clean(f"{room.display_name} · {req.status.lower()}", 120)


async def resolve(session: AsyncSession, access: Access, raw: dict[str, Any] | None) -> PageContext | None:
    """The checked context, or ``None`` when the route is unknown or not the person's to open."""
    if not raw:
        return None
    entry = match_route(str(raw.get("route") or ""), access.perms)
    if entry is None:
        return None
    kind, ident = raw.get("entity_kind"), raw.get("entity_id")
    if kind not in ENTITY_KINDS or not isinstance(ident, int) or ident < 1:
        return PageContext(entry)
    label_of = {"room": _room_label, "booking": _booking_label, "approval_request": _request_label}[str(kind)]
    label = await label_of(session, access, ident)
    if label is None:
        return PageContext(entry)
    return PageContext(entry, str(kind), ident, label)


__all__ = ["ENTITY_KINDS", "EntityKind", "PageContext", "match_route", "resolve"]
