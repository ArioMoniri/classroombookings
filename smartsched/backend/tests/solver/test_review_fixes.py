"""Strict solver review (docs/review/2026-10-08-solver-review.md), solver side: untrusted tool-made locks
(B2), room-set explanations (B2), honest partial summaries and every unplaced event explained (M3),
deterministic canonical stages (M2), the relaxation's week accounting (orchestrator R3), size-0 exams (R2),
one seat split per exam (MINOR), core minimality (MINOR), the residual week-split round (M5), the waste
exclusion of fallback sizes (M1).  Each rule: a feasible case, an infeasible case with a named diagnosis,
and a soft-weight case where it applies."""

from __future__ import annotations

from dataclasses import replace

from app.solver.build import prepare
from app.solver.cpsat import _timeout_partial, solve
from app.solver.diagnose import (
    accepted_exceptions,
    core_diagnosis,
    explain_event,
    explain_unplaced,
    partial_message,
)
from app.solver.model import Assignment, Constraint
from app.solver.options import classify
from app.solver.repair import validate
from app.solver.weeksplit import residual_gain, residual_split, split_blocked_weeks
from tests.solver.conftest import assigned, event, make_input, room

W1 = (3,)
OK = ("OPTIMAL", "FEASIBLE")


def _lock(eid: int, rooms: tuple[int, ...], day: int = 1, start: int = 1, dur: int = 2, weeks=W1) -> Assignment:  # type: ignore[no-untyped-def]
    return Assignment(eid, day, start, start + dur - 1, rooms, frozenset(weeks))


# --------------------------------------------------------------------------- B2: untrusted locks


def test_untrusted_lock_must_fit_feasible_infeasible_and_soft() -> None:
    rooms = (room(1, "A107", 58), room(2, "A204", 156))
    # feasible: a tool-made lock that fits is kept
    fits = event(1, size=50, weeks=W1, day=1, start=1, locked=_lock(1, (1,)), lock_trusted=False)
    res = solve(make_input(rooms, (fits,), weeks=W1, trust_locked_rooms=True))
    assert res.status in OK and assigned(res.assignments, 1).room_ids == (1,)
    # infeasible: 135 students locked into 58 seats by the fix button is not "the planner's room"
    big = replace(fits, size=135)
    res = solve(make_input(rooms, (big,), weeks=W1, trust_locked_rooms=True))
    assert res.status == "INFEASIBLE" and res.assignments == []
    d = next(d for d in res.diagnoses if d.code == "locked_ineligible")
    assert d.event_ids == [1] and "capacity 58 < 135" in d.message
    assert not any(d.code == "trusted_lock_capacity" for d in res.diagnoses)  # no false "planner's room kept"
    # the planner's own lock (trusted) is kept with the warning
    trusted = replace(big, lock_trusted=True)
    res = solve(make_input(rooms, (trusted,), weeks=W1, trust_locked_rooms=True))
    assert res.status in OK and any(d.code == "trusted_lock_capacity" for d in res.diagnoses)
    # soft weight: soft capacity penalises the untrusted lock, the weight scales it, the trusted one is free
    soft = (Constraint("capacity", {}, hard=False, weight=2),)
    pen = solve(make_input(rooms, (big,), soft, weeks=W1, trust_locked_rooms=True, weights={"capacity": 1}))
    assert pen.status in OK and pen.objective_breakdown.get("capacity") == (135 - 58) * 2
    free = solve(make_input(rooms, (trusted,), soft, weeks=W1, trust_locked_rooms=True, weights={"capacity": 1}))
    assert free.objective_breakdown.get("capacity", 0) == 0


def test_explanations_offer_room_sets_that_seat_the_event() -> None:
    """ING 302 (135 students, may use 2 rooms) is unplaced: the free option is a *set* with >= 135 seats,
    never "use A107" (58) on its own; releasing a busy small room alone is not suggested."""
    rooms = (room(1, "A107", 58), room(2, "A101", 100), room(3, "A106", 60), room(4, "A108", 40))
    ing = event(1, size=135, weeks=W1, day=1, start=1, max_rooms=2, label="ING 302")
    other = event(2, size=50, weeks=W1, day=1, start=1)
    prep = prepare(make_input(rooms, (ing, other), weeks=W1))
    d = explain_event(prep, 1, {2: Assignment(2, 1, 1, 2, (2,), frozenset(W1))})
    uses = [s for s in d.suggestions if s.startswith("use ")]
    assert uses == []  # A107 + A106 + A108 cannot seat 135 within 2 rooms while A101 is busy
    assert not [s for s in d.suggestions if s.startswith("release A107") or s.startswith("release A106")]
    assert any(s.startswith("release A101") for s in d.suggestions)  # A101 + A106 = 160 would fit
    free = explain_event(prep, 1, {})
    use = next(s for s in free.suggestions if s.startswith("use "))
    assert use == "use A101+A106 at day 1 P1-P2"
    opt = classify(0, use, free.message, [1])
    assert opt["action"] == "move" and opt["room_codes"] == ["A101", "A106"]
    assert free.params["free"][0]["seats"] >= 135


