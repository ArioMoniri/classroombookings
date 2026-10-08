"""Reproducing the planner's rooms when they are only soft hints: multi-room preference units, the
greedy preference pass, the preferred-room repair of the relaxation hint and the relaxation's
hint-closeness tier (feasible / soft-weight cases; the hard rules are untouched)."""

from __future__ import annotations

from dataclasses import replace

from app.solver.build import prepare
from app.solver.constraints.room_preference import units
from app.solver.cpsat import solve
from app.solver.diagnose import relaxation_diagnosis
from app.solver.greedy import greedy_assignments, prefer_rooms
from app.solver.model import Assignment
from tests.solver.conftest import assigned, event, make_input, room

W = (1,)


def test_multi_room_event_uses_its_preferred_set_for_free() -> None:
    prefs = (4, 7, 9)
    assert [units(prefs, r, 2) for r in (4, 7, 9, 1)] == [0, 0, 1, 2]
    assert [units(prefs, r, 1) for r in (4, 7, 9, 1)] == [0, 1, 2, 3]  # single-room: plain rank
    assert units((), 5, 3) == 1  # outside an empty list never costs nothing


def test_split_exam_reproduces_the_planners_room_pair() -> None:
    """Soft weight: the planner's pair A 204 + A 102 (rank 0 and 1) costs nothing, so it beats the
    tighter pair with less capacity waste; with a negligible preference weight the waste wins."""
    rooms = (
        room(1, "A204", 160, exam_capacity=80),
        room(2, "A102", 120, exam_capacity=60),
        room(3, "B101", 120, exam_capacity=60),
        room(4, "B102", 100, exam_capacity=50),
    )
    ex = event(1, size=105, kind="exam", weeks=W, day=1, start=1, max_rooms=2, preferred_room_ids=(1, 2))
    pref = solve(make_input(rooms, (ex,), weeks=W, weights={"room_preference": 10, "min_capacity_waste": 1}))
    assert set(assigned(pref.assignments, 1).room_ids) == {1, 2}
    assert pref.objective_breakdown.get("room_preference", 0) == 0
    waste = solve(make_input(rooms, (ex,), weeks=W, weights={"room_preference": 0, "min_capacity_waste": 10}))
    # A 102 and B 101 have the same seats: either tight pair wastes as little (the canonical tie-break picks one)
    assert set(assigned(waste.assignments, 1).room_ids) in ({3, 4}, {2, 4})


def _two_groups():  # type: ignore[no-untyped-def]
    """A (50) prefers R (60 seats); B (55, no preference) is bigger and would take R first."""
    rooms = (room(1, "R", 60), room(2, "S", 100))
    a = event(1, size=50, weeks=W, day=1, start=1, preferred_room_ids=(1,))
    b = event(2, size=55, weeks=W, day=1, start=1)
    return make_input(rooms, (a, b), weeks=W)


def test_greedy_preference_pass_seats_the_preferring_event_first() -> None:
    g = {a.event_id: a.room_ids for a in greedy_assignments(prepare(_two_groups()))}
    assert g == {1: (1,), 2: (2,)}


def test_greedy_still_places_locks_before_preferences() -> None:
    inp = _two_groups()
    lock = Assignment(2, 1, 1, 2, (1,), frozenset(W))
    inp = replace(inp, events=(inp.events[0], replace(inp.events[1], locked=lock)))
    g = {a.event_id: a.room_ids for a in greedy_assignments(prepare(inp))}
    assert g == {1: (2,), 2: (1,)}  # the lock wins, A takes the other room


def test_prefer_rooms_moves_events_back_where_the_room_is_free() -> None:
    prep = prepare(_two_groups())
    scattered = [Assignment(1, 1, 1, 2, (2,), frozenset(W)), Assignment(2, 1, 1, 2, (1,), frozenset(W))]
    assert prefer_rooms(prep, scattered) == scattered  # R is busy: nothing moves
    alone = [Assignment(1, 1, 1, 2, (2,), frozenset(W))]
    assert prefer_rooms(prep, alone)[0].room_ids == (1,)


def test_relaxation_keeps_the_hint_rooms_when_placement_allows() -> None:
    """Three groups, two rooms, one slot: one group must go (the maximum placement is 2); among the
    maximum placements the relaxation keeps the warm start's rooms (hint-closeness tier)."""
    rooms = (room(1, "R", 60), room(2, "S", 60))
    evs = tuple(event(i, size=30, weeks=W, day=1, start=1) for i in (1, 2, 3))
    inp = make_input(rooms, evs, weeks=W, best_effort=True, workers=1)
    hint = [Assignment(3, 1, 1, 2, (1,), frozenset(W)), Assignment(1, 1, 1, 2, (2,), frozenset(W))]
    _d, stats, placed = relaxation_diagnosis(prepare(inp), 5.0, hints=hint)
    assert stats["relax_status"] == "OPTIMAL" and stats["relax_hint_terms"] == 2
    assert {e: a.room_ids for e, a in placed.items()} == {3: (1,), 1: (2,)}
