"""AS-08 ``peak_smoothing``: an opt-in soft rule that moves *flexible* events (free day or start) out of
(day, period, room group) cells loaded above the peak threshold.  Fixed times never move, weight 0 (the
default) leaves every result byte-identical, and the model, ``evaluate`` and the greedy warm start agree."""

from __future__ import annotations

from dataclasses import replace

from app.solver.build import build_model, prepare
from app.solver.constraints import effective_constraints
from app.solver.constraints import peak_smoothing as ps
from app.solver.cpsat import solve
from app.solver.greedy import greedy_assignments
from app.solver.model import Assignment, Constraint, SolverResult
from app.solver.repair import score as repair_score
from app.solver.scoring import evaluate
from app.solver.weights import DEFAULT_WEIGHTS
from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from tests.solver.conftest import assigned, event, make_input, room

W = (1,)


def ok(res: SolverResult) -> SolverResult:
    assert res.status in ("OPTIMAL", "FEASIBLE"), (res.status, res.diagnoses)
    assert res.hard_score == 100, res.diagnoses
    return res


def _busy_monday(weight: int, *, extra: tuple[Constraint, ...] = ()):  # type: ignore[no-untyped-def]
    """Four rooms; three fixed classes fill Monday P1-P2 (75 %).  D may go on Monday or Tuesday at P1 and
    mildly prefers Monday (a soft day window on Tuesday, 5 per period)."""
    rooms = tuple(room(i, f"A10{i}", 40) for i in range(1, 5))
    fixed = tuple(event(i, size=30, day=1, start=1, weeks=W) for i in (1, 2, 3))
    flex = event(4, size=30, allowed_days=(1, 2), earliest=1, latest=2, weeks=W)
    rules = (Constraint("day_window", {"event_ids": [4], "periods": [], "days": [2], "earliest": 3}, hard=False),)
    return make_input(
        rooms,
        (*fixed, flex),
        rules + extra,
        days=(1, 2),
        weeks=W,
        workers=1,
        weights={"peak_smoothing": weight, "min_capacity_waste": 0},
    )


def test_default_weight_is_zero_and_kind_is_soft_only() -> None:
    assert DEFAULT_WEIGHTS["peak_smoothing"] == 0
    inp = _busy_monday(0)
    kinds = [c.kind for c in effective_constraints(inp)[0]]
    assert "peak_smoothing" not in kinds  # off: not even in the model
    on = [c for c in effective_constraints(replace(inp, weights={"peak_smoothing": 3}))[0] if c.kind == "peak_smoothing"]
    assert len(on) == 1 and on[0].hard is False
    hard = replace(inp, constraints=(Constraint("peak_smoothing", {}, hard=True),), weights={"peak_smoothing": 3})
    cons, warnings, _soft = effective_constraints(hard)
    assert [c.hard for c in cons if c.kind == "peak_smoothing"] == [False]
    assert any("peak_smoothing" in w and "soft" in w for w in warnings)  # never silently: reported


def test_toy_moves_flexible_event_out_of_full_cell() -> None:
    off = ok(solve(_busy_monday(0)))
    assert assigned(off.assignments, 4).day == 1  # the day window keeps it on Monday
    assert "peak_smoothing" not in off.objective_breakdown
    on = ok(solve(_busy_monday(10)))
    a = assigned(on.assignments, 4)
    assert a.day == 2  # 4 of 4 rooms > 3 (85 % of 4 = 3): moved to Tuesday
    assert on.objective_breakdown.get("peak_smoothing", 0) == 0
    assert on.objective_breakdown["day_window"] == 10
    # the fixed classes never move
    for i in (1, 2, 3):
        assert (assigned(on.assignments, i).day, assigned(on.assignments, i).start) == (1, 1)


def test_weight_decides_against_other_soft_terms() -> None:
    # 2 periods above the threshold x weight 2 = 4 < the day window's 10: stays on Monday
    low = ok(solve(_busy_monday(2)))
    assert assigned(low.assignments, 4).day == 1
    assert low.objective_breakdown["peak_smoothing"] == 4


def test_weight_zero_is_byte_identical() -> None:
    base = _busy_monday(0)
    without_key = replace(base, weights={"min_capacity_waste": 0})
    a, b = solve(base), solve(without_key)
    assert a.assignments == b.assignments
    assert (a.hard_score, a.soft_score, a.objective_breakdown) == (b.hard_score, b.soft_score, b.objective_breakdown)
    assert a.stats["constraints"] == b.stats["constraints"]
    ea, eb = evaluate(base, a.assignments), evaluate(without_key, b.assignments)
    assert (ea.penalties, ea.bounds) == (eb.penalties, eb.bounds)


def test_fixed_events_alone_are_never_penalised() -> None:
    inp = _busy_monday(10)
    # all four rooms taken by fixed classes on Monday P1: 100 % load, nothing can move, no penalty
    fixed = replace(inp, events=(*inp.events[:3], event(4, size=30, day=1, start=1, weeks=W)))
    res = ok(solve(fixed))
    assert res.objective_breakdown.get("peak_smoothing", 0) == 0
    ev = evaluate(fixed, res.assignments)
    assert ev.penalties.get("peak_smoothing", 0) == 0


