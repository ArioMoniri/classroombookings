"""Invigilator assignment for exam runs (docs/features.yml "invigilator assignment").

Data in, from the database only (no demo data):

* the exam run's placements (``assignments`` of an EXAM run): one :class:`~app.solver.invigilation.ExamSlot` per exam
  request, its instructors read from the exam list's instructor column (split into people, canonical names);
* the pool: the instructors named on the run's exams (``instructor_pool=exam_instructors``, the default), every
  instructor (``all``) or none (``none``), plus the active ``invigilator_pool`` rows of the term (or of every term:
  ``term_id`` null) - staff, research assistants; a pool row linked to an instructor carries that instructor's rules
  (unavailability, limits, load factor) and ``active=false`` takes the instructor out;
* busy times: teaching from every published course run whose term calendar covers an exam date, the person's own
  bookings that day (``Instructor.user_id``), the pool row's unavailability.

A term whose calendar has no dates, or no published course run around the exam dates, cannot tell who teaches when:
the plan then carries a ``teaching_unchecked`` warning (the rule is never dropped silently).

Runs (``invigilation_plans``) go through the job queue (one CP-SAT worker, fixed seed, deterministic budget). A
re-run is a child plan: its locked duties are kept, the parent's duties are the stability target. Every mutation is
audited (``invigilation.*`` / ``invigilator.*`` actions).
"""

from __future__ import annotations

import asyncio
import csv
import functools
import io
import logging
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers import normalize as n
from app.models import (
    Assignment,
    Booking,
    ExamRequest,
    Instructor,
    InvigilationDuty,
    InvigilationPlan,
    InvigilatorPoolMember,
    Room,
    ScheduleRun,
    Term,
    User,
    Week,
)
from app.models.invigilation import POOL_KINDS
from app.services import audit
from app.services.calendar import week_index_for_date
from app.services.calendar_views import clock
from app.solver import invigilation as inv

log = logging.getLogger(__name__)

#: exam runs whose timetable can be staffed
EXAM_STATUSES = frozenset({"OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"})
FINISHED = frozenset({"OPTIMAL", "FEASIBLE", "INFEASIBLE", "FAILED"})
OWN_EXAM = ("prefer", "allow", "forbid")
INSTRUCTOR_POOL = ("exam_instructors", "all", "none")
DEFAULTS: dict[str, Any] = {
    "students_per_invigilator": 40,
    "min_per_room": 1,
    "max_per_room": None,
    "own_exam": "prefer",
    "instructor_pool": "exam_instructors",
    "max_per_day": 3,
    "min_rest": 0,
    "time_limit_s": 20.0,
    "seed": 0,
    "weights": {},
}
#: a QUEUED / RUNNING plan with no live job after this long is reported as interrupted
STALE_AFTER = timedelta(minutes=10)


class PlanError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _ints(values: Iterable[Any] | None) -> list[int]:
    out: list[int] = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def person_keys(text: str | None) -> list[tuple[str, str]]:
    """(canonical name, display name) of every person in an exam list's instructor cell (non-person text skipped)."""
    return list(_person_keys(text))


@functools.lru_cache(maxsize=8192)
def _person_keys(text: str | None) -> tuple[tuple[str, str], ...]:
    # pure function of the cell text; the Turkish name normalisation is the costly part of building a plan's input
    # (~0.6 s for the Final's 926 exam rows), and every candidates / reassign call rebuilds that input
    out: list[tuple[str, str]] = []
    for raw in n.split_person_names(text):
        if n.non_person_reason(raw) is not None:
            continue
        p = n.canon_person_name(raw)
        if p is not None and p.canonical and p.canonical not in {k for k, _ in out}:
            out.append((p.canonical, p.full_name))
    return tuple(out)


# ------------------------------------------------------------------------------------------- exam people -> instructors

_TITLE_KEYS = frozenset(n.fold(k) for k in n._TITLE_TOKENS)


def name_tokens(text: str | None) -> tuple[str, ...]:
    """The comparable words of a person's name: folded (Turkish i, no diacritics), leading titles dropped (also
    abbreviations the importer does not know, "Öğ. Üy."), punctuation and number tokens ("#157") dropped; an
    initial stays one letter ("A. C. K." -> ``("a", "c", "k")``)."""
    raw = n.fold(text or "").split()
    # a leading title: a known title word, or an abbreviation of 2-5 letters written with a dot ("og.", "uy.")
    skip = 0
    while skip < len(raw) - 1:
        w = raw[skip]
        bare = w.rstrip(".")
        if bare in _TITLE_KEYS or (w.endswith(".") and 2 <= len(bare) <= 5 and bare.isalpha()):
            skip += 1
            continue
        break
    words = [t for w in raw[skip:] for t in re.split(r"[.\-’']+", w) if t]
    return tuple(t for t in (re.sub(r"[^a-z]", "", w) for w in words) if t)


@dataclass
class PeopleMatch:
    """How the exam list's people were found among the instructors (round-1 T-R1-42)."""

    #: instructor id -> the exam key it answers to (``ExamSlot.owner_keys``: the own-exam rule reads it)
    key_of: dict[int, str]
    exam_people: int
    matched: int
    by: dict[str, int]
    unmatched: list[str]
    ambiguous: list[str]


def match_exam_people(owners: Mapping[str, str], instructors: Iterable[Instructor]) -> PeopleMatch:
    """Exam-list people -> Instructor rows: the exact canonical name first (what the importer does), then the same
    words after folding (diacritics, dotless i, a title or a stray "#id" mask suffix), then the same initials
    ("A. C. K." for a list written in initials), then first + last name with a middle name left out. A tier only
    counts when exactly one instructor answers; two candidates are reported as ambiguous, never guessed."""
    ins = list(instructors)
    exact: dict[str, list[int]] = defaultdict(list)
    words: dict[tuple[str, ...], set[int]] = defaultdict(set)
    initials: dict[tuple[str, ...], set[int]] = defaultdict(set)
    toks: dict[int, tuple[str, ...]] = {}
    for i in ins:
        exact[i.canonical_name].append(i.id)
        for text in (i.canonical_name, i.full_name):
            t = name_tokens(text)
            if not t:
                continue
            words[t].add(i.id)
            initials[tuple(w[0] for w in t)].add(i.id)
            toks.setdefault(i.id, t)
    key_of: dict[int, str] = {}
    by: dict[str, int] = defaultdict(int)
    unmatched: list[str] = []
    ambiguous: list[str] = []
    for key, shown in sorted(owners.items()):
        t = name_tokens(key) or name_tokens(shown)
        tiers: list[tuple[str, set[int]]] = [("exact", set(exact.get(key, [])))]
        if t:
            tiers.append(("folded", words.get(t, set())))
            if all(len(w) == 1 for w in t):
                tiers.append(("initials", initials.get(t, set())))
            if len(t) >= 2:
                tiers.append(
                    (
                        "middle_name",
                        {
                            iid
                            for iid, it in toks.items()
                            if len(it) > len(t) and it[0] == t[0] and it[-1] == t[-1] and set(t) <= set(it)
                        },
                    )
                )
        hit: int | None = None
        clash = False
        for tier, ids in tiers:
            if len(ids) == 1:
                hit = next(iter(ids))
                by[tier] += 1
                break
            if len(ids) > 1:
                clash = True
                break
        if hit is None:
            (ambiguous if clash else unmatched).append(shown)
            continue
        key_of.setdefault(hit, key)
    matched = len(owners) - len(unmatched) - len(ambiguous)
    return PeopleMatch(key_of, len(owners), matched, dict(by), unmatched, ambiguous)


# ------------------------------------------------------------------------------------------- params


