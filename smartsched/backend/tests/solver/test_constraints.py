"""Per constraint kind: minimal feasible, minimal infeasible (diagnosis names the kind and the
events) and a soft-weight case where changing the weight changes the choice."""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.solver.cpsat import solve
from app.solver.model import Assignment, Block, Constraint, SolverResult
from app.solver.repair import validate
from tests.solver.conftest import assigned, event, make_input, room

ALL = tuple(range(1, 15))


def ok(res: SolverResult) -> SolverResult:
    assert res.status in ("OPTIMAL", "FEASIBLE"), (res.status, res.diagnoses, res.stats.get("error"))
    assert res.hard_score == 100, res.diagnoses
    return res


def infeasible(res: SolverResult, kind: str, *event_ids: int) -> None:
    assert res.status == "INFEASIBLE", res.status
    assert res.diagnoses, "no diagnosis produced"
    matching = [d for d in res.diagnoses if kind in d.constraint_kinds]
    assert matching, f"no diagnosis names {kind}: {[d.constraint_kinds for d in res.diagnoses]}"
    named = set().union(*(set(d.event_ids) for d in matching))
    assert set(event_ids) <= named, f"{event_ids} not all named in {named}: {[d.message for d in matching]}"
    for d in res.diagnoses:
        assert d.message
        assert d.severity in ("error", "warning", "info")


def room_of(res: SolverResult, eid: int) -> int:
    return assigned(res.assignments, eid).room_ids[0]


# ----------------------------------------------------------------------------- capacity


def test_capacity_feasible_and_infeasible() -> None:
    rooms = (room(1, "A101", 58), room(2, "A204", 156))
    ok_res = ok(solve(make_input(rooms, (event(1, size=100, day=1, start=1),))))
    assert room_of(ok_res, 1) == 2
    res = solve(make_input(rooms, (event(7, size=200, day=1, start=1),)))
    infeasible(res, "capacity", 7)
    assert any("split" in s for d in res.diagnoses for s in d.suggestions)


def test_capacity_soft_weight_changes_choice() -> None:
    rooms = (room(1, "A101", 20), room(2, "A204", 40))
    ev = event(1, size=30, day=1, start=1, preferred_room_ids=(1,))
    soft = (Constraint("capacity", {}, hard=False),)
    small_pref = solve(
        make_input(rooms, (ev,), soft, weights={"capacity": 1, "room_preference": 100, "min_capacity_waste": 0})
    )
    assert ok(small_pref).objective_breakdown.get("capacity") == 10  # 10 seats short × weight 1
    assert room_of(small_pref, 1) == 1
    strict = solve(
        make_input(rooms, (ev,), soft, weights={"capacity": 100, "room_preference": 1, "min_capacity_waste": 0})
    )
    assert room_of(ok(strict), 1) == 2
    assert [
        v
        for v in validate(strict.inp if hasattr(strict, "inp") else make_input(rooms, (ev,), soft), strict.assignments)
        if v.hard
    ] == []


def test_capacity_exam_split_across_rooms() -> None:
    rooms = (
        room(1, "A101", 58, exam_capacity=30),
        room(2, "A106", 58, exam_capacity=30),
        room(3, "A107", 58, exam_capacity=30),
    )
    exam = event(1, size=70, duration=2, kind="exam", weeks=(15,), day=1, start=1, max_rooms=3)
    inp = make_input(rooms, (exam,), weeks=(15,))
    res = ok(solve(inp))
    assert len(assigned(res.assignments, 1).room_ids) == 3
    too_big = replace(exam, size=100)
    infeasible(solve(replace(inp, events=(too_big,))), "capacity", 1)
    # max_rooms=2 cannot reach 70 either
    infeasible(solve(replace(inp, events=(replace(exam, max_rooms=2),))), "capacity", 1)


# ----------------------------------------------------------------------------- overlaps


