"""Solver weights learned from manual edits (adaptive scheduling AS-14, inverse optimisation lite;
docs/research/2026-10-17-adaptive-scheduling.md §3.3).

**Evidence.**  For every manual move (``assignments.origin`` MANUAL / AI_EDIT) in a run against its parent run, both
plans are scored by ``solver/evaluate.py`` with every soft term at weight 1, so ``ΔΦ_k = Φ_k(after) − Φ_k(before)``
is in the term's own units (one wrong building, ten empty seats, ...).  The planner chose *after*, so under the
weights they have in mind ``Σ_k w_k ΔΦ_k < 0``.  An edit that improves term *i* and worsens term *j* is one
**agreement** "i before j".  Locks keep the solver's own placement and carry no trade, so they are not used.

**Learning.**  Two small linear programs (OR-Tools GLOP, deterministic):

* :func:`learn` — the weight *ratios* that explain the edits best: the centre of the cone ``{w ≥ 0 : w·ΔΦ_e ≤ 0}``
  (Chebyshev centre on ``Σ w = Σ current``, slack for edits that contradict each other).  B9 checks it against
  synthetic edits made with known weights (Kendall τ of the ratios ≥ 0.8).
* :func:`proposal` — the **smallest change** of the current weights (L1) under which every edit costs at least one
  unit less than what it replaced (``w·ΔΦ_e ≤ −1``, slack again), no term below 1 that is on today; rounded to whole
  numbers.  It becomes a **draft** season-profile version with a TR/EN explanation ("12 düzenlemenin 10'unda bina
  tercihi boş koltuk karşısında öne çıktı. Öneri: building_preference 5 → 8.") and evidence (run ids and counts,
  no names).  Fewer than :data:`MIN_EDITS` edits propose nothing (``needs``).  Only an admin activates a draft.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from app.solver.model import Assignment as SA
from app.solver.model import Constraint, Event, Room, SolverInput
from app.solver.scoring import evaluate
from app.solver.weights import DEFAULT_WEIGHTS

MIN_EDITS = 5
MAX_WEIGHT = 10_000
SLACK_COST = 10.0
DEFAULTS: dict[str, int] = dict(DEFAULT_WEIGHTS)

#: plain names of the soft terms (TR, EN) for explanations
TERM_NAMES: dict[str, tuple[str, str]] = {
    "room_preference": ("derslik tercihi", "the room preference"),
    "building_preference": ("bina tercihi", "the building preference"),
    "learned_room_preference": ("öğrenilmiş derslik tercihi", "the learned room preference"),
    "learned_building_preference": ("öğrenilmiş bina tercihi", "the learned building preference"),
    "min_capacity_waste": ("boş koltuk", "empty seats"),
    "day_window": ("gün penceresi", "the day window"),
    "stability": ("değişiklik", "stability"),
    "stability_room": ("derslik değişikliği", "room changes"),
    "stability_time": ("saat değişikliği", "time changes"),
    "same_room_group": ("aynı derslik", "the same room"),
    "same_room_across_weeks": ("haftalar boyunca aynı derslik", "the same room across weeks"),
    "exam_gap": ("sınav aralığı", "the exam gap"),
    "max_exams_per_day": ("günlük sınav sınırı", "exams per day"),
    "evening_programs_in_buildings": ("ikinci öğretim binaları", "evening programme buildings"),
    "peak_smoothing": ("yoğun saat", "peak hours"),
    "capacity": ("kapasite", "capacity"),
    "fixed_time": ("sabit saat", "the fixed time"),
    "room_tags": ("derslik etiketi", "room tags"),
    "room_pin": ("derslik sabitleme", "the pinned room"),
    "room_forbid": ("yasak derslik", "the forbidden room"),
    "room_closed": ("kapalı derslik", "the closed room"),
}


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def _name(key: str) -> tuple[str, str]:
    return TERM_NAMES.get(key, (key, key))


_LOC_DIGIT = {1: "inde", 2: "sinde", 3: "ünde", 4: "ünde", 5: "inde", 6: "sında", 7: "sinde", 8: "inde", 9: "unda"}
_LOC_TENS = {1: "unda", 2: "sinde", 3: "unda", 4: "ında", 5: "sinde", 6: "ında", 7: "inde", 8: "inde", 9: "ında"}


def tr_locative(n: int) -> str:
    """``10'unda``, ``12'sinde``, ``40'ında``: the Turkish possessive locative of a number (vowel harmony on the
    last spoken word)."""
    if n == 0:
        return "0'ında"
    if n % 10:
        return f"{n}'{_LOC_DIGIT[n % 10]}"
    if n % 100:
        return f"{n}'{_LOC_TENS[(n // 10) % 10]}"
    if n % 1000:
        return f"{n}'ünde"  # yüz
    return f"{n}'inde"  # bin


# ------------------------------------------------------------------------------------------------ evidence


@dataclass(frozen=True)
class Edit:
    """One manual move: ``deltas`` = Φ(after) − Φ(before) per soft term, in units."""

    deltas: Mapping[str, int]
    run_id: int | None = None
    parent_run_id: int | None = None
    event_id: int | None = None


def unit_weights(inp: SolverInput) -> dict[str, int]:
    """Every soft term at 1 (a term that is off today stays off: switching it on would add a rule)."""
    keys = set(DEFAULT_WEIGHTS) | set(inp.weights)
    out: dict[str, int] = {}
    for k in sorted(keys):
        cur = inp.weights.get(k, DEFAULT_WEIGHTS.get(k, 1))
        out[k] = 1 if int(cur) > 0 else 0
    return out


def edit_deltas(inp: SolverInput, before: Sequence[SA], after: Sequence[SA]) -> dict[str, int]:
    """ΔΦ per soft term (units) of replacing the plan ``before`` with ``after`` (nonzero terms only)."""
    probe = replace(inp, weights=unit_weights(inp))
    a, b = evaluate(probe, list(before)).penalties, evaluate(probe, list(after)).penalties
    out = {k: int(b.get(k, 0)) - int(a.get(k, 0)) for k in sorted(set(a) | set(b))}
    return {k: v for k, v in out.items() if v}


def agreements(edits: Iterable[Edit]) -> Counter[tuple[str, str]]:
    """(i, j) -> edits that improved term i at the price of term j ("i before j")."""
    out: Counter[tuple[str, str]] = Counter()
    for e in edits:
        better = [k for k, v in e.deltas.items() if v < 0]
        worse = [k for k, v in e.deltas.items() if v > 0]
        for i in better:
            for j in worse:
                out[(i, j)] += 1
    return out


def kendall_tau(x: Sequence[float], y: Sequence[float]) -> float:
    """Kendall's τ-a of two equally long sequences."""
    n = len(x)
    if n < 2:
        return 1.0

    def sign(v: float) -> int:
        return (v > 0) - (v < 0)

    s = sum(sign(x[i] - x[j]) * sign(y[i] - y[j]) for i in range(n) for j in range(i + 1, n))
    return s / (n * (n - 1) / 2)


