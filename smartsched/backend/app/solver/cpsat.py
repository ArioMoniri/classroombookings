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
    CANONICAL_DETERMINISTIC_S,
    Clock,
    Prepared,
    build_model,
    hint_assignments,
    make_solver,
    prepare,
    stable_rank,
    status_name,
)
from app.solver.diagnose import (
    accepted_exceptions,
    diagnose,
    diagnose_with_placement,
    explain_unplaced,
    partial_message,
    static_check,
)
from app.solver.domains import normalize_input
from app.solver.evaluate import Evaluation
from app.solver.greedy import greedy_assignments, prefer_rooms
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


def _complete_hint(
    inp: SolverInput, hints: dict[int, Assignment], budget_s: float, clock: Clock | None = None
) -> dict[int, Assignment]:
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
        if clock is not None:
            clock.charge_s(res.stats.get("clock_s"))
        if res.status in ("OPTIMAL", "FEASIBLE") and res.hard_score == 100:
            return {a.event_id: a for a in res.assignments}
    except Exception:  # noqa: BLE001 - a hint is optional
        return hints
    return hints


#: rank range of the canonical optimum's tie-break objective (a prime below 2**16)
CANONICAL_RANKS = 65521


def _canonical_optimum(
    ctx: Any, solver: Any, assignments: list[Assignment], budget_s: float, clock: Clock | None = None
) -> list[Assignment] | None:
    """Several timetables can share the optimal objective (two equal rooms swapped); CP-SAT's parallel
    workers return whichever they find first.  Fix the objective at its optimum and pick the optimum
    with the smallest fixed pseudo-random rank of its (event, room) and (event, time) choices, so a
    fixed input and seed give the same timetable with ``workers > 1``.  ``None`` unless proven."""
    if budget_s < 1.0:
        return None
    # a wide rank range makes two different optima with the same rank sum (a tie the search would break by
    # its path, i.e. by the hint) very unlikely
    parts = []
    for (eid, rid), z in ctx.z.items():
        parts.append(stable_rank(eid, rid, modulus=CANONICAL_RANKS) * z)
    for (eid, ti), y in ctx.y.items():
        if y is not True and y is not ctx.placed.get(eid):
            parts.append(stable_rank(eid, 7919, ti, modulus=CANONICAL_RANKS) * y)
    if not parts:
        return None
    ctx.model.Add(ctx.objective_expr() == int(round(solver.ObjectiveValue())))
    ctx.model.Minimize(sum(parts))
    ctx.model.ClearHints()
    ctx.add_hints(assignments)
    # one worker and a deterministic time budget (review M2): proving the canonical optimum, and the
    # timetable returned, no longer depend on thread timing or machine load; the wall-clock limit only
    # guards against a pathological stage
    stage = make_solver(ctx.inp, max(1.0, budget_s), workers=1, deterministic_s=CANONICAL_DETERMINISTIC_S)
    status = stage.Solve(ctx.model)
    if clock is not None:
        clock.charge(stage)
    if status != cp_model.OPTIMAL:
        return None
    return ctx.extract(stage)  # type: ignore[no-any-return]


def polish_preferred(prep: Prepared, inp: SolverInput, assignments: list[Assignment]) -> tuple[list[Assignment], int]:
    """A time-limited search (status FEASIBLE) may stop with an event outside its free preferred room set
    (the planner's room when definitive rooms are hints).  Try each :func:`prefer_rooms` move on its own
    and keep it only if every hard rule still holds and the total penalty strictly drops (validated with
    :func:`evaluate`), so a proven optimum is never changed.  Returns the assignments and the moves kept."""
    better = prefer_rooms(prep, assignments)
    if better == assignments:
        return assignments, 0
    current = list(assignments)
    best = evaluate(inp, current).total_penalty()
    kept = 0
    for i, (old, new) in enumerate(zip(assignments, better, strict=True)):
        if old == new:
            continue
        cand = [*current[:i], new, *current[i + 1 :]]
        ev = evaluate(inp, cand)
        if ev.hard_violations() or ev.total_penalty() >= best:
            continue
        current, best, kept = cand, ev.total_penalty(), kept + 1
    return current, kept


#: share of the remaining time the full CP-SAT search gets when the day sweep can follow it
SEARCH_SHARE = 0.6


