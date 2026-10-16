"""Round-1 R1-M-03: a hard ``room_pin`` that cannot seat its class.

Fatih Bey's scenario: ING 302 (100 students, a class the bridge lets split over up to 3 rooms) hard-pinned to
B 201 (30 seats). The pin prunes every other room, the split capacity link (Σ seats >= size) can never hold, and
the old diagnosis called B 201 "a room that fits, busy at that time". The static checker now names the pin:
``no_room`` / ``reason: capacity`` with the pinned rooms, their seats and the rule id; best effort leaves exactly
that class out, every other class keeps every hard rule (hard 100), and the explanation is the pin, never
"rooms busy".

Feasible / infeasible (named) / soft-weight cases, single-room and split events, rule pins and event-level pins.
Deterministic: fixed seed, two solves give the same assignments.
"""

from __future__ import annotations

from app.solver.build import prepare
from app.solver.cpsat import solve
from app.solver.diagnose import static_check
from app.solver.model import Constraint
from tests.solver.conftest import assigned, event, make_input, room

ROOMS = (room(1, "A101", 58), room(2, "B201", 30), room(3, "C201", 126), room(4, "B202", 40))


def _pin(rooms: list[int], ids: list[int], *, hard: bool = True, cid: int = 75, weight: int = 1) -> Constraint:
    return Constraint("room_pin", {"event_ids": ids, "room_ids": rooms}, hard, weight, cid)


def _no_room(diags: list, eid: int):  # type: ignore[no-untyped-def]
    hit = [d for d in diags if d.code == "no_room" and d.event_ids == [eid]]
    assert hit, [(d.code, d.event_ids, d.message) for d in diags]
    return hit[0]


def test_feasible_hard_pin_to_a_room_that_seats_the_class() -> None:
    inp = make_input(ROOMS, (event(1, size=100, day=1, start=3, duration=3),), (_pin([3], [1]),))
    res = solve(inp)
    assert res.status == "OPTIMAL" and res.hard_score == 100
    assert assigned(res.assignments, 1).room_ids == (3,)


def test_single_room_class_pinned_too_small_is_named_by_the_pin() -> None:
    events = (event(1, size=100, day=1, start=3, duration=3, label="ING 302"), event(2, size=20, day=1, start=3))
    inp = make_input(ROOMS, events, (_pin([2], [1]),), best_effort=True)
    d = _no_room(static_check(prepare(inp)), 1)
    p = d.params
    assert p["reason"] == "capacity" and p["pin_constraint_ids"] == [75]
    assert p["pinned_rooms"] == [{"id": 2, "room": "B201", "capacity": 30}] and p["pinned_seats"] == 30
    assert {"room_pin", "capacity"} <= set(d.constraint_kinds)
    assert "pinned" in d.message and "B201" in d.message and "30" in d.message
    res = solve(inp)
    assert res.status == "INFEASIBLE" and res.stats.get("partial") and res.hard_score == 100
    assert {a.event_id for a in res.assignments} == {2}  # only the pinned class is left out
    assert not [x for x in res.diagnoses if x.code == "unplaced" and 1 in x.event_ids]


def test_split_class_pinned_to_one_small_room_is_not_called_rooms_busy() -> None:
    """The R1-M-03 case: a split-capable class keeps a non-empty room domain (B 201 alone), so only the capacity
    link refuses it; the explanation must be the pin, not "rooms that fit are busy"."""
    big = event(1, size=100, day=1, start=3, duration=3, label="ING 302", max_rooms=3)
    holder = event(2, size=25, day=1, start=3, duration=3, label="BCT 132 §1", required_room_ids={2})
    inp = make_input(ROOMS, (big, holder), (_pin([2], [1]),), best_effort=True)
    d = _no_room(static_check(prepare(inp)), 1)
    assert d.severity == "error" and d.params["reason"] == "capacity"
    assert d.params["pinned_seats"] == 30 and d.params["pin_constraint_ids"] == [75] and d.params["size"] == 100
    res = solve(inp)
    assert res.hard_score == 100 and {a.event_id for a in res.assignments} == {2}
    assert not [x for x in res.diagnoses if x.code == "unplaced" and x.event_ids == [1]]


def test_split_class_pinned_to_rooms_that_seat_it_together_is_feasible() -> None:
    big = event(1, size=100, day=1, start=3, duration=3, max_rooms=3)
    inp = make_input(ROOMS, (big,), (_pin([1, 2, 4], [1]),))  # 58 + 30 + 40 = 128 >= 100
    assert not [d for d in static_check(prepare(inp)) if d.severity == "error"]
    res = solve(inp)
    assert res.status in ("OPTIMAL", "FEASIBLE") and res.hard_score == 100
    a = assigned(res.assignments, 1)
    assert set(a.room_ids) <= {1, 2, 4} and sum(r.capacity for r in ROOMS if r.id in a.room_ids) >= 100


def test_event_level_pin_on_a_split_class_is_named_too() -> None:
    big = event(1, size=100, day=1, start=3, duration=3, max_rooms=2, required_room_ids={2, 4})
    d = _no_room(static_check(prepare(make_input(ROOMS, (big,)))), 1)
    assert d.params["reason"] == "capacity" and d.params["pinned_seats"] == 70
    assert d.params["pin_constraint_ids"] == [] and {r["room"] for r in d.params["pinned_rooms"]} == {"B201", "B202"}


def test_soft_pin_to_a_small_room_keeps_capacity_hard_and_costs_weight() -> None:
    """A soft pin is a wish: capacity stays hard (the class sits in a room that seats it) and the missed wish is
    a weighted soft penalty."""
    ev = (event(1, size=100, day=1, start=3, duration=3),)
    light = solve(make_input(ROOMS, ev, (_pin([2], [1], hard=False, weight=1),)))
    heavy = solve(make_input(ROOMS, ev, (_pin([2], [1], hard=False, weight=5),)))
    for res in (light, heavy):
        assert res.status in ("OPTIMAL", "FEASIBLE") and res.hard_score == 100
        assert assigned(res.assignments, 1).room_ids == (3,)
        assert res.objective_breakdown.get("room_pin", 0) > 0
    assert heavy.objective_breakdown["room_pin"] > light.objective_breakdown["room_pin"]
    assert not [
        d for d in static_check(prepare(make_input(ROOMS, ev, (_pin([2], [1], hard=False),)))) if d.code == "no_room"
    ]


def test_trusted_lock_is_not_a_pin_capacity_error() -> None:
    """The planner's own locked room (D1, ``trust_locked_rooms``) stays an accepted, reported exception."""
    from app.solver.model import Assignment

    locked = event(
        1,
        size=100,
        day=1,
        start=3,
        duration=3,
        max_rooms=3,
        locked=Assignment(1, 1, 3, 5, (2,), frozenset(range(1, 15))),
    )
    inp = make_input(ROOMS, (locked,), (_pin([2], [1]),), trust_locked_rooms=True)
    assert not [d for d in static_check(prepare(inp)) if d.code == "no_room"]


def test_deterministic_with_a_fixed_seed() -> None:
    events = tuple(event(i, size=20 + i, allowed_days=(1, 2), duration=2) for i in range(1, 9))
    inp = make_input(ROOMS, events, (_pin([2], [3]), _pin([3], [5], cid=76)), seed=7)
    a, b = solve(inp), solve(inp)
    assert sorted(a.assignments, key=lambda x: x.event_id) == sorted(b.assignments, key=lambda x: x.event_id)
