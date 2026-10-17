"""Relaxation policy (user decision 2026-10-15, ``app/solver/policy.py``): when not every request can be
placed, ``lock_first`` keeps the planner's trusted locks, then the coordinator priority, then the most
classes; ``most_classes_first`` keeps the most classes first.  Each rule: a feasible case (the policy changes
nothing), an infeasible case with the named loser and reason, a soft-weight case (soft terms never decide who
is placed), lock clashes (policy default Q5), no first-come tie-break (Q3), staged solves and determinism."""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.solver import policy
from app.solver.build import prepare
from app.solver.cpsat import solve
from app.solver.diagnose import static_check
from app.solver.model import Assignment, Constraint, SolverInput
from app.solver.repair import validate
from app.solver.serialization import input_from_dict, input_to_dict
from tests.solver.conftest import assigned, event, make_input, room

W1 = (3,)
OK = ("OPTIMAL", "FEASIBLE")


def _lock(eid: int, rooms: tuple[int, ...], day: int = 1, start: int = 1, dur: int = 2) -> Assignment:
    return Assignment(eid, day, start, start + dur - 1, rooms, frozenset(W1))


def _unplaced(res) -> list[int]:  # type: ignore[no-untyped-def]
    return sorted(res.stats.get("unplaced_ids") or [])


def _reason(res, eid: int) -> dict:  # type: ignore[no-untyped-def,type-arg]
    d = next(d for d in res.diagnoses if d.code == "unplaced" and d.event_ids == [eid])
    return d.params["policy"]  # type: ignore[no-any-return]


def _hard_ok(inp: SolverInput, res) -> bool:  # type: ignore[no-untyped-def]
    placed = {a.event_id for a in res.assignments}
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed), best_effort=False)
    return not [v for v in validate(sub, res.assignments) if v.hard]


def _lock_vs_two(pol: str) -> SolverInput:
    """One room.  The planner's lock holds it P1-P4; two unlocked classes need it at P1-P2 and P3-P4."""
    rooms = (room(1, "A101", 60),)
    lock = event(1, size=40, duration=4, weeks=W1, day=1, start=1, label="PHAR 114 §2", locked=_lock(1, (1,), dur=4))
    a = event(2, size=40, weeks=W1, day=1, start=1, label="MAT 112")
    b = event(3, size=40, weeks=W1, day=1, start=3, label="FIZ 101")
    return make_input(
        rooms, (lock, a, b), weeks=W1, best_effort=True, trust_locked_rooms=True, relaxation_policy=pol, workers=1
    )


# --------------------------------------------------------------------------- locks first vs most classes


def test_lock_first_keeps_the_lock_most_classes_first_keeps_two_classes() -> None:
    inp = _lock_vs_two("lock_first")
    res = solve(inp)
    assert res.status == "INFEASIBLE" and res.stats["partial"] and _hard_ok(inp, res)
    assert _unplaced(res) == [2, 3] and assigned(res.assignments, 1).room_ids == (1,)
    assert res.hard_score == 100
    for eid in (2, 3):
        r = _reason(res, eid)
        assert r["policy"] == "lock_first" and r["reason"] == "locked_row_kept" and r["winners"] == [1]
    msg = next(d.message for d in res.diagnoses if d.code == "unplaced" and d.event_ids == [2])
    assert "locked row kept: PHAR 114 §2" in msg
    assert res.stats["policy_tiers"]["policy"] == "lock_first"

    alt = replace(inp, relaxation_policy="most_classes_first")
    res2 = solve(alt)
    assert _unplaced(res2) == [1] and _hard_ok(alt, res2) and res2.hard_score == 100
    r = _reason(res2, 1)
    assert r["policy"] == "most_classes_first" and r["reason"] == "most_classes" and set(r["winners"]) == {2, 3}


def test_feasible_instance_is_identical_under_both_policies() -> None:
    rooms = (room(1, "A101", 60), room(2, "A102", 60))
    lock = event(1, duration=4, weeks=W1, day=1, start=1, locked=_lock(1, (1,), dur=4))
    a = event(2, weeks=W1, day=1, start=1, priority=5)
    b = event(3, weeks=W1, day=1, start=3, priority=-3)
    base = make_input(rooms, (lock, a, b), weeks=W1, best_effort=True, trust_locked_rooms=True, workers=1)
    first = solve(base)
    second = solve(replace(base, relaxation_policy="most_classes_first"))
    assert first.status in OK and second.status in OK
    assert first.assignments == second.assignments and len(first.assignments) == 3