def test_evaluate_and_model_agree_and_repair_scores_the_same() -> None:
    inp = _busy_monday(10)
    monday = [Assignment(i, 1, 1, 2, (i,), frozenset(W)) for i in (1, 2, 3, 4)]
    ev = evaluate(inp, monday)
    assert ev.penalties["peak_smoothing"] == 2 * 10  # one room above 3 for P1 and P2
    assert any(v.kind == "peak_smoothing" and v.event_ids == [4] for v in ev.violations)
    assert repair_score(inp, monday)[2]["peak_smoothing"] == 20
    # the CP-SAT objective term on the same (forced) placement
    prep = prepare(replace(inp, events=tuple(replace(e, locked=a) for e, a in zip(inp.events, monday, strict=True))))
    ctx = build_model(prep)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    assert solver.Solve(ctx.model) == cp_model.OPTIMAL
    assert ctx.term_values(solver)["peak_smoothing"] == 20


def test_greedy_warm_start_prefers_the_off_peak_cell() -> None:
    off = {a.event_id: a for a in greedy_assignments(prepare(_busy_monday(0)))}
    on = {a.event_id: a for a in greedy_assignments(prepare(_busy_monday(10)))}
    assert on[4].day == 2
    assert {k: v for k, v in off.items() if k != 4} == {k: v for k, v in on.items() if k != 4}


def test_room_groups_tags_and_cells() -> None:
    """Only the PC group is above its threshold: a lab class leaves it; a ``cells`` list limits the rule."""
    rooms = (room(1, "A101", 40, tags=("PC",)), room(2, "A102", 40, tags=("PC",)), room(3, "B201", 40))
    fixed = event(1, size=20, day=1, start=1, weeks=W, required_tags=("PC",))
    lab = event(2, size=20, allowed_days=(1, 2), earliest=1, latest=2, weeks=W, required_tags=("PC",))
    tuesday = Constraint("day_window", {"event_ids": [2], "days": [2], "earliest": 3}, hard=False)
    inp = make_input(
        rooms, (fixed, lab), (tuesday,), days=(1, 2), weeks=W, workers=1, weights={"peak_smoothing": 10}
    )
    assert ps.groups_of(inp, {}) == ["*", "tag:PC"]
    res = ok(solve(inp))
    assert assigned(res.assignments, 2).day == 2  # PC: 2 of 2 > 1 (85 % of 2)
    # a cells list naming only Tuesday leaves Monday unpenalised
    only_tue = replace(
        inp, constraints=(tuesday, Constraint("peak_smoothing", {"cells": [{"day": 2, "period": 1, "group": "tag:PC"}]}, hard=False))
    )
    assert assigned(ok(solve(only_tue)).assignments, 2).day == 1


def test_threshold_and_weeks_are_counted_per_week() -> None:
    """Load is counted per teaching week: two classes in disjoint weeks never share a cell."""
    rooms = (room(1, "A101", 40), room(2, "A102", 40))
    a = event(1, size=20, day=1, start=1, weeks=(1, 2))
    b = event(2, size=20, allowed_days=(1, 2), earliest=1, latest=2, weeks=(3, 4))
    c = event(3, size=20, allowed_days=(1, 2), earliest=1, latest=2, weeks=(1, 2))
    inp = make_input(rooms, (a, b, c), (), days=(1, 2), weeks=(1, 2, 3, 4), workers=1, weights={"peak_smoothing": 1})
    placed = [
        Assignment(1, 1, 1, 2, (1,), frozenset({1, 2})),
        Assignment(2, 1, 1, 2, (2,), frozenset({3, 4})),
        Assignment(3, 1, 1, 2, (2,), frozenset({1, 2})),
    ]
    # threshold 85 % of 2 rooms = 1: weeks 1-2 hold a + c (one above, 2 periods x 2 weeks), weeks 3-4 b alone
    assert evaluate(inp, placed).penalties["peak_smoothing"] == 4
    half = replace(inp, constraints=(Constraint("peak_smoothing", {"threshold_pct": 100}, hard=False),))
    assert evaluate(half, placed).penalties.get("peak_smoothing", 0) == 0
    res = ok(solve(inp))
    assert res.objective_breakdown.get("peak_smoothing", 0) == 0
    assert assigned(res.assignments, 3).day == 2


def test_infeasible_instance_keeps_its_diagnosis_with_peak_smoothing_on() -> None:
    """A soft rule never relaxes a hard one: the same named conflict with the rule on or off."""
    rooms = (room(1, "A101", 40),)
    events = (
        event(1, size=30, day=1, start=1, weeks=W, required_room_ids=(1,)),
        event(2, size=30, day=1, start=1, weeks=W, required_room_ids=(1,)),
        event(3, size=30, allowed_days=(1, 2), earliest=1, latest=2, weeks=W),
    )
    for weight in (0, 10):
        inp = make_input(rooms, events, (), days=(1, 2), weeks=W, workers=1, weights={"peak_smoothing": weight})
        res = solve(inp)
        assert res.status == "INFEASIBLE"
        kinds = {k for d in res.diagnoses for k in d.constraint_kinds}
        assert "no_room_overlap" in kinds or "room_pin" in kinds, [d.message for d in res.diagnoses]
        assert "peak_smoothing" not in kinds
