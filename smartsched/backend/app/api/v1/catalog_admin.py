"""From-scratch programme creation (P19-C1 / P19-C2): write endpoints next to the read-only reference lists.

=========================================================  ==========================  =====================
Route                                                      Permission                  Notes
=========================================================  ==========================  =====================
``POST /faculties``, ``PUT|DELETE /faculties/{id}``        planning.edit               409 on a canonical clash
``POST /programs``, ``PUT|DELETE /programs/{id}``          planning.edit               faculty link, İÖ flag
``POST /courses``, ``PUT|DELETE /courses/{id}``            planning.edit               409 on a course_key clash
``GET /courses/code-check?code=``                          planning.view               the wizard's checker
``POST /instructors``, ``PUT|DELETE /instructors/{id}``    planning.edit               placeholders refused
``POST /sections``, ``GET|PUT|DELETE /sections/{id}``      planning.edit (GET: view)   DELETE archives
``POST /sections/{id}/pattern``                            planning.edit               the weekly expander
``POST /requests/meetings``, ``DELETE /requests/meetings/{id}``  planning.edit         DELETE archives
``POST /requests/exams``, ``DELETE /requests/exams/{id}``  planning.edit               DELETE archives
=========================================================  ==========================  =====================

``DELETE ...?purge=true`` hard-deletes a hand-made (``MAN:``) section / meeting / exam that no run uses. The
semantics live in :mod:`app.services.catalog_admin`; the GET lists stay in ``reference.py`` / ``requests.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import DB, require_permission
from app.models import (
    Course,
    ExamRequest,
    Faculty,
    Instructor,
    MeetingRequest,
    Program,
    Section,
    SectionInstructor,
    User,
)
from app.schemas.catalog import CourseOut, FacultyOut, InstructorOut, ProgramOut, SectionOut
from app.schemas.catalog_admin import (
    CourseCodeCheckOut,
    CourseIn,
    CourseUpdate,
    DeleteOut,
    ExamCreateIn,
    FacultyIn,
    FacultyUpdate,
    InstructorIn,
    InstructorUpdate,
    MeetingCreateIn,
    PatternIn,
    PatternOut,
    ProgramIn,
    ProgramUpdate,
    SectionAdminOut,
    SectionIn,
    SectionInstructorOut,
    SectionUpdate,
)
from app.schemas.requests import ExamRequestOut, MeetingRequestOut
from app.services import catalog_admin as svc

router = APIRouter(tags=["catalog-admin"])

#: the permission of every planning write (``deps.Planner`` is the same check under its historic name)
Editor = Annotated[User, Depends(require_permission("planning.edit"))]
Reader = Annotated[User, Depends(require_permission("planning.view"))]


async def _run[T](db: DB, op: Awaitable[T]) -> T:
    """Run a service call, commit on success, roll back and map :class:`svc.CatalogError` to its HTTP status. A unique
    index tripped by a concurrent identical write (two coordinators adding ``MBG 532`` at once) is a 409 too."""
    try:
        result = await op
        await db.commit()
    except svc.CatalogError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.detail) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "the row was created or changed by someone else meanwhile; reload and retry") from exc
    return result


# --------------------------------------------------------------------------- faculties


@router.post("/faculties", response_model=FacultyOut, status_code=201)
async def create_faculty(body: FacultyIn, db: DB, user: Editor) -> Faculty:
    f = await _run(db, svc.create_faculty(db, user, body.name))
    await db.refresh(f)
    return f


@router.put("/faculties/{faculty_id}", response_model=FacultyOut)
async def update_faculty(faculty_id: int, body: FacultyUpdate, db: DB, user: Editor) -> Faculty:
    f = await _run(db, svc.update_faculty(db, user, faculty_id, body.name))
    await db.refresh(f)
    return f


@router.delete("/faculties/{faculty_id}", response_model=DeleteOut)
async def delete_faculty(faculty_id: int, db: DB, user: Editor) -> DeleteOut:
    audit_id = await _run(db, svc.delete_faculty(db, user, faculty_id))
    return DeleteOut(id=faculty_id, action="deleted", audit_id=audit_id)


# --------------------------------------------------------------------------- programmes


@router.post("/programs", response_model=ProgramOut, status_code=201)
async def create_program(body: ProgramIn, db: DB, user: Editor) -> Program:
    p = await _run(db, svc.create_program(db, user, **body.model_dump()))
    await db.refresh(p)
    return p


@router.put("/programs/{program_id}", response_model=ProgramOut)
async def update_program(program_id: int, body: ProgramUpdate, db: DB, user: Editor) -> Program:
    p = await _run(db, svc.update_program(db, user, program_id, body.model_dump(exclude_unset=True)))
    await db.refresh(p)
    return p


@router.delete("/programs/{program_id}", response_model=DeleteOut)
async def delete_program(program_id: int, db: DB, user: Editor) -> DeleteOut:
    audit_id = await _run(db, svc.delete_program(db, user, program_id))
    return DeleteOut(id=program_id, action="deleted", audit_id=audit_id)


# --------------------------------------------------------------------------- courses


@router.get("/courses/code-check", response_model=CourseCodeCheckOut)
async def course_code_check(code: str, db: DB, _: Reader) -> dict[str, Any]:
    return await svc.check_course_code(db, code)


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(body: CourseIn, db: DB, user: Editor) -> Course:
    c = await _run(db, svc.create_course(db, user, body.model_dump(exclude_unset=True)))
    await db.refresh(c)
    return c


@router.put("/courses/{course_id}", response_model=CourseOut)
async def update_course(course_id: int, body: CourseUpdate, db: DB, user: Editor) -> Course:
    c = await _run(db, svc.update_course(db, user, course_id, body.model_dump(exclude_unset=True)))
    await db.refresh(c)
    return c


@router.delete("/courses/{course_id}", response_model=DeleteOut)
async def delete_course(course_id: int, db: DB, user: Editor) -> DeleteOut:
    audit_id = await _run(db, svc.delete_course(db, user, course_id))
    return DeleteOut(id=course_id, action="deleted", audit_id=audit_id)


# --------------------------------------------------------------------------- instructors


@router.post("/instructors", response_model=InstructorOut, status_code=201)
async def create_instructor(body: InstructorIn, db: DB, user: Editor) -> Instructor:
    i = await _run(db, svc.create_instructor(db, user, body.model_dump(exclude_unset=True)))
    await db.refresh(i)
    return i


@router.put("/instructors/{instructor_id}", response_model=InstructorOut)
async def update_instructor(instructor_id: int, body: InstructorUpdate, db: DB, user: Editor) -> Instructor:
    i = await _run(db, svc.update_instructor(db, user, instructor_id, body.model_dump(exclude_unset=True)))
    await db.refresh(i)
    return i


@router.delete("/instructors/{instructor_id}", response_model=DeleteOut)
async def delete_instructor(instructor_id: int, db: DB, user: Editor) -> DeleteOut:
    audit_id = await _run(db, svc.delete_instructor(db, user, instructor_id))
    return DeleteOut(id=instructor_id, action="deleted", audit_id=audit_id)


# --------------------------------------------------------------------------- sections


async def _section_out(db: DB, section_id: int) -> SectionAdminOut:
    sec = await svc.load_section(db, section_id)
    base = SectionOut.model_validate(sec).model_dump()
    count = (
        await db.execute(
            select(func.count(MeetingRequest.id)).where(
                MeetingRequest.section_id == sec.id, MeetingRequest.archived.is_(False)
            )
        )
    ).scalar_one()
    return SectionAdminOut(
        **{
            **base,
            "course_code": sec.course.display_code,
            "course_name": sec.course.name,
            "program_name": sec.program.name if sec.program else None,
        },
        source_key=sec.source_key,
        instructors=[
            SectionInstructorOut(
                instructor_id=si.instructor_id,
                full_name=si.instructor.full_name,
                title=si.instructor.title,
                role=si.role,
            )
            for si in sorted(sec.instructors, key=lambda si: (si.role != "PRIMARY", si.instructor_id))
        ],
        meeting_count=int(count),
    )


@router.post("/sections", response_model=SectionAdminOut, status_code=201)
async def create_section(body: SectionIn, db: DB, user: Editor) -> SectionAdminOut:
    sec = await _run(db, svc.create_section(db, user, body.model_dump()))
    return await _section_out(db, sec.id)


@router.get("/sections/{section_id}", response_model=SectionAdminOut)
async def get_section(section_id: int, db: DB, _: Reader) -> SectionAdminOut:
    try:
        return await _section_out(db, section_id)
    except svc.NotFound as exc:
        raise HTTPException(404, exc.detail) from exc


@router.put("/sections/{section_id}", response_model=SectionAdminOut)
async def update_section(section_id: int, body: SectionUpdate, db: DB, user: Editor) -> SectionAdminOut:
    await _run(db, svc.update_section(db, user, section_id, body.model_dump(exclude_unset=True)))
    return await _section_out(db, section_id)


@router.delete("/sections/{section_id}", response_model=DeleteOut)
async def delete_section(section_id: int, db: DB, user: Editor, purge: bool = False) -> DeleteOut:
    action, audit_id = await _run(db, svc.archive_section(db, user, section_id, purge=purge))
    return DeleteOut(id=section_id, action=action, audit_id=audit_id)


# --------------------------------------------------------------------------- meetings, pattern, exams


async def _meetings_out(db: DB, ids: list[int]) -> list[MeetingRequestOut]:
    if not ids:
        return []
    rows = (
        await db.execute(
            select(MeetingRequest)
            .where(MeetingRequest.id.in_(ids))
            .options(
                selectinload(MeetingRequest.section).selectinload(Section.course),
                selectinload(MeetingRequest.section).selectinload(Section.program),
                selectinload(MeetingRequest.section)
                .selectinload(Section.instructors)
                .selectinload(SectionInstructor.instructor),
            )
            .order_by(MeetingRequest.id)
            .execution_options(populate_existing=True)
        )
    ).scalars()
    out = []
    for mr in rows:
        d = MeetingRequestOut.model_validate(mr)
        sec = mr.section
        d.course_code = sec.course.display_code
        d.course_name = sec.course.name
        d.section_label = sec.label
        d.program_name = sec.program.name if sec.program else None
        d.enrolment = sec.enrolment
        d.mode = sec.mode
        d.instructors = [si.instructor.full_name for si in sec.instructors]
        out.append(d)
    return out


@router.post("/sections/{section_id}/pattern", response_model=PatternOut, status_code=201)
async def apply_pattern(section_id: int, body: PatternIn, db: DB, user: Editor) -> PatternOut:
    """Expand a weekly pattern into meeting requests (``app.services.patterns``); with ``replace`` (default) the
    section's earlier hand-made meetings are archived first."""
    sec, created, archived_ids, warnings, audit_id = await _run(
        db, svc.apply_pattern(db, user, section_id, body.pattern(), replace=body.replace)
    )
    ids = [m.id for m in created]
    return PatternOut(
        section_id=sec.id,
        created=await _meetings_out(db, ids),
        archived_ids=archived_ids,
        warnings=warnings,
        audit_id=audit_id,
    )