def _sweep_days(inp: SolverInput, by_event: dict[int, Assignment]) -> dict[int, list[Event]]:
    """Day -> the events a day sweep re-rooms on that day: placed, room-needing, not locked."""
    out: dict[int, list[Event]] = {}
    for e in inp.events:
        a = by_event.get(e.id)
        if a is not None and e.needs_room and e.locked is None:
            out.setdefault(a.day, []).append(e)
    return out


def day_sweep(
    inp: SolverInput, assignments: list[Assignment], budget_s: float
) -> tuple[list[Assignment], dict[str, Any]]:
    """Room re-optimisation one day at a time, at the current times.

    A time-limited search on a large instance (Bahar: ~640 events, ~60 rooms) can stop far from the
    optimum (objective 1694 vs bound 1262 after 45 s), although with the times fixed the room choice
    only couples events of the *same* day.  So, per day: that day's placed unlocked events, pinned to
    their current day and start, plus the day's locked events are re-solved (hinted with the current
    rooms; cohort/instructor rules are unaffected since no time moves).  A day's new rooms are kept only
    if the whole timetable still satisfies every hard rule and its total penalty strictly drops
    (validated with :func:`evaluate`, which also covers soft terms linking days such as
    ``same_room_group``).  Each day gets a share of ``budget_s`` by its number of events."""
    stats: dict[str, Any] = {"sweep_days": 0, "sweep_improved_days": 0}
    t0 = time.perf_counter()
    clock = Clock(inp)
    current = {a.event_id: a for a in assignments}
    days = _sweep_days(inp, current)
    if not days:
        return assignments, stats
    best = evaluate(inp, assignments).total_penalty()
    stats["sweep_penalty_before"] = best
    total = sum(len(v) for v in days.values())
    for day in sorted(days):
        remaining = budget_s - clock.elapsed()
        if remaining < 0.5:
            break
        free = days[day]
        pinned = tuple(
            replace(e, fixed_day=day, fixed_start=current[e.id].start, allowed_days=frozenset({day})) for e in free
        )
        locked = tuple(e for e in inp.events if e.locked is not None and e.id in current and current[e.id].day == day)
        share = max(0.5, remaining * len(free) / max(1, total))
        total -= len(free)
        sub = replace(inp, events=pinned + locked, time_limit_s=share, best_effort=False)
        res = solve(sub, _complete=False, _hints=[current[e.id] for e in sub.events], _sweep=False)
        clock.charge_s(res.stats.get("clock_s"))
        stats["sweep_days"] += 1
        if res.status not in ("OPTIMAL", "FEASIBLE") or res.hard_score < 100:
            continue
        cand = dict(current)
        cand.update({a.event_id: a for a in res.assignments if a.event_id in current})
        ordered = [cand[a.event_id] for a in assignments]
        ev = evaluate(inp, ordered)
        if ev.hard_violations() or ev.total_penalty() >= best:
            continue
        current, best = cand, ev.total_penalty()
        stats["sweep_improved_days"] += 1
    stats["sweep_penalty_after"] = best
    stats["sweep_s"] = round(time.perf_counter() - t0, 3)
    stats["sweep_clock_s"] = round(clock.elapsed(), 6)
    return [current[a.event_id] for a in assignments], stats


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


