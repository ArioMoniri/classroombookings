from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, Viewer
from app.importers import normalize as n
from app.models import Course, Faculty, Instructor, Program, Section
from app.schemas.catalog import CourseOut, FacultyOut, InstructorOut, ProgramOut, SectionOut
from app.schemas.common import Page

router = APIRouter(tags=["reference"])


async def _page(db: DB, q: Select[Any], limit: int, offset: int) -> tuple[list[Any], int]:
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = list((await db.execute(q.limit(limit).offset(offset))).scalars())
    return items, total


@router.get("/faculties", response_model=Page[FacultyOut])
async def faculties(
    db: DB, _: Viewer, search: str | None = None, limit: int = Query(100, le=500), offset: int = 0
) -> dict[str, Any]:
    q = select(Faculty).order_by(Faculty.name)
    if search:
        q = q.where(Faculty.canonical_name.like(f"%{n.tr_casefold(search)}%"))
    items, total = await _page(db, q, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/programs", response_model=Page[ProgramOut])
async def programs(
    db: DB,
    _: Viewer,
    search: str | None = None,
    faculty_id: int | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    q = select(Program).order_by(Program.name)
    if search:
        q = q.where(Program.canonical_name.like(f"%{n.tr_casefold(search)}%"))
    if faculty_id:
        q = q.where(Program.faculty_id == faculty_id)
    items, total = await _page(db, q, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/instructors", response_model=Page[InstructorOut])
async def instructors(
    db: DB, _: Viewer, search: str | None = None, limit: int = Query(100, le=500), offset: int = 0
) -> dict[str, Any]:
    q = select(Instructor).order_by(Instructor.full_name)
    if search:
        q = q.where(Instructor.canonical_name.like(f"%{n.tr_casefold(search)}%"))
    items, total = await _page(db, q, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/courses", response_model=Page[CourseOut])
async def courses(
    db: DB, _: Viewer, search: str | None = None, limit: int = Query(100, le=500), offset: int = 0
) -> dict[str, Any]:
    q = select(Course).order_by(Course.code)
    if search:
        s = n.tr_upper(search).replace(" ", "")
        q = q.where(or_(Course.code.like(f"%{s}%"), Course.name.like(f"%{search}%")))
    items, total = await _page(db, q, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/sections", response_model=Page[SectionOut])
async def sections(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    search: str | None = None,
    program_id: int | None = None,
    include_archived: bool = False,
    limit: int = Query(100, le=1000),
    offset: int = 0,
) -> dict[str, Any]:
    q = select(Section).options(selectinload(Section.course), selectinload(Section.program)).order_by(Section.id)
    if term_id:
        q = q.where(Section.term_id == term_id)
    if program_id:
        q = q.where(Section.program_id == program_id)
    if not include_archived:
        q = q.where(Section.archived.is_(False))
    if search:
        s = n.tr_upper(search).replace(" ", "")
        q = q.join(Course, Course.id == Section.course_id).where(
            or_(Course.code.like(f"%{s}%"), Course.name.like(f"%{search}%"))
        )
    items, total = await _page(db, q, limit, offset)
    out = []
    for s_ in items:
        d = SectionOut.model_validate(s_)
        d.course_code = s_.course.display_code
        d.course_name = s_.course.name
        d.program_name = s_.program.name if s_.program else None
        out.append(d)
    return {"items": out, "total": total, "limit": limit, "offset": offset}
