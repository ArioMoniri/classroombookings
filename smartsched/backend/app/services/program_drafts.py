"""Program wizard drafts (P19-W-01..W-08; docs/design/v2/phase19-program-wizard.md §13).

The wizard no longer writes live rows as the coordinator types. Its state is one JSON payload per user + target
term (``program_drafts``), autosaved with per-field merges and resumable from the "Taslaklar" list. Nothing in
the term changes until :func:`commit` writes everything at once:

``payload`` (snake_case; the wizard's camelCase keys are accepted too, :func:`normalise`)::

    {"program": {"faculty_id": 3 | null, "faculty_name": "Fen Bilimleri Enstitüsü", "name": "...",
                 "level": "masterThesis", "evening": false, "language": "tr", "prefix": "MBG", "years": 2},
     "courses": [{"key": "c1", "course_id": null,            # an existing catalogue course, reused as is
                  "code": "MBG 532", "name": "Epigenetik", "t": 3, "u": 0, "l": 0, "credits": "3", "ects": 9,
                  "year": 1, "mode": "Yüz yüze", "compulsory": true,
                  "sections": [{"key": "s1", "label": "1", "enrolment": 80,
                                "instructors": [{"id": 12} | {"name": "Prof.Dr. Eda TAHİR TURANLI"} | null, ...],
                                "joint_section_ids": [345]}],   # sections of the term taught together
                  "pattern": {"theory_blocks": [3], "weekly_hours": null, "days": [2], "start": "08.30",
                              "weeks": "1-14"},
                  "room": {"capacity": null, "tags": [], "building": "", "preferred": "C 504"}}],
     "cohorts": [{"key": "y1", "label": "MBG YL 1. sınıf", "year": 1, "compulsory": ["c1"], "elective_groups": []}],
     "rules": {"window": {"enabled": true, "earliest": 1, "latest": 11, "hard": false}, "same_room": true}}

Validation (:func:`validate`) has three levels, as the spec asks: field and step checks on the payload alone, and
(``precheck=True``) the Studio static pre-check of the term with the draft's classes in it, computed by writing the
draft in a session that is rolled back (:func:`dry_run`). Only errors block the commit; warnings never do. Every
issue is ``{step, level, code, path, text: {tr, en}, vars}``.

:func:`commit` holds the term's write lock, writes faculty / programme / courses / people / sections / meetings /
rules through the ``catalog_admin`` services (the same normalisation, duplicate keys and per-entity audit), and
records ``program_draft.commit`` with every id it created. :func:`undo` (30 days) archives exactly those rows when
nothing outside the commit references them; otherwise it refuses and names each reference.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers import normalize as n
from app.models import (
    Assignment,
    AuditEvent,
    Booking,
    BookingSeries,
    ConstraintRow,
    Course,
    ExamRequest,
    Faculty,
    Instructor,
    MeetingRequest,
    Program,
    ProgramDraft,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
    User,
)
from app.models.base import utcnow
from app.services import catalog_admin as ca
from app.services import patterns as pt
from app.services.events import publish_event

STEPS = ("program", "courses", "sections", "instructors", "cohorts", "rooms", "constraints", "generate")
#: the wizard's current step names (components/program-wizard/wizard-model.ts) -> the spec's steps
STEP_ALIASES = {"term": "program", "patterns": "rooms", "precheck": "constraints"}
UNDO_DAYS = 30
#: an instructor's weekly load above this warns (setting ``planning.instructor_load_limit``; spec §4.4)
DEFAULT_LOAD_LIMIT = 20
MAX_COURSES = 120
MAX_SECTIONS = 40
LEVELS = ("associate", "bachelor", "masterThesis", "masterNonThesis", "phd")
PREFIX_RX = re.compile(r"^[A-Z]{2,4}$")
TR_LETTERS = re.compile(r"[ÇĞİÖŞÜçğıöşü]")


class DraftError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


# --------------------------------------------------------------------------- payload shape


def _snake(key: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", lambda m: "_" + m.group(1).lower(), key)


def normalise(value: Any) -> Any:
    """camelCase keys -> snake_case, recursively (values untouched); ``sameRoom`` -> ``same_room``."""
    if isinstance(value, Mapping):
        return {_snake(str(k)): normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalise(v) for v in value]
    return value


def _dict(v: Any) -> dict[str, Any]:
    return dict(v) if isinstance(v, Mapping) else {}


def _list(v: Any) -> list[Any]:
    return list(v) if isinstance(v, list) else []


def _int(v: Any) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        text = n.clean_text(v)
        if text and re.fullmatch(r"\d+", text):
            return int(text)
    return None


def _num(v: Any) -> float | None:
    """Comma decimals and NBSP as in the planning lists; ``None`` for empty, ``nan`` for non-numbers."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    text = n.clean_text(v)
    if text is None or text in ("-", "—"):
        return None
    if re.search(r"[^\d.,\s]", text):
        return float("nan")
    got = n.parse_float_loose(text)
    return float("nan") if got is None else float(got)


@dataclass
class Issue:
    step: str
    level: str  # error | warning | info
    code: str
    path: str
    tr: str
    en: str
    vars: dict[str, Any] = field(default_factory=dict)

    def out(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "level": self.level,
            "code": self.code,
            "path": self.path,
            "text": _t(self.tr, self.en),
            "vars": self.vars,
        }


# --------------------------------------------------------------------------- the term context


@dataclass
class Context:
    """What validation reads from the DB once: rooms, the target term, linked sections and people."""

    term: Term
    rooms: list[Room]
    joint: dict[int, Section]
    joint_place: dict[int, dict[str, Any]]
    instructors: dict[int, Instructor]
    by_canonical: dict[str, Instructor]
    faculties: dict[int, Faculty]
    program_clash: Program | None
    courses_by_key: dict[str, Course]
    load: dict[int, int]
    load_limit: int
    #: an archived programme of the same canonical name (an undone commit): the commit reopens it (follow-up 2)
    program_archived: Program | None = None
    #: the draft programme's canonical name (the "department" a namesake must share to be reused, follow-up 3)
    program_canonical: str | None = None
    #: archived people by canonical name (an undone commit's people; the names stay unique in the table)
    archived_by_canonical: dict[str, Instructor] = field(default_factory=dict)
    #: instructor id -> {programme canonical name: display name} of every section they ever taught (any term)
    units: dict[int, dict[str, str]] = field(default_factory=dict)


def section_periods(meetings: Iterable[MeetingRequest]) -> int:
    """Periods a week of a section's live meetings (a meeting without a start counts its ``duration``)."""
    total = 0
    for m in meetings:
        if m.archived:
            continue
        if m.start_period is not None and m.end_period is not None:
            total += m.end_period - m.start_period + 1
        else:
            total += int(m.duration_periods or 0)
    return total


async def instructor_loads(
    session: AsyncSession, term_id: int, instructor_ids: Iterable[int] | None = None
) -> dict[int, dict[str, Any]]:
    """P19 gap 7: each instructor's teaching load in the term, in periods a week, over live sections and meetings.
    A joint lecture listed once per programme (same day and periods, same weeks) counts once."""
    q = (
        select(SectionInstructor.instructor_id, MeetingRequest)
        .join(Section, Section.id == SectionInstructor.section_id)
        .join(MeetingRequest, MeetingRequest.section_id == Section.id)
        .where(Section.term_id == term_id, Section.archived.is_(False), MeetingRequest.archived.is_(False))
    )
    ids = list(instructor_ids) if instructor_ids is not None else None
    if ids is not None:
        if not ids:
            return {}
        q = q.where(SectionInstructor.instructor_id.in_(ids))
    out: dict[int, dict[str, Any]] = {}
    seen: dict[int, set[tuple[Any, ...]]] = defaultdict(set)
    sections: dict[int, set[int]] = defaultdict(set)
    for iid, mr in (await session.execute(q)).all():
        iid = int(iid)
        slot = (mr.day, mr.start_period, mr.end_period, tuple(sorted(mr.weeks or [])))
        row = out.setdefault(iid, {"instructor_id": iid, "periods_per_week": 0, "meetings": 0, "sections": 0})
        sections[iid].add(mr.section_id)
        if mr.start_period is not None and slot in seen[iid]:
            continue  # the same lecture listed for another programme
        seen[iid].add(slot)
        row["meetings"] += 1
        row["periods_per_week"] += section_periods([mr])
    for iid, row in out.items():
        row["sections"] = len(sections[iid])
    return out


async def load_limit(session: AsyncSession) -> int:
    from app.services import settings_service as ss

    try:
        v = await ss.get_value(session, "planning.instructor_load_limit")
    except Exception:  # noqa: BLE001 - an unknown key is the default
        v = None
    got = _int(v)
    return got if got and got > 0 else DEFAULT_LOAD_LIMIT


async def published_places(
    session: AsyncSession, term_id: int, section_ids: Iterable[int]
) -> dict[int, dict[str, Any]]:
    """Per section: its meetings' cells in the term's published course run (day, periods, rooms)."""
    from app.services.moderation import published_run

    ids = list(section_ids)
    run = await published_run(session, term_id)
    out: dict[int, dict[str, Any]] = {}
    if run is None or not ids:
        return out
    rooms = {r.id: r.display_name for r in (await session.execute(select(Room))).scalars()}
    q = (
        select(MeetingRequest.section_id, Assignment)
        .join(Assignment, Assignment.meeting_request_id == MeetingRequest.id)
        .where(Assignment.run_id == run.id, Assignment.archived.is_(False), MeetingRequest.section_id.in_(ids))
    )
    for sid, a in (await session.execute(q)).all():
        cell = {
            "meeting_request_id": a.meeting_request_id,
            "day": a.day,
            "start_period": a.start_period,
            "end_period": a.end_period,
            "rooms": [rooms.get(int(r), f"#{r}") for r in (a.room_ids or [])],
        }
        slot = out.setdefault(int(sid), {"run_id": run.id, "cells": []})
        if cell not in slot["cells"]:
            slot["cells"].append(cell)
    return out


