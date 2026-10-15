"""Learned suggestions: priors, explanations, decisions and resettable memory (P19-L3 / P19-L4).

Model (review 2026-10-15 §3b, decisions in docs/ROADMAP.md Phase 19):

* **score** of a (subject, attribute, value) for a target term T = Σ weight·sign·0.5^(Δterms/2), Δterms = lecture
  terms between the evidence's term and T (half-life of two terms).
* **confidence** = Wilson lower bound of support / total, with z = 1 (:data:`WILSON_Z`). With z = 1.96 the
  decided minimum evidence (2 rows over 2 terms, 3 repeats in one term) could never reach 0.6 (6/6 rows would be
  needed), so the one-sigma bound is used: 2/2 -> 0.67, 3/3 -> 0.75, 8/8 -> 0.89, 1/2 -> 0.21.
* **suggested** only when score > 0, support >= 2 over >= 2 terms or >= 3 in one term, confidence >= 0.6 and the
  attribute has a soft rule to propose. Room and time evidence counts only from terms of T's season (a Güz room
  says nothing about Bahar, academician needs §3.2); building and feature evidence is kept across seasons and
  labelled "farklı dönem verisi".
* **suggest only**: nothing here is applied without a person. Accepting creates one soft, targeted
  ``ConstraintRow(source="LEARNED")`` of the allowlist {room_preference, building_preference,
  same_room_across_weeks, day_window}, weight 5 by default (Q7: learned 5 < explicit 10), checked by
  :mod:`app.services.constraint_guard` and the per-source policy of ``app.ai.catalog``.
* explicit requests always win: classes of T that already request or hold rooms / a building (or a fixed time, for
  a time band) are not targeted; a suggestion with no class left is hidden. A room below the classes' current
  enrolment or no longer bookable is never suggested.
* stored text names no person (KVKK): ``{subject}`` is filled when read, from the FK. The accepted rule's
  ``source_ref.explanation`` uses ``öğretim elemanı #<id>``.

Memory reset (planning.admin, audited): person / term / all stamps ``reset_id`` on the matching observations and
dismissals and leaves a watermark so they are not learned again; undo within 30 days restores them; a daily purge
deletes expired resets' rows. A KVKK erasure deletes a person's observations, dismissals and priors at once and
cannot be undone. Neither touches requests, runs, bookings or accepted rules.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import (
    ConstraintRow,
    Course,
    Instructor,
    LearnedObservation,
    LearnedPrior,
    LearningReset,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
    User,
)
from app.models.base import utcnow
from app.models.learning import SuggestionFeedback
from app.services import constraint_guard
from app.services.events import publish_event
from app.services.learning_extract import BANDS, SIGNALS, band_range
from app.services.tr_grammar import _spoken_tail

log = logging.getLogger("smartsched.learning")

LEARNED_KINDS: frozenset[str] = frozenset(
    {"room_preference", "building_preference", "same_room_across_weeks", "day_window"}
)
LEARNED_WEIGHT = 5  # Q7: learned preference weight 5 < explicit soft preference 10
MAX_WEIGHT = 5
MIN_CONFIDENCE = 0.6
MIN_TERMS, MIN_TERM_SUPPORT, MIN_ONE_TERM = 2, 2, 3
WILSON_Z = 1.0
UNDO_DAYS = 30
SNOOZE_MODES = ("next_solve", "P7D", "next_term")
SAME_SEASON_ATTRS = frozenset({"room", "day", "period", "day_period"})
LEVELS = ((0.8, "high", "Yüksek"), (0.6, "medium", "Orta"), (0.5, "low", "Düşük"))
_DAYS_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
_DAYS_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
_BAND_TR = {"morning": "sabah", "afternoon": "öğleden sonra", "evening": "akşam"}
_BAND_TIME = {"morning": "08:30–13:20", "afternoon": "13:30–18:00", "evening": "18:00–22:50"}
_SEASON_MONTH = {"BAHAR": 2, "FINAL": 6, "BUT": 6, "YAZ": 7, "GUZ": 9}
_BACK, _FRONT = set("aıouAIOU"), set("eiöüEİÖÜ")
_HARD = set("fstkçşhpFSTKÇŞHP")


async def _count(session: AsyncSession, stmt: Any) -> int:
    """Rows touched by a bulk UPDATE / DELETE."""
    res = await session.execute(stmt)
    return int(getattr(res, "rowcount", 0) or 0)


class LearningError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


# ------------------------------------------------------------------------------------------------ helpers


def locative(text: str) -> str:
    """``text`` + the locative suffix: ``A 204'te``, ``C 201'de``, ``A Blok'ta``, ``A 106'da``."""
    word = _spoken_tail(text)
    vowels = [c for c in word if c in _BACK or c in _FRONT]
    front = bool(vowels) and vowels[-1] in _FRONT
    hard = bool(word) and word[-1] in _HARD
    return f"{text.rstrip()}'{'t' if hard else 'd'}{'e' if front else 'a'}"


def wilson_lower(pos: int, total: int, z: float = WILSON_Z) -> float:
    if total <= 0:
        return 0.0
    p = pos / total
    z2 = z * z
    centre = p + z2 / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))
    return max(0.0, (centre - margin) / (1 + z2 / total))


def level_of(confidence: float) -> dict[str, str] | None:
    for lo, en, tr in LEVELS:
        if confidence >= lo:
            return {"code": en, "tr": tr, "en": en.capitalize()}
    return None


def season_of(term: Term) -> str:
    folded = n.fold(term.code or "").upper()
    for key, words in (
        ("BAHAR", ("BAHAR", "SPRING")),
        ("GUZ", ("GUZ", "FALL", "AUTUMN")),
        ("YAZ", ("YAZ", "SUMMER")),
        ("BUT", ("BUT",)),
        ("FINAL", ("FINAL",)),
    ):
        if any(w in folded for w in words):
            return key
    return (term.kind or "REGULAR").upper()


def term_date(term: Term) -> date:
    if term.start_date is not None:
        return term.start_date
    m = re.search(r"(19|20)\d{2}", term.code or "")
    year = int(m.group(0)) if m else 2000
    return date(year, _SEASON_MONTH.get(season_of(term), 1), 1)


def is_lecture_term(term: Term) -> bool:
    return (term.kind or "REGULAR").upper() not in ("FINAL", "BUT")


def term_distance(terms: Mapping[int, Term], a: int, b: int) -> int:
    """Lecture terms from ``a`` to ``b`` (0 for the same term)."""
    if a == b or a not in terms or b not in terms:
        return 0
    da, db = sorted((term_date(terms[a]), term_date(terms[b])))
    between = sum(1 for t in terms.values() if is_lecture_term(t) and da < term_date(t) < db)
    return between + 1


def _term_label(t: Term) -> str:
    return t.code


# ------------------------------------------------------------------------------------------------ priors


Unit = tuple[Any, ...]


def evidence_unit(term_id: int | None, src: str, sid: int, sign: int, detail: Mapping[str, Any] | None) -> Unit:
    """One piece of evidence: a request row, except that the rows of one lecture (FIZ 111 §1 listed once per
    programme: same course, day, periods and rooms in one term) are one lecture, not five repeats."""
    tag = "neg" if sign < 0 else "pos"
    if src == "meeting_requests" and detail and detail.get("course"):
        periods = tuple(detail.get("periods") or ())
        rooms = tuple(sorted(str(r) for r in detail.get("rooms") or ()))
        return ("lecture", term_id, str(detail["course"]), detail.get("day"), periods, rooms, tag)
    return (src, sid, tag)


@dataclass
class _Group:
    rows_pos: dict[str, set[Unit]] = field(default_factory=lambda: defaultdict(set))
    rows_neg: dict[str, set[Unit]] = field(default_factory=lambda: defaultdict(set))
    score: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    scored: set[tuple[str, Unit, str]] = field(default_factory=set)
    all_pos: set[Unit] = field(default_factory=set)
    row_term: dict[Unit, int | None] = field(default_factory=dict)
    kinds: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    requests: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))


def _proposal(attribute: str, value: str, tagged: Mapping[str, list[int]]) -> dict[str, Any] | None:
    if attribute == "room" and value.isdigit():
        return {"kind": "room_preference", "params": {"room_ids": [int(value)]}}
    if attribute == "building":
        return {"kind": "building_preference", "params": {"building": value}}
    if attribute == "period":
        rng = band_range(value)
        if rng:
            return {"kind": "day_window", "params": {"earliest": rng[0], "latest": rng[1]}}
    if attribute == "tag" and tagged.get(value):
        return {"kind": "room_preference", "params": {"room_ids": list(tagged[value])}}
    return None  # day / day_period: no soft "prefer this weekday" rule kind yet


def _value_text(attribute: str, value: str, rooms: Mapping[int, Room]) -> dict[str, str]:
    if attribute == "room" and value.isdigit() and int(value) in rooms:
        name = rooms[int(value)].display_name
        return {"tr": name, "en": name, "tr_loc": locative(name), "en_loc": f"in {name}"}
    if attribute == "building":
        tr_b = f"{value} Blok"
        return {"tr": tr_b, "en": f"{value} block", "tr_loc": locative(tr_b), "en_loc": f"in {value} block"}
    if attribute == "period":
        band, hours = _BAND_TR.get(value, value), _BAND_TIME.get(value, "")
        return {
            "tr": f"{band} saatleri ({hours})",
            "en": f"the {value} ({hours})",
            "tr_loc": f"{band} saatlerinde ({hours})",
            "en_loc": f"in the {value} ({hours})",
        }
    if attribute == "tag":
        return {"tr": f"{value} özellikli derslik", "en": f"a {value} room", "tr_loc": f"{value} özellikli derslikte"}
    if attribute == "day" and value.isdigit():
        d = int(value)
        tr_day, en_day = _DAYS_TR.get(d, value), _DAYS_EN.get(d, value)
        return {"tr": tr_day, "en": en_day, "tr_loc": f"{tr_day} günü", "en_loc": f"on {en_day}"}
    if attribute == "day_period" and ":" in value:
        day_s, b = value.split(":", 1)
        day_i = int(day_s) if day_s.isdigit() else 0
        tr = f"{_DAYS_TR.get(day_i, day_s)} {_BAND_TR.get(b, b)}"
        en = f"{_DAYS_EN.get(day_i, day_s)} {b}"
        return {"tr": tr, "en": en, "tr_loc": tr, "en_loc": f"on {en}"}
    return {"tr": value, "en": value, "tr_loc": value, "en_loc": f"in {value}"}


def explanation(
    attribute: str, vt: Mapping[str, str], support: int, total: int, terms: list[dict[str, Any]], cross: bool
) -> dict[str, str]:
    """TR + EN evidence sentence with counts and terms; ``{subject}`` is filled at read time. Never says
    "her zaman" / "always" (fewer than 3 terms of history is the normal case)."""
    seen = [t for t in terms if t["pos"]]
    k = len(seen)
    breakdown = ", ".join(f"{t['code']}: {t['pos']}/{t['total']}" for t in terms)
    if attribute == "period":
        where_tr, where_en = vt["tr_loc"], vt.get("en_loc", vt["en"])
        tr = (
            f"{{subject}} {k} dönemdir {where_tr} ders veriyor: {support}/{total} ders ({breakdown})."
            if k >= 2
            else f"{{subject}}: tek dönemde {support}/{total} ders {where_tr} ({breakdown})."
        )
    elif attribute == "tag":
        where_tr, where_en = vt["tr"], vt["en"]
        tr = (
            f"{{subject}} {k} dönemdir {where_tr} istiyor: {support}/{total} talep ({breakdown})."
            if k >= 2
            else f"{{subject}}: tek dönemde {support}/{total} talepte {where_tr} istendi ({breakdown})."
        )
    else:
        where_tr, where_en = vt["tr_loc"], vt.get("en_loc", vt["en"])
        tr = (
            f"{{subject}} {k} dönemdir {where_tr}: {support}/{total} kayıt ({breakdown})."
            if k >= 2
            else f"{{subject}}: tek dönemde {support}/{total} kayıt {where_tr} ({breakdown})."
        )
    if attribute == "tag":
        en = (
            f"{{subject}} has asked for {where_en} for {k} terms: {support} of {total} requests ({breakdown})."
            if k >= 2
            else f"{{subject}} asked for {where_en} in {support} of {total} requests in one term ({breakdown})."
        )
    else:
        en = (
            f"{{subject}} has been {where_en} for {k} terms: {support} of {total} records ({breakdown})."
            if k >= 2
            else f"{{subject}}: {support} of {total} records in one term were {where_en} ({breakdown})."
        )
    if cross:
        tr += " Farklı dönem verisi içerir."
        en += " Includes other-season data."
    return {"tr": tr, "en": en}


def _claim(vt: Mapping[str, str]) -> dict[str, str]:
    return {"tr": f"{{subject}} için {vt['tr']} tercih edilsin mi?", "en": f"Prefer {vt['en']} for {{subject}}?"}


def if_accepted(weight: int) -> dict[str, str]:
    return {
        "tr": f"Kabul ederseniz yumuşak bir tercih (ağırlık {weight}) eklenir; kesin kural değildir.",
        "en": f"If accepted: adds a soft preference (weight {weight}), not a hard rule.",
    }


async def _fingerprint(session: AsyncSession) -> tuple[Any, ...]:
    obs = (
        await session.execute(
            select(func.count(), func.max(LearnedObservation.id), func.count(LearnedObservation.reset_id))
        )
    ).one()
    rs = (
        await session.execute(
            select(
                func.count(),
                func.max(LearningReset.id),
                func.count(LearningReset.undone_at),
                func.count(LearningReset.purged_at),
            )
        )
    ).one()
    return (*tuple(obs), *tuple(rs))


_FRESH: dict[tuple[str, int], tuple[Any, ...]] = {}


def _db_key(session: AsyncSession, term_id: int) -> tuple[str, int]:
    bind = session.get_bind()
    return (str(getattr(bind, "url", id(bind))), term_id)


async def ensure_priors(session: AsyncSession, term_id: int, *, force: bool = False) -> bool:
    """Recompute the term's priors when the evidence changed since the last computation in this process."""
    fp = await _fingerprint(session)
    key = _db_key(session, term_id)
    has = (await session.execute(select(func.count()).where(LearnedPrior.term_id == term_id))).scalar_one()
    if not force and has and _FRESH.get(key) == fp:
        return False
    await recompute_priors(session, term_id)
    _FRESH[key] = fp
    return True


