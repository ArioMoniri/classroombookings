"""Term context + resolution of the names the model uses into database ids.

The model only ever names things ("A 206", "Psikoloji 1. sınıf", "PHAR 240"); this module maps them to
ids with the normalisers of :mod:`app.importers.normalize` and a conservative fuzzy match. Anything
that does not resolve confidently becomes ``needs_review`` with candidates - ids are never invented.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.catalog import KINDS, validate_params
from app.importers.normalize import (
    PERIODS,
    canon_course_code,
    canon_program,
    parse_class_year,
    parse_room_codes,
    tr_casefold,
)
from app.models import Course, Instructor, Program, Room, Section, Term, Week
from app.schemas.ai import ProposedConstraint, ProposedSectionEdit, ResolvedEntity, SectionChanges
from app.services.calendar import week_index_for_date

FUZZY_ACCEPT = 0.86
FUZZY_SUGGEST = 0.55


def _room_brief(r: Room) -> str:
    exam = f"/{r.exam_capacity}" if r.exam_capacity else ""
    tags = ("," + "+".join(str(t) for t in r.tags)) if r.tags else ""
    return f"{r.display_name}({r.capacity}{exam}{tags})"


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
    #: section id -> Section (term sections incl. ones excluded from room planning)
    sections: dict[int, Section] = field(default_factory=dict)

    @property
    def week_count(self) -> int:
        return int(self.term.week_count or (max((w.index for w in self.weeks), default=14)))

    @property
    def rooms_by_code(self) -> dict[str, Room]:
        return {r.code: r for r in self.rooms}

    def prompt_block(self) -> str:
        """Compact, deterministic description for the system prompt (cache friendly)."""
        rooms = ", ".join(_room_brief(r) for r in sorted(self.rooms, key=lambda r: r.code))
        programs = "; ".join(p.name for p in sorted(self.programs, key=lambda p: p.canonical_name))
        courses = " ".join(c.display_code for c in sorted(self.courses, key=lambda c: c.code))
        wk = []
        for w in sorted(self.weeks, key=lambda w: w.index):
            start = w.start_date.isoformat() if w.start_date else "?"
            wk.append(f"W{w.index}={start}" + (f"({w.kind})" if w.kind != "LECTURE" else ""))
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
                .where(Section.term_id == term_id)
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
        if s.archived:
            continue
        courses[s.course_id] = s.course
        if s.program is not None:
            programs[s.program.id] = s.program
        mr_ids = [m.id for m in s.meeting_requests if not m.archived and m.needs_room]
        by_course.setdefault(s.course_id, []).append((s.id, s.program.canonical_name if s.program else None, mr_ids))
    for p in (await session.execute(select(Program))).scalars():
        programs.setdefault(p.id, p)
    instructors = list((await session.execute(select(Instructor))).scalars())
    return TermContext(
        term,
        weeks,
        rooms,
        list(programs.values()),
        list(courses.values()),
        instructors,
        by_course,
        {s.id: s for s in sections},
    )


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
        (
            (max(_ratio(key, r.code.casefold()), _ratio(key, r.display_name.casefold().replace(" ", ""))), r)
            for r in ctx.rooms
        ),
        key=lambda t: -t[0],
    )
    cands = [{"id": r.id, "label": r.display_name, "score": round(s, 2)} for s, r in scored[:3] if s >= FUZZY_SUGGEST]
    if scored and scored[0][0] >= FUZZY_ACCEPT:
        s, r = scored[0]
        return ResolvedEntity(
            type="room",
            text=text,
            resolved_id=r.id,
            resolved_label=r.display_name,
            confidence=round(s, 2),
            candidates=cands,
        )
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


_YEAR_PATTERNS = (
    r"\b\d\s*\.?\s*sınıf(lar)?\w*",
    r"\b(birinci|ikinci|üçüncü|dördüncü|beşinci|altıncı)\s+sınıf\w*",
    r"\bilk\s+yıl\w*",
    r"\b(first|second|third|fourth|fifth|sixth)[- ]year\b",
    r"\byear\s*\d\b",
    r"\b\d(st|nd|rd|th)[- ]year\b",
)
_FILLER = r"\b(öğrencileri|öğrencisi|öğrenciler|students?|programı|bölümü|için|for)\b"
_WORD_YEARS = {
    "birinci": 1,
    "ikinci": 2,
    "üçüncü": 3,
    "dördüncü": 4,
    "beşinci": 5,
    "altıncı": 6,
    "ilk": 1,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
}


def split_program_and_years(text: str) -> tuple[str, list[int]]:
    """``"Psikoloji 1. sınıf"`` -> ``("Psikoloji", [1])``; ``"first-year nursing"`` -> ``("nursing", [1])``."""
    low = tr_casefold(text)
    years: list[int] = []
    rest = low
    for pat in _YEAR_PATTERNS:
        for m in re.finditer(pat, rest):
            frag = m.group(0)
            word = frag.split()[0].split("-")[0]
            if word in _WORD_YEARS:
                years.append(_WORD_YEARS[word])
            else:
                years.extend(parse_class_year(frag) or [int(d) for d in re.findall(r"\d", frag)[:1]])
        rest = re.sub(pat, " ", rest)
    rest = re.sub(_FILLER, " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" ,;-")
    if not years:
        return text.strip(), []
    # keep the original casing of the programme part when possible
    idx = low.find(rest) if rest else -1
    name = text[idx : idx + len(rest)] if idx >= 0 else rest
    return name.strip(), sorted({y for y in years if 1 <= y <= 6})


#: English names planners use for Turkish programme names (resolver hint, never an id source).
PROGRAM_ALIASES = {
    "nursing": "hemşirelik",
    "pharmacy": "eczacılık",
    "psychology": "psikoloji",
    "medicine": "tıp",
    "dentistry": "diş hekimliği",
    "physiotherapy": "fizyoterapi ve rehabilitasyon",
    "nutrition": "beslenme ve diyetetik",
    "midwifery": "ebelik",
    "law": "hukuk",
    "architecture": "mimarlık",
}


def resolve_program(ctx: TermContext, text: str) -> ResolvedEntity:
    alias = PROGRAM_ALIASES.get(tr_casefold(text).strip())
    if alias is not None and any(p.canonical_name == alias for p in ctx.programs):
        ent = resolve_program(ctx, alias)
        ent.text = text
        return ent
    parsed = canon_program(text)
    if parsed is None:
        return ResolvedEntity(type="program", text=text)
    key = parsed.canonical
    exact = [p for p in ctx.programs if p.canonical_name == key]
    if exact:
        p = exact[0]
        return ResolvedEntity(
            type="program", text=text, resolved_id=p.id, resolved_label=p.canonical_name, confidence=1.0
        )
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
        return ResolvedEntity(
            type="program",
            text=text,
            resolved_id=p.id,
            resolved_label=p.canonical_name,
            confidence=round(s, 2),
            candidates=cands,
        )
    return ResolvedEntity(type="program", text=text, candidates=cands)


def resolve_course(
    ctx: TermContext, text: str, program_canonical: str | None = None
) -> tuple[ResolvedEntity, list[int]]:
    """Course text -> entity (course id) + meeting request ids in the term (optionally one programme)."""
    code = canon_course_code(text) or canon_course_code(re.sub(r"[^\w]+", " ", text))
    by_code = {c.code: c for c in ctx.courses}
    course = by_code.get(code or "")
    if course is None:
        cands: list[dict[str, Any]] = []
        if code:
            for c in ctx.courses:
                s = _ratio(code, c.code)
                if s >= 0.8:
                    cands.append({"id": c.id, "label": c.display_code, "score": round(s, 2)})
            cands.sort(key=lambda d: -float(d["score"]))
        return ResolvedEntity(type="course", text=text, candidates=cands[:3]), []
    ids: list[int] = []
    for _sid, prog, mr_ids in ctx.sections_by_course.get(course.id, []):
        if program_canonical and prog != program_canonical:
            continue
        ids.extend(mr_ids)
    ent = ResolvedEntity(
        type="course", text=text, resolved_id=course.id, resolved_label=course.display_code, confidence=1.0
    )
    return ent, sorted(set(ids))


_FOLD_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")
#: a fuzzy given-name match must beat the runner-up by this much, or it is ambiguous (review M12)
PERSON_TIE_MARGIN = 0.08
PERSON_GIVEN_MIN = 0.85


def _person_key(text: str) -> list[str]:
    """Canonical name words without titles, Turkish-casefolded and diacritic-folded (``Süer`` = ``Suer``)."""
    from app.importers.normalize import canon_person_name

    parsed = canon_person_name(text)
    canon = parsed.canonical if parsed is not None else tr_casefold(text)
    return [w.translate(_FOLD_ASCII).strip(".") for w in canon.split() if w.strip(".")]


def resolve_instructor(ctx: TermContext, text: str) -> ResolvedEntity:
    """Strict person resolution (review M12): an exact canonical name (titles ignored, Turkish case and
    diacritics folded), or the **exact surname** plus given names that each fuzzily match one of the
    candidate's given names, beating the runner-up by :data:`PERSON_TIE_MARGIN`. Anything else is left
    unresolved with suggestions, so an invented or misspelt name ends in ``needs_review``."""
    words = _person_key(text)
    people = [(i, _person_key(i.canonical_name)) for i in ctx.instructors]
    suggest = sorted(((_ratio(" ".join(words), " ".join(k)), i) for i, k in people if k), key=lambda t: -t[0])
    cands = [{"id": i.id, "label": i.full_name, "score": round(sc, 2)} for sc, i in suggest[:3] if sc >= FUZZY_SUGGEST]
    if not words:
        return ResolvedEntity(type="instructor", text=text, candidates=cands)
    exact = [i for i, k in people if k == words]
    if len(exact) == 1:
        return ResolvedEntity(
            type="instructor", text=text, resolved_id=exact[0].id, resolved_label=exact[0].full_name,
            confidence=1.0, candidates=cands,
        )  # fmt: skip
    if len(exact) > 1:  # two people with one name: the planner must pick
        return ResolvedEntity(
            type="instructor", text=text,
            candidates=[{"id": i.id, "label": i.full_name, "score": 1.0} for i in exact[:5]],
        )  # fmt: skip
    if len(words) < 2:
        return ResolvedEntity(type="instructor", text=text, candidates=cands)
    surname, given = words[-1], words[:-1]
    scored: list[tuple[float, Any]] = []
    for i, k in people:
        if len(k) < 2 or k[-1] != surname:
            continue
        their = k[:-1]
        per = [max((_ratio(g, t) for t in their), default=0.0) for g in given]
        if per and min(per) >= PERSON_GIVEN_MIN:
            scored.append((sum(per) / len(per), i))
    scored.sort(key=lambda t: -t[0])
    if scored and (len(scored) == 1 or scored[0][0] - scored[1][0] >= PERSON_TIE_MARGIN):
        sc, i = scored[0]
        return ResolvedEntity(
            type="instructor", text=text, resolved_id=i.id, resolved_label=i.full_name,
            confidence=round(min(0.95, sc), 2), candidates=cands,
        )  # fmt: skip
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


def clean_sentinels(d: dict[str, Any] | None) -> dict[str, Any]:
    """Drop the strict-schema "unset" sentinels: ``None``, ``""``, ``[]`` and integer ``0``."""
    out: dict[str, Any] = {}
    for k, v in (d or {}).items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, int) and not isinstance(v, bool) and v == 0:
            continue
        out[k] = v
    return out


def _ints(values: Any, lo: int, hi: int) -> list[int]:
    out: list[int] = []
    for v in values or []:
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if lo <= iv <= hi:
            out.append(iv)
    return sorted(set(out))


def _resolve_selector(
    ctx: TermContext,
    selector: dict[str, Any],
    params: dict[str, Any],
    entities: list[ResolvedEntity],
    issues: list[str],
) -> str | None:
    """Fill the resolved selector keys into ``params``; returns the programme canonical name."""
    program_canonical: str | None = None
    years = _ints(selector.get("class_years"), 1, 6)
    if selector.get("program_name"):
        name, text_years = split_program_and_years(str(selector["program_name"]))
        years = years or text_years
        ent = resolve_program(ctx, name)
        ent.text = str(selector["program_name"])
        entities.append(ent)
        if ent.resolved_id is not None:
            program_canonical = ent.resolved_label
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
        params["kinds"] = [str(k) for k in selector["kinds"] if k in ("course", "exam")]
    return program_canonical


def _weeks_from(ctx: TermContext, mp: dict[str, Any], entities: list[ResolvedEntity], issues: list[str]) -> list[int]:
    weeks = _ints(mp.get("weeks"), 1, ctx.week_count + 4)
    bounds: dict[str, int | None] = {}
    for key in ("from_date", "to_date"):
        if mp.get(key):
            ent = week_for_date(ctx, str(mp[key]))
            entities.append(ent)
            bounds[key] = ent.resolved_id
            if ent.resolved_id is None:
                issues.append(f"date '{mp[key]}' is outside the term")
    if bounds.get("from_date") or bounds.get("to_date"):
        weeks = list(range(int(bounds.get("from_date") or 1), int(bounds.get("to_date") or ctx.week_count) + 1))
    if mp.get("last_n_weeks"):
        n = int(mp["last_n_weeks"])
        weeks = list(range(max(1, ctx.week_count - n + 1), ctx.week_count + 1))
    return weeks


def resolve_proposal(ctx: TermContext, raw: dict[str, Any]) -> ProposedConstraint:
    """Map one model proposal (names) to a :class:`ProposedConstraint` (ids) with review status.

    Every id in the result comes from the database; names that do not resolve confidently are kept
    as entities with candidates and the proposal is ``needs_review``.
    """
    kind = str(raw.get("kind") or "")
    spec = KINDS.get(kind)
    nl_text = str(raw.get("nl_text") or "")
    if spec is None:
        return ProposedConstraint(kind=kind, nl_text=nl_text, status="rejected", issues=[f"unknown kind '{kind}'"])
    hardness = str(raw.get("hardness") or spec.default_hardness)
    try:
        weight = int(raw.get("weight") or 0)
    except (TypeError, ValueError):
        weight = 0
    weight = max(1, min(10, weight or 5)) if hardness == "soft" else max(1, min(10, weight or 1))
    issues: list[str] = []
    entities: list[ResolvedEntity] = []
    params: dict[str, Any] = {}
    selector = clean_sentinels(raw.get("selector"))
    mp = clean_sentinels(raw.get("params"))

    if hardness not in spec.allowed_hardness:
        issues.append(f"'{kind}' cannot be {hardness}; using {spec.allowed_hardness[0]}")
        hardness = spec.allowed_hardness[0]

    if spec.selectable:
        _resolve_selector(ctx, selector, params, entities, issues)
    elif selector:
        issues.append(f"'{kind}' applies to all events; the selector was ignored")

    amount = int(mp.get("amount") or 0)
    days = _ints(mp.get("days"), 1, 7)
    periods = _ints(mp.get("periods"), 1, len(PERIODS))
    earliest = int(mp.get("earliest") or 0)
    latest = int(mp.get("latest") or 0)
    buildings = [str(b).strip().upper()[:1] for b in (mp.get("buildings") or []) if str(b).strip()]

    # --- rooms -------------------------------------------------------------
    room_ids: list[int] = []
    if mp.get("room_codes"):
        ents = resolve_rooms(ctx, [str(c) for c in mp["room_codes"]])
        entities.extend(ents)
        room_ids = [e.resolved_id for e in ents if e.resolved_id is not None]
        issues.extend(f"room '{e.text}' not found" for e in ents if e.resolved_id is None)

    # --- kind-specific params ---------------------------------------------
    if kind in ("room_pin", "room_forbid", "room_preference"):
        if room_ids:
            params["room_ids"] = room_ids
        elif not mp.get("room_codes"):
            issues.append(f"{kind} needs at least one room")
    elif kind == "room_closed":
        if room_ids:
            params["room_id"] = room_ids[0]
            if len(room_ids) > 1:
                issues.append("room_closed takes one room; extra rooms need separate rules")
        elif not mp.get("room_codes"):
            issues.append("room_closed needs a room")
        if len(days) == 1:
            params["day"] = days[0]
        elif days:
            params["days"] = days
        else:
            issues.append("room_closed needs a day")
        if periods:
            params["periods"] = periods
        elif earliest or latest:
            params["start"] = earliest or 1
            params["end"] = latest or len(PERIODS)
        if mp.get("label"):
            params["label"] = str(mp["label"])
    elif kind in ("building_preference", "evening_programs_in_buildings"):
        if not buildings:
            issues.append("no building given")
        elif kind == "building_preference" and len(buildings) == 1:
            params["building"] = buildings[0]
        else:
            params["buildings"] = buildings
        if kind == "building_preference" and days:
            params["days"] = days
            issues.append("day-specific building rules are applied to every day by the solver (review)")
    elif kind == "room_tags":
        for key in ("required_tags", "forbidden_tags"):
            if mp.get(key):
                params[key] = sorted({str(t).upper() for t in mp[key]})
        if not params.get("required_tags") and not params.get("forbidden_tags"):
            issues.append("room_tags needs required_tags or forbidden_tags")
    elif kind == "day_window":
        if periods:
            params["periods"] = periods
        else:
            if earliest:
                params["earliest"] = earliest
            if latest:
                params["latest"] = latest
            if not earliest and not latest:
                issues.append("day_window needs periods or earliest/latest")
        if days:
            params["days"] = days
    elif kind == "fixed_time":
        if days:
            params["day"] = days[0]
        if amount:
            params["start"] = amount
        if not days and not amount:
            issues.append("fixed_time needs a day and/or a start period")
    elif kind == "capacity" and amount:
        params["size"] = amount
    elif kind == "min_capacity_waste" and amount:
        params["unit"] = amount
    elif kind == "exam_gap":
        params["min_periods"] = amount or 1
    elif kind == "max_exams_per_day":
        params["n"] = amount or 1
    if kind in ("exam_gap", "max_exams_per_day") and "kinds" not in params:
        params["kinds"] = ["exam"]
    if kind in ("same_room_group", "same_room_across_weeks") and len(params.get("event_ids", [])) < 2:
        issues.append(f"{kind} needs course codes that resolve to two or more meetings")
    if kind in ("room_pin", "room_forbid", "room_preference", "day_window", "fixed_time", "stability") and not any(
        k in params for k in ("event_ids", "program", "cohorts", "instructors", "match")
    ):
        issues.append(f"{kind} without a selector applies to every event (review)")

    # --- weeks / dates (room_closed honours weeks; other kinds: review) ----
    weeks = _weeks_from(ctx, mp, entities, issues)
    if weeks:
        params["weeks"] = weeks
        if kind not in ("room_closed", "room_pin"):
            issues.append(
                "week-limited rule: the solver applies this rule to all weeks of an event; "
                "split the meeting by week pattern first (needs review)"
            )

    # --- validation + status ----------------------------------------------
    issues.extend(validate_params(kind, params, hardness))
    return ProposedConstraint(
        kind=kind,
        params=params,
        hardness="hard" if hardness == "hard" else "soft",
        weight=weight,
        nl_text=nl_text,
        rationale=str(raw.get("rationale") or ""),
        confidence=_confidence(raw, entities),
        title=str(raw.get("title") or "") or None,
        status=_status(issues, entities, _confidence(raw, entities)),
        issues=issues,
        entities=entities,
    )


def _confidence(raw: dict[str, Any], entities: list[ResolvedEntity]) -> float:
    try:
        conf = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf)) or 0.8
    resolved = [e.confidence for e in entities if e.resolved_id is not None]
    if resolved:
        conf = min(conf, min(resolved))
    if any(e.resolved_id is None for e in entities):
        conf = min(conf, 0.4)
    return round(conf, 2)


def _status(issues: list[str], entities: list[ResolvedEntity], conf: float) -> Literal["ok", "needs_review"]:
    unresolved = any(e.resolved_id is None for e in entities)
    return "needs_review" if (issues or unresolved or conf < 0.6) else "ok"


# ---------------------------------------------------------------------------
# Sections (file ingestion + chat section edits)
# ---------------------------------------------------------------------------


def section_label(ctx: TermContext, section_id: int) -> str:
    s = ctx.sections.get(section_id)
    if s is None:
        return f"section {section_id}"
    prog = s.program.name if s.program is not None else "-"
    return f"{s.course.display_code}{' §' + s.label if s.label else ''} ({prog})"


def resolve_section_targets(
    ctx: TermContext, target: dict[str, Any], entities: list[ResolvedEntity], issues: list[str]
) -> list[int]:
    """``section_ids`` (validated against the term) or ``course_codes`` [+ programme, section label]."""
    out: list[int] = []
    for sid in _ints(target.get("section_ids"), 1, 2**31 - 1):
        if sid in ctx.sections:
            out.append(sid)
            entities.append(
                ResolvedEntity(
                    type="section",
                    text=str(sid),
                    resolved_id=sid,
                    resolved_label=section_label(ctx, sid),
                    confidence=1.0,
                )
            )
        else:
            entities.append(ResolvedEntity(type="section", text=str(sid)))
            issues.append(f"section id {sid} is not in this term")
    prog_canon: str | None = None
    if target.get("program_name"):
        name, _years = split_program_and_years(str(target["program_name"]))
        ent = resolve_program(ctx, name)
        ent.text = str(target["program_name"])
        entities.append(ent)
        if ent.resolved_id is None:
            issues.append(f"programme '{target['program_name']}' not found")
        else:
            prog_canon = ent.resolved_label
    label = str(target.get("section_label") or "").strip().lstrip("§").strip()
    by_code = {c.code: c for c in ctx.courses}
    for code in target.get("course_codes") or []:
        canon = canon_course_code(str(code)) or canon_course_code(re.sub(r"[^\w]+", " ", str(code)))
        course = by_code.get(canon or "")
        if course is None:
            # sections excluded from planning still count (include_sections must find them)
            course = next((s.course for s in ctx.sections.values() if s.course.code == canon), None)
        if course is None:
            ent, _ = resolve_course(ctx, str(code))
            entities.append(ent)
            issues.append(f"course '{code}' not found in this term")
            continue
        matches = [
            s.id
            for s in ctx.sections.values()
            if s.course_id == course.id
            and not s.archived
            and (prog_canon is None or (s.program is not None and s.program.canonical_name == prog_canon))
            and (not label or (s.label or "").strip() == label)
        ]
        entities.append(
            ResolvedEntity(
                type="course", text=str(code), resolved_id=course.id, resolved_label=course.display_code, confidence=1.0
            )
        )
        if not matches:
            issues.append(f"no section of '{code}' matches the programme / section label")
        out.extend(matches)
    return sorted(set(out))


def resolve_section_edit(ctx: TermContext, op: str, raw: dict[str, Any]) -> ProposedSectionEdit:
    """Model section edit (names) -> :class:`ProposedSectionEdit` with validated section/room ids."""
    data = clean_sentinels(raw)
    issues: list[str] = []
    entities: list[ResolvedEntity] = []
    section_ids = resolve_section_targets(ctx, data, entities, issues)
    if not section_ids and not issues:
        issues.append("no section targeted")
    changes: dict[str, Any] = {}
    if op == "set_field":
        if data.get("enrolment"):
            changes["enrolment"] = int(data["enrolment"])
        if data.get("day"):
            changes["day"] = int(data["day"])
        if data.get("start_period"):
            changes["start_period"] = int(data["start_period"])
        if data.get("end_period"):
            changes["end_period"] = int(data["end_period"])
        if data.get("mode"):
            changes["mode"] = str(data["mode"])
        if data.get("preferred_room_codes"):
            ents = resolve_rooms(ctx, [str(c) for c in data["preferred_room_codes"]])
            entities.extend(ents)
            ids = [e.resolved_id for e in ents if e.resolved_id is not None]
            issues.extend(f"room '{e.text}' not found" for e in ents if e.resolved_id is None)
            if ids:
                changes["preferred_room_ids"] = ids
        if not changes:
            issues.append("set_field without any change")
    status: Literal["ok", "needs_review", "rejected"] = "ok"
    sc: SectionChanges | None = None
    try:
        sc = SectionChanges(**changes)
    except ValueError as exc:  # pydantic ValidationError is a ValueError
        issues.append(f"invalid change: {str(exc).splitlines()[0][:160]}")
        status = "rejected"
    if sc is not None and sc.start_period and sc.end_period and sc.end_period < sc.start_period:
        issues.append("end period before start period")
        status = "rejected"
    conf = _confidence(raw, entities)
    if status != "rejected":
        status = _status(issues, entities, conf)
    return ProposedSectionEdit(
        op=op if op in ("include", "exclude", "set_field") else "set_field",
        section_ids=section_ids,
        changes=sc or SectionChanges(),
        nl_text=str(raw.get("nl_text") or raw.get("reason") or ""),
        rationale=str(raw.get("rationale") or raw.get("reason") or ""),
        confidence=conf,
        status=status,
        issues=issues,
        entities=entities,
        labels=[section_label(ctx, sid) for sid in section_ids],
    )


__all__ = [
    "TermContext",
    "clean_sentinels",
    "load_term_context",
    "resolve_course",
    "resolve_instructor",
    "resolve_program",
    "resolve_proposal",
    "resolve_room",
    "resolve_rooms",
    "resolve_section_edit",
    "resolve_section_targets",
    "section_label",
    "split_program_and_years",
    "week_for_date",
]
