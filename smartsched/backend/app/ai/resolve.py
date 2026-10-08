"""Term context + resolution of the names the model uses into database ids.

The model only ever names things ("A 206", "Psikoloji 1. sınıf", "PHAR 240"); this module maps them to
ids with the normalisers of :mod:`app.importers.normalize` and a conservative fuzzy match. Anything
that does not resolve confidently becomes ``needs_review`` with candidates - ids are never invented.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.catalog import KINDS, validate_params
from app.importers.normalize import (
    PERIODS,
    canon_course_code,
    canon_program,
    parse_room_codes,
    tr_casefold,
)
from app.models import Course, Instructor, MeetingRequest, Program, Room, Section, Term, Week
from app.schemas.ai import ProposedConstraint, ResolvedEntity
from app.services.calendar import week_index_for_date

FUZZY_ACCEPT = 0.86
FUZZY_SUGGEST = 0.55


@dataclass
class TermContext:
    term: Term
    weeks: list[Week]
    rooms: list[Room]
    programs: list[Program]
    courses: list[Course]
    instructors: list[Instructor]
    #: course id -> [(section id, program canonical, [meeting request ids])]
    sections_by_course: dict[int, list[tuple[int, str | None, list[int]]]] = field(default_factory=dict)

    @property
    def week_count(self) -> int:
        return int(self.term.week_count or (max((w.index for w in self.weeks), default=14)))

    @property
    def rooms_by_code(self) -> dict[str, Room]:
        return {r.code: r for r in self.rooms}

    def prompt_block(self) -> str:
        """Compact, deterministic description for the system prompt (cache friendly)."""
        rooms = ", ".join(
            f"{r.display_name}({r.capacity}{'/' + str(r.exam_capacity) if r.exam_capacity else ''}{',' + '+'.join(str(t) for t in r.tags) if r.tags else ''})"
            for r in sorted(self.rooms, key=lambda r: r.code)
        )
        programs = "; ".join(p.name for p in sorted(self.programs, key=lambda p: p.canonical_name))
        courses = " ".join(c.display_code for c in sorted(self.courses, key=lambda c: c.code))
        wk = []
        for w in sorted(self.weeks, key=lambda w: w.index):
            wk.append(f"W{w.index}={w.start_date.isoformat() if w.start_date else '?'}{'(' + w.kind + ')' if w.kind != 'LECTURE' else ''}")
        periods = " ".join(f"P{p.index}={p.label}" for p in PERIODS)
        buildings = sorted({r.code[:1] for r in self.rooms})
        return (
            f"Term {self.term.code} ({self.term.name}), {self.week_count} weeks"
            + (f", starts {self.term.start_date.isoformat()}" if self.term.start_date else "")
            + ".\n"
            f"Weeks: {' '.join(wk) if wk else 'W1..W' + str(self.week_count)}\n"
            f"Days: 1=Pazartesi 2=Salı 3=Çarşamba 4=Perşembe 5=Cuma 6=Cumartesi 7=Pazar\n"
            f"Periods (18/day): {periods}\n"
            f"Buildings: {', '.join(buildings)}. Rooms (code(capacity[/exam capacity][,tags])): {rooms}\n"
            f"Programmes: {programs}\n"
            f"Course codes in this term: {courses}\n"
        )


async def load_term_context(session: AsyncSession, term_id: int) -> TermContext:
    term = await session.get(Term, term_id)
    if term is None:
        raise ValueError(f"term {term_id} not found")
    weeks = list((await session.execute(select(Week).where(Week.term_id == term_id).order_by(Week.index))).scalars())
    rooms = list((await session.execute(select(Room).where(Room.is_bookable.is_(True)).order_by(Room.code))).scalars())
    sections = list(
        (
            await session.execute(
                select(Section)
                .where(Section.term_id == term_id, Section.archived.is_(False))
                .options(
                    selectinload(Section.course),
                    selectinload(Section.program),
                    selectinload(Section.meeting_requests),
                    selectinload(Section.instructors),
                )
            )
        ).scalars()
    )
    courses: dict[int, Course] = {}
    programs: dict[int, Program] = {}
    by_course: dict[int, list[tuple[int, str | None, list[int]]]] = {}
    for s in sections:
        courses[s.course_id] = s.course
        if s.program is not None:
            programs[s.program.id] = s.program
        mr_ids = [m.id for m in s.meeting_requests if not m.archived]
        by_course.setdefault(s.course_id, []).append((s.id, s.program.canonical_name if s.program else None, mr_ids))
    for p in (await session.execute(select(Program))).scalars():
        programs.setdefault(p.id, p)
    instructors = list((await session.execute(select(Instructor))).scalars())
    return TermContext(term, weeks, rooms, list(programs.values()), list(courses.values()), instructors, by_course)


# ---------------------------------------------------------------------------
# Individual resolvers
# ---------------------------------------------------------------------------


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def resolve_room(ctx: TermContext, text: str) -> ResolvedEntity:
    codes = parse_room_codes(text)
    by_code = ctx.rooms_by_code
    if codes and codes[0] in by_code:
        r = by_code[codes[0]]
        return ResolvedEntity(type="room", text=text, resolved_id=r.id, resolved_label=r.display_name, confidence=1.0)
    key = tr_casefold(text).replace(" ", "")
    scored = sorted(
        ((max(_ratio(key, r.code.casefold()), _ratio(key, r.display_name.casefold().replace(" ", ""))), r) for r in ctx.rooms),
        key=lambda t: -t[0],
    )
    cands = [{"id": r.id, "label": r.display_name, "score": round(s, 2)} for s, r in scored[:3] if s >= FUZZY_SUGGEST]
    if scored and scored[0][0] >= FUZZY_ACCEPT:
        s, r = scored[0]
        return ResolvedEntity(type="room", text=text, resolved_id=r.id, resolved_label=r.display_name, confidence=round(s, 2), candidates=cands)
    return ResolvedEntity(type="room", text=text, candidates=cands)


def resolve_rooms(ctx: TermContext, texts: list[str]) -> list[ResolvedEntity]:
    out: list[ResolvedEntity] = []
    for t in texts:
        parts = parse_room_codes(t)
        if len(parts) > 1:  # "A 301-A 302-A 303" in one string
            out.extend(resolve_room(ctx, p) for p in parts)
        else:
            out.append(resolve_room(ctx, t))
    return out


def resolve_program(ctx: TermContext, text: str) -> ResolvedEntity:
    parsed = canon_program(text)
    if parsed is None:
        return ResolvedEntity(type="program", text=text)
    key = parsed.canonical
    exact = [p for p in ctx.programs if p.canonical_name == key]
    if exact:
        p = exact[0]
        return ResolvedEntity(type="program", text=text, resolved_id=p.id, resolved_label=p.canonical_name, confidence=1.0)
    scored = []
    for p in ctx.programs:
        pk = p.canonical_name
        s = _ratio(key, pk)
        if pk.startswith(key) or key.startswith(pk):
            s = max(s, 0.9 if abs(len(pk) - len(key)) <= 8 else 0.8)
        scored.append((s, p))
    scored.sort(key=lambda t: -t[0])
    cands = [{"id": p.id, "label": p.canonical_name, "score": round(s, 2)} for s, p in scored[:3] if s >= FUZZY_SUGGEST]
    if scored and scored[0][0] >= FUZZY_ACCEPT and (len(scored) < 2 or scored[1][0] < scored[0][0] - 0.05):
        s, p = scored[0]
        return ResolvedEntity(type="program", text=text, resolved_id=p.id, resolved_label=p.canonical_name, confidence=round(s, 2), candidates=cands)
    return ResolvedEntity(type="program", text=text, candidates=cands)


def resolve_course(ctx: TermContext, text: str, program_canonical: str | None = None) -> tuple[ResolvedEntity, list[int]]:
    """Course text -> entity (course id) + meeting request ids in the term (optionally one programme)."""
    code = canon_course_code(text)
    by_code = {c.code: c for c in ctx.courses}
    course = by_code.get(code or "")
    if course is None:
        cands = []
        if code:
            for c in ctx.courses:
                s = _ratio(code, c.code)
                if s >= 0.8:
                    cands.append({"id": c.id, "label": c.display_code, "score": round(s, 2)})
            cands.sort(key=lambda d: -d["score"])
        return ResolvedEntity(type="course", text=text, candidates=cands[:3]), []
    ids: list[int] = []
    for _sid, prog, mr_ids in ctx.sections_by_course.get(course.id, []):
        if program_canonical and prog != program_canonical:
            continue
        ids.extend(mr_ids)
    ent = ResolvedEntity(type="course", text=text, resolved_id=course.id, resolved_label=course.display_code, confidence=1.0)
    return ent, sorted(set(ids))


def resolve_instructor(ctx: TermContext, text: str) -> ResolvedEntity:
    key = tr_casefold(text)
    scored = sorted(((_ratio(key, i.canonical_name), i) for i in ctx.instructors), key=lambda t: -t[0])
    cands = [{"id": i.id, "label": i.full_name, "score": round(s, 2)} for s, i in scored[:3] if s >= FUZZY_SUGGEST]
    if scored and scored[0][0] >= FUZZY_ACCEPT:
        s, i = scored[0]
        return ResolvedEntity(type="instructor", text=text, resolved_id=i.id, resolved_label=i.full_name, confidence=round(s, 2), candidates=cands)
    return ResolvedEntity(type="instructor", text=text, candidates=cands)


def week_for_date(ctx: TermContext, text: str) -> ResolvedEntity:
    try:
        d = date.fromisoformat(text[:10])
    except ValueError:
        return ResolvedEntity(type="date", text=text)
    w = week_index_for_date(ctx.term, d, ctx.weeks)
    if w is None or w < 1 or w > ctx.week_count + 4:
        return ResolvedEntity(type="date", text=text, candidates=[{"week": w}] if w else [])
    return ResolvedEntity(type="date", text=text, resolved_id=w, resolved_label=f"W{w}", confidence=1.0)


# ---------------------------------------------------------------------------
# Proposal resolution (model output -> ProposedConstraint with resolved params)
# ---------------------------------------------------------------------------

_SELECTOR_KEYS = ("course_codes", "program_name", "class_years", "instructor_name", "match", "kinds")


def _clean(d: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (d or {}).items() if v is not None and v != [] and v != ""}


def resolve_proposal(ctx: TermContext, raw: dict[str, Any]) -> ProposedConstraint:
    """Map one model proposal (names) to a :class:`ProposedConstraint` (ids) with review status."""
    kind = str(raw.get("kind") or "")
    spec = KINDS.get(kind)
    hardness = str(raw.get("hardness") or (spec.default_hardness if spec else "soft"))
    weight = int(raw.get("weight") or 1)
    weight = max(1, min(10, weight))
    issues: list[str] = []
    entities: list[ResolvedEntity] = []
    params: dict[str, Any] = {}
    selector = _clean(raw.get("selector"))
    mp = _clean(raw.get("params"))

    if spec is None:
        return ProposedConstraint(kind=kind, hardness="soft", nl_text=str(raw.get("nl_text") or ""), status="rejected", issues=[f"unknown kind '{kind}'"])
    if hardness not in spec.allowed_hardness:
        issues.append(f"'{kind}' cannot be {hardness}; using {spec.allowed_hardness[0]}")
        hardness = spec.allowed_hardness[0]

    # --- selector ---------------------------------------------------------
    program_canonical: str | None = None
    if selector.get("program_name"):
        ent = resolve_program(ctx, str(selector["program_name"]))
        entities.append(ent)
        if ent.resolved_id is not None:
            program_canonical = ent.resolved_label
            years = [int(y) for y in (selector.get("class_years") or []) if int(y) > 0]
            if years:
                params["cohorts"] = [f"PROG:{program_canonical}:Y{y}" for y in years]
            else:
                params["program"] = program_canonical
        else:
            issues.append(f"programme '{selector['program_name']}' not found")
    if selector.get("course_codes"):
        ids: list[int] = []
        for code in selector["course_codes"]:
            ent, mr_ids = resolve_course(ctx, str(code), program_canonical)
            entities.append(ent)
            if ent.resolved_id is None:
                issues.append(f"course '{code}' not found in this term")
            elif not mr_ids:
                issues.append(f"course '{code}' has no roomed meetings in this term")
            ids.extend(mr_ids)
        if ids:
            params["event_ids"] = sorted(set(ids))
            params.pop("program", None)  # course ids are more specific than the programme
            params.pop("cohorts", None)
    if selector.get("instructor_name"):
        ent = resolve_instructor(ctx, str(selector["instructor_name"]))
        entities.append(ent)
        if ent.resolved_id is not None:
            params["instructors"] = [f"INS:{ent.resolved_id}"]
        else:
            issues.append(f"instructor '{selector['instructor_name']}' not found")
    if selector.get("match") and not any(k in params for k in ("event_ids", "program", "cohorts", "instructors")):
        params["match"] = str(selector["match"])
        issues.append("selector is a free-text match; please confirm the targeted events")
    if selector.get("kinds"):
        params["kinds"] = [str(k) for k in selector["kinds"]]
    if not spec.selectable:
        for k in ("event_ids", "program", "cohorts", "instructors", "match", "kinds"):
            params.pop(k, None)

    # --- params -----------------------------------------------------------
    if mp.get("room_codes"):
        ents = resolve_rooms(ctx, [str(c) for c in mp["room_codes"]])
        entities.extend(ents)
        room_ids = [e.resolved_id for e in ents if e.resolved_id is not None]
        for e in ents:
            if e.resolved_id is None:
                issues.append(f"room '{e.text}' not found")
        if kind == "room_closed":
            if room_ids:
                params["room_id"] = room_ids[0]
                if len(room_ids) > 1:
                    issues.append("room_closed takes one room; extra rooms need separate rules")
        elif room_ids:
            params["room_ids"] = room_ids
    if kind == "evening_programs_in_buildings":
        params["buildings"] = [str(b).upper()[:1] for b in (mp.get("buildings") or ([mp["building"]] if mp.get("building") else []))]
        if not params["buildings"]:
            issues.append("no building given")
    elif kind == "building_preference":
        if mp.get("buildings"):
            params["buildings"] = [str(b).upper()[:1] for b in mp["buildings"]]
        elif mp.get("building"):
            params["building"] = str(mp["building"]).upper()[:1]
        else:
            issues.append("no building given")
        if mp.get("days"):
            params["days"] = [int(d) for d in mp["days"]]
            issues.append("day-specific building rules are applied to every day by the solver (review)")
    if kind == "room_tags":
        for key in ("required_tags", "forbidden_tags"):
            if mp.get(key):
                params[key] = [str(t).upper() for t in mp[key]]
        if not params.get("required_tags") and not params.get("forbidden_tags"):
            issues.append("room_tags needs required_tags or forbidden_tags")
    if kind == "day_window":
        if mp.get("periods"):
            params["periods"] = [int(p) for p in mp["periods"]]
        else:
            if mp.get("earliest") is not None:
                params["earliest"] = int(mp["earliest"])
            if mp.get("latest") is not None:
                params["latest"] = int(mp["latest"])
            if "earliest" not in params and "latest" not in params:
                issues.append("day_window needs periods or earliest/latest")
        if mp.get("days"):
            params["days"] = [int(d) for d in mp["days"]]
    if kind == "room_closed":
        if mp.get("day") is not None:
            params["day"] = int(mp["day"])
        elif mp.get("days"):
            params["days"] = [int(d) for d in mp["days"]]
        else:
            issues.append("room_closed needs a day")
        if mp.get("periods"):
            params["periods"] = [int(p) for p in mp["periods"]]
        elif mp.get("start_period") is not None or mp.get("end_period") is not None:
            params["start"] = int(mp.get("start_period") or 1)
            params["end"] = int(mp.get("end_period") or len(PERIODS))
        if mp.get("label"):
            params["label"] = str(mp["label"])
        if "room_id" not in params:
            issues.append("room_closed needs a room")
    if kind == "fixed_time":
        if mp.get("day") is not None:
            params["day"] = int(mp["day"])
        if mp.get("start_period") is not None:
            params["start"] = int(mp["start_period"])
    if kind == "capacity" and mp.get("size") is not None:
        params["size"] = int(mp["size"])
    if kind == "min_capacity_waste" and mp.get("unit") is not None:
        params["unit"] = int(mp["unit"])
    if kind == "exam_gap" and mp.get("min_periods") is not None:
        params["min_periods"] = int(mp["min_periods"])
    if kind == "max_exams_per_day" and mp.get("max_per_day") is not None:
        params["n"] = int(mp["max_per_day"])
    if kind in ("exam_gap", "max_exams_per_day") and "kinds" not in params:
        params["kinds"] = ["exam"]
    if kind in ("same_room_group", "same_room_across_weeks") and "event_ids" not in params:
        issues.append(f"{kind} needs course codes to group")

    # --- weeks / dates (room_closed honours weeks; other kinds: review) ----
    weeks: list[int] = [int(w) for w in (mp.get("weeks") or [])]
    for key in ("from_date", "to_date"):
        if mp.get(key):
            ent = week_for_date(ctx, str(mp[key]))
            entities.append(ent)
            if ent.resolved_id is None:
                issues.append(f"date '{mp[key]}' is outside the term")
    from_w = next((e.resolved_id for e in entities if e.type == "date" and e.text == str(mp.get("from_date"))), None)
    to_w = next((e.resolved_id for e in entities if e.type == "date" and e.text == str(mp.get("to_date"))), None)
    if from_w or to_w:
        weeks = list(range(int(from_w or 1), int(to_w or ctx.week_count) + 1))
    if mp.get("last_n_weeks"):
        n = int(mp["last_n_weeks"])
        weeks = list(range(max(1, ctx.week_count - n + 1), ctx.week_count + 1))
    if weeks:
        params["weeks"] = sorted(set(weeks))
        if kind != "room_closed":
            issues.append(
                "week-limited rule: the solver applies room rules to all weeks of an event; "
                "split the meeting by week pattern first (needs review)"
            )

    # --- validation + status ----------------------------------------------
    issues.extend(validate_params(kind, params, hardness))
    unresolved = any(e.resolved_id is None for e in entities)
    conf = float(raw.get("confidence") or 0.0)
    conf = max(0.0, min(1.0, conf))
    if entities:
        conf = min(conf or 1.0, min(e.confidence for e in entities if e.resolved_id is not None) if not unresolved else conf)
    status = "needs_review" if (issues or unresolved or conf < 0.6) else "ok"
    if unresolved:
        conf = min(conf, 0.4)
    return ProposedConstraint(
        kind=kind,
        params=params,
        hardness="hard" if hardness == "hard" else "soft",
        weight=weight,
        nl_text=str(raw.get("nl_text") or ""),
        rationale=str(raw.get("rationale") or ""),
        confidence=round(conf, 2),
        title=str(raw.get("title") or "") or None,
        status=status,
        issues=issues,
        entities=entities,
    )


__all__ = [
    "TermContext",
    "load_term_context",
    "resolve_course",
    "resolve_instructor",
    "resolve_program",
    "resolve_proposal",
    "resolve_room",
    "resolve_rooms",
    "week_for_date",
]
