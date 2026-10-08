"""Week segments for term runs (``app.solver.weeksplit``): a room blocked in some weeks only moves those
weeks; the planner's lock holds for the others.  Feasible / infeasible-with-diagnosis / soft-weight
triples plus the bookkeeping (constraints, previous, merge back, determinism)."""

from __future__ import annotations

from dataclasses import replace

from app.solver.cpsat import solve
from app.solver.model import Assignment, Block, Constraint
from app.solver.repair import validate
from app.solver.weeksplit import (
    REASON_BLOCKED,
    REASON_LOCK_CLASH,
    REASON_NO_COMMON_ROOM,
    REASON_ROOM_CHANGES,
    fully_placed,
    merge_back,
    residual_split,
    solve_segmented,
    split_blocked_weeks,
    to_original,
)

from tests.solver.conftest import event, make_input, room

W3 = (1, 2, 3)


def _lock(eid: int, rooms: tuple[int, ...], weeks: tuple[int, ...] = W3, day: int = 1, start: int = 1) -> Assignment:
    return Assignment(eid, day, start, start + 1, rooms, frozenset(weeks))


def _blocked_lock_input(**kw: object):  # type: ignore[no-untyped-def]
    """E1 locked to A101 for weeks 1-3; A101 carries an ETKİNLİK block on day 1 P1-P2 in week 2."""
    rooms = (room(1, "A101", 58), room(2, "A102", 58), room(3, "A103", 20))
    e1 = event(1, size=40, weeks=W3, day=1, start=1, label="MAT 112", locked=_lock(1, (1,)))
    blocks = (Block(1, 2, 1, 1, 2),)
    return make_input(rooms, (e1,), weeks=W3, blocks=blocks, trust_locked_rooms=True, best_effort=True, **kw)


# --------------------------------------------------------------------------- locked room blocked in one week


def test_locked_room_blocked_in_one_week_moves_only_that_week() -> None:
    inp = _blocked_lock_input()
    sp = split_blocked_weeks(inp)
    main = next(e for e in sp.inp.events if e.id == 1)
    seg = next(e for e in sp.inp.events if e.id != 1)
    assert main.weeks == frozenset({1, 3}) and main.locked is not None and main.locked.weeks == frozenset({1, 3})
    assert seg.weeks == frozenset({2}) and seg.locked is None and (seg.fixed_day, seg.fixed_start) == (1, 1)
    assert seg.label == "MAT 112 [w2]" and seg.preferred_room_ids[0] == 1 and sp.origin == {seg.id: 1}
    note = sp.diagnoses[0]
    assert note.code == "week_split" and note.severity == "warning" and note.params["reason"] == REASON_BLOCKED
    assert note.params["kept_weeks"] == [1, 3] and note.params["moved_weeks"] == [2]
    assert "MAT 112 keeps A101 in week(s) 1, 3" in note.message and "blocked by the grid in week(s) 2" in note.message

    res, split = solve_segmented(inp)
    assert res.status in ("OPTIMAL", "FEASIBLE") and res.hard_score == 100
    assert not [v for v in validate(split.inp, res.assignments) if v.hard]
    out = to_original(split, res)
    rows = sorted(out.assignments, key=lambda a: min(a.weeks))
    assert [(sorted(a.weeks), a.room_ids) for a in rows] == [([1, 3], (1,)), ([2], (2,))]  # A103 is too small
    assert all(a.event_id == 1 for a in rows)
    assert out.stats["placed"] == 1 and out.stats["unplaced"] == 0 and out.stats["week_split"]["room_changes"] == 1
    assert any(d.code == "week_split" and d.event_ids == [1] for d in out.diagnoses)


def test_without_split_the_whole_term_is_lost() -> None:
    """Regression of the Bahar-term case: one blocked week made the lock ineligible for the whole term."""
    res = solve(_blocked_lock_input())
    assert res.stats["placed"] == 0 and any(d.code == "locked_ineligible" for d in res.diagnoses)