def solve(
    inp: SolverInput,
    *,
    _complete: bool = True,
    _hints: list[Assignment] | None = None,
    _sweep: bool = True,
) -> SolverResult:
    t0 = time.perf_counter()
    clock = Clock(inp)
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
                return _best_effort(inp, prep, static, stats, t0, run_core=False, hints=_hints, clock=clock)
            _stamp(stats, t0, clock)
            return SolverResult("INFEASIBLE", [], 0, 0, {}, static, stats)
        ctx = build_model(prep, "solve")
        t_greedy = time.perf_counter()
        hints = {a.event_id: a for a in (_hints or [])}
        if len(hints) < len(inp.events):
            for a in greedy_assignments(prep):
                hints.setdefault(a.event_id, a)
        stats["greedy_placed"] = len(hints)
        if _complete and len(hints) < len(inp.events):
            hints = _complete_hint(inp, hints, min(10.0, max(1.0, inp.time_limit_s * 0.15)), clock)
            stats["hint_completed"] = len(hints)
        hints.update({a.event_id: a for a in hint_assignments(inp)})  # previous / locked win
        stats["greedy_s"] = round(time.perf_counter() - t_greedy, 3)
        stats["hinted_events"] = ctx.add_hints([hints[e.id] for e in inp.events if e.id in hints])
        stats["warnings"].extend(ctx.warnings)
        search_s = inp.time_limit_s - clock.elapsed()
        # a complete warm start guarantees a solution: keep part of the time for the day sweep, which
        # closes most of the gap a time-limited search leaves on large instances (see day_sweep)
        sweep = (
            _sweep
            and all(e.id in hints for e in inp.events)
            and len(_sweep_days(inp, {e.id: hints[e.id] for e in inp.events})) > 1
        )
        if sweep:
            search_s *= SEARCH_SHARE
        solver = make_solver(inp, max(0.5, search_s))
        status = solver.Solve(ctx.model)
        clock.charge(solver)
        name = status_name(solver, status)
        stats["solver_status"] = name
        stats["solve_s"] = round(solver.WallTime(), 3)
        stats["branches"] = int(solver.NumBranches())
        stats["conflicts"] = int(solver.NumConflicts())
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            assignments = ctx.extract(solver)
            if status == cp_model.OPTIMAL:
                canon = _canonical_optimum(ctx, solver, assignments, inp.time_limit_s - clock.elapsed(), clock)
                if canon is not None:
                    assignments = canon
                    stats["canonical"] = True
            else:
                if sweep:
                    budget = inp.time_limit_s - clock.elapsed()
                    assignments, sweep_stats = day_sweep(inp, assignments, budget)
                    clock.charge_s(sweep_stats.get("sweep_clock_s"))
                    stats.update(sweep_stats)
                assignments, moves = polish_preferred(prep, inp, assignments)
                if moves:
                    stats["polish_preferred_moves"] = moves
            ev = evaluate(inp, assignments)
            stats["objective_value"] = int(round(solver.ObjectiveValue()))
            stats["objective_bound"] = int(round(solver.BestObjectiveBound()))
            stats["cp_breakdown"] = ctx.term_values(solver)
            stats["evaluated_penalty"] = ev.total_penalty()
            _stamp(stats, t0, clock)
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
                return _best_effort(inp, prep, static, stats, t0, run_core=True, hints=_hints, clock=clock)
            budget = relax_budget(inp)
            diagnoses = static + diagnose(prep, budget, clock=clock)
            stats.update(prep.stats)
            stats["diagnose_s"] = round(time.perf_counter() - t0 - stats["solve_s"], 3)
            _stamp(stats, t0, clock)
            return SolverResult("INFEASIBLE", [], 0, 0, {}, diagnoses, stats)
        if inp.best_effort and hints:
            partial = _timeout_partial(inp, prep, static, stats, t0, hints, name, clock)
            if partial is not None:
                return partial
        _stamp(stats, t0, clock)
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
        _stamp(stats, t0, clock)
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


def _stamp(stats: dict[str, Any], t0: float, clock: Clock | None) -> None:
    """Wall time and the solve's clock (deterministic time in deterministic mode, see ``build.Clock``)."""
    stats["wall_s"] = round(time.perf_counter() - t0, 3)
    if clock is not None:
        stats["clock_s"] = round(clock.elapsed(), 6)
        stats["deterministic"] = clock.det


#: share of the time limit the slack relaxation (diagnosis / best effort phase 1) may use; it scales with
#: the limit (review M5: it was capped at 120 s whatever the limit)
RELAX_SHARE = 0.5


def relax_budget(inp: SolverInput) -> float:
    return max(2.0, inp.time_limit_s * RELAX_SHARE)


def _timeout_partial(
    inp: SolverInput,
    prep: Prepared,
    static: list[Diagnosis],
    stats: dict[str, Any],
    t0: float,
    hints: dict[int, Assignment],
    status_name_: str,
    clock: Clock | None = None,
) -> SolverResult | None:
    """``best_effort`` and the search ended without any solution (UNKNOWN): return the warm start's
    placement when it keeps every hard rule for its events (checked, never assumed), with every other
    event explained.  Status stays ``TIMEOUT``: nothing is proven, not even that the rest cannot be placed."""
    placed = {e.id: hints[e.id] for e in inp.events if e.id in hints}
    if not placed:
        return None
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed), best_effort=False)
    assignments = [placed[e.id] for e in sub.events]
    ev = evaluate(sub, assignments)
    if ev.hard_violations():
        return None
    explained = {d.event_ids[0] for d in static if d.severity == "error" and len(d.event_ids) == 1}
    unplaced_ids = [e.id for e in inp.events if e.id not in placed]
    diags = explain_unplaced(prep, placed, explained)
    stats.update(
        partial=True,
        partial_source="warm_start",
        partial_reason="timeout",
        placed=len(placed),
        unplaced=len(unplaced_ids),
        events_total=len(inp.events),
        unplaced_ids=unplaced_ids[:500],
        evaluated_penalty=ev.total_penalty(),
    )
    _stamp(stats, t0, clock)
    summary = Diagnosis(
        unplaced_ids[:200],
        [],
        f"no complete timetable found within {inp.time_limit_s:.0f}s (status {status_name_}); best effort keeps the "
        f"warm start: {len(placed)} of {len(inp.events)} events placed, every hard rule holds for them; the rest "
        "is not proven impossible — raise the time limit",
        ["increase time_limit_s", "solve week by week"],
        "warning",
        "partial",
        {"reason": "timeout"},
    )
    return _result_from_evaluation("TIMEOUT", assignments, ev, [summary, *static, *diags], stats)