def _forget(term_id: int | None = None) -> None:
    for k in list(_FRESH):
        if term_id is None or k[1] == term_id:
            _FRESH.pop(k, None)


async def recompute_priors(session: AsyncSession, term_id: int) -> int:
    """Upsert the priors of target term ``term_id`` from the visible observations (``reset_id IS NULL``)."""
    terms = {t.id: t for t in (await session.execute(select(Term))).scalars()}
    target = terms.get(term_id)
    if target is None:
        raise LearningError(404, "term not found")
    season = season_of(target)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    tagged: dict[str, list[int]] = defaultdict(list)
    for r in sorted(rooms.values(), key=lambda r: (-int(r.capacity or 0), r.code)):
        if r.is_bookable:
            for t in r.tags or []:
                tagged[str(t).upper()].append(r.id)
    q = select(
        LearnedObservation.term_id,
        LearnedObservation.kind,
        LearnedObservation.subject_type,
        LearnedObservation.subject_key,
        LearnedObservation.attribute,
        LearnedObservation.value,
        LearnedObservation.sign,
        LearnedObservation.weight,
        LearnedObservation.source_table,
        LearnedObservation.source_id,
        LearnedObservation.detail,
    ).where(LearnedObservation.reset_id.is_(None))
    groups: dict[tuple[str, str, str], _Group] = defaultdict(_Group)
    cross: dict[tuple[str, str, str, str], bool] = defaultdict(bool)
    seasons = {tid: season_of(t) for tid, t in terms.items()}
    decays = {tid: 0.5 ** (term_distance(terms, term_id, tid) / 2) for tid in terms}
    for t_id, kind, st, sk, attr, val, sign, weight, src, sid, detail in (await session.execute(q)).all():
        tid_k = int(t_id) if t_id is not None else -1
        known = tid_k in terms
        other = known and seasons[tid_k] != season
        if attr in SAME_SEASON_ATTRS and (not known or other):
            continue
        g = groups[(st, sk, attr)]
        row = evidence_unit(t_id, src, sid, sign, detail)
        g.row_term[row] = t_id
        if (val, row, kind) not in g.scored:  # a lecture listed once per programme counts once
            g.scored.add((val, row, kind))
            g.score[val] += weight * sign * (decays[tid_k] if known else 1.0)
        g.kinds[val][kind] += 1
        if detail and detail.get("request_id"):
            g.requests[val].add(int(detail["request_id"]))
        if sign < 0:
            g.rows_neg[val].add(row)
        else:
            g.rows_pos[val].add(row)
            g.all_pos.add(row)
        if other:
            cross[(st, sk, attr, val)] = True

    now = utcnow()
    computed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for (st, sk, attr), g in groups.items():
        for val in set(g.rows_pos) | set(g.rows_neg):
            pos = g.rows_pos.get(val, set())
            if not pos:
                continue
            universe = g.all_pos | g.rows_neg.get(val, set())
            support, total = len(pos), len(universe)
            per_term: dict[int | None, list[int]] = defaultdict(lambda: [0, 0])
            for row in universe:
                per_term[g.row_term.get(row)][1] += 1
            for row in pos:
                per_term[g.row_term.get(row)][0] += 1
            term_rows = sorted(
                (
                    {
                        "term_id": tid,
                        "code": _term_label(terms[tid]) if tid in terms else "—",
                        "pos": c[0],
                        "total": c[1],
                    }
                    for tid, c in per_term.items()
                ),
                key=lambda d: term_date(terms[d["term_id"]]) if d["term_id"] in terms else date.min,
            )
            seen_terms = sum(1 for d in term_rows if int(d["pos"] or 0))
            best_one = max((int(d["pos"] or 0) for d in term_rows), default=0)
            conf = round(wilson_lower(support, total), 4)
            score = round(g.score.get(val, 0.0), 4)
            proposal = _proposal(attr, val, tagged)
            enough = (seen_terms >= MIN_TERMS and support >= MIN_TERM_SUPPORT) or best_one >= MIN_ONE_TERM
            is_cross = cross.get((st, sk, attr, val), False)
            vt = _value_text(attr, val, rooms)
            computed[(st, sk, attr, val)] = {
                "score": score,
                "support": support,
                "total": total,
                "terms_count": seen_terms,
                "confidence": conf,
                "suggestible": bool(proposal) and score > 0 and enough and conf >= MIN_CONFIDENCE,
                "active": True,
                "proposal": proposal,
                "explanation": {
                    **explanation(attr, vt, support, total, term_rows, is_cross),
                    "claim_tr": _claim(vt)["tr"],
                    "claim_en": _claim(vt)["en"],
                },
                "evidence": {
                    "terms": term_rows,
                    "kinds": dict(g.kinds.get(val, {})),
                    "request_ids": sorted(g.requests.get(val, set()))[:50],
                    "cross_season": is_cross,
                    "value_label": {"tr": vt["tr"], "en": vt["en"]},
                },
                "computed_at": now,
            }

    fields = tuple(k for k in next(iter(computed.values()), {}) if k != "computed_at")
    cols = [getattr(LearnedPrior, k) for k in fields]
    q_old = select(
        LearnedPrior.id,
        LearnedPrior.subject_type,
        LearnedPrior.subject_key,
        LearnedPrior.attribute,
        LearnedPrior.value,
        LearnedPrior.active,
        LearnedPrior.suggestible,
        *cols,
    ).where(LearnedPrior.term_id == term_id)
    existing: dict[tuple[str, str, str, str], tuple[int, bool, bool, dict[str, Any]]] = {}
    for row in (await session.execute(q_old)).all():
        existing[(row[1], row[2], row[3], row[4])] = (row[0], row[5], row[6], dict(zip(fields, row[7:], strict=True)))
    fresh_rows: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for key, data in computed.items():
        old = existing.get(key)
        if old is None:
            fresh_rows.append(
                {
                    "term_id": term_id,
                    "subject_type": key[0],
                    "subject_key": key[1],
                    "attribute": key[2],
                    "value": key[3],
                    **data,
                }
            )
        elif any(old[3].get(k) != data[k] for k in fields):
            changed.append({"id": old[0], **data})
    for key, (pid, active, suggestible, _) in existing.items():
        if key not in computed and (active or suggestible):
            changed.append({"id": pid, "active": False, "suggestible": False, "computed_at": now})
    # bulk executemany by primary key (thousands of priors change at once after a reset or a new import)
    for chunk in range(0, len(changed), 2000):
        await session.execute(update(LearnedPrior), changed[chunk : chunk + 2000])
    for chunk in range(0, len(fresh_rows), 2000):
        await session.execute(insert(LearnedPrior), fresh_rows[chunk : chunk + 2000])
    await session.flush()
    return len(computed)


