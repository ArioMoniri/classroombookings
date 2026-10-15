"""``Event.share_room``: small exams invigilated together in one room (seat budget instead of
exclusive occupancy)."""

from __future__ import annotations

from dataclasses import replace

from app.solver.cpsat import solve
from app.solver.model import Assignment
from app.solver.repair import validate
from tests.solver.conftest import assigned, event, make_input, room

W = (15,)


def _exam(i: int, size: int, **kw: object):  # type: ignore[no-untyped-def]
    return event(i, size=size, duration=2, kind="exam", weeks=W, day=1, start=1, share_room=True, **kw)


def test_sharing_exams_fit_in_one_room() -> None:
    rooms = (room(1, "A101", 58, exam_capacity=30),)
    exams = (_exam(1, 12), _exam(2, 10), _exam(3, 8))  # 30 seats exactly
    inp = make_input(rooms, exams, weeks=W)
    res = solve(inp)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.diagnoses
    assert res.hard_score == 100
    assert all(assigned(res.assignments, i).room_ids == (1,) for i in (1, 2, 3))
    assert not [v for v in validate(inp, res.assignments) if v.hard]


def test_seat_budget_exceeded_is_infeasible_with_diagnosis() -> None:
    rooms = (room(1, "A101", 58, exam_capacity=30),)
    exams = (_exam(1, 12), _exam(2, 10), _exam(3, 9))  # 31 > 30
    res = solve(make_input(rooms, exams, weeks=W))
    assert res.status == "INFEASIBLE"
    named = {e for d in res.diagnoses for e in d.event_ids}
    assert named & {1, 2, 3}
    assert any("no_room_overlap" in d.constraint_kinds for d in res.diagnoses)
    text = " ".join(d.message for d in res.diagnoses)
    assert "shared seats" in text or "busy" in text
    # validate() flags the overfull room on a manual edit as well
    bad = [Assignment(i, 1, 1, 2, (1,), frozenset(W)) for i in (1, 2, 3)]
    kinds = {v.kind for v in validate(make_input(rooms, exams, weeks=W), bad) if v.hard}
    assert "no_room_overlap" in kinds
    # a second room makes it feasible again
    res2 = solve(make_input(rooms + (room(2, "A106", 58, exam_capacity=30),), exams, weeks=W))
    assert res2.status in ("OPTIMAL", "FEASIBLE") and res2.hard_score == 100


def test_non_sharing_event_keeps_the_room_exclusive() -> None:
    rooms = (room(1, "A101", 58, exam_capacity=30),)
    sharing = _exam(1, 10)
    exclusive = replace(_exam(2, 10), share_room=False)
    res = solve(make_input(rooms, (sharing, exclusive), weeks=W))
    assert res.status == "INFEASIBLE"
    assert any("no_room_overlap" in d.constraint_kinds for d in res.diagnoses)
    # and with two rooms they are separated
    res2 = solve(make_input(rooms + (room(2, "A106", 58, exam_capacity=30),), (sharing, exclusive), weeks=W))
    assert res2.status in ("OPTIMAL", "FEASIBLE")
    assert assigned(res2.assignments, 1).room_ids != assigned(res2.assignments, 2).room_ids
    manual = [Assignment(1, 1, 1, 2, (1,), frozenset(W)), Assignment(2, 1, 1, 2, (1,), frozenset(W))]
    assert "no_room_overlap" in {
        v.kind for v in validate(make_input(rooms, (sharing, exclusive), weeks=W), manual) if v.hard
    }


def test_locked_sharing_exams_like_the_final_plan() -> None:
    """The planner's definitive rooms: three locked exams in A101 at the same time."""
    rooms = (room(1, "A101", 58, exam_capacity=30), room(2, "A106", 58, exam_capacity=30))
    exams = tuple(
        replace(_exam(i, s), locked=Assignment(i, 1, 1, 2, (1,), frozenset(W)), fixed_day=None, fixed_start=None)
        for i, s in ((1, 12), (2, 10), (3, 8))
    )
    res = solve(make_input(rooms, exams, weeks=W))
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.diagnoses
    assert res.hard_score == 100
    too_many = exams + (replace(_exam(4, 5), locked=Assignment(4, 1, 1, 2, (1,), frozenset(W))),)
    res2 = solve(make_input(rooms, too_many, weeks=W))
    assert res2.status == "INFEASIBLE"
    assert {1, 2, 3, 4} & {e for d in res2.diagnoses for e in d.event_ids}


def test_sharing_across_disjoint_weeks_and_courses() -> None:
    rooms = (room(1, "A101", 58, exam_capacity=30),)
    a = replace(_exam(1, 25), weeks=frozenset({15}))
    b = replace(_exam(2, 25), weeks=frozenset({16}))  # different week: no budget conflict
    res = solve(make_input(rooms, (a, b), weeks=(15, 16)))
    assert res.status in ("OPTIMAL", "FEASIBLE") and res.hard_score == 100
    # course events use the lecture capacity when sharing
    c1 = event(1, size=30, duration=2, day=1, start=1, share_room=True)
    c2 = event(2, size=28, duration=2, day=1, start=1, share_room=True)
    res2 = solve(make_input(rooms, (c1, c2)))
    assert res2.status in ("OPTIMAL", "FEASIBLE") and res2.hard_score == 100
    res3 = solve(make_input(rooms, (c1, replace(c2, size=29))))
    assert res3.status == "INFEASIBLE"


def test_inconsistent_seat_hint_is_repaired() -> None:
    """Roadmap Phase 9 (unlocked exam runs): the hint values ``seats[e, r]`` by a proportional split (80 over
    A + B = 40 / 40), which overfills A next to a 30-student exam (exam capacity 60); the repair solves the
    seats alone with the hinted placement fixed (A 30 / B 50), so the warm start is a real first solution."""
    from app.solver.build import build_model, make_solver, prepare
    from app.solver.model import Assignment
    from ortools.sat.python import cp_model

    rooms = (room(1, "A", 120, exam_capacity=60), room(2, "B", 120, exam_capacity=60))
    split = event(1, size=80, kind="exam", weeks=(3,), day=1, start=1, max_rooms=2, share_room=True)
    single = event(2, size=30, kind="exam", weeks=(3,), day=1, start=1, share_room=True)
    inp = make_input(rooms, (split, single), weeks=(3,), workers=1)
    wk = frozenset({3})
    hint = [Assignment(1, 1, 1, 2, (1, 2), wk), Assignment(2, 1, 1, 2, (1,), wk)]

    def fixed_status(ctx) -> int:  # type: ignore[no-untyped-def]
        s = make_solver(inp, 5.0)
        s.parameters.fix_variables_to_their_hinted_value = True
        return s.Solve(ctx.model)  # type: ignore[no-any-return]

    ctx = build_model(prepare(inp), "solve")
    ctx.add_hints(hint)
    assert fixed_status(ctx) == cp_model.INFEASIBLE  # the proportional seat hint is not a solution
    ctx = build_model(prepare(inp), "solve")
    ctx.add_hints(hint)
    assert ctx.repair_derived_hints(5.0) > 0
    assert fixed_status(ctx) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert ctx.repair_derived_hints(5.0) == 0  # consistent now
