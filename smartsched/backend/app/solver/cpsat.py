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

from app.solver.build import (
    Prepared,
    build_model,
    hint_assignments,
    make_solver,
    prepare,
    stable_rank,
    status_name,
)
from app.solver.diagnose import diagnose, diagnose_with_placement, explain_unplaced, static_check
from app.solver.domains import normalize_input
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


def _canonical_optimum(
    ctx: Any, solver: Any, assignments: list[Assignment], budget_s: float
) -> list[Assignment] | None:
    """Several timetables can share the optimal objective (two equal rooms swapped); CP-SAT's parallel
    workers return whichever they find first.  Fix the objective at its optimum and pick the optimum
    with the smallest fixed pseudo-random rank of its (event, room) and (event, time) choices, so a
    fixed input and seed give the same timetable with ``workers > 1``.  ``None`` unless proven."""
    if budget_s < 1.0:
        return None
    parts = []
    for (eid, rid), z in ctx.z.items():
        parts.append(stable_rank(eid, rid) * z)
    for (eid, ti), y in ctx.y.items():
        if y is not True and y is not ctx.placed.get(eid):
            parts.append(stable_rank(eid, 7919, ti) * y)
    if not parts:
        return None
    ctx.model.Add(ctx.objective_expr() == int(round(solver.ObjectiveValue())))
    ctx.model.Minimize(sum(parts))
    ctx.model.ClearHints()
    ctx.add_hints(assignments)
    stage = make_solver(ctx.inp, max(0.5, min(budget_s, 20.0)))
    if stage.Solve(ctx.model) != cp_model.OPTIMAL:
        return None
    return ctx.extract(stage)  # type: ignore[no-any-return]


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


def solve(inp: SolverInput, *, _complete: bool = True, _hints: list[Assignment] | None = None) -> SolverResult:
    t0 = time.perf_counter()
    stats: dict[str, Any] = {}
    try:
        inp = normalize_input(inp)
        prep: Prepared = prepare(inp)
        stats.update(prep.stats)
        stats["warnings"] = list(prep.warnings)
        static = static_check(prep)
        stats["static_check_s"] = round(time.perf_counter() - t0, 3)
        errors = [d for d in static if d.severity == "error"]
        if errors:
            stats["solver_status"] = "STATIC_INFEASIBLE"
            if inp.best_effort:
                return _best_effort(inp, prep, static, stats, t0, run_core=False, hints=_hints)
            stats["wall_s"] = round(time.perf_counter() - t0, 3)
            return SolverResult("INFEASIBLE", [], 0, 0, {}, static, stats)
        ctx = build_model(prep, "solve")
        t_greedy = time.perf_counter()
        hints = {a.event_id: a for a in (_hints or [])}
        if len(hints) < len(inp.events):
            for a in greedy_assignments(prep):
                hints.setdefault(a.event_id, a)
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
            if status == cp_model.OPTIMAL:
                canon = _canonical_optimum(ctx, solver, assignments, inp.time_limit_s - (time.perf_counter() - t0))
                if canon is not None:
                    assignments = canon
                    stats["canonical"] = True
            ev = evaluate(inp, assignments)
            stats["objective_value"] = int(round(solver.ObjectiveValue()))
            stats["objective_bound"] = int(round(solver.BestObjectiveBound()))
            stats["cp_breakdown"] = ctx.term_values(solver)
            stats["evaluated_penalty"] = ev.total_penalty()
            stats["wall_s"] = round(time.perf_counter() - t0, 3)
            stats.update(placed=len(assignments), unplaced=0, events_total=len(inp.events))
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
                        "internal",
                    )
                )
            return _result_from_evaluation(
                "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE", assignments, ev, warnings, stats
            )
        if status == cp_model.INFEASIBLE:
            if inp.best_effort:
                return _best_effort(inp, prep, static, stats, t0, run_core=True, hints=_hints)
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
                    "timeout",
                )
            ],
            stats,
        )
    except Exception as exc:  # noqa: BLE001 - the API wants a result, not a traceback
        stats["wall_s"] = round(time.perf_counter() - t0, 3)
        stats["error"] = f"{type(exc).__name__}: {exc}"
        stats["traceback"] = traceback.format_exc()
        return SolverResult(
            "ERROR",
            [],
            0,
            0,
            {},
            [Diagnosis([], [], f"solver error: {type(exc).__name__}: {exc}", [], "error", "internal")],
            stats,
        )