# ------------------------------------------------------------------------------------------------ targets


@dataclass
class _Targets:
    """Meeting requests of the target term, per subject, with what they already ask for."""

    by_subject: dict[tuple[str, str], list[MeetingRequest]] = field(default_factory=lambda: defaultdict(list))
    enrolment: dict[int, int] = field(default_factory=dict)


async def _targets(session: AsyncSession, term_id: int) -> _Targets:
    out = _Targets()
    q = (
        select(MeetingRequest, Section)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(
            Section.term_id == term_id,
            Section.archived.is_(False),
            MeetingRequest.archived.is_(False),
            MeetingRequest.needs_room.is_(True),
        )
        .order_by(MeetingRequest.id)
    )
    rows = (await session.execute(q)).all()
    sections = {sec.id for _, sec in rows}
    people: dict[int, list[int]] = defaultdict(list)
    if sections:
        for si in (
            await session.execute(
                select(SectionInstructor).where(
                    SectionInstructor.section_id.in_(sections), SectionInstructor.role == "PRIMARY"
                )
            )
        ).scalars():
            people[si.section_id].append(si.instructor_id)
    users = {
        i.id: i.user_id
        for i in (await session.execute(select(Instructor).where(Instructor.user_id.is_not(None)))).scalars()
    }
    for mr, sec in rows:
        out.enrolment[mr.id] = int(sec.enrolment or 0)
        keys = [("course", str(sec.course_id)), ("section", str(sec.id))]
        if sec.program_id is not None:
            keys.append(("program", str(sec.program_id)))
        for iid in people.get(sec.id, []):
            keys.append(("instructor", str(iid)))
            if users.get(iid):
                keys.append(("user", str(users[iid])))
        for k in keys:
            out.by_subject[k].append(mr)
    return out