def test_no_room_overlap() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    a, b = event(1, day=1, start=1, duration=3), event(2, day=1, start=3, duration=2)
    res = ok(solve(make_input(rooms, (a, b))))
    assert room_of(res, 1) != room_of(res, 2)
    infeasible(solve(make_input(rooms[:1], (a, b))), "no_room_overlap", 1, 2)
    # cannot be softened: warning recorded, rule stays hard
    res3 = solve(make_input(rooms[:1], (a, b), (Constraint("no_room_overlap", {}, hard=False),)))
    assert res3.status == "INFEASIBLE"
    assert any("cannot be soft" in w for w in res3.stats["warnings"])


def test_no_room_overlap_flexible_events_use_cp_core() -> None:
    """Not detectable statically: three flexible 2-period events, one room, window P1-P4."""
    rooms = (room(1, "A101", 58),)
    evs = tuple(event(i, duration=2, allowed_days=(1,), earliest=1, latest=4) for i in (1, 2, 3))
    res = solve(make_input(rooms, evs))
    assert res.stats["solver_status"] == "INFEASIBLE"
    infeasible(res, "no_room_overlap")
    assert res.stats.get("core_initial", 0) >= 1 or res.stats.get("unplaced") == 1
    named = set().union(*(set(d.event_ids) for d in res.diagnoses))
    assert named & {1, 2, 3}


def test_no_cohort_overlap() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    a = event(1, day=1, start=1, duration=3, cohort_keys={"PROG:X:Y1"})
    b = event(2, day=1, start=3, duration=2, cohort_keys={"PROG:X:Y1"})
    c = event(3, day=1, start=3, duration=2, cohort_keys={"PROG:X:Y2"})
    ok(solve(make_input(rooms, (a, c))))
    infeasible(solve(make_input(rooms, (a, b))), "no_cohort_overlap", 1, 2)
    # flexible event of the same cohort is pushed away from the fixed one
    flex = event(4, allowed_days=(1,), duration=2, cohort_keys={"PROG:X:Y1"})
    res = ok(solve(make_input(rooms, (a, flex))))
    assert assigned(res.assignments, 4).start >= 4
    # disjoint weeks never conflict
    ok(solve(make_input(rooms, (replace(a, weeks=frozenset(range(1, 8))), replace(b, weeks=frozenset(range(8, 15)))))))


def test_no_instructor_overlap() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    a = event(1, day=2, start=5, duration=2, instructor_keys={"INS:ayse"})
    b = event(2, day=2, start=6, duration=2, instructor_keys={"INS:ayse"})
    infeasible(solve(make_input(rooms, (a, b))), "no_instructor_overlap", 1, 2)
    ok(solve(make_input(rooms, (a, replace(b, instructor_keys=frozenset({"INS:veli"}))))))
    flex = event(3, allowed_days=(2,), duration=2, earliest=5, latest=8, instructor_keys={"INS:ayse"})
    res = ok(solve(make_input(rooms, (a, flex))))
    assert assigned(res.assignments, 3).start == 7


# ----------------------------------------------------------------------------- fixed_time


def test_fixed_time_hard_and_static_errors() -> None:
    rooms = (room(1, "A101", 58),)
    res = ok(solve(make_input(rooms, (event(1, day=3, start=7, duration=2),))))
    a = assigned(res.assignments, 1)
    assert (a.day, a.start, a.end) == (3, 7, 8)
    infeasible(solve(make_input(rooms, (event(2, day=3, start=18, duration=2),))), "fixed_time", 2)
    infeasible(solve(make_input(rooms, (event(3, day=6, start=1),))), "fixed_time", 3)  # day 6 not in grid
    # locked assignment wins and is honoured; overlapping locks are reported
    locked = Assignment(4, 2, 2, 3, (1,), frozenset(ALL))
    res2 = ok(solve(make_input(rooms, (event(4, allowed_days=(1, 2, 3), locked=locked),))))
    assert assigned(res2.assignments, 4) == locked
    lock2 = Assignment(5, 2, 3, 4, (1,), frozenset(ALL))
    infeasible(
        solve(
            make_input(
                rooms, (event(4, allowed_days=(1, 2), locked=locked), event(5, allowed_days=(1, 2), locked=lock2))
            )
        ),
        "no_room_overlap",
        4,
        5,
    )