def test_without_best_effort_nothing_is_relaxed_silently() -> None:
    inp = replace(_lock_vs_two("lock_first"), best_effort=False)
    res = solve(inp)
    assert res.status == "INFEASIBLE" and res.assignments == []
    assert any(d.severity == "error" and d.code for d in res.diagnoses)


# --------------------------------------------------------------------------- coordinator priority


def test_higher_priority_wins_one_room_under_both_policies() -> None:
    rooms = (room(1, "A101", 100),)
    hi = event(1, size=20, weeks=W1, day=1, start=1, label="NRS 204", priority=5)
    lo = event(2, size=90, weeks=W1, day=1, start=1, label="ING 302")  # bigger: the old tie-break kept it
    for pol in policy.POLICIES:
        inp = make_input(rooms, (hi, lo), weeks=W1, best_effort=True, relaxation_policy=pol, workers=1)
        res = solve(inp)
        assert _unplaced(res) == [2] and _hard_ok(inp, res), pol
        r = _reason(res, 2)
        assert r["winners"] == [1]
        assert r["reason"] == ("lower_priority" if pol == "lock_first" else "most_classes")
    # equal priority: the larger class is kept (no first-come tie-break: the row order does not matter)
    for order in ((replace(hi, priority=0), lo), (lo, replace(hi, priority=0))):
        res = solve(make_input(rooms, order, weeks=W1, best_effort=True, workers=1))
        assert _unplaced(res) == [1]


def test_priority_beats_the_count_under_lock_first_only() -> None:
    """A priority-3 class competes with two priority-0 classes (P1-P2 and P3-P4) for the only room."""
    rooms = (room(1, "A101", 60),)
    hi = event(1, duration=4, weeks=W1, day=1, start=1, label="BME 528", priority=3)
    a = event(2, weeks=W1, day=1, start=1)
    b = event(3, weeks=W1, day=1, start=3)
    inp = make_input(rooms, (hi, a, b), weeks=W1, best_effort=True, workers=1)
    res = solve(inp)
    assert _unplaced(res) == [2, 3] and _reason(res, 2)["reason"] == "lower_priority"
    res2 = solve(replace(inp, relaxation_policy="most_classes_first"))
    assert _unplaced(res2) == [1] and _reason(res2, 1)["reason"] == "most_classes"


def test_soft_weights_never_decide_who_is_placed() -> None:
    """A huge room-preference weight for the losing class changes nothing about the placement (soft terms
    only order the placed events' rooms in phase 2)."""
    inp = _lock_vs_two("lock_first")
    events = tuple(replace(e, preferred_room_ids=(1,)) if e.id == 2 else e for e in inp.events)
    heavy = replace(
        inp,
        events=events,
        constraints=(Constraint("room_preference", {}, hard=False, weight=1000),),
        weights={"room_preference": 10_000},
    )
    res = solve(heavy)
    assert _unplaced(res) == [2, 3] and _hard_ok(heavy, res)


# --------------------------------------------------------------------------- lock clashes (Q5)


def _two_locks(p1: int, p2: int, *, swap: bool = False) -> SolverInput:
    rooms = (room(1, "B204", 60),)
    x = event(11, size=30, weeks=W1, day=5, start=3, label="BME 528 §1", locked=_lock(11, (1,), 5, 3), priority=p1)
    y = event(12, size=30, weeks=W1, day=5, start=3, label="RAD 282 §1", locked=_lock(12, (1,), 5, 3), priority=p2)
    evs = (y, x) if swap else (x, y)
    return make_input(rooms, evs, weeks=W1, best_effort=True, trust_locked_rooms=True, workers=1)


