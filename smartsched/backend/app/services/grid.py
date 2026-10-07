"""Room x period matrix for a run (one week), used by the UI and the xlsx export."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers.normalize import PERIODS
from app.models import Assignment, Block, ExamRequest, MeetingRequest, Room, ScheduleRun, Section, Term
from app.services.calendar import date_for, day_label


async def assignment_labels(session: AsyncSession, assignments: list[Assignment]) -> dict[int, str]:
    labels: dict[int, str] = {}
    mr_ids = [a.meeting_request_id for a in assignments if a.meeting_request_id]
    ex_ids = [a.exam_request_id for a in assignments if a.exam_request_id]
    mr_labels: dict[int, str] = {}
    if mr_ids:
        rows = await session.execute(
            select(MeetingRequest.id, Section.label, Section.course_id)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(MeetingRequest.id.in_(mr_ids))
        )
        from app.models import Course

        courses = {c.id: c.display_code for c in (await session.execute(select(Course))).scalars()}
        for mid, label, cid in rows:
            mr_labels[mid] = f"{courses.get(cid, '?')}{' §' + label if label else ''}"
    ex_labels: dict[int, str] = {}
    if ex_ids:
        for eid, code in await session.execute(
            select(ExamRequest.id, ExamRequest.course_code).where(ExamRequest.id.in_(ex_ids))
        ):
            ex_labels[eid] = code
    for a in assignments:
        labels[a.id] = (
            a.label
            or (mr_labels.get(a.meeting_request_id or -1) if a.meeting_request_id else None)
            or (ex_labels.get(a.exam_request_id or -1) if a.exam_request_id else None)
            or "?"
        )
    return labels


async def build_grid(
    session: AsyncSession, run: ScheduleRun, week: int | None, include_blocks: bool = True
) -> dict[str, Any]:
    term = await session.get(Term, run.term_id)
    assert term is not None
    week = week or 1
    q = select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
    assignments = [
        a
        for a in (await session.execute(q)).scalars()
        if a.week == week or a.week is None and (not a.weeks or week in [int(w) for w in a.weeks])
    ]
    labels = await assignment_labels(session, assignments)
    rooms = (await session.execute(select(Room).order_by(Room.code))).scalars().all()
    used_room_ids = {int(r) for a in assignments for r in (a.room_ids or [])}
    blocks: list[Block] = []
    if include_blocks:
        blocks = [
            b
            for b in (
                await session.execute(select(Block).where(Block.term_id == term.id, Block.archived.is_(False)))
            ).scalars()
            if not b.weeks or week in [int(w) for w in b.weeks]
        ]
        used_room_ids |= {b.room_id for b in blocks}
    rooms = [r for r in rooms if r.is_bookable or r.id in used_room_ids]
    days: list[dict[str, Any]] = []
    for day in range(1, 8):
        day_rooms = []
        for r in rooms:
            cells: list[dict[str, Any] | None] = [None] * len(PERIODS)
            for a in assignments:
                if a.day != day or r.id not in [int(x) for x in a.room_ids or []]:
                    continue
                for p in range(a.start_period, a.end_period + 1):
                    cells[p - 1] = {
                        "kind": "assignment",
                        "id": a.id,
                        "label": labels[a.id],
                        "start_period": a.start_period,
                        "end_period": a.end_period,
                        "head": p == a.start_period,
                        "locked": a.is_locked,
                        "origin": a.origin,
                        "tags": a.tags or [],
                        "notes": a.notes,
                    }
            for b in blocks:
                bday = b.day or (b.date.isoweekday() if b.date else None)
                if bday != day or b.room_id != r.id:
                    continue
                for p in range(b.start_period, b.end_period + 1):
                    if cells[p - 1] is None:
                        cells[p - 1] = {
                            "kind": "block",
                            "id": b.id,
                            "label": b.label,
                            "start_period": b.start_period,
                            "end_period": b.end_period,
                            "head": p == b.start_period,
                            "tags": b.tags or [],
                            "notes": b.notes,
                        }
            day_rooms.append(
                {
                    "room_id": r.id,
                    "code": r.code,
                    "display_name": r.display_name,
                    "capacity": r.capacity,
                    "exam_capacity": r.exam_capacity,
                    "tags": r.tags or [],
                    "cells": cells,
                }
            )
        d = date_for(term, week, day)
        days.append({"day": day, "label": day_label(day), "date": d.isoformat() if d else None, "rooms": day_rooms})
    return {
        "run_id": run.id,
        "term_id": term.id,
        "week": week,
        "periods": [{"index": p.index, "start": f"{p.start:%H:%M}", "end": f"{p.end:%H:%M}"} for p in PERIODS],
        "days": days,
        "assignments": len(assignments),
        "blocks": len(blocks),
    }
