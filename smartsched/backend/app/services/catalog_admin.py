"""From-scratch catalogue writes (P19-C1 / P19-C2): faculties, programmes, courses, instructors, sections,
meeting and exam requests, and the weekly-pattern expander, with no import.

Every write

* normalises its text like the importers (:mod:`app.importers.normalize`: NBSP, Turkish ``İ``/``ı``, comma
  decimals, dotted times, Turkish mode words) and checks duplicates on the importers' keys (``canonical_name``,
  :func:`normalize.course_key`), so a later import of the same entity finds the hand-made row;
* stamps ``source_key="MAN:<uuid4>"`` where the model has one (sections, meeting and exam requests);
* is audited through :func:`app.services.events.publish_event` (``<entity>.create|update|archive|delete`` with
  before/after snapshots; a pattern is one ``section.pattern`` parent with a ``meeting.create`` child per
  meeting);
* archives instead of deleting where the model can (sections, meetings, exams). A hard delete (``purge``) is
  refused while any run's assignment points at the row, because ``Assignment.meeting_request_id`` /
  ``exam_request_id`` are ``SET NULL`` and the plan would silently lose its class. Imported rows are never
  purged (the next import would recreate them).

Errors are :class:`CatalogError` subclasses carrying the HTTP status and a JSON-safe detail; the router maps them.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import replace as dc_replace
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers import normalize as n
from app.models import (
    Assignment,
    AuditEvent,
    Booking,
    BookingSeries,
    Building,
    Course,
    ExamRequest,
    Faculty,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
    User,
)
from app.services import audit
from app.services import patterns as pt
from app.services.events import publish_event

MAN_PREFIX = "MAN:"
MODES = ("F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER")
MAX_ENROLMENT = 2000
#: the only requested tags the solver bridge turns into rules (``solver_bridge.build_solver_input``)
ENFORCED_TAGS = frozenset({"PC", "TIP"})

# --------------------------------------------------------------------------- errors


class CatalogError(Exception):
    status = 400

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra

    @property
    def detail(self) -> dict[str, Any] | str:
        return {"message": self.message, **self.extra} if self.extra else self.message


class NotFound(CatalogError):
    status = 404


class Invalid(CatalogError):
    status = 422


class Conflict(CatalogError):
    status = 409


def man_key() -> str:
    return f"{MAN_PREFIX}{uuid.uuid4()}"


# --------------------------------------------------------------------------- value parsing


def _text(value: Any, what: str, *, required: bool = False, limit: int = 255) -> str | None:
    text = n.clean_text(value)
    if text is None:
        if required:
            raise Invalid(f"{what} is empty")
        return None
    if len(text) > limit:
        raise Invalid(f"{what} is longer than {limit} characters")
    return text


def parse_count(value: Any, what: str, *, hi: int = MAX_ENROLMENT) -> int | None:
    """``80``, ``"80"``, ``"80 kişi"``, ``"\\xa0"`` / ``"-"`` (empty) -> int; time-shaped (``"12:30:00"``, a shifted
    row) and out-of-range values are refused (review D11)."""
    if value is None or isinstance(value, bool):
        if isinstance(value, bool):
            raise Invalid(f"{what} must be a number")
        return None
    if isinstance(value, float) and not value.is_integer():
        raise Invalid(f"{what} must be a whole number (got {value})")
    if isinstance(value, str):
        text = n.clean_text(value)
        if text is None:
            return None
        if re.search(r"\d\s*[:.]\s*\d{2}\b", text) and not re.fullmatch(r"\d+", text):
            raise Invalid(f"{what} {text!r} looks like a time, not a number")
    num = n.parse_int_loose(value)
    if num is None or not 0 <= num <= hi:
        raise Invalid(f"{what} must be a whole number within 0..{hi} (got {value!r})")
    return num


def parse_decimal(value: Any, what: str, *, hi: float = 60.0) -> float | None:
    """``4.5``, ``"4,5"``, ``"4..5"`` -> 4.5 (comma decimals of the planning lists)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise Invalid(f"{what} must be a number")
    if isinstance(value, str) and n.clean_text(value) is None:
        return None
    num = n.parse_float_loose(value)
    if num is None or not 0 <= num <= hi:
        raise Invalid(f"{what} must be a number within 0..{hi:g} (got {value!r})")
    if isinstance(value, str) and re.search(r"[^\d.,\s]", n.clean_text(value) or ""):
        raise Invalid(f"{what} {value!r} is not a number")
    return num


def parse_mode(value: Any) -> str:
    """Mode code (``F2F`` ...) or the planning-list words (``Yüz yüze``, ``Çevrimiçi``, ``Hibrit``, ``UZEM``)."""
    text = n.clean_text(value)
    if text is None:
        return "F2F"
    code = n.tr_upper(text).replace("İ", "I")
    if code in MODES:
        return code
    parsed = n.parse_mode(text)
    if parsed.mode == "OTHER":
        raise Invalid(f"unknown mode {text!r} (one of {', '.join(MODES)} or Yüz yüze / Online / Hibrit / UZEM)")
    return parsed.mode