def test_lock_clash_keeps_the_higher_priority_and_names_the_loser() -> None:
    inp = _two_locks(0, 4)
    pre = next(d for d in static_check(prepare(inp)) if d.code == "locked_overlap")
    assert pre.params["keeps"] == 12 and pre.params["priorities"] == {"11": 0, "12": 4}
    assert "a run keeps RAD 282 §1 (#12) (higher priority)" in pre.message
    res = solve(inp)
    assert _unplaced(res) == [11] and assigned(res.assignments, 12).room_ids == (1,) and _hard_ok(inp, res)
    r = _reason(res, 11)
    assert r["reason"] == "lock_clash_priority" and r["winners"] == [12]
    # the other way round
    res = solve(_two_locks(4, 0))
    assert _unplaced(res) == [12] and _reason(res, 12)["reason"] == "lock_clash_priority"


def test_equal_priority_lock_clash_does_not_depend_on_row_order() -> None:
    first = solve(_two_locks(0, 0))
    second = solve(_two_locks(0, 0, swap=True))
    assert _unplaced(first) == _unplaced(second) and len(_unplaced(first)) == 1
    loser = _unplaced(first)[0]
    assert _reason(first, loser)["reason"] == "lock_clash_tie"
    pre = next(d for d in static_check(prepare(_two_locks(0, 0))) if d.code == "locked_overlap")
    assert pre.params["keeps"] is None and "equal priority" in pre.message


# --------------------------------------------------------------------------- tiers, stages, determinism


def test_cost_tiers_and_groups() -> None:
    inp = _lock_vs_two("lock_first")
    ts = policy.tiers(inp)
    assert [t.name for t in ts] == ["locks", "requests", "weeks"]
    assert policy.cost(inp, {2, 3}) > policy.cost(inp, {1})  # a lost lock outweighs two classes
    alt = replace(inp, relaxation_policy="most_classes_first")
    assert [t.name for t in policy.tiers(alt)] == ["requests", "weeks", "locks"]
    assert policy.better(alt, {2, 3}, {1})
    assert len(policy.objective_groups(ts)) == 1
    prio = replace(inp, events=tuple(replace(e, priority=e.id) for e in inp.events))
    assert [t.name for t in policy.tiers(prio)] == ["locks", "priority:3", "priority:2", "priority:1", "weeks"]
    assert policy.policy_name("typo") == "lock_first" and policy.clamp_priority(999) == policy.PRIORITY_MAX


def test_staged_solve_gives_the_lexicographic_optimum(monkeypatch: pytest.MonkeyPatch) -> None:
    rooms = (room(1, "A101", 60),)
    hi = event(1, duration=4, weeks=W1, day=1, start=1, priority=3)
    a = event(2, weeks=W1, day=1, start=1, priority=1)
    b = event(3, weeks=W1, day=1, start=3)
    inp = make_input(rooms, (hi, a, b), weeks=W1, best_effort=True, workers=1)
    single = solve(inp)
    monkeypatch.setattr(policy, "SINGLE_OBJECTIVE_LIMIT", 3)  # every tier its own stage
    staged = solve(inp)
    assert staged.stats.get("relax_stages", 0) >= 3 and "relax_stages" not in single.stats
    assert _unplaced(staged) == _unplaced(single) == [2, 3] and _hard_ok(inp, staged)


def test_deterministic_mode_is_bit_identical_with_priorities() -> None:
    rooms = (room(1, "A101", 60), room(2, "A102", 40))
    evs = tuple(
        event(i, size=30 + (i % 3) * 10, weeks=W1, day=1 + i % 2, start=1 + (i % 4) * 2, priority=i % 3)
        for i in range(1, 15)
    )
    inp = make_input(rooms, evs, weeks=W1, best_effort=True, workers=1, time_limit_s=10.0)
    a, b = solve(inp), solve(inp)
    assert a.assignments == b.assignments and a.stats["unplaced_ids"] == b.stats["unplaced_ids"]
    assert a.stats["deterministic"] is True and _hard_ok(inp, a)


def test_serialization_round_trip_keeps_priority_and_policy() -> None:
    base = _lock_vs_two("most_classes_first")
    inp = replace(base, events=tuple(replace(e, priority=7) for e in base.events))
    back = input_from_dict(input_to_dict(inp))
    assert back.relaxation_policy == "most_classes_first" and {e.priority for e in back.events} == {7}


# --------------------------------------------------------------------------- accessibility vs a lock (Q4)


