"""``solve(inp: SolverInput) -> SolverResult`` — the CP-SAT entry point.

Pipeline: ``prepare`` (effective constraints, domains, pruning) → static checker → model →
hints (locked + previous) → CP-SAT (multi-worker, time limit, seed) → extraction → independent
pure-Python evaluation (so ``solve`` and ``validate`` agree) → on INFEASIBLE, :mod:`diagnose`.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import replace
from typing import Any

from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from app.solver.build import Prepared, build_model, hint_assignments, make_solver, prepare, status_name
from app.solver.diagnose import diagnose, static_check
from app.solver.evaluate import Evaluation
from app.solver.greedy import greedy_assignments
from app.solver.model import Assignment, Diagnosis, Event, SolverInput, SolverResult
from app.solver.scoring import evaluate


def _result_from_evaluation(
    status: str, assignments: list[Assignment], ev: Evaluation, diagnoses: list[Diagnosis], stats: dict[str, Any]
) -> SolverResult:
    return SolverResult(
        status=status,  # type: ignore[arg-type]
        assignments=assignments,
        hard_score=ev.hard_score(),
        soft_score=ev.soft_score(),
        objective_breakdown=dict(sorted(ev.penalties.items())),
        diagnoses=diagnoses,
        stats=stats,
    )


def _complete_hint(inp: SolverInput, hints: dict[int, Assignment], budget_s: float) -> dict[int, Assignment]:
    """Greedy left a few events unplaced: re-solve a small neighbourhood (everything else locked)
    so the main model starts from a *complete* feasible hint.  Best effort, never raises."""
    unplaced = [e for e in inp.events if e.id not in hints]
    if not unplaced or len(unplaced) > max(10, len(inp.events) // 20):
        return hints
    try:
        free: set[int] = set()
        placed = list(hints.values())
        for e in unplaced:
            free |= neighbours_of_options(inp, placed, e)
        events = tuple(
            e if (e.id in free or e.id not in hints or e.locked is not None) else replace(e, locked=hints[e.id])
            for e in inp.events
        )
        sub = replace(inp, events=events, previous=tuple(placed), time_limit_s=budget_s, workers=max(1, inp.workers))
        res = solve(sub, _complete=False)
        if res.status in ("OPTIMAL", "FEASIBLE") and res.hard_score == 100:
            return {a.event_id: a for a in res.assignments}
    except Exception:  # noqa: BLE001 - a hint is optional
        return hints
    return hints


def neighbours_of_options(inp: SolverInput, placed: list[Assignment], e: Event) -> set[int]:
    """Placed events that could block any option of ``e`` (same key, or a room ``e`` may use)."""
    from app.solver.domains import TimeOption, build_domains, weeks_intersect

    dom = build_domains(replace(inp, events=(e,))).domain(e.id)
    rooms = set(dom.rooms)
    keys = e.cohort_keys | e.instructor_keys
    by_id = {x.id: x for x in inp.events}
    out: set[int] = set()
    for a in placed:
        other = by_id.get(a.event_id)
        if other is None or not weeks_intersect(other.weeks, e.weeks):
            continue
        ta = TimeOption(a.day, a.start, a.end - a.start + 1)
        if not any(t.overlaps(ta) for t in dom.times):
            continue
        if (rooms & set(a.room_ids)) or (keys & (other.cohort_keys | other.instructor_keys)):
            out.add(a.event_id)
    return out


def solve(inp: SolverInput, *, _complete: bool = True) -> SolverResult:
    t0 = time.perf_counter()
    stats: dict[str, Any] = {}
    try:
        prep: Prepared = prepare(inp)
        stats.update(prep.stats)
        stats["warnings"] = list(prep.warnings)
        static = static_check(prep)
        stats["static_check_s"] = round(time.perf_counter() - t0, 3)
        errors = [d for d in static if d.severity == "error"]
        if errors:
            stats["wall_s"] = round(time.perf_counter() - t0, 3)
            stats["solver_status"] = "STATIC_INFEASIBLE"
            return SolverResult("INFEASIBLE", [], 0, 0, {}, static, stats)
        ctx = build_model(prep, "solve")
        t_greedy = time.perf_counter()
        hints = {a.event_id: a for a in greedy_assignments(prep)}
        stats["greedy_placed"] = len(hints)
        if _complete and len(hints) < len(inp.events):
            hints = _complete_hint(inp, hints, min(10.0, max(1.0, inp.time_limit_s * 0.15)))
            stats["hint_completed"] = len(hints)
        hints.update({a.event_id: a for a in hint_assignments(inp)})  # previous / locked win
        stats["greedy_s"] = round(time.perf_counter() - t_greedy, 3)
        stats["hinted_events"] = ctx.add_hints([hints[e.id] for e in inp.events if e.id in hints])
        stats["warnings"].extend(ctx.warnings)
        elapsed = time.perf_counter() - t0
        solver = make_solver(inp, max(0.5, inp.time_limit_s - elapsed))
        status = solver.Solve(ctx.model)
        name = status_name(solver, status)
        stats["solver_status"] = name
        stats["solve_s"] = round(solver.WallTime(), 3)
        stats["branches"] = int(solver.NumBranches())
        stats["conflicts"] = int(solver.NumConflicts())
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            assignments = ctx.extract(solver)
            ev = evaluate(inp, assignments)
            stats["objective_value"] = int(round(solver.ObjectiveValue()))
            stats["objective_bound"] = int(round(solver.BestObjectiveBound()))
            stats["cp_breakdown"] = ctx.term_values(solver)
            stats["evaluated_penalty"] = ev.total_penalty()
            stats["wall_s"] = round(time.perf_counter() - t0, 3)
            warnings: list[Diagnosis] = [d for d in static if d.severity != "error"]
            hard = ev.hard_violations()
            if hard:  # should never happen; never hide it
                warnings.append(
                    Diagnosis(
                        sorted({i for v in hard for i in v.event_ids}),
                        sorted({v.kind for v in hard}),
                        "solver output violates hard rules: " + "; ".join(v.message for v in hard[:5]),
                        [],
                        "error",
                    )
                )
            return _result_from_evaluation(
                "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE", assignments, ev, warnings, stats
            )
        if status == cp_model.INFEASIBLE:
            budget = max(2.0, min(inp.time_limit_s * 0.5, 120.0))
            diagnoses = static + diagnose(prep, budget)
            stats.update(prep.stats)
            stats["diagnose_s"] = round(time.perf_counter() - t0 - stats["solve_s"], 3)
            stats["wall_s"] = round(time.perf_counter() - t0, 3)
            return SolverResult("INFEASIBLE", [], 0, 0, {}, diagnoses, stats)
        stats["wall_s"] = round(time.perf_counter() - t0, 3)
        return SolverResult(
            "TIMEOUT",
            [],
            0,
            0,
            {},
            static
            + [
                Diagnosis(
                    [],
                    [],
                    f"no solution found within {inp.time_limit_s:.0f}s (status "
                    f"{name}); raise the time limit or reduce the horizon",
                    ["increase time_limit_s", "solve week by week", "lock more events"],
                    "warning",
                )
            ],
            stats,
        )
    except Exception as exc:  # noqa: BLE001 - the API wants a result, not a traceback
        stats["wall_s"] = round(time.perf_counter() - t0, 3)
        stats["error"] = f"{type(exc).__name__}: {exc}"
        stats["traceback"] = traceback.format_exc()
        return SolverResult(
            "ERROR", [], 0, 0, {}, [Diagnosis([], [], f"solver error: {type(exc).__name__}: {exc}", [], "error")], stats
        )


__all__ = ["solve"]