def test_blocked_week_without_any_free_room_is_reported_and_the_rest_stays() -> None:
    """Infeasible: in week 2 no other room seats the group.  The segment stays unplaced with a named
    reason; the original keeps its lock for weeks 1 and 3 (partially placed, never silently dropped)."""
    rooms = (room(1, "A101", 58), room(3, "A103", 20))
    inp = replace(_blocked_lock_input(), rooms=rooms)
    res, split = solve_segmented(inp)
    assert res.status == "INFEASIBLE" and res.stats["partial"] and res.hard_score == 100
    seg_id = next(i for i in split.origin)
    assert res.stats["unplaced_ids"] == [seg_id]
    why = next(d for d in res.diagnoses if d.code == "unplaced" or (d.code == "no_room" and seg_id in d.event_ids))
    assert seg_id in why.event_ids and "MAT 112 [w2]" in why.message
    out = to_original(split, res)
    assert out.stats["placed"] == 0 and out.stats["partially_placed_ids"] == [1] and out.stats["unplaced_ids"] == [1]
    assert [(sorted(a.weeks), a.room_ids) for a in out.assignments] == [([1, 3], (1,))]
    assert all(seg_id not in d.event_ids for d in out.diagnoses)  # ids translated back to the request


def test_trusted_small_lock_does_not_demand_a_bigger_room_for_the_moved_week() -> None:
    """The planner seats 70 students in a 58-seat room (trusted lock); the moved week needs no more
    seats than the planner's room offered, and the clip is reported."""
    inp = _blocked_lock_input()
    inp = replace(inp, events=tuple(replace(e, size=70) for e in inp.events))
    sp = split_blocked_weeks(inp)
    seg = next(e for e in sp.inp.events if e.id != 1)
    assert seg.size == 58 and sp.diagnoses[0].params["size_clipped_to"] == 58
    res, split = solve_segmented(inp)
    assert res.hard_score == 100 and len(fully_placed(split, res.assignments)) == 1


def test_lock_clash_in_some_weeks_moves_the_longer_lock() -> None:
    """E1 (weeks 1-3) and E2 (week 2 only) are both locked to A101 at the same time: E2 keeps its room,
    E1 moves in week 2 (``locked_clash``); without the split one of them is lost."""
    rooms = (room(1, "A101", 58), room(2, "A102", 58))
    e1 = event(1, weeks=W3, day=1, start=1, locked=_lock(1, (1,)))
    e2 = event(2, weeks=(2,), day=1, start=1, locked=_lock(2, (1,), (2,)))
    inp = make_input(rooms, (e1, e2), weeks=W3, best_effort=True)
    sp = split_blocked_weeks(inp)
    assert sp.diagnoses[0].params["reason"] == REASON_LOCK_CLASH and sp.diagnoses[0].params["clash_ids"] == [2]
    res, split = solve_segmented(inp)
    assert res.hard_score == 100 and fully_placed(split, res.assignments) == {1, 2}
    rows = {(a.event_id, tuple(sorted(a.weeks))): a.room_ids for a in to_original(split, res).assignments}
    assert rows == {(1, (1, 3)): (1,), (1, (2,)): (2,), (2, (2,)): (1,)}
    assert solve(inp).stats["placed"] == 1


def test_full_overlap_is_left_to_the_static_checker() -> None:
    """Two locks holding the room in *every* week are a data error, not a week problem: no split."""
    rooms = (room(1, "A101", 58), room(2, "A102", 58))
    e1 = event(1, weeks=W3, day=1, start=1, locked=_lock(1, (1,)))
    e2 = event(2, weeks=W3, day=1, start=1, locked=_lock(2, (1,)))
    sp = split_blocked_weeks(make_input(rooms, (e1, e2), weeks=W3))
    assert not sp.segments and not sp.diagnoses


# --------------------------------------------------------------------------- unlocked fixed-time events