def parse_class_years(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        years = []
        for y in value:
            if isinstance(y, bool) or not isinstance(y, int):
                raise Invalid(f"class year {y!r} is not a number")
            years.append(y)
    else:
        years = n.parse_class_year(value)
    years = list(dict.fromkeys(years))
    if any(not 0 <= y <= 8 for y in years):
        raise Invalid(f"class years must be within 0..8 (got {years})")
    return years


def parse_course_code(value: Any) -> tuple[str, str]:
    """Strict: the text must be one course code and nothing else -> (stored code, display code)."""
    text = n.clean_text(value)
    if text is None:
        raise Invalid("course code is empty")
    codes = n.extract_course_codes(text)
    if len(codes) != 1 or n.course_key(text) != n.course_key(codes[0]):
        raise Invalid(f"{text!r} is not one course code (letters and a number, e.g. MBG 532)")
    return codes[0], n.display_course_code(codes[0])


def _email(value: Any) -> str | None:
    text = n.clean_text(value)
    if text is None:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        raise Invalid(f"{text!r} is not an e-mail address")
    return text.lower()


# --------------------------------------------------------------------------- audit


async def _audit(
    session: AsyncSession,
    action: str,
    entity: str,
    obj_id: Any,
    actor: User,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    term_id: int | None = None,
) -> AuditEvent | None:
    return await publish_event(
        session, action, entity, obj_id, before=before, after=after, actor=actor, term_id=term_id
    )


def _snap(obj: Any, drop: Iterable[str] = ("created_at", "updated_at")) -> dict[str, Any]:
    return {k: v for k, v in audit.snapshot(obj).items() if k not in set(drop)}


async def _get[T](session: AsyncSession, model: type[T], ident: int, what: str) -> T:
    obj = await session.get(model, ident)
    if obj is None:
        raise NotFound(f"{what} {ident} not found")
    return obj


# --------------------------------------------------------------------------- faculties


def faculty_out(f: Faculty) -> dict[str, Any]:
    return {"id": f.id, "name": f.name, "canonical_name": f.canonical_name}


async def _faculty_clash(session: AsyncSession, canonical: str, exclude: int | None = None) -> Faculty | None:
    q = select(Faculty).where(Faculty.canonical_name == canonical)
    if exclude is not None:
        q = q.where(Faculty.id != exclude)
    return (await session.execute(q)).scalars().first()


def _canon_faculty(name: Any) -> n.OrgParse:
    text = _text(name, "faculty name", required=True)
    parsed = n.canon_faculty(text)
    if parsed is None:
        raise Invalid("faculty name is empty")
    return parsed


async def create_faculty(session: AsyncSession, actor: User, name: Any) -> Faculty:
    parsed = _canon_faculty(name)
    clash = await _faculty_clash(session, parsed.canonical)
    if clash is not None:
        raise Conflict(f"faculty {clash.name} already exists", existing=faculty_out(clash))
    f = Faculty(name=parsed.name, canonical_name=parsed.canonical)
    session.add(f)
    await session.flush()
    await _audit(session, "faculty.create", "faculty", f.id, actor, after=_snap(f))
    return f


async def update_faculty(session: AsyncSession, actor: User, faculty_id: int, name: Any) -> Faculty:
    f = await _get(session, Faculty, faculty_id, "faculty")
    before = _snap(f)
    if name is not None:
        parsed = _canon_faculty(name)
        clash = await _faculty_clash(session, parsed.canonical, exclude=f.id)
        if clash is not None:
            raise Conflict(f"faculty {clash.name} already exists", existing=faculty_out(clash))
        f.name, f.canonical_name = parsed.name, parsed.canonical
    after = _snap(f)
    if after != before:
        await _audit(session, "faculty.update", "faculty", f.id, actor, before=before, after=after)
    return f


async def delete_faculty(session: AsyncSession, actor: User, faculty_id: int) -> int | None:
    """The model has no archive flag: deleted only when no programme belongs to it."""
    f = await _get(session, Faculty, faculty_id, "faculty")
    used = (await session.execute(select(func.count(Program.id)).where(Program.faculty_id == f.id))).scalar_one()
    if used:
        raise Conflict(f"{f.name} has {used} programme(s); move or delete them first", programs=int(used))
    before = _snap(f)
    await session.delete(f)
    await session.flush()
    ev = await _audit(session, "faculty.delete", "faculty", faculty_id, actor, before=before)
    return ev.id if ev else None


# --------------------------------------------------------------------------- programmes


def program_out(p: Program) -> dict[str, Any]:
    return {
        "id": p.id,
        "faculty_id": p.faculty_id,
        "name": p.name,
        "canonical_name": p.canonical_name,
        "is_evening": p.is_evening,
    }


async def _program_clash(session: AsyncSession, canonical: str, exclude: int | None = None) -> Program | None:
    q = select(Program).where(Program.canonical_name == canonical)
    if exclude is not None:
        q = q.where(Program.id != exclude)
    return (await session.execute(q)).scalars().first()


def _canon_program(name: Any) -> n.OrgParse:
    parsed = n.canon_program(_text(name, "programme name", required=True))
    if parsed is None:
        raise Invalid("programme name is empty")
    return parsed


async def create_program(
    session: AsyncSession,
    actor: User,
    *,
    name: Any,
    faculty_id: int | None = None,
    is_evening: bool | None = None,
    description: str | None = None,
) -> Program:
    parsed = _canon_program(name)
    if faculty_id is not None:
        await _get(session, Faculty, faculty_id, "faculty")
    clash = await _program_clash(session, parsed.canonical)
    if clash is not None:
        raise Conflict(f"programme {clash.name} already exists", existing=program_out(clash))
    p = Program(
        name=parsed.name,
        canonical_name=parsed.canonical,
        faculty_id=faculty_id,
        is_evening=parsed.is_evening if is_evening is None else is_evening,
        description=_text(description, "description"),
    )
    session.add(p)
    await session.flush()
    await _audit(session, "program.create", "program", p.id, actor, after=_snap(p))
    return p


async def update_program(session: AsyncSession, actor: User, program_id: int, data: dict[str, Any]) -> Program:
    p = await _get(session, Program, program_id, "programme")
    before = _snap(p)
    if data.get("name") is not None:
        parsed = _canon_program(data["name"])
        clash = await _program_clash(session, parsed.canonical, exclude=p.id)
        if clash is not None:
            raise Conflict(f"programme {clash.name} already exists", existing=program_out(clash))
        p.name, p.canonical_name = parsed.name, parsed.canonical
    if "faculty_id" in data:
        if data["faculty_id"] is not None:
            await _get(session, Faculty, int(data["faculty_id"]), "faculty")
        p.faculty_id = data["faculty_id"]
    if data.get("is_evening") is not None:
        p.is_evening = bool(data["is_evening"])
    if "description" in data:
        p.description = _text(data["description"], "description")
    after = _snap(p)
    if after != before:
        await _audit(session, "program.update", "program", p.id, actor, before=before, after=after)
    return p


async def delete_program(session: AsyncSession, actor: User, program_id: int) -> int | None:
    """Deleted only when nothing refers to it (sections, exam requests, users, bookings); a CRBS department with
    members is removed through ``DELETE /departments/{id}`` (setup.departments), which unlinks them."""
    p = await _get(session, Program, program_id, "programme")
    uses = {
        "sections": (
            await session.execute(select(func.count(Section.id)).where(Section.program_id == p.id))
        ).scalar_one(),
        "exam_requests": (
            await session.execute(select(func.count(ExamRequest.id)).where(ExamRequest.program_id == p.id))
        ).scalar_one(),
        "users": (await session.execute(select(func.count(User.id)).where(User.department_id == p.id))).scalar_one(),
        "bookings": (
            await session.execute(select(func.count(Booking.id)).where(Booking.department_id == p.id))
        ).scalar_one()
        + (
            await session.execute(select(func.count(BookingSeries.id)).where(BookingSeries.department_id == p.id))
        ).scalar_one(),
    }
    used = {k: int(v) for k, v in uses.items() if v}
    if used:
        what = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in used.items())
        raise Conflict(f"{p.name} is used by {what}", uses=used)
    before = _snap(p)
    await session.delete(p)
    await session.flush()
    ev = await _audit(session, "program.delete", "program", program_id, actor, before=before)
    return ev.id if ev else None


