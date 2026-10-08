"""Real-data modes (README "Real-data modes"): ``trust_locked_rooms`` (D1), ``fixed_conflicts_as_warnings``
(D2), ``best_effort`` (D3) and multi-room room sharing (F5).  Each mode: a feasible case, an infeasible
case with a named diagnosis, and a soft-weight case."""

from __future__ import annotations

from dataclasses import replace

from app.solver.cpsat import solve
from app.solver.model import Assignment, Constraint, SolverInput
from app.solver.repair import validate
from app.solver.seats import seats_feasible
from app.solver.serialization import input_from_dict, input_to_dict, result_from_dict, result_to_dict
from tests.solver.conftest import assigned, event, make_input, room

W1 = (3,)
OK = ("OPTIMAL", "FEASIBLE")


def _lock(eid: int, day: int, start: int, dur: int, rooms: tuple[int, ...], weeks=W1) -> Assignment:  # type: ignore[no-untyped-def]
    return Assignment(eid, day, start, start + dur - 1, rooms, frozenset(weeks))


def _hard(inp: SolverInput, assignments: list[Assignment]) -> list[str]:
    return [v.message for v in validate(inp, assignments) if v.hard]


# --------------------------------------------------------------------------------------------- D1


def _acu_input(trust: bool) -> SolverInput:
    rooms = (room(1, "A207", 120, exam_capacity=55), room(2, "A204", 156, exam_capacity=74))
    acu = event(1, size=122, duration=2, label="ACU 132", weeks=W1, day=1, start=3, locked=_lock(1, 1, 3, 2, (1,)))
    other = event(2, size=40, duration=2, weeks=W1, day=1, start=3)
    return make_input(rooms, (acu, other), weeks=W1, trust_locked_rooms=trust)


def test_trusted_lock_smaller_room_is_kept_with_warning() -> None:
    inp = _acu_input(trust=True)
    res = solve(inp)
    assert res.status in OK, [d.message for d in res.diagnoses]
    assert res.hard_score == 100
    assert assigned(res.assignments, 1).room_ids == (1,)
    warn = [d for d in res.diagnoses if d.code == "trusted_lock_capacity"]
    assert len(warn) == 1 and warn[0].severity == "warning" and warn[0].event_ids == [1]
    assert "ACU 132 expects 122 students but is locked to A207 (55 exam / 120 lecture seats)" in warn[0].message
    assert any("A204" in s for s in warn[0].suggestions)
    assert _hard(inp, res.assignments) == []


def test_untrusted_lock_smaller_room_is_infeasible_and_named() -> None:
    res = solve(_acu_input(trust=False))
    assert res.status == "INFEASIBLE" and res.assignments == []
    d = next(d for d in res.diagnoses if d.code == "locked_ineligible")
    assert d.event_ids == [1] and "capacity" in d.constraint_kinds and "capacity 120 < 122" in d.message


def test_trusted_lock_is_not_penalised_by_soft_capacity() -> None:
    """Soft capacity weight: an untrusted short room is penalised (weight scales it), a trusted lock not."""
    rooms = (room(1, "A101", 50), room(2, "A102", 50))
    soft = (Constraint("capacity", {}, hard=False, weight=3),)
    locked = event(1, size=60, weeks=W1, day=1, start=1, locked=_lock(1, 1, 1, 2, (1,)))
    free = event(2, size=60, weeks=W1, day=2, start=1)
    base = make_input(rooms, (locked, free), soft, weeks=W1, trust_locked_rooms=True, weights={"capacity": 1})
    res = solve(base)
    assert res.status in OK and res.hard_score == 100
    assert res.objective_breakdown.get("capacity") == 10 * 3  # only the free event: 10 seats short x 3
    res2 = solve(replace(base, constraints=(Constraint("capacity", {}, hard=False, weight=5),)))
    assert res2.objective_breakdown.get("capacity") == 10 * 5
    assert res.stats["objective_value"] == res.stats["evaluated_penalty"]