def test_alternative_periods_respect_max_rooms_and_seats() -> None:
    rooms = (room(1, "A107", 58), room(2, "A101", 100))
    ing = event(1, size=135, weeks=W1, day=1, start=1, max_rooms=2)
    blocker = event(2, size=50, weeks=W1, day=1, start=1)
    prep = prepare(make_input(rooms, (ing, blocker), weeks=W1))
    d = explain_event(prep, 1, {2: Assignment(2, 1, 1, 2, (2,), frozenset(W1))})
    alt = next(s for s in d.suggestions if s.startswith("alternative periods"))
    assert "A101+A107" in alt and "in A107," not in alt


# --------------------------------------------------------------------------- M3: honest partial runs


def test_every_unplaced_event_is_explained_beyond_fifty() -> None:
    rooms = (room(1, "A101", 58),)
    events = tuple(event(i, size=30, weeks=W1, day=1, start=1) for i in range(1, 62))
    prep = prepare(make_input(rooms, events, weeks=W1))
    placed = {1: Assignment(1, 1, 1, 2, (1,), frozenset(W1))}
    diags = explain_unplaced(prep, placed)
    assert {i for d in diags if d.code == "unplaced" for i in d.event_ids} == set(range(2, 62))


def test_partial_summary_lists_the_accepted_exceptions() -> None:
    rooms = (room(1, "A207", 120), room(2, "A101", 58))
    acu = event(1, size=122, weeks=W1, day=1, start=1, locked=_lock(1, (1,)), label="ACU 132")
    a = event(2, size=30, weeks=W1, day=2, start=1, instructor_keys={"INS:1"})
    b = event(3, size=30, weeks=W1, day=2, start=1, instructor_keys={"INS:1"})
    c = event(4, size=30, weeks=W1, day=3, start=1, required_tags={"PC"})  # no PC room: unplaced
    res = solve(
        make_input(
            rooms, (acu, a, b, c), weeks=W1, trust_locked_rooms=True, fixed_conflicts_as_warnings=True, best_effort=True
        )
    )
    summary = res.diagnoses[0]
    assert summary.code == "partial" and summary.params["exceptions"] == {"D1": 1, "D2": 1, "D3": 1}
    assert "except 2 accepted exception(s)" in summary.message and "keeps every hard rule" in summary.message
    assert accepted_exceptions([]) == {} and "every placed event keeps every hard rule" in partial_message(3, 4, {})


def test_timeout_with_best_effort_returns_the_checked_warm_start() -> None:
    rooms = (room(1, "A101", 58),)
    e1 = event(1, weeks=W1, day=1, start=1)
    e2 = event(2, weeks=W1, day=1, start=1)
    inp = make_input(rooms, (e1, e2), weeks=W1, best_effort=True)
    prep = prepare(inp)
    stats: dict[str, object] = {}
    res = _timeout_partial(inp, prep, [], stats, 0.0, {1: Assignment(1, 1, 1, 2, (1,), frozenset(W1))}, "UNKNOWN")
    assert res is not None and res.status == "TIMEOUT" and [a.event_id for a in res.assignments] == [1]
    assert res.stats["partial"] and res.stats["partial_reason"] == "timeout" and res.stats["unplaced_ids"] == [2]
    assert res.diagnoses[0].code == "partial" and "not proven impossible" in res.diagnoses[0].message
    assert any(d.code == "unplaced" and d.event_ids == [2] for d in res.diagnoses)
    # a warm start that breaks a hard rule is never returned
    bad = {1: Assignment(1, 1, 1, 2, (1,), frozenset(W1)), 2: Assignment(2, 1, 1, 2, (1,), frozenset(W1))}
    assert _timeout_partial(inp, prep, [], {}, 0.0, bad, "UNKNOWN") is None


def test_phase2_stats_are_passed_through() -> None:
    rooms = (room(1, "A101", 58),)
    events = (
        event(1, weeks=W1, day=1, start=1),
        event(2, weeks=W1, day=1, start=1),
        event(3, weeks=W1, day=2, start=1),
    )
    res = solve(make_input(rooms, events, weeks=W1, best_effort=True))
    assert res.stats["partial"] and res.stats["phase2_status"] in OK
    assert "phase2_solver_status" in res.stats and "phase2_wall_s" in res.stats


# --------------------------------------------------------------------------- core minimality (MINOR)


def test_core_says_minimal_only_when_proven_and_never_suggests_soft_overlaps() -> None:
    rooms = (room(1, "A101", 58),)
    events = tuple(event(i, allowed_days=(1,), earliest=1, latest=4, cohort_keys={"PSI:Y1"}) for i in (1, 2, 3))
    prep = prepare(make_input(rooms, events, weeks=W1))
    core, stats = core_diagnosis(prep, 10.0)
    assert core and stats["core_minimal"] is True and core[0].message.startswith("minimal conflict set")
    assert core[0].params["minimal"] is True
    assert not any("no_cohort_overlap" in s and "soft" in s for s in core[0].suggestions)
    assert not any("no_room_overlap" in s and "soft" in s for s in core[0].suggestions)
    starved, sstats = core_diagnosis(prep, 0.0)  # no budget for the shrinking probes
    if starved:
        assert sstats["core_minimal"] is False and "not proven minimal" in starved[0].message