# --------------------------------------------------------------------------- courses


def course_out(c: Course) -> dict[str, Any]:
    return {
        "id": c.id,
        "code": c.code,
        "display_code": c.display_code,
        "name": c.name,
        "t_hours": c.t_hours,
        "u_hours": c.u_hours,
        "l_hours": c.l_hours,
        "credits": c.credits,
        "ects": c.ects,
    }


async def course_by_key(session: AsyncSession, code: str, exclude: int | None = None) -> Course | None:
    """The course whose :func:`normalize.course_key` equals ``code``'s (``MBG 532`` = ``mbg0532``; ``BİF`` =
    ``BIF``; ``ÇEV`` = ``CEV`` once the key folds Turkish letters), oldest first like the importers' lookup."""
    key = n.course_key(code)
    for cid, ccode in (await session.execute(select(Course.id, Course.code).order_by(Course.id))).all():
        if cid != exclude and n.course_key(ccode) == key:
            return await session.get(Course, cid)
    return None


def _hours_fields(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in ("t_hours", "u_hours", "l_hours"):
        if k in data:
            out[k] = parse_count(data[k], k, hi=40)
    for k in ("credits", "ects"):
        if k in data:
            out[k] = parse_decimal(data[k], k)
    if "name" in data:
        out["name"] = _text(data["name"], "course name")
    return out


async def check_course_code(session: AsyncSession, value: Any) -> dict[str, Any]:
    """The code checker of the wizard (design §4.2): canonical forms and the colliding course, never raises."""
    raw = n.clean_text(value) or ""
    try:
        code, display = parse_course_code(raw)
    except Invalid as exc:
        return {"input": raw, "code": None, "display_code": None, "key": None, "message": exc.message}
    clash = await course_by_key(session, code)
    return {
        "input": raw,
        "code": code,
        "display_code": display,
        "key": n.course_key(code),
        "duplicate": course_out(clash) if clash else None,
        "message": f"course {clash.display_code} already exists" if clash else None,
    }


async def create_course(session: AsyncSession, actor: User, data: dict[str, Any]) -> Course:
    code, display = parse_course_code(data.get("code"))
    clash = await course_by_key(session, code)
    if clash is not None:
        raise Conflict(
            f"course {clash.display_code} already exists (same code as {display})", existing=course_out(clash)
        )
    c = Course(code=code, display_code=display, **_hours_fields({k: v for k, v in data.items() if k != "code"}))
    session.add(c)
    await session.flush()
    await _audit(session, "course.create", "course", c.id, actor, after=_snap(c))
    return c


async def update_course(session: AsyncSession, actor: User, course_id: int, data: dict[str, Any]) -> Course:
    c = await _get(session, Course, course_id, "course")
    before = _snap(c)
    if data.get("code") is not None:
        code, display = parse_course_code(data["code"])
        clash = await course_by_key(session, code, exclude=c.id)
        if clash is not None:
            raise Conflict(f"course {clash.display_code} already exists", existing=course_out(clash))
        c.code, c.display_code = code, display
    for k, v in _hours_fields({k: v for k, v in data.items() if k != "code"}).items():
        setattr(c, k, v)
    after = _snap(c)
    if after != before:
        await _audit(session, "course.update", "course", c.id, actor, before=before, after=after)
    return c


async def delete_course(session: AsyncSession, actor: User, course_id: int) -> int | None:
    """No archive flag on courses: deleted only when no section (any term, archived too) uses it."""
    c = await _get(session, Course, course_id, "course")
    used = (await session.execute(select(func.count(Section.id)).where(Section.course_id == c.id))).scalar_one()
    if used:
        raise Conflict(
            f"{c.display_code} is used by {used} section(s); archive the sections instead", sections=int(used)
        )
    before = _snap(c)
    await session.delete(c)
    await session.flush()
    ev = await _audit(session, "course.delete", "course", course_id, actor, before=before)
    return ev.id if ev else None


# --------------------------------------------------------------------------- instructors


def instructor_out(i: Instructor) -> dict[str, Any]:
    return {
        "id": i.id,
        "full_name": i.full_name,
        "canonical_name": i.canonical_name,
        "title": i.title,
        "email": i.email,
    }


def _person(value: Any) -> n.PersonParse:
    text = _text(value, "instructor name", required=True)
    why = n.non_person_reason(text)
    if why is not None:
        raise Invalid(
            f"{text!r} names no person ({why}); leave the section without instructors for 'Belirlenmedi'", reason=why
        )
    parsed = n.canon_person_name(text)
    if parsed is None:
        raise Invalid("instructor name is empty")
    return parsed


async def _instructor_clash(session: AsyncSession, canonical: str, exclude: int | None = None) -> Instructor | None:
    q = select(Instructor).where(Instructor.canonical_name == canonical)
    if exclude is not None:
        q = q.where(Instructor.id != exclude)
    return (await session.execute(q)).scalars().first()


async def create_instructor(session: AsyncSession, actor: User, data: dict[str, Any]) -> Instructor:
    parsed = _person(data.get("full_name"))
    clash = await _instructor_clash(session, parsed.canonical)
    if clash is not None:
        raise Conflict(f"instructor {clash.full_name} already exists", existing=instructor_out(clash))
    title = _text(data.get("title"), "title", limit=64) or parsed.title
    i = Instructor(
        full_name=parsed.full_name, canonical_name=parsed.canonical, title=title, email=_email(data.get("email"))
    )
    session.add(i)
    await session.flush()
    await _audit(session, "instructor.create", "instructor", i.id, actor, after=_snap(i))
    return i


async def update_instructor(session: AsyncSession, actor: User, instructor_id: int, data: dict[str, Any]) -> Instructor:
    i = await _get(session, Instructor, instructor_id, "instructor")
    before = _snap(i)
    if data.get("full_name") is not None:
        parsed = _person(data["full_name"])
        clash = await _instructor_clash(session, parsed.canonical, exclude=i.id)
        if clash is not None:
            raise Conflict(f"instructor {clash.full_name} already exists", existing=instructor_out(clash))
        i.full_name, i.canonical_name = parsed.full_name, parsed.canonical
        if parsed.title and "title" not in data:
            i.title = parsed.title
    if "title" in data:
        i.title = _text(data["title"], "title", limit=64)
    if "email" in data:
        i.email = _email(data["email"])
    after = _snap(i)
    if after != before:
        await _audit(session, "instructor.update", "instructor", i.id, actor, before=before, after=after)
    return i


async def delete_instructor(session: AsyncSession, actor: User, instructor_id: int) -> int | None:
    i = await _get(session, Instructor, instructor_id, "instructor")
    used = (
        await session.execute(
            select(func.count()).select_from(SectionInstructor).where(SectionInstructor.instructor_id == i.id)
        )
    ).scalar_one()
    if used:
        raise Conflict(
            f"{i.full_name} teaches {used} section(s); remove them from the sections first", sections=int(used)
        )
    before = _snap(i)
    await session.delete(i)
    await session.flush()
    ev = await _audit(session, "instructor.delete", "instructor", instructor_id, actor, before=before)
    return ev.id if ev else None


# --------------------------------------------------------------------------- sections


SECTION_OPTS = (
    selectinload(Section.course),
    selectinload(Section.program),
    selectinload(Section.instructors).selectinload(SectionInstructor.instructor),
)


async def load_section(session: AsyncSession, section_id: int) -> Section:
    sec = (
        await session.execute(
            select(Section)
            .where(Section.id == section_id)
            .options(*SECTION_OPTS)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if sec is None:
        raise NotFound(f"section {section_id} not found")
    return sec


def _section_snap(sec: Section, links: Sequence[tuple[int, str]]) -> dict[str, Any]:
    snap = _snap(sec, drop=("created_at", "updated_at", "source_row"))
    snap["instructors"] = [{"instructor_id": i, "role": r} for i, r in links]
    return snap


async def _links(session: AsyncSession, section_id: int) -> list[tuple[int, str]]:
    rows = await session.execute(
        select(SectionInstructor.instructor_id, SectionInstructor.role)
        .where(SectionInstructor.section_id == section_id)
        .order_by(SectionInstructor.role, SectionInstructor.instructor_id)
    )
    return [(int(i), str(r)) for i, r in rows.all()]


async def _check_instructors(session: AsyncSession, items: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
    seen: dict[int, str] = {}
    for it in items:
        iid, role = int(it["instructor_id"]), str(it.get("role") or "PRIMARY")
        if iid in seen:
            raise Invalid(f"instructor {iid} is listed twice")
        await _get(session, Instructor, iid, "instructor")
        seen[iid] = role
    return list(seen.items())


def _label(value: Any) -> str | None:
    label = n.parse_section_label(value)
    if label is not None and len(label) > 64:
        raise Invalid("section label is longer than 64 characters")
    return label


async def _section_clash(
    session: AsyncSession, term_id: int, course_id: int, program_id: int | None, label: str | None, exclude: int | None
) -> Section | None:
    q = select(Section).where(
        Section.term_id == term_id,
        Section.course_id == course_id,
        Section.archived.is_(False),
        Section.program_id.is_(None) if program_id is None else Section.program_id == program_id,
    )
    if exclude is not None:
        q = q.where(Section.id != exclude)
    want = n.tr_casefold(label or "")
    for s in (await session.execute(q)).scalars():
        if n.tr_casefold(s.label or "") == want:
            return s
    return None


def section_brief(s: Section) -> dict[str, Any]:
    return {"id": s.id, "term_id": s.term_id, "course_id": s.course_id, "label": s.label, "source_key": s.source_key}


async def create_section(session: AsyncSession, actor: User, data: dict[str, Any]) -> Section:
    term = await _get(session, Term, int(data["term_id"]), "term")
    course = await _get(session, Course, int(data["course_id"]), "course")
    program_id = data.get("program_id")
    if program_id is not None:
        await _get(session, Program, int(program_id), "programme")
    label = _label(data.get("label"))
    clash = await _section_clash(session, term.id, course.id, program_id, label, None)
    if clash is not None:
        raise Conflict(
            f"{course.display_code}{' §' + label if label else ''} already has a section in {term.code}",
            existing=section_brief(clash),
        )
    years = parse_class_years(data.get("class_years"))
    links = await _check_instructors(session, data.get("instructors") or [])
    sec = Section(
        term_id=term.id,
        course_id=course.id,
        program_id=program_id,
        label=label,
        class_year=years[0] if years else None,
        class_years=years,
        semester_no=data.get("semester_no"),
        enrolment=parse_count(data.get("enrolment"), "enrolment"),
        mode=parse_mode(data.get("mode")),
        remote_pct=parse_count(data.get("remote_pct"), "remote_pct", hi=100),
        whole_term_in_room=data.get("whole_term_in_room"),
        notes=n.clean_text(data.get("notes")),
        source_key=man_key(),
    )
    session.add(sec)
    await session.flush()
    for iid, role in links:
        session.add(SectionInstructor(section_id=sec.id, instructor_id=iid, role=role))
    await session.flush()
    await _audit(session, "section.create", "section", sec.id, actor, after=_section_snap(sec, links), term_id=term.id)
    return sec


async def update_section(session: AsyncSession, actor: User, section_id: int, data: dict[str, Any]) -> Section:
    sec = await load_section(session, section_id)
    links_before = await _links(session, sec.id)
    before = _section_snap(sec, links_before)
    if "program_id" in data and data["program_id"] is not None:
        await _get(session, Program, int(data["program_id"]), "programme")
    program_id = data["program_id"] if "program_id" in data else sec.program_id
    label = _label(data["label"]) if "label" in data else sec.label
    if (program_id, label) != (sec.program_id, sec.label):
        clash = await _section_clash(session, sec.term_id, sec.course_id, program_id, label, sec.id)
        if clash is not None:
            raise Conflict("another section of the course has this programme and label", existing=section_brief(clash))
    sec.program_id, sec.label = program_id, label
    if "class_years" in data:
        years = parse_class_years(data["class_years"])
        sec.class_years, sec.class_year = years, (years[0] if years else None)
    if "semester_no" in data:
        sec.semester_no = data["semester_no"]
    if "enrolment" in data:
        sec.enrolment = parse_count(data["enrolment"], "enrolment")
    if "remote_pct" in data:
        sec.remote_pct = parse_count(data["remote_pct"], "remote_pct", hi=100)
    if "whole_term_in_room" in data:
        sec.whole_term_in_room = data["whole_term_in_room"]
    if "notes" in data:
        sec.notes = n.clean_text(data["notes"])
    if data.get("mode") is not None:
        sec.mode = parse_mode(data["mode"])
        # hand-made meetings follow the section's mode (online / UZEM / hospital: no room); imported rows keep the
        # importer's per-row decision (venue words, definitive place)
        needs_room = sec.mode in n.ROOM_MODES
        for mr in (
            await session.execute(
                select(MeetingRequest).where(
                    MeetingRequest.section_id == sec.id,
                    MeetingRequest.archived.is_(False),
                    MeetingRequest.source_key.like(f"{MAN_PREFIX}%"),
                )
            )
        ).scalars():
            mr.needs_room = needs_room
    links = links_before
    if data.get("instructors") is not None:
        links = await _check_instructors(session, data["instructors"])
        current = {si.instructor_id: si for si in sec.instructors}
        wanted = dict(links)
        for iid, si in current.items():
            if iid not in wanted:
                await session.delete(si)
            elif si.role != wanted[iid]:
                si.role = wanted[iid]
        for iid, role in links:
            if iid not in current:
                session.add(SectionInstructor(section_id=sec.id, instructor_id=iid, role=role))
        await session.flush()
        links = await _links(session, sec.id)
    await session.flush()
    after = _section_snap(sec, links)
    if after != before:
        await _audit(
            session, "section.update", "section", sec.id, actor, before=before, after=after, term_id=sec.term_id
        )
    return sec


async def _runs_using(
    session: AsyncSession, *, meeting_ids: Sequence[int] = (), exam_ids: Sequence[int] = ()
) -> list[ScheduleRun]:
    conds = []
    if meeting_ids:
        conds.append(Assignment.meeting_request_id.in_(list(meeting_ids)))
    if exam_ids:
        conds.append(Assignment.exam_request_id.in_(list(exam_ids)))
    if not conds:
        return []
    run_ids = select(Assignment.run_id).where(or_(*conds)).distinct()
    return list(
        (
            await session.execute(select(ScheduleRun).where(ScheduleRun.id.in_(run_ids)).order_by(ScheduleRun.id))
        ).scalars()
    )


def _refuse_purge(what: str, runs: Sequence[ScheduleRun]) -> None:
    if not runs:
        return
    active = [r.id for r in runs if r.is_active]
    names = ", ".join(f"#{r.id}{' (active)' if r.is_active else ''}" for r in runs[:10])
    raise Conflict(
        f"{what} is placed in run(s) {names}; deleting it would orphan their assignments, archive it instead",
        run_ids=[r.id for r in runs],
        active_run_ids=active,
    )


def _refuse_imported(what: str, source_key: str | None) -> None:
    if not (source_key or "").startswith(MAN_PREFIX):
        raise Conflict(f"{what} comes from an import; imported rows are archived, never deleted")


async def archive_section(
    session: AsyncSession, actor: User, section_id: int, *, purge: bool = False
) -> tuple[str, int | None]:
    sec = await load_section(session, section_id)
    meetings = list(
        (await session.execute(select(MeetingRequest).where(MeetingRequest.section_id == sec.id))).scalars()
    )
    before = _section_snap(sec, await _links(session, sec.id))
    if purge:
        label = f"section {sec.course.display_code}{' §' + sec.label if sec.label else ''}"
        _refuse_imported(label, sec.source_key)
        exams = list((await session.execute(select(ExamRequest.id).where(ExamRequest.section_id == sec.id))).scalars())
        if exams:
            raise Conflict(f"{label} has {len(exams)} exam request(s); delete or archive them first", exam_ids=exams)
        _refuse_purge(label, await _runs_using(session, meeting_ids=[m.id for m in meetings]))
        term_id = sec.term_id
        await session.delete(sec)  # cascades to its meetings and instructor links
        await session.flush()
        ev = await _audit(session, "section.delete", "section", section_id, actor, before=before, term_id=term_id)
        return "deleted", ev.id if ev else None
    sec.archived = True
    for mr in meetings:
        mr.archived = True
    await session.flush()
    after = _section_snap(sec, await _links(session, sec.id))
    after["archived_meeting_ids"] = [m.id for m in meetings]
    ev = await _audit(
        session, "section.archive", "section", sec.id, actor, before=before, after=after, term_id=sec.term_id
    )
    return "archived", ev.id if ev else None


# --------------------------------------------------------------------------- meetings and the pattern expander


async def _buildings(session: AsyncSession) -> tuple[str, ...]:
    codes = [str(c).upper() for c in (await session.execute(select(Building.code))).scalars()]
    return tuple(sorted(set(codes) | {"A", "B", "C", "D"}))


async def _room_id(session: AsyncSession, code: str | None) -> int | None:
    if not code:
        return None
    rid = (await session.execute(select(Room.id).where(Room.code == code))).scalar_one_or_none()
    if rid is None:
        raise Invalid(f"room {n.display_room_code(code)} is not in the room master")
    return int(rid)


def _meeting_snap(mr: MeetingRequest) -> dict[str, Any]:
    return _snap(mr)


async def _write_meetings(
    session: AsyncSession, sec: Section, specs: Sequence[pt.MeetingSpec], note: str | None = None
) -> list[MeetingRequest]:
    out: list[MeetingRequest] = []
    for spec in specs:
        room_id = await _room_id(session, spec.requested_room_code)
        notes = " | ".join(p for p in (spec.notes, n.clean_text(note)) if p) or None
        mr = MeetingRequest(
            section_id=sec.id,
            day=spec.day,
            days=list(spec.days),
            start_period=spec.start_period,
            end_period=spec.end_period,
            start_time=spec.start_time,
            end_time=spec.end_time,
            weeks=list(spec.weeks),
            requested_room_text=spec.requested_room_text,
            requested_room_ids=[room_id] if room_id is not None else [],
            requested_building=spec.requested_building,
            requested_tags=list(spec.requested_tags),
            requested_capacity=spec.requested_capacity,
            flexible_day=spec.flexible_day,
            needs_room=spec.needs_room,
            definitive_room_text=None,
            definitive_room_ids=[],
            status="PARSED",
            parse_warnings=[],
            notes=notes,
            source_key=man_key(),
            source_row_index=None,
            archived=False,
        )
        session.add(mr)
        out.append(mr)
    await session.flush()
    return out


def _tag_warnings(specs: Iterable[pt.MeetingSpec]) -> list[str]:
    tags = sorted({t for s in specs for t in s.requested_tags} - ENFORCED_TAGS)
    if not tags:
        return []
    return [
        f"room tag(s) {', '.join(tags)} are recorded on the request but the solver enforces only PC (required) "
        "and TIP (allowed); name a preferred room or add a room rule to enforce them"
    ]


def _course_hours(sec: Section) -> tuple[int | None, int | None, int | None]:
    return sec.course.t_hours, sec.course.u_hours, sec.course.l_hours


async def apply_pattern(
    session: AsyncSession, actor: User, section_id: int, raw: dict[str, Any], *, replace: bool = True
) -> tuple[Section, list[MeetingRequest], list[int], list[str], int | None]:
    """Expand ``raw`` (see :mod:`app.services.patterns`) into meeting requests of the section. With ``replace`` the
    section's earlier hand-made meetings are archived first (imported meetings are never touched)."""
    sec = await load_section(session, section_id)
    if sec.archived:
        raise Conflict("the section is archived")
    term = await _get(session, Term, sec.term_id, "term")
    try:
        spec = pt.build_spec(
            raw,
            course_hours=_course_hours(sec),
            max_week=int(term.week_count or 14),
            buildings=await _buildings(session),
        )
    except pt.PatternError as exc:
        raise Invalid(str(exc)) from exc
    specs = pt.expand(spec, enrolment=sec.enrolment, needs_room=sec.mode in n.ROOM_MODES)
    archived: list[MeetingRequest] = []
    if replace:
        archived = list(
            (
                await session.execute(
                    select(MeetingRequest)
                    .where(
                        MeetingRequest.section_id == sec.id,
                        MeetingRequest.archived.is_(False),
                        MeetingRequest.source_key.like(f"{MAN_PREFIX}%"),
                    )
                    .order_by(MeetingRequest.id)
                )
            ).scalars()
        )
        for mr in archived:
            mr.archived = True
    created = await _write_meetings(session, sec, specs)
    items: list[tuple[Any, dict[str, Any] | None, dict[str, Any] | None]] = [
        (mr.id, None, _meeting_snap(mr)) for mr in created
    ]
    ev = await publish_event(
        session,
        "section.pattern",
        "section",
        sec.id,
        items=items,
        item_type="meeting",
        child_action="meeting.create",
        parent_after={"pattern": audit.jsonable(raw), "archived_ids": [m.id for m in archived]},
        actor=actor,
        term_id=sec.term_id,
    )
    return sec, created, [m.id for m in archived], _tag_warnings(specs), ev.id if ev else None


async def create_meeting(session: AsyncSession, actor: User, data: dict[str, Any]) -> tuple[MeetingRequest, list[str]]:
    """One meeting by hand: a one-block pattern (``periods`` or the ``end`` clock time gives its length)."""
    sec = await load_section(session, int(data["section_id"]))
    if sec.archived:
        raise Conflict("the section is archived")
    term = await _get(session, Term, sec.term_id, "term")
    try:
        start = pt.parse_start(data.get("start"))
        periods = data.get("periods")
        if periods is None:
            end_text = n.clean_text(data.get("end"))
            end_t = n.parse_time(end_text) if end_text else None
            if end_t is None:
                raise pt.PatternError("periods or end (e.g. 13:20) is required")
            match = n.time_to_period(end_t, "end")
            if match.period is None or match.warning or match.period < start:
                raise pt.PatternError(f"end {end_t:%H:%M} is not the end of a period after the start")
            periods = match.period - start + 1
        raw: dict[str, Any] = {"theory": int(periods), "days": data.get("days"), "start": start}
        for k in ("weeks", "room_needs"):
            if data.get(k) is not None:
                raw[k] = data[k]
        spec = pt.build_spec(
            raw, course_hours=(None, 0, 0), max_week=int(term.week_count or 14), buildings=await _buildings(session)
        )
    except pt.PatternError as exc:
        raise Invalid(str(exc)) from exc
    specs = pt.expand(spec, enrolment=sec.enrolment, needs_room=sec.mode in n.ROOM_MODES)
    specs = [dc_replace(s, notes="") for s in specs]  # a single hand-made meeting carries only the caller's note
    (mr,) = await _write_meetings(session, sec, specs, data.get("notes"))
    await _audit(session, "meeting.create", "meeting", mr.id, actor, after=_meeting_snap(mr), term_id=sec.term_id)
    return mr, _tag_warnings(specs)


async def archive_meeting(
    session: AsyncSession, actor: User, meeting_id: int, *, purge: bool = False
) -> tuple[str, int | None]:
    mr = await _get(session, MeetingRequest, meeting_id, "meeting request")
    sec = await _get(session, Section, mr.section_id, "section")
    before = _meeting_snap(mr)
    if purge:
        _refuse_imported(f"meeting request {mr.id}", mr.source_key)
        _refuse_purge(f"meeting request {mr.id}", await _runs_using(session, meeting_ids=[mr.id]))
        await session.delete(mr)
        await session.flush()
        ev = await _audit(session, "meeting.delete", "meeting", meeting_id, actor, before=before, term_id=sec.term_id)
        return "deleted", ev.id if ev else None
    mr.archived = True
    await session.flush()
    ev = await _audit(
        session, "meeting.archive", "meeting", mr.id, actor, before=before, after=_meeting_snap(mr), term_id=sec.term_id
    )
    return "archived", ev.id if ev else None


# --------------------------------------------------------------------------- exam requests


def _clock(value: Any, what: str) -> Any:
    text = n.clean_text(value)
    if text is None:
        return None
    t = n.parse_time(text)
    if t is None:
        raise Invalid(f"{what} {text!r} is not a time (e.g. 09.20)")
    return t


async def create_exam(session: AsyncSession, actor: User, data: dict[str, Any]) -> ExamRequest:
    """An exam request like the exam-list importer writes one (periods from the clock times, off-grid times snapped
    with a parse warning, ``merge_key`` = term + course key + date + start), stamped ``MAN:``."""
    term = await _get(session, Term, int(data["term_id"]), "term")
    sec: Section | None = None
    if data.get("section_id") is not None:
        sec = await load_section(session, int(data["section_id"]))
        if sec.term_id != term.id:
            raise Invalid(f"section {sec.id} belongs to another term")
    code_in = data.get("course_code") or (sec.course.code if sec else None)
    if not code_in:
        raise Invalid("course_code is required (or a section_id)")
    code, _display = parse_course_code(code_in)
    program_id = data.get("program_id") if data.get("program_id") is not None else (sec.program_id if sec else None)
    if program_id is not None:
        await _get(session, Program, int(program_id), "programme")
    years = (
        parse_class_years(data.get("class_years"))
        if data.get("class_years") is not None
        else (list(sec.class_years or []) if sec else [])
    )
    enrolment = parse_count(data.get("enrolment"), "enrolment")
    if enrolment is None and sec is not None:
        enrolment = sec.enrolment
    start, end = _clock(data.get("start"), "start"), _clock(data.get("end"), "end")
    if start is not None and end is not None and end <= start:
        raise Invalid("end is not after start")
    periods = n.time_range_to_periods(start, end)
    try:
        needs = pt.parse_room_needs(
            {"tags": data.get("requested_tags"), "building": data.get("requested_building")},
            await _buildings(session),
        )
    except pt.PatternError as exc:
        raise Invalid(str(exc)) from exc
    no_exam = bool(data.get("no_exam"))
    needs_room = not no_exam
    date = data.get("date")
    status = "NEEDS_REVIEW" if needs_room and (date is None or periods.start_period is None) else "PARSED"
    merge = f"{term.code}:{n.course_key(code)}:{date.isoformat()}:{start:%H%M}" if date and start else None
    ex = ExamRequest(
        term_id=term.id,
        section_id=sec.id if sec else None,
        course_code=code,
        course_name=_text(data.get("course_name"), "course name") or (sec.course.name if sec else None),
        program_id=program_id,
        class_year=years[0] if years else None,
        class_years=years,
        enrolment=enrolment,
        instructor_text=_text(data.get("instructor_text"), "instructor"),
        date=date,
        start_time=start,
        end_time=end,
        start_period=periods.start_period,
        end_period=periods.end_period,
        requested_room_count=data.get("requested_room_count"),
        requested_min_capacity=data.get("requested_min_capacity"),
        requested_tags=list(needs.tags),
        requested_building=needs.building,
        on_campus_written=bool(data.get("on_campus_written")),
        no_exam=no_exam,
        needs_room=needs_room,
        merge_key=merge,
        status=status,
        parse_warnings=list(periods.warnings),
        notes=n.clean_text(data.get("notes")),
        source_key=man_key(),
        archived=False,
    )
    session.add(ex)
    await session.flush()
    await _audit(session, "exam.create", "exam", ex.id, actor, after=_snap(ex), term_id=term.id)
    return ex


async def archive_exam(
    session: AsyncSession, actor: User, exam_id: int, *, purge: bool = False
) -> tuple[str, int | None]:
    ex = await _get(session, ExamRequest, exam_id, "exam request")
    before = _snap(ex)
    if purge:
        _refuse_imported(f"exam request {ex.id}", ex.source_key)
        _refuse_purge(f"exam request {ex.id}", await _runs_using(session, exam_ids=[ex.id]))
        term_id = ex.term_id
        await session.delete(ex)
        await session.flush()
        ev = await _audit(session, "exam.delete", "exam", exam_id, actor, before=before, term_id=term_id)
        return "deleted", ev.id if ev else None
    ex.archived = True
    await session.flush()
    ev = await _audit(session, "exam.archive", "exam", ex.id, actor, before=before, after=_snap(ex), term_id=ex.term_id)
    return "archived", ev.id if ev else None


__all__ = [
    "MAN_PREFIX",
    "CatalogError",
    "Conflict",
    "Invalid",
    "NotFound",
    "apply_pattern",
    "archive_exam",
    "archive_meeting",
    "archive_section",
    "check_course_code",
    "course_by_key",
    "create_course",
    "create_exam",
    "create_faculty",
    "create_instructor",
    "create_meeting",
    "create_program",
    "create_section",
    "delete_course",
    "delete_faculty",
    "delete_instructor",
    "delete_program",
    "load_section",
    "parse_class_years",
    "parse_count",
    "parse_course_code",
    "parse_decimal",
    "parse_mode",
    "update_course",
    "update_faculty",
    "update_instructor",
    "update_program",
    "update_section",
]