def test_trusted_lock_tag_mismatch_is_a_warning() -> None:
    rooms = (room(1, "C205", 30), room(2, "A103", 47, tags=("PC",)))
    e = event(1, size=20, weeks=W1, day=1, start=1, required_tags=("PC",), locked=_lock(1, 1, 1, 2, (1,)))
    res = solve(make_input(rooms, (e,), weeks=W1, trust_locked_rooms=True))
    assert res.status in OK and res.hard_score == 100 and assigned(res.assignments, 1).room_ids == (1,)
    assert [d.code for d in res.diagnoses] == ["trusted_lock_tags"]
    strict = solve(make_input(rooms, (e,), weeks=W1))
    assert strict.status == "INFEASIBLE" and any(d.code == "locked_ineligible" for d in strict.diagnoses)


def test_lecture_locked_to_several_rooms_uses_them_all() -> None:
    """Bahar locks big lectures to "A 101 / A 106": a single-room request with a 2-room lock."""
    rooms = (room(1, "A101", 58), room(2, "A106", 58), room(3, "A204", 156))
    e = event(1, size=110, weeks=W1, day=1, start=1, locked=_lock(1, 1, 1, 2, (1, 2)))
    inp = make_input(rooms, (e,), weeks=W1)
    res = solve(inp)
    assert res.status in OK and res.hard_score == 100, [d.message for d in res.diagnoses]
    assert assigned(res.assignments, 1).room_ids == (1, 2)
    assert _hard(inp, res.assignments) == []


# --------------------------------------------------------------------------------------------- D2


def _clash_input(waive: bool, flex_window: tuple[int, int] = (1, 18)) -> SolverInput:
    rooms = (room(1, "A101", 58), room(2, "A102", 58), room(3, "A106", 58))
    ins = ("INS:7",)
    a = event(1, label="MAT 101", weeks=W1, day=1, start=3, instructor_keys=ins)
    b = event(2, label="MAT 205", weeks=W1, day=1, start=4, instructor_keys=ins)  # overlaps P4
    flex = event(
        3,
        label="MAT 300",
        weeks=W1,
        allowed_days=(1,),
        earliest=flex_window[0],
        latest=flex_window[1],
        instructor_keys=ins,
    )
    return make_input(rooms, (a, b, flex), weeks=W1, days=(1,), fixed_conflicts_as_warnings=waive)


def test_fixed_conflict_waived_as_input_warning() -> None:
    inp = _clash_input(waive=True)
    res = solve(inp)
    assert res.status in OK and res.hard_score == 100, [d.message for d in res.diagnoses]
    d = next(d for d in res.diagnoses if d.code == "input_conflict")
    assert d.severity == "warning" and d.event_ids == [1, 2] and "no_instructor_overlap" in d.constraint_kinds
    assert "MAT 101" in d.message and "MAT 205" in d.message
    assert any("move MAT 101 or MAT 205" in s for s in d.suggestions)
    assert any("instructor name" in s for s in d.suggestions)
    # both keep their requested times; the flexible event avoids both (P3-P5 is busy)
    assert (assigned(res.assignments, 1).start, assigned(res.assignments, 2).start) == (3, 4)
    flex = assigned(res.assignments, 3)
    assert flex.end < 3 or flex.start > 5
    assert _hard(inp, res.assignments) == []


def test_fixed_conflict_without_waiver_is_infeasible_and_named() -> None:
    res = solve(_clash_input(waive=False))
    assert res.status == "INFEASIBLE"
    d = next(d for d in res.diagnoses if d.code == "fixed_conflict")
    assert d.severity == "error" and sorted(d.event_ids) == [1, 2]


def test_waiver_never_frees_a_flexible_event() -> None:
    """A flexible event whose window only fits on top of the fixed pair still clashes: error."""
    res = solve(_clash_input(waive=True, flex_window=(3, 5)))
    assert res.status == "INFEASIBLE"
    assert any(3 in d.event_ids and d.severity == "error" for d in res.diagnoses)


def test_waived_pair_costs_no_soft_penalty() -> None:
    """Soft-weight: the waived pair adds nothing; the flexible event's soft day window (weight) decides."""
    base = _clash_input(waive=True)
    window = Constraint("day_window", {"event_ids": [3], "earliest": 10, "latest": 18}, hard=False, weight=4)
    res = solve(replace(base, constraints=(window,)))
    assert res.status in OK and res.hard_score == 100
    assert assigned(res.assignments, 3).start >= 10 and res.objective_breakdown.get("day_window", 0) == 0
    assert res.stats["objective_value"] == res.stats["evaluated_penalty"]


# --------------------------------------------------------------------------------------------- D3