def test_fixed_time_soft_weight_changes_choice() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    a = event(1, day=1, start=1, duration=2)
    b = event(2, allowed_days=(1, 2), duration=2, earliest=1, latest=2)
    cons = (
        Constraint("fixed_time", {"event_ids": [2], "day": 2}, hard=False, id=1),
        Constraint("day_window", {"event_ids": [2], "days": [2], "earliest": 5}, hard=False, id=2),
    )
    prefer_time = ok(solve(make_input(rooms, (a, b), cons, weights={"fixed_time": 50, "day_window": 1})))
    assert assigned(prefer_time.assignments, 2).day == 2
    prefer_window = ok(solve(make_input(rooms, (a, b), cons, weights={"fixed_time": 1, "day_window": 50})))
    assert assigned(prefer_window.assignments, 2).day == 1
    # implicit fixed day/start can be softened globally
    one_room = (room(1, "A101", 58),)
    c = event(3, day=1, start=1, duration=2, allowed_days=(1, 2))
    soft = solve(make_input(one_room, (a, c), (Constraint("fixed_time", {}, hard=False),)))
    assert ok(soft).objective_breakdown.get("fixed_time", 0) > 0
    infeasible(solve(make_input(one_room, (a, c))), "no_room_overlap", 1, 3)


# ----------------------------------------------------------------------------- room_tags / pin / forbid


def test_room_tags() -> None:
    rooms = (room(1, "A101", 58), room(2, "B207", 60, tags=("PC",)))
    res = ok(solve(make_input(rooms, (event(1, day=1, start=1, required_tags={"PC"}),))))
    assert room_of(res, 1) == 2
    res2 = ok(solve(make_input(rooms, (event(1, day=1, start=1, forbidden_tags={"PC"}),))))
    assert room_of(res2, 1) == 1
    infeasible(solve(make_input(rooms, (event(5, day=1, start=1, required_tags={"TIP"}),))), "room_tags", 5)
    # targeted hard constraint
    res3 = ok(
        solve(
            make_input(
                rooms,
                (event(1, day=1, start=1),),
                (Constraint("room_tags", {"event_ids": [1], "required_tags": ["PC"]}, True),),
            )
        )
    )
    assert room_of(res3, 1) == 2


def test_room_tags_soft_weight_changes_choice() -> None:
    rooms = (room(1, "A101", 58), room(2, "B207", 60, tags=("PC",)))
    ev = event(1, day=1, start=1, required_tags={"PC"}, preferred_room_ids=(1,))
    soft = (Constraint("room_tags", {}, hard=False),)
    pref = ok(solve(make_input(rooms, (ev,), soft, weights={"room_tags": 1, "room_preference": 100})))
    assert room_of(pref, 1) == 1 and pref.objective_breakdown["room_tags"] == 1
    tags = ok(solve(make_input(rooms, (ev,), soft, weights={"room_tags": 100, "room_preference": 1})))
    assert room_of(tags, 1) == 2


def test_room_pin() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    res = ok(solve(make_input(rooms, (event(1, day=1, start=1, required_room_ids={2}),))))
    assert room_of(res, 1) == 2
    infeasible(solve(make_input(rooms, (event(1, day=1, start=1, required_room_ids={99}),))), "room_pin", 1)
    infeasible(
        solve(
            make_input(
                rooms,
                (event(1, day=1, start=1, required_room_ids={2}), event(2, day=1, start=1, required_room_ids={2})),
            )
        ),
        "no_room_overlap",
        1,
        2,
    )
    ev = event(1, size=20, day=1, start=1, required_room_ids={2})
    big = (room(1, "A101", 20), room(2, "A204", 156))
    soft = (Constraint("room_pin", {}, hard=False),)
    waste = ok(solve(make_input(big, (ev,), soft, weights={"room_pin": 1, "min_capacity_waste": 100})))
    assert room_of(waste, 1) == 1
    pin = ok(solve(make_input(big, (ev,), soft, weights={"room_pin": 100, "min_capacity_waste": 1})))
    assert room_of(pin, 1) == 2


