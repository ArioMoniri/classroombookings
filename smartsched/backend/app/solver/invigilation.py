"""Invigilator assignment for a placed exam timetable (pure: no DB, no HTTP).

``solve_invigilation(InvigilationInput) -> InvigilationResult``.

Model
-----
A **post** is one room at one time of one date that needs invigilators: the placed exams sharing a room at
overlapping times form one post (their students sit together, one team watches them; the Final plan seats several
exams in one room). :func:`build_posts` makes posts from the exam placements and the staffing rule:

``required = max(min_per_room, ceil(seated / students_per_invigilator), sum over the post's exams of
ceil(invigilators_requested / rooms of that exam))`` (``max_per_room`` caps the ratio part only; an explicit
request is never cut).

Hard rules (never relaxed; a post that cannot be fully staffed is reported, not filled with a rule broken):

* exactly ``required`` people per post (``short[k]`` counts the missing ones, minimised first, and every missing
  invigilator is a named diagnosis);
* nobody in two posts at once (``min_rest`` periods between two duties of a day);
* nobody during their busy times: teaching, declared unavailability, their own bookings (``Person.busy``);
* own exams (``own_exam``): ``forbid`` - never invigilate an exam of one's own course; ``prefer`` - one's own exam
  is preferred and the person is busy elsewhere while it runs; ``allow`` - no rule;
* at most ``max_per_day`` duties a day and ``max_duties`` in total per person;
* locked duties hold (a lock that breaks a hard rule is reported as ``locked_conflict`` and the plan is infeasible).

Soft objective (after the shortfall is minimal, phase 2): the highest load (periods, scaled by the person's
``load_factor``), the load above each person's fair share, several duties on one day, own exams (bonus under
``prefer``) and, on a re-run, keeping the previous plan's duties (stability). Weights: :data:`DEFAULT_WEIGHTS`.

Determinism: one worker, fixed seed, deterministic time budget; the same input gives the same plan.

Diagnoses for an under-staffed post: ``no_candidates`` (fewer eligible people than needed, with the reasons
everyone else is out), ``slot_shortage`` (a minimal set of posts at one time that together need more people than
are free - Hall's condition, shrunk by deletion so every post in it matters), ``cap_shortage`` (the daily or total
caps of the free people are the limit).
"""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

OwnExam = Literal["prefer", "allow", "forbid"]

DEFAULT_WEIGHTS: dict[str, int] = {
    "max_load": 10,  # per period of the busiest (factor-scaled) load
    "spread": 2,  # per period above a person's fair share
    "same_day": 3,  # per duty beyond the first of a day
    "own_exam": 5,  # bonus per own-exam duty (prefer)
    "stability": 4,  # per previous duty not kept (re-run)
}
#: deterministic-time share of the shortfall phase
PHASE1_SHARE = 0.4


# ------------------------------------------------------------------------------------------- input


@dataclass(frozen=True)
class ExamRoom:
    id: int
    code: str
    building: str
    exam_capacity: int


@dataclass(frozen=True)
class ExamSlot:
    """A placed exam (one solver event or one exam request): date, periods (inclusive) and rooms."""

    exam_id: int
    label: str
    date: date
    start: int
    end: int
    room_ids: tuple[int, ...]
    size: int
    invigilators: int | None = None  # requested for the whole exam (the exam list's "N gözetmen")
    owner_keys: frozenset[str] = frozenset()  # canonical names of the exam's instructors


@dataclass(frozen=True)
class StaffingRule:
    students_per_invigilator: int = 40
    min_per_room: int = 1
    max_per_room: int | None = None


