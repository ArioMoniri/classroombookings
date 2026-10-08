"""LNS repair after an edit, neighbourhood computation, validate/score helpers."""

from __future__ import annotations

from dataclasses import replace

from app.solver.model import Assignment
from app.solver.repair import neighbours, repair, score, validate
from tests.solver.conftest import assigned, event, make_input, room
from tests.solver.generators import GenParams, generate

ALL = frozenset(range(1, 15))


def _instance() -> tuple:
    inp, planted = generate(GenParams(n_rooms=10, n_events=30, seed=11, tightness=0.3, days=(1, 2, 3)))
    inp = replace(inp, time_limit_s=10.0, workers=2)
    assert not [v for v in validate(inp, planted) if v.hard]
    return inp, planted


def test_repair_keeps_untouched_events_stable() -> None:
    inp, planted = _instance()
    by_id = {a.event_id: a for a in planted}
    size = {e.id: e.size for e in inp.events}
    flexible = {e.id for e in inp.events if e.fixed_day is None}
    # move the smallest flexible event onto the room/time of another small event (a conflict)
    small = sorted(planted, key=lambda a: size[a.event_id])
    victim = next(a for a in small if a.event_id in flexible)
    rooms = {r.id: r for r in inp.rooms}
    victim_event = next(e for e in inp.events if e.id == victim.event_id)

    def eligible(a: Assignment) -> bool:  # the victim could legally sit in the target's room
        r = rooms[a.room_ids[0]]
        return (
            r.capacity >= victim_event.size
            and not (r.tags & victim_event.forbidden_tags)
            and victim_event.required_tags <= r.tags
        )

    target = next(
        a
        for a in small
        if a.event_id != victim.event_id and (a.day, a.start) != (victim.day, victim.start) and eligible(a)
    )
    moved = Assignment(
        victim.event_id,
        target.day,
        target.start,
        target.start + (victim.end - victim.start),
        target.room_ids,
        victim.weeks,
    )
    edited = [moved if a.event_id == victim.event_id else a for a in planted]
    assert [v for v in validate(inp, edited) if v.hard], "edit should conflict"
    res = repair(inp, edited, [victim.event_id], time_limit_s=10.0)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.diagnoses
    assert res.hard_score == 100
    freed = set(res.stats["repair"]["freed"])
    assert victim.event_id not in freed  # keep_changed: the edit itself is locked
    assert assigned(res.assignments, victim.event_id) == moved
    for a in res.assignments:
        if a.event_id not in freed and a.event_id != victim.event_id:
            assert a == by_id[a.event_id], f"untouched event {a.event_id} moved"
    assert not [v for v in validate(inp, res.assignments) if v.hard]


def test_repair_can_free_the_changed_event_too() -> None:
    inp, planted = _instance()
    victim = planted[3]
    res = repair(inp, planted, [victim.event_id], time_limit_s=5.0, keep_changed=False)
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert victim.event_id in res.stats["repair"]["freed"]
    # stability keeps the event where it was when nothing forces a move
    assert assigned(res.assignments, victim.event_id) == victim


def test_repair_reports_impossible_edit() -> None:
    rooms = (room(1, "A101", 58),)
    a, b = event(1, day=1, start=1, duration=2), event(2, day=1, start=3, duration=2)
    inp = make_input(rooms, (a, b))
    current = [Assignment(1, 1, 1, 2, (1,), ALL), Assignment(2, 1, 3, 4, (1,), ALL)]
    # the user drags event 2 onto P2-P3 in the only room: event 1 is fixed there -> impossible
    edited = [current[0], Assignment(2, 1, 2, 3, (1,), ALL)]
    res = repair(inp, edited, [2], time_limit_s=5.0)
    assert res.status == "INFEASIBLE"
    assert res.diagnoses


def test_neighbours_radius() -> None:
    inp, planted = _instance()
    seed = planted[0].event_id
    n1 = neighbours(inp, planted, [seed], radius=1)
    assert seed in n1
    n0 = neighbours(inp, planted, [seed], radius=0)
    assert n0 == {seed}


def test_score_helper_matches_validate() -> None:
    inp, planted = _instance()
    hard, soft, breakdown = score(inp, planted)
    assert hard == 100 and 0 <= soft <= 100
    assert sum(breakdown.values()) == sum(v.penalty for v in validate(inp, planted) if not v.hard)