def _explicit(mr: MeetingRequest, attribute: str) -> bool:
    """The class already says what it wants (an explicit request always wins over a learned habit)."""
    if attribute in ("room", "building", "tag"):
        return bool(mr.requested_room_ids or mr.definitive_room_ids or mr.requested_building)
    if attribute == "period":
        return mr.start_period is not None and not mr.flexible_day
    return True


# ------------------------------------------------------------------------------------------------ read model


async def _subject_labels(
    session: AsyncSession, keys: Iterable[tuple[str, str]]
) -> dict[tuple[str, str], dict[str, Any]]:
    """Display labels, rendered at read time from the FKs (names are never stored with the learned data)."""
    wanted: dict[str, set[int]] = defaultdict(set)
    for st, sk in keys:
        if sk.isdigit():
            wanted[st].add(int(sk))
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if wanted.get("course"):
        for c in (await session.execute(select(Course).where(Course.id.in_(wanted["course"])))).scalars():
            out[("course", str(c.id))] = {"label": c.display_code, "safe": c.display_code}
    if wanted.get("section"):
        q = select(Section.id, Section.label, Course.display_code).join(Course, Course.id == Section.course_id)
        for sid, label, code in (await session.execute(q.where(Section.id.in_(wanted["section"])))).all():
            text = f"{code} §{label}" if label else code
            out[("section", str(sid))] = {"label": text, "safe": text}
    if wanted.get("program"):
        for p in (await session.execute(select(Program).where(Program.id.in_(wanted["program"])))).scalars():
            out[("program", str(p.id))] = {"label": p.name, "safe": p.name}
    if wanted.get("instructor"):
        for i in (await session.execute(select(Instructor).where(Instructor.id.in_(wanted["instructor"])))).scalars():
            name = " ".join(x for x in (i.title, i.full_name) if x)
            out[("instructor", str(i.id))] = {"label": name, "safe": f"öğretim elemanı #{i.id}"}
    if wanted.get("user"):
        for u in (await session.execute(select(User).where(User.id.in_(wanted["user"])))).scalars():
            out[("user", str(u.id))] = {"label": u.full_name or f"#{u.id}", "safe": f"kullanıcı #{u.id}"}
    return out


def _fill(text: str, subject: str) -> str:
    return text.replace("{subject}", subject)


async def _feedback_state(session: AsyncSession, term_id: int) -> dict[tuple[str, str, str, str], SuggestionFeedback]:
    rows = (
        await session.execute(
            select(SuggestionFeedback)
            .where(SuggestionFeedback.term_id == term_id, SuggestionFeedback.reset_id.is_(None))
            .order_by(SuggestionFeedback.id)
        )
    ).scalars()
    return {(f.subject_type, f.subject_key, f.attribute, f.value): f for f in rows}  # latest decision wins


async def _snooze_active(session: AsyncSession, fb: SuggestionFeedback, now: datetime) -> bool:
    if fb.snooze_mode == "next_term":
        return True
    if fb.snooze_mode == "P7D":
        return fb.snoozed_until is not None and fb.snoozed_until > now
    later = (
        await session.execute(
            select(func.count()).where(ScheduleRun.term_id == fb.term_id, ScheduleRun.created_at > fb.created_at)
        )
    ).scalar_one()
    return later == 0


def _subject_filter(
    person_id: int | None, course_id: int | None, user_of: Mapping[int, int]
) -> set[tuple[str, str]] | None:
    if person_id is None and course_id is None:
        return None
    keys: set[tuple[str, str]] = set()
    if person_id is not None:
        keys.add(("instructor", str(person_id)))
        if person_id in user_of:
            keys.add(("user", str(user_of[person_id])))
    if course_id is not None:
        keys.add(("course", str(course_id)))
    return keys