def test_a_lock_never_overrides_an_accessibility_need() -> None:
    """Policy Q4: the planner's lock into a room without step-free access is a named static error
    (``lock_accessibility``), never a kept room with a warning; an accessible lock is fine; other missing tags
    of a trusted lock stay warnings (D1)."""
    rooms = (room(1, "C602", 60), room(2, "A106", 60, tags=("ACCESSIBLE",)))
    need = event(1, weeks=W1, day=2, start=4, required_tags={"ACCESSIBLE"}, locked=_lock(1, (1,), 2, 4))
    inp = make_input(rooms, (need,), weeks=W1, trust_locked_rooms=True, workers=1)
    pre = static_check(prepare(inp))
    d = next(d for d in pre if d.code == "lock_accessibility")
    assert d.severity == "error" and d.event_ids == [1] and "accessibility" in d.message
    assert not any(x.code == "trusted_lock_tags" for x in pre)
    res = solve(inp)
    assert res.status == "INFEASIBLE" and res.assignments == []
    # validate() of a manual edit refuses it too (the trusted-lock waiver does not cover it)
    assert [v for v in validate(inp, [need.locked]) if v.hard and v.kind == "room_tags"]  # type: ignore[list-item]
    ok = replace(need, locked=_lock(1, (2,), 2, 4))
    assert solve(replace(inp, events=(ok,))).status in OK
    pc = replace(need, required_tags=frozenset({"PC"}))
    warn = static_check(prepare(replace(inp, events=(pc,))))
    assert any(x.code == "trusted_lock_tags" for x in warn) and not any(x.severity == "error" for x in warn)


# ------------------------------------------------------------------ round-2 T-R2-34: the published timetable wins ties


def _tie_input(previous: tuple[Assignment, ...]) -> SolverInput:
    """One room, two equal-priority classes at the same fixed time: only one can be placed."""
    rooms = (room(1, "A101", 60),)
    a = event(1, size=40, weeks=W1, day=1, start=1, label="BP 127 §1")
    b = event(2, size=50, weeks=W1, day=1, start=1, label="ACU 314")
    return make_input(rooms, (a, b), weeks=W1, best_effort=True, workers=1, time_limit_s=5.0, previous=previous)


def test_a_previously_placed_class_keeps_its_cell_against_a_newcomer_at_equal_priority() -> None:
    """R2-M-03: BP 127 §1 (placed in the published run) lost its room to ACU 314 (never placed) at equal priority
    because the tie went to the larger class.  A re-solve keeps the published class; the newcomer's loss says so."""
    inp = _tie_input((_lock(1, (1,)),))
    res = solve(inp)
    assert [a.event_id for a in res.assignments] == [1] and res.hard_score == 100
    reason = _reason(res, 2)
    assert reason["reason"] == "published_kept" and reason["winners"] == [1]
    # and the other way round: the previous placement, not the size or the id, decides
    flipped = solve(_tie_input((_lock(2, (1,)),)))
    assert [a.event_id for a in flipped.assignments] == [2]
    assert _reason(flipped, 1)["reason"] == "published_kept"
    # the tier sits after the locks and the counts, before the event-weeks
    tiers = policy.describe(inp)["tiers"]
    assert tiers.index("requests") < tiers.index("previous") < tiers.index("weeks")


def test_previous_tier_never_beats_a_lock_a_priority_or_the_count() -> None:
    inp = _tie_input((_lock(1, (1,)),))
    # a higher coordinator priority on the newcomer still wins
    prio = replace(inp, events=(inp.events[0], replace(inp.events[1], priority=5)))
    assert [a.event_id for a in solve(prio).assignments] == [2]
    # a trusted planner lock on the newcomer still wins
    locked = replace(inp, events=(inp.events[0], replace(inp.events[1], locked=_lock(2, (1,)))))
    assert [a.event_id for a in solve(locked).assignments] == [2]
    # the policy cost ranks a placement keeping the published class ahead of one that does not
    assert policy.cost(inp, [1]) < policy.cost(inp, [2])
    assert "previous" in policy.describe(inp)["tiers"]
    # without a previous timetable the tier is absent and nothing changes
    assert "previous" not in policy.describe(_tie_input(()))["tiers"]