def _best_effort(
    inp: SolverInput,
    prep: Prepared,
    static: list[Diagnosis],
    stats: dict[str, Any],
    t0: float,
    *,
    run_core: bool,
    hints: list[Assignment] | None = None,
    clock: Clock | None = None,
) -> SolverResult:
    """``best_effort``: the instance cannot be scheduled completely.  Phase 1 (slack relaxation,
    hinted with the greedy placement) maximises the number of placed events and explains every
    unplaced one; phase 2 re-solves the *placed* events with the normal objective (hinted with phase
    1).  Status stays INFEASIBLE (the full request set has no solution); ``stats.partial`` /
    ``placed`` / ``unplaced`` / ``unplaced_ids`` describe the partial timetable, and the hard/soft
    scores are those of the placed events (hard 100 = every hard rule holds for them)."""
    clock = clock or Clock(inp)
    budget = relax_budget(inp)
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
    diagnoses, placed = diagnose_with_placement(
        prep, budget, core=run_core, hints=greedy, explained=explained, clock=clock
    )
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
        _stamp(stats, t0, clock)
        return SolverResult("INFEASIBLE", [], 0, 0, {}, static + diagnoses, stats)
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed), best_effort=False)
    remaining = inp.time_limit_s - clock.elapsed()
    assignments = [placed[e.id] for e in sub.events]
    # the relaxation ignores soft terms: move events back into their preferred rooms where those are free
    # (validated), so phase 2 starts from a good incumbent instead of an arbitrary room choice
    better = prefer_rooms(prep, assignments)
    if better != assignments and not evaluate(sub, better).hard_violations():
        stats["hint_preferred_moves"] = sum(1 for x, y in zip(assignments, better, strict=True) if x != y)
        assignments = better
    phase2 = None
    if remaining > 1.0:
        phase2 = solve(replace(sub, time_limit_s=remaining), _complete=False, _hints=assignments)
        clock.charge_s(phase2.stats.get("clock_s"))
        stats["phase2_status"] = phase2.status
        stats["phase2_s"] = phase2.stats.get("wall_s")
        # every scalar stat of phase 2 (solver status, canonical stage, objective / bound, sweep, polish ...)
        stats.update(
            {
                f"phase2_{k}": v
                for k, v in phase2.stats.items()
                if isinstance(v, int | float | str | bool) and not k.startswith("phase2_") and k != "traceback"
            }
        )
        if phase2.status in ("OPTIMAL", "FEASIBLE"):
            assignments = phase2.assignments
    if phase2 is None or phase2.status != "OPTIMAL":
        assignments, moves = polish_preferred(prep, sub, assignments)
        if moves:
            stats["polish_preferred_moves"] = moves
    ev = evaluate(sub, assignments)
    stats["evaluated_penalty"] = ev.total_penalty()
    _stamp(stats, t0, clock)
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
    exceptions = accepted_exceptions([*static, *diagnoses], len(unplaced_ids))
    summary = Diagnosis(
        unplaced_ids[:200],
        [],
        partial_message(len(placed), len(inp.events), exceptions)
        if not hard
        else f"best effort: {len(placed)} of {len(inp.events)} events placed",
        ["fix the reported input problems and re-run to place the rest"],
        "warning",
        "partial",
        {"exceptions": exceptions},
    )
    return _result_from_evaluation("INFEASIBLE", assignments, ev, [summary, *static, *diagnoses, *extra], stats)


__all__ = ["solve"]
