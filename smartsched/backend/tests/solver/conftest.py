"""Solver test fixtures.  Runnable with ``cd smartsched/backend && python -m pytest tests/solver -q``."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.solver.model import Assignment, Event, Room, SolverInput  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: long-running scale tests (enable with SMARTSCHED_SLOW=1)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("SMARTSCHED_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="slow test; set SMARTSCHED_SLOW=1 to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


def room(
    id: int,
    code: str,
    capacity: int,
    building: str | None = None,
    tags: tuple[str, ...] = (),
    exam_capacity: int | None = None,
) -> Room:
    return Room(
        id=id,
        code=code,
        capacity=capacity,
        exam_capacity=capacity // 2 if exam_capacity is None else exam_capacity,
        building=building or code[0],
        tags=frozenset(tags),
    )


def event(
    id: int,
    size: int = 30,
    duration: int = 2,
    *,
    kind: str = "course",
    label: str | None = None,
    weeks: tuple[int, ...] | None = None,
    day: int | None = None,
    start: int | None = None,
    allowed_days: tuple[int, ...] = (),
    earliest: int = 1,
    latest: int = 18,
    **kw: object,
) -> Event:
    fields: dict[str, object] = dict(
        id=id,
        kind=kind,
        label=label or f"E{id}",
        size=size,
        duration=duration,
        weeks=frozenset(weeks if weeks is not None else range(1, 15)),
        fixed_day=day,
        fixed_start=start,
        allowed_days=frozenset(allowed_days),
        earliest_start=earliest,
        latest_end=latest,
    )
    for k, v in kw.items():
        if k in (
            "required_tags",
            "forbidden_tags",
            "required_room_ids",
            "forbidden_room_ids",
            "cohort_keys",
            "instructor_keys",
        ):
            v = frozenset(v)  # type: ignore[arg-type]
        elif k == "preferred_room_ids":
            v = tuple(v)  # type: ignore[arg-type]
        fields[k] = v
    return Event(**fields)  # type: ignore[arg-type]


def make_input(
    rooms: tuple[Room, ...], events: tuple[Event, ...], constraints: tuple = (), **kw: object
) -> SolverInput:
    defaults: dict[str, object] = dict(
        days=(1, 2, 3, 4, 5), periods_per_day=18, weeks=tuple(range(1, 15)), time_limit_s=10.0, seed=0, workers=2
    )
    defaults.update(kw)
    return SolverInput(rooms=rooms, events=events, constraints=constraints, **defaults)  # type: ignore[arg-type]


def assigned(result_assignments: list[Assignment], event_id: int) -> Assignment:
    for a in result_assignments:
        if a.event_id == event_id:
            return a
    raise AssertionError(f"event {event_id} not assigned")


@pytest.fixture
def small_rooms() -> tuple[Room, ...]:
    return (
        room(1, "A101", 58),
        room(2, "A204", 156, tags=("AMPHI",)),
        room(3, "B207", 60, tags=("PC", "LAB")),
        room(4, "A201", 96, tags=("TIP",)),
        room(5, "C301", 72),
    )
