"""P19-00c (hard-rule integrity): a built-in hard rule switched to soft by an explicit constraint is named on
every result (``stats.waived_rules`` + a ``waived_rules`` warning with the breaking events), so a run never
claims hard 100 silently.  Feasible (strict), infeasible (strict, named), soft-weight (waived and reported)."""

from __future__ import annotations

from app.solver.cpsat import solve
from app.solver.diagnose import accepted_exceptions
from app.solver.model import Constraint
from app.solver.scoring import evaluate
from tests.solver.conftest import event, make_input, room

W1 = (3,)


def test_strict_capacity_is_infeasible_and_names_the_rule() -> None:
    inp = make_input((room(1, "A101", 50),), (event(1, size=180, weeks=W1, day=1, start=1),), weeks=W1)
    res = solve(inp)
    assert res.status == "INFEASIBLE" and res.assignments == []
    assert "waived_rules" not in res.stats
    assert any(d.severity == "error" and "capacity" in d.constraint_kinds for d in res.diagnoses)


def test_strict_feasible_run_reports_no_waiver() -> None:
    inp = make_input((room(1, "A101", 200),), (event(1, size=180, weeks=W1, day=1, start=1),), weeks=W1)
    res = solve(inp)
    assert res.status == "OPTIMAL" and res.hard_score == 100
    assert "waived_rules" not in res.stats and not any(d.code == "waived_rules" for d in res.diagnoses)


def test_soft_capacity_is_reported_as_waived_with_the_breaking_event() -> None:
    soft = (Constraint("capacity", {}, hard=False, weight=3),)
    inp = make_input(
        (room(1, "A101", 50),),
        (event(1, size=180, weeks=W1, day=1, start=1, label="ING 101"),),
        soft,
        weeks=W1,
        weights={"capacity": 1},
    )
    res = solve(inp)
    assert res.status == "OPTIMAL" and res.hard_score == 100  # the rules in force hold ...
    assert res.stats["waived_rules"] == ["capacity"]  # ... and the waived one is named
    assert res.stats["waived_violations"] == {"capacity": 1}
    d = next(d for d in res.diagnoses if d.code == "waived_rules")
    assert d.severity == "warning" and d.event_ids == [1] and d.params["rules"] == ["capacity"]
    assert "ING 101 needs 180 seats" in d.message and "covers the other hard rules only" in d.message
    assert res.objective_breakdown["capacity"] == (180 - 50) * 3  # the weight scales the penalty
    assert accepted_exceptions([d]) == {"waived": 1}
    ev = evaluate(inp, res.assignments)
    assert ev.waived == ("capacity",) and len(ev.waived_violations()) == 1 and not ev.hard_violations()


def test_targeted_soft_rule_is_waived_too_even_when_nothing_breaks_it() -> None:
    soft = (Constraint("room_tags", {"event_ids": [1]}, hard=False),)
    inp = make_input(
        (room(1, "A101", 60, tags=("PC",)),),
        (event(1, weeks=W1, day=1, start=1, required_tags={"PC"}),),
        soft,
        weeks=W1,
    )
    res = solve(inp)
    assert res.stats["waived_rules"] == ["room_tags"] and res.stats["waived_violations"] == {}
    assert "no placed event breaks them" in next(d.message for d in res.diagnoses if d.code == "waived_rules")
