"""Helpers for the booking enhancements wave 2 tests (P2, P8, V2, A4) on the real Bahar 2026 import
(``tests/crbs_env``)."""

from __future__ import annotations

from datetime import date

from app.core import db as dbmod
from app.models import Assignment, Room, ScheduleRun
from app.services import bookings as bsvc
from sqlalchemy import select


async def free_rooms(day: date, start: int, end: int, *, codes: list[str] | None = None, limit: int = 5) -> list[str]:
    """Canonical codes of bookable plain rooms (no TIP / PC tag, capacity known) free on ``day`` P``start``-P``end``
    in the published timetable, blocks and bookings, in room order."""
    async with dbmod.get_session_factory()() as s:
        q = select(Room).where(Room.is_bookable.is_(True)).order_by(Room.code)
        out: list[str] = []
        for r in (await s.execute(q)).scalars():
            if codes is not None and r.code not in codes:
                continue
            if codes is None and (r.tags or not r.capacity):
                continue
            if await bsvc.find_conflict(s, r.id, day, start, end) is None:
                out.append(r.code)
                if len(out) >= limit:
                    break
        return out


async def exam_run_slots(term_id: int) -> list[tuple[int, date, int, int, list[int]]]:
    """(assignment id, date, start, end, room ids) of the term's imported exam board (the Final weeks)."""
    async with dbmod.get_session_factory()() as s:
        run = (
            await s.execute(select(ScheduleRun).where(ScheduleRun.term_id == term_id, ScheduleRun.kind == "EXAM"))
        ).scalar_one()
        rows = (
            await s.execute(
                select(Assignment).where(Assignment.run_id == run.id, Assignment.date.is_not(None)).order_by(
                    Assignment.date, Assignment.start_period, Assignment.id
                )
            )
        ).scalars()
        return [(a.id, a.date, a.start_period, a.end_period, [int(x) for x in a.room_ids or []]) for a in rows]


async def exam_run_id(term_id: int) -> int:
    async with dbmod.get_session_factory()() as s:
        return (
            await s.execute(
                select(ScheduleRun.id).where(ScheduleRun.term_id == term_id, ScheduleRun.kind == "EXAM")
            )
        ).scalar_one()


async def room_codes() -> dict[int, str]:
    async with dbmod.get_session_factory()() as s:
        return {r.id: r.code for r in (await s.execute(select(Room))).scalars()}