def test_room_forbid() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    res = ok(solve(make_input(rooms, (event(1, day=1, start=1, forbidden_room_ids={1}),))))
    assert room_of(res, 1) == 2
    infeasible(solve(make_input(rooms, (event(1, day=1, start=1, forbidden_room_ids={1, 2}),))), "room_forbid", 1)
    ev = event(1, size=20, day=1, start=1, forbidden_room_ids={1})
    big = (room(1, "A101", 20), room(2, "A204", 156))
    c = Constraint("room_forbid", {"event_ids": [1], "room_ids": [1]}, hard=False)
    inp = make_input(
        big, (replace(ev, forbidden_room_ids=frozenset()),), (c,), weights={"room_forbid": 1, "min_capacity_waste": 100}
    )
    assert room_of(ok(solve(inp)), 1) == 1
    assert room_of(ok(solve(replace(inp, weights={"room_forbid": 100, "min_capacity_waste": 1}))), 1) == 2


# ----------------------------------------------------------------------------- preferences


def test_building_preference() -> None:
    rooms = (room(1, "A204", 156), room(2, "C301", 72))
    ev = event(1, size=30, day=1, start=1, preferred_building="A")
    waste = ok(solve(make_input(rooms, (ev,), weights={"building_preference": 1, "min_capacity_waste": 100})))
    assert room_of(waste, 1) == 2
    bld = ok(solve(make_input(rooms, (ev,), weights={"building_preference": 100, "min_capacity_waste": 1})))
    assert room_of(bld, 1) == 1
    hard = Constraint("building_preference", {"event_ids": [1], "building": "A"}, hard=True, id=9)
    assert room_of(ok(solve(make_input(rooms, (ev,), (hard,), weights={"min_capacity_waste": 100}))), 1) == 1
    infeasible(
        solve(make_input((room(1, "A101", 58), room(2, "C201", 126)), (event(1, size=100, day=1, start=1),), (hard,))),
        "building_preference",
        1,
    )


def test_room_preference_rank() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58), room(3, "A204", 156))
    ev = event(1, size=30, day=1, start=1, preferred_room_ids=(3, 2, 1))
    pref = ok(solve(make_input(rooms, (ev,), weights={"room_preference": 100, "min_capacity_waste": 1})))
    assert room_of(pref, 1) == 3
    waste = ok(solve(make_input(rooms, (ev,), weights={"room_preference": 1, "min_capacity_waste": 100})))
    assert room_of(waste, 1) in (1, 2)
    assert waste.objective_breakdown["room_preference"] in (1, 2)
    # busy first choice falls through to the second
    other = event(2, size=30, day=1, start=1, required_room_ids={3})
    second = ok(solve(make_input(rooms, (ev, other), weights={"room_preference": 100, "min_capacity_waste": 1})))
    assert room_of(second, 1) == 2


def test_min_capacity_waste() -> None:
    rooms = (room(1, "A101", 58), room(2, "A204", 156))
    ev = event(1, size=20, day=1, start=1, preferred_room_ids=(2,))
    waste = ok(solve(make_input(rooms, (ev,), weights={"room_preference": 1, "min_capacity_waste": 100})))
    assert room_of(waste, 1) == 1
    assert waste.objective_breakdown["min_capacity_waste"] == 300  # (58-20)//10 = 3 units × 100
    pref = ok(solve(make_input(rooms, (ev,), weights={"room_preference": 100, "min_capacity_waste": 1})))
    assert room_of(pref, 1) == 2