async def load_context(session: AsyncSession, term: Term, payload: Mapping[str, Any]) -> Context:
    courses = _list(payload.get("courses"))
    joint_ids: set[int] = set()
    instructor_ids: set[int] = set()
    for c in courses:
        for s in _list(_dict(c).get("sections")):
            s = _dict(s)
            joint_ids |= {v for v in (_int(x) for x in _list(s.get("joint_section_ids"))) if v is not None}
            for ref in _list(s.get("instructors")):
                if (iid := _int(_dict(ref).get("id"))) is not None:
                    instructor_ids.add(iid)
    joint: dict[int, Section] = {}
    if joint_ids:
        q = (
            select(Section)
            .where(Section.id.in_(sorted(joint_ids)))
            .options(
                selectinload(Section.course),
                selectinload(Section.program),
                selectinload(Section.meeting_requests),
                selectinload(Section.instructors).selectinload(SectionInstructor.instructor),
            )
        )
        joint = {s.id: s for s in (await session.execute(q)).scalars()}
    instructors = (
        {
            i.id: i
            for i in (await session.execute(select(Instructor).where(Instructor.id.in_(instructor_ids)))).scalars()
        }
        if instructor_ids
        else {}
    )
    every = list((await session.execute(select(Instructor))).scalars())
    by_canonical = {i.canonical_name: i for i in every if not i.archived}
    archived_by_canonical = {i.canonical_name: i for i in every if i.archived}
    prog = _dict(payload.get("program"))
    clash = archived_prog = None
    parsed = n.canon_program(n.clean_text(prog.get("name")) or "") if n.clean_text(prog.get("name")) else None
    if parsed is not None:
        # follow-up 2: an archived programme (its creation was undone) is no clash; the commit reopens it
        same = list(
            (await session.execute(select(Program).where(Program.canonical_name == parsed.canonical))).scalars()
        )
        clash = next((p for p in same if not p.archived), None)
        archived_prog = next((p for p in same if p.archived), None) if clash is None else None
    # the programmes each named / chosen person taught in (follow-up 3: "clearly the same" = same name + programme)
    typed = {
        pp.canonical
        for c in courses
        for s in _list(_dict(c).get("sections"))
        for ref in _list(_dict(s).get("instructors"))
        if ref
        and _int(_dict(ref).get("id")) is None
        and (nm := n.clean_text(_dict(ref).get("name")))
        and n.non_person_reason(nm) is None
        and (pp := n.canon_person_name(nm)) is not None
    }
    candidates = set(instructor_ids) | {
        i.id for k, i in {**archived_by_canonical, **by_canonical}.items() if k in typed
    }
    units: dict[int, dict[str, str]] = defaultdict(dict)
    if candidates:
        for iid, canon, pname in (
            await session.execute(
                select(SectionInstructor.instructor_id, Program.canonical_name, Program.name)
                .join(Section, Section.id == SectionInstructor.section_id)
                .join(Program, Program.id == Section.program_id)
                .where(SectionInstructor.instructor_id.in_(sorted(candidates)))
            )
        ).all():
            units[int(iid)][str(canon)] = str(pname)
    keys: dict[str, Course] = {}
    wanted = {n.course_key(str(_dict(c).get("code") or "")) for c in courses if n.clean_text(_dict(c).get("code"))}
    for c in (await session.execute(select(Course).order_by(Course.id))).scalars():
        k = n.course_key(c.code)
        if k in wanted and keys.get(k) is None:
            keys[k] = c
    loads = await instructor_loads(session, term.id, instructor_ids)
    return Context(
        term=term,
        rooms=list((await session.execute(select(Room))).scalars()),
        joint=joint,
        joint_place=await published_places(session, term.id, joint.keys()),
        instructors=instructors,
        by_canonical=by_canonical,
        faculties={f.id: f for f in (await session.execute(select(Faculty))).scalars()},
        program_clash=clash,
        courses_by_key={k: v for k, v in keys.items() if v is not None},
        load={iid: int(v["periods_per_week"]) for iid, v in loads.items()},
        load_limit=await load_limit(session),
        program_archived=archived_prog,
        program_canonical=parsed.canonical if parsed is not None else None,
        archived_by_canonical=archived_by_canonical,
        units=dict(units),
    )


# --------------------------------------------------------------------------- rooms fit (P19-W-04)


def room_brief(r: Room) -> dict[str, Any]:
    return {
        "id": r.id,
        "code": r.code,
        "display_name": r.display_name,
        "capacity": int(r.capacity or 0),
        "tags": sorted(r.tags or []),
        "bookable": bool(r.is_bookable),
    }


def rooms_fit(
    rooms: Iterable[Room], capacity: int, tags: Iterable[str] = (), building: str | None = None
) -> list[Room]:
    """Bookable rooms seating ``capacity`` with every tag, smallest first; TIP rooms only when TIP is asked."""
    want = {str(t).upper() for t in tags if t}
    b = (n.clean_text(building) or "").upper()
    out = []
    for r in rooms:
        rtags = {str(t).upper() for t in (r.tags or [])}
        if not r.is_bookable or int(r.capacity or 0) < capacity or not want <= rtags:
            continue
        if "TIP" in rtags and "TIP" not in want:
            continue
        if b and not n.tr_upper(r.code or "").startswith(b):
            continue
        out.append(r)
    return sorted(out, key=lambda r: (int(r.capacity or 0), r.code))


def _fmt_rooms(rs: list[Room], k: int = 4) -> str:
    return ", ".join(f"{r.display_name} ({r.capacity})" for r in rs[:k]) + (" …" if len(rs) > k else "")


def _find_room(rooms: Iterable[Room], text: str) -> Room | None:
    key = n.tr_upper(re.sub(r"\s+", "", text or ""))
    for r in rooms:
        if n.tr_upper(r.code or "") == key or n.tr_upper(re.sub(r"\s+", "", r.display_name or "")) == key:
            return r
    return None


# --------------------------------------------------------------------------- validation


def _hours_of(c: Mapping[str, Any]) -> tuple[int, int, int]:
    vals = []
    for k in ("t", "u", "l"):
        v = _num(c.get(k))
        vals.append(int(v) if v is not None and v == v and v >= 0 else 0)
    return vals[0], vals[1], vals[2]


def joint_total(s: Mapping[str, Any], ctx: Context) -> int:
    own = _int(s.get("enrolment")) or 0
    linked = sum(
        int(ctx.joint[j].enrolment or 0) for j in (_int(x) for x in _list(s.get("joint_section_ids"))) if j in ctx.joint
    )
    return own + linked


def pattern_body(c: Mapping[str, Any], s: Mapping[str, Any], ctx: Context | None = None) -> dict[str, Any]:
    """The ``catalog_admin.apply_pattern`` body of a course's section (same as the wizard's ``patternBody``)."""
    t, u, l = _hours_of(c)
    pat = _dict(c.get("pattern"))
    room = _dict(c.get("room"))
    zero = not (t + u + l)
    theory = (_int(pat.get("weekly_hours")) or 0) if zero else t
    body: dict[str, Any] = {"theory": theory, "practice": 0 if zero else u, "lab": 0 if zero else l}
    blocks = [b for b in (_int(x) for x in _list(pat.get("theory_blocks"))) if b]
    if blocks and not zero:
        body["block_size"] = blocks
    if pat.get("slots"):
        body["slots"] = pat["slots"]
    else:
        body["days"] = pat.get("days") if pat.get("days") not in (None, "", []) else None
        body["start"] = pat.get("start")
    body["weeks"] = pat.get("weeks") or None
    needs: dict[str, Any] = {}
    if _list(room.get("tags")):
        needs["tags"] = _list(room.get("tags"))
    if n.clean_text(room.get("building")):
        needs["building"] = room["building"]
    if n.clean_text(room.get("preferred")):
        needs["preferred_room"] = room["preferred"]
    cap = _int(room.get("capacity")) or (joint_total(s, ctx) if ctx else _int(s.get("enrolment")))
    if cap:
        needs["capacity"] = cap
    if needs:
        body["room_needs"] = needs
    return body