def clean_params(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """The run parameters with defaults; 422 on a value outside its range (nothing is guessed)."""
    p = {**DEFAULTS, **{k: v for k, v in (raw or {}).items() if v is not None}}
    unknown = set(raw or {}) - set(DEFAULTS)
    if unknown:
        raise PlanError(422, f"unknown parameter(s): {', '.join(sorted(unknown))}")

    def as_int(key: str, lo: int, hi: int, allow_none: bool = False) -> None:
        v = p.get(key)
        if v is None and allow_none:
            return
        try:
            iv = int(str(v))
        except (TypeError, ValueError) as exc:
            raise PlanError(422, f"{key} must be an integer") from exc
        if not lo <= iv <= hi:
            raise PlanError(422, f"{key} must be between {lo} and {hi}")
        p[key] = iv

    as_int("students_per_invigilator", 1, 1000)
    as_int("min_per_room", 0, 20)
    as_int("max_per_room", 1, 50, allow_none=True)
    as_int("max_per_day", 1, 12, allow_none=True)
    as_int("min_rest", 0, 6)
    as_int("seed", 0, 2**31 - 1)
    try:
        p["time_limit_s"] = float(p["time_limit_s"])
    except (TypeError, ValueError) as exc:
        raise PlanError(422, "time_limit_s must be a number") from exc
    if not 1.0 <= p["time_limit_s"] <= 600.0:
        raise PlanError(422, "time_limit_s must be between 1 and 600")
    if p["own_exam"] not in OWN_EXAM:
        raise PlanError(422, f"own_exam must be one of {', '.join(OWN_EXAM)}")
    if p["instructor_pool"] not in INSTRUCTOR_POOL:
        raise PlanError(422, f"instructor_pool must be one of {', '.join(INSTRUCTOR_POOL)}")
    w = p.get("weights") or {}
    if not isinstance(w, dict) or set(w) - set(inv.DEFAULT_WEIGHTS):
        raise PlanError(422, f"weights may only name {', '.join(inv.DEFAULT_WEIGHTS)}")
    for k, v in w.items():
        if not isinstance(v, int) or not 0 <= v <= 1000:
            raise PlanError(422, f"weight {k} must be an integer 0..1000")
    p["weights"] = dict(w)
    return p


# ------------------------------------------------------------------------------------------- pool


def pool_out(r: InvigilatorPoolMember) -> dict[str, Any]:
    return {
        "id": r.id,
        "term_id": r.term_id,
        "instructor_id": r.instructor_id,
        "full_name": r.full_name,
        "kind": r.kind,
        "max_duties": r.max_duties,
        "max_per_day": r.max_per_day,
        "load_factor": r.load_factor,
        "unavailable": list(r.unavailable or []),
        "active": bool(r.active),
        "notes": r.notes,
        "person_key": f"INS:{r.instructor_id}" if r.instructor_id else f"STAFF:{r.id}",
    }


def _check_unavailable(items: Any) -> list[dict[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise PlanError(422, "unavailable must be a list")
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            raise PlanError(422, "each unavailable entry is an object")
        e: dict[str, Any] = {}
        if it.get("date"):
            try:
                e["date"] = date.fromisoformat(str(it["date"])).isoformat()
            except ValueError as exc:
                raise PlanError(422, f"bad date {it['date']!r}") from exc
        elif it.get("day") is not None:
            if int(it["day"]) not in range(1, 8):
                raise PlanError(422, "day must be 1..7")
            e["day"] = int(it["day"])
        else:
            raise PlanError(422, "an unavailable entry needs a date or a day")
        sp, ep = it.get("start_period"), it.get("end_period")
        if (sp is None) != (ep is None):
            raise PlanError(422, "give both start_period and end_period, or neither (whole day)")
        if sp is not None:
            if not 1 <= int(str(sp)) <= int(str(ep)) <= 18:
                raise PlanError(422, "periods must satisfy 1 <= start_period <= end_period <= 18")
            e["start_period"], e["end_period"] = int(str(sp)), int(str(ep))
        if it.get("note"):
            e["note"] = str(it["note"])[:200]
        out.append(e)
    return out


async def list_pool(session: AsyncSession, term_id: int | None = None) -> list[dict[str, Any]]:
    q = select(InvigilatorPoolMember).order_by(InvigilatorPoolMember.full_name, InvigilatorPoolMember.id)
    if term_id is not None:
        q = q.where((InvigilatorPoolMember.term_id == term_id) | (InvigilatorPoolMember.term_id.is_(None)))
    return [pool_out(r) for r in (await session.execute(q)).scalars()]


async def save_pool_member(
    session: AsyncSession, body: Mapping[str, Any], actor: User, member_id: int | None = None
) -> dict[str, Any]:
    row: InvigilatorPoolMember | None
    if member_id is not None:
        row = await session.get(InvigilatorPoolMember, member_id)
        if row is None:
            raise PlanError(404, f"pool member {member_id} not found")
        before = pool_out(row)
    else:
        row, before = None, None
    data = dict(body)
    ins: Instructor | None = None
    if data.get("instructor_id") is not None:
        ins = await session.get(Instructor, int(data["instructor_id"]))
        if ins is None:
            raise PlanError(404, f"instructor {data['instructor_id']} not found")
    if data.get("term_id") is not None and await session.get(Term, int(data["term_id"])) is None:
        raise PlanError(404, f"term {data['term_id']} not found")
    name = str(data.get("full_name") or (ins.full_name if ins else "") or (row.full_name if row else "")).strip()
    if not name:
        raise PlanError(422, "full_name is required (or an instructor_id)")
    parsed = n.canon_person_name(name)
    kind = str(data.get("kind") or (row.kind if row else ("INSTRUCTOR" if ins else "STAFF"))).upper()
    if kind not in POOL_KINDS:
        raise PlanError(422, f"kind must be one of {', '.join(POOL_KINDS)}")
    lf_raw = data.get("load_factor")
    lf = int(str(lf_raw)) if lf_raw is not None else (row.load_factor if row else 100)
    if not 10 <= lf <= 500:
        raise PlanError(422, "load_factor must be between 10 and 500 (percent)")
    for key in ("max_duties", "max_per_day"):
        if data.get(key) is not None and not 0 <= int(data[key]) <= 200:
            raise PlanError(422, f"{key} must be between 0 and 200")
    if row is None:
        row = InvigilatorPoolMember(created_by=actor.id)
        session.add(row)
    row.full_name = name
    row.canonical_name = parsed.canonical if parsed else name.casefold()
    row.kind = kind
    row.load_factor = lf
    if "term_id" in data or member_id is None:
        row.term_id = int(data["term_id"]) if data.get("term_id") is not None else None
    if "instructor_id" in data or member_id is None:
        row.instructor_id = ins.id if ins else None
    for key in ("max_duties", "max_per_day"):
        if key in data or member_id is None:
            setattr(row, key, int(data[key]) if data.get(key) is not None else None)
    if "unavailable" in data or member_id is None:
        row.unavailable = _check_unavailable(data.get("unavailable"))
    if "active" in data or member_id is None:
        row.active = bool(data.get("active", True))
    if "notes" in data:
        row.notes = (str(data["notes"])[:2000] or None) if data["notes"] is not None else None
    row.updated_at = _now()
    await session.flush()
    after = pool_out(row)
    await audit.record(
        session,
        "invigilator.update" if before else "invigilator.create",
        "invigilator_pool",
        row.id,
        before=before,
        after=after,
        actor=actor,
        term_id=row.term_id,
    )
    await session.commit()
    return after


async def delete_pool_member(session: AsyncSession, member_id: int, actor: User) -> None:
    row = await session.get(InvigilatorPoolMember, member_id)
    if row is None:
        raise PlanError(404, f"pool member {member_id} not found")
    before = pool_out(row)
    await session.delete(row)
    await audit.record(
        session, "invigilator.delete", "invigilator_pool", member_id, before=before, actor=actor, term_id=row.term_id
    )
    await session.commit()


# ------------------------------------------------------------------------------------------- input


@dataclass
class Built:
    inp: inv.InvigilationInput
    exams: dict[int, ExamRequest]
    rooms: dict[int, Room]
    people: dict[str, dict[str, Any]]  # person id -> {name, instructor_id, staff_id, kind}
    warnings: list[dict[str, Any]] = field(default_factory=list)
    teaching_runs: list[int] = field(default_factory=list)


async def _exam_run(session: AsyncSession, run_id: int) -> ScheduleRun:
    run = await session.get(ScheduleRun, run_id)
    if run is None:
        raise PlanError(404, f"run {run_id} not found")
    if run.kind != "EXAM":
        raise PlanError(422, _t(f"#{run.id} bir sınav çalıştırması değil", f"run {run.id} is not an exam run"))
    if run.status not in EXAM_STATUSES:
        raise PlanError(
            409,
            _t(
                f"#{run.id} durumu {run.status}; gözetmen ataması yerleşmiş bir sınav programı ister",
                f"run {run.id} is {run.status}; invigilators need a placed exam timetable",
            ),
        )
    return run


def _slots(
    rows: list[Assignment], exams: Mapping[int, ExamRequest], labels: Mapping[int, str]
) -> tuple[list[inv.ExamSlot], list[int]]:
    by_exam: dict[int, list[Assignment]] = defaultdict(list)
    for a in rows:
        if a.exam_request_id is not None:
            by_exam[int(a.exam_request_id)].append(a)
    out: list[inv.ExamSlot] = []
    undated: list[int] = []
    for eid, rs in sorted(by_exam.items()):
        er = exams.get(eid)
        if er is None:
            continue
        for a in sorted(rs, key=lambda x: x.id):
            d = a.date or er.date
            if d is None:
                undated.append(eid)
                continue
            out.append(
                inv.ExamSlot(
                    exam_id=eid,
                    label=labels.get(eid, er.course_code),
                    date=d,
                    start=a.start_period,
                    end=a.end_period,
                    room_ids=tuple(_ints(a.room_ids)),
                    size=int(er.enrolment or 0),
                    invigilators=er.invigilators_requested,
                    owner_keys=frozenset(k for k, _ in person_keys(er.instructor_text)),
                )
            )
    return out, sorted(set(undated))


def _unavailable(row: InvigilatorPoolMember, dates: Iterable[date]) -> list[inv.Busy]:
    out: list[inv.Busy] = []
    ds = sorted(set(dates))
    for e in row.unavailable or []:
        sp, ep = int(e.get("start_period") or 1), int(e.get("end_period") or 18)
        note = str(e.get("note") or "")
        if e.get("date"):
            d = date.fromisoformat(str(e["date"]))
            if d in ds:
                out.append(inv.Busy(d, sp, ep, "unavailable", note))
        elif e.get("day"):
            out.extend(inv.Busy(d, sp, ep, "unavailable", note) for d in ds if d.isoweekday() == int(e["day"]))
    return out


async def _teaching(
    session: AsyncSession, dates: list[date], instructor_ids: set[int], warnings: list[dict[str, Any]]
) -> tuple[dict[int, list[inv.Busy]], list[int]]:
    """Busy spans from the published course runs around the exam dates.

    A date inside a dated term's weeks is checked against that term's published course run when the run covers the
    week; it is *unchecked* (warned) when the term has no published course run or the run's horizon leaves the week
    out. A date outside every dated term has no classes. A published course run of a term without dates cannot be
    placed on the calendar: every date is unchecked against it (warned, with the term)."""
    from app.services.solver_bridge import horizon_weeks
    from app.services.utilisation import teaching_spans

    busy: dict[int, list[inv.Busy]] = defaultdict(list)
    published = {
        r.term_id: r
        for r in sorted(
            (
                await session.execute(
                    select(ScheduleRun).where(ScheduleRun.kind == "COURSE", ScheduleRun.is_active.is_(True))
                )
            ).scalars(),
            key=lambda r: r.id,
        )
    }
    terms = list((await session.execute(select(Term).where(Term.kind != "FINAL").order_by(Term.id))).scalars())
    unchecked: dict[date, set[str]] = defaultdict(set)
    used: list[int] = []
    for term in terms:
        weeks_rows = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
        run = published.get(term.id)
        if week_index_for_date(term, dates[0], weeks_rows) is None:
            if run is not None:
                for d in dates:
                    unchecked[d].add(f"{term.code}: no_dates")
            continue
        by_week: dict[int, list[date]] = defaultdict(list)
        for d in dates:
            w = week_index_for_date(term, d, weeks_rows)
            if w is not None and 1 <= w <= int(term.week_count or 0):
                by_week[w].append(d)
        if not by_week:
            continue  # no exam date falls in this term's teaching weeks
        if run is None:
            for ds in by_week.values():
                for d in ds:
                    unchecked[d].add(f"{term.code}: not_published")
            continue
        horizon = set(horizon_weeks(run, term))
        for w, ds in by_week.items():
            if w not in horizon:
                for d in ds:
                    unchecked[d].add(f"{term.code}: week_{w}_outside_run_{run.id}")
        weeks = sorted(w for w in by_week if w in horizon)
        if not weeks:
            continue
        used.append(run.id)
        for sp in await teaching_spans(session, run, weeks):
            if sp.instructor_id not in instructor_ids:
                continue
            for d in by_week.get(sp.week, []):
                if d.isoweekday() == sp.day:
                    busy[sp.instructor_id].append(inv.Busy(d, sp.start, sp.end, "teaching", f"run:{run.id}"))
    if unchecked:
        ds = sorted(unchecked)
        warnings.append(
            {
                "code": "teaching_unchecked",
                "severity": "warning",
                "dates": [d.isoformat() for d in ds],
                "why": sorted({x for v in unchecked.values() for x in v}),
                "text": _t(
                    f"{len(ds)} sınav gününde ders saatleri denetlenemedi (o haftayı kapsayan yayımlanmış ders "
                    "programı ya da dönem takvimi yok); bu günlerde ders çakışması kontrol edilmedi",
                    f"Teaching could not be checked on {len(ds)} exam date(s) (no published course run or term "
                    "calendar covers that week); clashes with classes on those dates were not checked",
                ),
            }
        )
    return busy, used


async def _bookings(session: AsyncSession, dates: list[date], user_of: Mapping[int, int]) -> dict[int, list[inv.Busy]]:
    busy: dict[int, list[inv.Busy]] = defaultdict(list)
    if not user_of:
        return busy
    ins_of = {u: i for i, u in user_of.items()}
    rows = (
        await session.execute(
            select(Booking).where(
                Booking.user_id.in_(list(ins_of)), Booking.date.in_(dates), Booking.status == "BOOKED"
            )
        )
    ).scalars()
    for b in rows:
        assert b.user_id is not None
        busy[ins_of[b.user_id]].append(inv.Busy(b.date, b.start_period, b.end_period, "booking", f"booking:{b.id}"))
    return busy


async def build_input(
    session: AsyncSession,
    run: ScheduleRun,
    params: Mapping[str, Any],
    *,
    locks: Iterable[inv.Duty] = (),
    previous: Iterable[inv.Duty] = (),
) -> Built:
    from app.services.scenario_compare import exam_label

    p = clean_params(params)
    exams = {
        er.id: er
        for er in (
            await session.execute(
                select(ExamRequest).options(selectinload(ExamRequest.program)).where(ExamRequest.term_id == run.term_id)
            )
        ).scalars()
    }
    rows = list(
        (
            await session.execute(select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False)))
        ).scalars()
    )
    rooms = {r.id: r for r in (await session.execute(select(Room).options(selectinload(Room.building)))).scalars()}
    exam_rooms = {
        rid: inv.ExamRoom(
            rid, r.display_name, r.building.code if r.building else (r.code[:1] or "?"), int(r.exam_capacity or 0)
        )
        for rid, r in rooms.items()
    }
    rule = inv.StaffingRule(int(p["students_per_invigilator"]), int(p["min_per_room"]), p["max_per_room"])

    def slots_and_posts() -> tuple[list[inv.ExamSlot], list[int], list[inv.Post], list[int]]:
        # CPU only (name normalisation, seat splits) on rows already loaded: off the event loop
        labels = {eid: exam_label(er) for eid, er in exams.items()}
        slots, undated = _slots(rows, exams, labels)
        posts, no_room = inv.build_posts(slots, exam_rooms, rule)
        return slots, undated, posts, no_room

    slots, undated, posts, no_room = await asyncio.to_thread(slots_and_posts)
    warnings: list[dict[str, Any]] = []
    if no_room:
        warnings.append(
            {
                "code": "exams_without_room",
                "severity": "warning",
                "exam_ids": sorted(set(no_room)),
                "text": _t(
                    f"{len(set(no_room))} sınavın salonu yok (çevrimiçi ya da havuz dışı): gözetmen atanmadı",
                    f"{len(set(no_room))} exam(s) have no room (online or outside the pool): no invigilators assigned",
                ),
            }
        )
    if undated:
        warnings.append(
            {
                "code": "exams_without_date",
                "severity": "warning",
                "exam_ids": undated,
                "text": _t(
                    f"{len(undated)} sınavın tarihi yok: gözetmen atanamadı",
                    f"{len(undated)} exam(s) have no date: no invigilators could be assigned",
                ),
            }
        )
    dates = sorted({x.date for x in posts})
    # the pool
    pool_rows = list(
        (
            await session.execute(
                select(InvigilatorPoolMember)
                .where((InvigilatorPoolMember.term_id == run.term_id) | (InvigilatorPoolMember.term_id.is_(None)))
                .order_by(InvigilatorPoolMember.id)
            )
        ).scalars()
    )
    # a term row overrides a global row of the same instructor / name
    rule_rows: dict[str, InvigilatorPoolMember] = {}
    for r in sorted(pool_rows, key=lambda r: (r.term_id is not None, r.id)):
        rule_rows[f"INS:{r.instructor_id}" if r.instructor_id else f"NAME:{r.canonical_name}"] = r
    # the people of the exams this run seats (canonical names, as ExamSlot.owner_keys carries them)
    owners = {k: k for sl in slots for k in sl.owner_keys}
    ins_q = select(Instructor).where(Instructor.archived.is_(False)).order_by(Instructor.id)
    all_ins = list((await session.execute(ins_q)).scalars())
    # the exam list names people as written ("Öğ. Üy. ...", initials, a middle name left out): find them among the
    # instructors with the tiers of match_exam_people, not by the exact canonical name only (T-R1-42)
    found = match_exam_people(owners, all_ins)
    if p["instructor_pool"] == "all":
        chosen = list(all_ins)
    elif p["instructor_pool"] == "exam_instructors":
        chosen = [i for i in all_ins if i.id in found.key_of]
    else:
        chosen = []
    if p["instructor_pool"] == "exam_instructors" and found.exam_people and found.matched < found.exam_people:
        missed = found.exam_people - found.matched
        warnings.append(
            {
                "code": "pool_match",
                "severity": "info",
                "matched": found.matched,
                "exam_people": found.exam_people,
                "ambiguous": len(found.ambiguous),
                "text": _t(
                    f"Sınav listesindeki {found.exam_people} kişiden {found.matched}'i eğitmen kaydıyla eşleşti; "
                    f"{missed} kişi eğitmen listesinde yok"
                    + (f" ({len(found.ambiguous)} kişi birden çok kayda uyuyor)" if found.ambiguous else "")
                    + ": bunlar gözetmen havuzuna girmedi",
                    f"{found.matched} of the {found.exam_people} people on the exam list matched an instructor; "
                    f"{missed} are not on the instructor list"
                    + (f" ({len(found.ambiguous)} fit more than one record)" if found.ambiguous else "")
                    + " and are not in the invigilator pool",
                ),
                "suggestions": [
                    {
                        "code": "pool_add",
                        "text": _t(
                            "Eksik kişileri Havuz sekmesinden ekleyin ya da havuzu 'Tüm eğitmenler' yapın",
                            "Add the missing people on the Pool tab, or set the pool to 'All instructors'",
                        ),
                    }
                ],
            }
        )
    linked = {r.instructor_id for r in rule_rows.values() if r.instructor_id and r.active}
    chosen_ids = {i.id for i in chosen} | linked
    by_id = {i.id: i for i in all_ins}
    excluded = {r.instructor_id for r in rule_rows.values() if r.instructor_id and not r.active}
    ins_people = [by_id[i] for i in sorted(chosen_ids - excluded) if i in by_id]
    teach, teaching_runs = await _teaching(session, dates, {i.id for i in ins_people}, warnings) if dates else ({}, [])
    books = await _bookings(session, dates, {i.id: i.user_id for i in ins_people if i.user_id})
    people: list[inv.Person] = []
    meta: dict[str, dict[str, Any]] = {}
    for i in ins_people:
        rr = rule_rows.get(f"INS:{i.id}")
        busy = [*teach.get(i.id, []), *books.get(i.id, []), *(_unavailable(rr, dates) if rr else [])]
        pid = f"INS:{i.id}"
        name = f"{i.title} {i.full_name}" if i.title else i.full_name
        people.append(
            inv.Person(
                pid,
                name,
                found.key_of.get(i.id, i.canonical_name),
                "instructor",
                tuple(sorted(busy, key=lambda b: (b.date, b.start, b.reason))),
                rr.max_duties if rr else None,
                rr.max_per_day if rr else None,
                rr.load_factor if rr else 100,
            )
        )
        meta[pid] = {"name": name, "instructor_id": i.id, "staff_id": rr.id if rr else None, "kind": "INSTRUCTOR"}
    for key, r in sorted(rule_rows.items(), key=lambda kv: kv[1].id):
        if r.instructor_id or not r.active or not key.startswith("NAME:"):
            continue
        pid = f"STAFF:{r.id}"
        people.append(
            inv.Person(
                pid,
                r.full_name,
                r.canonical_name,
                "staff",
                tuple(sorted(_unavailable(r, dates), key=lambda b: (b.date, b.start))),
                r.max_duties,
                r.max_per_day,
                r.load_factor,
            )
        )
        meta[pid] = {"name": r.full_name, "instructor_id": None, "staff_id": r.id, "kind": r.kind}
    if not people:
        if p["instructor_pool"] == "none":
            why = _t(
                "havuz 'Eğitmen yok' seçili ve havuza kimse eklenmedi", "the pool is set to 'none' and nobody was added"
            )
        elif p["instructor_pool"] == "all":
            why = _t("eğitmen kaydı yok ve havuza kimse eklenmedi", "there are no instructors and nobody was added")
        elif not found.exam_people:
            why = _t(
                "sınav listesinde öğretim elemanı adı yok ve havuza kimse eklenmedi",
                "the exam list names no instructor and nobody was added to the pool",
            )
        else:
            why = _t(
                f"sınav listesindeki {found.exam_people} kişiden hiçbiri eğitmen kaydıyla eşleşmedi ve havuza kimse "
                "eklenmedi",
                f"none of the {found.exam_people} people on the exam list matched an instructor and nobody was added "
                "to the pool",
            )
        warnings.append(
            {
                "code": "pool_empty",
                "severity": "error",
                "instructor_pool": p["instructor_pool"],
                "exam_people": found.exam_people,
                "instructors": len(all_ins),
                "text": _t(f"Gözetmen havuzu boş: {why['tr']}", f"The invigilator pool is empty: {why['en']}"),
                "suggestions": [
                    {
                        "code": "pool_all",
                        "text": _t(
                            f"Havuzu 'Tüm eğitmenler' yapıp yeniden çalıştırın ({len(all_ins)} eğitmen)",
                            f"Re-run with the pool set to 'All instructors' ({len(all_ins)} instructors)",
                        ),
                    }
                ]
                if p["instructor_pool"] != "all" and all_ins
                else [],
            }
        )
    built = inv.InvigilationInput(
        posts=tuple(posts),
        people=tuple(people),
        locks=tuple(locks),
        previous=tuple(previous),
        own_exam=p["own_exam"],
        max_per_day=p["max_per_day"],
        min_rest=int(p["min_rest"]),
        weights=dict(p["weights"]),
        time_limit_s=float(p["time_limit_s"]),
        seed=int(p["seed"]),
        workers=1,  # deterministic, like publish and re-solve
    )
    return Built(built, exams, rooms, meta, warnings, teaching_runs)


# ------------------------------------------------------------------------------------------- texts

REASON_TEXT = {
    "teaching": ("dersi var", "teaching"),
    "unavailable": ("uygun değil", "unavailable"),
    "booking": ("kendi rezervasyonu var", "own booking"),
    "own_exam": ("kendi dersinin sınavı", "own course's exam"),
    "own_exam_elsewhere": ("kendi sınavında", "at their own exam"),
    "no_capacity": ("görev almıyor", "takes no duties"),
    "on_duty": ("aynı saatte başka bir salonda görevli", "on duty in another room at that time"),
    "rest": ("iki görev arasındaki dinlenme süresi yetmiyor", "too little rest between two duties"),
    "day_cap": ("o gün görev sınırına ulaştı", "has reached the daily duty limit"),
    "total_cap": ("toplam görev sınırına ulaştı", "has reached the total duty limit"),
    "on_post": ("bu görevde zaten var", "already on this duty"),
}


def _reasons(ex: Mapping[str, int], lang: str) -> str:
    i = 0 if lang == "tr" else 1
    parts = [f"{v} {REASON_TEXT.get(k, (k, k))[i]}" for k, v in ex.items()]
    return ", ".join(parts) or ("havuzda kimse yok" if lang == "tr" else "nobody in the pool")


def _when(d: str, s: int, e: int) -> str:
    return f"{date.fromisoformat(d):%d.%m.%Y} {clock(s)}–{clock(e, True)}"


def describe(d: inv.InvigDiagnosis, params: Mapping[str, Any], labels: Mapping[int, str]) -> dict[str, Any]:
    """A solver diagnosis as stored and shown: TR + EN text and structured suggestions (each an action)."""
    pr = d.params
    exams = [labels.get(e, f"#{e}") for e in d.exam_ids][:8]
    ex_txt = ", ".join(exams)
    sug: list[dict[str, Any]] = []
    spi = int(params.get("students_per_invigilator") or 40)
    if d.code == "no_candidates":
        tr = (
            f"{pr['room_code']} {_when(pr['date'], pr['start'], pr['end'])} ({ex_txt}): {pr['required']} gözetmen "
            f"gerekiyor, yalnızca {pr['candidates']} kişi uygun ({_reasons(pr['excluded'], 'tr')})"
        )
        en = (
            f"{pr['room_code']} {_when(pr['date'], pr['start'], pr['end'])} ({ex_txt}) needs {pr['required']} "
            f"invigilator(s); only {pr['candidates']} may take it ({_reasons(pr['excluded'], 'en')})"
        )
        sug.append(
            {
                "code": "add_staff",
                "count": pr["add_people"],
                "text": _t(
                    f"Bu saatte boş {pr['add_people']} kişiyi havuza ekleyin",
                    f"Add {pr['add_people']} person(s) free at that time to the pool",
                ),
            }
        )
        if pr["excluded"].get("own_exam"):
            sug.append(
                {
                    "code": "allow_own_exam",
                    "own_exam": "prefer",
                    "text": _t(
                        "Hocaların kendi sınavlarında gözetmenlik yapmasına izin verin",
                        "Let instructors invigilate their own exams",
                    ),
                }
            )
    elif d.code == "slot_shortage":
        tr = (
            f"{_when(pr['date'], pr['start'], pr['end'])} civarında {pr['posts']} salon ({', '.join(pr['rooms'])}) "
            f"birlikte {pr['required_total']} gözetmen istiyor, bunlar için yalnızca {pr['people_free']} kişi boş"
        )
        en = (
            f"Around {_when(pr['date'], pr['start'], pr['end'])}, {pr['posts']} room(s) ({', '.join(pr['rooms'])}) "
            f"need {pr['required_total']} invigilators together but only {pr['people_free']} people are free for them"
        )
        sug.append(
            {
                "code": "add_staff",
                "count": pr["add_people"],
                "text": _t(
                    f"Bu saatte boş {pr['add_people']} kişiyi havuza ekleyin",
                    f"Add {pr['add_people']} person(s) free at that time to the pool",
                ),
            }
        )
        sug.append(
            {
                "code": "raise_ratio",
                "students_per_invigilator": spi + 10,
                "text": _t(
                    f"Gözetmen başına öğrenciyi {spi} yerine {spi + 10} yapın",
                    f"Raise students per invigilator from {spi} to {spi + 10}",
                ),
            }
        )
        sug.append(
            {
                "code": "move_exam",
                "exam_ids": d.exam_ids[:8],
                "text": _t("Bu sınavlardan birini başka bir saate taşıyın", "Move one of these exams to another slot"),
            }
        )
    elif d.code == "cap_shortage":
        cap = params.get("max_per_day")
        tr = (
            f"{pr['room_code']} {_when(pr['date'], pr['start'], pr['end'])}: {pr['missing']} gözetmen eksik; boş olan "
            f"{pr['capped']} kişi günlük ya da toplam görev sınırına ulaştı"
        )
        en = (
            f"{pr['room_code']} {_when(pr['date'], pr['start'], pr['end'])} is {pr['missing']} invigilator(s) short; "
            f"{pr['capped']} free people have reached their daily or total duty limit"
        )
        if cap:
            sug.append(
                {
                    "code": "raise_max_per_day",
                    "max_per_day": int(cap) + 1,
                    "text": _t(
                        f"Günlük görev sınırını {cap} yerine {int(cap) + 1} yapın",
                        f"Raise the daily duty limit from {cap} to {int(cap) + 1}",
                    ),
                }
            )
        sug.append({"code": "add_staff", "count": pr["missing"], "text": _t("Havuza kişi ekleyin", "Add people")})
    elif d.code == "overlap_shortage":
        tr = (
            f"{pr['room_code']} {_when(pr['date'], pr['start'], pr['end'])}: {pr['missing']} gözetmen eksik; uygun "
            "herkes çakışan başka bir salonda görevli"
        )
        en = (
            f"{pr['room_code']} {_when(pr['date'], pr['start'], pr['end'])} is {pr['missing']} short; "
            "everyone eligible is on duty in an overlapping room"
        )
        sug.append(
            {
                "code": "add_staff",
                "count": pr["add_people"],
                "text": _t(f"{pr['add_people']} kişi ekleyin", f"Add {pr['add_people']} person(s)"),
            }
        )
    elif d.code == "locked_conflict":
        why = REASON_TEXT.get(str(pr.get("reason") or ""), ("başka bir görevle çakışıyor", "clashes with a duty"))
        tr = f"Kilitli görev tutmuyor: {d.person_ids[0]} {d.post_keys[0]} ({why[0]})"
        en = f"A locked duty breaks a hard rule: {d.person_ids[0]} at {d.post_keys[0]} ({why[1]})"
        sug.append(
            {
                "code": "unlock",
                "post_key": d.post_keys[0],
                "person_key": d.person_ids[0],
                "text": _t("Kilidi kaldırıp yeniden çalıştırın", "Unlock it and re-run"),
            }
        )
    elif d.code == "lock_stale":
        tr = f"Kilitli görev artık programla eşleşmiyor (sınav taşınmış olabilir): {d.post_keys[0]}"
        en = f"A locked duty no longer matches the timetable (the exam may have moved): {d.post_keys[0]}"
    else:
        tr = en = d.message
    return {
        "code": d.code,
        "severity": d.severity,
        "message": d.message,
        "text": _t(tr, en),
        "post_keys": d.post_keys,
        "exam_ids": d.exam_ids,
        "exams": exams,
        "person_keys": d.person_ids,
        "params": pr,
        "suggestions": sug,
    }


# ------------------------------------------------------------------------------------------- runs


def plan_brief(plan: InvigilationPlan) -> dict[str, Any]:
    st = plan.stats or {}
    return {
        "id": plan.id,
        "term_id": plan.term_id,
        "exam_run_id": plan.exam_run_id,
        "parent_plan_id": plan.parent_plan_id,
        "status": plan.status,
        "label": plan.label,
        "hard_score": plan.hard_score,
        "soft_score": plan.soft_score,
        "is_active": bool(plan.is_active),
        "params": plan.params or {},
        "error": plan.error,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "finished_at": plan.finished_at.isoformat() if plan.finished_at else None,
        "counts": {
            "posts": st.get("posts"),
            "required": st.get("required"),
            "filled": st.get("filled"),
            "missing": st.get("missing"),
            "people": st.get("people"),
            "eligible_people": st.get("eligible_people"),
        },
        "headline": st.get("headline"),
        "empty": bool(st.get("empty")),
        "empty_reason": st.get("empty_reason"),
        "progress": plan_progress(plan),
    }


def plan_progress(plan: InvigilationPlan) -> dict[str, Any]:
    """The queue job's last reported phase and percentage, as stored on the plan (``progress_phase`` /
    ``progress_pct``); a plan finished before alembic 0033 reads ``done`` (or ``failed``) without a number."""
    if plan.progress_phase:
        return {"phase": plan.progress_phase, "pct": plan.progress_pct}
    if plan.status == "FAILED":
        return {"phase": "failed", "pct": None}
    if plan.status in ("QUEUED", "RUNNING"):
        return {"phase": plan.status.lower(), "pct": None}
    return {"phase": "done", "pct": 100}


async def create_plan(
    session: AsyncSession,
    exam_run_id: int,
    params: Mapping[str, Any] | None,
    actor: User,
    *,
    parent: InvigilationPlan | None = None,
    label: str | None = None,
) -> InvigilationPlan:
    run = await _exam_run(session, exam_run_id)
    p = clean_params({**((parent.params or {}) if parent else {}), **(params or {})})
    plan = InvigilationPlan(
        term_id=run.term_id,
        exam_run_id=run.id,
        parent_plan_id=parent.id if parent else None,
        status="QUEUED",
        label=(label or None) and str(label)[:255],
        params=p,
        stats={},
        diagnosis=[],
        created_by=actor.id,
        progress_phase="queued",
        progress_pct=0,
    )
    session.add(plan)
    await session.flush()
    from app.workers.queue import worker_id

    plan.stats = {"worker": worker_id()}
    await audit.record(
        session,
        "invigilation.rerun" if parent else "invigilation.run",
        "invigilation_plan",
        plan.id,
        after={"exam_run_id": run.id, "parent_plan_id": plan.parent_plan_id, "params": p},
        actor=actor,
        term_id=run.term_id,
    )
    await session.commit()
    return plan


def _duty_inputs(rows: Iterable[InvigilationDuty]) -> tuple[list[inv.Duty], list[inv.Duty]]:
    rows = list(rows)
    locks = [inv.Duty(d.post_key, d.person_key, True) for d in rows if d.is_locked]
    prev = [inv.Duty(d.post_key, d.person_key, d.is_locked) for d in rows]
    return locks, prev


async def _duties(session: AsyncSession, plan_id: int) -> list[InvigilationDuty]:
    return list(
        (
            await session.execute(
                select(InvigilationDuty).where(InvigilationDuty.plan_id == plan_id).order_by(InvigilationDuty.id)
            )
        ).scalars()
    )


def _headline(res: inv.InvigilationResult) -> dict[str, str]:
    st = res.stats
    if res.status in ("OPTIMAL", "FEASIBLE"):
        return _t(
            f"{st['posts']} salon-oturum, {st['required']} görev: tümü atandı · en yoğun kişi {st['max_periods']} "
            f"periyot (adil pay {st['fair_share_periods']})",
            f"{st['posts']} room sessions, {st['required']} duties: all assigned · busiest person {st['max_periods']} "
            f"periods (fair share {st['fair_share_periods']})",
        )
    if res.status == "INFEASIBLE":
        errs = sum(1 for d in res.diagnoses if d.severity == "error")
        return _t(
            f"{st.get('filled', 0)}/{st.get('required', 0)} görev atandı · {st.get('missing', 0)} gözetmen eksik, "
            f"{errs} neden açıklandı; hiçbir kural esnetilmedi",
            f"{st.get('filled', 0)}/{st.get('required', 0)} duties assigned · {st.get('missing', 0)} invigilator(s) "
            f"missing, {errs} cause(s) explained; no rule relaxed",
        )
    return _t(f"Durum: {res.status}", f"Status: {res.status}")


async def run_plan(session_factory: Any, plan_id: int, progress: Any = None) -> dict[str, Any]:
    """Queue job: build the input from the database, solve off the event loop, store duties and diagnoses.

    Each phase is reported to the queue (SSE listeners) and stored on the plan (``progress_phase`` /
    ``progress_pct``, shown as ``progress`` in the brief): ``loading`` 10 (reading the exam run, the pool, the
    teaching), ``solving`` 30 (CP-SAT in a worker thread: the solver reports nothing until it returns, so the number
    stays at 30 for the whole solve; ``started_at`` and ``params.time_limit_s`` bound it), ``persisting`` 90,
    ``done`` 100."""

    def report(phase: str, pct: int, plan: InvigilationPlan | None = None) -> None:
        if plan is not None:
            plan.progress_phase, plan.progress_pct = phase, pct
        if progress:
            progress(phase, pct)

    async with session_factory() as session:
        plan = await session.get(InvigilationPlan, plan_id)
        if plan is None:
            raise ValueError(f"plan {plan_id} not found")
        plan.status, plan.started_at = "RUNNING", _now()
        report("loading", 10, plan)
        await session.commit()
        run = await _exam_run(session, plan.exam_run_id)
        locks: list[inv.Duty] = []
        prev: list[inv.Duty] = []
        if plan.parent_plan_id:
            locks, prev = _duty_inputs(await _duties(session, plan.parent_plan_id))
        built = await build_input(session, run, plan.params or {}, locks=locks, previous=prev)
        plan = await session.get(InvigilationPlan, plan_id)
        if plan is not None:
            report("solving", 30, plan)
        await session.commit()
    res = await asyncio.to_thread(inv.solve_invigilation, built.inp)
    from app.services.scenario_compare import exam_label

    labels = {eid: exam_label(er) for eid, er in built.exams.items()}
    posts = {p.key: p for p in built.inp.posts}
    async with session_factory() as session:
        plan = await session.get(InvigilationPlan, plan_id)
        if plan is None:
            return {"status": "DELETED"}
        report("persisting", 90, plan)
        await session.commit()
        await session.execute(delete(InvigilationDuty).where(InvigilationDuty.plan_id == plan_id))
        for d in res.duties:
            post = posts[d.post_key]
            m = built.people.get(d.person_id, {})
            session.add(
                InvigilationDuty(
                    plan_id=plan_id,
                    post_key=d.post_key,
                    date=post.date,
                    start_period=post.start,
                    end_period=post.end,
                    room_id=post.room_id,
                    exam_request_ids=list(post.exam_ids),
                    person_key=d.person_id,
                    person_name=str(m.get("name") or d.person_id)[:255],
                    instructor_id=m.get("instructor_id"),
                    staff_id=m.get("staff_id"),
                    is_locked=d.locked,
                    origin="LOCK" if d.locked else "SOLVER",
                )
            )
        diags = [describe(d, plan.params or {}, labels) for d in res.diagnoses]
        plan.diagnosis = [*built.warnings, *diags]
        plan.status = res.status if res.status in FINISHED else "FAILED"
        plan.hard_score = res.hard_score if res.status != "ERROR" else None
        plan.soft_score = res.soft_score if res.status != "ERROR" else None
        if built.warnings and any(w.get("severity") == "error" for w in built.warnings) and res.status != "INFEASIBLE":
            plan.status = "INFEASIBLE" if built.inp.posts else plan.status
        # round-1 R1-M-11: a plan with nothing to staff (0 room-sessions or 0 required duties) is an empty plan, not
        # "En iyi · tümü atandı" with hard 100 / soft 100, and it is never published
        empty = plan.status != "FAILED" and (not built.inp.posts or int(res.stats.get("required") or 0) == 0)
        empty_reason: dict[str, str] | None = None
        if empty:
            plan.hard_score = None
            plan.soft_score = None
            empty_reason = (
                _t(
                    f"Sınav çalıştırması #{plan.exam_run_id} hiçbir sınavı bir salona yerleştirmemiş: gözetmen "
                    "atanacak salon-oturum yok. Önce sınavları salonlara yerleştiren bir sınav çalıştırması seçin.",
                    f"Exam run #{plan.exam_run_id} seats no exam in a room: there is no room session to staff. "
                    "Pick an exam run that places the exams in rooms first.",
                )
                if not built.inp.posts
                else _t(
                    "Hiçbir salon-oturum gözetmen istemiyor (gerekli görev 0).",
                    "No room session asks for an invigilator (0 duties required).",
                )
            )
        plan.stats = {
            **(plan.stats or {}),
            **res.stats,
            "empty": empty,
            "empty_reason": empty_reason,
            "objective_breakdown": res.objective_breakdown,
            "shortfall": res.shortfall,
            "loads": res.loads,
            "teaching_runs": built.teaching_runs,
            "posts_detail": [
                {
                    "key": p.key,
                    "date": p.date.isoformat(),
                    "start_period": p.start,
                    "end_period": p.end,
                    "room_id": p.room_id,
                    "room": p.room_code,
                    "building": p.building,
                    "exam_ids": list(p.exam_ids),
                    "seated": p.seated,
                    "required": p.required,
                }
                for p in built.inp.posts
            ],
            "headline": _t(f"Atanacak görev yok · {empty_reason['tr']}", f"Nothing to assign · {empty_reason['en']}")
            if empty_reason
            else _headline(res),
            "progress": 100,
        }
        if res.status == "ERROR":
            plan.error = "; ".join(res.stats.get("problems") or [])[:4000]
        plan.finished_at = _now()
        if plan.status == "FAILED":
            plan.progress_phase = "failed"
        else:
            report("done", 100, plan)
        await session.commit()
    return {"status": res.status, "duties": len(res.duties)}


def enqueue_plan(plan_id: int) -> None:
    from app.core.db import get_session_factory
    from app.workers.queue import JobState, get_queue

    factory = get_session_factory()

    async def body(progress: Any) -> dict[str, Any]:
        return await run_plan(factory, plan_id, progress)

    async def on_status(st: JobState) -> None:
        if st.status != "FAILED":
            return
        async with factory() as s:
            row = await s.get(InvigilationPlan, plan_id)
            if row is None:
                return
            row.status = "FAILED"
            row.error = (st.error or "")[:4000]
            row.finished_at = _now()
            row.progress_phase = "failed"
            await s.commit()

    get_queue().enqueue(f"invig:{plan_id}", body, on_status=on_status)


async def _plan(session: AsyncSession, plan_id: int) -> InvigilationPlan:
    plan = await session.get(InvigilationPlan, plan_id)
    if plan is None:
        raise PlanError(404, f"plan {plan_id} not found")
    await _recover(session, plan)
    return plan


INTERRUPTED = "interrupted: the server restarted while the plan was queued or running; re-run it"


def _orphaned(plan: InvigilationPlan, now: datetime, *, startup: bool) -> bool:
    """A QUEUED / RUNNING plan nobody is working on: no live job of this process holds it, and it is not another
    live replica's (that one beats ``heartbeat_at``; ``run_stale_after_s``). A plan of this boot without a job is
    always an orphan; a row without any beat (made before alembic 0033) only after :data:`STALE_AFTER`."""
    from app.core.config import get_settings
    from app.workers.queue import BOOT_ID, get_queue

    if get_queue().state(f"invig:{plan.id}") is not None:
        return False  # a job of this process holds it
    worker = (plan.stats or {}).get("worker") or {}
    if not startup and worker.get("boot") == BOOT_ID:
        return True
    stale = timedelta(seconds=float(get_settings().run_stale_after_s))
    if plan.heartbeat_at is not None:
        return now - plan.heartbeat_at > stale
    return startup or (plan.created_at is not None and now - plan.created_at > STALE_AFTER)


def _fail_interrupted(plan: InvigilationPlan, now: datetime) -> None:
    plan.status = "FAILED"
    plan.error = INTERRUPTED
    plan.finished_at = now
    plan.progress_phase = "failed"


async def _recover(session: AsyncSession, plan: InvigilationPlan) -> None:
    """A plan left QUEUED / RUNNING by a process that is gone (restart) is reported as FAILED, never as running."""
    if plan.status not in ("QUEUED", "RUNNING"):
        return
    now = _now()
    if _orphaned(plan, now, startup=False):
        _fail_interrupted(plan, now)
        await session.commit()


async def recover_interrupted_plans(session: AsyncSession) -> int:
    """Startup sweep (``app.main`` lifespan, next to ``recover_interrupted``): plans left QUEUED / RUNNING by a dead
    process become FAILED. Nothing of this boot runs yet; a plan another replica is still beating for is kept."""
    now = _now()
    n_failed = 0
    q = select(InvigilationPlan).where(InvigilationPlan.status.in_(("QUEUED", "RUNNING")))
    for plan in (await session.execute(q)).scalars():
        if _orphaned(plan, now, startup=True):
            _fail_interrupted(plan, now)
            n_failed += 1
    await session.commit()
    if n_failed:
        log.warning("marked %d invigilation plan(s) FAILED (interrupted by restart)", n_failed)
    return n_failed


async def list_plans(
    session: AsyncSession, *, exam_run_id: int | None = None, term_id: int | None = None
) -> list[dict[str, Any]]:
    q = select(InvigilationPlan).order_by(InvigilationPlan.id.desc())
    if exam_run_id is not None:
        q = q.where(InvigilationPlan.exam_run_id == exam_run_id)
    if term_id is not None:
        q = q.where(InvigilationPlan.term_id == term_id)
    out = []
    for p in (await session.execute(q.limit(200))).scalars():
        await _recover(session, p)
        out.append(plan_brief(p))
    return out


def duty_out(d: InvigilationDuty) -> dict[str, Any]:
    return {
        "id": d.id,
        "post_key": d.post_key,
        "date": d.date.isoformat(),
        "start_period": d.start_period,
        "end_period": d.end_period,
        "time": f"{clock(d.start_period)}–{clock(d.end_period, True)}",
        "room_id": d.room_id,
        "exam_request_ids": list(d.exam_request_ids or []),
        "person_key": d.person_key,
        "person_name": d.person_name,
        "instructor_id": d.instructor_id,
        "staff_id": d.staff_id,
        "is_locked": bool(d.is_locked),
        "origin": d.origin,
    }


async def plan_detail(session: AsyncSession, plan_id: int, *, person: str | None = None) -> dict[str, Any]:
    plan = await _plan(session, plan_id)
    duties = await _duties(session, plan.id)
    st = plan.stats or {}
    by_post: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in duties:
        if person and d.person_key != person:
            continue
        by_post[d.post_key].append(duty_out(d))
    from app.services.scenario_compare import exam_label

    exam_ids = {e for p in st.get("posts_detail") or [] for e in p["exam_ids"]}
    exams = {
        er.id: er
        for er in (
            await session.execute(
                select(ExamRequest)
                .options(selectinload(ExamRequest.program))
                .where(ExamRequest.id.in_(sorted(exam_ids) or [0]))
            )
        ).scalars()
    }
    short = st.get("shortfall") or {}
    posts = []
    for p in st.get("posts_detail") or []:
        if person and p["key"] not in by_post:
            continue
        posts.append(
            {
                **p,
                "time": f"{clock(p['start_period'])}–{clock(p['end_period'], True)}",
                "exams": [
                    {
                        "id": e,
                        "label": exam_label(exams[e]) if e in exams else f"#{e}",
                        "instructor_text": exams[e].instructor_text if e in exams else None,
                    }
                    for e in p["exam_ids"]
                ],
                "assigned": by_post.get(p["key"], []),
                "missing": int(short.get(p["key"], 0)),
            }
        )
    loads = st.get("loads") or {}
    names = {d.person_key: d.person_name for d in duties}
    people = sorted(
        ({"person_key": k, "name": names.get(k, k), **v} for k, v in loads.items()),
        key=lambda r: (-int(r["periods"]), r["name"]),
    )
    return {
        **plan_brief(plan),
        "posts": posts,
        "people": people,
        "diagnosis": plan.diagnosis or [],
        "objective_breakdown": st.get("objective_breakdown") or {},
        "stats": {k: v for k, v in st.items() if k not in ("posts_detail", "loads", "shortfall", "worker")},
    }


async def _editable(session: AsyncSession, plan_id: int) -> InvigilationPlan:
    plan = await _plan(session, plan_id)
    if plan.status in ("QUEUED", "RUNNING"):
        raise PlanError(409, _t("Plan hâlâ çalışıyor", "The plan is still running"))
    return plan


async def lock_duty(session: AsyncSession, plan_id: int, duty_id: int, locked: bool, actor: User) -> dict[str, Any]:
    plan = await _editable(session, plan_id)
    d = await session.get(InvigilationDuty, duty_id)
    if d is None or d.plan_id != plan.id:
        raise PlanError(404, f"duty {duty_id} not found in plan {plan.id}")
    before = duty_out(d)
    d.is_locked = bool(locked)
    await audit.record(
        session,
        "invigilation.lock" if locked else "invigilation.unlock",
        "invigilation_duty",
        d.id,
        before=before,
        after=duty_out(d),
        actor=actor,
        term_id=plan.term_id,
    )
    await session.commit()
    return duty_out(d)


async def _rebuild(session: AsyncSession, plan: InvigilationPlan) -> Built:
    run = await _exam_run(session, plan.exam_run_id)
    return await build_input(session, run, plan.params or {})


def _plan_map(built: Built, duties: Iterable[tuple[str, str]]) -> dict[int, list[int]]:
    kidx = {p.key: k for k, p in enumerate(built.inp.posts)}
    pidx = {p.id: i for i, p in enumerate(built.inp.people)}
    out: dict[int, list[int]] = defaultdict(list)
    for post_key, person in duties:
        if post_key in kidx and person in pidx:
            out[kidx[post_key]].append(pidx[person])
    return out


@dataclass(frozen=True)
class PostCheck:
    """One person against one post: ``reason`` None = may take it; else the rule (a :data:`REASON_TEXT` key) and a
    line in the solver's ``validate`` wording for a 409, plus the duty it clashes with."""

    reason: str | None = None
    problem: str | None = None
    clash_post_key: str | None = None


def check_post(
    inp: inv.InvigilationInput,
    k: int,
    current: Mapping[int, Sequence[int]],
    people: Iterable[int] | None = None,
) -> dict[int, PostCheck]:
    """The hard rules of post ``k`` for each person, given the plan's other duties (``current``: post index ->
    person indexes; the people on ``k`` itself are not counted against anyone).

    Only what adding this one duty can break is checked, with per-person indexes instead of one whole-plan
    validation per person (``GET …/candidates`` took ~58 s on the Final that way):

    * eligibility for the post - teaching, unavailability, own bookings, ``no_capacity``, own exam (``forbid``) and
      one's own exam elsewhere at the time (``prefer``) - by the solver's own :func:`inv.eligibility` on that date's
      posts only (every rule of a post looks at its date alone, so the answer is the same as on the whole plan);
    * a duty of the person at an overlapping time (``on_duty``) or within ``min_rest`` periods (``rest``);
    * the daily cap (the person's, else the plan's) and the total cap.

    A break the person's other duties already have (a lock made before an unavailability was declared) is not this
    post's concern: it is reported by the plan, not by every candidate list."""
    posts = inp.posts
    p = posts[k]
    same_day = [q for q, x in enumerate(posts) if x.date == p.date]
    el = inv.eligibility(replace(inp, posts=tuple(posts[q] for q in same_day), locks=(), previous=()))
    kk = same_day.index(k)
    taken: dict[int, list[int]] = defaultdict(list)
    for q, ps in current.items():
        if q == k:
            continue
        for i in ps:
            taken[i].append(q)
    out: dict[int, PostCheck] = {}
    for i in range(len(inp.people)) if people is None else people:
        person = inp.people[i]
        why = el.why.get((kk, i))
        if why is not None:
            out[i] = PostCheck(why, f"{person.id} at {p.key}: {why}")
            continue
        mine = sorted(taken.get(i, ()), key=lambda q: (posts[q].date, posts[q].start, posts[q].key))
        day = [q for q in mine if posts[q].date == p.date]
        clash = next((q for q in day if posts[q].start <= p.end and p.start <= posts[q].end), None)
        rest = inp.min_rest
        near = next(
            (q for q in day if rest and posts[q].start <= p.end + rest and p.start <= posts[q].end + rest), None
        )
        day_cap = person.max_per_day if person.max_per_day is not None else inp.max_per_day
        if clash is not None or near is not None:
            other = posts[clash if clash is not None else near]
            out[i] = PostCheck(
                "on_duty" if clash is not None else "rest", f"{person.id}: {other.key} and {p.key} at once", other.key
            )
        elif day_cap is not None and len(day) + 1 > day_cap:
            out[i] = PostCheck("day_cap", f"{person.id}: more than {day_cap} duties a day")
        elif person.max_duties is not None and len(mine) + 1 > person.max_duties:
            out[i] = PostCheck("total_cap", f"{person.id}: more than {person.max_duties} duties")
        else:
            out[i] = PostCheck()
    return out


def _candidates(built: Built, plan_id: int, post_key: str, pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
    kidx = {p.key: k for k, p in enumerate(built.inp.posts)}
    if post_key not in kidx:
        raise PlanError(404, f"post {post_key} is not in plan {plan_id}")
    k = kidx[post_key]
    current = _plan_map(built, pairs)
    on_post = set(current.get(k, []))
    checks = check_post(built.inp, k, current, [i for i in range(len(built.inp.people)) if i not in on_post])
    free, busy = [], []
    for i, person in enumerate(built.inp.people):
        if i in on_post:
            continue
        c = checks[i]
        row = {"person_key": person.id, "name": person.name, "kind": person.kind}
        if c.reason is None:
            free.append(row)
            continue
        tr, en = REASON_TEXT.get(c.reason, ("başka görevde ya da sınırda", "on another duty or at a limit"))
        busy.append({**row, "reason": c.reason, "reason_text": _t(tr, en), "clash_post_key": c.clash_post_key})
    return {"post_key": post_key, "free": free, "unavailable": busy[:500]}


async def candidates(session: AsyncSession, plan_id: int, post_key: str) -> dict[str, Any]:
    """Who could take a post of this plan now: eligible and free (not on duty elsewhere at that time, under the
    caps), and everyone else with the reason. The rule checks run in a worker thread (:func:`check_post`)."""
    plan = await _editable(session, plan_id)
    built = await _rebuild(session, plan)
    pairs = [(d.post_key, d.person_key) for d in await _duties(session, plan.id)]
    return await asyncio.to_thread(_candidates, built, plan.id, post_key, pairs)


#: diagnoses about seats that are missing (a manual fill can resolve them)
SHORTAGE_CODES = frozenset({"no_candidates", "slot_shortage", "cap_shortage", "overlap_shortage"})


def _score(built: Built, rows: Sequence[tuple[str, str, bool]], previous: Sequence[inv.Duty]) -> dict[str, Any]:
    """The plan's scores after a manual edit, counted like ``inv.solve_invigilation`` counts a solved plan: the
    shortfall per post, the hard score (every required seat and every locked duty that holds), the soft score
    (busiest scaled load against the fair share), the loads (duties, periods, own exams, days) and the objective
    breakdown (``inv.breakdown_of``). ``rows``: (post key, person key, locked) of every stored duty. CPU only."""
    inp = replace(built.inp, previous=tuple(previous))
    posts, people = inp.posts, inp.people
    plan = _plan_map(built, [(a, b) for a, b, _ in rows])
    el = inv.eligibility(inp)
    short = {k: posts[k].required - len(plan.get(k, [])) for k in range(len(posts))}
    shortfall = {posts[k].key: v for k, v in sorted(short.items()) if v > 0}
    required = sum(x.required for x in posts)
    filled = required - sum(shortfall.values())
    locks = sum(1 for *_, locked in rows if locked)
    hard = 100 if not shortfall else min(99, math.floor(100 * (filled + locks) / (required + locks)))
    loads: dict[str, dict[str, int]] = {}
    days: dict[str, set[date]] = defaultdict(set)
    for k, ps in plan.items():
        for i in ps:
            e = loads.setdefault(people[i].id, {"duties": 0, "periods": 0, "own_exam": 0, "days": 0})
            e["duties"] += 1
            e["periods"] += posts[k].duration
            e["own_exam"] += 1 if (k, i) in el.own else 0
            days[people[i].id].add(posts[k].date)
    for pid, ds in days.items():
        loads[pid]["days"] = len(ds)
    eligible = {i for ks in el.cands.values() for i in ks}
    scaled = [
        loads[people[i].id]["periods"] * 100 / max(1, people[i].load_factor) for i in eligible if people[i].id in loads
    ]
    total = sum(posts[k].duration * len(ps) for k, ps in plan.items())
    longest = max((posts[k].duration for k, ps in plan.items() if ps), default=0)
    fsum = sum(max(1, people[i].load_factor) for i in eligible) or 1
    lb = max(total * 100 / fsum, float(longest) * 100 / max((people[i].load_factor for i in eligible), default=100))
    soft = 100 if not scaled else max(0, min(100, round(100 * lb / max(scaled))))
    return {
        "hard_score": hard,
        "soft_score": soft,
        "shortfall": shortfall,
        "loads": dict(sorted(loads.items())),
        "objective_breakdown": inv.breakdown_of(inp, el, plan),
        "required": required,
        "filled": filled,
        "missing": required - filled,
        "max_periods": round(max(scaled), 2) if scaled else 0,
        "fair_share_periods": round(lb, 2),
    }


async def _rescore(session: AsyncSession, plan: InvigilationPlan, built: Built) -> None:
    """Re-score the plan from its stored duties (after a manual fill or swap; the session holds the edit)."""
    await session.flush()
    rows = [(d.post_key, d.person_key, bool(d.is_locked)) for d in await _duties(session, plan.id)]
    previous: list[inv.Duty] = []
    if plan.parent_plan_id:
        previous = _duty_inputs(await _duties(session, plan.parent_plan_id))[1]
    sc = await asyncio.to_thread(_score, built, rows, previous)
    shortfall = sc["shortfall"]
    diags = []
    for x in plan.diagnosis or []:
        if x.get("code") in SHORTAGE_CODES and x.get("post_keys"):
            x = {**x, "resolved": all(not shortfall.get(k) for k in x["post_keys"])}
        diags.append(x)
    plan.diagnosis = diags
    blocking = [
        x
        for x in diags
        if x.get("severity") == "error" and not x.get("resolved") and x.get("code") not in SHORTAGE_CODES
    ]
    if plan.status == "INFEASIBLE" and not shortfall and not blocking:
        plan.status = "FEASIBLE"  # every seat staffed by hand, no broken lock left
    plan.hard_score, plan.soft_score = sc["hard_score"], sc["soft_score"]
    st = {**(plan.stats or {}), **{k: v for k, v in sc.items() if k not in ("hard_score", "soft_score")}}
    st["manual_edits"] = int(st.get("manual_edits") or 0) + 1
    errs = [x for x in diags if x.get("severity") == "error" and not x.get("resolved")]
    res = inv.InvigilationResult(
        plan.status,
        [],
        sc["hard_score"],
        sc["soft_score"],
        sc["objective_breakdown"],
        [inv.InvigDiagnosis(str(x.get("code")), "error", "") for x in errs],
        shortfall,
        sc["loads"],
        st,
    )
    st["headline"] = _headline(res)
    plan.stats = st


def _refuse(check: PostCheck) -> PlanError:
    assert check.reason is not None
    tr, en = REASON_TEXT.get(check.reason, ("başka görevde ya da sınırda", "on another duty or at a limit"))
    return PlanError(
        409,
        {
            "tr": "Bu kişi bu göreve atanamaz: bir sert kural bozulur",
            "en": "This person cannot take the duty: a hard rule would break",
            "reason": check.reason,
            "reason_text": _t(tr, en),
            "clash_post_key": check.clash_post_key,
            "problems": [check.problem] if check.problem else [],
        },
    )


def _set_person(d: InvigilationDuty, built: Built, person_key: str) -> None:
    m = built.people.get(person_key, {})
    d.person_key = person_key
    d.person_name = str(m.get("name") or person_key)[:255]
    d.instructor_id = m.get("instructor_id")
    d.staff_id = m.get("staff_id")
    d.is_locked = True
    d.origin = "MANUAL"


async def reassign_duty(
    session: AsyncSession, plan_id: int, duty_id: int, person_key: str, actor: User, reason: str | None = None
) -> dict[str, Any]:
    """A planner swaps the person of one duty: checked against every hard rule of that post (409 with the problems
    otherwise); the new duty is MANUAL and locked, so a re-run keeps it; the plan is re-scored."""
    plan = await _editable(session, plan_id)
    d = await session.get(InvigilationDuty, duty_id)
    if d is None or d.plan_id != plan.id:
        raise PlanError(404, f"duty {duty_id} not found in plan {plan.id}")
    built = await _rebuild(session, plan)
    pidx = {p.id: i for i, p in enumerate(built.inp.people)}
    if person_key not in pidx:
        raise PlanError(422, f"{person_key} is not in this plan's pool")
    kidx = {p.key: k for k, p in enumerate(built.inp.posts)}
    if d.post_key not in kidx:
        raise PlanError(
            409,
            _t(
                "Bu görev artık sınav programıyla eşleşmiyor (sınav taşınmış olabilir); planı yeniden çalıştırın",
                "This duty no longer matches the exam timetable (the exam may have moved); re-run the plan",
            ),
        )
    duties = await _duties(session, plan.id)
    if person_key != d.person_key:
        if any(x.post_key == d.post_key and x.person_key == person_key for x in duties):
            raise _refuse(PostCheck("on_post", f"post {d.post_key}: a person listed twice"))
        pairs = [(x.post_key, x.person_key) for x in duties if x.id != d.id]
        k, i = kidx[d.post_key], pidx[person_key]
        check = (await asyncio.to_thread(check_post, built.inp, k, _plan_map(built, pairs), [i]))[i]
        if check.reason is not None:
            raise _refuse(check)
    before = duty_out(d)
    _set_person(d, built, person_key)
    await audit.record(
        session,
        "invigilation.reassign",
        "invigilation_duty",
        d.id,
        before=before,
        after=duty_out(d),
        actor=actor,
        reason=reason,
        term_id=plan.term_id,
    )
    await _rescore(session, plan, built)
    await session.commit()
    return duty_out(d)


async def add_duty(
    session: AsyncSession, plan_id: int, post_key: str, person_key: str, actor: User, reason: str | None = None
) -> dict[str, Any]:
    """A planner fills an under-staffed post by hand: one more invigilator on ``post_key``. Checked against every
    hard rule of the post (eligibility, overlapping duties, rest, daily and total caps; 409 with ``problems`` like
    reassign) and against the post's required count; the duty is MANUAL and locked (a re-run keeps it), audited
    (``invigilation.add_duty``) and the plan is re-scored."""
    plan = await _editable(session, plan_id)
    built = await _rebuild(session, plan)
    kidx = {p.key: k for k, p in enumerate(built.inp.posts)}
    if post_key not in kidx:
        raise PlanError(404, f"post {post_key} is not in plan {plan.id}")
    pidx = {p.id: i for i, p in enumerate(built.inp.people)}
    if person_key not in pidx:
        raise PlanError(422, f"{person_key} is not in this plan's pool")
    k, i = kidx[post_key], pidx[person_key]
    post = built.inp.posts[k]
    duties = await _duties(session, plan.id)
    on = [x for x in duties if x.post_key == post_key]
    if any(x.person_key == person_key for x in on):
        raise _refuse(PostCheck("on_post", f"post {post_key}: a person listed twice"))
    if len(on) >= post.required:
        raise PlanError(
            409,
            {
                "tr": f"Bu salon-oturum için gereken {post.required} gözetmen zaten atanmış",
                "en": f"This room session already has the {post.required} invigilator(s) it needs",
                "reason": "post_full",
                "reason_text": _t("gözetmen sayısı dolu", "fully staffed"),
                "clash_post_key": None,
                "problems": [f"post {post_key}: {len(on) + 1} > {post.required} invigilators"],
            },
        )
    pairs = [(x.post_key, x.person_key) for x in duties]
    check = (await asyncio.to_thread(check_post, built.inp, k, _plan_map(built, pairs), [i]))[i]
    if check.reason is not None:
        raise _refuse(check)
    d = InvigilationDuty(
        plan_id=plan.id,
        post_key=post.key,
        date=post.date,
        start_period=post.start,
        end_period=post.end,
        room_id=post.room_id,
        exam_request_ids=list(post.exam_ids),
    )
    _set_person(d, built, person_key)
    session.add(d)
    await session.flush()
    await audit.record(
        session,
        "invigilation.add_duty",
        "invigilation_duty",
        d.id,
        after=duty_out(d),
        actor=actor,
        reason=reason,
        term_id=plan.term_id,
    )
    await _rescore(session, plan, built)
    await session.commit()
    return {**duty_out(d), "plan": plan_brief(plan)}


async def rerun(
    session: AsyncSession, plan_id: int, params: Mapping[str, Any] | None, actor: User, label: str | None = None
) -> InvigilationPlan:
    parent = await _editable(session, plan_id)
    return await create_plan(session, parent.exam_run_id, params, actor, parent=parent, label=label)


async def activate(session: AsyncSession, plan_id: int, actor: User) -> dict[str, Any]:
    plan = await _editable(session, plan_id)
    if plan.status not in ("OPTIMAL", "FEASIBLE", "INFEASIBLE"):
        raise PlanError(409, _t(f"Plan durumu {plan.status}; yayımlanamaz", f"plan is {plan.status}; cannot publish"))
    st = plan.stats or {}
    if st.get("empty") or not st.get("posts"):
        why = st.get("empty_reason") or _t("Planda atanacak görev yok.", "The plan has nothing to assign.")
        raise PlanError(
            409,
            {
                "code": "empty_plan",
                "tr": f"Boş plan yayımlanamaz: {why['tr']}",
                "en": f"An empty plan cannot be published: {why['en']}",
            },
        )
    previous = (
        (
            await session.execute(
                select(InvigilationPlan).where(
                    InvigilationPlan.exam_run_id == plan.exam_run_id, InvigilationPlan.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    for p in previous:
        if p.id != plan.id:
            p.is_active = False
    await session.flush()
    plan.is_active = True
    await audit.record(
        session,
        "invigilation.activate",
        "invigilation_plan",
        plan.id,
        before={"active_plan_ids": [p.id for p in previous]},
        after={"active_plan_id": plan.id, "status": plan.status, "missing": (plan.stats or {}).get("missing")},
        actor=actor,
        term_id=plan.term_id,
    )
    await session.commit()
    return plan_brief(plan)


async def delete_plan(session: AsyncSession, plan_id: int, actor: User) -> None:
    plan = await _editable(session, plan_id)
    if plan.is_active:
        raise PlanError(409, _t("Yayımdaki plan silinemez", "The published plan cannot be deleted"))
    before = plan_brief(plan)
    await session.delete(plan)
    await audit.record(
        session, "invigilation.delete", "invigilation_plan", plan_id, before=before, actor=actor, term_id=plan.term_id
    )
    await session.commit()


# ------------------------------------------------------------------------------------------- exports


async def roster_csv(session: AsyncSession, plan_id: int) -> str:
    data = await plan_detail(session, plan_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["date", "start", "end", "room", "building", "exams", "required", "missing", "person", "person_key", "locked"]
    )
    for p in data["posts"]:
        exams = " / ".join(e["label"] for e in p["exams"])
        rows = p["assigned"] or [None]
        for d in rows:
            w.writerow(
                [
                    p["date"],
                    clock(p["start_period"]),
                    clock(p["end_period"], True),
                    p["room"],
                    p["building"],
                    exams,
                    p["required"],
                    p["missing"],
                    d["person_name"] if d else "",
                    d["person_key"] if d else "",
                    ("1" if d["is_locked"] else "0") if d else "",
                ]
            )
    return buf.getvalue()


async def load_heatmap(session: AsyncSession, plan_id: int) -> dict[str, Any]:
    """Invigilation load: person x date duty counts (and periods), with totals per date; the exam-side counterpart of
    the instructor load heatmap."""
    plan = await _plan(session, plan_id)
    duties = await _duties(session, plan.id)
    dates = sorted({d.date for d in duties})
    cells: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"duties": 0, "periods": 0}))
    names: dict[str, str] = {}
    for d in duties:
        c = cells[d.person_key][d.date.isoformat()]
        c["duties"] += 1
        c["periods"] += d.end_period - d.start_period + 1
        names[d.person_key] = d.person_name
    rows: list[dict[str, Any]] = []
    for key, by_date in cells.items():
        rows.append(
            {
                "person_key": key,
                "name": names[key],
                "duties": sum(v["duties"] for v in by_date.values()),
                "periods": sum(v["periods"] for v in by_date.values()),
                "max_per_day": max(v["duties"] for v in by_date.values()),
                "cells": [{"date": k, **v} for k, v in sorted(by_date.items())],
            }
        )
    rows.sort(key=lambda r: (-r["periods"], r["name"]))
    per_date = [
        {
            "date": d.isoformat(),
            "duties": sum(1 for x in duties if x.date == d),
            "people": len({x.person_key for x in duties if x.date == d}),
        }
        for d in dates
    ]
    return {"plan_id": plan.id, "dates": [d.isoformat() for d in dates], "rows": rows, "per_date": per_date}


def load_heatmap_csv(data: Mapping[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["person_key", "name", "date", "duties", "periods", "total_duties", "total_periods"])
    for r in data["rows"]:
        for c in r["cells"]:
            w.writerow([r["person_key"], r["name"], c["date"], c["duties"], c["periods"], r["duties"], r["periods"]])
    return buf.getvalue()


__all__ = [
    "PlanError",
    "activate",
    "add_duty",
    "check_post",
    "build_input",
    "candidates",
    "clean_params",
    "create_plan",
    "delete_plan",
    "delete_pool_member",
    "enqueue_plan",
    "list_plans",
    "list_pool",
    "load_heatmap",
    "lock_duty",
    "plan_detail",
    "plan_progress",
    "reassign_duty",
    "recover_interrupted_plans",
    "rerun",
    "roster_csv",
    "run_plan",
    "save_pool_member",
]