def test_same_room_group_and_across_weeks() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    a = event(
        1, label="OPT 126", day=1, start=1, weeks=tuple(range(1, 8)), preferred_room_ids=(1,), same_room_group="opt"
    )
    b = event(
        2, label="OPT 126", day=1, start=1, weeks=tuple(range(8, 15)), preferred_room_ids=(2,), same_room_group="opt"
    )
    apart = ok(
        solve(
            make_input(
                rooms, (a, b), weights={"same_room_group": 1, "same_room_across_weeks": 1, "room_preference": 100}
            )
        )
    )
    assert room_of(apart, 1) == 1 and room_of(apart, 2) == 2
    assert (
        apart.objective_breakdown["same_room_group"] == 1 and apart.objective_breakdown["same_room_across_weeks"] == 1
    )
    together = ok(
        solve(
            make_input(
                rooms, (a, b), weights={"same_room_group": 100, "same_room_across_weeks": 100, "room_preference": 1}
            )
        )
    )
    assert room_of(together, 1) == room_of(together, 2)
    hard = ok(
        solve(
            make_input(
                rooms, (a, b), (Constraint("same_room_group", {}, hard=True),), weights={"room_preference": 1000}
            )
        )
    )
    assert room_of(hard, 1) == room_of(hard, 2)
    # hard group with overlapping weeks and one room each -> impossible
    c = replace(b, weeks=frozenset(range(1, 15)))
    infeasible(
        solve(make_input(rooms, (a, c), (Constraint("same_room_group", {}, hard=True),))), "same_room_group", 1, 2
    )


# ----------------------------------------------------------------------------- exams


def test_exam_gap() -> None:
    rooms = (room(1, "A101", 58, exam_capacity=30), room(2, "A106", 58, exam_capacity=30))
    exams = tuple(
        event(
            i,
            size=25,
            duration=2,
            kind="exam",
            weeks=(15,),
            allowed_days=(1,),
            earliest=1,
            latest=6,
            cohort_keys={"PROG:X:Y1"},
        )
        for i in (1, 2)
    )
    gap = Constraint("exam_gap", {"cohort": "PROG:X:Y1", "min_periods": 2}, hard=True)
    res = ok(solve(make_input(rooms, exams, (gap,), weeks=(15,))))
    t1, t2 = assigned(res.assignments, 1), assigned(res.assignments, 2)
    assert max(t2.start - t1.end - 1, t1.start - t2.end - 1) >= 2
    tight = tuple(replace(e, latest_end=5) for e in exams)
    infeasible(solve(make_input(rooms, tight, (gap,), weeks=(15,))), "exam_gap", 1, 2)
    # soft: window pull vs gap
    soft_gap = Constraint("exam_gap", {"cohort": "PROG:X:Y1", "min_periods": 2}, hard=False)
    early = Constraint("day_window", {"cohort": "PROG:X:Y1", "latest": 4}, hard=False)
    want_gap = ok(
        solve(make_input(rooms, exams, (soft_gap, early), weeks=(15,), weights={"exam_gap": 100, "day_window": 1}))
    )
    a1, a2 = assigned(want_gap.assignments, 1), assigned(want_gap.assignments, 2)
    assert max(a2.start - a1.end - 1, a1.start - a2.end - 1) >= 2
    want_early = ok(
        solve(make_input(rooms, exams, (soft_gap, early), weeks=(15,), weights={"exam_gap": 1, "day_window": 100}))
    )
    assert all(assigned(want_early.assignments, i).end <= 4 for i in (1, 2))
    assert want_early.objective_breakdown["exam_gap"] == 1