# --------------------------------------------------------------------------- R3: relaxation week accounting


def test_relaxation_drops_the_shorter_request_not_the_whole_term() -> None:
    """Two fixed requests want the only room: a 14-week class and a 1-week one with more students.  Both
    cost one request; the unplaced event-weeks decide: the 1-week class gives way (before: the term class
    was dropped on the student tie-break)."""
    rooms = (room(1, "A101", 100),)
    term = event(1, size=30, day=1, start=1, label="PHAR 114")
    once = event(2, size=90, weeks=(9,), day=1, start=1, label="RAD 282 [w9]")
    res = solve(make_input(rooms, (term, once), best_effort=True))
    assert res.stats["partial"] and res.stats["unplaced_ids"] == [2]
    assert assigned(res.assignments, 1).room_ids == (1,)


# --------------------------------------------------------------------------- R2: size-0 exams


def test_size_zero_split_exam_is_placed_next_to_free_rooms() -> None:
    rooms = (room(1, "A109", 60, exam_capacity=30), room(2, "A205", 60, exam_capacity=30))
    ex = event(1, size=0, kind="exam", weeks=W1, day=1, start=1, max_rooms=3, share_room=True, label="TDS102")
    res = solve(make_input(rooms, (ex,), weeks=W1))
    assert res.status in OK and assigned(res.assignments, 1).room_ids


# --------------------------------------------------------------------------- one seat split per exam (MINOR)


def test_validation_requires_one_seat_split_for_the_whole_exam() -> None:
    """A split exam (80 over A + B, P1-P2) next to a single-room exam in A at P1 and one in B at P2: each
    period alone fits (20/60, then 60/20), but the CP model keeps one split for the whole exam, and no
    constant split fits both periods (A <= 30 and B <= 30)."""
    rooms = (room(1, "A", 120, exam_capacity=60), room(2, "B", 120, exam_capacity=60))
    split = event(1, size=80, kind="exam", weeks=W1, day=1, start=1, duration=2, max_rooms=2, share_room=True)
    a = event(2, size=30, kind="exam", weeks=W1, day=1, start=1, duration=1, share_room=True)
    b = event(3, size=30, kind="exam", weeks=W1, day=1, start=2, duration=1, share_room=True)
    inp = make_input(rooms, (split, a, b), weeks=W1)
    wk = frozenset(W1)
    bad = [Assignment(1, 1, 1, 2, (1, 2), wk), Assignment(2, 1, 1, 1, (1,), wk), Assignment(3, 1, 2, 2, (2,), wk)]
    assert [v for v in validate(inp, bad) if v.hard]
    ok = [Assignment(1, 1, 1, 2, (1, 2), wk), Assignment(2, 1, 1, 1, (1,), wk), Assignment(3, 1, 2, 2, (1,), wk)]
    assert not [v for v in validate(inp, ok) if v.hard]  # both singles in A: a constant 20-30 / 50-60 split fits
    res = solve(inp)
    assert res.status in OK and not [v for v in validate(inp, res.assignments) if v.hard]


# --------------------------------------------------------------------------- M5: residual round skipped


def test_residual_round_is_skipped_when_its_segments_clash() -> None:
    rooms = (room(1, "A", 58), room(2, "B", 58), room(3, "C", 58))
    wk = (1, 2, 3)
    e = event(1, weeks=wk, day=1, start=1, cohort_keys={"P:Y1"})
    x = event(2, weeks=(2,), day=1, start=1, locked=_lock(2, (1,), weeks=(2,)))  # holds A in week 2
    z = event(3, weeks=(2,), day=1, start=1, cohort_keys={"P:Y1"}, locked=_lock(3, (3,), weeks=(2,)))
    blocker = event(4, weeks=(1, 3), day=1, start=1, locked=_lock(4, (2,), weeks=(1, 3)))  # holds B in 1, 3
    inp = make_input(rooms, (e, x, z, blocker), weeks=wk, best_effort=True)
    split = split_blocked_weeks(inp)
    placed = [x.locked, z.locked, blocker.locked]
    nxt = residual_split(split, placed)  # type: ignore[arg-type]
    assert nxt is not None
    cand, hints = nxt
    assert residual_gain(split, placed, cand, hints) <= 0  # type: ignore[arg-type]


# --------------------------------------------------------------------------- M1: fallback sizes not in waste


def test_fallback_sizes_stay_out_of_waste_minimisation() -> None:
    rooms = (room(1, "A204", 156),)
    e = event(1, size=10, weeks=W1, day=1, start=1)
    base = solve(make_input(rooms, (e,), weeks=W1))
    assert base.objective_breakdown.get("min_capacity_waste", 0) > 0
    excl = (Constraint("min_capacity_waste", {"exclude_event_ids": [1]}, hard=False),)
    res = solve(make_input(rooms, (e,), excl, weeks=W1))
    assert res.status in OK and res.objective_breakdown.get("min_capacity_waste", 0) == 0
