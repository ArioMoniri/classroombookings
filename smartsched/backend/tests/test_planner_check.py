"""Planner-level validator (``app.services.planner_check``): every rule has a clean case, a violation, an
accepted exception that the run reports, and the same exception unreported (which counts as a violation)."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.planner_check import BlockInfo, CheckData, Req, RoomInfo, Row, check


def _req(i: int, *, day: int | None = 1, start: int = 1, end: int = 2, size: int | None = 30, **kw: Any) -> Req:
    fields: dict[str, Any] = dict(
        id=i,
        label=f"C{i}",
        day=day,
        days=frozenset({day} if day else {1, 2, 3, 4, 5}),
        start=start,
        end=end,
        date=None,
        weeks=frozenset({3}),
        size=size,
        locked=False,
        definitive=frozenset(),
        tags=frozenset(),
        cohort=frozenset(),
        instructors=frozenset(),
    )
    fields.update(kw)
    return Req(**fields)


def _row(i: int, req: int, rooms: tuple[int, ...], *, day: int = 1, start: int = 1, end: int = 2, **kw: Any) -> Row:
    fields: dict[str, Any] = dict(
        id=i,
        req=req,
        day=day,
        start=start,
        end=end,
        date=None,
        weeks=frozenset({3}),
        rooms=rooms,
        origin="SOLVER",
        is_locked=False,
    )
    fields.update(kw)
    return Row(**fields)


ROOMS = {
    1: RoomInfo(1, "A101", 58, frozenset(), True),
    2: RoomInfo(2, "A204", 156, frozenset(), True),
    3: RoomInfo(3, "A103", 47, frozenset({"PC"}), True),
    4: RoomInfo(4, "M101", 80, frozenset({"TIP"}), True),
    9: RoomInfo(9, "LAB1", 0, frozenset(), False),  # outside the pool
}


def _data(reqs: list[Req], rows: list[Row], diags: list[dict[str, Any]] | None = None, **kw: Any) -> CheckData:
    fields: dict[str, Any] = dict(
        run_id=1,
        exam=False,
        reqs={r.id: r for r in reqs},
        rows=rows,
        rooms=ROOMS,
        blocks=[],
        members={},
        diagnoses=diags or [],
    )
    fields.update(kw)
    return CheckData(**fields)


def _diag(code: str, ids: list[int], severity: str = "warning") -> dict[str, Any]:
    return {"code": code, "event_ids": ids, "severity": severity}


def test_clean_run_has_no_findings_and_scores_100() -> None:
    res = check(_data([_req(1), _req(2)], [_row(1, 1, (1,)), _row(2, 2, (2,))]))
    assert res.findings == [] and res.hard_score == 100 and res.strict_score == 100 and res.placed_pct == 100.0


def test_double_booking_in_the_pool_is_a_violation_outside_the_pool_an_exception() -> None:
    res = check(_data([_req(1), _req(2)], [_row(1, 1, (1,)), _row(2, 2, (1,))]))
    assert [f.rule for f in res.violations] == ["room_double_booking"] and res.hard_score < 100
    outside = _data([_req(1), _req(2)], [_row(1, 1, (9,)), _row(2, 2, (9,))])
    unreported = check(outside)
    assert [f.cause for f in unreported.violations] == ["outside_pool"]  # an exception nobody reported
    reported = check(_data(outside.reqs.values().__iter__().__class__ and [_req(1), _req(2)], outside.rows,
                           [_diag("outside_pool_overlap", [1, 2])]))
    assert reported.violations == [] and reported.exceptions_by_cause() == {"outside_pool": 1}
    assert reported.hard_score == 100 and reported.strict_score < 100


def test_capacity_violation_and_trusted_planner_room() -> None:
    small = [_req(1, size=70)]
    assert [f.rule for f in check(_data(small, [_row(1, 1, (1,))])).violations] == ["capacity"]
    locked = [_req(1, size=70, locked=True, definitive=frozenset({1}))]
    unreported = check(_data(locked, [_row(1, 1, (1,))]))
    assert [(f.rule, f.cause) for f in unreported.violations] == [("capacity", "D1")]
    ok = check(_data(locked, [_row(1, 1, (1,))], [_diag("trusted_lock_capacity", [1])]))
    assert ok.violations == [] and ok.exceptions_by_cause() == {"D1": 1}
    # trust off: the planner's room is no excuse
    strict = check(_data(locked, [_row(1, 1, (1,))], [_diag("trusted_lock_capacity", [1])], trust=False))
    assert [f.cause for f in strict.violations] == [None]
    # a lock moved by a tool into another small room is never trusted (review B2)
    moved = check(_data(locked, [_row(1, 1, (3,))], [_diag("trusted_lock_capacity", [1])]))
    assert {f.rule for f in moved.violations} >= {"capacity"}


def test_joint_lecture_members_are_summed_and_clipping_is_not_hidden() -> None:
    """Two programme rows of one lecture in A 101 (58): 40 + 40 students do not fit (review B1)."""
    reqs = [_req(1, size=40), _req(2, size=40)]
    rows = [_row(1, 1, (1,)), _row(2, 2, (1,))]
    res = check(_data(reqs, rows, members={1: [1, 2]}))
    assert [f.rule for f in res.violations] == ["capacity"] and "80 students" in res.violations[0].message
    locked = [_req(i, size=40, locked=True, definitive=frozenset({1})) for i in (1, 2)]
    ok = check(_data(locked, rows, [_diag("trusted_lock_capacity", [1])], members={1: [1, 2]}))
    assert ok.violations == [] and ok.exceptions_by_cause() == {"D1": 1}


def test_time_weeks_and_locked_room() -> None:
    reqs = [_req(1, locked=True, definitive=frozenset({1}))]
    moved = check(_data(reqs, [_row(1, 1, (1,), start=3, end=4)]))
    assert [f.rule for f in moved.violations] == ["time"]
    manual = check(_data(reqs, [_row(1, 1, (1,), start=3, end=4, origin="MANUAL")]))
    assert manual.violations == [] and manual.exceptions_by_cause() == {"manual": 1}
    wrong_room = check(_data(reqs, [_row(1, 1, (2,))]))
    assert [(f.rule, f.cause) for f in wrong_room.violations] == [("locked_room", "week_split")]
    split = check(_data(reqs, [_row(1, 1, (2,))], [_diag("week_split", [1])]))
    assert split.violations == []
    weeks = check(_data([_req(1)], [_row(1, 1, (1,), weeks=frozenset({3, 4}))]))
    assert [f.rule for f in weeks.violations] == ["weeks"]
    prefer = check(_data(reqs, [_row(1, 1, (2,))], lock_mode=False))  # definitive rooms are only hints
    assert prefer.violations == []


def test_blocks_and_tags() -> None:
    blocked = _data([_req(1)], [_row(1, 1, (1,))])
    blocked.blocks = [BlockInfo(1, None, 1, 2, 3, "ETKİNLİK")]
    assert [f.rule for f in check(blocked).violations] == ["blocked"]
    blocked.blocks = [BlockInfo(1, 4, 1, 2, 3, "week 4 only")]
    assert check(blocked).violations == []
    pc = [_req(1, tags=frozenset({"PC"}))]
    assert [f.rule for f in check(_data(pc, [_row(1, 1, (1,))])).violations] == ["tags"]
    assert check(_data(pc, [_row(1, 1, (3,))])).violations == []
    tip = check(_data([_req(1)], [_row(1, 1, (4,))]))
    assert [f.rule for f in tip.violations] == ["tags"]
    planner_tip = [_req(1, locked=True, definitive=frozenset({4}))]
    assert check(_data(planner_tip, [_row(1, 1, (4,))])).violations == []


def test_cohort_and_instructor_clashes_d2() -> None:
    reqs = [_req(1, cohort=frozenset({"psi:Y1"})), _req(2, cohort=frozenset({"psi:Y1"}))]
    rows = [_row(1, 1, (1,)), _row(2, 2, (2,))]
    unreported = check(_data(reqs, rows))
    assert [(f.rule, f.cause) for f in unreported.violations] == [("cohort", "D2")]
    ok = check(_data(reqs, rows, [_diag("input_conflict", [1, 2])]))
    assert ok.violations == [] and ok.exceptions_by_cause() == {"D2": 1}
    no_waiver = check(_data(reqs, rows, [_diag("input_conflict", [1, 2])], fixed_waiver=False))
    assert [f.cause for f in no_waiver.violations] == [None]
    # a flexible request placed on top of a fixed one is never waived
    flex = [_req(1, instructors=frozenset({"7"})), _req(2, day=None, instructors=frozenset({"7"}))]
    res = check(_data(flex, rows, [_diag("input_conflict", [1, 2])]))
    assert [(f.rule, f.cause) for f in res.violations] == [("instructor", None)]


def test_unplaced_requests_must_be_named_by_an_error() -> None:
    reqs = [_req(1), _req(2)]
    res = check(_data(reqs, [_row(1, 1, (1,))]))
    assert [(f.rule, f.cause, f.reported) for f in res.violations] == [("unplaced", "D3", False)]
    ok = check(_data(reqs, [_row(1, 1, (1,))], [_diag("unplaced", [2], "error")]))
    assert ok.violations == [] and ok.requests_placed == 1 and ok.placed_pct == 50.0
    assert ok.hard_score == 100  # the hard score is that of the placed requests
    # a joint lecture named by its head covers every member
    members = check(_data(reqs, [], [_diag("unplaced", [1], "error")], members={1: [1, 2]}))
    assert members.violations == []


def test_missing_enrolment_needs_a_reported_fallback_and_is_checked_with_it() -> None:
    reqs = [_req(1, size=None)]
    res = check(_data(reqs, [_row(1, 1, (1,))]))
    assert [f.rule for f in res.violations] == ["missing_enrolment"]
    ok = check(_data(reqs, [_row(1, 1, (1,))], [_diag("missing_enrolment", [1])], fallbacks={1: 40}))
    assert ok.violations == [] and ok.exceptions_by_cause() == {"missing_enrolment": 1}
    too_big = check(_data(reqs, [_row(1, 1, (1,))], [_diag("missing_enrolment", [1])], fallbacks={1: 90}))
    assert [f.rule for f in too_big.violations] == ["capacity"]


def test_shared_exam_rooms_use_one_seat_flow() -> None:
    """Exams share rooms when the students fit: 40 + 30 in A 204 (78 exam seats) fit; a split exam over
    A 101 + A 204 with a single-room exam next to it fits only through the flow."""
    rooms = {1: RoomInfo(1, "A101", 29, frozenset(), True), 2: RoomInfo(2, "A204", 78, frozenset(), True)}
    d = date(2026, 6, 1)

    def ex(i: int, size: int, **kw: Any) -> Req:
        return _req(i, size=size, date=d, weeks=frozenset({15}), **kw)

    def row(i: int, rs: tuple[int, ...]) -> Row:
        return _row(i, i, rs, date=d, weeks=frozenset({15}))

    ok = check(_data([ex(1, 40), ex(2, 30)], [row(1, (2,)), row(2, (2,))], exam=True, rooms=rooms))
    assert ok.violations == []
    over = check(_data([ex(1, 60), ex(2, 30)], [row(1, (2,)), row(2, (2,))], exam=True, rooms=rooms))
    assert [f.rule for f in over.violations] == ["capacity"]
    # split exam (70 over A101 + A204) + a 30-student exam in A204: 29 + 49 + 30 = 107 = seats, feasible
    flow = check(_data([ex(1, 70), ex(2, 30)], [row(1, (1, 2)), row(2, (2,))], exam=True, rooms=rooms))
    assert flow.violations == []
    flow_over = check(_data([ex(1, 80), ex(2, 30)], [row(1, (1, 2)), row(2, (2,))], exam=True, rooms=rooms))
    assert [f.rule for f in flow_over.violations] == ["capacity"]