def test_max_exams_per_day() -> None:
    rooms = tuple(room(i, f"A10{i}", 58, exam_capacity=30) for i in (1, 2, 3))
    exams = tuple(
        event(
            i,
            size=25,
            duration=2,
            kind="exam",
            weeks=(15,),
            allowed_days=(1, 2),
            earliest=1,
            latest=8,
            cohort_keys={"C"},
        )
        for i in (1, 2, 3)
    )
    limit = Constraint("max_exams_per_day", {"cohort": "C", "n": 2}, hard=True)
    res = ok(solve(make_input(rooms, exams, (limit,), weeks=(15,))))
    days = [assigned(res.assignments, i).day for i in (1, 2, 3)]
    assert max(days.count(d) for d in (1, 2)) <= 2
    one_day = tuple(replace(e, allowed_days=frozenset({1})) for e in exams)
    infeasible(solve(make_input(rooms, one_day, (limit,), weeks=(15,))), "max_exams_per_day", 1, 2, 3)
    soft_limit = Constraint("max_exams_per_day", {"cohort": "C", "n": 2}, hard=False)
    avoid_tue = Constraint(
        "day_window", {"cohort": "C", "days": [2], "periods": [99]}, hard=False
    )  # every Tuesday period is "outside"
    spread = ok(
        solve(
            make_input(
                rooms, exams, (soft_limit, avoid_tue), weeks=(15,), weights={"max_exams_per_day": 100, "day_window": 1}
            )
        )
    )
    assert sorted(assigned(spread.assignments, i).day for i in (1, 2, 3)) == [1, 1, 2]
    monday = ok(
        solve(
            make_input(
                rooms, exams, (soft_limit, avoid_tue), weeks=(15,), weights={"max_exams_per_day": 1, "day_window": 100}
            )
        )
    )
    assert [assigned(monday.assignments, i).day for i in (1, 2, 3)] == [1, 1, 1]
    assert monday.objective_breakdown["max_exams_per_day"] == 1


# ----------------------------------------------------------------------------- stability / closed / window / evening


def test_stability() -> None:
    rooms = (room(1, "A101", 58), room(2, "A204", 156))
    ev = event(1, size=20, day=1, start=1)
    prev = (Assignment(1, 1, 1, 2, (2,), frozenset(ALL)),)
    keep = ok(solve(make_input(rooms, (ev,), previous=prev, weights={"stability_room": 100, "min_capacity_waste": 1})))
    assert room_of(keep, 1) == 2 and keep.objective_breakdown.get("stability_room", 0) == 0
    move = ok(solve(make_input(rooms, (ev,), previous=prev, weights={"stability_room": 1, "min_capacity_waste": 100})))
    assert room_of(move, 1) == 1 and move.objective_breakdown["stability_room"] == 1
    flex = event(2, size=20, allowed_days=(1, 2), duration=2, earliest=1, latest=4)
    prev2 = (Assignment(2, 2, 3, 4, (1,), frozenset(ALL)),)
    res = ok(solve(make_input(rooms, (flex,), previous=prev2)))
    assert assigned(res.assignments, 2) == prev2[0]
    pinned = Constraint("stability", {"event_ids": [1]}, hard=True)
    assert (
        room_of(ok(solve(make_input(rooms, (ev,), (pinned,), previous=prev, weights={"min_capacity_waste": 1000}))), 1)
        == 2
    )


def test_room_closed_and_blocks() -> None:
    rooms = (room(1, "A101", 58), room(2, "A106", 58))
    ev = event(1, day=1, start=2, duration=2, preferred_room_ids=(1,))
    closed = Constraint("room_closed", {"room": "A101", "day": 1, "periods": [1, 2, 3], "label": "HAZIRLIK"}, hard=True)
    assert room_of(ok(solve(make_input(rooms, (ev,), (closed,)))), 1) == 2
    assert room_of(ok(solve(make_input(rooms, (ev,), blocks=(Block(1, None, 1, 1, 3),)))), 1) == 2
    assert (
        room_of(ok(solve(make_input(rooms, (ev,), blocks=(Block(1, 15, 1, 1, 3),)))), 1) == 1
    )  # week outside the event
    infeasible(solve(make_input(rooms[:1], (ev,), (closed,))), "room_closed", 1)
    infeasible(solve(make_input(rooms[:1], (ev,), blocks=(Block(1, 3, 1, 1, 3),))), "no_room_overlap", 1)
    soft = Constraint("room_closed", {"room": "A101", "day": 1, "periods": [1, 2, 3]}, hard=False)
    assert (
        room_of(ok(solve(make_input(rooms, (ev,), (soft,), weights={"room_closed": 1, "room_preference": 100}))), 1)
        == 1
    )
    assert (
        room_of(ok(solve(make_input(rooms, (ev,), (soft,), weights={"room_closed": 100, "room_preference": 1}))), 1)
        == 2
    )