def _best_effort(
    inp: SolverInput,
    prep: Prepared,
    static: list[Diagnosis],
    stats: dict[str, Any],
    t0: float,
    *,
    run_core: bool,
    hints: list[Assignment] | None = None,
) -> SolverResult:
    """``best_effort``: the instance cannot be scheduled completely.  Phase 1 (slack relaxation,
    hinted with the greedy placement) maximises the number of placed events and explains every
    unplaced one; phase 2 re-solves the *placed* events with the normal objective (hinted with phase
    1).  Status stays INFEASIBLE (the full request set has no solution); ``stats.partial`` /
    ``placed`` / ``unplaced`` / ``unplaced_ids`` describe the partial timetable, and the hard/soft
    scores are those of the placed events (hard 100 = every hard rule holds for them)."""
    budget = max(2.0, min(inp.time_limit_s * 0.5, 120.0))
    explained = {d.event_ids[0] for d in static if d.severity == "error" and len(d.event_ids) == 1}
    greedy = greedy_assignments(prep)
    stats["greedy_placed"] = len(greedy)
    if hints is not None:
        # a caller's partial schedule (e.g. the previous round of ``weeksplit.solve_segmented``) is the
        # warm start when it places more events than greedy; it is re-checked like greedy below
        known = {e.id for e in inp.events}
        given = [a for a in hints if a.event_id in known]
        if len(given) >= len(greedy):
            greedy = given
            stats["warm_start"] = "hints"
            stats["hints_placed"] = len(given)
    diagnoses, placed = diagnose_with_placement(prep, budget, core=run_core, hints=greedy, explained=explained)
    stats.update(prep.stats)
    stats["diagnose_s"] = round(time.perf_counter() - t0 - stats.get("solve_s", 0.0), 3)
    stats["partial_source"] = "relaxation"
    if len(greedy) > len(placed):
        # the relaxation timed out or stopped early below the greedy warm start: keep the greedy
        # placement if it satisfies every hard rule for its events (checked, never assumed)
        g_sub = replace(inp, events=tuple(e for e in inp.events if e.id in {a.event_id for a in greedy}))
        if not evaluate(g_sub, greedy).hard_violations():
            placed = {a.event_id: a for a in greedy}
            stats["partial_source"] = "greedy"
            diagnoses = [d for d in diagnoses if d.code not in ("unplaced", "unplaced_summary", "relax_timeout")]
            diagnoses += explain_unplaced(prep, placed, explained)
    unplaced_ids = [e.id for e in inp.events if e.id not in placed]
    stats.update(
        partial=True,
        placed=len(placed),
        unplaced=len(unplaced_ids),
        events_total=len(inp.events),
        unplaced_ids=unplaced_ids[:500],
    )
    if not placed:
        stats["wall_s"] = round(time.perf_counter() - t0, 3)
        return SolverResult("INFEASIBLE", [], 0, 0, {}, static + diagnoses, stats)
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed), best_effort=False)
    remaining = inp.time_limit_s - (time.perf_counter() - t0)
    assignments = [placed[e.id] for e in sub.events]
    phase2 = None
    if remaining > 1.0:
        phase2 = solve(replace(sub, time_limit_s=remaining), _complete=False, _hints=assignments)
        stats["phase2_status"] = phase2.status
        stats["phase2_s"] = phase2.stats.get("wall_s")
        if phase2.status in ("OPTIMAL", "FEASIBLE"):
            assignments = phase2.assignments
    ev = evaluate(sub, assignments)
    stats["evaluated_penalty"] = ev.total_penalty()
    stats["wall_s"] = round(time.perf_counter() - t0, 3)
    hard = ev.hard_violations()
    extra: list[Diagnosis] = []
    if hard:  # never hide it (the relaxation and phase 2 enforce every hard rule)
        extra.append(
            Diagnosis(
                sorted({i for v in hard for i in v.event_ids}),
                sorted({v.kind for v in hard}),
                "partial timetable violates hard rules: " + "; ".join(v.message for v in hard[:5]),
                [],
                "error",
                "internal",
            )
        )
    summary = Diagnosis(
        unplaced_ids[:200],
        [],
        f"best effort: {len(placed)} of {len(inp.events)} events placed, {len(unplaced_ids)} cannot be placed "
        f"(reasons below); hard rules hold for every placed event"
        if not hard
        else f"best effort: {len(placed)} of {len(inp.events)} events placed",
        ["fix the reported input problems and re-run to place the rest"],
        "warning",
        "partial",
    )
    return _result_from_evaluation("INFEASIBLE", assignments, ev, [summary, *static, *diagnoses, *extra], stats)


__all__ = ["solve"]
