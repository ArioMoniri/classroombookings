"""``cpsat.day_sweep`` (room re-optimisation per day at fixed times) and ``cpsat.polish_preferred`` (single
validated moves into the preferred room): both only ever keep a change that leaves every hard rule
intact and strictly lowers the total penalty."""

from __future__ import annotations

from app.solver.build import prepare
from app.solver.cpsat import day_sweep, polish_preferred
from app.solver.domains import normalize_input
from app.solver.model import Assignment
from app.solver.scoring import evaluate
from tests.solver.conftest import event, make_input, room

ROOMS = (room(1, "A101", 40), room(2, "A204", 120))


def _a(eid: int, day: int, start: int, rooms: tuple[int, ...], dur: int = 2) -> Assignment:
    return Assignment(eid, day, start, start + dur - 1, rooms, frozenset({1}))


def test_sweep_rerooms_each_day_into_the_cheaper_room() -> None:
    evs = (
        event(1, size=30, weeks=(1,), day=1, start=1),
        event(2, size=30, weeks=(1,), day=1, start=5),
        event(3, size=30, weeks=(1,), day=2, start=1),
    )
    inp = normalize_input(make_input(ROOMS, evs, weeks=(1,)))
    start = [_a(1, 1, 1, (2,)), _a(2, 1, 5, (2,)), _a(3, 2, 1, (2,))]  # 30 students in the 120-seat hall
    before = evaluate(inp, start).total_penalty()
    out, stats = day_sweep(inp, start, budget_s=10)
    assert [a.room_ids for a in out] == [(1,), (1,), (1,)]
    assert [(a.day, a.start) for a in out] == [(a.day, a.start) for a in start]  # times never move
    ev = evaluate(inp, out)
    assert ev.hard_score() == 100 and ev.total_penalty() < before
    assert stats["sweep_days"] == 2 and stats["sweep_improved_days"] == 2
    assert stats["sweep_penalty_after"] == ev.total_penalty()
    assert day_sweep(inp, start, budget_s=10)[0] == out  # deterministic


def test_sweep_keeps_locked_events_and_hard_rules() -> None:
    lock = _a(1, 1, 1, (1,))
    evs = (
        event(1, size=30, weeks=(1,), day=1, start=1, locked=lock),
        event(2, size=30, weeks=(1,), day=1, start=2),  # overlaps the lock: A101 is taken
        event(3, size=30, weeks=(1,), day=2, start=1),
    )
    inp = normalize_input(make_input(ROOMS, evs, weeks=(1,), trust_locked_rooms=True))
    start = [lock, _a(2, 1, 2, (2,)), _a(3, 2, 1, (2,))]
    out, stats = day_sweep(inp, start, budget_s=10)
    by = {a.event_id: a for a in out}
    assert by[1] == lock and by[2].room_ids == (2,)  # the cheaper room is held by the lock
    assert by[3].room_ids == (1,)
    assert evaluate(inp, out).hard_score() == 100
    assert stats["sweep_improved_days"] == 1


def test_sweep_never_accepts_a_day_that_worsens_a_cross_day_term() -> None:
    """``same_room_group`` links a day-1 and a day-2 event: moving either alone into the smaller room
    saves 8 waste units (9 -> 1) but costs the group penalty (weight 20), so neither day is accepted."""
    evs = (
        event(1, size=30, weeks=(1,), day=1, start=1, same_room_group="g"),
        event(2, size=30, weeks=(1,), day=2, start=1, same_room_group="g"),
        event(3, size=30, weeks=(1,), day=3, start=1),
    )
    inp = normalize_input(make_input(ROOMS, evs, weeks=(1,), weights={"same_room_group": 20}))
    start = [_a(1, 1, 1, (2,)), _a(2, 2, 1, (2,)), _a(3, 3, 1, (2,))]
    before = evaluate(inp, start).total_penalty()
    out, stats = day_sweep(inp, start, budget_s=10)
    assert out[:2] == start[:2]
    assert out[2].room_ids == (1,)  # the unlinked day-3 event still moves
    assert evaluate(inp, out).total_penalty() == before - 8
    assert stats["sweep_improved_days"] == 1


def test_polish_moves_into_the_preferred_room_only_when_the_penalty_drops() -> None:
    rooms = (room(1, "A101", 40), room(2, "C301", 60))
    e = event(1, size=30, weeks=(1,), day=1, start=1, preferred_room_ids=(2,))
    start = [_a(1, 1, 1, (1,))]
    inp = normalize_input(make_input(rooms, (e,), weeks=(1,)))
    out, moves = polish_preferred(prepare(inp), inp, start)  # preference 10 > 2 waste units
    assert moves == 1 and out[0].room_ids == (2,)
    waste = normalize_input(
        make_input(rooms, (e,), weeks=(1,), weights={"room_preference": 1, "min_capacity_waste": 5})
    )
    out, moves = polish_preferred(prepare(waste), waste, start)  # 1 preference unit < 2 x 5 waste
    assert moves == 0 and out == start


def test_polish_never_moves_into_a_busy_preferred_room() -> None:
    rooms = (room(1, "A101", 40), room(2, "C301", 60))
    evs = (
        event(1, size=30, weeks=(1,), day=1, start=1, preferred_room_ids=(2,)),
        event(2, size=50, weeks=(1,), day=1, start=1),
    )
    inp = normalize_input(make_input(rooms, evs, weeks=(1,)))
    start = [_a(1, 1, 1, (1,)), _a(2, 1, 1, (2,))]
    out, moves = polish_preferred(prepare(inp), inp, start)
    assert moves == 0 and out == start