@router.post("/requests/meetings", response_model=MeetingRequestOut, status_code=201)
async def create_meeting(body: MeetingCreateIn, db: DB, user: Editor) -> MeetingRequestOut:
    data = body.model_dump(exclude_unset=True)
    if body.room_needs is not None:
        data["room_needs"] = body.room_needs.model_dump(exclude_none=True)
    mr, _warnings = await _run(db, svc.create_meeting(db, user, data))
    return (await _meetings_out(db, [mr.id]))[0]


@router.delete("/requests/meetings/{meeting_id}", response_model=DeleteOut)
async def delete_meeting(meeting_id: int, db: DB, user: Editor, purge: bool = False) -> DeleteOut:
    action, audit_id = await _run(db, svc.archive_meeting(db, user, meeting_id, purge=purge))
    return DeleteOut(id=meeting_id, action=action, audit_id=audit_id)


@router.post("/requests/exams", response_model=ExamRequestOut, status_code=201)
async def create_exam(body: ExamCreateIn, db: DB, user: Editor) -> ExamRequestOut:
    ex = await _run(db, svc.create_exam(db, user, body.model_dump()))
    row = (
        await db.execute(
            select(ExamRequest)
            .where(ExamRequest.id == ex.id)
            .options(selectinload(ExamRequest.program))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    out = ExamRequestOut.model_validate(row)
    out.program_name = row.program.name if row.program else None
    return out


@router.delete("/requests/exams/{exam_id}", response_model=DeleteOut)
async def delete_exam(exam_id: int, db: DB, user: Editor, purge: bool = False) -> DeleteOut:
    action, audit_id = await _run(db, svc.archive_exam(db, user, exam_id, purge=purge))
    return DeleteOut(id=exam_id, action=action, audit_id=audit_id)


# Program wizard drafts + wizard reads (P19-W-01..W-08, app/api/v1/program_drafts.py) are mounted through this router,
# so the wizard's write path (drafts, one transactional commit) lives next to the per-row endpoints it replaces.
from app.api.v1 import program_drafts as _program_drafts  # noqa: E402

router.include_router(_program_drafts.router)
