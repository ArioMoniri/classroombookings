"""R4 of the planner comparison: large classes without a definitive room set may use several rooms of one
building when no single free room fits (``solver_bridge.allow_large_splits``, run param
``split_large_classes``, default on)."""

from __future__ import annotations

from app.services.solver_bridge import MODE_DEFAULTS, allow_large_splits
from app.solver import model as sm

# rooms of the room master (tests/fixtures/room_master.csv)
ROOMS = (
    sm.Room(1, "A204", 156, 74, "A", frozenset()),
    sm.Room(2, "A203", 148, 148, "A", frozenset({"TIP"})),
    sm.Room(3, "C201", 126, 60, "C", frozenset()),
    sm.Room(4, "C301", 72, 35, "C", frozenset()),
    sm.Room(5, "C302", 72, 35, "C", frozenset()),
    sm.Room(6, "C401", 72, 35, "C", frozenset()),
    sm.Room(7, "B202", 64, 32, "B", frozenset()),
    sm.Room(8, "B203", 64, 32, "B", frozenset()),
)


def _ev(eid: int, size: int, **kw) -> sm.Event:  # type: ignore[no-untyped-def]
    base = dict(
        id=eid,
        kind="course",
        label=f"E{eid}",
        size=size,
        duration=2,
        weeks=frozenset({3}),
        fixed_day=1,
        fixed_start=4,
        allowed_days=frozenset({1}),
        forbidden_tags=frozenset({"TIP"}),
    )
    base.update(kw)
    return sm.Event(**base)  # type: ignore[arg-type]


def _lock(eid: int, room: int) -> sm.Event:
    return _ev(eid, 50, locked=sm.Assignment(eid, 1, 4, 5, (room,), frozenset({3})))


def test_split_is_on_by_default() -> None:
    assert MODE_DEFAULTS["split_large_classes"] is True


def test_eng105_like_class_splits_inside_one_building() -> None:
    """ENG 105 §1 (Güz row 11, 85 students, Monday 11:00-12:30): A 204 and C 201 are held by locked classes,
    so no single room fits; two 72-seat C rooms do."""
    events = [_ev(10, 85), _lock(20, 1), _lock(21, 3)]
    out, info = allow_large_splits(events, ROOMS, [])
    eng = out[0]
    assert info == [{"event_id": 10, "label": "E10", "size": 85, "building": "C", "rooms_needed": 2}]
    assert eng.max_rooms == 3  # the rooms needed + one spare
    # every room of another building that cannot seat 85 alone is forbidden: a split stays in C
    assert {7, 8} <= eng.forbidden_room_ids and not {4, 5, 6} & eng.forbidden_room_ids
    assert 1 not in eng.forbidden_room_ids  # A 204 seats the class alone (free in another week segment)
    assert out[1:] == events[1:]  # locks untouched


def test_no_split_when_a_single_room_is_free() -> None:
    out, info = allow_large_splits([_ev(10, 85), _lock(20, 1)], ROOMS, [])
    assert info == [] and out[0].max_rooms == 1  # C 201 (126) is free


def test_blocked_rooms_count_and_other_weeks_do_not() -> None:
    blocks = [sm.Block(1, 3, 1, 3, 6), sm.Block(3, None, 1, 1, 18)]
    out, info = allow_large_splits([_ev(10, 85)], ROOMS, blocks)
    assert info and out[0].max_rooms > 1
    out, info = allow_large_splits([_ev(10, 85)], ROOMS, [sm.Block(1, 4, 1, 3, 6), sm.Block(3, None, 1, 1, 18)])
    assert info == []  # A 204 is blocked in week 4 only; the class meets in week 3


def test_requested_building_wins_and_unseatable_classes_stay() -> None:
    events = [_ev(10, 120, preferred_building="B"), _lock(20, 1), _lock(21, 3)]
    out, info = allow_large_splits(events, ROOMS, [])
    assert info[0]["building"] == "B" and info[0]["rooms_needed"] == 2
    out, info = allow_large_splits([_ev(10, 500), _lock(20, 1)], ROOMS, [])
    assert info == [] and out[0].max_rooms == 1  # no building seats 500 in at most 4 rooms
    locked = _lock(30, 4)
    assert allow_large_splits([locked], ROOMS, [])[0] == [locked]


def test_tags_and_tip_rooms_are_respected() -> None:
    pc = (
        *ROOMS,
        sm.Room(9, "A103", 47, 47, "A", frozenset({"PC"})),
        sm.Room(10, "A104", 47, 47, "A", frozenset({"PC"})),
    )
    out, info = allow_large_splits([_ev(10, 80, required_tags=frozenset({"PC"}))], pc, [])
    assert info[0]["building"] == "A" and out[0].max_rooms == 3
    # A 203 (TIP, 148) never counts as free for a class that may not use TIP rooms
    out, info = allow_large_splits([_ev(10, 140), _lock(20, 1)], ROOMS, [])
    assert info and info[0]["building"] == "C"


def test_split_params_are_run_options() -> None:
    import pytest
    from app.services.run_params import ParamError, clean_client_params

    assert clean_client_params({"split_large_classes": False, "split_max_rooms": 3}) == {
        "split_large_classes": False,
        "split_max_rooms": 3,
    }
    with pytest.raises(ParamError):
        clean_client_params({"split_max_rooms": 20})
    with pytest.raises(ParamError):
        clean_client_params({"split_large_classes": "yes"})