@dataclass(frozen=True)
class Post:
    key: str  # "<date>|<room id>|<start>-<end>" (stable across re-runs while the exams stay put)
    date: date
    start: int
    end: int
    room_id: int
    room_code: str
    building: str
    exam_ids: tuple[int, ...]
    labels: tuple[str, ...]
    seated: int
    required: int
    owner_keys: frozenset[str] = frozenset()

    @property
    def duration(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class Busy:
    date: date
    start: int
    end: int
    reason: str  # teaching | unavailable | booking
    ref: str = ""


@dataclass(frozen=True)
class Person:
    id: str  # "INS:<instructor id>" | "STAFF:<pool id>"
    name: str
    key: str  # canonical name (matches ExamSlot.owner_keys)
    kind: str = "instructor"
    busy: tuple[Busy, ...] = ()
    max_duties: int | None = None
    max_per_day: int | None = None
    load_factor: int = 100  # percent: 200 = expected to take twice the average share


@dataclass(frozen=True)
class Duty:
    post_key: str
    person_id: str
    locked: bool = False


@dataclass(frozen=True)
class InvigilationInput:
    posts: tuple[Post, ...]
    people: tuple[Person, ...]
    locks: tuple[Duty, ...] = ()
    previous: tuple[Duty, ...] = ()
    own_exam: OwnExam = "prefer"
    max_per_day: int | None = 3  # default daily cap of a person without their own
    min_rest: int = 0
    weights: Mapping[str, int] = field(default_factory=dict)
    time_limit_s: float = 20.0
    seed: int = 0
    workers: int = 1


# ------------------------------------------------------------------------------------------- output


@dataclass
class InvigDiagnosis:
    code: str
    severity: str  # error | warning
    message: str
    post_keys: list[str] = field(default_factory=list)
    exam_ids: list[int] = field(default_factory=list)
    person_ids: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvigilationResult:
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | ERROR
    duties: list[Duty]
    hard_score: int
    soft_score: int
    objective_breakdown: dict[str, int]
    diagnoses: list[InvigDiagnosis]
    shortfall: dict[str, int]
    loads: dict[str, dict[str, int]]
    stats: dict[str, Any]


# ------------------------------------------------------------------------------------------- posts


def split_seats(size: int, caps: Sequence[int]) -> list[int]:
    """Students per room of a split exam: proportional to the rooms' exam seats (largest remainder; equal shares
    when no room has a seat count)."""
    n = len(caps)
    if n == 0:
        return []
    if n == 1:
        return [max(0, size)]
    weights = [max(0, c) for c in caps]
    total = sum(weights)
    if total == 0:
        weights, total = [1] * n, n
    raw = [size * w / total for w in weights]
    out = [math.floor(x) for x in raw]
    rest = size - sum(out)
    order = sorted(range(n), key=lambda i: (-(raw[i] - out[i]), i))
    for i in order[: max(0, rest)]:
        out[i] += 1
    return out


def build_posts(
    exams: Iterable[ExamSlot], rooms: Mapping[int, ExamRoom], rule: StaffingRule
) -> tuple[list[Post], list[int]]:
    """Posts of a placed exam timetable, and the exams that have no room (online, outside the room pool)."""
    by_room_date: dict[tuple[int, date], list[tuple[ExamSlot, int]]] = defaultdict(list)
    no_room: list[int] = []
    for e in sorted(exams, key=lambda x: (x.date, x.start, x.exam_id)):
        rids = [r for r in dict.fromkeys(e.room_ids)]
        if not rids:
            no_room.append(e.exam_id)
            continue
        seats = split_seats(e.size, [rooms[r].exam_capacity if r in rooms else 0 for r in rids])
        for r, s in zip(rids, seats, strict=True):
            by_room_date[(r, e.date)].append((e, s))
    spi = max(1, int(rule.students_per_invigilator))
    posts: list[Post] = []
    for (rid, d), items in sorted(by_room_date.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        items.sort(key=lambda t: (t[0].start, t[0].end, t[0].exam_id))
        groups: list[list[tuple[ExamSlot, int]]] = []
        end = -1
        for it in items:
            if groups and it[0].start <= end:
                groups[-1].append(it)
                end = max(end, it[0].end)
            else:
                groups.append([it])
                end = it[0].end
        room = rooms.get(rid)
        for g in groups:
            start = min(e.start for e, _s in g)
            stop = max(e.end for e, _s in g)
            seated = sum(s for _e, s in g)
            by_ratio = max(int(rule.min_per_room), math.ceil(seated / spi) if seated else 0)
            if rule.max_per_room is not None:
                by_ratio = min(by_ratio, max(int(rule.min_per_room), int(rule.max_per_room)))
            explicit = sum(
                math.ceil(int(e.invigilators) / max(1, len(set(e.room_ids)))) for e, _s in g if e.invigilators
            )
            posts.append(
                Post(
                    key=f"{d.isoformat()}|{rid}|{start}-{stop}",
                    date=d,
                    start=start,
                    end=stop,
                    room_id=rid,
                    room_code=room.code if room else str(rid),
                    building=room.building if room else "?",
                    exam_ids=tuple(e.exam_id for e, _s in g),
                    labels=tuple(e.label for e, _s in g),
                    seated=seated,
                    required=max(by_ratio, explicit, 0),
                    owner_keys=frozenset().union(*(e.owner_keys for e, _s in g)),
                )
            )
    return posts, no_room


# ------------------------------------------------------------------------------------------- eligibility


def _overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 <= b1 and b0 <= a1


def _conflict(a: Post, b: Post, rest: int) -> bool:
    return a.date == b.date and a.start <= b.end + rest and b.start <= a.end + rest


@dataclass
class Eligibility:
    cands: dict[int, list[int]]  # post index -> person indexes
    excluded: dict[int, Counter[str]]  # post index -> reason -> people
    why: dict[tuple[int, int], str]  # (post, person) -> reason (only for excluded pairs)
    own: set[tuple[int, int]]  # (post, person) pairs of one's own exam


def eligibility(inp: InvigilationInput) -> Eligibility:
    posts, people = inp.posts, inp.people
    cands: dict[int, list[int]] = {k: [] for k in range(len(posts))}
    excluded: dict[int, Counter[str]] = {k: Counter() for k in range(len(posts))}
    why: dict[tuple[int, int], str] = {}
    own: set[tuple[int, int]] = set()
    own_posts: dict[int, list[int]] = defaultdict(list)
    for k, p in enumerate(posts):
        for i, person in enumerate(people):
            if person.key and person.key in p.owner_keys:
                own.add((k, i))
                own_posts[i].append(k)
    for i, person in enumerate(people):
        busy_by_date: dict[date, list[Busy]] = defaultdict(list)
        for b in person.busy:
            busy_by_date[b.date].append(b)
        cap_day = person.max_per_day if person.max_per_day is not None else inp.max_per_day
        for k, p in enumerate(posts):
            reason: str | None = None
            if person.max_duties == 0 or cap_day == 0:
                reason = "no_capacity"
            if reason is None:
                for b in busy_by_date.get(p.date, ()):
                    if _overlap(b.start, b.end, p.start, p.end):
                        reason = b.reason
                        break
            if reason is None and (k, i) in own and inp.own_exam == "forbid":
                reason = "own_exam"
            if reason is None and inp.own_exam == "prefer" and (k, i) not in own:
                for o in own_posts.get(i, ()):
                    q = posts[o]
                    if q.date == p.date and _overlap(q.start, q.end, p.start, p.end):
                        reason = "own_exam_elsewhere"
                        break
            if reason is None:
                cands[k].append(i)
            else:
                excluded[k][reason] += 1
                why[(k, i)] = reason
    return Eligibility(cands, excluded, why, own)


# ------------------------------------------------------------------------------------------- greedy


def _caps(inp: InvigilationInput, i: int) -> tuple[int | None, int | None]:
    p = inp.people[i]
    return (p.max_per_day if p.max_per_day is not None else inp.max_per_day), p.max_duties


def greedy(
    inp: InvigilationInput, el: Eligibility, fixed: Mapping[int, list[int]] | None = None
) -> dict[int, list[int]]:
    """A complete-as-possible plan respecting every hard rule: posts by start time, each filled with the eligible
    people of least (factor-scaled) load. A hint for CP-SAT and the fallback when CP-SAT finds nothing."""
    posts = inp.posts
    taken: dict[int, list[int]] = defaultdict(list)  # person -> post indexes
    load: dict[int, int] = defaultdict(int)
    out: dict[int, list[int]] = {k: list((fixed or {}).get(k, [])) for k in range(len(posts))}
    for k, ps in out.items():
        for i in ps:
            taken[i].append(k)
            load[i] += posts[k].duration
    order = sorted(range(len(posts)), key=lambda k: (posts[k].date, posts[k].start, len(el.cands[k]), posts[k].key))
    for k in order:
        p = posts[k]
        need = p.required - len(out[k])
        if need <= 0:
            continue

        def ok(i: int, k: int = k, p: Post = p) -> bool:
            if i in out[k]:
                return False
            if any(_conflict(posts[o], p, inp.min_rest) for o in taken[i]):
                return False
            day_cap, total_cap = _caps(inp, i)
            if day_cap is not None and sum(1 for o in taken[i] if posts[o].date == p.date) >= day_cap:
                return False
            return not (total_cap is not None and len(taken[i]) >= total_cap)

        free = [i for i in el.cands[k] if ok(i)]
        f = {i: max(1, inp.people[i].load_factor) for i in free}
        free.sort(
            key=lambda i: (-(1 if (k, i) in el.own and inp.own_exam == "prefer" else 0), load[i] * 100 // f[i], i)
        )
        for i in free[:need]:
            out[k].append(i)
            taken[i].append(k)
            load[i] += p.duration
    return out


# ------------------------------------------------------------------------------------------- CP-SAT


def _weight(inp: InvigilationInput, name: str) -> int:
    v = inp.weights.get(name)
    return max(0, int(DEFAULT_WEIGHTS.get(name, 1) if v is None else v))


def _cliques(posts: Sequence[Post], idxs: Sequence[int], rest: int) -> list[list[int]]:
    """Maximal sets of mutually conflicting posts among ``idxs`` (interval graph: sweep over the start points,
    with each end extended by ``rest``)."""
    by_date: dict[date, list[int]] = defaultdict(list)
    for k in idxs:
        by_date[posts[k].date].append(k)
    out: list[list[int]] = []
    for ks in by_date.values():
        points = sorted({posts[k].start for k in ks})
        prev: set[int] = set()
        for t in points:
            cur = {k for k in ks if posts[k].start <= t <= posts[k].end + rest}
            if len(cur) > 1 and not cur <= prev:
                out.append(sorted(cur))
            prev = cur
    return out


def _cp_solve(
    inp: InvigilationInput,
    el: Eligibility,
    fixed: Mapping[int, list[int]],
    hint: Mapping[int, list[int]],
    budget_s: float,
) -> tuple[dict[int, list[int]] | None, str, dict[str, int], dict[str, Any]]:
    from ortools.sat.python import cp_model

    posts, people = inp.posts, inp.people
    m = cp_model.CpModel()
    x: dict[tuple[int, int], Any] = {}
    for k in range(len(posts)):
        for i in el.cands[k]:
            x[(k, i)] = m.new_bool_var(f"x_{k}_{i}")
    for k, ps in fixed.items():
        for i in ps:
            if (k, i) in x:
                m.add(x[(k, i)] == 1)
    short: dict[int, Any] = {}
    for k, p in enumerate(posts):
        terms = [x[(k, i)] for i in el.cands[k]]
        short[k] = m.new_int_var(0, p.required, f"short_{k}")
        m.add(sum(terms) + short[k] == p.required)
    by_person: dict[int, list[int]] = defaultdict(list)
    for k, i in x:
        by_person[i].append(k)
    for i, ks in by_person.items():
        for cl in _cliques(posts, ks, inp.min_rest):
            m.add_at_most_one(x[(k, i)] for k in cl)
        day_cap, total_cap = _caps(inp, i)
        if day_cap is not None:
            per_day: dict[date, list[int]] = defaultdict(list)
            for k in ks:
                per_day[posts[k].date].append(k)
            for d_ks in per_day.values():
                if len(d_ks) > day_cap:
                    m.add(sum(x[(k, i)] for k in d_ks) <= day_cap)
        if total_cap is not None and len(ks) > total_cap:
            m.add(sum(x[(k, i)] for k in ks) <= total_cap)
    det = deterministic_budget(inp, budget_s)
    total_short = sum(short.values())
    hint_short = sum(max(0, p.required - len(hint.get(k, []))) for k, p in enumerate(posts))
    values: dict[tuple[int, int], int] = {(k, i): int(i in hint.get(k, [])) for (k, i) in x}
    stats: dict[str, Any] = {"variables": len(x), "greedy_shortfall": hint_short}
    spent = 0.0
    if hint_short == 0:  # the greedy plan staffs every post: a shortfall of 0 is optimal, no phase 1
        best_short, phase1_optimal = 0, True
        stats["phase1"] = "SKIPPED"
    else:
        for key, v in x.items():
            m.add_hint(v, values[key])
        m.minimize(total_short)
        solver = _solver(inp, det * PHASE1_SHARE)
        st = solver.solve(m)
        spent += float(solver.deterministic_time)
        stats["phase1"] = solver.status_name(st)
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE) and int(round(solver.objective_value)) <= hint_short:
            best_short = int(round(solver.objective_value))
            phase1_optimal = st == cp_model.OPTIMAL
            values = {key: int(solver.value(v)) for key, v in x.items()}
        else:
            best_short, phase1_optimal = hint_short, False
        m.clear_objective()  # type: ignore[no-untyped-call]
        m.clear_hints()  # type: ignore[no-untyped-call]
    stats["phase1_shortfall"] = best_short
    # phase 2: shortfall fixed at its best value, the soft objective
    m.add(total_short <= best_short)
    for key, v in x.items():
        m.add_hint(v, values[key])
    total_demand = sum(p.required * p.duration for p in posts)
    eligible = sorted(by_person)
    fsum = sum(max(1, people[i].load_factor) for i in eligible) or 1
    horizon = sum(p.duration for p in posts) or 1
    mx = m.new_int_var(0, horizon * 100, "max_load")
    spread_terms = []
    day_terms = []
    for i in eligible:
        ks = by_person[i]
        f = max(1, people[i].load_factor)
        load = sum(posts[k].duration * x[(k, i)] for k in ks)
        m.add(load * (10000 // f) <= mx * 100)
        target = math.ceil(total_demand * f / fsum)
        e = m.new_int_var(0, horizon, f"ex_{i}")
        m.add(e >= load - target)
        spread_terms.append(e)
        days_of: dict[date, list[int]] = defaultdict(list)
        for k in ks:
            days_of[posts[k].date].append(k)
        for d_ks in days_of.values():
            if len(d_ks) > 1:
                extra = m.new_int_var(0, len(d_ks), f"day_{i}_{d_ks[0]}")
                m.add(extra >= sum(x[(k, i)] for k in d_ks) - 1)
                day_terms.append(extra)
    own_terms = [x[(k, i)] for (k, i) in el.own if (k, i) in x] if inp.own_exam == "prefer" else []
    prev = {(d.post_key, d.person_id) for d in inp.previous}
    key_idx = {p.key: k for k, p in enumerate(posts)}
    pid_idx = {p.id: i for i, p in enumerate(people)}
    stab_terms = [
        1 - x[(key_idx[a], pid_idx[b])]
        for (a, b) in sorted(prev)
        if a in key_idx and b in pid_idx and (key_idx[a], pid_idx[b]) in x
    ]
    w = {n: _weight(inp, n) for n in DEFAULT_WEIGHTS}
    m.minimize(
        w["max_load"] * mx
        + w["spread"] * sum(spread_terms)
        + w["same_day"] * sum(day_terms)
        - w["own_exam"] * sum(own_terms)
        + w["stability"] * sum(stab_terms)
    )
    s2 = _solver(inp, det * (1 - PHASE1_SHARE) if hint_short else det)
    st2 = s2.solve(m)
    spent += float(s2.deterministic_time)
    stats["phase2"] = s2.status_name(st2)
    stats["deterministic_time"] = round(spent, 3)
    ok2 = st2 in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    if ok2:
        plan = {k: [i for i in el.cands[k] if s2.value(x[(k, i)])] for k in range(len(posts))}
    else:  # no better plan in the budget: the phase-1 / greedy plan (same shortfall, validated by the caller)
        plan = {k: [i for i in el.cands[k] if values[(k, i)]] for k in range(len(posts))}
    optimal = phase1_optimal and st2 == cp_model.OPTIMAL
    return plan, "OPTIMAL" if optimal else "FEASIBLE", breakdown_of(inp, el, plan), stats


def breakdown_of(inp: InvigilationInput, el: Eligibility, plan: Mapping[int, Sequence[int]]) -> dict[str, int]:
    """The soft objective of a plan, term by term, exactly as the CP-SAT model counts it (so a greedy plan and a
    CP-SAT plan are reported alike)."""
    posts, people = inp.posts, inp.people
    w = {n: _weight(inp, n) for n in DEFAULT_WEIGHTS}
    load: dict[int, int] = defaultdict(int)
    per_day: Counter[tuple[int, date]] = Counter()
    own = 0
    for k, ps in plan.items():
        for i in ps:
            load[i] += posts[k].duration
            per_day[(i, posts[k].date)] += 1
            if (k, i) in el.own:
                own += 1
    eligible = {i for ks in el.cands.values() for i in ks}
    fsum = sum(max(1, people[i].load_factor) for i in eligible) or 1
    total_demand = sum(p.required * p.duration for p in posts)
    mx = max((math.ceil(load[i] * (10000 // max(1, people[i].load_factor)) / 100) for i in eligible), default=0)
    spread = sum(max(0, load[i] - math.ceil(total_demand * max(1, people[i].load_factor) / fsum)) for i in eligible)
    same_day = sum(max(0, n - 1) for n in per_day.values())
    key_idx = {p.key: k for k, p in enumerate(posts)}
    pid_idx = {p.id: i for i, p in enumerate(people)}
    prev = [
        (key_idx[d.post_key], pid_idx[d.person_id])
        for d in inp.previous
        if d.post_key in key_idx and d.person_id in pid_idx
    ]
    lost = sum(1 for k, i in prev if i in el.cands[k] and i not in plan.get(k, []))
    return {
        "max_load": w["max_load"] * mx,
        "spread": w["spread"] * spread,
        "same_day": w["same_day"] * same_day,
        "own_exam": -w["own_exam"] * own if inp.own_exam == "prefer" else 0,
        "stability": w["stability"] * lost,
    }


def _solver(inp: InvigilationInput, det_s: float) -> Any:
    """One CP-SAT solver: the input's workers and seed, a deterministic budget (the wall clock is a safety net).
    No LP relaxation and a light presolve: on the Final-sized model (150k Booleans) the LP and probing used the whole
    budget before the search started, and the hinted plan has to survive presolve."""
    from ortools.sat.python import cp_model

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = max(1, int(inp.workers))
    solver.parameters.random_seed = int(inp.seed)
    solver.parameters.max_deterministic_time = max(0.5, det_s)
    solver.parameters.max_time_in_seconds = max(30.0, det_s * 8)
    solver.parameters.linearization_level = 0
    solver.parameters.cp_model_probing_level = 0
    solver.parameters.symmetry_level = 0
    solver.parameters.keep_all_feasible_solutions_in_presolve = True
    return solver


def deterministic_budget(inp: InvigilationInput, budget_s: float | None = None) -> float:
    return max(1.0, float(inp.time_limit_s if budget_s is None else budget_s))


# ------------------------------------------------------------------------------------------- validation


def validate(inp: InvigilationInput, plan: Mapping[int, Sequence[int]]) -> list[str]:
    """Every hard rule a plan breaks (empty: none). Used on the solver's own output and on manual edits."""
    el = eligibility(inp)
    posts = inp.posts
    issues: list[str] = []
    taken: dict[int, list[int]] = defaultdict(list)
    for k, ps in plan.items():
        if len(set(ps)) != len(ps):
            issues.append(f"post {posts[k].key}: a person listed twice")
        if len(ps) > posts[k].required:
            issues.append(f"post {posts[k].key}: {len(ps)} > {posts[k].required} invigilators")
        for i in ps:
            if i not in el.cands[k]:
                issues.append(f"{inp.people[i].id} at {posts[k].key}: {el.why.get((k, i), 'not eligible')}")
            taken[i].append(k)
    for i, ks in taken.items():
        ks = sorted(ks, key=lambda k: (posts[k].date, posts[k].start))
        for a in range(len(ks)):
            for b in range(a + 1, len(ks)):
                if _conflict(posts[ks[a]], posts[ks[b]], inp.min_rest):
                    issues.append(f"{inp.people[i].id}: {posts[ks[a]].key} and {posts[ks[b]].key} at once")
        day_cap, total_cap = _caps(inp, i)
        days_of = Counter(posts[k].date for k in ks)
        if day_cap is not None and any(v > day_cap for v in days_of.values()):
            issues.append(f"{inp.people[i].id}: more than {day_cap} duties a day")
        if total_cap is not None and len(ks) > total_cap:
            issues.append(f"{inp.people[i].id}: more than {total_cap} duties")
    return issues


# ------------------------------------------------------------------------------------------- diagnosis


def _index(posts: Sequence[Post], key: str) -> int:
    return next(k for k, p in enumerate(posts) if p.key == key)


def _span(p: Post) -> str:
    return f"{p.date.isoformat()} P{p.start}-P{p.end}"


def _hall_witness(inp: InvigilationInput, el: Eligibility, k: int) -> tuple[list[int], set[int]] | None:
    """A minimal set of posts that overlap ``k`` at one period and together need more people than are eligible
    for any of them (Hall's condition fails), or None."""
    posts = inp.posts
    p = posts[k]
    best: tuple[list[int], set[int]] | None = None
    for t in range(p.start, p.end + inp.min_rest + 1):
        clique = [
            q
            for q in range(len(posts))
            if q != k and posts[q].date == p.date and posts[q].start <= t <= posts[q].end + inp.min_rest
        ]
        chosen = [k]
        union = set(el.cands[k])
        need = p.required
        found = need > len(union)
        rest = sorted(clique, key=lambda q: (len(set(el.cands[q]) - union), posts[q].key))
        while not found and rest:
            rest.sort(key=lambda q: (len(set(el.cands[q]) - union), -posts[q].required, posts[q].key))
            q = rest.pop(0)
            chosen.append(q)
            union |= set(el.cands[q])
            need += posts[q].required
            found = need > len(union)
        if not found:
            continue
        # deletion filter: drop every post whose removal keeps the deficit (minimal conflict set)
        for q in list(chosen):
            if q == k or len(chosen) == 1:
                continue
            trial = [c for c in chosen if c != q]
            u: set[int] = set().union(*(set(el.cands[c]) for c in trial))
            if sum(posts[c].required for c in trial) > len(u):
                chosen = trial
        u = set().union(*(set(el.cands[c]) for c in chosen))
        if best is None or len(chosen) < len(best[0]):
            best = (sorted(chosen, key=lambda c: posts[c].key), u)
    return best


def explain(
    inp: InvigilationInput, el: Eligibility, plan: Mapping[int, Sequence[int]], shortfall: Mapping[int, int]
) -> list[InvigDiagnosis]:
    posts = inp.posts
    out: list[InvigDiagnosis] = []
    covered: set[int] = set()
    for k in sorted(shortfall, key=lambda k: (posts[k].date, posts[k].start, posts[k].key)):
        miss = shortfall[k]
        if miss <= 0 or k in covered:
            continue
        p = posts[k]
        n_c = len(el.cands[k])
        reasons = dict(sorted(el.excluded[k].items()))
        base = {
            "date": p.date.isoformat(),
            "start": p.start,
            "end": p.end,
            "room_id": p.room_id,
            "room_code": p.room_code,
            "required": p.required,
            "assigned": len(plan.get(k, [])),
            "missing": miss,
            "seated": p.seated,
            "excluded": reasons,
        }
        if n_c < p.required:
            out.append(
                InvigDiagnosis(
                    "no_candidates",
                    "error",
                    f"{p.room_code} {_span(p)} ({', '.join(p.labels)}) needs {p.required} invigilator(s) but only "
                    f"{n_c} of {len(inp.people)} people may invigilate it ({_reasons_en(reasons)})",
                    [p.key],
                    list(p.exam_ids),
                    [],
                    {**base, "candidates": n_c, "add_people": p.required - n_c},
                )
            )
            continue
        wit = _hall_witness(inp, el, k)
        if wit is not None:
            ks, union = wit
            need = sum(posts[q].required for q in ks)
            covered |= {q for q in ks if shortfall.get(q, 0) > 0}
            out.append(
                InvigDiagnosis(
                    "slot_shortage",
                    "error",
                    f"On {p.date.isoformat()} around P{p.start}-P{p.end}, {len(ks)} room(s) "
                    f"({', '.join(posts[q].room_code for q in ks)}) need {need} invigilators together but only "
                    f"{len(union)} people are free for them",
                    [posts[q].key for q in ks],
                    sorted({e for q in ks for e in posts[q].exam_ids}),
                    [],
                    {
                        **base,
                        "posts": len(ks),
                        "required_total": need,
                        "people_free": len(union),
                        "add_people": need - len(union),
                        "rooms": [posts[q].room_code for q in ks],
                    },
                )
            )
            continue
        capped = []
        for i in el.cands[k]:
            day_cap, total_cap = _caps(inp, i)
            mine = [q for q, ps in plan.items() if i in ps]
            today = sum(1 for q in mine if posts[q].date == p.date)
            if (day_cap is not None and today >= day_cap) or (total_cap is not None and len(mine) >= total_cap):
                capped.append(inp.people[i].id)
        if capped:
            out.append(
                InvigDiagnosis(
                    "cap_shortage",
                    "error",
                    f"{p.room_code} {_span(p)} is {miss} invigilator(s) short: {len(capped)} eligible people have "
                    "reached their daily or total duty limit",
                    [p.key],
                    list(p.exam_ids),
                    capped[:50],
                    {**base, "capped": len(capped), "max_per_day": inp.max_per_day},
                )
            )
            continue
        # the eligible people are all on duty in rooms that overlap this one (a chain of overlapping exams)
        busy_in = sorted(
            {
                posts[q].key
                for q, ps in plan.items()
                if q != k and _conflict(posts[q], p, inp.min_rest) and set(ps) & set(el.cands[k])
            }
        )
        out.append(
            InvigDiagnosis(
                "overlap_shortage",
                "error",
                f"{p.room_code} {_span(p)} is {miss} invigilator(s) short: everyone eligible is on duty in an "
                f"overlapping room ({len(busy_in)} room(s))",
                [p.key, *busy_in],
                sorted({e for q in [p.key, *busy_in] for e in posts[_index(posts, q)].exam_ids}),
                [],
                {**base, "overlapping_posts": busy_in, "add_people": miss},
            )
        )
    return out


_REASON_EN = {
    "teaching": "teaching",
    "unavailable": "unavailable",
    "booking": "own booking",
    "own_exam": "own course's exam",
    "own_exam_elsewhere": "at their own exam",
    "no_capacity": "no duties allowed",
}


def _reasons_en(reasons: Mapping[str, int]) -> str:
    return ", ".join(f"{v} {_REASON_EN.get(k, k)}" for k, v in reasons.items()) or "nobody in the pool"


# ------------------------------------------------------------------------------------------- solve


def solve_invigilation(inp: InvigilationInput) -> InvigilationResult:
    t0 = time.perf_counter()
    posts, people = inp.posts, inp.people
    key_idx = {p.key: k for k, p in enumerate(posts)}
    pid_idx = {p.id: i for i, p in enumerate(people)}
    el = eligibility(inp)
    diags: list[InvigDiagnosis] = []
    fixed: dict[int, list[int]] = defaultdict(list)
    lock_conflicts = 0
    for d in sorted(inp.locks, key=lambda d: (d.post_key, d.person_id)):
        k, i = key_idx.get(d.post_key), pid_idx.get(d.person_id)
        if k is None or i is None:
            diags.append(
                InvigDiagnosis(
                    "lock_stale",
                    "warning",
                    f"locked duty {d.person_id} at {d.post_key} no longer matches the exam timetable or the pool",
                    [d.post_key],
                    [],
                    [d.person_id],
                    {"post_key": d.post_key, "person_id": d.person_id},
                )
            )
            continue
        trial = {**{q: list(v) for q, v in fixed.items()}, k: [*fixed.get(k, []), i]}
        problems = validate(inp, trial)
        if problems:
            lock_conflicts += 1
            diags.append(
                InvigDiagnosis(
                    "locked_conflict",
                    "error",
                    f"locked duty {people[i].name} at {posts[k].room_code} {_span(posts[k])} breaks a hard rule: "
                    f"{problems[-1]}",
                    [d.post_key],
                    list(posts[k].exam_ids),
                    [d.person_id],
                    {
                        "post_key": d.post_key,
                        "person_id": d.person_id,
                        "reason": el.why.get((k, i)),
                        "problems": problems,
                    },
                )
            )
            continue
        fixed[k].append(i)
    hint = greedy(inp, el, fixed)
    plan: dict[int, list[int]] | None
    breakdown: dict[str, int] = {}
    cp_stats: dict[str, Any] = {}
    status = "FEASIBLE"
    engine = "cpsat"
    if not posts:
        plan, status, engine = {}, "OPTIMAL", "none"
    else:
        try:
            plan, status, breakdown, cp_stats = _cp_solve(inp, el, fixed, hint, deterministic_budget(inp))
        except ModuleNotFoundError:  # pragma: no cover - OR-Tools is a hard dependency of the backend
            plan = None
        if plan is None:
            plan, status, engine = hint, "FEASIBLE", "greedy"
    problems = validate(inp, plan)
    if problems:  # never ship a plan that breaks a hard rule: fall back to the greedy plan (validated too)
        plan, engine = hint, "greedy"
        problems = validate(inp, plan)
        if problems:
            return InvigilationResult("ERROR", [], 0, 0, {}, diags, {}, {}, {"problems": problems[:20]})
    breakdown = breakdown_of(inp, el, plan)
    shortfall = {k: posts[k].required - len(plan.get(k, [])) for k in range(len(posts))}
    shortfall = {k: v for k, v in shortfall.items() if v > 0}
    diags.extend(explain(inp, el, plan, shortfall))
    required = sum(p.required for p in posts)
    filled = required - sum(shortfall.values())
    infeasible = bool(shortfall) or lock_conflicts > 0
    # hard score: the share of hard items that hold (every required invigilator seat and every lock)
    items = required + len(inp.locks)
    held = filled + len(inp.locks) - lock_conflicts
    hard = 100 if not infeasible else min(99, math.floor(100 * held / items) if items else 0)
    loads: dict[str, dict[str, int]] = {}
    for k, ps in plan.items():
        for i in ps:
            e = loads.setdefault(people[i].id, {"duties": 0, "periods": 0, "own_exam": 0, "days": 0})
            e["duties"] += 1
            e["periods"] += posts[k].duration
            if (k, i) in el.own:
                e["own_exam"] += 1
    days: dict[str, set[date]] = defaultdict(set)
    for k, ps in plan.items():
        for i in ps:
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
    duties = [
        Duty(posts[k].key, people[i].id, locked=i in fixed.get(k, []))
        for k in sorted(plan, key=lambda k: posts[k].key)
        for i in sorted(plan[k], key=lambda i: people[i].id)
    ]
    return InvigilationResult(
        status="INFEASIBLE" if infeasible else status,
        duties=duties,
        hard_score=hard,
        soft_score=soft,
        objective_breakdown=breakdown,
        diagnoses=diags,
        shortfall={posts[k].key: v for k, v in sorted(shortfall.items())},
        loads=dict(sorted(loads.items())),
        stats={
            "engine": engine,
            "posts": len(posts),
            "people": len(people),
            "eligible_people": len(eligible),
            "required": required,
            "filled": filled,
            "missing": required - filled,
            "locks": len(inp.locks),
            "lock_conflicts": lock_conflicts,
            "max_periods": round(max(scaled) / 100 * 100) / 100 if scaled else 0,
            "fair_share_periods": round(lb / 100, 2),
            "wall_s": round(time.perf_counter() - t0, 3),
            "workers": inp.workers,
            "seed": inp.seed,
            **cp_stats,
        },
    )