def ratio_vector(weights: Mapping[str, float], keys: Sequence[str]) -> list[float]:
    """``w_i / w_j`` for every pair i < j of ``keys`` (a zero weight counts as 1e-9)."""
    out = []
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            out.append(max(1e-9, float(weights[keys[a]])) / max(1e-9, float(weights[keys[b]])))
    return out


# ------------------------------------------------------------------------------------------------ learning


@dataclass
class Learned:
    terms: list[str]
    weights: dict[str, float]  # recovered ratios, scaled to Σ current over ``terms``
    margin: float
    explained: int  # edits with w·ΔΦ < 0 under the recovered weights
    edits: int
    pairs: Counter[tuple[str, str]] = field(default_factory=Counter)


def _terms(edits: Sequence[Edit]) -> list[str]:
    from app.services.seasons import weight_keys

    known = set(weight_keys())
    return sorted({k for e in edits for k, v in e.deltas.items() if v and k in known})


def _lp() -> Any:
    from ortools.linear_solver import pywraplp

    solver = pywraplp.Solver.CreateSolver("GLOP")
    assert solver is not None
    return solver


def learn(edits: Sequence[Edit], current: Mapping[str, int]) -> Learned:
    terms = _terms(edits)
    edits = sorted(edits, key=lambda e: (sorted(e.deltas.items()), e.run_id or 0, e.event_id or 0))
    pairs = agreements(edits)
    if not terms:
        return Learned([], {}, 0.0, 0, len(edits), pairs)
    total = float(sum(max(1, int(current.get(k, DEFAULTS.get(k, 1)))) for k in terms))
    s = _lp()
    inf = s.infinity()
    w = {k: s.NumVar(0.0, inf, f"w_{k}") for k in terms}
    t = s.NumVar(0.0, inf, "t")
    s.Add(sum(w.values()) == total)
    for k in terms:
        s.Add(w[k] >= t)
    slacks = []
    for n, e in enumerate(edits):
        d = {k: float(v) for k, v in e.deltas.items() if k in w}
        norm = sum(v * v for v in d.values()) ** 0.5
        if not norm:
            continue
        sl = s.NumVar(0.0, inf, f"s_{n}")
        slacks.append(sl)
        s.Add(sum(w[k] * (v / norm) for k, v in d.items()) + t <= sl)
    s.Maximize(t - SLACK_COST * sum(slacks))
    s.Solve()
    weights = {k: round(w[k].solution_value(), 6) for k in terms}
    explained = sum(1 for e in edits if sum(weights.get(k, 0.0) * v for k, v in e.deltas.items()) < 0)
    return Learned(terms, weights, round(t.solution_value(), 6), explained, len(edits), pairs)


