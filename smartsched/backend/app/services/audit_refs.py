"""BUG-02: the names behind the id fields of audit events, for one viewer (the before/after table of /admin/audit
showed ``room_id 14 -> 17``).

:func:`refs_for` answers ``{event id: {field: {id: name}}}`` for the id fields of each event's ``before`` /
``after`` / ``diff`` (``room_id`` -> "A 101", ``user_id`` -> "Ayşe Yılmaz", ``period_id`` -> "P1", ...), with one
query per record kind for a whole page. It names only what the viewer may already see elsewhere:

* rooms: ``audit.view`` or ``room.view`` on the room (role or room ACL), as the booking grid;
* people: ``audit.view``, the viewer themself, or (booking events) ``book_single`` / ``book_recur``
  ``.view_other_users`` on the booking's room, as :func:`app.services.bookings.can_view_user`;
* periods, departments, terms, room groups, buildings, schedules and roles: by name (setup data, not personal).

An id that is not named stays a number; the frontend then shows the number with the field's label."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, Building, BookingPeriod, BookingSchedule, Program, Role, Room, RoomGroup, Term, User
from app.services.audit import user_label
from app.services.bookings_perms import Access

#: id field -> record kind
FIELD_KINDS: dict[str, str] = {
    "room_id": "room",
    "new_room_id": "room",
    "user_id": "user",
    "owner_user_id": "user",
    "created_by": "user",
    "cancelled_by": "user",
    "decided_by": "user",
    "approver_id": "user",
    "period_id": "period",
    "department_id": "department",
    "term_id": "term",
    "room_group_id": "room_group",
    "building_id": "building",
    "schedule_id": "schedule",
    "default_schedule_id": "schedule",
    "role_id": "role",
}

_MODELS: dict[str, Any] = {
    "room": Room,
    "user": User,
    "period": BookingPeriod,
    "department": Program,
    "term": Term,
    "room_group": RoomGroup,
    "building": Building,
    "schedule": BookingSchedule,
    "role": Role,
}

_BOOKING_ENTITIES = frozenset({"booking", "booking_series", "series"})


def _ids(value: Any) -> Iterable[int]:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        yield value
    elif isinstance(value, str) and value.isdigit():
        yield int(value)
    elif isinstance(value, list | tuple):  # a diff pair [old, new]
        for v in value:
            yield from _ids(v)


def _fields(ev: AuditEvent) -> dict[str, set[int]]:
    out: dict[str, set[int]] = defaultdict(set)
    for snap in (ev.before, ev.after, ev.diff):
        for field, value in (snap or {}).items():
            if field in FIELD_KINDS:
                out[field].update(_ids(value))
    return out


def _name(kind: str, obj: Any) -> str | None:
    if kind == "room":
        return str(obj.display_name or obj.code)
    if kind == "user":
        return user_label(obj)
    return str(getattr(obj, "name", None) or getattr(obj, "code", None) or "") or None


async def refs_for(
    session: AsyncSession, access: Access, events: list[AuditEvent]
) -> dict[int, dict[str, dict[str, str]]]:
    full = access.can("audit.view")
    per_event = {ev.id: _fields(ev) for ev in events}
    wanted: dict[str, set[int]] = defaultdict(set)
    for fields in per_event.values():
        for field, ids in fields.items():
            wanted[FIELD_KINDS[field]].update(ids)
    for ev in events:  # the booking's room decides whether its people may be named
        if ev.entity_type in _BOOKING_ENTITIES:
            wanted["room"].update(_ids((ev.after or ev.before or {}).get("room_id")))
    loaded: dict[str, dict[int, Any]] = {}
    for kind, ids in wanted.items():
        if not ids:
            continue
        model = _MODELS[kind]
        rows = (await session.execute(select(model).where(model.id.in_(sorted(ids))))).scalars()
        loaded[kind] = {r.id: r for r in rows}
    rooms = loaded.get("room", {})

    def room_ok(rid: int) -> bool:
        room = rooms.get(rid)
        return room is not None and (full or access.can_view_room(room))

    out: dict[int, dict[str, dict[str, str]]] = {}
    for ev in events:
        people_room: Room | None = None
        if ev.entity_type in _BOOKING_ENTITIES:
            rid = next(iter(_ids((ev.after or ev.before or {}).get("room_id"))), None)
            people_room = rooms.get(rid) if rid is not None else None
        others_ok = full or (
            people_room is not None
            and (
                access.can("book_single.view_other_users", people_room)
                or access.can("book_recur.view_other_users", people_room)
            )
        )
        refs: dict[str, dict[str, str]] = {}
        for field, ids in per_event[ev.id].items():
            kind = FIELD_KINDS[field]
            names: dict[str, str] = {}
            for i in sorted(ids):
                obj = loaded.get(kind, {}).get(i)
                if obj is None:
                    continue
                if kind == "room" and not room_ok(i):
                    continue
                if kind == "user" and not (others_ok or i == access.user_id):
                    continue
                name = _name(kind, obj)
                if name:
                    names[str(i)] = name
            if names:
                refs[field] = names
        out[ev.id] = refs
    return out
