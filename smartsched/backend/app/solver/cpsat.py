"""``solve(inp: SolverInput) -> SolverResult`` — the CP-SAT entry point.

Pipeline: ``prepare`` (effective constraints, domains, pruning) → static checker → model →
hints (locked + previous) → CP-SAT (multi-worker, time limit, seed) → extraction → independent
pure-Python evaluation (so ``solve`` and ``validate`` agree) → on INFEASIBLE, :mod:`diagnose`.
"""

from __future__ import annotations

import time
import traceback
from typing import Any

from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from app.solver.build import Prepared, build_model, hint_assignments, make_solver, prepare, status_name
from app.solver.diagnose import diagnose, static_check
from app.solver.evaluate import Evaluation
from app.solver.greedy import greedy_assignments
from app.solver.model import Assignment, Diagnosis, SolverInput, SolverResult
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


def solve(inp: SolverInput) -> SolverResult:
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
