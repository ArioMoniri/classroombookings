"""Round-1 R1-S-02: a hard ``day_window`` ("no classes after 17:30" for a whole programme) that removes the only
time of a class the planning list locks later in the day crashed the static checker (IndexError on an empty time
domain), so the pre-check answered 500 and the run ended ERROR. The class must be explained (``no_time`` naming the
window rule) and left out; every other class keeps every hard rule.

Feasible / infeasible (named) / soft-weight cases; deterministic.
"""

from __future__ import annotations

from app.solver.build import prepare
from app.solver.cpsat import solve
from app.solver.diagnose import static_check
from app.solver.model import Assignment, Constraint
from tests.solver.conftest import assigned, event, make_input, room

ALL = frozenset(range(1, 15))
ROOMS = (room(1, "A101", 58), room(2, "B201", 60))


def _late_locked(eid: int = 1) -> object:
    # locked at P13-P14 (18:00) like the evening nursing rows of the Bahar list
    return event(
        eid, size=30, duration=2, cohort_keys={"PROG:Hemşirelik:Y1"}, locked=Assignment(eid, 1, 13, 14, (1,), ALL)
    )


def _window(hard: bool = True, weight: int = 1) -> Constraint:
    return Constraint("day_window", {"program": "Hemşirelik", "earliest": 1, "latest": 11}, hard, weight, 9)


def test_window_that_removes_a_locked_time_is_explained_not_a_crash() -> None:
    other = event(2, size=20, day=1, start=1, cohort_keys={"PROG:Hemşirelik:Y1"})
    inp = make_input(ROOMS, (_late_locked(), other), (_window(),), best_effort=True)
    diags = static_check(prepare(inp))  # used to raise IndexError
    mine = [d for d in diags if d.event_ids == [1]]
    assert [d.code for d in mine] == ["no_time"], [(d.code, d.message) for d in diags]
    assert "day_window" in mine[0].constraint_kinds and "#9" in mine[0].message
    res = solve(inp)
    assert res.status != "ERROR" and res.hard_score == 100
    assert {a.event_id for a in res.assignments} == {2}


def test_window_that_keeps_the_locked_time_is_feasible() -> None:
    late = Constraint("day_window", {"program": "Hemşirelik", "earliest": 1, "latest": 16}, True, 1, 9)
    res = solve(make_input(ROOMS, (_late_locked(),), (late,)))
    assert res.status == "OPTIMAL" and res.hard_score == 100
    assert assigned(res.assignments, 1).start == 13


def test_soft_window_keeps_the_lock_and_costs_weight() -> None:
    light = solve(make_input(ROOMS, (_late_locked(),), (_window(False, 1),)))
    heavy = solve(make_input(ROOMS, (_late_locked(),), (_window(False, 4),)))
    for res in (light, heavy):
        assert res.status == "OPTIMAL" and res.hard_score == 100 and assigned(res.assignments, 1).start == 13
    assert heavy.objective_breakdown["day_window"] > light.objective_breakdown["day_window"] > 0


def test_deterministic() -> None:
    inp = make_input(ROOMS, (_late_locked(), event(2, allowed_days=(1, 2))), (_window(),), best_effort=True, seed=3)
    a, b = solve(inp), solve(inp)
    assert a.assignments == b.assignments and a.hard_score == b.hard_score
