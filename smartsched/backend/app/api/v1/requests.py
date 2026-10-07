from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, Planner, Viewer
from app.importers import normalize as n
from app.models import Course, ExamRequest, MeetingRequest, Program, Section, SectionInstructor
from app.schemas.common import Page
from app.schemas.requests import (
    CheckRoomIn,
    CheckRoomOut,
    ExamCohortOut,
    ExamRequestOut,
    ExamRequestUpdate,
    MeetingRequestOut,
    MeetingRequestUpdate,
)
from app.services.conflicts import check_meeting_room

router = APIRouter(prefix="/requests", tags=["requests"])


def _meeting_out(mr: MeetingRequest) -> MeetingRequestOut:
    d = MeetingRequestOut.model_validate(mr)
    sec = mr.section
    d.course_code = sec.course.display_code
    d.course_name = sec.course.name
    d.section_label = sec.label
    d.program_name = sec.program.name if sec.program else None
    d.enrolment = sec.enrolment
    d.mode = sec.mode
    d.instructors = [si.instructor.full_name for si in sec.instructors]
    return d


_MEETING_OPTS = (
    selectinload(MeetingRequest.section).selectinload(Section.course),
    selectinload(MeetingRequest.section).selectinload(Section.program),
    selectinload(MeetingRequest.section).selectinload(Section.instructors).selectinload(SectionInstructor.instructor),
)


@router.get("/meetings", response_model=Page[MeetingRequestOut])
async def list_meetings(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    status: str | None = None,
    needs_room: bool | None = None,
    day: int | None = None,
    program_id: int | None = None,
    search: str | None = None,
    include_archived: bool = False,
    limit: int = Query(100, le=2000),
    offset: int = 0,
) -> dict[str, Any]:
    q = (
        select(MeetingRequest)
        .join(Section, Section.id == MeetingRequest.section_id)
        .options(*_MEETING_OPTS)
        .order_by(MeetingRequest.id)
    )
    if term_id:
        q = q.where(Section.term_id == term_id)
    if status:
        q = q.where(MeetingRequest.status == status)
    if needs_room is not None:
        q = q.where(MeetingRequest.needs_room.is_(needs_room))
    if day:
        q = q.where(MeetingRequest.day == day)
    if program_id:
        q = q.where(Section.program_id == program_id)
    if not include_archived:
        q = q.where(MeetingRequest.archived.is_(False))
    if search:
        s = n.tr_upper(search).replace(" ", "")
        q = q.join(Course, Course.id == Section.course_id).where(
            or_(Course.code.like(f"%{s}%"), Course.name.like(f"%{search}%"))
        )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = [_meeting_out(m) for m in (await db.execute(q.limit(limit).offset(offset))).scalars()]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def _meeting(db: DB, mr_id: int) -> MeetingRequest:
    mr = (
        await db.execute(select(MeetingRequest).where(MeetingRequest.id == mr_id).options(*_MEETING_OPTS))
    ).scalar_one_or_none()
    if mr is None:
        raise HTTPException(404, "meeting request not found")
    return mr


@router.get("/meetings/{mr_id}", response_model=MeetingRequestOut)
async def get_meeting(mr_id: int, db: DB, _: Viewer) -> MeetingRequestOut:
    return _meeting_out(await _meeting(db, mr_id))