def test_day_window() -> None:
    rooms = (room(1, "A101", 58),)
    ev = event(
        1,
        allowed_days=(1,),
        duration=2,
        earliest=1,
        latest=18,
        cohort_keys={"PROG:Hemşirelik:Y1"},
        preferred_room_ids=(),
    )
    window = Constraint("day_window", {"program": "Hemşirelik", "latest": 11}, hard=True)
    late = Constraint("fixed_time", {"event_ids": [1], "start": 13}, hard=False)
    res = ok(solve(make_input(rooms, (ev,), (window, late))))
    assert assigned(res.assignments, 1).end <= 11
    fixed_late = event(2, day=1, start=13, duration=2, cohort_keys={"PROG:Hemşirelik:Y1"})
    infeasible(solve(make_input(rooms, (fixed_late,), (window,))), "day_window", 2)
    soft_window = replace(window, hard=False)
    stay_late = ok(solve(make_input(rooms, (ev,), (soft_window, late), weights={"day_window": 1, "fixed_time": 100})))
    assert assigned(stay_late.assignments, 1).start == 13
    go_early = ok(solve(make_input(rooms, (ev,), (soft_window, late), weights={"day_window": 100, "fixed_time": 1})))
    assert assigned(go_early.assignments, 1).end <= 11


def test_evening_programs_in_buildings() -> None:
    rooms = (room(1, "A101", 58), room(2, "C305", 32))
    ev = event(1, size=30, day=1, start=14, duration=2, cohort_keys={"PROG:Psikoloji İÖ:Y1"}, preferred_room_ids=(1,))
    hard = Constraint("evening_programs_in_buildings", {"buildings": ["B", "C"]}, hard=True)
    assert room_of(ok(solve(make_input(rooms, (ev,), (hard,)))), 1) == 2
    big = replace(ev, size=50)
    infeasible(solve(make_input(rooms, (big,), (hard,))), "evening_programs_in_buildings", 1)
    soft = replace(hard, hard=False)
    assert (
        room_of(
            ok(
                solve(
                    make_input(
                        rooms, (ev,), (soft,), weights={"evening_programs_in_buildings": 1, "room_preference": 100}
                    )
                )
            ),
            1,
        )
        == 1
    )
    assert (
        room_of(
            ok(
                solve(
                    make_input(
                        rooms, (ev,), (soft,), weights={"evening_programs_in_buildings": 100, "room_preference": 1}
                    )
                )
            ),
            1,
        )
        == 2
    )
    # a day programme is not affected
    day = replace(ev, cohort_keys=frozenset({"PROG:Psikoloji:Y1"}))
    assert room_of(ok(solve(make_input(rooms, (day,), (hard,)))), 1) == 1


@pytest.mark.parametrize("kind", ["no_room_overlap", "no_cohort_overlap", "no_instructor_overlap"])
def test_overlap_kinds_cannot_be_softened(kind: str) -> None:
    rooms = (room(1, "A101", 58),)
    res = solve(make_input(rooms, (event(1, day=1, start=1),), (Constraint(kind, {}, hard=False, id=3),)))
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert any(kind in w and "cannot be soft" in w for w in res.stats["warnings"])
