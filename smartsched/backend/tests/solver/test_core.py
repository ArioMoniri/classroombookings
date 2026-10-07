"""Core behaviour: feasibility, determinism, validate() == solve(), serialisation, tiny fixture."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from app.solver.cpsat import solve
from app.solver.model import Assignment
from app.solver.repair import score, validate
from app.solver.serialization import input_from_dict, input_to_dict, load_input, result_from_dict, result_to_dict
from tests.solver.conftest import assigned, event, make_input, room

DATA = Path(__file__).parent / "data"


def test_tiny_fixture_solves_without_hard_violations() -> None:
    inp = load_input(DATA / "tiny.json")
    res = solve(inp)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.diagnoses
    assert res.hard_score == 100
    assert len(res.assignments) == len(inp.events)
    assert not [v for v in validate(inp, res.assignments) if v.hard]
    # MAT 112 is fixed Mon P4-P6 and prefers A101; FIZ 101 (120) can only fit A204
    a1, a2 = assigned(res.assignments, 1), assigned(res.assignments, 2)
    assert (a1.day, a1.start, a1.end) == (1, 4, 6)
    assert a1.room_ids == (1,)
    assert a2.room_ids == (2,)
    # the TIP room is reserved: only TIP 201 (required tag) may use it
    for a in res.assignments:
        if a.event_id != 4:
            assert 4 not in a.room_ids
    # evening programme in B/C, after P13
    a5 = assigned(res.assignments, 5)
    assert a5.start >= 13 and a5.room_ids[0] in (3, 5)
    # the lab needs the PC room and shares cohort+instructor with MAT 112 -> not Mon P4-P6
    a3 = assigned(res.assignments, 3)
    assert a3.room_ids == (3,)
    assert not (a3.day == 1 and a3.start <= 6 and a3.end >= 4)


def test_validate_agrees_with_solve(small_rooms: tuple) -> None:
    events = tuple(
        event(
            i,
            size=20 + 7 * i,
            duration=2,
            day=1 + i % 5,
            start=1 + (i * 3) % 12,
            preferred_room_ids=(1 + i % 5,),
            cohort_keys={f"C{i % 3}"},
        )
        for i in range(12)
    )
    inp = make_input(small_rooms, events)
    res = solve(inp)
    assert res.status in ("OPTIMAL", "FEASIBLE")
    hard, soft, breakdown = score(inp, res.assignments)
    assert (hard, soft) == (res.hard_score, res.soft_score)
    assert breakdown == res.objective_breakdown
    # the CP-SAT objective equals the independently evaluated penalty
    assert res.stats["objective_value"] == res.stats["evaluated_penalty"] == sum(breakdown.values())


def test_deterministic_with_fixed_seed(small_rooms: tuple) -> None:
    events = tuple(
        event(i, size=25, duration=2, allowed_days=(1, 2, 3), latest=10, preferred_building="C") for i in range(1, 9)
    )
    inp = make_input(small_rooms, events, workers=1, seed=7, time_limit_s=10)
    a = solve(inp)
    b = solve(inp)
    assert a.status == b.status in ("OPTIMAL", "FEASIBLE")
    assert a.assignments == b.assignments
    assert a.objective_breakdown == b.objective_breakdown


def test_validate_reports_manual_edit_conflicts(small_rooms: tuple) -> None:
    e1 = event(1, size=30, duration=2, day=1, start=4, cohort_keys={"C1"})
    e2 = event(2, size=30, duration=2, day=1, start=5, cohort_keys={"C2"})
    inp = make_input(small_rooms, (e1, e2))
    bad = [
        Assignment(1, 1, 4, 5, (1,), frozenset(range(1, 15))),
        Assignment(2, 1, 5, 6, (1,), frozenset(range(1, 15))),  # same room, overlapping P5
    ]
    kinds = {v.kind for v in validate(inp, bad) if v.hard}
    assert "no_room_overlap" in kinds
    # moving E2 to the wrong time violates fixed_time; a too-small room violates capacity
    bad2 = [
        Assignment(1, 1, 4, 5, (1,), frozenset(range(1, 15))),
        Assignment(2, 2, 5, 6, (3,), frozenset(range(1, 15))),
    ]
    assert "fixed_time" in {v.kind for v in validate(inp, bad2) if v.hard}
    tiny = replace(small_rooms[0], capacity=10)
    inp3 = replace(inp, rooms=(tiny,) + small_rooms[1:])
    good_time = [Assignment(1, 1, 4, 5, (1,), frozenset(range(1, 15)))]
    assert "capacity" in {v.kind for v in validate(inp3, good_time) if v.hard}
    assert "unassigned" in {v.kind for v in validate(inp3, good_time) if v.hard}


def test_serialization_round_trip() -> None:
    inp = load_input(DATA / "tiny.json")
    d = input_to_dict(inp)
    assert input_from_dict(json.loads(json.dumps(d))) == inp
    res = solve(inp)
    back = result_from_dict(json.loads(json.dumps(result_to_dict(res))))
    assert back.assignments == res.assignments
    assert back.status == res.status


def test_needs_room_false_only_gets_a_time(small_rooms: tuple) -> None:
    online = event(1, size=200, duration=2, allowed_days=(1,), needs_room=False, cohort_keys={"C"})
    f2f = event(2, size=30, duration=2, day=1, start=1, cohort_keys={"C"})
    res = solve(make_input(small_rooms, (online, f2f)))
    assert res.status in ("OPTIMAL", "FEASIBLE")
    a = assigned(res.assignments, 1)
    assert a.room_ids == ()
    assert a.start >= 3  # cohort overlap still applies


def test_week_split_events_may_share_a_room(small_rooms: tuple) -> None:
    rooms = (room(1, "A101", 58),)
    a = event(1, size=30, duration=2, day=1, start=1, weeks=tuple(range(1, 8)))
    b = event(2, size=30, duration=2, day=1, start=1, weeks=tuple(range(8, 15)))
    res = solve(make_input(rooms, (a, b)))
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert assigned(res.assignments, 1).room_ids == assigned(res.assignments, 2).room_ids == (1,)
    # but overlapping weeks cannot share
    c = event(2, size=30, duration=2, day=1, start=1, weeks=tuple(range(7, 15)))
    res2 = solve(make_input(rooms, (a, c)))
    assert res2.status == "INFEASIBLE"
    assert any("no_room_overlap" in d.constraint_kinds for d in res2.diagnoses)
