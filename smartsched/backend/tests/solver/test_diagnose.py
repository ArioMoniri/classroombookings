"""Infeasibility diagnosis: static checker, assumption cores, relaxation + per-event explanations."""

from __future__ import annotations

from dataclasses import replace

from app.solver.build import prepare
from app.solver.cpsat import solve
from app.solver.diagnose import core_diagnosis, explain_event, relaxation_diagnosis, static_check
from app.solver.model import Assignment, Block
from tests.solver.conftest import event, make_input, room

ALL = frozenset(range(1, 15))


def test_static_checker_catalogue() -> None:
    rooms = (room(1, "A101", 58), room(2, "B207", 60, tags=("PC",)))
    events = (
        event(1, size=500, day=1, start=1),  # larger than every room
        event(2, day=1, start=1, required_tags={"TIP"}),  # tag nobody has
        event(3, day=1, start=1, required_room_ids={42}),  # pin to unknown room
        event(4, day=1, start=18, duration=2),  # outside the grid
        event(5, allowed_days=(1,), locked=Assignment(5, 2, 1, 2, (1,), ALL)),  # locked
        event(6, allowed_days=(1,), locked=Assignment(6, 2, 2, 3, (1,), ALL)),  # overlapping lock
        event(7, day=3, start=1, cohort_keys={"C"}),
        event(8, day=3, start=1, cohort_keys={"C"}),  # fixed-vs-fixed cohort clash
        event(9, day=4, start=1),
        event(10, day=4, start=1),
        event(11, day=4, start=1),  # three fixed events, two rooms -> pigeonhole
    )
    prep = prepare(make_input(rooms, events))
    diags = static_check(prep)
    by_event: dict[int, set[str]] = {}
    for d in diags:
        assert d.severity == "error"
        assert d.message and d.suggestions
        for e in d.event_ids:
            by_event.setdefault(e, set()).update(d.constraint_kinds)
    assert "capacity" in by_event[1]
    assert "room_tags" in by_event[2]
    assert "room_pin" in by_event[3]
    assert "fixed_time" in by_event[4]
    assert "no_room_overlap" in by_event[5] and "no_room_overlap" in by_event[6]
    assert "no_cohort_overlap" in by_event[7] and "no_cohort_overlap" in by_event[8]
    assert {9, 10, 11} <= set(by_event) and "no_room_overlap" in by_event[9]
    res = solve(make_input(rooms, events))
    assert res.status == "INFEASIBLE" and res.stats["solver_status"] == "STATIC_INFEASIBLE"


def test_core_is_small_and_relaxation_explains() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    # five flexible 2-period events in a P1-P4 window with two rooms (room for four), plus happy events
    crammed = tuple(event(i, duration=2, allowed_days=(1,), earliest=1, latest=4) for i in (1, 2, 3, 4, 5))
    happy = tuple(event(i, duration=2, day=2, start=i) for i in (10, 11, 12))
    inp = make_input(rooms, crammed + happy)
    prep = prepare(inp)
    core, stats = core_diagnosis(prep, 10.0)
    assert core and stats["core_final"] <= stats["core_initial"]
    assert set(core[0].event_ids) <= {1, 2, 3, 4, 5}
    assert not set(core[0].event_ids) & {10, 11, 12}
    assert "no_room_overlap" in core[0].constraint_kinds
    relax, rstats, placed = relaxation_diagnosis(prep, 10.0)
    assert rstats["unplaced"] == 1
    assert len(placed) == 7
    per_event = [d for d in relax if d.constraint_kinds]
    assert per_event and "busy" in per_event[0].message
    assert any(s.startswith("release") for s in per_event[0].suggestions)


def test_explain_event_names_rooms_and_holders() -> None:
    rooms = (room(1, "A101", 58), room(2, "A204", 156, tags=("TIP",)))
    big = event(1, size=100, day=1, start=4, duration=3, forbidden_tags={"TIP"})
    other = event(2, size=30, day=1, start=5, duration=2)
    inp = make_input(rooms, (big, other), blocks=(Block(1, None, 1, 1, 2),))
    prep = prepare(inp)
    d = explain_event(prep, 1, {2: Assignment(2, 1, 5, 6, (1,), ALL)})
    assert d.event_ids == [1]
    assert "A204" not in d.message or "room_tags" in d.constraint_kinds
    assert "capacity" in d.constraint_kinds or "room_tags" in d.constraint_kinds
    assert d.suggestions


def test_cohort_core_named_in_full_solve() -> None:
    rooms = tuple(room(i, f"A10{i}", 58) for i in range(1, 5))
    evs = tuple(
        event(i, duration=2, allowed_days=(1,), earliest=1, latest=4, cohort_keys={"PROG:X:Y1"}) for i in (1, 2, 3)
    )
    res = solve(make_input(rooms, evs))
    assert res.status == "INFEASIBLE"
    kinds = {k for d in res.diagnoses for k in d.constraint_kinds}
    assert "no_cohort_overlap" in kinds
    named = {e for d in res.diagnoses for e in d.event_ids}
    assert named & {1, 2, 3}
    assert res.stats.get("core_initial", 0) >= 1


def test_alternative_period_suggestion() -> None:
    rooms = (room(1, "A101", 58),)
    a = event(1, day=1, start=1, duration=2)
    b = event(2, day=1, start=2, duration=2)
    res = solve(make_input(rooms, (a, b)))
    assert res.status == "INFEASIBLE"
    text = " ".join(s for d in res.diagnoses for s in d.suggestions)
    assert "alternative periods" in text or "move" in text


def test_timeout_returns_status_timeout() -> None:
    rooms = tuple(room(i, f"R{i}", 58) for i in range(1, 4))
    evs = tuple(event(i, duration=2, allowed_days=(1, 2, 3, 4, 5)) for i in range(1, 40))
    inp = replace(make_input(rooms, evs), time_limit_s=0.01, workers=1)
    res = solve(inp)
    assert res.status in ("TIMEOUT", "FEASIBLE", "OPTIMAL")
    if res.status == "TIMEOUT":
        assert res.diagnoses and res.diagnoses[0].severity == "warning"
