"""Round-2 T-R2-34 (R2-M-03 / R1-S-04): the moderation re-solve's pure helpers on week-segmented placements.

No database: the stored rows of a term run (``stats.solver_assignments``) keep one row per room set of a class whose
room changes in some weeks; the re-solve must start from all of them, judge the published cells segment by segment
and give every move outside the edit a cause.
"""

from __future__ import annotations

import importlib

from app.models import ScheduleRun
from app.services import moderation as m
from app.solver import model as sm
from app.solver.model import Assignment, Block

from tests.solver.conftest import event, make_input, room

rp = importlib.import_module("app.solver.repair")  # the package re-exports the function under this name

W = (1, 2, 3)


def _inp() -> sm.SolverInput:
    rooms = (room(1, "A101", 60), room(2, "B201", 60), room(3, "B202", 60))
    lock = Assignment(1, 1, 1, 2, (1,), frozenset(W))
    return make_input(
        rooms,
        (
            event(1, size=50, weeks=W, day=1, start=1, label="ACU 141", locked=lock),
            event(2, size=40, weeks=W, day=2, start=1, label="PSY 277"),
        ),
        weeks=W,
        blocks=(Block(1, 1, 1, 1, 2),),
        workers=1,
        best_effort=True,
        trust_locked_rooms=True,
    )


def _run_with_rows(rows: list[list[object]]) -> ScheduleRun:
    return ScheduleRun(term_id=1, kind="COURSE", status="FEASIBLE_PARTIAL", stats={"solver_assignments": rows})


def test_base_assignments_keep_every_week_segment_row() -> None:
    inp = _inp()
    base = _run_with_rows(
        [
            [1, 1, 1, 2, [2], [1], None],  # the blocked week in B201
            [1, 1, 1, 2, [1], [2, 3], None],  # the lock in the other weeks
            [1, 1, 1, 2, [1], [2, 3], None],  # a duplicate row is read once
            [2, 2, 1, 2, [1], [1, 2, 3], None],
            [9, 2, 1, 2, [1], [1, 2, 3], None],  # an event the child no longer has
        ]
    )
    cur = m.base_assignments(inp, base)
    assert [(a.event_id, a.room_ids, sorted(a.weeks)) for a in cur] == [
        (1, (2,), [1]),
        (1, (1,), [2, 3]),
        (2, (1,), [1, 2, 3]),
    ]


def test_violating_is_judged_per_segment_not_on_a_flattened_room() -> None:
    inp = _inp()
    current = [
        Assignment(1, 1, 1, 2, (2,), frozenset({1})),
        Assignment(1, 1, 1, 2, (1,), frozenset({2, 3})),
        Assignment(2, 2, 1, 2, (1,), frozenset(W)),
    ]
    view = rp.segment_view(inp, current)
    assert m.violating(view) == set()
    # the room of the moved week is blocked by a booking added since: that segment, and only it, is in conflict
    inp2 = make_input(inp.rooms, inp.events, weeks=W, blocks=(*inp.blocks, Block(2, 1, 1, 1, 2)), best_effort=True)
    view2 = rp.segment_view(inp2, current)
    bad = m.violating(view2)
    assert bad and all(view2.root_of(s) == 1 for s in bad) and 1 not in bad


def test_move_cause_names_the_freed_neighbour_or_the_broken_cell() -> None:
    rep = {"freed_by": {"7": {"cause": "neighbour", "of": 3}, "8": {"cause": "base_conflict"}}}
    labels = {3: "PSY 277", 7: "ACU 96AA", 8: "ACU 1F2C"}
    c7 = m.move_cause(rep, 7, {}, labels)
    assert c7 is not None and c7["code"] == "freed_neighbour" and c7["request_id"] == 3
    assert "PSY 277" in c7["text"]["tr"] and "ACU 96AA" in c7["text"]["tr"] and c7["text"]["en"]
    c8 = m.move_cause(rep, 8, {}, labels)
    assert c8 is not None and c8["code"] == "base_conflict" and c8["text"]["tr"] and c8["text"]["en"]
    assert m.move_cause(rep, 9, {}, labels) is None
    # a joint lecture member is looked up through its solver event
    c = m.move_cause(rep, 70, {70: 7}, labels)
    assert c is not None and c["code"] == "freed_neighbour"
