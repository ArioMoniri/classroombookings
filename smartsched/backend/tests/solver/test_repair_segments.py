"""Round-2 T-R2-34 (R2-M-03 / R1-S-04): a minimal-change repair on a term run whose placements have week segments.

The Güz term run keeps a planner-locked class in its locked room in the weeks that room is free and moves only the
blocked week to another room (``weeksplit``).  A moderation re-solve starts from those stored rows: the repair must
see them as week segments (not flatten them to one room), keep every segment outside the edit's neighbourhood, put
back a chain of moves whose old cells are free as a whole, and record why each freed event was freed.
"""

from __future__ import annotations

import importlib
from dataclasses import replace

from app.solver.model import Assignment, Block, SolverResult
from tests.solver.conftest import event, make_input, room

rp = importlib.import_module("app.solver.repair")  # the package re-exports the function under this name

W = (1, 2, 3)
OK = ("OPTIMAL", "FEASIBLE")


def _rows(assignments: list[Assignment], eid: int) -> list[Assignment]:
    return sorted((a for a in assignments if a.event_id == eid), key=lambda a: min(a.weeks))


def _term_with_blocked_week():
    """A101 is blocked in week 1 at Mon P1-P2; class 1 is locked there, so its week 1 sits in B201 (the Güz case)."""
    rooms = (room(1, "A101", 60), room(2, "B201", 60), room(3, "B202", 60))
    lock = Assignment(1, 1, 1, 2, (1,), frozenset(W))
    locked = event(1, size=50, weeks=W, day=1, start=1, label="ACU 141", locked=lock)
    other = event(2, size=40, weeks=W, day=2, start=1, label="PSY 277")
    third = event(3, size=40, weeks=W, day=2, start=1, label="MBG 101")
    inp = make_input(
        rooms,
        (locked, other, third),
        weeks=W,
        blocks=(Block(1, 1, 1, 1, 2),),
        workers=1,
        time_limit_s=10.0,
        best_effort=True,
        trust_locked_rooms=True,
    )
    current = [
        Assignment(1, 1, 1, 2, (1,), frozenset({2, 3})),  # the locked room in the free weeks
        Assignment(1, 1, 1, 2, (2,), frozenset({1})),  # the blocked week moved to B201 by the term run
        Assignment(2, 2, 1, 2, (1,), frozenset(W)),
        Assignment(3, 2, 1, 2, (2,), frozenset(W)),
    ]
    return inp, current


def test_segment_view_keeps_every_stored_row_of_a_split_class() -> None:
    inp, current = _term_with_blocked_week()
    view = rp.segment_view(inp, current)
    segs = view.segments_of(1)
    assert len(segs) == 2 and 1 in segs
    placed = {a.event_id: a for a in view.current}
    assert placed[1].room_ids == (1,) and placed[1].weeks == frozenset({2, 3})
    seg = next(s for s in segs if s != 1)
    assert placed[seg].room_ids == (2,) and placed[seg].weeks == frozenset({1})
    # nothing of the published timetable breaks a hard rule when it is read as segments
    assert rp.violating_events(view) == set()


def test_repair_after_a_priority_edit_keeps_the_split_class_and_drops_nothing() -> None:
    inp, current = _term_with_blocked_week()
    edited = replace(inp, events=tuple(replace(e, priority=10) if e.id == 2 else e for e in inp.events))
    res = rp.repair(edited, current, [2], time_limit_s=10.0, keep_changed=False, scope={2})
    assert res.status in OK, [d.message for d in res.diagnoses]
    assert res.hard_score == 100
    rep = res.stats["repair"]
    assert rep["dropped"] == [] and rep["hard_violations"] == 0
    # the locked class keeps both of its rows: the lock in weeks 2-3, B201 in the blocked week
    rows = _rows(res.assignments, 1)
    assert [(a.room_ids, set(a.weeks)) for a in rows] == [({2}, {1}), ({1}, {2, 3})] or [
        (set(a.room_ids), set(a.weeks)) for a in rows
    ] == [({2}, {1}), ({1}, {2, 3})]
    assert 1 not in {m["event_id"] for m in rep["moved"]}
    assert rep["freed_by"] == {} or all(int(k) != 1 for k in rep["freed_by"])


