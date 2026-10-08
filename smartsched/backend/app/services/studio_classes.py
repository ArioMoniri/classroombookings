"""Studio class list (step 2): filtered rows with draft state, bulk edits with an imported snapshot, revert.

Edits write through to ``meeting_requests`` / ``sections`` (so the inbox, grid and studio agree). Before
the first studio edit of a row the current (imported) values are captured in ``imported_snapshots``
(``entity`` = ``meeting`` / ``section``); ``changed_fields`` compares against it and ``revert`` restores
it. A snapshot whose ``fingerprint`` (hash of the imported source row) no longer matches - the planning
list was re-imported with different content - is stale: it is ignored and replaced on the next edit.
Edits made outside the studio before the first studio edit count as "imported" (lazy capture).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers.identity import (
    MEETING_FIELDS,
    SECTION_FIELDS,
    expand_coupled,
    meeting_snapshot_fp,
    plain,
    section_snapshot_fp,
)
from app.importers.normalize import PERIODS, tr_casefold, tr_upper
from app.models import (
    ExamRequest,
    ImportedSnapshot,
    MeetingRequest,
    Program,
    Room,
    Section,
    SectionInstructor,
    StudioDraft,
    Term,
    User,
)
from app.services import studio as st

EDITABLE = (*SECTION_FIELDS, *MEETING_FIELDS)



def _would_be(mr: MeetingRequest, w: dict[str, Any]) -> Any:
    from types import SimpleNamespace

    keys = ("start_period", "end_period", "day", "days", "status", "definitive_room_ids")
    return SimpleNamespace(**{k: w.get(k, getattr(mr, k)) for k in keys})


def coherence_errors(mr: Any) -> list[str]:
    """Invariants of a meeting request after an edit or a revert."""
    errors: list[str] = []
    s, e = mr.start_period, mr.end_period
    if (s is None) != (e is None):
        errors.append("start_period and end_period must be set together")
    elif s is not None and e is not None and not 1 <= s <= e <= len(PERIODS):
        errors.append(f"periods must satisfy 1 <= start <= end <= {len(PERIODS)} (got P{s}-P{e})")
    days = [int(d) for d in mr.days or []]
    if mr.day is not None and days and mr.day not in days:
        errors.append(f"day {mr.day} is not one of days {days}")
    if mr.status == "LOCKED" and (not mr.definitive_room_ids or not mr.day or not s):
        errors.append("a locked class needs its room, a fixed day and a time")
    return errors


ROOM_TAGS = frozenset({"TIP", "PC", "LAB", "AMPHI"})
#: modes without a physical room (``app.importers.normalize.parse_mode`` + the AI edits)
REMOTE_MODES = frozenset({"ONLINE", "UZEM", "ASYNC", "HOSPITAL"})
STATUSES = ("NEW", "PARSED", "NEEDS_REVIEW", "LOCKED")
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def fold(text: str | None) -> str:
    """Turkish-aware, diacritic-insensitive search key (``İ``/``ı``, NBSP, ``Ç`` -> ``c`` ...)."""
    s = tr_casefold(str(text or "")).translate(_FOLD)
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def time_label(start: int | None, end: int | None) -> str | None:
    if not start or not end or not 1 <= start <= end <= len(PERIODS):
        return None
    return f"{PERIODS[start - 1].start:%H:%M}-{PERIODS[end - 1].end:%H:%M}"


_plain = plain


def section_fp(sec: Section) -> str:
    return section_snapshot_fp(sec.source_row, sec.source_key)


def meeting_fp(mr: MeetingRequest) -> str:
    return meeting_snapshot_fp(mr.section.source_row, mr.source_key, mr.source_row_index)


@dataclass
class Snapshots:
    meetings: dict[int, ImportedSnapshot]
    sections: dict[int, ImportedSnapshot]


async def load_snapshots(session: AsyncSession, meetings: Iterable[MeetingRequest]) -> Snapshots:
    mrs = list(meetings)
    mids = [m.id for m in mrs]
    sids = list({m.section_id for m in mrs})
    out = Snapshots({}, {})
    if mids:
        for s in (
            await session.execute(
                select(ImportedSnapshot).where(
                    ImportedSnapshot.entity == "meeting", ImportedSnapshot.entity_id.in_(mids)
                )
            )
        ).scalars():
            out.meetings[s.entity_id] = s
    if sids:
        for s in (
            await session.execute(
                select(ImportedSnapshot).where(
                    ImportedSnapshot.entity == "section", ImportedSnapshot.entity_id.in_(sids)
                )
            )
        ).scalars():
            out.sections[s.entity_id] = s
    # stale snapshots (planning list re-imported with other content) are ignored
    by_id = {m.id: m for m in mrs}
    out.meetings = {k: v for k, v in out.meetings.items() if v.fingerprint == meeting_fp(by_id[k])}
    secs = {m.section_id: m.section for m in mrs}
    out.sections = {k: v for k, v in out.sections.items() if v.fingerprint == section_fp(secs[k])}
    return out


def changed_fields(mr: MeetingRequest, snaps: Snapshots) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ss = snaps.sections.get(mr.section_id)
    if ss is not None:
        for f in SECTION_FIELDS:
            if f in ss.values and _plain(getattr(mr.section, f)) != ss.values[f]:
                out.append({"field": f, "imported": ss.values[f], "current": _plain(getattr(mr.section, f))})
    ms = snaps.meetings.get(mr.id)
    if ms is not None:
        for f in MEETING_FIELDS:
            if f in ms.values and _plain(getattr(mr, f)) != ms.values[f]:
                out.append({"field": f, "imported": ms.values[f], "current": _plain(getattr(mr, f))})
    return out


async def ensure_snapshots(session: AsyncSession, mr: MeetingRequest, snaps: Snapshots) -> None:
    """Capture the pre-edit values of ``mr`` and its section once (lazily, before the first edit). An
    existing valid snapshot is kept; a stale one (re-imported source row) is replaced."""
    sec = mr.section
    if sec.id not in snaps.sections:
        fp = section_fp(sec)
        row = (
            await session.execute(
                select(ImportedSnapshot).where(
                    ImportedSnapshot.entity == "section", ImportedSnapshot.entity_id == sec.id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ImportedSnapshot(entity="section", entity_id=sec.id)
            session.add(row)
        if row.fingerprint != fp or not row.values:
            row.values, row.fingerprint = {f: _plain(getattr(sec, f)) for f in SECTION_FIELDS}, fp
        snaps.sections[sec.id] = row
    if mr.id not in snaps.meetings:
        fp = meeting_fp(mr)
        mrow = (
            await session.execute(
                select(ImportedSnapshot).where(
                    ImportedSnapshot.entity == "meeting", ImportedSnapshot.entity_id == mr.id
                )
            )
        ).scalar_one_or_none()
        if mrow is None:
            mrow = ImportedSnapshot(entity="meeting", entity_id=mr.id)
            session.add(mrow)
        if mrow.fingerprint != fp or not mrow.values:
            values = {f: _plain(getattr(mr, f)) for f in MEETING_FIELDS}
            values["_start_time"] = _plain(mr.start_time)
            values["_end_time"] = _plain(mr.end_time)
            mrow.values, mrow.fingerprint = values, fp
        snaps.meetings[mr.id] = mrow


# --------------------------------------------------------------------------- rows


@dataclass
class ClassFilters:
    faculty_id: int | None = None
    program_id: int | None = None
    class_year: int | None = None
    day: int | None = None
    building: str | None = None
    mode: str | None = None
    status: str | None = None
    changed: bool | None = None
    included: bool | None = None
    needs_room: bool | None = None
    pinned: bool | None = None
    rule_id: int | None = None
    ids: list[int] | None = None
    q: str | None = None


async def _room_codes(session: AsyncSession) -> dict[int, str]:
    return {r.id: r.display_name for r in (await session.execute(select(Room))).scalars()}


async def rule_matches(session: AsyncSession, draft: StudioDraft) -> dict[int, set[int]]:
    """Targeted rules in play -> request ids they select (draft pins / overrides applied, no exclusions so
    left-out rows still show their rules)."""
    from app.solver.constraints._common import is_targeted, select_events

    in_play = await st.rules_in_play(session, draft)
    if not in_play:
        return {}
    snap = st.draft_snapshot(draft, await st.disabled_builtins(session, draft))
    snap["excluded_event_ids"] = []
    din = await st.build_draft_input(session, draft, snapshot=snap)
    out: dict[int, set[int]] = {}
    for c in din.inp.constraints:
        if c.id is None or not is_targeted(c):
            continue
        out[c.id] = {rid for e in select_events(din.inp, c.params) for rid in din.members.get(e.id, [e.id])}
    return out


def _meeting_row(
    mr: MeetingRequest,
    rooms: dict[int, str],
    excluded: set[int],
    pinned: set[int],
    snaps: Snapshots,
    rules: dict[int, set[int]],
) -> dict[str, Any]:
    sec = mr.section
    prog = sec.program
    req_rooms = [int(r) for r in mr.requested_room_ids or []]
    def_rooms = [int(r) for r in mr.definitive_room_ids or []]
    schedulable = bool(mr.needs_room and mr.start_period and mr.end_period)
    return {
        "id": mr.id,
        "kind": "COURSE",
        "section_id": sec.id,
        "course_code": sec.course.display_code,
        "course_name": sec.course.name,
        "section_label": sec.label,
        "program_id": sec.program_id,
        "program_name": prog.name if prog else None,
        "faculty_id": prog.faculty_id if prog else None,
        "faculty_name": prog.faculty.name if prog and prog.faculty else None,
        "is_evening": bool(prog.is_evening) if prog else False,
        "class_year": sec.class_year,
        "class_years": [int(y) for y in sec.class_years or [] if y is not None],
        "day": mr.day,
        "days": [int(d) for d in mr.days or []],
        "start_period": mr.start_period,
        "end_period": mr.end_period,
        "time_label": time_label(mr.start_period, mr.end_period),
        "weeks": [int(w) for w in mr.weeks or []],
        "enrolment": sec.enrolment,
        "mode": sec.mode,
        "needs_room": bool(mr.needs_room),
        "flexible_day": bool(mr.flexible_day),
        "requested_room_ids": req_rooms,
        "requested_room_codes": [rooms.get(r, f"#{r}") for r in req_rooms],
        "requested_building": mr.requested_building,
        "requested_tags": [str(t) for t in mr.requested_tags or []],
        "definitive_room_ids": def_rooms,
        "definitive_room_codes": [rooms.get(r, f"#{r}") for r in def_rooms],
        "status": mr.status,
        "locked": mr.status == "LOCKED",
        "instructors": [si.instructor.full_name for si in sec.instructors if si.instructor is not None],
        "included": mr.id not in excluded,
        "schedulable": schedulable,
        "pinned": mr.id in pinned,
        "changed_fields": changed_fields(mr, snaps),
        "rule_ids": sorted(cid for cid, ids in rules.items() if mr.id in ids),
    }


def _match(row: dict[str, Any], f: ClassFilters, rules: dict[int, set[int]], hay: str) -> bool:
    if f.ids is not None and row["id"] not in f.ids:
        return False
    if f.faculty_id is not None and row["faculty_id"] != f.faculty_id:
        return False
    if f.program_id is not None and row["program_id"] != f.program_id:
        return False
    if f.class_year is not None and f.class_year not in (row["class_years"] or [row["class_year"]]):
        return False
    if f.day is not None and row["day"] != f.day and f.day not in row["days"]:
        return False
    if f.building:
        b = tr_upper(f.building.strip())[:1]
        codes = row["requested_room_codes"] + row["definitive_room_codes"]
        if row.get("requested_building") != b and not any(str(c).upper().startswith(b) for c in codes):
            return False
    if f.mode and str(row.get("mode") or "").upper() != f.mode.upper():
        return False
    if f.status and row["status"] != f.status.upper():
        return False
    if f.changed is not None and bool(row["changed_fields"]) != f.changed:
        return False
    if f.included is not None and row["included"] != f.included:
        return False
    if f.needs_room is not None and row["needs_room"] != f.needs_room:
        return False
    if f.pinned is not None and row["pinned"] != f.pinned:
        return False
    if f.rule_id is not None and row["id"] not in rules.get(f.rule_id, set()):
        return False
    if f.q:
        q = fold(f.q)
        if q not in hay and q.replace(" ", "") not in hay.replace(" ", ""):
            return False
    return True


def _hay(row: dict[str, Any]) -> str:
    parts = [
        row.get("course_code"),
        row.get("course_name"),
        row.get("program_name"),
        row.get("faculty_name"),
        row.get("section_label"),
        *row.get("instructors", []),
        *row.get("requested_room_codes", []),
        *row.get("definitive_room_codes", []),
    ]
    return " | ".join(fold(p) for p in parts if p)


async def class_page(
    session: AsyncSession, draft: StudioDraft, f: ClassFilters, *, limit: int = 200, offset: int = 0
) -> dict[str, Any]:
    if draft.kind == "EXAM":
        return await _exam_page(session, draft, f, limit=limit, offset=offset)
    meetings = await st.load_meetings(session, draft.term_id)
    rooms = await _room_codes(session)
    snaps = await load_snapshots(session, meetings)
    rules = await rule_matches(session, draft)
    if f.rule_id is not None and f.rule_id not in rules:
        if f.rule_id not in await st.rules_in_play(session, draft):
            raise st.StudioError(404, f"rule {f.rule_id} is not in play for this draft")
    excluded = {int(i) for i in draft.excluded_event_ids or []}
    pinned = {int(p["event_id"]) for p in draft.pins or []}
    rows = [_meeting_row(m, rooms, excluded, pinned, snaps, rules) for m in meetings]
    counts = {
        "total": len(rows),
        "in_plan": sum(1 for r in rows if r["included"] and r["schedulable"]),
        "left_out": sum(1 for r in rows if not r["included"]),
        "changed": sum(1 for r in rows if r["changed_fields"]),
        "pinned": sum(1 for r in rows if r["pinned"]),
        "locked": sum(1 for r in rows if r["locked"]),
        "needs_review": sum(1 for r in rows if r["status"] == "NEEDS_REVIEW"),
        "needs_room": sum(1 for r in rows if r["needs_room"]),
        "no_day_time": sum(1 for r in rows if r["needs_room"] and not r["schedulable"]),
        "evening": sum(1 for r in rows if r["is_evening"]),
    }
    hits = [r for r in rows if _match(r, f, rules, _hay(r) if f.q else "")]
    return {
        "items": hits[offset : offset + limit],
        "total": len(hits),
        "limit": limit,
        "offset": offset,
        "counts": counts,
    }


async def _exam_page(
    session: AsyncSession, draft: StudioDraft, f: ClassFilters, *, limit: int, offset: int
) -> dict[str, Any]:
    exams = list(
        (
            await session.execute(
                select(ExamRequest)
                .where(ExamRequest.term_id == draft.term_id, ExamRequest.archived.is_(False))
                .options(selectinload(ExamRequest.program).selectinload(Program.faculty))
                .order_by(ExamRequest.date, ExamRequest.start_period, ExamRequest.id)
            )
        ).scalars()
    )
    rooms = await _room_codes(session)
    excluded = {int(i) for i in draft.excluded_event_ids or []}
    pinned = {int(p["event_id"]) for p in draft.pins or []}
    rules = await rule_matches(session, draft)
    rows: list[dict[str, Any]] = []
    for ex in exams:
        prog = ex.program
        req_rooms = [int(r) for r in ex.requested_room_ids or []]
        def_rooms = [int(r) for r in ex.definitive_room_ids or []]
        rows.append(
            {
                "id": ex.id,
                "kind": "EXAM",
                "course_code": ex.course_code,
                "course_name": ex.course_name,
                "program_id": ex.program_id,
                "program_name": prog.name if prog else None,
                "faculty_id": prog.faculty_id if prog else None,
                "faculty_name": prog.faculty.name if prog and prog.faculty else ex.faculty_text,
                "is_evening": bool(prog.is_evening) if prog else False,
                "class_year": ex.class_year,
                "class_years": [int(y) for y in ex.class_years or [] if y is not None],
                "day": ex.date.isoweekday() if ex.date else None,
                "days": [ex.date.isoweekday()] if ex.date else [],
                "date": ex.date,
                "start_period": ex.start_period,
                "end_period": ex.end_period,
                "time_label": time_label(ex.start_period, ex.end_period),
                "enrolment": ex.enrolment,
                "needs_room": bool(ex.needs_room),
                "requested_room_ids": req_rooms,
                "requested_room_codes": [rooms.get(r, f"#{r}") for r in req_rooms],
                "requested_building": ex.requested_building,
                "requested_tags": [str(t) for t in ex.requested_tags or []],
                "definitive_room_ids": def_rooms,
                "definitive_room_codes": [rooms.get(r, f"#{r}") for r in def_rooms],
                "requested_room_count": ex.requested_room_count,
                "status": ex.status,
                "locked": ex.status == "LOCKED",
                "instructors": [ex.instructor_text] if ex.instructor_text else [],
                "included": ex.id not in excluded,
                "schedulable": bool(ex.needs_room and ex.date and ex.start_period and ex.end_period),
                "pinned": ex.id in pinned,
                "changed_fields": [],
                "rule_ids": sorted(cid for cid, ids in rules.items() if ex.id in ids),
            }
        )
    counts = {
        "total": len(rows),
        "in_plan": sum(1 for r in rows if r["included"] and r["schedulable"]),
        "left_out": sum(1 for r in rows if not r["included"]),
        "changed": 0,
        "pinned": sum(1 for r in rows if r["pinned"]),
        "locked": sum(1 for r in rows if r["locked"]),
        "needs_review": sum(1 for r in rows if r["status"] == "NEEDS_REVIEW"),
        "needs_room": sum(1 for r in rows if r["needs_room"]),
        "no_day_time": sum(1 for r in rows if r["needs_room"] and not r["schedulable"]),
        "evening": sum(1 for r in rows if r["is_evening"]),
    }
    hits = [r for r in rows if _match(r, f, rules, _hay(r) if f.q else "")]
    return {
        "items": hits[offset : offset + limit],
        "total": len(hits),
        "limit": limit,
        "offset": offset,
        "counts": counts,
    }


# --------------------------------------------------------------------------- edits


async def _load(session: AsyncSession, ids: Iterable[int]) -> dict[int, MeetingRequest]:
    wanted = list({int(i) for i in ids})
    if not wanted:
        return {}
    q = (
        select(MeetingRequest)
        .where(MeetingRequest.id.in_(wanted))
        .options(
            selectinload(MeetingRequest.section).selectinload(Section.course),
            selectinload(MeetingRequest.section).selectinload(Section.program).selectinload(Program.faculty),
            selectinload(MeetingRequest.section)
            .selectinload(Section.instructors)
            .selectinload(SectionInstructor.instructor),
        )
    )
    return {m.id: m for m in (await session.execute(q)).scalars()}


async def _section_meeting_ids(session: AsyncSession, section_id: int) -> list[int]:
    q = select(MeetingRequest.id).where(MeetingRequest.section_id == section_id, MeetingRequest.archived.is_(False))
    return list((await session.execute(q.order_by(MeetingRequest.id))).scalars())


def _validate(
    mr: MeetingRequest, p: dict[str, Any], term: Term, room_ids: set[int], buildings: set[str]
) -> tuple[list[str], dict[str, Any]]:
    """Per-row validation -> (errors, normalised field values to write)."""
    errors: list[str] = []
    w: dict[str, Any] = {}
    if "enrolment" in p:
        w["enrolment"] = p["enrolment"]
    if "mode" in p and p["mode"] is not None:
        w["mode"] = p["mode"]
        if "needs_room" not in p:
            w["needs_room"] = p["mode"] not in REMOTE_MODES
    if "needs_room" in p and p["needs_room"] is not None:
        w["needs_room"] = bool(p["needs_room"])
    if "days" in p and p["days"] is not None:
        days = sorted({int(d) for d in p["days"]})
        if any(not 1 <= d <= 7 for d in days):
            errors.append("days must be 1..7")
        w["days"] = days
        w["day"] = days[0] if len(days) == 1 else None
        w["flexible_day"] = len(days) != 1
    if "day" in p:
        if p["day"] is None:
            w["day"] = None
            w["flexible_day"] = True
        else:
            w["day"], w["days"], w["flexible_day"] = int(p["day"]), [int(p["day"])], False
    if "flexible_day" in p and p["flexible_day"] is not None:
        w["flexible_day"] = bool(p["flexible_day"])
        if p["flexible_day"] and "day" not in p:
            w["day"] = None
            w.setdefault("days", [int(d) for d in mr.days or []] or ([mr.day] if mr.day else []))
    if "start_period" in p or "end_period" in p:
        old_s, old_e = mr.start_period, mr.end_period
        dur = (old_e - old_s) if old_s and old_e else 0
        s = p.get("start_period") or old_s
        e = p.get("end_period") or ((s + dur) if s and "start_period" in p else old_e)
        if s is None or e is None:
            errors.append("give both start_period and end_period")
        elif not 1 <= s <= e <= len(PERIODS):
            errors.append(f"periods must satisfy 1 <= start <= end <= {len(PERIODS)} (got P{s}-P{e})")
        else:
            w["start_period"], w["end_period"] = s, e
            w["start_time"], w["end_time"] = PERIODS[s - 1].start, PERIODS[e - 1].end
    if "weeks" in p and p["weeks"] is not None:
        weeks = sorted({int(x) for x in p["weeks"]})
        max_w = int(term.week_count or 14) + 4
        if any(not 1 <= x <= max_w for x in weeks):
            errors.append(f"weeks must be within 1..{max_w}")
        w["weeks"] = weeks
    for key in ("requested_room_ids", "definitive_room_ids"):
        if key in p and p[key] is not None:
            ids = list(dict.fromkeys(int(r) for r in p[key]))
            bad = [r for r in ids if r not in room_ids]
            if bad:
                errors.append(f"unknown room id(s) {bad}")
            w[key] = ids
    if "requested_building" in p:
        b = tr_upper(str(p["requested_building"] or "").strip())[:1] or None
        if b is not None and b not in buildings:
            errors.append(f"unknown building {p['requested_building']!r} (known: {sorted(buildings)})")
        w["requested_building"] = b
    if "requested_tags" in p and p["requested_tags"] is not None:
        tags = sorted({tr_upper(str(t)).strip() for t in p["requested_tags"] if str(t).strip()})
        tags = ["AMPHI" if t == "AMFI" else t for t in tags]
        bad_tags = [t for t in tags if t not in ROOM_TAGS]
        if bad_tags:
            errors.append(f"unknown tag(s) {bad_tags} (known: {sorted(ROOM_TAGS)})")
        w["requested_tags"] = tags
    if "locked" in p and p["locked"] is not None:
        if p["locked"]:
            rooms = w.get("definitive_room_ids", mr.definitive_room_ids or [])
            day = w.get("day", mr.day)
            start = w.get("start_period", mr.start_period)
            if not rooms:
                errors.append("pick the class's room (definitive_room_ids) before locking it")
            if not day or not start:
                errors.append("a locked class needs a fixed day and time")
            w["status"] = "LOCKED"
        elif mr.status == "LOCKED":
            w["status"] = "PARSED"
    return errors, w


def _warnings(mr: MeetingRequest, w: dict[str, Any], caps: dict[int, tuple[str, int]]) -> list[str]:
    size = w.get("enrolment", mr.section.enrolment) or 0
    out: list[str] = []
    for key in ("requested_room_ids", "definitive_room_ids"):
        for r in w.get(key, getattr(mr, key) or []):
            code, cap = caps.get(int(r), (f"#{r}", 0))
            if size and cap and cap < size:
                out.append(f"{code} has {cap} seats, this class has {size}")
    return list(dict.fromkeys(out))


async def bulk_edit(session: AsyncSession, body: Any, user: User) -> dict[str, Any]:
    items: list[tuple[int, dict[str, Any]]] = []
    if body.patch is not None:
        patch = body.patch.model_dump(exclude_unset=True)
        items += [(int(i), patch) for i in body.ids]
    elif body.ids:
        raise st.StudioError(422, "ids given without a patch")
    items += [(it.id, it.patch.model_dump(exclude_unset=True)) for it in body.items]
    if not items:
        raise st.StudioError(422, "nothing to edit: send ids + patch or items")
    if len(items) > 2000:
        raise st.StudioError(413, "at most 2000 rows per call")
    meetings = await _load(session, [i for i, _ in items])
    rooms = list((await session.execute(select(Room))).scalars())
    room_ids = {r.id for r in rooms}
    caps = {r.id: (r.display_name, int(r.capacity or 0)) for r in rooms}
    buildings = {r.code[:1] for r in rooms if r.code}
    terms: dict[int, Term] = {}
    snaps = await load_snapshots(session, meetings.values())
    results: list[dict[str, Any]] = []
    touched: list[int] = []
    for mid, patch in items:
        mr = meetings.get(mid)
        if mr is None or mr.archived:
            results.append({"id": mid, "ok": False, "errors": ["meeting request not found"], "changed": []})
            continue
        if not patch:
            results.append({"id": mid, "ok": False, "errors": ["empty patch"], "changed": []})
            continue
        term = terms.get(mr.section.term_id) or await session.get(Term, mr.section.term_id)
        assert term is not None
        terms[term.id] = term
        errors, w = _validate(mr, patch, term, room_ids, buildings)
        if not errors:  # the row as it would be after the patch (e.g. a LOCKED class losing its room)
            now = set(coherence_errors(mr))
            errors = [e for e in coherence_errors(_would_be(mr, w)) if e not in now]
        if errors:
            results.append({"id": mid, "ok": False, "errors": errors, "changed": []})
            continue
        warnings = _warnings(mr, w, caps)
        changed = [
            k
            for k, v in w.items()
            if k not in ("start_time", "end_time")
            and _plain(getattr(mr.section if k in SECTION_FIELDS else mr, k)) != _plain(v)
        ]
        if not body.dry_run and changed:
            sec = mr.section
            siblings = [mr]
            if "mode" in w:  # a mode change switches needs_room on every meeting of the section
                sib_ids = await _section_meeting_ids(session, sec.id)
                meetings.update(await _load(session, [i for i in sib_ids if i not in meetings]))
                siblings = [meetings[i] for i in sib_ids]
            for m in {mr.id: mr, **{x.id: x for x in siblings}}.values():
                await ensure_snapshots(session, m, snaps)
            for k, v in w.items():
                if k in SECTION_FIELDS:
                    setattr(sec, k, v)
                elif k == "needs_room" and "mode" in w and "needs_room" not in patch:
                    for m in siblings:
                        m.needs_room = bool(v)
                else:
                    setattr(mr, k, v)
            touched.append(mid)
        results.append({"id": mid, "ok": True, "errors": [], "changed": changed, "warnings": warnings})
    if not body.dry_run:
        await session.commit()
    rows: list[dict[str, Any]] = []
    if touched:
        rows = await rows_for(session, touched, user)
    return {
        "results": results,
        "updated": len(touched),
        "failed": sum(1 for r in results if not r["ok"]),
        "rows": rows,
    }


async def rows_for(session: AsyncSession, ids: list[int], user: User) -> list[dict[str, Any]]:
    """Fresh class rows (draft state of ``user``'s COURSE draft of the rows' term)."""
    meetings = await _load(session, ids)
    if not meetings:
        return []
    term_id = next(iter(meetings.values())).section.term_id
    draft = await st.get_draft(session, term_id, user.id, "COURSE")
    rooms = await _room_codes(session)
    snaps = await load_snapshots(session, meetings.values())
    excluded = {int(i) for i in draft.excluded_event_ids or []}
    pinned = {int(p["event_id"]) for p in draft.pins or []}
    return [_meeting_row(meetings[i], rooms, excluded, pinned, snaps, {}) for i in ids if i in meetings]


async def revert(session: AsyncSession, ids: list[int], fields: list[str] | None, user: User) -> list[dict[str, Any]]:
    if fields is not None:
        bad = [f for f in fields if f not in EDITABLE]
        if bad:
            raise st.StudioError(422, f"unknown field(s) {bad}; revertable: {list(EDITABLE)}")
    meetings = await _load(session, ids)
    missing = [i for i in ids if i not in meetings]
    if missing:
        raise st.StudioError(404, f"meeting request(s) not found: {missing}")
    snaps = await load_snapshots(session, meetings.values())
    before = {mr.id: set(coherence_errors(mr)) for mr in meetings.values()}
    for mr in meetings.values():
        want = expand_coupled(fields or EDITABLE)  # never half a group (start without end, day vs days)
        ss = snaps.sections.get(mr.section_id)
        if ss is not None:
            for f in SECTION_FIELDS:
                if f in want and f in ss.values:
                    setattr(mr.section, f, ss.values[f])
            if "mode" in want:  # the mode edit also switched needs_room on the section's meetings
                sibs = await _load(session, await _section_meeting_ids(session, mr.section_id))
                sib_snaps = await load_snapshots(session, sibs.values())
                for m in sibs.values():
                    ms_sib = sib_snaps.meetings.get(m.id)
                    if ms_sib is not None and "needs_room" in ms_sib.values:
                        m.needs_room = ms_sib.values["needs_room"]
        ms = snaps.meetings.get(mr.id)
        if ms is None:
            continue
        for f in MEETING_FIELDS:
            if f in want and f in ms.values:
                setattr(mr, f, ms.values[f])
        if want & {"start_period", "end_period"}:
            for f, key in (("start_time", "_start_time"), ("end_time", "_end_time")):
                raw = ms.values.get(key)
                setattr(mr, f, time.fromisoformat(raw) if raw else None)
    bad = {
        mr.id: errs for mr in meetings.values() if (errs := [e for e in coherence_errors(mr) if e not in before[mr.id]])
    }
    if bad:
        await session.rollback()
        raise st.StudioError(422, {"message": "the revert would leave inconsistent classes", "errors": bad})
    await session.commit()
    return await rows_for(session, ids, user)


__all__ = [
    "EDITABLE",
    "ClassFilters",
    "bulk_edit",
    "changed_fields",
    "class_page",
    "fold",
    "revert",
    "rule_matches",
]
