"""Room groups made from buildings (``POST /room-admin/groups/from-buildings`` and the room-master import).

CRBS shows only rooms that belong to a room group (``org.use_room_groups`` on, ``bookings.show_ungrouped_rooms``
off: the defaults). The workbook importers create rooms but no groups, so an install seeded from the planning
files had every room hidden from the booking grid and from "Boş derslik bul" (owner report 2026-11-02 item 3:
"0 boş oda"). The room master import now files every ungrouped bookable room into its building's group (``A Blok``
...), as the e2e and recording stacks did by hand (``POST /room-admin/groups/from-buildings``); the deploy seed
re-runs the room master when room_master.csv changes. CRBS's rule itself is unchanged: without any group the
booking grid stays empty (tests/test_crbs_bookings.py ``test_ungrouped_rooms_hidden_like_crbs``)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import Building, RoomGroup
from app.models.catalog import Room


async def groups_from_buildings(session: AsyncSession, *, bookable_only: bool = False) -> list[RoomGroup]:
    """One group per building (A, B, C, D blocks) holding that building's ungrouped rooms (created when missing,
    reused by name). Rooms that already have a group keep it. ``bookable_only``: leave retired / unbookable rooms
    out (the room-master import). Flushes; the caller commits."""
    out: list[RoomGroup] = []
    for b in (await session.execute(select(Building).order_by(Building.code))).scalars():
        q = select(Room).where(Room.building_id == b.id, Room.room_group_id.is_(None))
        if bookable_only:
            q = q.where(Room.is_bookable.is_(True))
        rooms = list((await session.execute(q)).scalars())
        if not rooms:
            continue
        name = (n.clean_text(b.name) or b.code)[:32]
        g = (await session.execute(select(RoomGroup).where(RoomGroup.name == name))).scalar_one_or_none()
        if g is None:
            pos = (await session.execute(select(func.max(RoomGroup.pos)))).scalar() or 0
            g = RoomGroup(name=name, pos=pos + 1)
            session.add(g)
            await session.flush()
        for r in rooms:
            r.room_group_id, r.room_group = g.id, g.name
        out.append(g)
    await session.flush()
    return out


__all__ = ["groups_from_buildings"]