@router.put("/meetings/{mr_id}", response_model=MeetingRequestOut)
async def update_meeting(mr_id: int, body: MeetingRequestUpdate, db: DB, _: Planner) -> MeetingRequestOut:
    mr = await _meeting(db, mr_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(mr, k, v)
    if body.days is not None and len(body.days) == 1:
        mr.day = body.days[0]
    await db.commit()
    return _meeting_out(await _meeting(db, mr_id))


@router.post("/meetings/{mr_id}/check-room", response_model=CheckRoomOut)
async def check_room(mr_id: int, body: CheckRoomIn, db: DB, _: Viewer) -> CheckRoomOut:
    mr = await _meeting(db, mr_id)
    conflicts = await check_meeting_room(db, mr, body.room_ids)
    return CheckRoomOut(ok=not conflicts, conflicts=conflicts)


def _exam_out(ex: ExamRequest) -> ExamRequestOut:
    d = ExamRequestOut.model_validate(ex)
    d.program_name = ex.program.name if ex.program else None
    return d


@router.get("/exams")
async def list_exams(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    status: str | None = None,
    group_by: str | None = Query(None, pattern="^(merge_key)$"),
    date: str | None = None,
    search: str | None = None,
    include_archived: bool = False,
    limit: int = Query(200, le=5000),
    offset: int = 0,
) -> dict[str, Any]:
    q = (
        select(ExamRequest)
        .options(selectinload(ExamRequest.program))
        .order_by(ExamRequest.date, ExamRequest.start_period, ExamRequest.course_code)
    )
    if term_id:
        q = q.where(ExamRequest.term_id == term_id)
    if status:
        q = q.where(ExamRequest.status == status)
    if date:
        q = q.where(ExamRequest.date == date)
    if not include_archived:
        q = q.where(ExamRequest.archived.is_(False))
    if search:
        s = n.tr_upper(search).replace(" ", "")
        q = q.where(or_(ExamRequest.course_code.like(f"%{s}%"), ExamRequest.course_name.like(f"%{search}%")))
    if group_by == "merge_key":
        rows = list((await db.execute(q)).scalars())
        groups: dict[str, list[ExamRequest]] = defaultdict(list)
        for ex in rows:
            groups[ex.merge_key or f"single:{ex.id}"].append(ex)
        cohorts = []
        for key, members in groups.items():
            head = members[0]
            statuses = {m.status for m in members}
            cohorts.append(
                ExamCohortOut(
                    merge_key=key,
                    course_code=head.course_code,
                    course_name=head.course_name,
                    date=head.date,
                    start_period=head.start_period,
                    end_period=head.end_period,
                    start_time=head.start_time,
                    end_time=head.end_time,
                    enrolment=sum(int(m.enrolment or 0) for m in members),
                    programs=[m.program.name if m.program else "?" for m in members],
                    request_ids=[m.id for m in members],
                    definitive_room_ids=list(
                        dict.fromkeys(int(r) for m in members for r in (m.definitive_room_ids or []))
                    ),
                    status="LOCKED"
                    if statuses == {"LOCKED"}
                    else ("NEEDS_REVIEW" if "NEEDS_REVIEW" in statuses else head.status),
                )
            )
        total = len(cohorts)
        return {
            "items": [c.model_dump() for c in cohorts[offset : offset + limit]],
            "total": total,
            "limit": limit,
            "offset": offset,
            "group_by": "merge_key",
        }
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = [_exam_out(e).model_dump() for e in (await db.execute(q.limit(limit).offset(offset))).scalars()]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.put("/exams/{ex_id}", response_model=ExamRequestOut)
async def update_exam(ex_id: int, body: ExamRequestUpdate, db: DB, _: Planner) -> ExamRequestOut:
    ex = (
        await db.execute(select(ExamRequest).where(ExamRequest.id == ex_id).options(selectinload(ExamRequest.program)))
    ).scalar_one_or_none()
    if ex is None:
        raise HTTPException(404, "exam request not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ex, k, v)
    await db.commit()
    await db.refresh(ex)
    return _exam_out(ex)


@router.get("/stats")
async def request_stats(db: DB, _: Viewer, term_id: int) -> dict[str, Any]:
    q = (
        select(MeetingRequest.status, func.count())
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(Section.term_id == term_id, MeetingRequest.archived.is_(False))
        .group_by(MeetingRequest.status)
    )
    meetings = {k: v for k, v in (await db.execute(q)).all()}
    qe = (
        select(ExamRequest.status, func.count())
        .where(ExamRequest.term_id == term_id, ExamRequest.archived.is_(False))
        .group_by(ExamRequest.status)
    )
    exams = {k: v for k, v in (await db.execute(qe)).all()}
    programs = (
        await db.execute(select(func.count(func.distinct(Section.program_id))).where(Section.term_id == term_id))
    ).scalar_one()
    return {
        "term_id": term_id,
        "meetings": meetings,
        "exams": exams,
        "programs": programs,
        "program_count": (await db.execute(select(func.count(Program.id)))).scalar_one(),
    }
