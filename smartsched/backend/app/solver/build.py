"""Model assembly: domains → prune → variables → constraint modules → objective."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from app.solver.constraints import HANDLERS, effective_constraints
from app.solver.context import Mode, ModelContext
from app.solver.domains import Domains, build_domains
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
    constraints, warnings, soft_structural = effective_constraints(inp)
    doms = build_domains(inp, soft_structural)
    for c in constraints:
        h = HANDLERS[c.kind]
        if c.hard and h.prune is not None:
            h.prune(doms, c)
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
        ctx.model.Minimize(sum(1 - p for p in ctx.placed.values()))
    prep.stats[f"build_{mode}_s"] = round(time.perf_counter() - t0, 3)
    prep.stats[f"bools_{mode}"] = ctx.n_bools
    return ctx


def hint_assignments(inp: SolverInput) -> list[Assignment]:
    """Locked assignments win over previous ones."""
    by_id: dict[int, Assignment] = {a.event_id: a for a in inp.previous}
    for e in inp.events:
        if e.locked is not None:
            by_id[e.id] = e.locked
    return [by_id[e.id] for e in inp.events if e.id in by_id]


def make_solver(inp: SolverInput, time_limit_s: float, workers: int | None = None, lns_only: bool = False) -> Any:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.1, float(time_limit_s))
    solver.parameters.num_workers = max(1, int(inp.workers if workers is None else workers))
    solver.parameters.random_seed = int(inp.seed)
    solver.parameters.log_search_progress = False
    if lns_only:
        solver.parameters.use_lns_only = True
    return solver


def status_name(solver: Any, status: int) -> str:
    return str(solver.StatusName(status))