async def suggestions(
    session: AsyncSession,
    term_id: int,
    *,
    person_id: int | None = None,
    course_id: int | None = None,
    state: str = "open",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Suggestions for ``term_id`` (``state``: open | accepted | dismissed | snoozed | hidden | all)."""
    if await session.get(Term, term_id) is None:
        raise LearningError(404, "term not found")
    await ensure_priors(session, term_id)
    user_of = {
        i.id: i.user_id
        for i in (await session.execute(select(Instructor).where(Instructor.user_id.is_not(None)))).scalars()
        if i.user_id is not None
    }
    wanted = _subject_filter(person_id, course_id, user_of)
    if wanted is not None and course_id is not None:  # the course's sections too
        q_sec = select(Section.id).where(Section.term_id == term_id, Section.course_id == course_id)
        wanted |= {("section", str(s)) for s in (await session.execute(q_sec)).scalars()}
    feedback = await _feedback_state(session, term_id)
    q = select(LearnedPrior).where(LearnedPrior.term_id == term_id, LearnedPrior.active.is_(True))
    # suggested priors, plus decided ones (a dismissal lowers the score below the threshold: History still lists it)
    priors = [
        p
        for p in (await session.execute(q)).scalars()
        if (p.suggestible or (p.subject_type, p.subject_key, p.attribute, p.value) in feedback)
        and (wanted is None or (p.subject_type, p.subject_key) in wanted)
    ]
    targets = await _targets(session, term_id)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    labels = await _subject_labels(session, {(p.subject_type, p.subject_key) for p in priors})
    now = utcnow()
    out: list[dict[str, Any]] = []
    for p in sorted(priors, key=lambda p: (-p.confidence, -p.score, p.id)):
        item = _render(p, targets, rooms, labels)
        fb = feedback.get((p.subject_type, p.subject_key, p.attribute, p.value))
        if fb is not None:
            if fb.action == "ACCEPT":
                item["state"], item["constraint_id"] = "accepted", fb.constraint_id
            elif fb.action == "REJECT":
                item["state"] = "dismissed"
            elif fb.action == "SNOOZE" and await _snooze_active(session, fb, now):
                item["state"], item["snoozed_until"] = "snoozed", fb.snoozed_until
                item["snooze_mode"] = fb.snooze_mode
            if fb.action in ("ACCEPT", "REJECT") or item["state"] == "snoozed":
                item["decided_at"], item["decided_by"] = fb.created_at, fb.actor_id
        if state != "all" and item["state"] != state:
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _render(
    p: LearnedPrior,
    targets: _Targets,
    rooms: Mapping[int, Room],
    labels: Mapping[tuple[str, str], Mapping[str, Any]],
    weight: int = LEARNED_WEIGHT,
) -> dict[str, Any]:
    label = labels.get((p.subject_type, p.subject_key), {"label": f"#{p.subject_key}", "safe": f"#{p.subject_key}"})
    reqs = targets.by_subject.get((p.subject_type, p.subject_key), [])
    free = [mr for mr in reqs if not _explicit(mr, p.attribute)]
    state, why = "open", None
    if not reqs:
        state, why = "hidden", "no_classes_this_term"
    elif not free:
        state, why = "hidden", "explicit_request_wins"
    elif p.attribute == "room" and p.value.isdigit():
        room = rooms.get(int(p.value))
        need = max((targets.enrolment.get(mr.id, 0) for mr in free), default=0)
        if room is None or not room.is_bookable:
            state, why = "hidden", "room_unavailable"
        elif room.capacity and need > room.capacity:
            state, why = "hidden", "room_too_small"
    expl = p.explanation or {}
    subj = str(label["label"])
    proposal = dict(p.proposal or {})
    params = {**dict(proposal.get("params") or {}), "event_ids": [mr.id for mr in free]}
    lvl = level_of(p.confidence)
    return {
        "id": p.id,
        "term_id": p.term_id,
        "subject": {
            "type": p.subject_type,
            "id": int(p.subject_key) if p.subject_key.isdigit() else p.subject_key,
            "label": subj,
        },
        "attribute": p.attribute,
        "value": p.value,
        "value_label": (p.evidence or {}).get("value_label"),
        "claim": {"tr": _fill(str(expl.get("claim_tr", "")), subj), "en": _fill(str(expl.get("claim_en", "")), subj)},
        "explanation": {"tr": _fill(str(expl.get("tr", "")), subj), "en": _fill(str(expl.get("en", "")), subj)},
        "if_accepted": if_accepted(weight),
        "proposal": {"kind": proposal.get("kind"), "params": params, "hardness": "soft", "weight": weight},
        "support": {"rows": p.support, "total": p.total, "seen_terms": p.terms_count},
        "score": p.score,
        "confidence": p.confidence,
        "level": lvl,
        "cross_season": bool((p.evidence or {}).get("cross_season")),
        "evidence": p.evidence or {},
        "impact": {
            "request_ids": [mr.id for mr in free],
            "covered_request_ids": [mr.id for mr in reqs if mr not in free],
        },
        "state": state,
        "hidden_reason": why,
        "snoozed_until": None,
        "snooze_mode": None,
        "constraint_id": None,
        "decided_at": None,
        "decided_by": None,
    }


async def priors_for(
    session: AsyncSession, term_id: int, subject_type: str | None = None, subject_key: str | None = None
) -> list[dict[str, Any]]:
    """All active priors (suggested or not) of a subject: the evidence view behind the cards."""
    if await session.get(Term, term_id) is None:
        raise LearningError(404, "term not found")
    await ensure_priors(session, term_id)
    q = select(LearnedPrior).where(LearnedPrior.term_id == term_id, LearnedPrior.active.is_(True))
    if subject_type:
        q = q.where(LearnedPrior.subject_type == subject_type)
    if subject_key:
        q = q.where(LearnedPrior.subject_key == subject_key)
    rows = list((await session.execute(q.order_by(LearnedPrior.score.desc(), LearnedPrior.id).limit(500))).scalars())
    labels = await _subject_labels(session, {(p.subject_type, p.subject_key) for p in rows})
    out = []
    for p in rows:
        subj = str(labels.get((p.subject_type, p.subject_key), {"label": f"#{p.subject_key}"})["label"])
        expl = p.explanation or {}
        out.append(
            {
                "id": p.id,
                "subject": {"type": p.subject_type, "id": p.subject_key, "label": subj},
                "attribute": p.attribute,
                "value": p.value,
                "value_label": (p.evidence or {}).get("value_label"),
                "score": p.score,
                "support": p.support,
                "total": p.total,
                "terms_count": p.terms_count,
                "confidence": p.confidence,
                "suggestible": p.suggestible,
                "explanation": {"tr": _fill(str(expl.get("tr", "")), subj), "en": _fill(str(expl.get("en", "")), subj)},
                "evidence": p.evidence or {},
            }
        )
    return out


# ------------------------------------------------------------------------------------------------ decisions


def learned_rule_issues(kind: str, params: Mapping[str, Any], hardness: str, weight: int) -> list[str]:
    """Why a learned rule may not be written: the allowlist, soft only, weight 1..5, targeted, and the hard-rule
    integrity guard (``constraint_guard``: no structural waiver from LEARNED, ever) plus the AI layer's per-source
    policy (``app.ai.catalog.source_policy_issues``)."""
    from app.ai.catalog import source_policy_issues

    issues: list[str] = []
    if kind not in LEARNED_KINDS:
        issues.append(f"learned suggestions may only become {', '.join(sorted(LEARNED_KINDS))}; not '{kind}'")
    if hardness != "soft":
        issues.append("learned suggestions are soft preferences only")
    if not 1 <= int(weight) <= MAX_WEIGHT:
        issues.append(f"learned suggestions carry weight 1..{MAX_WEIGHT}")
    if not constraint_guard.is_targeted_params(params):
        issues.append("a learned rule must name its classes (event_ids)")
    issues += constraint_guard.guard_rule(kind, params, hardness, source="LEARNED", may_waive=False, reason=None)
    issues += source_policy_issues(kind, dict(params), hardness, "LEARNED", weight=weight)
    return list(dict.fromkeys(issues))


async def _prior(session: AsyncSession, prior_id: int) -> LearnedPrior:
    p = await session.get(LearnedPrior, prior_id)
    if p is None or not p.active:
        raise LearningError(404, "suggestion not found")
    return p


async def _render_one(session: AsyncSession, p: LearnedPrior, weight: int = LEARNED_WEIGHT) -> dict[str, Any]:
    targets = await _targets(session, p.term_id)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    labels = await _subject_labels(session, [(p.subject_type, p.subject_key)])
    return _render(p, targets, rooms, labels, weight)


async def _decision_obs(session: AsyncSession, p: LearnedPrior, fb: SuggestionFeedback, kind: str, actor: User) -> None:
    sign, weight = SIGNALS[kind]
    await session.execute(
        insert(LearnedObservation),
        [
            {
                "ts": fb.created_at,
                "created_at": utcnow(),
                "term_id": p.term_id,
                "kind": kind,
                "subject_type": p.subject_type,
                "subject_key": p.subject_key,
                "attribute": p.attribute,
                "value": p.value,
                "sign": sign,
                "weight": weight,
                "source_table": "suggestion_feedback",
                "source_id": fb.id,
                "actor_id": actor.id,
                "detail": {"prior_id": p.id},
            }
        ],
    )


def _scope_of(p: LearnedPrior) -> dict[str, Any]:
    return {
        "term_id": p.term_id,
        "subject_type": p.subject_type,
        "subject_key": p.subject_key,
        "attribute": p.attribute,
        "value": p.value,
    }


async def accept(
    session: AsyncSession, prior_id: int, actor: User, *, weight: int | None = None, kind: str | None = None
) -> dict[str, Any]:
    """One soft, targeted LEARNED rule for the term's classes the suggestion names (never anything else)."""
    p = await _prior(session, prior_id)
    w = LEARNED_WEIGHT if weight is None else int(weight)
    item = await _render_one(session, p, w)
    if item["state"] != "open":
        raise LearningError(409, f"the suggestion cannot be accepted ({item['hidden_reason'] or item['state']})")
    fb_prev = (await _feedback_state(session, p.term_id)).get((p.subject_type, p.subject_key, p.attribute, p.value))
    if fb_prev is not None and fb_prev.action == "ACCEPT":
        raise LearningError(409, "the suggestion was already accepted")
    proposal = item["proposal"]
    rule_kind = kind or proposal["kind"]
    params: dict[str, Any] = dict(proposal["params"])
    if rule_kind != proposal["kind"]:
        if rule_kind == "same_room_across_weeks" and p.attribute in ("room", "building"):
            params = {"event_ids": params["event_ids"]}
        elif rule_kind in LEARNED_KINDS:
            raise LearningError(422, f"'{rule_kind}' does not fit a {p.attribute} suggestion")
    issues = learned_rule_issues(rule_kind, params, "soft", w)
    if issues:
        raise LearningError(422, "; ".join(issues))
    labels = await _subject_labels(session, [(p.subject_type, p.subject_key)])
    safe = str(labels.get((p.subject_type, p.subject_key), {"safe": f"#{p.subject_key}"})["safe"])
    expl = p.explanation or {}
    stored = {"tr": _fill(str(expl.get("tr", "")), safe), "en": _fill(str(expl.get("en", "")), safe)}
    row = ConstraintRow(
        term_id=p.term_id,
        run_id=None,
        kind=rule_kind,
        params=params,
        hardness="soft",
        weight=w,
        source="LEARNED",
        source_ref={
            "prior_id": p.id,
            "explanation": stored,
            "subject": {"type": p.subject_type, "id": p.subject_key},
            "attribute": p.attribute,
            "value": p.value,
            "support": {"rows": p.support, "total": p.total, "seen_terms": p.terms_count},
            "confidence": p.confidence,
            "request_ids": (p.evidence or {}).get("request_ids", [])[:20],
        },
        nl_text=_fill(str(expl.get("claim_tr", "")), safe),
        enabled=True,
        created_by=actor.id,
    )
    session.add(row)
    await session.flush()
    fb = SuggestionFeedback(**_scope_of(p), prior_id=p.id, action="ACCEPT", constraint_id=row.id, actor_id=actor.id)
    session.add(fb)
    await session.flush()
    await _decision_obs(session, p, fb, "suggestion_accepted", actor)
    await publish_event(
        session,
        "suggestion.accept",
        "suggestion",
        p.id,
        after={
            "constraint_id": row.id,
            "kind": rule_kind,
            "weight": w,
            "event_ids": params["event_ids"],
            **_scope_of(p),
        },
        actor=actor,
        term_id=p.term_id,
    )
    return {"constraint_id": row.id, "kind": rule_kind, "params": params, "weight": w, "hardness": "soft"}


async def reject(session: AsyncSession, prior_id: int, actor: User, *, reason: str | None = None) -> dict[str, Any]:
    """-3 evidence and the suggestion stays hidden for its scope and term (``Bir daha önerme``)."""
    p = await _prior(session, prior_id)
    fb = SuggestionFeedback(**_scope_of(p), prior_id=p.id, action="REJECT", reason=(reason or None), actor_id=actor.id)
    session.add(fb)
    await session.flush()
    await _decision_obs(session, p, fb, "suggestion_rejected", actor)
    await publish_event(
        session,
        "suggestion.dismiss",
        "suggestion",
        p.id,
        after=_scope_of(p),
        actor=actor,
        reason=reason,
        term_id=p.term_id,
    )
    return {"id": p.id, "state": "dismissed"}


async def snooze(session: AsyncSession, prior_id: int, actor: User, *, until: str) -> dict[str, Any]:
    if until not in SNOOZE_MODES:
        raise LearningError(422, f"until must be one of {', '.join(SNOOZE_MODES)}")
    p = await _prior(session, prior_id)
    now = utcnow()
    fb = SuggestionFeedback(
        **_scope_of(p),
        prior_id=p.id,
        action="SNOOZE",
        snooze_mode=until,
        snoozed_until=now + timedelta(days=7) if until == "P7D" else None,
        actor_id=actor.id,
        created_at=now,
    )
    session.add(fb)
    await session.flush()
    await publish_event(
        session,
        "suggestion.snooze",
        "suggestion",
        p.id,
        after={**_scope_of(p), "until": until},
        actor=actor,
        term_id=p.term_id,
    )
    return {"id": p.id, "state": "snoozed", "until": until, "snoozed_until": fb.snoozed_until}


# ------------------------------------------------------------------------------------------------ memory


async def _person_keys(session: AsyncSession, instructor_id: int) -> list[tuple[str, str]]:
    ins = await session.get(Instructor, instructor_id)
    if ins is None:
        raise LearningError(404, "instructor not found")
    keys = [("instructor", str(ins.id))]
    if ins.user_id is not None:
        keys.append(("user", str(ins.user_id)))
    return keys


def _subject_clause(model: Any, keys: list[tuple[str, str]]) -> Any:
    from sqlalchemy import and_, or_

    return or_(*(and_(model.subject_type == st, model.subject_key == sk) for st, sk in keys))


async def _scope(session: AsyncSession, scope: str, value: Any) -> tuple[str | None, Any, Any]:
    """(scope_value, observation filter, feedback filter) of a reset scope."""
    if scope == "all":
        return None, LearnedObservation.reset_id.is_(None), SuggestionFeedback.action.in_(("REJECT", "SNOOZE"))
    if value is None or not str(value).strip().isdigit():
        raise LearningError(422, f"scope '{scope}' needs a numeric value")
    vid = int(str(value).strip())
    if scope == "term":
        if await session.get(Term, vid) is None:
            raise LearningError(404, "term not found")
        # a term reset excludes that term's evidence; dismissals stay (they are decisions, not learned data)
        return str(vid), LearnedObservation.term_id == vid, None
    if scope == "person":
        keys = await _person_keys(session, vid)
        return (
            str(vid),
            _subject_clause(LearnedObservation, keys),
            _subject_clause(SuggestionFeedback, keys) & SuggestionFeedback.action.in_(("REJECT", "SNOOZE")),
        )
    raise LearningError(422, "scope must be person, term or all")


async def reset(session: AsyncSession, actor: User, *, scope: str, value: Any, reason: str) -> dict[str, Any]:
    """Hide the scope's learned evidence and dismissals (undo for 30 days, then purged)."""
    if len((reason or "").strip()) < 3:
        raise LearningError(422, "a reset needs a written reason")
    scope_value, obs_where, fb_where = await _scope(session, scope, value)
    now = utcnow()
    rs = LearningReset(
        kind="RESET",
        scope_type=scope,
        scope_value=scope_value,
        reason=reason.strip(),
        actor_id=actor.id,
        created_at=now,
        watermark=now,
        expires_at=now + timedelta(days=UNDO_DAYS),
        counts={},
    )
    session.add(rs)
    await session.flush()
    before_open = await _open_count(session, scope, scope_value)
    n_obs = await _count(
        session,
        update(LearnedObservation)
        .where(obs_where, LearnedObservation.reset_id.is_(None))
        .values(reset_id=rs.id)
        .execution_options(synchronize_session=False),
    )
    n_fb = 0
    if fb_where is not None:
        n_fb = await _count(
            session,
            update(SuggestionFeedback)
            .where(fb_where, SuggestionFeedback.reset_id.is_(None))
            .values(reset_id=rs.id)
            .execution_options(synchronize_session=False),
        )
    rs.counts = {"observations": int(n_obs or 0), "feedback": int(n_fb or 0), "suggestions": before_open}
    _forget()
    await publish_event(
        session,
        "learning.reset",
        "learning_reset",
        rs.id,
        after={"scope": scope, "subject": scope_value, "counts": rs.counts, "undo_until": rs.expires_at.isoformat()},
        actor=actor,
        reason=rs.reason,
        term_id=int(scope_value) if scope == "term" and scope_value else None,
    )
    return reset_out(rs)


async def _open_count(session: AsyncSession, scope: str, scope_value: str | None) -> int:
    """Suggestible priors the reset touches (all target terms), for the dialog and the audit row."""
    q = select(func.count()).where(LearnedPrior.active.is_(True), LearnedPrior.suggestible.is_(True))
    if scope == "person" and scope_value is not None:
        keys = await _person_keys(session, int(scope_value))
        q = q.where(_subject_clause(LearnedPrior, keys))
    return int((await session.execute(q)).scalar_one())


def reset_out(rs: LearningReset, now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    undoable = rs.kind == "RESET" and rs.undone_at is None and rs.purged_at is None and rs.expires_at > now
    return {
        "id": rs.id,
        "reset_id": rs.id,
        "kind": rs.kind,
        "scope": rs.scope_type,
        "value": rs.scope_value,
        "reason": rs.reason,
        "actor_id": rs.actor_id,
        "created_at": rs.created_at,
        "undo_until": rs.expires_at,
        "days_left": max(0, (rs.expires_at - now).days) if undoable else 0,
        "undoable": undoable,
        "undone_at": rs.undone_at,
        "purged_at": rs.purged_at,
        "counts": rs.counts or {},
    }


async def list_resets(session: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
    rows = (await session.execute(select(LearningReset).order_by(LearningReset.id.desc()).limit(limit))).scalars()
    now = utcnow()
    return [reset_out(r, now) for r in rows]


async def undo_reset(
    session: AsyncSession, reset_id: int, actor: User, *, now: datetime | None = None
) -> dict[str, Any]:
    rs = await session.get(LearningReset, reset_id)
    if rs is None:
        raise LearningError(404, "reset not found")
    now = now or utcnow()
    if rs.kind != "RESET":
        raise LearningError(409, "a KVKK erasure cannot be undone")
    if rs.undone_at is not None:
        raise LearningError(409, "the reset was already undone")
    if rs.purged_at is not None or rs.expires_at <= now:
        raise LearningError(409, f"the undo window ended on {rs.expires_at.date().isoformat()}")
    n_obs = await _count(
        session,
        update(LearnedObservation)
        .where(LearnedObservation.reset_id == rs.id)
        .values(reset_id=None)
        .execution_options(synchronize_session=False),
    )
    n_fb = await _count(
        session,
        update(SuggestionFeedback)
        .where(SuggestionFeedback.reset_id == rs.id)
        .values(reset_id=None)
        .execution_options(synchronize_session=False),
    )
    rs.undone_at, rs.undone_by = now, actor.id
    _forget()
    await publish_event(
        session,
        "learning.reset.undo",
        "learning_reset",
        rs.id,
        after={
            "scope": rs.scope_type,
            "subject": rs.scope_value,
            "restored": {"observations": n_obs, "feedback": n_fb},
        },
        actor=actor,
    )
    return reset_out(rs, now)


async def purge_expired(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Hard-delete the rows of resets whose undo window ended (daily job). The reset row and its audit entry stay
    (no personal content beyond the subject id), so the watermark keeps the evidence from being learned again."""
    now = now or utcnow()
    due = list(
        (
            await session.execute(
                select(LearningReset).where(
                    LearningReset.kind == "RESET",
                    LearningReset.undone_at.is_(None),
                    LearningReset.purged_at.is_(None),
                    LearningReset.expires_at <= now,
                )
            )
        ).scalars()
    )
    totals = {"resets": 0, "observations": 0, "feedback": 0}
    for rs in due:
        n_obs = await _count(session, delete(LearnedObservation).where(LearnedObservation.reset_id == rs.id))
        n_fb = await _count(session, delete(SuggestionFeedback).where(SuggestionFeedback.reset_id == rs.id))
        rs.purged_at = now
        totals["resets"] += 1
        totals["observations"] += int(n_obs or 0)
        totals["feedback"] += int(n_fb or 0)
        await publish_event(
            session,
            "learning.purge",
            "learning_reset",
            rs.id,
            after={"scope": rs.scope_type, "subject": rs.scope_value, "observations": n_obs, "feedback": n_fb},
        )
    if due:
        _forget()
    return totals


async def erase_person(session: AsyncSession, actor: User, *, instructor_id: int, reason: str) -> dict[str, Any]:
    """KVKK erasure of a person's learned memory: observations, dismissals and priors are deleted now (no undo
    window). Requests, runs, bookings and accepted rules are source data: erasing them is a separate flow."""
    if len((reason or "").strip()) < 3:
        raise LearningError(422, "an erasure needs a written reason")
    keys = await _person_keys(session, instructor_id)
    now = utcnow()
    rs = LearningReset(
        kind="ERASURE",
        scope_type="person",
        scope_value=str(instructor_id),
        reason=reason.strip(),
        actor_id=actor.id,
        created_at=now,
        watermark=now,
        expires_at=now,
        purged_at=now,
        counts={},
    )
    session.add(rs)
    await session.flush()
    n_obs = await _count(session, delete(LearnedObservation).where(_subject_clause(LearnedObservation, keys)))
    n_fb = await _count(session, delete(SuggestionFeedback).where(_subject_clause(SuggestionFeedback, keys)))
    n_pr = await _count(session, delete(LearnedPrior).where(_subject_clause(LearnedPrior, keys)))
    rs.counts = {"observations": int(n_obs or 0), "feedback": int(n_fb or 0), "priors": int(n_pr or 0)}
    _forget()
    await publish_event(
        session,
        "learning.erase",
        "learning_reset",
        rs.id,
        after={"scope": "person", "subject": str(instructor_id), "counts": rs.counts},
        actor=actor,
        reason=rs.reason,
    )
    return reset_out(rs, now)


async def memory_summary(session: AsyncSession, term_id: int | None = None) -> dict[str, Any]:
    terms = {t.id: t for t in (await session.execute(select(Term))).scalars()}
    per_term = dict(
        (
            await session.execute(
                select(LearnedObservation.term_id, func.count())
                .where(LearnedObservation.reset_id.is_(None))
                .group_by(LearnedObservation.term_id)
            )
        ).all()
    )
    hidden = (await session.execute(select(func.count()).where(LearnedObservation.reset_id.is_not(None)))).scalar_one()
    out: dict[str, Any] = {
        "terms": [
            {"term_id": tid, "code": terms[tid].code if tid in terms else None, "observations": int(c)}
            for tid, c in sorted(per_term.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))
        ],
        "observations": int(sum(per_term.values())),
        "hidden_by_reset": int(hidden),
    }
    if term_id is not None:
        items = await suggestions(session, term_id, state="all", limit=100_000)
        counts: dict[str, int] = defaultdict(int)
        for it in items:
            counts[it["state"]] += 1
        out.update({"term_id": term_id, "suggestions": dict(counts)})
    return out


async def refresh(session: AsyncSession, term_id: int | None = None) -> dict[str, Any]:
    from app.services import learning_extract

    rep = await learning_extract.extract(session)
    out: dict[str, Any] = {"extract": rep.as_dict()}
    if term_id is not None:
        out["priors"] = await recompute_priors(session, term_id)
        _forget(term_id)
    return out


# ------------------------------------------------------------------------------------------------ daily purge job

PURGE_INTERVAL_S = 24 * 3600.0
_task: asyncio.Task[None] | None = None


async def purge_once() -> dict[str, int]:
    from app.core.db import get_session_factory

    async with get_session_factory()() as session:
        out = await purge_expired(session)
        await session.commit()
    return out


async def _loop(interval: float) -> None:
    while True:
        try:
            out = await purge_once()
            if out.get("resets"):
                log.info("learning purge: %s", out)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failing purge must never stop the loop or the app
            log.exception("learning purge failed")
        await asyncio.sleep(interval)


def start_purge_job(interval: float = PURGE_INTERVAL_S) -> None:
    """Started from ``app.main`` lifespan next to ``approvals_sweeper.start()`` (not in the test environment)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(interval), name="learning-purge")


async def stop_purge_job() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None


__all__ = [
    "BANDS",
    "LEARNED_KINDS",
    "LEARNED_WEIGHT",
    "LearningError",
    "accept",
    "ensure_priors",
    "erase_person",
    "explanation",
    "learned_rule_issues",
    "list_resets",
    "locative",
    "memory_summary",
    "priors_for",
    "purge_expired",
    "purge_once",
    "recompute_priors",
    "refresh",
    "reject",
    "reset",
    "snooze",
    "start_purge_job",
    "stop_purge_job",
    "suggestions",
    "undo_reset",
    "wilson_lower",
]
