"""Model assembly: domains → prune → variables → constraint modules → objective."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from app.solver.constraints import HANDLERS, effective_constraints
from app.solver.context import Mode, ModelContext
from app.solver.domains import Domains, build_domains, normalize_input, shares_room, trusted_lock
from app.solver.model import Assignment, Constraint, SolverInput


@dataclass
class Prepared:
    """Everything computed before the CP-SAT model: effective constraints and pruned domains."""

    inp: SolverInput
    constraints: list[Constraint]
    warnings: list[str]
    soft_structural: frozenset[str]
    doms: Domains
    stats: dict[str, Any] = field(default_factory=dict)


def prepare(inp: SolverInput) -> Prepared:
    t0 = time.perf_counter()
    inp = normalize_input(inp)  # idempotent (cpsat.solve normalises first; precheck calls prepare directly)
    constraints, warnings, soft_structural = effective_constraints(inp)
    doms = build_domains(inp, soft_structural)
    for c in constraints:
        h = HANDLERS[c.kind]
        if c.hard and h.prune is not None:
            h.prune(doms, c)
    doms.trusted_full = trusted_full_groups(inp, doms)
    n_opts = sum(d.option_count() for d in doms.by_event.values())
    fixed = sum(1 for d in doms.by_event.values() if d.fixed_time)
    stats = {
        "prepare_s": round(time.perf_counter() - t0, 3),
        "events": len(inp.events),
        "rooms": len(inp.rooms),
        "fixed_time_events": fixed,
        "candidate_options": n_opts,
        "constraints": [c.kind for c in constraints],
    }
    return Prepared(inp, constraints, warnings, soft_structural, doms, stats)


def trusted_full_groups(inp: SolverInput, doms: Domains) -> list[frozenset[int]]:
    """``trust_locked_rooms``: planner-locked room-sharing events whose seats cannot be allotted (ACU 132
    + ACU 310 locked together in A 207).  The planner's rooms are kept: each group holds its rooms
    *exclusively* for the union of its members' periods (nobody else may join an over-full room), and
    the static checker reports it as a warning.  Groups chained through shared members are merged."""
    from app.solver.seats import seat_conflicts

    locked = {e.id: e.locked for e in inp.events if e.locked is not None and shares_room(e) and trusted_lock(inp, e)}
    if len(locked) < 2:
        return []
    groups: list[set[int]] = []
    for ids, _rooms, _day, _p, _w in seat_conflicts(inp, doms.events_by_id, doms.rooms_by_id, locked):  # type: ignore[arg-type]
        merged = set(ids)
        rest = []
        for g in groups:
            if g & merged:
                merged |= g
            else:
                rest.append(g)
        groups = [*rest, merged]
    return sorted((frozenset(g) for g in groups), key=lambda g: sorted(g))


def build_model(prep: Prepared, mode: Mode = "solve") -> ModelContext:
    t0 = time.perf_counter()
    ctx = ModelContext(prep.inp, prep.doms, mode)
    for c in prep.constraints:
        if mode != "solve" and not c.hard:
            continue  # satisfaction / relaxation models carry no soft terms
        HANDLERS[c.kind].apply(ctx, c)
    if mode == "solve":
        ctx.model.Minimize(ctx.objective_expr())
    elif mode == "relax":
        ctx.relax_objective = _relax_objective(ctx, prep.inp)
        ctx.model.Minimize(ctx.relax_objective)
    prep.stats[f"build_{mode}_s"] = round(time.perf_counter() - t0, 3)
    prep.stats[f"bools_{mode}"] = ctx.n_bools
    return ctx


def stable_rank(*key: int, modulus: int = 997) -> int:
    """Fixed pseudo-random rank in 1..``modulus`` of an integer tuple (splitmix64 mixing: non-linear, so
    swapping two events between two rooms does not tie; no Python ``hash`` randomisation)."""
    h = 0x9E3779B97F4A7C15
    mask = (1 << 64) - 1
    for k in key:
        h = (h ^ (k & mask)) * 0xBF58476D1CE4E5B9 & mask
        h ^= h >> 31
        h = h * 0x94D049BB133111EB & mask
        h ^= h >> 29
    return h % modulus + 1


def week_segment_groups(inp: SolverInput) -> list[list[int]]:
    """Events that are week segments of one request (``weeksplit.split_blocked_weeks`` marks their
    ``same_room_across_weeks`` group with ``week_segments``)."""
    ids = {e.id for e in inp.events}
    out: list[list[int]] = []
    for c in inp.constraints:
        if c.kind == "same_room_across_weeks" and c.params.get("week_segments"):
            for g in c.params.get("groups") or []:
                members = [int(i) for i in g if int(i) in ids]
                if len(members) > 1:
                    out.append(members)
    return out


def _relax_objective(ctx: ModelContext, inp: SolverInput) -> Any:
    """Lexicographic: (1) requests not completely placed, (2) unplaced event-weeks of every request (a
    request that loses one week beats one that loses the term), (3) keep planner-locked events placed (a
    locked event and a free one competing for a room: the free one gives way).
    Without week segments this is the plain ``(L+1)·#unplaced + #unplaced locked``."""
    locked = {e.id for e in inp.events if e.locked is not None}
    weeks = {e.id: max(1, len(e.weeks)) for e in inp.events}
    groups = [[i for i in g if i in ctx.placed] for g in week_segment_groups(inp)]
    groups = [g for g in groups if len(g) > 1]
    segmented = {i for g in groups for i in g}
    tier3 = len(locked) + 1
    # unplaced event-weeks count for *every* event: a request dropped for all 14 weeks costs 14 weeks, not
    # fewer than one segment of another request (orchestrator R3: PHAR 114 §2 lost its lock for the term so
    # that another request's 7-week segment could take the room)
    tier2 = tier3 * (sum(weeks[i] for i in ctx.placed) + 1)
    terms: list[Any] = []
    for eid, p in ctx.placed.items():
        lock = 1 if eid in locked else 0
        if eid in segmented:
            terms.append((tier3 * weeks[eid] + lock) * (1 - p))
        else:
            terms.append((tier2 + tier3 * weeks[eid] + lock) * (1 - p))
    for n, g in enumerate(groups):
        full = ctx.new_bool(f"segments_placed_{n}")
        for i in g:
            ctx.model.AddImplication(full, ctx.placed[i])
        ctx.model.AddBoolOr([full] + [ctx.placed[i].Not() for i in g])
        ctx.derive(full, lambda h, ids=tuple(g): int(all(i in h.by_event for i in ids)))
        terms.append(tier2 * (1 - full))
    return sum(terms) if terms else 0