def _pigeonhole_input(best_effort: bool) -> SolverInput:
    rooms = (room(1, "A101", 58), room(2, "A102", 58))
    events = tuple(event(i, size=30, weeks=W1, day=1, start=1, label=f"C{i}") for i in (1, 2, 3))
    extra = event(4, size=30, weeks=W1, allowed_days=(1,), preferred_room_ids=(2,))
    huge = event(5, size=500, weeks=W1, day=2, start=1, label="HUGE")
    return make_input(rooms, (*events, extra, huge), weeks=W1, days=(1, 2), best_effort=best_effort)


def test_best_effort_returns_maximum_placement() -> None:
    inp = _pigeonhole_input(best_effort=True)
    res = solve(inp)
    assert res.status == "INFEASIBLE"
    assert res.stats["partial"] is True and res.stats["events_total"] == 5
    assert res.stats["placed"] == 3 and res.stats["unplaced"] == 2  # 2 rooms for 3 fixed + HUGE has no room
    assert 5 in res.stats["unplaced_ids"]
    placed = {a.event_id for a in res.assignments}
    assert len(placed) == 3 and 5 not in placed and 4 in placed
    assert res.hard_score == 100  # every hard rule holds for the placed events
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed))
    assert _hard(sub, res.assignments) == []
    assert res.diagnoses[0].code == "partial" and "3 of 5 events placed" in res.diagnoses[0].message
    # every unplaced event has a reason; HUGE is explained once (static "no eligible room")
    unplaced = set(res.stats["unplaced_ids"])
    for eid in unplaced:
        assert any(d.event_ids == [eid] or (eid in d.event_ids and d.code == "pigeonhole") for d in res.diagnoses)
    assert sum(1 for d in res.diagnoses if d.event_ids == [5]) == 1


def test_best_effort_off_keeps_strict_result() -> None:
    res = solve(_pigeonhole_input(best_effort=False))
    assert res.status == "INFEASIBLE" and res.assignments == [] and "partial" not in res.stats


def test_best_effort_phase_two_uses_the_objective() -> None:
    """Soft-weight: the placed flexible event takes its preferred room in the partial timetable."""
    res = solve(_pigeonhole_input(best_effort=True))
    assert assigned(res.assignments, 4).room_ids == (2,) and res.objective_breakdown.get("room_preference", 0) == 0
    inp = replace(
        _pigeonhole_input(best_effort=True),
        events=tuple(replace(e, preferred_room_ids=(1,)) if e.id == 4 else e for e in _pigeonhole_input(True).events),
    )
    assert assigned(solve(inp).assignments, 4).room_ids == (1,)


def test_best_effort_overlapping_locks_unplace_one() -> None:
    rooms = (room(1, "A101", 58),)
    a = event(1, weeks=W1, day=1, start=1, locked=_lock(1, 1, 1, 2, (1,)))
    b = event(2, weeks=W1, day=1, start=2, locked=_lock(2, 1, 2, 2, (1,)))
    c = event(3, weeks=W1, day=1, start=5)
    res = solve(make_input(rooms, (a, b, c), weeks=W1, best_effort=True))
    assert res.status == "INFEASIBLE" and res.stats["placed"] == 2 and res.hard_score == 100
    assert 3 in {x.event_id for x in res.assignments}
    assert any(d.code == "locked_overlap" for d in res.diagnoses)


def test_best_effort_is_deterministic() -> None:
    inp = replace(_pigeonhole_input(best_effort=True), workers=4, seed=3)
    r1, r2 = solve(inp), solve(inp)
    assert sorted((a.event_id, a.room_ids) for a in r1.assignments) == sorted(
        (a.event_id, a.room_ids) for a in r2.assignments
    )


def test_modes_round_trip_through_json() -> None:
    inp = replace(_pigeonhole_input(True), trust_locked_rooms=True, fixed_conflicts_as_warnings=True)
    back = input_from_dict(input_to_dict(inp))
    assert (back.trust_locked_rooms, back.fixed_conflicts_as_warnings, back.best_effort) == (True, True, True)
    res = solve(inp)
    assert [d.code for d in result_from_dict(result_to_dict(res)).diagnoses] == [d.code for d in res.diagnoses]


# --------------------------------------------------------------------------------------------- F5