def _code_of(c: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(stored code, display code, error) of a course row."""
    raw = n.clean_text(c.get("code"))
    if raw is None:
        return None, None, "empty"
    if TR_LETTERS.search(raw):
        return None, None, "turkish"
    try:
        code, display = ca.parse_course_code(raw)
    except ca.CatalogError:
        return None, None, "shape"
    return code, display, None


def validate_payload(payload: Mapping[str, Any], ctx: Context) -> list[Issue]:
    """Field and step checks (no solve); spec §4 per step."""
    out: list[Issue] = []

    def add(step: str, level: str, issue_code: str, path: str, tr: str, en: str, /, **vars_: Any) -> None:
        out.append(Issue(step, level, issue_code, path, tr, en, vars_))

    p = _dict(payload.get("program"))
    name = n.clean_text(p.get("name"))
    if not name:
        add("program", "error", "no_name", "program.name", "Program adı gerekli", "The programme needs a name")
    elif ctx.program_clash is not None:
        add(
            "program",
            "error",
            "program_exists",
            "program.name",
            f"Aynı adlı program var: {ctx.program_clash.name}",
            f"A programme with this name exists: {ctx.program_clash.name}",
            program_id=ctx.program_clash.id,
        )
    elif ctx.program_archived is not None:
        add(
            "program",
            "info",
            "program_restored",
            "program.name",
            f"Arşivlenmiş {ctx.program_archived.name} programı yeniden açılacak (önceki oluşturma geri alınmıştı)",
            f"The archived programme {ctx.program_archived.name} will be reopened (its creation was undone)",
            program_id=ctx.program_archived.id,
        )
    fid = _int(p.get("faculty_id"))
    if fid is not None and fid not in ctx.faculties:
        add("program", "error", "unknown_faculty", "program.faculty_id", "Birim bulunamadı", "Unknown unit", id=fid)
    if fid is None and not n.clean_text(p.get("faculty_name")):
        add("program", "error", "no_faculty", "program.faculty", "Birim seçin", "Choose the unit")
    prefix = n.clean_text(p.get("prefix"))
    if prefix:
        if TR_LETTERS.search(prefix):
            add(
                "program",
                "error",
                "prefix_turkish",
                "program.prefix",
                "Ders kodlarında Türkçe harf kullanılmıyor",
                "Course codes use no Turkish letters",
                prefix=prefix,
            )
        elif not PREFIX_RX.match(prefix):
            add(
                "program",
                "error",
                "prefix_shape",
                "program.prefix",
                "Önek 2-4 büyük harf olmalı",
                "The prefix is 2-4 capitals",
            )
    level = p.get("level")
    if level is not None and level not in LEVELS:
        add("program", "warning", "level", "program.level", "Bilinmeyen düzey", "Unknown level", level=level)

    courses = [_dict(c) for c in _list(payload.get("courses"))]
    if not courses:
        add("courses", "error", "no_courses", "courses", "En az bir ders ekleyin", "Add at least one course")
    if len(courses) > MAX_COURSES:
        add("courses", "error", "too_many", "courses", f"En çok {MAX_COURSES} ders", f"At most {MAX_COURSES} courses")
    seen: dict[str, str] = {}
    ects_by_year: dict[int, float] = defaultdict(float)
    keys_in_draft: set[str] = set()
    compulsory_keys: set[str] = set()
    for i, c in enumerate(courses):
        ckey = str(c.get("key") or i)
        keys_in_draft.add(ckey)
        path = f"courses.{ckey}"
        existing_id = _int(c.get("course_id"))
        code, display, err = _code_of(c)
        label = display or n.clean_text(c.get("code")) or "—"
        if err == "empty" and existing_id is None:
            add("courses", "error", "code_empty", f"{path}.code", "Ders kodu gerekli", "The course code is required")
        elif err == "turkish":
            add(
                "courses",
                "error",
                "code_turkish",
                f"{path}.code",
                "Ders kodlarında Türkçe harf kullanılmıyor",
                "Course codes use no Turkish letters",
                code=label,
            )
        elif err == "shape":
            add(
                "courses",
                "error",
                "code_shape",
                f"{path}.code",
                f"'{label}' bir ders kodu değil (ör. MBG 532)",
                f"'{label}' is not a course code (e.g. MBG 532)",
                code=label,
            )
        elif code is not None:
            raw = n.clean_text(c.get("code")) or ""
            k = n.course_key(code)
            if k in seen:
                add(
                    "courses",
                    "error",
                    "duplicate",
                    f"{path}.code",
                    f"{display} taslakta iki kez var",
                    f"{display} is in the draft twice",
                    code=display,
                )
            seen[k] = ckey
            if raw != display:
                add(
                    "courses",
                    "info",
                    "code_fixed",
                    f"{path}.code",
                    f"Ders kodu '{raw}' → {display} olarak düzeltildi",
                    f"Course code '{raw}' → {display}",
                    code=display,
                )
            if existing_id is None and k in ctx.courses_by_key:
                ex = ctx.courses_by_key[k]
                add(
                    "courses",
                    "info",
                    "code_exists",
                    f"{path}.code",
                    f"{ex.display_code} katalogda var; o ders kullanılacak",
                    f"{ex.display_code} is in the catalogue; it is reused",
                    course_id=ex.id,
                )
        if not n.clean_text(c.get("name")) and existing_id is None:
            add(
                "courses",
                "warning",
                "no_course_name",
                f"{path}.name",
                f"{label}: ders adı boş",
                f"{label}: no course name",
                code=label,
            )
        for k in ("t", "u", "l", "credits", "ects"):
            v = _num(c.get(k))
            if v is not None and (v != v or v < 0):
                add(
                    "courses",
                    "error",
                    "bad_number",
                    f"{path}.{k}",
                    f"{label}: {k.upper()} sayı değil",
                    f"{label}: {k.upper()} is not a number",
                    code=label,
                    field=k,
                )
        t, u, l = _hours_of(c)
        hours = t + u + l
        if not hours:
            add(
                "courses",
                "warning",
                "zero_hours",
                f"{path}.t",
                f"{label}: T+U+L = 0; 6. adımda haftalık saat girin",
                f"{label}: T+U+L = 0; enter weekly hours in step 6",
                code=label,
            )
        year = _int(c.get("year")) or 1
        e = _num(c.get("ects"))
        if e is not None and e == e:
            ects_by_year[year] += e
        try:
            mode = ca.parse_mode(c.get("mode"))
        except ca.CatalogError:
            add(
                "courses",
                "error",
                "mode",
                f"{path}.mode",
                "Bilinmeyen öğretim şekli",
                "Unknown delivery mode",
                code=label,
            )
            mode = "F2F"
        if c.get("compulsory", True):
            compulsory_keys.add(ckey)

        # sections
        sections = [_dict(s) for s in _list(c.get("sections"))]
        if not sections:
            add(
                "sections",
                "error",
                "no_sections",
                f"{path}.sections",
                f"{label}: şube yok",
                f"{label}: no section",
                code=label,
            )
        if len(sections) > MAX_SECTIONS:
            add(
                "sections",
                "error",
                "too_many_sections",
                f"{path}.sections",
                "Çok fazla şube",
                "Too many sections",
                code=label,
            )
        labels_seen: set[str] = set()
        for j, s in enumerate(sections):
            skey = str(s.get("key") or j)
            spath = f"{path}.sections.{skey}"
            slabel = n.parse_section_label(s.get("label")) or ""
            if n.tr_casefold(slabel) in labels_seen:
                add(
                    "sections",
                    "error",
                    "duplicate_section",
                    f"{spath}.label",
                    f"{label} §{slabel} iki kez var",
                    f"{label} §{slabel} twice",
                    code=label,
                )
            labels_seen.add(n.tr_casefold(slabel))
            enrol = _num(s.get("enrolment"))
            if enrol is not None and (enrol != enrol or enrol < 0 or not float(enrol).is_integer()):
                add(
                    "sections",
                    "error",
                    "bad_enrolment",
                    f"{spath}.enrolment",
                    f"{label} §{slabel}: öğrenci sayısı sayı değil",
                    f"{label} §{slabel}: enrolment is not a whole number",
                    code=label,
                )
            elif (enrol or 0) <= 0 and mode in n.ROOM_MODES:
                add(
                    "sections",
                    "error",
                    "no_students",
                    f"{spath}.enrolment",
                    f"{label} §{slabel}: öğrenci sayısı 0",
                    f"{label} §{slabel}: 0 students",
                    code=label,
                    section=slabel,
                )
            sec_hours = hours or (_int(_dict(c.get("pattern")).get("weekly_hours")) or 0)
            for jid in (_int(x) for x in _list(s.get("joint_section_ids"))):
                if jid is None:
                    continue
                js = ctx.joint.get(jid)
                if js is None or js.archived:
                    add(
                        "sections",
                        "error",
                        "joint_unknown",
                        f"{spath}.joint",
                        f"Ortak şube #{jid} bulunamadı",
                        f"Joint section #{jid} not found",
                        id=jid,
                    )
                    continue
                jl = f"{js.course.display_code if js.course else '#'}{' §' + js.label if js.label else ''}"
                if js.term_id != ctx.term.id:
                    add(
                        "sections",
                        "error",
                        "joint_other_term",
                        f"{spath}.joint",
                        f"{jl} başka bir dönemde",
                        f"{jl} is in another term",
                        id=jid,
                    )
                    continue
                jp = section_periods(js.meeting_requests)
                if jp and sec_hours and jp != sec_hours:
                    add(
                        "sections",
                        "warning",
                        "joint_length",
                        f"{spath}.joint",
                        f"{label} {sec_hours} saat, {jl} {jp} saat",
                        f"{label} has {sec_hours} periods, {jl} {jp}",
                        code=label,
                        linked=jl,
                    )
                live = [m for m in js.meeting_requests if not m.archived]
                if live and not any(m.definitive_room_ids for m in live):
                    add(
                        "sections",
                        "warning",
                        "joint_no_room_set",
                        f"{spath}.joint",
                        f"{jl} için kesinleşen derslik yok: saat ortak, oda çözücüye kalır",
                        f"{jl} has no definitive room: the time is shared, the room is the solver's",
                        linked=jl,
                    )
                place = ctx.joint_place.get(jid)
                if place and place["cells"]:
                    cell = place["cells"][0]
                    where = f"P{cell['start_period']}-P{cell['end_period']} {' + '.join(cell['rooms'])}"
                    add(
                        "sections",
                        "info",
                        "joint_placed",
                        f"{spath}.joint",
                        f"{jl} yayındaki planda: gün {cell['day']}, {where}",
                        f"{jl} in the published plan: day {cell['day']}, {where}",
                        linked=jl,
                        cell=cell,
                    )
            # instructors
            refs = [r for r in _list(s.get("instructors")) if r]
            if not refs and mode == "F2F":
                add(
                    "instructors",
                    "warning",
                    "no_instructor",
                    f"{spath}.instructors",
                    f"{label} §{slabel}: öğretim elemanı atanmadı; çözüm öğretim elemanı çakışmasını kontrol edemez",
                    f"{label} §{slabel}: no instructor; the solve cannot check instructor clashes",
                    code=label,
                )
            ids_here: set[int] = set()
            new_names_here: dict[str, str] = {}  # new people by canonical name: the commit creates one record
            for slot, ref in enumerate(refs):
                ref = _dict(ref)
                ipath = f"{spath}.instructors.{slot}"
                iid = _int(ref.get("id"))
                if iid is not None:
                    if iid not in ctx.instructors:
                        add(
                            "instructors",
                            "error",
                            "unknown_instructor",
                            ipath,
                            f"Öğretim elemanı #{iid} bulunamadı",
                            f"Instructor #{iid} not found",
                            id=iid,
                        )
                        continue
                    if ctx.instructors[iid].archived:  # chosen on purpose: the commit reopens the record
                        chosen = ctx.instructors[iid]
                        add(
                            "instructors",
                            "info",
                            "instructor_restored",
                            ipath,
                            f"Arşivdeki {chosen.full_name} kaydı yeniden kullanılacak",
                            f"The archived record of {chosen.full_name} will be reused",
                            id=chosen.id,
                        )
                else:
                    nm = n.clean_text(ref.get("name"))
                    if not nm:
                        add(
                            "instructors",
                            "error",
                            "no_instructor_name",
                            ipath,
                            "Yeni kişinin adı gerekli",
                            "The new person needs a name",
                        )
                        continue
                    why = n.non_person_reason(nm)
                    parsed = n.canon_person_name(nm) if why is None else None
                    if parsed is None:
                        add(
                            "instructors",
                            "error",
                            "not_a_person",
                            ipath,
                            f"'{nm}' bir kişi adı değil",
                            f"'{nm}' names no person",
                            name=nm,
                        )
                        continue
                    match = ctx.by_canonical.get(parsed.canonical)
                    gone = ctx.archived_by_canonical.get(parsed.canonical) if match is None else None
                    if match is not None:
                        units = ctx.units.get(match.id, {})
                        elsewhere = sorted(v for k, v in units.items() if k != ctx.program_canonical)
                        add(
                            "instructors",
                            "info",
                            "instructor_matched",
                            ipath,
                            f"'{nm}' → var olan {match.full_name}"
                            + (f" (ders verdiği programlar: {', '.join(elsewhere[:3])})" if elsewhere else ""),
                            f"'{nm}' → existing {match.full_name}"
                            + (f" (teaches in: {', '.join(elsewhere[:3])})" if elsewhere else ""),
                            id=match.id,
                            units=elsewhere,
                        )
                        iid = match.id
                    elif gone is not None:
                        # follow-up 3: a namesake of an archived person (an undone commit). The same name in the
                        # same programme is the same person: the record is reopened. Anywhere else it may be
                        # someone else, and the name cannot be stored twice: the coordinator decides.
                        units = ctx.units.get(gone.id, {})
                        if ctx.program_canonical is not None and ctx.program_canonical in units:
                            add(
                                "instructors",
                                "info",
                                "instructor_restored",
                                ipath,
                                f"'{nm}' → arşivdeki {gone.full_name} kaydı yeniden kullanılacak",
                                f"'{nm}' → the archived record of {gone.full_name} will be reused",
                                id=gone.id,
                            )
                            iid = gone.id
                        else:
                            where = ", ".join(sorted(units.values())[:3])
                            add(
                                "instructors",
                                "error",
                                "instructor_archived_namesake",
                                ipath,
                                f"'{nm}' adıyla arşivlenmiş bir öğretim elemanı var"
                                + (f" ({where})" if where else "")
                                + ". Aynı kişiyse listeden bu kaydı seçin; değilse adı ayırt edici yazın.",
                                f"An archived instructor is named '{nm}'"
                                + (f" ({where})" if where else "")
                                + ". If it is the same person, pick that record; otherwise write the name distinctly.",
                                id=gone.id,
                                name=gone.full_name,
                                units=sorted(units.values()),
                            )
                            continue
                    elif parsed.canonical in new_names_here:
                        # R2-M-07: 'Yeni kişi' pressed twice for the same name: the commit would create one
                        # record and list it twice (catalog_admin: "instructor N is listed twice"), so it is
                        # refused here, on the step, with a fix
                        add(
                            "instructors",
                            "error",
                            "instructor_twice",
                            ipath,
                            f"Bu kişi bu şubede zaten var: {new_names_here[parsed.canonical]}",
                            f"This person is already on this section: {new_names_here[parsed.canonical]}",
                            name=new_names_here[parsed.canonical],
                        )
                        continue
                    else:
                        new_names_here[parsed.canonical] = parsed.full_name
                        add(
                            "instructors",
                            "info",
                            "instructor_new",
                            ipath,
                            f"Yeni kişi: {parsed.full_name}",
                            f"New person: {parsed.full_name}",
                            name=parsed.full_name,
                        )
                if iid is not None:
                    if iid in ids_here:
                        add(
                            "instructors",
                            "error",
                            "instructor_twice",
                            ipath,
                            f"Bu kişi bu şubede zaten var: {ctx.instructors[iid].full_name}",
                            f"This person is already on this section: {ctx.instructors[iid].full_name}",
                            id=iid,
                        )
                    ids_here.add(iid)
                    load = ctx.load.get(iid, 0) + sec_hours
                    if load > ctx.load_limit:
                        add(
                            "instructors",
                            "warning",
                            "load_high",
                            ipath,
                            f"Bu dönem {load} saat (sınır {ctx.load_limit})",
                            f"{load} periods this term (limit {ctx.load_limit})",
                            load=load,
                            limit=ctx.load_limit,
                            id=iid,
                        )

        # weekly pattern + rooms (step 6)
        if mode not in n.ROOM_MODES and mode != "HYBRID":
            continue
        pat = _dict(c.get("pattern"))
        ppath = f"{path}.pattern"
        joint_all = all(_list(s.get("joint_section_ids")) for s in sections) and sections
        if not joint_all:
            if not hours and not (_int(pat.get("weekly_hours")) or 0):
                add(
                    "rooms",
                    "error",
                    "need_weekly_hours",
                    f"{ppath}.weekly_hours",
                    f"{label}: haftalık saat girin",
                    f"{label}: enter the weekly hours",
                    code=label,
                )
            blocks = [b for b in (_int(x) for x in _list(pat.get("theory_blocks"))) if b]
            if hours and blocks and sum(blocks) != t:
                placed = sum(blocks) + u + l
                add(
                    "rooms",
                    "error",
                    "pattern_total",
                    f"{ppath}.theory_blocks",
                    f"{label}: {hours} saatlik ders için yalnızca {placed} saat yerleştirildi",
                    f"{label}: only {placed} of {hours} periods placed",
                    code=label,
                    hours=hours,
                    placed=placed,
                )
            if not pat.get("slots"):
                if not n.clean_text(pat.get("start")) and _int(pat.get("start")) is None:
                    add(
                        "rooms",
                        "error",
                        "no_start",
                        f"{ppath}.start",
                        f"{label}: başlangıç saati gerekli",
                        f"{label}: start time required",
                        code=label,
                    )
                if pat.get("days") in (None, "", []):
                    add(
                        "rooms",
                        "error",
                        "no_days",
                        f"{ppath}.days",
                        f"{label}: gün seçin",
                        f"{label}: choose the days",
                        code=label,
                    )
            body = pattern_body(c, sections[0] if sections else {}, ctx)
            try:
                pt.build_spec(body, course_hours=(t, u, l), max_week=int(ctx.term.week_count or 14))
            except pt.PatternError as exc:
                if not any(i.path.startswith(ppath) and i.level == "error" for i in out):
                    add("rooms", "error", "pattern", ppath, f"{label}: {exc}", f"{label}: {exc}", code=label)
        room = _dict(c.get("room"))
        rpath = f"{path}.room"
        tags = [str(x).upper() for x in _list(room.get("tags")) if x]
        for s in sections:
            cap = _int(room.get("capacity")) or joint_total(s, ctx)
            if not cap:
                continue
            fit = rooms_fit(ctx.rooms, cap, tags, room.get("building"))
            if not fit:
                code = "no_lab_room" if "LAB" in tags else "no_room"
                add(
                    "rooms",
                    "error",
                    code,
                    rpath,
                    f"{label}: {cap} öğrenciye uyan oda yok",
                    f"{label}: no room seats {cap}",
                    code=label,
                    n=cap,
                )
            else:
                add(
                    "rooms",
                    "info",
                    "fits",
                    rpath,
                    f"{label} {cap} öğrenci · sığan odalar: {_fmt_rooms(fit)}",
                    f"{label} {cap} students · rooms that fit: {_fmt_rooms(fit)}",
                    code=label,
                    n=cap,
                    rooms=[room_brief(r) for r in fit[:10]],
                    count=len(fit),
                )
                if int(fit[0].capacity or 0) == cap and len(fit) <= 4:
                    add(
                        "rooms",
                        "warning",
                        "exact_fit",
                        rpath,
                        f"{fit[0].display_name} tam {cap} kişilik; kayıt artarsa sığmaz",
                        f"{fit[0].display_name} seats exactly {cap}; more students won't fit",
                        code=label,
                        room=fit[0].display_name,
                    )
            pref = n.clean_text(room.get("preferred"))
            if pref:
                pr = _find_room(ctx.rooms, pref)
                if pr is None or not pr.is_bookable or not pr.capacity:
                    add(
                        "rooms",
                        "warning",
                        "preferred_unknown",
                        f"{rpath}.preferred",
                        f"{pref}: kapasite bilinmiyor ve planlanabilir oda havuzunda değil",
                        f"{pref}: unknown capacity, not in the plannable pool",
                        room=pref,
                    )
                elif int(pr.capacity or 0) < cap:
                    fit_n, fits = len(fit), _fmt_rooms(fit)
                    add(
                        "rooms",
                        "warning",
                        "preferred_small",
                        f"{rpath}.preferred",
                        f"{pr.display_name} ({pr.capacity}) {cap} öğrenciye yetmez · {fit_n} oda sığar: {fits}",
                        f"{pr.display_name} ({pr.capacity}) is too small for {cap} · {fit_n} rooms fit: {fits}",
                        room=pr.display_name,
                        seats=pr.capacity,
                        n=cap,
                    )
            break  # one consequence line per course (sections of one course share the room need)
    for year, ects in ects_by_year.items():
        if ects > 30:
            add(
                "courses",
                "warning",
                "ects_high",
                "courses",
                f"{year}. sınıf: {ects:g} AKTS (> 30)",
                f"Year {year}: {ects:g} ECTS (> 30)",
                year=year,
                ects=ects,
            )

    cohorts = [_dict(x) for x in _list(payload.get("cohorts"))]
    in_cohort: set[str] = set()
    for ci, co in enumerate(cohorts):
        cpath = f"cohorts.{co.get('key') or ci}"
        members = [str(x) for x in _list(co.get("compulsory"))] + [
            str(x) for g in _list(co.get("elective_groups")) for x in _list(g)
        ]
        for m in members:
            if m not in keys_in_draft:
                add(
                    "cohorts",
                    "error",
                    "cohort_unknown_course",
                    cpath,
                    f"Kohortta bilinmeyen ders: {m}",
                    f"Unknown course in cohort: {m}",
                    key=m,
                )
        in_cohort |= set(members)
        hours = 0
        for c in courses:
            if str(c.get("key")) in {str(x) for x in _list(co.get("compulsory"))}:
                t, u, l = _hours_of(c)
                hours += (t + u + l) or (_int(_dict(c.get("pattern")).get("weekly_hours")) or 0)
        if hours:
            days = -(-hours // 8)
            add(
                "cohorts",
                "info",
                "cohort_hours",
                cpath,
                f"Haftada {hours} saat zorunlu ders; kohort için en az {days} gün gerekir",
                f"{hours} compulsory periods a week; at least {days} days",
                hours=hours,
                days=days,
            )
    if cohorts:
        for key in sorted(compulsory_keys - in_cohort):
            add(
                "cohorts",
                "warning",
                "not_in_cohort",
                f"courses.{key}",
                "Zorunlu ders hiçbir kohortta değil",
                "A compulsory course is in no cohort",
                key=key,
            )

    w = _dict(_dict(payload.get("rules")).get("window"))
    if w.get("enabled") and (_int(w.get("earliest")) or 1) > (_int(w.get("latest")) or 18):
        add(
            "constraints",
            "error",
            "window_order",
            "rules.window",
            "Pencere başlangıcı bitişinden sonra",
            "The window starts after it ends",
        )
    return out


def steps_of(issues: list[Issue], payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    courses = _list(payload.get("courses"))
    empty = {
        "program": not n.clean_text(_dict(payload.get("program")).get("name")),
        "courses": not courses,
        "sections": not courses,
        "instructors": not courses,
        "cohorts": not _list(payload.get("cohorts")),
        "rooms": not any(_dict(_dict(c).get("pattern")) for c in courses),
        "constraints": False,
        "generate": False,
    }
    out = []
    for step in STEPS:
        mine = [i for i in issues if i.step == step]
        errors = [i.out() for i in mine if i.level == "error"]
        warnings = [i.out() for i in mine if i.level == "warning"]
        status = "error" if errors else "warning" if warnings else "empty" if empty[step] else "ok"
        out.append(
            {
                "step": step,
                "status": status,
                "errors": errors,
                "warnings": warnings,
                "info": [i.out() for i in mine if i.level == "info"],
            }
        )
    return out


def summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    courses = [_dict(c) for c in _list(payload.get("courses"))]
    sections = [_dict(s) for c in courses for s in _list(c.get("sections"))]
    people: set[str] = set()
    fresh: set[str] = set()
    for s in sections:
        for ref in _list(s.get("instructors")):
            ref = _dict(ref)
            if _int(ref.get("id")) is not None:
                people.add(f"#{ref['id']}")
            elif n.clean_text(ref.get("name")):
                people.add(n.tr_casefold(ref["name"]))
                fresh.add(n.tr_casefold(ref["name"]))
    hours = 0
    for c in courses:
        t, u, l = _hours_of(c)
        hours += (t + u + l) or (_int(_dict(c.get("pattern")).get("weekly_hours")) or 0)
    ects = sum(e for e in (_num(c.get("ects")) for c in courses) if e is not None and e == e)
    return {
        "courses": len(courses),
        "sections": len(sections),
        "joint_links": sum(len(_list(s.get("joint_section_ids"))) for s in sections),
        "people": len(people),
        "new_people": len(fresh),
        "cohorts": len(_list(payload.get("cohorts"))),
        "weekly_hours": hours,
        "ects": ects,
    }


async def validate(
    session: AsyncSession, draft: ProgramDraft, *, step: str | None = None, precheck: bool = False
) -> dict[str, Any]:
    term = await session.get(Term, draft.term_id)
    if term is None:
        raise DraftError(404, "term not found")
    payload = normalise(draft.payload or {})
    ctx = await load_context(session, term, payload)
    issues = validate_payload(payload, ctx)
    pre = None
    if precheck and not any(i.level == "error" for i in issues):
        pre = await program_precheck(draft)
        for it in pre["items"]:
            if it["severity"] in ("error", "warning"):
                issues.append(
                    Issue(
                        "constraints",
                        it["severity"],
                        f"precheck_{it['group']}",
                        "precheck",
                        it["title"]["tr"],
                        it["title"]["en"],
                        {"item_id": it["id"]},
                    )
                )
    steps = steps_of(issues, payload)
    wanted = STEP_ALIASES.get(step or "", step)
    if wanted:
        steps = [s for s in steps if s["step"] == wanted]
    errors = sum(1 for i in issues if i.level == "error")
    return {
        "draft_id": draft.id,
        "version": draft.version,
        "can_commit": errors == 0,
        "counts": {
            "errors": errors,
            "warnings": sum(1 for i in issues if i.level == "warning"),
            "info": sum(1 for i in issues if i.level == "info"),
        },
        "steps": steps,
        "issues": [i.out() for i in issues if not wanted or i.step == wanted],
        "summary": summary(payload),
        "precheck": pre,
    }


# --------------------------------------------------------------------------- CRUD + autosave (P19-W-01)


def draft_out(d: ProgramDraft, *, full: bool = True) -> dict[str, Any]:
    out = {
        "id": d.id,
        "term_id": d.term_id,
        "owner_id": d.owner_id,
        "title": d.title,
        "step": d.step,
        "version": d.version,
        "status": d.status,
        "program_id": d.program_id,
        "commit_audit_id": d.commit_audit_id,
        "committed_at": d.committed_at.isoformat() if d.committed_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "updated_by": d.updated_by,
        "summary": summary(normalise(d.payload or {})),
    }
    if full:
        out["payload"] = d.payload or {}
        out["created"] = (d.meta or {}).get("created")
    return out


def _title(payload: Mapping[str, Any]) -> str | None:
    return (n.clean_text(_dict(normalise(payload).get("program")).get("name")) or None) if payload else None


async def create(
    session: AsyncSession, actor: User, term_id: int, payload: Mapping[str, Any] | None, step: str | None
) -> ProgramDraft:
    if await session.get(Term, term_id) is None:
        raise DraftError(404, "term not found")
    data = dict(payload or {})
    d = ProgramDraft(
        term_id=term_id,
        owner_id=actor.id,
        payload=data,
        meta={"paths": {}},
        version=1,
        status="draft",
        step=step,
        title=_title(data),
        updated_by=actor.id,
    )
    session.add(d)
    await session.commit()
    await session.refresh(d)
    return d


async def get_draft(
    session: AsyncSession, draft_id: int, actor: User | None = None, *, admin: bool = False
) -> ProgramDraft:
    d = await session.get(ProgramDraft, draft_id)
    if d is None:
        raise DraftError(404, "draft not found")
    return d


async def list_drafts(
    session: AsyncSession, actor: User, *, mine: bool = True, term_id: int | None = None, status: str | None = "draft"
) -> list[dict[str, Any]]:
    q = select(ProgramDraft)
    if mine:
        q = q.where(ProgramDraft.owner_id == actor.id)
    if term_id is not None:
        q = q.where(ProgramDraft.term_id == term_id)
    if status:
        q = q.where(ProgramDraft.status == status)
    rows = list((await session.execute(q.order_by(ProgramDraft.updated_at.desc(), ProgramDraft.id.desc()))).scalars())
    terms = {t.id: t.code for t in (await session.execute(select(Term))).scalars()}
    return [{**draft_out(d, full=False), "term_code": terms.get(d.term_id)} for d in rows]


def _segments(path: str) -> list[str]:
    segs = [s for s in re.split(r"[./]", path.strip()) if s != ""]
    if not segs:
        raise DraftError(422, "path is empty")
    return segs


def _step_into(node: Any, seg: str, create: bool) -> tuple[Any, Any]:
    """(container, key) for ``seg`` in ``node``: list items by index, ``-`` (append) or by their ``key``."""
    if isinstance(node, list):
        if seg == "-":
            return node, len(node)
        if seg.isdigit():
            return node, int(seg)
        for i, item in enumerate(node):
            if isinstance(item, dict) and str(item.get("key")) == seg:
                return node, i
        raise DraftError(422, f"no list item with key {seg!r}")
    if isinstance(node, dict):
        return node, seg
    raise DraftError(422, f"cannot descend into {type(node).__name__} at {seg!r}")


def apply_op(payload: dict[str, Any], path: str, value: Any, op: str = "set") -> Any:
    """Set / remove one field of the payload in place; returns the overwritten value."""
    segs = _segments(path)
    node: Any = payload
    for i, seg in enumerate(segs[:-1]):
        cont, key = _step_into(node, seg, True)
        if isinstance(cont, list):
            if key >= len(cont):
                raise DraftError(422, f"index {key} out of range at {'.'.join(segs[: i + 1])}")
            node = cont[key]
        else:
            if key not in cont or cont[key] is None:
                cont[key] = [] if segs[i + 1].isdigit() or segs[i + 1] == "-" else {}
            node = cont[key]
    cont, key = _step_into(node, segs[-1], True)
    if isinstance(cont, list):
        old = cont[key] if key < len(cont) else None
        if op == "remove":
            if key < len(cont):
                del cont[key]
        elif key == len(cont):
            cont.append(value)
        elif key < len(cont):
            cont[key] = value
        else:
            raise DraftError(422, f"index {key} out of range")
        return old
    old = cont.get(key)
    if op == "remove":
        cont.pop(key, None)
    else:
        cont[key] = value
    return old


async def patch(
    session: AsyncSession,
    draft: ProgramDraft,
    actor: User,
    *,
    ops: list[dict[str, Any]] | None = None,
    payload: Mapping[str, Any] | None = None,
    base_version: int | None = None,
    step: str | None = None,
) -> dict[str, Any]:
    """Autosave: field ops (``{path, value, op: set|remove}``, last write wins per field; a path written by someone
    else after ``base_version`` comes back in ``overwritten`` so the UI can show the info line) or a whole
    ``payload`` (refused with 409 when ``base_version`` is stale). Returns the new version and the validation."""
    from sqlalchemy.orm.attributes import flag_modified

    if draft.status != "draft":
        raise DraftError(409, f"the draft is {draft.status}; it is read-only")
    cur = int(draft.version or 1)
    meta = copy.deepcopy(draft.meta or {})
    paths: dict[str, Any] = dict(meta.get("paths") or {})
    data = copy.deepcopy(draft.payload or {})
    overwritten: list[dict[str, Any]] = []
    new_version = cur + 1
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if payload is not None:
        if base_version is not None and base_version != cur:
            raise DraftError(
                409,
                {"message": "the draft changed since you loaded it", "version": cur, "updated_by": draft.updated_by},
            )
        data = dict(payload)
        paths = {"*": {"v": new_version, "by": actor.id, "at": now}}
    for op in ops or []:
        path = str(op.get("path") or "")
        kind = str(op.get("op") or "set")
        if kind not in ("set", "remove"):
            raise DraftError(422, "op must be set or remove")
        if base_version is not None and base_version < cur:
            for p, info in paths.items():
                if (
                    (p == path or p.startswith(path + ".") or path.startswith(p + ".") or p == "*")
                    and int(info.get("v", 0)) > base_version
                    and info.get("by") != actor.id
                ):
                    overwritten.append({"path": path, "by": info.get("by"), "at": info.get("at"), "previous": None})
                    break
        old = apply_op(data, path, op.get("value"), kind)
        if overwritten and overwritten[-1]["path"] == path and overwritten[-1]["previous"] is None:
            overwritten[-1]["previous"] = old
        paths[path] = {"v": new_version, "by": actor.id, "at": now}
    if len(paths) > 2000:  # keep the merge memory bounded
        paths = dict(sorted(paths.items(), key=lambda kv: -int(kv[1].get("v", 0)))[:1000])
    meta["paths"] = paths
    draft.payload = data
    draft.meta = meta
    flag_modified(draft, "payload")
    flag_modified(draft, "meta")
    draft.version = new_version
    draft.updated_by = actor.id
    draft.updated_at = utcnow()
    draft.title = _title(data)
    if step is not None:
        draft.step = step
    await session.commit()
    await session.refresh(draft)
    return {
        "id": draft.id,
        "version": draft.version,
        "overwritten": overwritten,
        "validation": await validate(session, draft),
    }


async def delete(session: AsyncSession, draft: ProgramDraft) -> None:
    if draft.status == "committed":
        raise DraftError(409, "a committed draft is the undo record of its programme; undo the commit instead")
    await session.delete(draft)
    await session.commit()


# --------------------------------------------------------------------------- TSV paste preview (P19-W-03)

HEADER_WORDS = {
    "kod": "code", "code": "code", "ders kodu": "code", "ders": "code", "ad": "name", "adı": "name", "ders adı": "name",
    "name": "name", "t": "t", "u": "u", "l": "l", "k": "credits", "kredi": "credits", "akts": "ects", "ects": "ects",
    "sınıf": "year", "sinif": "year", "year": "year", "şube": "label", "sube": "label", "öğrenci": "enrolment",
    "ogrenci": "enrolment", "kontenjan": "enrolment",
}  # fmt: skip
DEFAULT_COLUMNS = ("code", "name", "t", "u", "l", "credits", "ects", "year")


def paste_preview(tsv: str) -> dict[str, Any]:
    """Excel copies rows as TSV: header detection (Kod / Ad / T / U / L / K / AKTS / Sınıf), NBSP, comma decimals and
    the course-code fix per row; nothing is stored."""
    lines = (tsv or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    columns = list(DEFAULT_COLUMNS)
    rows: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        if not (n.clean_text(line) or ""):
            if i < len(lines):
                ignored.append({"line": i, "reason": "empty"})
            continue
        cells = [n.clean_text(c) or "" for c in line.split("\t")]
        header = [HEADER_WORDS.get(n.tr_casefold(c)) for c in cells]
        if not rows and sum(1 for h in header if h) >= 2:
            columns = [h or f"skip{j}" for j, h in enumerate(header)]
            ignored.append({"line": i, "reason": "header"})
            continue
        get = {col: (cells[j] if j < len(cells) else "") for j, col in enumerate(columns)}
        if not get.get("code"):
            ignored.append({"line": i, "reason": "no_code"})
            continue
        code, display, err = _code_of({"code": get["code"]})
        row: dict[str, Any] = {
            "line": i,
            "code": display or get["code"],
            "code_error": err,
            "name": get.get("name") or "",
        }
        for k in ("t", "u", "l", "credits", "ects", "year", "enrolment"):
            v = _num(get.get(k))
            row[k] = None if v is None or v != v else (int(v) if float(v).is_integer() else v)
        rows.append(row)
    return {"columns": columns, "rows": rows, "ignored": ignored}


# --------------------------------------------------------------------------- materialise (commit + dry run)


@dataclass
class Created:
    faculty_id: int | None = None
    program_id: int | None = None
    program_audit_id: int | None = None
    courses: list[int] = field(default_factory=list)
    reused_courses: list[int] = field(default_factory=list)
    instructors: list[int] = field(default_factory=list)
    reused_instructors: list[int] = field(default_factory=list)
    sections: list[int] = field(default_factory=list)
    meetings: list[int] = field(default_factory=list)
    rules: list[int] = field(default_factory=list)
    joint_links: list[dict[str, int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: archived rows the commit reopened (follow-ups 2 + 3); they are also in the lists above, so an undo of this
    #: commit archives them again
    restored: dict[str, Any] = field(
        default_factory=lambda: {"faculty_id": None, "program_id": None, "courses": [], "people": []}
    )

    def out(self) -> dict[str, Any]:
        return {
            "faculty_id": self.faculty_id,
            "program_id": self.program_id,
            "courses": self.courses,
            "reused_courses": self.reused_courses,
            "people": self.instructors,
            "reused_people": self.reused_instructors,
            "sections": self.sections,
            "requests": self.meetings,
            "rules": self.rules,
            "joint_links": self.joint_links,
            "restored": self.restored,
        }


async def _reopen(session: AsyncSession, actor: User, obj: Any, entity: str, **changes: Any) -> int | None:
    """Un-archive ``obj`` (an undone commit's row), apply ``changes`` and audit ``<entity>.restore``; returns the
    audit event id."""
    from app.services import audit as audit_svc

    before = audit_svc.snapshot(obj)
    obj.archived = False
    for k, v in changes.items():
        setattr(obj, k, v)
    await session.flush()
    ev = await publish_event(
        session, f"{entity}.restore", entity, obj.id, before=before, after=audit_svc.snapshot(obj), actor=actor
    )
    return ev.id if ev is not None else None


async def _rule(
    session: AsyncSession,
    actor: User,
    term_id: int,
    kind: str,
    params: dict[str, Any],
    hardness: str,
    weight: int,
    text: str,
) -> int:
    from app.ai.catalog import validate_params
    from app.services.constraint_guard import guard_rule

    issues = validate_params(kind, dict(params), hardness) + guard_rule(
        kind, params, hardness, source="ADMIN", may_waive=False, reason=None
    )
    if issues:
        raise DraftError(422, {"message": "invalid rule", "issues": issues[:10]})
    from app.services import pin_guard

    short = await pin_guard.shortfalls(session, kind, params, hardness, term_id=term_id)
    if short:  # round-1 R1-M-03
        raise DraftError(422, pin_guard.refusal(short, overridable=False))
    row = ConstraintRow(
        term_id=term_id,
        run_id=None,
        kind=kind,
        params=params,
        hardness=hardness,
        weight=weight,
        source="ADMIN",
        nl_text=text,
        enabled=True,
        created_by=actor.id,
        source_ref={"program_draft": True},
    )
    session.add(row)
    await session.flush()
    await publish_event(
        session,
        "constraint.create",
        "constraint",
        row.id,
        after={"kind": kind, "params": params, "hardness": hardness, "weight": weight},
        actor=actor,
        term_id=term_id,
    )
    return row.id


async def _joint_meetings(session: AsyncSession, actor: User, sec: Section, linked: Section) -> list[MeetingRequest]:
    """The new section meets with ``linked``: copies of its live meetings (day, periods, weeks, the planner's room
    set and status), so the bridge merges them into one lecture (``merge_joint_lectures``)."""
    out: list[MeetingRequest] = []
    code = linked.course.display_code if linked.course else "#"
    tag = f"Ortak ders: {code}{' §' + linked.label if linked.label else ''} (#{linked.id})"
    for m in sorted((m for m in linked.meeting_requests if not m.archived), key=lambda m: m.id):
        mr = MeetingRequest(
            section_id=sec.id,
            day=m.day,
            days=list(m.days or ([] if m.day is None else [m.day])),
            start_period=m.start_period,
            end_period=m.end_period,
            start_time=m.start_time,
            end_time=m.end_time,
            weeks=list(m.weeks or []),
            requested_room_text=m.requested_room_text,
            requested_room_ids=list(m.requested_room_ids or []),
            requested_building=m.requested_building,
            requested_tags=list(m.requested_tags or []),
            requested_capacity=None,
            flexible_day=bool(m.flexible_day),
            needs_room=bool(m.needs_room) and sec.mode in n.ROOM_MODES,
            definitive_room_text=m.definitive_room_text,
            definitive_room_ids=list(m.definitive_room_ids or []),
            status=m.status if m.status in ("LOCKED", "PARSED") else "PARSED",
            parse_warnings=[],
            notes=tag,
            source_key=ca.man_key(),
            source_row_index=None,
            archived=False,
        )
        mr.duration_periods = m.duration_periods
        session.add(mr)
        out.append(mr)
    await session.flush()
    for mr in out:
        await publish_event(
            session,
            "meeting.create",
            "meeting",
            mr.id,
            after={"section_id": sec.id, "joint_with": linked.id, "day": mr.day, "start_period": mr.start_period},
            actor=actor,
            term_id=sec.term_id,
        )
    return out


async def materialise(session: AsyncSession, draft: ProgramDraft, actor: User) -> Created:
    """Write the draft into the term (flush only; the caller commits or rolls back). Errors raise
    :class:`DraftError` 422 naming the failing path."""
    term = await session.get(Term, draft.term_id)
    if term is None:
        raise DraftError(404, "term not found")
    payload = normalise(draft.payload or {})
    ctx = await load_context(session, term, payload)
    issues = validate_payload(payload, ctx)
    errors = [i.out() for i in issues if i.level == "error"]
    if errors:
        raise DraftError(
            422,
            {
                "message": "the draft has errors",
                "message_tr": "Taslakta düzeltilmesi gereken hatalar var",
                "issues": errors[:50],
                "errors": len(errors),
            },
        )
    made = Created()
    p = _dict(payload.get("program"))
    path = "program"
    try:
        fid = _int(p.get("faculty_id"))
        if fid is None:
            parsed = n.canon_faculty(n.clean_text(p.get("faculty_name")) or "")
            clash = (
                (await session.execute(select(Faculty).where(Faculty.canonical_name == parsed.canonical)))
                .scalars()
                .first()
                if parsed
                else None
            )
            if clash is not None:
                fid = clash.id
                if clash.archived:  # the unit of an undone commit
                    await _reopen(session, actor, clash, "faculty")
                    made.faculty_id = made.restored["faculty_id"] = clash.id
            else:
                f = await ca.create_faculty(session, actor, p.get("faculty_name"))
                fid, made.faculty_id = f.id, f.id
        if ctx.program_archived is not None:
            # follow-up 2: the programme's creation was undone; the name is unique, so the archived row is reopened
            prog = ctx.program_archived
            parsed_prog = n.canon_program(n.clean_text(p.get("name")) or "")
            assert parsed_prog is not None  # validated
            made.program_audit_id = await _reopen(
                session,
                actor,
                prog,
                "program",
                name=parsed_prog.name,
                faculty_id=fid,
                is_evening=bool(p.get("evening")) if p.get("evening") is not None else parsed_prog.is_evening,
            )
            made.program_id = made.restored["program_id"] = prog.id
        else:
            prog = await ca.create_program(
                session,
                actor,
                name=p.get("name"),
                faculty_id=fid,
                is_evening=bool(p.get("evening")) if p.get("evening") is not None else None,
            )
            made.program_id = prog.id
            made.program_audit_id = (
                await session.execute(
                    select(AuditEvent.id)
                    .where(AuditEvent.action == "program.create", AuditEvent.entity_id == str(prog.id))
                    .order_by(AuditEvent.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        async def reuse_course(course: Course) -> None:
            if course.archived:  # a course of an undone commit: reopened, and archived again by this one's undo
                await _reopen(session, actor, course, "course")
                if course.id not in made.courses:
                    made.courses.append(course.id)
                    made.restored["courses"].append(course.id)
            elif course.id not in made.courses:
                made.reused_courses.append(course.id)

        async def reuse_person(ins: Instructor) -> None:
            if ins.archived:
                await _reopen(session, actor, ins, "instructor")
                made.instructors.append(ins.id)
                made.restored["people"].append(ins.id)
            elif ins.id not in made.instructors:
                made.reused_instructors.append(ins.id)

        people: dict[str, int] = {}
        for i, c in enumerate(_dict(x) for x in _list(payload.get("courses"))):
            path = f"courses.{c.get('key') or i}"
            cid = _int(c.get("course_id"))
            if cid is not None:
                course = await session.get(Course, cid)
                if course is None:
                    raise DraftError(422, {"message": f"course {cid} not found", "path": path})
                await reuse_course(course)
            else:
                code, _display, _err = _code_of(c)
                course = ctx.courses_by_key.get(n.course_key(code or ""))
                if course is not None:
                    await reuse_course(course)
                else:
                    data = {
                        "code": c.get("code"),
                        "name": c.get("name"),
                        "t_hours": _hours_of(c)[0],
                        "u_hours": _hours_of(c)[1],
                        "l_hours": _hours_of(c)[2],
                    }
                    for k in ("credits", "ects"):
                        if c.get(k) not in (None, ""):
                            data[k] = c.get(k)
                    course = await ca.create_course(session, actor, data)
                    made.courses.append(course.id)
            mode = ca.parse_mode(c.get("mode"))
            year = _int(c.get("year")) or 1
            for j, s in enumerate(_dict(x) for x in _list(c.get("sections"))):
                path = f"{path}.sections.{s.get('key') or j}"
                links: list[dict[str, Any]] = []
                for slot, ref in enumerate(r for r in _list(s.get("instructors")) if r):
                    ref = _dict(ref)
                    iid = _int(ref.get("id"))
                    if iid is not None:
                        chosen = ctx.instructors.get(iid)
                        if chosen is not None and iid not in people.values():
                            await reuse_person(chosen)
                            people[chosen.canonical_name] = iid
                    else:
                        parsed_p = n.canon_person_name(n.clean_text(ref.get("name")) or "")
                        assert parsed_p is not None  # validated
                        if parsed_p.canonical in people:
                            iid = people[parsed_p.canonical]
                        elif parsed_p.canonical in ctx.by_canonical:
                            iid = ctx.by_canonical[parsed_p.canonical].id
                            await reuse_person(ctx.by_canonical[parsed_p.canonical])
                        elif parsed_p.canonical in ctx.archived_by_canonical:  # validated: same programme
                            iid = ctx.archived_by_canonical[parsed_p.canonical].id
                            await reuse_person(ctx.archived_by_canonical[parsed_p.canonical])
                        else:
                            ins = await ca.create_instructor(
                                session,
                                actor,
                                {"full_name": ref.get("name"), "title": ref.get("title"), "email": ref.get("email")},
                            )
                            iid = ins.id
                            made.instructors.append(iid)
                        people[parsed_p.canonical] = iid
                    links.append({"instructor_id": iid, "role": "PRIMARY" if slot == 0 else "SECONDARY"})
                enrol = _int(s.get("enrolment"))
                sec = await ca.create_section(
                    session,
                    actor,
                    {
                        "term_id": term.id,
                        "course_id": course.id,
                        "program_id": prog.id,
                        "label": s.get("label") or "1",
                        "class_years": [year],
                        "enrolment": enrol,
                        "mode": mode,
                        "instructors": links,
                        "notes": c.get("note") or c.get("notes"),
                    },
                )
                made.sections.append(sec.id)
                joint = [ctx.joint[j] for j in (_int(x) for x in _list(s.get("joint_section_ids"))) if j in ctx.joint]
                if joint:
                    # one shared meeting set: the first link's meetings (the others meet at the same time)
                    sec_full = await ca.load_section(session, sec.id)
                    mrs = await _joint_meetings(session, actor, sec_full, joint[0])
                    made.meetings += [m.id for m in mrs]
                    made.joint_links += [{"section_id": sec.id, "linked_section_id": js.id} for js in joint]
                else:
                    _sec, created, _arch, warns, _ev = await ca.apply_pattern(
                        session, actor, sec.id, pattern_body(c, s, ctx), replace=False
                    )
                    made.meetings += [m.id for m in created]
                    made.warnings += warns
        rules = _dict(payload.get("rules"))
        if made.meetings:
            w = _dict(rules.get("window"))
            name = prog.name
            if w.get("enabled"):
                hard = bool(w.get("hard"))
                params = {
                    "event_ids": sorted(made.meetings),
                    "earliest": _int(w.get("earliest")) or 1,
                    "latest": _int(w.get("latest")) or 18,
                }
                made.rules.append(
                    await _rule(
                        session,
                        actor,
                        term.id,
                        "day_window",
                        params,
                        "hard" if hard else "soft",
                        1 if hard else 10,
                        f"{name}: P{params['earliest']}–P{params['latest']}",
                    )
                )
            if rules.get("same_room"):
                made.rules.append(
                    await _rule(
                        session,
                        actor,
                        term.id,
                        "same_room_across_weeks",
                        {"event_ids": sorted(made.meetings)},
                        "soft",
                        10,
                        f"{name}: aynı oda / same room",
                    )
                )
    except ca.CatalogError as exc:
        raise DraftError(
            exc.status if exc.status != 400 else 422,
            {"message": exc.message, "message_tr": catalog_tr(exc.message), "path": path, **exc.extra},
        ) from exc
    await session.flush()
    return made


_EXISTS = re.compile(r"^(faculty|unit|programme|course|instructor) (.+) already exists$")
_EXISTS_TR = {
    "faculty": "Birim",
    "unit": "Birim",
    "programme": "Program",
    "course": "Ders",
    "instructor": "Öğretim elemanı",
}


def catalog_tr(message: str) -> str:
    """A Turkish line for a catalogue refusal the validation did not foresee (the English one stays in
    ``message``)."""
    m = _EXISTS.match(message or "")
    if m:
        return f"{_EXISTS_TR[m.group(1)]} {m.group(2)} zaten kayıtlı; taslakta var olan kaydı seçin"
    return f"Kayıt yazılamadı: {message}"


async def program_precheck(draft: ProgramDraft) -> dict[str, Any]:
    """P19-W-06: the Studio static pre-check of the term with the draft's classes written in, in a session that is
    rolled back (nothing is stored). Items are kept when they involve one of the draft's classes; ``counts`` and
    ``readiness`` describe those only. Also returns the rooms that fit each new class."""
    from app.core.db import get_session_factory
    from app.services import precheck as pc
    from app.services.solver_bridge import build_solver_input
    from app.solver.build import prepare
    from app.solver.diagnose import static_check

    factory = get_session_factory()
    async with factory() as s:
        try:
            d = await s.get(ProgramDraft, draft.id)
            assert d is not None
            actor = await s.get(User, d.owner_id) if d.owner_id else None
            if actor is None:
                actor = (await s.execute(select(User).order_by(User.id))).scalars().first()
            assert actor is not None
            made = await materialise(s, d, actor)
            probe = ScheduleRun(term_id=d.term_id, kind="COURSE", horizon="TERM", horizon_params={}, params={})
            inp, members = await build_solver_input(s, probe)
            mine = set(made.meetings)
            head_of = {m: h for h, ms in members.items() for m in ms}
            heads = {head_of.get(m, m) for m in mine}
            names = {i.id: i.full_name for i in (await s.execute(select(Instructor))).scalars()}
            all_rooms = list((await s.execute(select(Room))).scalars())
            from app.services.studio import DraftInput

            din = DraftInput(inp=inp, members=members, excluded=[])
            ctx = pc._Ctx(
                din,
                {r.id: r for r in inp.rooms},
                names,
                {r.code: r.display_name for r in all_rooms},
                {r.id: r.display_name for r in all_rooms},
            )  # noqa: SLF001
            items = []
            if inp.events:
                for diag in static_check(prepare(inp)):
                    if heads & set(diag.event_ids or []):
                        items.append(pc._from_diagnosis(ctx, diag))  # noqa: SLF001
            fits = []
            by_id = {e.id: e for e in inp.events}
            for h in sorted(heads):
                e = by_id.get(h)
                if e is None:
                    continue
                fit = ctx.fitting_rooms(e, limit=10)
                fits.append(
                    {
                        "event_id": h,
                        "label": e.label,
                        "size": e.size,
                        "request_ids": members.get(h, [h]),
                        "rooms": [{"id": r.id, "code": r.code, "capacity": r.capacity} for r in fit],
                    }
                )
        finally:
            await s.rollback()
    errors = sum(1 for it in items if it["severity"] == "error")
    warnings = sum(1 for it in items if it["severity"] == "warning")
    return {
        "readiness": "blocked" if errors else "needs_look" if warnings else "ready",
        "counts": {"errors": errors, "warnings": warnings, "events": len(heads), "requests": len(mine)},
        "items": items,
        "rooms_fit": fits,
        "joint_merged": sorted(h for h in heads if len(members.get(h, [])) > 1),
    }


# --------------------------------------------------------------------------- commit (P19-W-07)


async def commit(session: AsyncSession, draft: ProgramDraft, actor: User, *, solve: str = "none") -> dict[str, Any]:
    """One transaction: everything the draft describes, ``program_draft.commit`` audited with every id, the draft
    marked committed (it stays as the undo record). ``solve="minimal"`` then starts a minimal-change re-solve of
    the term's published run with the new requests as the changed ones (``moderation.create_resolve``, repair,
    never activated): the UI opens ``/moderation/recreate/{run_id}``. Without a published run ``run_id`` is null
    and ``next`` says ``studio``."""
    from app.services import term_lock

    if draft.status != "draft":
        raise DraftError(409, f"the draft is already {draft.status}")
    if solve not in ("none", "minimal"):
        raise DraftError(422, "solve must be none or minimal")
    term = await session.get(Term, draft.term_id)
    if term is None:
        raise DraftError(404, "term not found")
    try:
        async with term_lock.term_write_lock(term_lock.term_key(term.code), f"program-draft:{draft.id}", wait_s=30):
            try:
                made = await materialise(session, draft, actor)
                ev = await publish_event(
                    session,
                    "program_draft.commit",
                    "program_draft",
                    draft.id,
                    after={"program_audit_id": made.program_audit_id, **made.out()},
                    actor=actor,
                    term_id=term.id,
                )
                draft.status = "committed"
                draft.program_id = made.program_id
                draft.commit_audit_id = made.program_audit_id
                draft.committed_at = utcnow()
                meta = dict(draft.meta or {})
                meta["created"] = {**made.out(), "commit_event_id": ev.id if ev else None, "warnings": made.warnings}
                draft.meta = meta
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    except term_lock.TermLocked as exc:
        raise DraftError(409, {"code": "term_locked", "message": str(exc)}) from exc
    run_id = None
    nxt = "program"
    if solve == "minimal" and made.meetings:
        from app.services import moderation as mod

        base = await mod.published_run(session, term.id)
        if base is not None and base.status in mod.BASE_STATUSES:
            child = await mod.create_resolve(session, term, base, made.meetings, "repair", actor)
            run_id = child.id
            mod.enqueue_resolve(child.id)
            nxt = "moderation_preview"
        else:
            nxt = "studio"
    return {
        "draft_id": draft.id,
        "program_id": made.program_id,
        "created": made.out(),
        "counts": {k: len(v) for k, v in made.out().items() if isinstance(v, list)},
        "audit_id": made.program_audit_id,
        "warnings": made.warnings,
        "run_id": run_id,
        "next": nxt,
        "undo_until": (draft.committed_at + timedelta(days=UNDO_DAYS)).isoformat() if draft.committed_at else None,
    }


# --------------------------------------------------------------------------- undo (P19-W-08)


async def undo_blockers(session: AsyncSession, draft: ProgramDraft) -> list[dict[str, Any]]:
    """Why the commit cannot be undone: every reference to its rows from outside the commit."""
    from app.services.moderation import published_run

    made = _dict((draft.meta or {}).get("created"))
    out: list[dict[str, Any]] = []
    secs = [int(x) for x in _list(made.get("sections"))]
    meets = [int(x) for x in _list(made.get("requests"))]
    prog = _int(made.get("program_id"))
    term_id = draft.term_id
    run = await published_run(session, term_id)
    if run is not None and meets:
        placed = (
            await session.execute(
                select(func.count(Assignment.id)).where(
                    Assignment.run_id == run.id,
                    Assignment.meeting_request_id.in_(meets),
                    Assignment.archived.is_(False),
                )
            )
        ).scalar_one()
        if placed:
            out.append(
                {
                    "code": "published",
                    "run_id": run.id,
                    "count": int(placed),
                    "text": _t(
                        f"Programın {placed} dersi yayındaki planda (#{run.id}); önce onlarsız bir plan yayınlayın",
                        f"{placed} of its classes are in the published plan (#{run.id}); "
                        "publish a plan without them first",
                    ),
                }
            )
    if prog is not None:
        other = list(
            (
                await session.execute(
                    select(Section.id).where(
                        Section.program_id == prog, Section.archived.is_(False), Section.id.notin_(secs or [-1])
                    )
                )
            ).scalars()
        )
        if other:
            out.append(
                {
                    "code": "other_sections",
                    "section_ids": other,
                    "text": _t(
                        f"Programda sonradan eklenen {len(other)} şube var",
                        f"{len(other)} sections were added to the programme later",
                    ),
                }
            )
        users = (await session.execute(select(func.count(User.id)).where(User.department_id == prog))).scalar_one()
        books = (
            await session.execute(select(func.count(Booking.id)).where(Booking.department_id == prog))
        ).scalar_one() + (
            await session.execute(select(func.count(BookingSeries.id)).where(BookingSeries.department_id == prog))
        ).scalar_one()
        if users:
            out.append(
                {
                    "code": "users",
                    "count": int(users),
                    "text": _t(f"{users} kullanıcı bu programa bağlı", f"{users} users belong to the programme"),
                }
            )
        if books:
            out.append(
                {
                    "code": "bookings",
                    "count": int(books),
                    "text": _t(f"{books} rezervasyon bu programa bağlı", f"{books} bookings name the programme"),
                }
            )
        exams = (
            await session.execute(
                select(func.count(ExamRequest.id)).where(
                    (ExamRequest.program_id == prog) | ExamRequest.section_id.in_(secs or [-1])
                )
            )
        ).scalar_one()
        if exams:
            out.append(
                {
                    "code": "exams",
                    "count": int(exams),
                    "text": _t(f"{exams} sınav talebi programa bağlı", f"{exams} exam requests name the programme"),
                }
            )
    if secs:
        extra = list(
            (
                await session.execute(
                    select(MeetingRequest.id).where(
                        MeetingRequest.section_id.in_(secs),
                        MeetingRequest.archived.is_(False),
                        MeetingRequest.id.notin_(meets or [-1]),
                    )
                )
            ).scalars()
        )
        if extra:
            out.append(
                {
                    "code": "other_requests",
                    "request_ids": extra,
                    "text": _t(
                        f"Şubelere sonradan {len(extra)} talep eklendi",
                        f"{len(extra)} requests were added to its sections later",
                    ),
                }
            )
    courses = [int(x) for x in _list(made.get("courses"))]
    if courses:
        used = list(
            (
                await session.execute(
                    select(Section.course_id)
                    .where(Section.course_id.in_(courses), Section.id.notin_(secs or [-1]), Section.archived.is_(False))
                    .distinct()
                )
            ).scalars()
        )
        if used:
            out.append(
                {
                    "code": "courses_used",
                    "course_ids": used,
                    "text": _t(
                        f"Oluşturulan {len(used)} ders başka şubelerde kullanılıyor",
                        f"{len(used)} created courses are used by other sections",
                    ),
                }
            )
    people = [int(x) for x in _list(made.get("people"))]
    if people:
        used = list(
            (
                await session.execute(
                    select(SectionInstructor.instructor_id)
                    .join(Section, Section.id == SectionInstructor.section_id)
                    .where(
                        SectionInstructor.instructor_id.in_(people),
                        Section.id.notin_(secs or [-1]),
                        Section.archived.is_(False),
                    )
                    .distinct()
                )
            ).scalars()
        )
        if used:
            out.append(
                {
                    "code": "people_used",
                    "instructor_ids": used,
                    "text": _t(
                        f"Eklenen {len(used)} kişi başka şubelerde ders veriyor",
                        f"{len(used)} added people teach other sections",
                    ),
                }
            )
        linked = (
            await session.execute(
                select(func.count(Instructor.id)).where(Instructor.id.in_(people), Instructor.user_id.is_not(None))
            )
        ).scalar_one()
        if linked:
            out.append(
                {
                    "code": "people_linked",
                    "count": int(linked),
                    "text": _t(
                        f"Eklenen {linked} kişi bir kullanıcı hesabına bağlandı",
                        f"{linked} added people were linked to user accounts",
                    ),
                }
            )
    fac = _int(made.get("faculty_id"))
    if fac is not None:
        progs = (
            await session.execute(
                select(func.count(Program.id)).where(
                    Program.faculty_id == fac, Program.id != (prog or -1), Program.archived.is_(False)
                )
            )
        ).scalar_one()
        if progs:
            out.append(
                {
                    "code": "faculty_used",
                    "count": int(progs),
                    "text": _t(
                        f"Oluşturulan birimde {progs} başka program var",
                        f"The created unit has {progs} other programmes",
                    ),
                }
            )
    return out


def undo_window(draft: ProgramDraft) -> datetime | None:
    return draft.committed_at + timedelta(days=UNDO_DAYS) if draft.committed_at else None


async def undo(session: AsyncSession, draft: ProgramDraft, actor: User, *, dry: bool = False) -> dict[str, Any]:
    """Archive what the commit created (sections + their meetings, courses, people, programme, unit) and switch its
    rules off, within 30 days and when nothing outside the commit references them; else 409 with the reasons.
    ``dry`` only answers whether it can."""
    if draft.status != "committed":
        raise DraftError(
            409,
            "only a committed draft can be undone"
            if draft.status == "draft"
            else f"the commit is already {draft.status}",
        )
    until = undo_window(draft)
    blockers = await undo_blockers(session, draft)
    expired = until is not None and utcnow() > until
    if expired:
        blockers.insert(
            0, {"code": "expired", "text": _t("30 günlük geri alma süresi doldu", "The 30-day undo window has passed")}
        )
    if dry:
        return {
            "draft_id": draft.id,
            "can_undo": not blockers,
            "blockers": blockers,
            "undo_until": until.isoformat() if until else None,
        }
    if blockers:
        raise DraftError(409, {"message": "the programme cannot be undone", "blockers": blockers})
    made = _dict((draft.meta or {}).get("created"))
    archived: dict[str, list[int]] = defaultdict(list)
    try:
        for sid in _list(made.get("sections")):
            sec = await session.get(Section, int(sid))
            if sec is not None and not sec.archived:
                await ca.archive_section(session, actor, sec.id)
                archived["sections"].append(sec.id)
        archived["requests"] = [int(x) for x in _list(made.get("requests"))]
        model: Any
        for model, key in ((Course, "courses"), (Instructor, "people")):
            for oid in _list(made.get(key)):
                obj = await session.get(model, int(oid))
                if obj is not None and not obj.archived:
                    obj.archived = True
                    archived[key].append(obj.id)
        for rid in _list(made.get("rules")):
            row = await session.get(ConstraintRow, int(rid))
            if row is not None and row.enabled:
                row.enabled = False
                archived["rules"].append(row.id)
        for model, key in ((Program, "program_id"), (Faculty, "faculty_id")):
            oid = _int(made.get(key))
            if oid is not None:
                obj = await session.get(model, oid)
                if obj is not None and not obj.archived:
                    obj.archived = True
                    archived[key.removesuffix("_id")].append(obj.id)
        await session.flush()
        ev = await publish_event(
            session,
            "program.undo",
            "program",
            _int(made.get("program_id")),
            before={"draft_id": draft.id},
            after={"archived": dict(archived)},
            actor=actor,
            term_id=draft.term_id,
            undo_of=draft.commit_audit_id,
        )
        draft.status = "undone"
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return {
        "draft_id": draft.id,
        "program_id": _int(made.get("program_id")),
        "archived": dict(archived),
        "audit_id": ev.id if ev else None,
    }


# --------------------------------------------------------------------------- undo from the audit log (follow-up 4)

#: the audit actions of a wizard commit's programme (``drafts.commit_audit_id``): created, or an archived programme
#: of the same name reopened (backend follow-ups 2026-10-16 item 2)
AUDIT_UNDO_ACTIONS = ("program.create", "program.restore")


async def drafts_by_audit(session: AsyncSession, audit_ids: Iterable[int]) -> dict[int, ProgramDraft]:
    """audit event id -> the committed (or undone) draft whose programme it records."""
    ids = sorted({int(i) for i in audit_ids})
    if not ids:
        return {}
    rows = (await session.execute(select(ProgramDraft).where(ProgramDraft.commit_audit_id.in_(ids)))).scalars()
    return {int(d.commit_audit_id): d for d in rows if d.commit_audit_id is not None}


def _audit_err(status: int, code: str, en: str, tr: str, **data: Any) -> DraftError:
    return DraftError(status, {"code": code, "message": en, "message_tr": tr, **data})


async def undo_from_audit(session: AsyncSession, access: Any, ev: AuditEvent) -> dict[str, Any]:
    """``POST /audit/{id}/undo`` on a ``program.create`` / ``program.restore`` row: the drafts undo of the wizard
    commit that wrote it (:func:`undo`: the same blockers, the 30-day window, and the drafts' permission - the
    coordinator who created it or a planning administrator, with ``planning.edit``). A programme typed in the
    catalogue (no wizard commit) is not reversible here. Errors carry ``code``, ``message`` and ``message_tr``."""
    draft = (await drafts_by_audit(session, [ev.id])).get(ev.id)
    if draft is None:
        raise _audit_err(
            409,
            "not_reversible",
            "this programme was not created by the programme wizard; archive it in the catalogue instead",
            "Bu program, program sihirbazıyla oluşturulmadı; geri almak yerine katalogdan arşivleyin",
        )
    if not access.can("planning.edit"):
        raise _audit_err(403, "forbidden", "requires permission planning.edit", "planning.edit yetkisi gerekiyor")
    if draft.owner_id != access.user.id and not access.can("planning.admin"):
        raise _audit_err(
            403,
            "forbidden",
            "only the coordinator who created the programme or a planning administrator undoes it",
            "Programı yalnızca oluşturan koordinatör ya da bir planlama yöneticisi geri alabilir",
        )
    if draft.status == "undone":
        raise _audit_err(409, "already_undone", "this change was already undone", "bu değişiklik zaten geri alındı")
    try:
        out = await undo(session, draft, access.user)
    except DraftError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        blockers = list(detail.get("blockers") or [])
        if blockers:
            raise _audit_err(
                exc.status,
                "blocked",
                "the programme cannot be undone: "
                + "; ".join(str(_dict(b.get("text")).get("en", "")) for b in blockers),
                "Program geri alınamaz: " + "; ".join(str(_dict(b.get("text")).get("tr", "")) for b in blockers),
                blockers=blockers,
                draft_id=draft.id,
            ) from exc
        raise _audit_err(
            exc.status, "not_reversible", str(detail.get("message")), "bu değişiklik geri alınamaz", draft_id=draft.id
        ) from exc
    return {
        "undone": int(out["audit_id"]) if out.get("audit_id") is not None else 0,
        "action": ev.action,
        "booking_ids": [],
        "draft_id": draft.id,
        "program_id": out.get("program_id"),
        "archived": {k: [int(x) for x in v] for k, v in (out.get("archived") or {}).items()},
    }


# --------------------------------------------------------------------------- section search (P19-W-05, gap 7)


async def search_sections(
    session: AsyncSession,
    term: Term,
    *,
    q: str | None = None,
    course_code: str | None = None,
    program_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Sections of the term for joint-teaching links and cohorts: by course code (any spacing / case / Turkish
    letters, ``mbg014`` = ``MBG 014``), label, course name or programme (Turkish-aware), with the instructors, weekly
    periods, the requested meetings and the current placement in the published run."""
    from app.services.calendar_views import tr_fold

    stmt = (
        select(Section)
        .where(Section.term_id == term.id, Section.archived.is_(False))
        .options(
            selectinload(Section.course),
            selectinload(Section.program),
            selectinload(Section.meeting_requests),
            selectinload(Section.instructors).selectinload(SectionInstructor.instructor),
        )
        .order_by(Section.id)
    )
    if program_id is not None:
        stmt = stmt.where(Section.program_id == program_id)
    rows = list((await session.execute(stmt)).scalars())
    key = n.course_key(course_code) if n.clean_text(course_code) else None
    needle = tr_fold(q) if n.clean_text(q) else None
    qkey = n.course_key(q) if needle and n.extract_course_codes(q or "") else None
    hits = []
    for s in rows:
        code = s.course.display_code if s.course else ""
        if key and n.course_key(s.course.code if s.course else "") != key:
            continue
        if needle:
            hay = " ".join(
                [code, s.course.name or "" if s.course else "", s.label or "", s.program.name if s.program else ""]
            )
            ok = needle in tr_fold(hay) or needle.replace(" ", "") in tr_fold(code).replace(" ", "")
            if qkey and s.course is not None and n.course_key(s.course.code) == qkey:
                ok = True
            if not ok:
                continue
        hits.append(s)
    total = len(hits)
    hits = hits[:limit]
    places = await published_places(session, term.id, [s.id for s in hits])
    items = []
    for s in hits:
        live = [m for m in s.meeting_requests if not m.archived]
        items.append(
            {
                "section_id": s.id,
                "course_id": s.course_id,
                "course_code": s.course.display_code if s.course else None,
                "course_name": s.course.name if s.course else None,
                "label": s.label,
                "program_id": s.program_id,
                "program_name": s.program.name if s.program else None,
                "class_years": list(s.class_years or ([s.class_year] if s.class_year else [])),
                "enrolment": s.enrolment,
                "mode": s.mode,
                "periods_per_week": section_periods(live),
                "instructors": [
                    {"id": si.instructor_id, "full_name": si.instructor.full_name, "role": si.role}
                    for si in s.instructors
                ],
                "meetings": [
                    {
                        "id": m.id,
                        "day": m.day,
                        "days": list(m.days or []),
                        "start_period": m.start_period,
                        "end_period": m.end_period,
                        "weeks": list(m.weeks or []),
                        "definitive_room_text": m.definitive_room_text,
                        "status": m.status,
                    }
                    for m in sorted(live, key=lambda m: m.id)
                ],
                "placement": places.get(s.id),
            }
        )
    return {"term_id": term.id, "total": total, "items": items}


__all__ = [
    "DraftError",
    "commit",
    "create",
    "instructor_loads",
    "list_drafts",
    "materialise",
    "paste_preview",
    "patch",
    "program_precheck",
    "rooms_fit",
    "search_sections",
    "undo",
    "validate",
]
