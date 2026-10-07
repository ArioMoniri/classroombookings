"""Solver contract (frozen, see docs/ARCHITECTURE.md "Solver contract").

Pure dataclasses; no DB, no HTTP.  Period indexes are 1-based and inclusive:
an event with ``start=4`` and ``duration=3`` occupies periods 4, 5 and 6 and its
``Assignment.end`` is 6.  ``Block.end`` is inclusive as well.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


@dataclass(frozen=True)
class Room:
    id: int
    code: str
    capacity: int
    exam_capacity: int
    building: str
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Assignment:
    event_id: int
    day: int
    start: int
    end: int
    room_ids: tuple[int, ...]
    weeks: frozenset[int]
    date: date | None = None


@dataclass(frozen=True)
class Block:
    """A pre-occupied room slot (HAZIRLIK, UZEM, event, CRBS booking ...)."""

    room_id: int
    week: int | None  # None = every week
    day: int
    start: int
    end: int  # inclusive
    label: str = ""


@dataclass(frozen=True)
class Event:
    id: int  # meeting_request.id or exam_request.id
    kind: Literal["course", "exam"]
    label: str  # "MAT 112 §1"
    size: int  # enrolment
    duration: int  # number of consecutive periods
    weeks: frozenset[int]  # weeks in which the event occupies a room (course) / {week} (exam)
    fixed_day: int | None = None  # 1..7
    fixed_start: int | None = None  # period index 1..18
    allowed_days: frozenset[int] = frozenset()  # when day not fixed; empty = all days of the grid
    earliest_start: int = 1
    latest_end: int = 18
    fixed_date: date | None = None  # exams
    required_tags: frozenset[str] = frozenset()  # e.g. {"PC"}
    forbidden_tags: frozenset[str] = frozenset()  # e.g. {"TIP"}
    required_room_ids: frozenset[int] = frozenset()  # hard pin
    preferred_room_ids: tuple[int, ...] = ()  # soft, ordered
    preferred_building: str | None = None
    forbidden_room_ids: frozenset[int] = frozenset()
    min_rooms: int = 1
    max_rooms: int = 1  # exams may split
    cohort_keys: frozenset[str] = frozenset()  # "PROG:Psikoloji:Y1" -> no overlap within key
    instructor_keys: frozenset[str] = frozenset()  # "INS:canonical name"
    same_room_group: str | None = None  # events sharing this key should share room
    locked: Assignment | None = None
    needs_room: bool = True


@dataclass(frozen=True)
class Constraint:
    kind: str
    params: Mapping[str, Any]
    hard: bool
    weight: int = 1
    id: int | None = None


@dataclass(frozen=True)
class SolverInput:
    rooms: tuple[Room, ...]
    events: tuple[Event, ...]
    constraints: tuple[Constraint, ...] = ()
    days: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)
    periods_per_day: int = 18
    weeks: tuple[int, ...] = tuple(range(1, 15))
    blocks: tuple[Block, ...] = ()
    previous: tuple[Assignment, ...] = ()  # for stability objective
    time_limit_s: float = 60.0
    seed: int = 0
    workers: int = 8
    weights: Mapping[str, int] = field(default_factory=dict)  # soft objective weights by name


@dataclass
class Diagnosis:
    event_ids: list[int]
    constraint_kinds: list[str]
    message: str
    suggestions: list[str]
    severity: str  # "error" | "warning" | "info"


@dataclass
class SolverResult:
    status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT", "ERROR"]
    assignments: list[Assignment]
    hard_score: int  # 0..100
    soft_score: int  # 0..100
    objective_breakdown: dict[str, int]
    diagnoses: list[Diagnosis]
    stats: dict[str, Any]