def test_unlocked_event_without_a_common_free_room_is_segmented() -> None:
    """A101 is blocked in week 2, A102 in weeks 1 and 3: no room is free in every week."""
    rooms = (room(1, "A101", 58), room(2, "A102", 58))
    e = event(1, weeks=W3, day=1, start=1)
    blocks = (Block(1, 2, 1, 1, 2), Block(2, 1, 1, 1, 2), Block(2, 3, 1, 1, 2))
    inp = make_input(rooms, (e,), weeks=W3, blocks=blocks)
    sp = split_blocked_weeks(inp)
    assert sp.diagnoses[0].params["reason"] == REASON_NO_COMMON_ROOM
    assert sorted(sorted(x.weeks) for x in sp.inp.events) == [[1, 3], [2]]
    assert solve(inp).status == "INFEASIBLE"
    res, split = solve_segmented(inp)
    assert res.status in ("OPTIMAL", "FEASIBLE") and res.hard_score == 100
    rows = {tuple(sorted(a.weeks)): a.room_ids for a in to_original(split, res).assignments}
    assert rows == {(1, 3): (1,), (2,): (2,)}


def test_unlocked_event_with_a_common_room_is_not_split() -> None:
    rooms = (room(1, "A101", 58), room(2, "A102", 58))
    inp = make_input(rooms, (event(1, weeks=W3, day=1, start=1),), weeks=W3, blocks=(Block(1, 2, 1, 1, 2),))
    sp = split_blocked_weeks(inp)
    assert sp.inp is inp and not sp.diagnoses


def _profile_input(weight: int | None = None):  # type: ignore[no-untyped-def]
    """30 students; A101 (40 seats) blocked in week 2, A204 (200 seats) always free."""
    rooms = (room(1, "A101", 40), room(2, "A204", 200))
    e = event(1, size=30, weeks=W3, day=1, start=1)
    weights = {} if weight is None else {"same_room_across_weeks": weight}
    return make_input(rooms, (e,), weeks=W3, blocks=(Block(1, 2, 1, 1, 2),), weights=weights)


def test_profile_split_soft_weight_decides_between_room_change_and_waste() -> None:
    """Soft weight: by default one week moves to the big hall (waste 17 units + 8 for the extra room <
    2 × 17 waste); with a heavy ``same_room_across_weeks`` weight all weeks stay in A204."""
    sp = split_blocked_weeks(_profile_input(), profile_split=True)
    assert sp.diagnoses[0].params["reason"] == REASON_ROOM_CHANGES
    res, split = solve_segmented(_profile_input(), profile_split=True)
    out = to_original(split, res)
    assert {tuple(sorted(a.weeks)): a.room_ids for a in out.assignments} == {(1, 3): (1,), (2,): (2,)}
    assert out.objective_breakdown["same_room_across_weeks"] == 8
    res2, split2 = solve_segmented(_profile_input(weight=50), profile_split=True)
    out2 = to_original(split2, res2)
    assert [(sorted(a.weeks), a.room_ids) for a in out2.assignments] == [([1, 2, 3], (2,))]  # merged back
    assert not [d for d in out2.diagnoses if d.code == "week_split"]  # no room change happened: not reported


# --------------------------------------------------------------------------- relaxation and residual round


def test_relaxation_prefers_losing_one_week_over_losing_two_requests() -> None:
    """E1 (locked A101, blocked in week 2) needs A102 in week 2, where E2 and E3 (week 2 only) compete
    for A102 at overlapping times: dropping E1's week-2 segment keeps both one-week requests."""
    rooms = (room(1, "A101", 58), room(2, "A102", 58))
    e1 = event(1, weeks=W3, day=1, start=1, duration=4, locked=Assignment(1, 1, 1, 4, (1,), frozenset(W3)))
    e2 = event(2, weeks=(2,), day=1, start=1)
    e3 = event(3, weeks=(2,), day=1, start=3)
    inp = make_input(rooms, (e1, e2, e3), weeks=W3, blocks=(Block(1, 2, 1, 1, 4),), best_effort=True)
    res, split = solve_segmented(inp)
    assert fully_placed(split, res.assignments) == {2, 3}
    assert to_original(split, res).stats["partially_placed_ids"] == [1]


