"""Room conflict checks for inline edits (inbox) and manual moves."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, Block, MeetingRequest, Room, ScheduleRun, Section


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


async def active_run_for_term(session: AsyncSession, term_id: int, kind: str | None = None) -> ScheduleRun | None:
    q = select(ScheduleRun).where(ScheduleRun.term_id == term_id, ScheduleRun.is_active.is_(True))
    if kind:
        q = q.where(ScheduleRun.kind == kind)
    return (await session.execute(q.order_by(ScheduleRun.id.desc()))).scalars().first()


async def check_room_conflicts(
    session: AsyncSession,
    *,
    term_id: int,
    room_ids: list[int],
    day: int | None,
    start_period: int,
    end_period: int,
    weeks: list[int],
    exclude_meeting_request_id: int | None = None,
    exclude_assignment_id: int | None = None,
    run_id: int | None = None,
) -> list[dict[str, Any]]:
    if day is None:
        return []
    conflicts: list[dict[str, Any]] = []
    week_set = set(weeks)
    rooms = (
        {r.id: r for r in (await session.execute(select(Room).where(Room.id.in_(room_ids)))).scalars()}
        if room_ids
        else {}
    )
    blocks = (
        (
            await session.execute(
                select(Block).where(Block.term_id == term_id, Block.room_id.in_(room_ids), Block.archived.is_(False))
            )
        )
        .scalars()
        .all()
    )
    for b in blocks:
        bday = b.day or (b.date.isoweekday() if b.date else None)
        if bday != day or not _overlap(start_period, end_period, b.start_period, b.end_period):
            continue
        bweeks = {int(w) for w in (b.weeks or [])}
        if bweeks and week_set and not (bweeks & week_set):
            continue
        conflicts.append(
            {
                "kind": "block",
                "id": b.id,
                "room_id": b.room_id,
                "room": rooms[b.room_id].display_name if b.room_id in rooms else None,
                "label": b.label,
                "day": bday,
                "start_period": b.start_period,
                "end_period": b.end_period,
                "weeks": sorted(bweeks & week_set) if week_set else sorted(bweeks),
            }
        )
    run = await session.get(ScheduleRun, run_id) if run_id else await active_run_for_term(session, term_id)
    if run is not None:
        q = select(Assignment).where(Assignment.run_id == run.id, Assignment.day == day, Assignment.archived.is_(False))
        for a in (await session.execute(q)).scalars():
            if exclude_assignment_id and a.id == exclude_assignment_id:
                continue
            if exclude_meeting_request_id and a.meeting_request_id == exclude_meeting_request_id:
                continue
            if not set(int(r) for r in (a.room_ids or [])) & set(room_ids):
                continue
            if not _overlap(start_period, end_period, a.start_period, a.end_period):
                continue
            aweeks = {int(w) for w in (a.weeks or ([a.week] if a.week else []))}
            if aweeks and week_set and not (aweeks & week_set):
                continue
            conflicts.append(
                {
                    "kind": "assignment",
                    "id": a.id,
                    "run_id": run.id,
                    "room_id": next((int(r) for r in a.room_ids if int(r) in rooms), None),
                    "label": a.label,
                    "meeting_request_id": a.meeting_request_id,
                    "exam_request_id": a.exam_request_id,
                    "day": a.day,
                    "start_period": a.start_period,
                    "end_period": a.end_period,
                    "weeks": sorted(aweeks & week_set) if week_set else sorted(aweeks),
                }
            )
    return conflicts


async def check_meeting_room(session: AsyncSession, mr: MeetingRequest, room_ids: list[int]) -> list[dict[str, Any]]:
    section = await session.get(Section, mr.section_id)
    assert section is not None
    if mr.start_period is None or mr.end_period is None:
        return []
    return await check_room_conflicts(
        session,
        term_id=section.term_id,
        room_ids=room_ids,
        day=mr.day,
        start_period=mr.start_period,
        end_period=mr.end_period,
        weeks=[int(w) for w in (mr.weeks or [])],
        exclude_meeting_request_id=mr.id,
    )