def _split_exam(i: int, size: int, rooms: tuple[int, ...] | None, max_rooms: int = 2, **kw: object):  # type: ignore[no-untyped-def]
    lock = _lock(i, 1, 4, 2, rooms, (15,)) if rooms else None
    return event(
        i,
        size=size,
        duration=2,
        kind="exam",
        weeks=(15,),
        day=1,
        start=4,
        share_room=True,
        max_rooms=max_rooms,
        locked=lock,
        **kw,
    )


def _final_rooms():  # type: ignore[no-untyped-def]
    return (
        room(1, "A204", 156, exam_capacity=74),
        room(2, "A102", 96, exam_capacity=48),
        room(3, "C301", 72, exam_capacity=35),
    )


def test_two_split_exams_share_a_room_pair() -> None:
    """PSI 212 + FZT 260 in A 204 + A 102 (Final plan): 70 + 50 seats <= 74 + 48."""
    exams = (_split_exam(1, 70, (1, 2), label="PSI 212"), _split_exam(2, 50, (1, 2), label="FZT 260"))
    inp = make_input(_final_rooms(), exams, weeks=(15,))
    res = solve(inp)
    assert res.status in OK and res.hard_score == 100, [d.message for d in res.diagnoses]
    assert assigned(res.assignments, 1).room_ids == (1, 2) == assigned(res.assignments, 2).room_ids
    assert _hard(inp, res.assignments) == []


def test_split_exams_over_the_seat_budget_are_named() -> None:
    exams = (_split_exam(1, 80, (1, 2), label="PSI 212"), _split_exam(2, 50, (1, 2), label="FZT 260"))  # 130 > 122
    inp = make_input(_final_rooms(), exams, weeks=(15,))
    res = solve(inp)
    assert res.status == "INFEASIBLE"
    d = next(d for d in res.diagnoses if d.code == "locked_overlap")
    assert sorted(d.event_ids) == [1, 2] and "need 130 seats" in d.message and "seat 122" in d.message
    bad = [_lock(1, 1, 4, 2, (1, 2), (15,)), _lock(2, 1, 4, 2, (1, 2), (15,))]
    assert any("seat 122 but the exams need 130" in m for m in _hard(inp, bad))


def test_split_exam_seats_respect_each_room() -> None:
    """Hall condition: a single-room exam in A 102 leaves 48-30 seats there for the split exam."""
    single = event(
        3,
        size=30,
        duration=2,
        kind="exam",
        weeks=(15,),
        day=1,
        start=4,
        share_room=True,
        locked=_lock(3, 1, 4, 2, (2,), (15,)),
    )
    fits = (_split_exam(1, 90, (1, 2)), single)  # 74 + 18 = 92 >= 90
    assert solve(make_input(_final_rooms(), fits, weeks=(15,))).status in OK
    too_big = (_split_exam(1, 93, (1, 2)), single)  # 93 > 92 although 93 + 30 <= 122 - in total seats
    res = solve(make_input(_final_rooms(), too_big, weeks=(15,)))
    assert res.status == "INFEASIBLE" and any(d.code == "locked_overlap" for d in res.diagnoses)
    assert seats_feasible({1: 90, 3: 30}, {1: [1, 2], 3: [2]}, {1: 74, 2: 48})
    assert not seats_feasible({1: 93, 3: 30}, {1: [1, 2], 3: [2]}, {1: 74, 2: 48})


def test_unlocked_split_exam_shares_with_preference_weight() -> None:
    """Soft-weight: an unlocked split exam prefers C 301; with the preference it shares rooms with a locked one."""
    locked = _split_exam(1, 60, (1, 2))
    free = _split_exam(2, 50, None, max_rooms=2, preferred_room_ids=(1, 2))
    rooms = _final_rooms()[:2]  # only A 204 + A 102: sharing is the only option
    inp = make_input(rooms, (locked, free), weeks=(15,))
    res = solve(inp)
    assert res.status in OK and res.hard_score == 100, [d.message for d in res.diagnoses]
    assert set(assigned(res.assignments, 2).room_ids) <= {1, 2}
    assert _hard(inp, res.assignments) == []
    inp3 = make_input(
        _final_rooms(), (locked, replace(free, preferred_room_ids=(3,), size=30, max_rooms=1)), weeks=(15,)
    )
    res3 = solve(inp3)
    assert assigned(res3.assignments, 2).room_ids == (3,) and res3.objective_breakdown.get("room_preference", 0) == 0