def _explained(weights: Mapping[str, float], edits: Sequence[Edit]) -> int:
    return sum(1 for e in edits if sum(float(weights.get(k, 0)) * v for k, v in e.deltas.items()) < 0)


def minimal_change(edits: Sequence[Edit], current: Mapping[str, int], terms: Sequence[str]) -> dict[str, int]:
    """The whole-number weights closest (L1) to ``current`` under which every edit is at least one unit cheaper
    than what it replaced (slack where edits contradict each other); a term on today stays >= 1."""
    s = _lp()
    inf = s.infinity()
    cur = {k: int(current.get(k, DEFAULTS.get(k, 1))) for k in terms}
    w = {k: s.NumVar(1.0 if cur[k] >= 1 else 0.0, float(MAX_WEIGHT), f"w_{k}") for k in terms}
    u = {k: s.NumVar(0.0, inf, f"u_{k}") for k in terms}
    for k in terms:
        s.Add(u[k] >= w[k] - cur[k])
        s.Add(u[k] >= cur[k] - w[k])
    slacks = []
    for n, e in enumerate(edits):
        d = {k: float(v) for k, v in e.deltas.items() if k in w}
        if not d:
            continue
        sl = s.NumVar(0.0, inf, f"s_{n}")
        slacks.append(sl)
        s.Add(sum(w[k] * v for k, v in d.items()) <= -1.0 + sl)
    s.Minimize(sum(u.values()) + SLACK_COST * sum(slacks))
    s.Solve()
    out = {k: int(round(w[k].solution_value())) for k in terms}
    for k in terms:
        if cur[k] >= 1:
            out[k] = max(1, out[k])
    return out


def confidence_of(n: int) -> str:
    if n < MIN_EDITS:
        return "none"
    return "low" if n < 12 else ("medium" if n < 30 else "high")


def proposal(learned: Learned, current: Mapping[str, int], edits: Sequence[Edit]) -> dict[str, Any] | None:
    """The draft weight change (or ``None``: too few edits, or the current weights already explain them)."""
    if len(edits) < MIN_EDITS or not learned.terms:
        return None
    ordered = sorted(edits, key=lambda e: (sorted(e.deltas.items()), e.run_id or 0, e.event_id or 0))
    cur = {k: int(current.get(k, DEFAULTS.get(k, 1))) for k in learned.terms}
    new = minimal_change(ordered, cur, learned.terms)
    changed = [k for k in learned.terms if new[k] != cur[k]]
    changes: list[dict[str, Any]] = [{"key": k, "current": cur[k], "proposed": new[k]} for k in changed]
    if not changes:
        return None
    now, then = _explained(cur, ordered), _explained(new, ordered)
    if then <= now:
        return None
    pairs = learned.pairs
    # the pair that speaks most for the largest change: raised i over some j, or some i over a lowered j
    k = max(changed, key=lambda x: (abs(new[x] - cur[x]) / max(1, cur[x]), x))
    if new[k] > cur[k]:
        cands = [((k, j), n) for (i, j), n in pairs.items() if i == k]
    else:
        cands = [((i, k), n) for (i, j), n in pairs.items() if j == k]
    if cands:
        (i, j), m = max(cands, key=lambda x: (x[1], x[0]))
        both = m + pairs.get((j, i), 0)
        (ti, ei), (tj, ej) = _name(i), _name(j)
        lead_tr = f"{both} düzenlemenin {tr_locative(m)} {ti}, {tj} karşısında öne çıktı."
        lead_en = f"In {m} of {both} edits {ei} came before {ej}."
    else:
        lead_tr = f"{len(ordered)} düzenleme {_name(k)[0]} ağırlığının değişmesini gerektiriyor."
        lead_en = f"{len(ordered)} edits call for a different weight of {_name(k)[1]}."
    arrows = ", ".join(f"{c['key']} {c['current']} → {c['proposed']}" for c in changes)
    explanation = _t(f"{lead_tr} Öneri: {arrows}.", f"{lead_en} Proposal: {arrows}.")
    run_ids = sorted({e.run_id for e in ordered if e.run_id is not None})
    parent_ids = sorted({e.parent_run_id for e in ordered if e.parent_run_id is not None})
    evidence = {
        "edits": len(ordered),
        "run_ids": run_ids,
        "parent_run_ids": parent_ids,
        "pairs": [
            {"before": i, "after": j, "edits": n}
            for (i, j), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        ],
        "term_edits": {t: sum(1 for e in ordered if e.deltas.get(t)) for t in learned.terms},
        "explained_now": now,
        "explained_proposed": then,
        "recovered_ratios": learned.weights,
        "method": "inverse optimisation lite: minimal L1 change with w·ΔΦ <= -1 per edit (GLOP)",
    }
    return {
        "status": "draft",
        "solver_weights": {c["key"]: c["proposed"] for c in changes},
        "changes": changes,
        "explanation": explanation,
        "evidence": evidence,
        "edits_explained": then,
        "edits_explained_now": now,
    }