def hint_assignments(inp: SolverInput) -> list[Assignment]:
    """Locked assignments win over previous ones."""
    by_id: dict[int, Assignment] = {a.event_id: a for a in inp.previous}
    for e in inp.events:
        if e.locked is not None:
            by_id[e.id] = e.locked
    return [by_id[e.id] for e in inp.events if e.id in by_id]


#: wall-clock safety net of a deterministic-mode CP-SAT call: factor x its deterministic budget
DETERMINISTIC_WALL_FACTOR = 6.0


def deterministic_mode(inp: SolverInput) -> bool:
    """``workers == 1`` is the deterministic mode: every CP-SAT call gets a *deterministic* time budget
    derived from ``time_limit_s`` only, and the stages split their budgets by deterministic time, so the same
    input and seed give the same result on any machine load (bit-for-bit, review M2)."""
    return int(inp.workers) == 1


class Clock:
    """Time used by a solve: wall seconds, or in deterministic mode the deterministic time of its CP-SAT
    calls (Python work is deterministic anyway).  Nested solves report theirs in ``stats["clock_s"]``."""

    def __init__(self, inp: SolverInput) -> None:
        self.det = deterministic_mode(inp)
        self.t0 = time.perf_counter()
        self.spent = 0.0

    def elapsed(self) -> float:
        return self.spent if self.det else time.perf_counter() - self.t0

    def charge(self, solver: Any) -> None:
        if self.det:
            self.spent += float(solver.deterministic_time)

    def charge_s(self, seconds: Any) -> None:
        if self.det and isinstance(seconds, int | float):
            self.spent += float(seconds)


#: deterministic-time budget of the canonical stages (``cpsat._canonical_optimum``,
#: ``diagnose._canonical_placement``): single worker, so the same model gives the same answer on any load
CANONICAL_DETERMINISTIC_S = 60.0


def make_solver(
    inp: SolverInput,
    time_limit_s: float,
    workers: int | None = None,
    lns_only: bool = False,
    deterministic_s: float | None = None,
) -> Any:
    """CP-SAT solver with the run's seed.  ``deterministic_s`` adds a deterministic time limit (use it with
    ``workers=1`` for reproducible stages; ``time_limit_s`` is then only a wall-clock safety net)."""
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.1, float(time_limit_s))
    if deterministic_s is not None:
        solver.parameters.max_deterministic_time = max(0.1, float(deterministic_s))
    if deterministic_mode(inp):
        # the budget is deterministic time; the wall clock is only a safety net
        det = min(float(time_limit_s), float(deterministic_s)) if deterministic_s is not None else float(time_limit_s)
        solver.parameters.max_deterministic_time = max(0.1, det)
        solver.parameters.max_time_in_seconds = max(30.0, det * DETERMINISTIC_WALL_FACTOR)
    solver.parameters.num_workers = max(1, int(inp.workers if workers is None else workers))
    solver.parameters.random_seed = int(inp.seed)
    solver.parameters.log_search_progress = False
    # presolve probing over tens of thousands of optional intervals burns minutes of wall time
    # (its deterministic-time accounting is far off); search-time probing workers remain enabled
    solver.parameters.cp_model_probing_level = 0
    if lns_only:
        solver.parameters.use_lns_only = True
    return solver


def status_name(solver: Any, status: int) -> str:
    return str(solver.StatusName(status))
