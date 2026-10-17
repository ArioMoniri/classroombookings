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


# ------------------------------------------------------------------ round-3 R3-M-01: published classes are kept


def _fri(eid: int, start: int, dur: int, rooms: tuple[int, ...]) -> Assignment:
    return Assignment(eid, 5, start, start + dur - 1, rooms, frozenset(W))


def _r3_input(syb_priority: int = 0) -> sm.SolverInput:
    """The Güz pair of R3-M-01: NUT 121 (planner-locked to C501, Fri 11:50-13:20, published) and SYB 111 (planner-locked
    to C501, Fri 10:10-12:30, never placed) hold one room at overlapping times; NUT 404 (published, Fri all day) and
    NUT 402 (newcomer) share the 4th-year cohort; PSY 277 is the one edited section (its priority raised)."""
    c501, d106, a308 = room(44, "C501", 72), room(60, "D106", 60), room(20, "A308", 42)
    nut121 = event(2183, size=40, weeks=W, day=5, start=5, label="NUT 121", locked=_fri(2183, 5, 2, (44,)))
    syb111 = event(2290, size=57, duration=3, weeks=W, day=5, start=3, label="SYB 111", locked=_fri(2290, 3, 3, (44,)))
    syb111 = sm.Event(**{**syb111.__dict__, "priority": syb_priority})
    nut404 = event(2498, size=55, duration=11, weeks=W, day=5, start=1, label="NUT 404", cohort_keys=("PROG:NUT:4",))
    nut402 = event(2497, size=55, duration=11, weeks=W, day=5, start=1, label="NUT 402", cohort_keys=("PROG:NUT:4",))
    psy = event(1602, size=42, duration=3, weeks=W, day=1, start=3, label="PSY 277", priority=1)
    return make_input(
        (c501, d106, a308),
        (nut121, syb111, nut404, nut402, psy),
        weeks=W,
        workers=1,
        best_effort=True,
        trust_locked_rooms=True,
        fixed_conflicts_as_warnings=False,
    )


def _r3_rows() -> tuple[list[Assignment], list[Assignment]]:
    published = [_fri(2183, 5, 2, (44,)), _fri(2498, 1, 11, (60,)), Assignment(1602, 1, 3, 5, (20,), frozenset(W))]
    # what the re-solve returned: the newcomers took the published classes' cells (equal priority)
    child = [_fri(2290, 3, 3, (44,)), _fri(2497, 1, 11, (60,)), Assignment(1602, 1, 3, 5, (20,), frozenset(W))]
    return published, child


def _result(rows: list[Assignment]) -> sm.SolverResult:
    diags = [
        sm.Diagnosis([2183], ["room_pin"], "NUT 121 lost the lock clash", [], "error", "unplaced", {"policy": {}}),
        sm.Diagnosis([2498], ["no_cohort_overlap"], "NUT 404 cohort", [], "error", "unplaced", {"policy": {}}),
    ]
    stats = {"placed": 3, "unplaced": 2, "events_total": 5, "unplaced_ids": [2183, 2498], "partial": True}
    return sm.SolverResult("INFEASIBLE", list(rows), 100, 90, {}, diags, stats)


def test_section_priority_resolve_never_gives_a_published_class_to_an_equal_priority_newcomer() -> None:
    """R3-M-01: one section-priority edit (PSY 277) and the re-solve gave planner-locked, published NUT 121 to SYB 111
    and NUT 404 to NUT 402 (both newcomers, equal priority).  The published classes go back; the newcomers are listed
    unplaced with the reason ``published_kept`` naming the class that kept the cell."""
    inp = _r3_input()
    published, child = _r3_rows()
    res = _result(child)
    out = rp.keep_published(inp, published, res, scope={1602})
    placed = {a.event_id for a in res.assignments}
    assert placed == {2183, 2498, 1602}
    assert sorted(out["restored"]) == [2183, 2498] and sorted(out["evicted"]) == [2290, 2497]
    assert res.hard_score == 100
    assert res.stats["placed"] == 3 and sorted(res.stats["unplaced_ids"]) == [2290, 2497]
    lost = {d.event_ids[0]: d for d in res.diagnoses if d.code == "unplaced" and d.severity == "error"}
    assert set(lost) == {2290, 2497}
    assert lost[2290].params["policy"]["reason"] == "published_kept" and lost[2290].params["policy"]["winners"] == [2183]
    assert lost[2497].params["policy"]["winners"] == [2498]
    # nothing else moved: the edited class keeps its cell
    assert next(a for a in res.assignments if a.event_id == 1602) == published[2]


def test_a_higher_priority_newcomer_keeps_the_cell_it_won() -> None:
    inp = _r3_input(syb_priority=1)
    published, child = _r3_rows()
    res = _result(child)
    out = rp.keep_published(inp, published, res, scope={1602})
    placed = {a.event_id for a in res.assignments}
    assert 2290 in placed and 2183 not in placed  # SYB 111 has the higher priority: the loss stands (and is named)
    assert out["restored"] == [2498] and out["evicted"] == [2497]


def test_the_edited_scope_may_take_a_published_cell() -> None:
    """A class of the edited scope that took a published cell keeps it: the edit is the user's intent."""
    inp = _r3_input()
    published, child = _r3_rows()
    res = _result(child)
    out = rp.keep_published(inp, published, res, scope={1602, 2290})
    placed = {a.event_id for a in res.assignments}
    assert 2290 in placed and 2183 not in placed and out["restored"] == [2498]


def test_policy_names_published_kept_in_a_lock_clash_at_equal_priority() -> None:
    from app.solver import policy

    inp = _r3_input()
    inp = sm.SolverInput(**{**inp.__dict__, "previous": (_fri(2183, 5, 2, (44,)),)})
    by_id = {e.id: e for e in inp.events}
    r = policy.loss_reason(inp, by_id[2290], [2183], by_id)
    assert r["reason"] == "published_kept" and r["winners"] == [2183]