def test_repair_frees_only_the_segment_whose_cell_breaks_a_rule_now() -> None:
    """A booking added since blocks B201 in week 1: only that segment is freed and re-placed; the lock stays."""
    inp, current = _term_with_blocked_week()
    inp2 = replace(inp, blocks=(*inp.blocks, Block(2, 1, 1, 1, 2)))
    view = rp.segment_view(inp2, current)
    bad = rp.violating_events(view)
    seg = next(s for s in view.segments_of(1) if s != 1)
    assert bad == {seg}
    res = rp.repair(inp2, current, [2], time_limit_s=10.0, keep_changed=False, scope={2}, free=bad, view=view)
    assert res.status in OK and res.hard_score == 100
    rows = _rows(res.assignments, 1)
    assert {(tuple(a.room_ids), frozenset(a.weeks)) for a in rows} == {
        ((3,), frozenset({1})),
        ((1,), frozenset({2, 3})),
    }
    rep = res.stats["repair"]
    assert rep["dropped"] == []
    # the move of week 1 carries its cause: the published cell broke a rule
    assert {int(k): v for k, v in rep["freed_by"].items()} == {1: {"cause": "base_conflict"}}


def test_moved_diff_compares_week_segment_rows() -> None:
    _inp, current = _term_with_blocked_week()
    assert rp.moved_diff(current, current) == []
    changed = [replace(a, room_ids=(3,)) if a.event_id == 1 and a.weeks == frozenset({1}) else a for a in current]
    diff = rp.moved_diff(current, changed)
    assert [m["event_id"] for m in diff] == [1]
    assert diff[0]["from"]["room_ids"] == [1] and diff[0]["to"]["room_ids"] == [1]  # the main row (most weeks)
    assert [s["room_ids"] for s in diff[0]["from"]["segments"]] == [[2], [1]]
    assert [s["room_ids"] for s in diff[0]["to"]["segments"]] == [[3], [1]]


def test_minimal_change_puts_back_a_cyclic_swap_outside_the_scope() -> None:
    """Two freed neighbours swapped rooms; neither old cell is free alone, both are free together: both go back."""
    rooms = (room(1, "A101", 60), room(2, "A102", 60), room(3, "A103", 60))
    evs = tuple(event(i, size=30, weeks=W, day=1, start=1) for i in (1, 2, 3))
    inp = make_input(rooms, evs, weeks=W, workers=1)
    wk = frozenset(W)
    current = [Assignment(1, 1, 1, 2, (1,), wk), Assignment(2, 1, 1, 2, (2,), wk), Assignment(3, 1, 1, 2, (3,), wk)]
    swapped = [Assignment(1, 1, 1, 2, (2,), wk), Assignment(2, 1, 1, 2, (1,), wk), Assignment(3, 1, 1, 2, (3,), wk)]
    view = rp.segment_view(inp, current)
    result = SolverResult("FEASIBLE", list(swapped), 100, 100, {}, [], {"repair": {}})
    reverted = rp.minimal_change(view, result, scope={3})
    assert reverted == [1, 2]
    assert sorted(result.assignments, key=lambda a: a.event_id) == current


def test_repair_records_why_each_event_was_freed() -> None:
    """The user moved class 1 into class 2's room: 2 is freed as a neighbour of 1 (and says so); 3 is untouched."""
    rooms = (room(1, "A101", 60), room(2, "A102", 60), room(3, "A103", 60))
    evs = tuple(event(i, weeks=W, day=1 if i < 3 else 2, start=1) for i in (1, 2, 3))
    inp = make_input(rooms, evs, weeks=W, workers=1, time_limit_s=5.0, best_effort=True)
    wk = frozenset(W)
    edited = [Assignment(1, 1, 1, 2, (2,), wk), Assignment(2, 1, 1, 2, (2,), wk), Assignment(3, 2, 1, 2, (1,), wk)]
    res = rp.repair(inp, edited, [1], time_limit_s=5.0, keep_changed=True, scope={1}, radius=1)
    assert res.status in OK and res.hard_score == 100
    rep = res.stats["repair"]
    assert rep["changed"] == [1] and rep["freed"] == [2]
    assert {int(k): v for k, v in rep["freed_by"].items()} == {2: {"cause": "neighbour", "of": 1}}
    assert rep["dropped"] == [] and 3 not in rep["freed"]
    assert [m["event_id"] for m in rep["moved"]] == [2]  # 2 gave way; the edit itself is the input
