"""Room x period matrix for a run (one week), used by the UI and the xlsx export, plus the
assignment enrichment shared by ``/runs/{id}/assignments``, ``/grid`` and the move/lock endpoints."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers.normalize import PERIODS
from app.models import (
    Assignment,
    Block,
    Course,
    ExamRequest,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
)
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


@dataclass
class Enrichment:
    """Per-assignment data the UI needs for tooltips, capacity checks and conflict highlighting."""

    display_label: str = "?"
    room_codes: list[str] = field(default_factory=list)
    course_code: str | None = None
    course_name: str | None = None
    section_label: str | None = None
    program_name: str | None = None
    class_year: int | None = None
    size: int = 0
    enrolment: int | None = None
    instructors: list[str] = field(default_factory=list)
    capacity: int | None = None
    week_set: list[int] = field(default_factory=list)
    is_conflict: bool = False
    conflict_reasons: list[str] = field(default_factory=list)

    @property
    def instructor(self) -> str | None:
        return " / ".join(self.instructors) if self.instructors else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "display_label": self.display_label,
            "room_codes": self.room_codes,
            "course_code": self.course_code,
            "course_name": self.course_name,
            "section_label": self.section_label,
            "program_name": self.program_name,
            "class_year": self.class_year,
            "size": self.size,
            "enrolment": self.enrolment,
            "instructors": self.instructors,
            "instructor": self.instructor,
            "capacity": self.capacity,
            "week_set": self.week_set,
            "is_conflict": self.is_conflict,
            "conflict_reasons": self.conflict_reasons,
        }


def assignment_weeks(a: Assignment) -> set[int]:
    if a.weeks:
        return {int(w) for w in a.weeks}
    return {a.week} if a.week else set()


def _weeks_overlap(a: set[int], b: set[int]) -> bool:
    return not a or not b or bool(a & b)


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


async def enrich_assignments(
    session: AsyncSession,
    run: ScheduleRun,
    rows: list[Assignment],
    *,
    all_rows: list[Assignment] | None = None,
    rooms_by_id: dict[int, Room] | None = None,
    blocks: list[Block] | None = None,
) -> dict[int, Enrichment]:
    """Return ``assignment.id -> Enrichment`` for ``rows``.

    Conflicts are computed against *every* non-archived assignment of the run (``all_rows``; loaded
    when not given) and the term's blocks: two assignments share a room on the same day with
    overlapping periods and weeks, an assignment sits on a block, or the group does not fit the room.
    """
    if rooms_by_id is None:
        rooms_by_id = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    if all_rows is None:
        all_rows = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
                )
            ).scalars()
        )
    if blocks is None:
        blocks = list(
            (
                await session.execute(select(Block).where(Block.term_id == run.term_id, Block.archived.is_(False)))
            ).scalars()
        )
    labels = await assignment_labels(session, rows)
    out: dict[int, Enrichment] = {}

    # request / section / course / instructor lookups
    mr_ids = [a.meeting_request_id for a in rows if a.meeting_request_id]
    ex_ids = [a.exam_request_id for a in rows if a.exam_request_id]
    meetings: dict[int, MeetingRequest] = {}
    if mr_ids:
        q = (
            select(MeetingRequest)
            .where(MeetingRequest.id.in_(mr_ids))
            .options(
                selectinload(MeetingRequest.section).selectinload(Section.course),
                selectinload(MeetingRequest.section).selectinload(Section.program),
                selectinload(MeetingRequest.section)
                .selectinload(Section.instructors)
                .selectinload(SectionInstructor.instructor),
            )
        )
        meetings = {m.id: m for m in (await session.execute(q)).scalars()}
    exams: dict[int, ExamRequest] = {}
    if ex_ids:
        qe = select(ExamRequest).where(ExamRequest.id.in_(ex_ids)).options(selectinload(ExamRequest.program))
        exams = {e.id: e for e in (await session.execute(qe)).scalars()}
    # exam cohorts merged by merge_key share a room: size = sum of the cohort
    cohort_size: dict[str, int] = defaultdict(int)
    if exams:
        keys = {e.merge_key for e in exams.values() if e.merge_key}
        if keys:
            for mk, enrol in await session.execute(
                select(ExamRequest.merge_key, ExamRequest.enrolment).where(
                    ExamRequest.term_id == run.term_id, ExamRequest.merge_key.in_(keys), ExamRequest.archived.is_(False)
                )
            ):
                cohort_size[mk] += int(enrol or 0)

    # index of the whole run for overlap checks: (room, day) -> assignments
    by_room_day: dict[tuple[int, int], list[Assignment]] = defaultdict(list)
    for a in all_rows:
        for r in a.room_ids or []:
            by_room_day[(int(r), a.day)].append(a)
    blocks_by_room_day: dict[tuple[int, int], list[Block]] = defaultdict(list)
    for b in blocks:
        bday = b.day or (b.date.isoweekday() if b.date else None)
        if bday is not None:
            blocks_by_room_day[(b.room_id, bday)].append(b)

    for a in rows:
        e = Enrichment(display_label=labels[a.id])
        room_ids = [int(r) for r in a.room_ids or []]
        e.room_codes = [rooms_by_id[r].display_name if r in rooms_by_id else str(r) for r in room_ids]
        e.week_set = sorted(assignment_weeks(a))
        exam = run.kind == "EXAM"
        if a.meeting_request_id and a.meeting_request_id in meetings:
            mr = meetings[a.meeting_request_id]
            sec = mr.section
            e.course_code = sec.course.display_code
            e.course_name = sec.course.name
            e.section_label = sec.label
            e.program_name = sec.program.name if sec.program else None
            e.class_year = sec.class_year
            e.enrolment = sec.enrolment
            e.size = int(sec.enrolment or mr.requested_capacity or 0)
            e.instructors = [si.instructor.full_name for si in sec.instructors]
        elif a.exam_request_id and a.exam_request_id in exams:
            ex = exams[a.exam_request_id]
            e.course_code = ex.course_code
            e.course_name = ex.course_name
            e.program_name = ex.program.name if ex.program else None
            e.class_year = ex.class_year
            e.enrolment = ex.enrolment
            e.size = cohort_size[ex.merge_key] if ex.merge_key and cohort_size[ex.merge_key] else int(ex.enrolment or 0)
            e.instructors = [ex.instructor_text] if ex.instructor_text else []
        elif a.course_codes:
            e.course_code = str(a.course_codes[0])
        caps = [
            (rooms_by_id[r].exam_capacity if exam else rooms_by_id[r].capacity) or 0 for r in room_ids if r in rooms_by_id
        ]
        e.capacity = sum(caps) if caps else None
        reasons: list[str] = []
        if e.capacity is not None and e.size and e.size > e.capacity and not exam:
            reasons.append(f"capacity: {e.size} > {e.capacity}")
        aw = assignment_weeks(a)
        for r in room_ids:
            for other in by_room_day[(r, a.day)]:
                if other.id == a.id or not _overlap(a.start_period, a.end_period, other.start_period, other.end_period):
                    continue
                if not _weeks_overlap(aw, assignment_weeks(other)):
                    continue
                if exam and other.exam_request_id and a.exam_request_id:
                    ea, eb = exams.get(a.exam_request_id), None
                    if ea is not None and ea.merge_key:
                        # members of the same merged cohort legitimately share the room(s)
                        eb_key = (
                            await session.execute(select(ExamRequest.merge_key).where(ExamRequest.id == other.exam_request_id))
                        ).scalar_one_or_none()
                        if eb_key == ea.merge_key:
                            continue
                    del eb
                    continue  # exams may share a room (seat budget is checked by the solver)
                rc = rooms_by_id[r].display_name if r in rooms_by_id else str(r)
                reasons.append(f"room overlap: {rc} with #{other.id}")
                break
            for b in blocks_by_room_day[(r, a.day)]:
                if not _overlap(a.start_period, a.end_period, b.start_period, b.end_period):
                    continue
                if not _weeks_overlap(aw, {int(w) for w in (b.weeks or [])}):
                    continue
                rc = rooms_by_id[r].display_name if r in rooms_by_id else str(r)
                reasons.append(f"block: {rc} {b.label}")
                break
        e.conflict_reasons = reasons
        e.is_conflict = bool(reasons)
        out[a.id] = e
    return out


async def build_grid(
    session: AsyncSession, run: ScheduleRun, week: int | None, include_blocks: bool = True
) -> dict[str, Any]:
    term = await session.get(Term, run.term_id)
    assert term is not None
    week = week or 1
    q = select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
    all_rows = list((await session.execute(q)).scalars())
    assignments = [
        a for a in all_rows if a.week == week or a.week is None and (not a.weeks or week in [int(w) for w in a.weeks])
    ]
    rooms = (await session.execute(select(Room).order_by(Room.code))).scalars().all()
    rooms_by_id = {r.id: r for r in rooms}
    term_blocks = list(
        (await session.execute(select(Block).where(Block.term_id == term.id, Block.archived.is_(False)))).scalars()
    )
    enrich = await enrich_assignments(
        session, run, assignments, all_rows=all_rows, rooms_by_id=rooms_by_id, blocks=term_blocks
    )
    used_room_ids = {int(r) for a in assignments for r in (a.room_ids or [])}
    blocks: list[Block] = []
    if include_blocks:
        blocks = [b for b in term_blocks if not b.weeks or week in [int(w) for w in b.weeks]]
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
                en = enrich[a.id]
                for p in range(a.start_period, a.end_period + 1):
                    cells[p - 1] = {
                        "kind": "assignment",
                        "id": a.id,
                        "label": en.display_label,
                        "start_period": a.start_period,
                        "end_period": a.end_period,
                        "head": p == a.start_period,
                        "locked": a.is_locked,
                        "origin": a.origin,
                        "tags": a.tags or [],
                        "notes": a.notes,
                        "meeting_request_id": a.meeting_request_id,
                        "exam_request_id": a.exam_request_id,
                        "room_ids": [int(x) for x in a.room_ids or []],
                        "week": a.week,
                        "weeks": en.week_set,
                        "date": a.date.isoformat() if a.date else None,
                        **{k: v for k, v in en.as_dict().items() if k not in {"display_label", "room_codes", "week_set"}},
                        "room_codes": en.room_codes,
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
                            "source": b.source,
                            "weeks": [int(w) for w in (b.weeks or [])],
                        }
            day_rooms.append(
                {
                    "room_id": r.id,
                    "code": r.code,
                    "display_name": r.display_name,
                    "capacity": r.capacity,
                    "exam_capacity": r.exam_capacity,
                    "tags": r.tags or [],
                    "building_id": r.building_id,
                    "floor": r.floor,
                    "is_bookable": r.is_bookable,
                    "cells": cells,
                }
            )
        d = date_for(term, week, day)
        days.append({"day": day, "label": day_label(day), "date": d.isoformat() if d else None, "rooms": day_rooms})
    week_start = date_for(term, week, 1)
    return {
        "run_id": run.id,
        "term_id": term.id,
        "week": week,
        "week_start": week_start.isoformat() if week_start else None,
        "periods": [{"index": p.index, "start": f"{p.start:%H:%M}", "end": f"{p.end:%H:%M}"} for p in PERIODS],
        "days": days,
        "assignments": len(assignments),
        "blocks": len(blocks),
        "conflicts": sum(1 for a in assignments if enrich[a.id].is_conflict),
    }
