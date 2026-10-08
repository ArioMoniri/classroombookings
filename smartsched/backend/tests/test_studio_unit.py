"""Pure parts of the studio: ``apply_draft`` on a hand-made SolverInput (exclusions in merged lectures,
pins, per-draft rule switches, built-ins honoured by CP-SAT) and the run-time estimate."""

from __future__ import annotations

from app.services.studio import NO_KEY, apply_draft, estimate_seconds
from app.solver import model as sm

ROOMS = (
    sm.Room(1, "A101", 60, 30, "A", frozenset()),
    sm.Room(2, "A204", 156, 74, "A", frozenset()),
    sm.Room(3, "A201", 96, 48, "A", frozenset({"TIP"})),
)


def _ev(eid: int, label: str, size: int, start: int, ins: str = "INS:1", cohort: str = "PROG:psikoloji:Y1") -> sm.Event:
    return sm.Event(
        id=eid,
        kind="course",
        label=label,
        size=size,
        duration=2,
        weeks=frozenset({1}),
        fixed_day=1,
        fixed_start=start,
        allowed_days=frozenset({1}),
        forbidden_tags=frozenset({"TIP"}),
        cohort_keys=frozenset({cohort}),
        instructor_keys=frozenset({ins}),
    )


def _inp(*events: sm.Event, constraints: tuple[sm.Constraint, ...] = ()) -> sm.SolverInput:
    return sm.SolverInput(rooms=ROOMS, events=events, constraints=constraints, weeks=(1,), time_limit_s=5, workers=1)


def test_exclusions_shrink_merged_lectures_and_drop_whole_events():
    merged = _ev(10, "FİZ 111 §1", 150, 1)
    single = _ev(20, "PSİ 155", 40, 4, ins="INS:2", cohort="PROG:psikoloji:Y2")
    members = {10: [10, 11, 12], 20: [20]}
    sizes = {10: 50, 11: 60, 12: 40}
    out, mem, dropped = apply_draft(_inp(merged, single), members, {"excluded_event_ids": [11, 20]}, sizes)
    assert [e.id for e in out.events] == [10] and dropped == [20]
    assert mem == {10: [10, 12]} and out.events[0].size == 90
    # excluding the head keeps the event (id = old head) for the remaining member
    out, mem, _ = apply_draft(_inp(merged), members, {"excluded_event_ids": [10]}, sizes)
    assert mem == {10: [11, 12]} and out.events[0].size == 100


def test_pins_rule_switches_and_overrides():
    a, b = _ev(1, "MAT 112", 50, 1), _ev(2, "MAT 102", 50, 5, ins="INS:9", cohort="PROG:x:Y1")
    rules = (
        sm.Constraint("room_preference", {"event_ids": [1], "room_ids": [2]}, False, 5, 101),
        sm.Constraint("day_window", {"event_ids": [2], "latest": 11}, True, 1, 102),
    )
    snap = {
        "pins": [{"event_id": 1, "room_ids": [2]}, {"event_id": 2, "day": 3, "start_period": 7}],
        "disabled_rule_ids": [101],
        "rule_overrides": {"102": {"hardness": "soft", "weight": 8}},
    }
    out, _, _ = apply_draft(_inp(a, b, constraints=rules), {1: [1], 2: [2]}, snap)
    ea, eb = out.events
    assert ea.required_room_ids == frozenset({2}) and ea.forbidden_tags == frozenset()
    assert (eb.fixed_day, eb.fixed_start, eb.allowed_days) == (3, 7, frozenset({3}))
    assert [(c.id, c.hard, c.weight) for c in out.constraints] == [(102, False, 8)]


def test_disabled_instructor_overlap_is_honoured_by_cpsat():
    from app.solver.cpsat import solve

    # two classes of one instructor, fixed at the same time in different programmes -> infeasible
    a = _ev(1, "MAT 112 §1", 50, 3, ins="INS:7", cohort="PROG:a:Y1")
    b = _ev(2, "MAT 112 §2", 50, 3, ins="INS:7", cohort="PROG:b:Y1")
    by_ins = sm.Constraint("room_preference", {"instructors": ["INS:7"], "room_ids": [1]}, False, 5, 7)
    inp = _inp(a, b, constraints=(by_ins,))
    assert solve(inp).status == "INFEASIBLE"
    out, _, _ = apply_draft(inp, {1: [1], 2: [2]}, {"disabled_builtin_kinds": ["no_instructor_overlap"]})
    assert all(not e.instructor_keys for e in out.events)
    # the instructor-selected rule was frozen into explicit event ids before the keys were cleared
    pref = next(c for c in out.constraints if c.id == 7)
    assert pref.params == {"room_ids": [1], "event_ids": [1, 2]}
    assert any(c.kind == "no_instructor_overlap" and c.params == {"keys": [NO_KEY]} for c in out.constraints)
    res = solve(out)
    assert res.status in {"FEASIBLE", "OPTIMAL"} and res.hard_score == 100


def test_disabled_cohort_overlap_and_capacity():
    from app.solver.cpsat import solve

    a = _ev(1, "PSİ 101", 50, 3, ins="INS:1")
    b = _ev(2, "PSİ 102", 50, 3, ins="INS:2")  # same cohort, same time
    big = _ev(3, "BME 419", 200, 8, ins="INS:3", cohort="PROG:bme:Y4")  # no room seats 200
    inp = _inp(a, b, big)
    assert solve(inp).status == "INFEASIBLE"
    out, _, _ = apply_draft(
        inp, {1: [1], 2: [2], 3: [3]}, {"disabled_builtin_kinds": ["no_cohort_overlap", "capacity"]}
    )
    assert all(e.cohort_keys for e in out.events)  # kept for selectors / exam rules
    res = solve(out)
    assert res.status in {"FEASIBLE", "OPTIMAL"} and len(res.assignments) == 3


def test_estimate_words():
    small = estimate_seconds(300, 60, 14, 60)
    assert 5 <= small["low"] < small["high"] <= 60 and small["words"]["en"]
    big = estimate_seconds(1300, 61, 14, 300)
    assert 50 <= big["low"] <= 120 and big["high"] <= 450 and "minute" in big["words"]["en"]
    assert "dakika" in big["words"]["tr"]
    assert estimate_seconds(0, 10, 1, 60)["high"] == 1