def propose(edits: Sequence[Edit], current: Mapping[str, int]) -> dict[str, Any]:
    """Learning + proposal on edits that are already scored (no database)."""
    n = len(edits)
    if n < MIN_EDITS:
        return {
            "edits": n,
            "confidence": "none",
            "needs": _t(
                f"En az {MIN_EDITS} elle düzenleme gerekli (şu an {n})",
                f"At least {MIN_EDITS} manual edits are needed (now {n})",
            ),
            "learned": None,
            "proposal": None,
        }
    learned = learn(edits, current)
    p = proposal(learned, current, edits)
    return {
        "edits": n,
        "confidence": confidence_of(n),
        "needs": None
        if p is not None
        else _t(
            "Düzenlemeler bugünkü ağırlıklarla zaten açıklanıyor; değişiklik önerilmedi",
            "The current weights already explain the edits; no change proposed",
        ),
        "learned": {"terms": learned.terms, "weights": learned.weights, "explained": learned.explained},
        "proposal": p,
    }


# ------------------------------------------------------------------------------------------------ synthetic (B9)

SYNTH_TERMS = ("room_preference", "building_preference", "day_window", "min_capacity_waste")


def synthetic_input(seed: int = 0) -> SolverInput:
    """A toy term (two buildings, three sizes each, 24 classes with room and building wishes and a soft day window)
    where moving one class trades the four :data:`SYNTH_TERMS` against each other."""
    rng = random.Random(seed)
    rooms = tuple(
        Room(id=i + 1, code=f"{b}{cap}", capacity=cap, exam_capacity=cap // 2, building=b, tags=frozenset())
        for i, (b, cap) in enumerate((b, c) for b in ("A", "B") for c in (30, 60, 120))
    )
    events = []
    for i in range(1, 25):
        size = rng.choice((20, 25, 40, 55, 90))
        fits = [r.id for r in rooms if r.capacity >= size]
        events.append(
            Event(
                id=i,
                kind="course",
                label=f"S{i}",
                size=size,
                duration=2,
                weeks=frozenset({1}),
                fixed_day=None,
                fixed_start=None,
                allowed_days=frozenset({1, 2, 3, 4, 5}),
                latest_end=12,
                preferred_room_ids=(rng.choice(fits),),
                preferred_building=rng.choice(("A", "B")),
            )
        )
    window = Constraint("day_window", {"days": [1, 2, 3, 4, 5], "earliest": 3, "latest": 8}, hard=False)
    return SolverInput(
        rooms=rooms, events=tuple(events), constraints=(window,), weeks=(1,), days=(1, 2, 3, 4, 5), periods_per_day=12
    )


def _random_placement(rng: random.Random, inp: SolverInput, e: Event) -> SA:
    fits = [r.id for r in inp.rooms if r.capacity >= e.size]
    start = rng.randint(1, inp.periods_per_day - e.duration + 1)
    return SA(e.id, rng.choice(sorted(e.allowed_days)), start, start + e.duration - 1, (rng.choice(fits),), e.weeks)


def synthetic_edits(true_weights: Mapping[str, int], *, n: int = 60, seed: int = 0, noise: float = 0.0) -> list[Edit]:
    """``n`` edits a planner with ``true_weights`` would make: for a random class, of two random placements the
    planner keeps the one that costs less under ``true_weights`` (ties are skipped; with ``noise`` the other one).
    Both plans are scored by ``evaluate`` (units per term)."""
    rng = random.Random(seed)
    inp = synthetic_input(seed)
    base = {e.id: _random_placement(rng, inp, e) for e in inp.events}
    probe = replace(inp, weights=unit_weights(inp))
    out: list[Edit] = []
    tries = 0
    while len(out) < n and tries < n * 50:
        tries += 1
        e = inp.events[rng.randrange(len(inp.events))]
        a, b = _random_placement(rng, inp, e), _random_placement(rng, inp, e)
        plan_a = [*(x for k, x in base.items() if k != e.id), a]
        plan_b = [*(x for k, x in base.items() if k != e.id), b]
        pa, pb = evaluate(probe, plan_a).penalties, evaluate(probe, plan_b).penalties
        ca = sum(true_weights.get(k, 0) * v for k, v in pa.items())
        cb = sum(true_weights.get(k, 0) * v for k, v in pb.items())
        if ca == cb:
            continue
        before, after = (plan_a, plan_b) if cb < ca else (plan_b, plan_a)
        if noise and rng.random() < noise:
            before, after = after, before
        d = edit_deltas(inp, before, after)
        if not d:
            continue
        out.append(Edit(d, run_id=1, parent_run_id=0, event_id=e.id))
    return out


# ------------------------------------------------------------------------------------------------ database


async def _parent_plan(session: Any, parent: Any, members: Mapping[int, list[int]]) -> dict[int, SA]:
    from sqlalchemy import select

    from app.models import Assignment
    from app.services.solver_bridge import solver_assignments_of

    stored = solver_assignments_of(parent)
    if stored is not None:
        return {a.event_id: a for a in stored}
    head_of = {m: h for h, ms in members.items() for m in ms}
    out: dict[int, SA] = {}
    rows = (
        await session.execute(
            select(Assignment)
            .where(Assignment.run_id == parent.id, Assignment.archived.is_(False))
            .order_by(Assignment.id)
        )
    ).scalars()
    for a in rows:
        if a.meeting_request_id is None:
            continue
        eid = head_of.get(int(a.meeting_request_id))
        if eid is None or eid in out:
            continue
        ws = frozenset(int(w) for w in (a.weeks or ([a.week] if a.week else [])))
        out[eid] = SA(eid, int(a.day), int(a.start_period), int(a.end_period), tuple(int(r) for r in a.room_ids), ws)
    return out


async def edits_for_term(session: Any, term_id: int) -> tuple[list[Edit], dict[str, Any]]:
    """Scored manual moves of the term's runs against their parent runs, and the input of the last parent."""
    from sqlalchemy import select

    from app.models import Assignment, ScheduleRun
    from app.services.solver_bridge import build_solver_input

    children = list(
        (
            await session.execute(
                select(ScheduleRun)
                .where(
                    ScheduleRun.term_id == term_id,
                    ScheduleRun.parent_run_id.is_not(None),
                    ScheduleRun.kind == "COURSE",
                )
                .order_by(ScheduleRun.id)
            )
        ).scalars()
    )
    edits: list[Edit] = []
    info: dict[str, Any] = {"runs": [], "skipped": Counter()}
    cache: dict[int, tuple[SolverInput, dict[int, list[int]], dict[int, SA]]] = {}
    for child in children:
        moved = list(
            (
                await session.execute(
                    select(Assignment)
                    .where(
                        Assignment.run_id == child.id,
                        Assignment.archived.is_(False),
                        Assignment.meeting_request_id.is_not(None),
                        Assignment.origin.in_(("MANUAL", "AI_EDIT")),
                    )
                    .order_by(Assignment.id)
                )
            ).scalars()
        )
        if not moved:
            continue
        parent = await session.get(ScheduleRun, child.parent_run_id)
        if parent is None:
            info["skipped"]["no_parent"] += len(moved)
            continue
        if parent.id not in cache:
            probe = ScheduleRun(
                term_id=parent.term_id,
                kind=parent.kind,
                horizon=parent.horizon,
                horizon_params=dict(parent.horizon_params or {}),
                params=dict(parent.params or {}),
                stats=dict(parent.stats or {}),
            )
            inp, members = await build_solver_input(session, probe)
            cache[parent.id] = (inp, members, await _parent_plan(session, parent, members))
        inp, members, before = cache[parent.id]
        head_of = {m: h for h, ms in members.items() for m in ms}
        seen: set[int] = set()
        n_run = 0
        for a in moved:
            eid = head_of.get(int(a.meeting_request_id))
            if eid is None:
                info["skipped"]["not_in_input"] += 1
                continue
            if eid in seen:
                continue  # per-week rows and joint lectures: one edit per class
            seen.add(eid)
            prev = before.get(eid)
            ws = frozenset(int(w) for w in (a.weeks or ([a.week] if a.week else []))) or (
                prev.weeks if prev else frozenset(inp.weeks)
            )
            new = SA(eid, int(a.day), int(a.start_period), int(a.end_period), tuple(int(r) for r in a.room_ids), ws)
            after = {**before, eid: new}
            d = edit_deltas(inp, list(before.values()), list(after.values()))
            if not d:
                info["skipped"]["no_soft_change"] += 1
                continue
            edits.append(Edit(d, run_id=child.id, parent_run_id=parent.id, event_id=eid))
            n_run += 1
        if n_run:
            info["runs"].append({"run_id": child.id, "parent_run_id": parent.id, "edits": n_run})
    info["skipped"] = dict(info["skipped"])
    return edits, info


async def _write_draft(session: Any, term: Any, p: dict[str, Any], actor: Any) -> Any:
    from sqlalchemy import select

    from app.models.seasons import SeasonProfile
    from app.services import seasons

    season = seasons.season_of(term)
    season_key = season if season in ("BAHAR", "GUZ", "YAZ", "FINAL", "BUT") else "*"
    active = await seasons.resolve_profile(session, season_key, "LECTURE")
    key = (
        active.key
        if active is not None and active.id is not None
        else f"learned-{season_key.lower()}".replace("*", "all")
    )
    base_weights: dict[str, int] = dict(active.solver_weights) if active is not None and active.id is not None else {}
    data = {
        "solver_weights": {**base_weights, **p["solver_weights"]},
        "explanation": p["explanation"],
        "evidence": p["evidence"],
    }
    draft = (
        (
            await session.execute(
                select(SeasonProfile)
                .where(SeasonProfile.key == key, SeasonProfile.status == "draft", SeasonProfile.origin == "learned")
                .order_by(SeasonProfile.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if draft is not None:
        return await seasons.update_profile(session, draft.id, data, actor=actor)
    if active is not None and active.id is not None:
        row = await seasons.update_profile(session, active.id, data, actor=actor)
        row.origin = "learned"
        await session.flush()
        return row
    lab = {"BAHAR": ("Bahar", "Spring"), "GUZ": ("Güz", "Autumn"), "YAZ": ("Yaz", "Summer")}.get(
        season_key, (season_key, season_key)
    )
    return await seasons.create_profile(
        session,
        {
            "key": key,
            "name_tr": f"{lab[0]} – öğrenilmiş ağırlıklar",
            "name_en": f"{lab[1]} – learned weights",
            "applies_to": [{"season": season_key, "period_kind": "LECTURE"}],
            **data,
        },
        actor=actor,
        origin="learned",
    )


async def propose_for_term(session: Any, term_id: int, *, actor: Any = None) -> dict[str, Any]:
    """``POST /learning/weights/propose {term_id}``: learn from the term's manual edits and write (or refresh) one
    **draft** season-profile version.  Nothing is activated; the caller commits."""
    from app.models import ScheduleRun, Term
    from app.services import seasons

    term = await session.get(Term, term_id)
    if term is None:
        raise LookupError(term_id)
    edits, info = await edits_for_term(session, term_id)
    probe = ScheduleRun(term_id=term_id, kind="COURSE", horizon="TERM", params={})
    eff = await seasons.effective_weights(session, probe, term=term)
    out = propose(edits, eff.weights)
    if out["proposal"] is not None:
        row = await _write_draft(session, term, out["proposal"], actor)
        out["proposal"] = {**out["proposal"], "profile_id": row.id, "key": row.key, "version": row.version}
    return {"term_id": term_id, "term_code": term.code, **info, **out}


__all__ = [
    "DEFAULTS",
    "MIN_EDITS",
    "Edit",
    "Learned",
    "agreements",
    "edit_deltas",
    "edits_for_term",
    "kendall_tau",
    "learn",
    "minimal_change",
    "propose",
    "propose_for_term",
    "proposal",
    "ratio_vector",
    "synthetic_edits",
    "synthetic_input",
    "tr_locative",
    "unit_weights",
]