def test_residual_round_splits_an_event_left_unplaced() -> None:
    """Given a placement, an unplaced fixed-time event gets the rooms that are free in its weeks."""
    rooms = (room(1, "A101", 58), room(2, "A102", 58))
    e1 = event(1, weeks=(1,), day=1, start=1)
    e2 = event(2, weeks=(2, 3), day=1, start=1)
    e3 = event(3, weeks=(3,), day=1, start=1)
    e4 = event(4, weeks=W3, day=1, start=1)
    inp = make_input(rooms, (e1, e2, e3, e4), weeks=W3, best_effort=True)
    sp = split_blocked_weeks(inp)
    placed = [
        Assignment(1, 1, 1, 2, (1,), frozenset({1})),
        Assignment(2, 1, 1, 2, (2,), frozenset({2, 3})),
        Assignment(3, 1, 1, 2, (1,), frozenset({3})),
    ]
    nxt = residual_split(sp, placed)
    assert nxt is not None
    sp2, hints = nxt
    # A102 is free in week 1, A101 in week 2, nothing in week 3 (A101 E3, A102 E2)
    parts = sorted(sorted(e.weeks) for e in sp2.inp.events if sp2.origin_of(e.id) == 4)
    assert parts == [[1], [2], [3]]
    hinted = {tuple(sorted(h.weeks)): h.room_ids for h in hints if sp2.origin_of(h.event_id) == 4}
    assert hinted == {(1,): (2,), (2,): (1,)}  # week 3 stays unhinted (no room at all)
    note = sp2.diagnoses[-1]
    assert note.params["reason"] == "no_room_all_weeks" and note.params["uncovered_weeks"] == [3]
    assert not [v for v in validate(sp2.inp, hints) if v.hard and set(v.event_ids) & {h.event_id for h in hints}]


# --------------------------------------------------------------------------- bookkeeping


def test_targeted_constraints_and_previous_follow_the_segments() -> None:
    inp = _blocked_lock_input()
    pin = Constraint("room_forbid", {"event_ids": [1], "rooms": [3]}, True, id=7)
    prev = Assignment(1, 1, 1, 2, (1,), frozenset(W3))
    sp = split_blocked_weeks(replace(inp, constraints=(pin,), previous=(prev,)))
    seg = next(i for i in sp.origin)
    c7 = next(c for c in sp.inp.constraints if c.id == 7)
    assert c7.params["event_ids"] == [1, seg]
    group = next(c for c in sp.inp.constraints if c.params.get("week_segments"))
    assert group.kind == "same_room_across_weeks" and not group.hard and group.params["groups"] == [[1, seg]]
    assert sorted((a.event_id, sorted(a.weeks)) for a in sp.inp.previous) == [(seg, [2]), (1, [1, 3])]


def test_merge_back_joins_segments_in_the_same_room() -> None:
    sp = split_blocked_weeks(_blocked_lock_input())
    seg = next(i for i in sp.origin)
    same = [Assignment(1, 1, 1, 2, (2,), frozenset({1, 3})), Assignment(seg, 1, 1, 2, (2,), frozenset({2}))]
    assert [(a.event_id, sorted(a.weeks)) for a in merge_back(sp, same)] == [(1, [1, 2, 3])]


def test_week_split_is_deterministic_and_idempotent() -> None:
    inp = replace(_blocked_lock_input(), workers=4, seed=5)
    a, sa = solve_segmented(inp)
    b, sb = solve_segmented(inp)
    assert sorted((x.event_id, x.room_ids, sorted(x.weeks)) for x in a.assignments) == sorted(
        (x.event_id, x.room_ids, sorted(x.weeks)) for x in b.assignments
    )
    again = split_blocked_weeks(sa.inp)
    assert not again.segments  # the split input needs no further split
    assert [e.id for e in sa.inp.events] == [e.id for e in sb.inp.events]


def test_single_week_runs_are_untouched() -> None:
    rooms = (room(1, "A101", 58),)
    e1 = event(1, weeks=(3,), day=1, start=1, locked=_lock(1, (1,), (3,)))
    inp = make_input(rooms, (e1,), weeks=(3,), blocks=(Block(1, 3, 1, 1, 2),))
    assert split_blocked_weeks(inp).inp is inp
