"""Frozen solver contract (see docs/ARCHITECTURE.md, "Solver contract").

Pure Python dataclasses: no DB, no HTTP. The solver is ``solve(SolverInput) -> SolverResult``.
Do not change field names/semantics without updating docs/ARCHITECTURE.md and all consumers.
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
    tags: frozenset[str]


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
    room_id: int
    week: int | None
    day: int
    start: int
    end: int


@dataclass(frozen=True)
class Event:
    id: int  # meeting_request.id or exam_request.id
    kind: Literal["course", "exam"]
    label: str  # "MAT 112 §1"
    size: int  # enrolment
    duration: int  # number of consecutive periods
    weeks: frozenset[int]  # weeks in which the event occupies a room (course) / {week} (exam)
    fixed_day: int | None  # 1..7
    fixed_start: int | None  # period index 1..18
    allowed_days: frozenset[int]  # when day not fixed
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
    share_room: bool = False  # exams: may sit in one room with other sharing exams (Σ sizes ≤ exam capacity)
    #: ``locked`` is the planner's own decision (a LOCKED planning-list row).  Only such locks are trusted by
    #: ``trust_locked_rooms`` (D1); a lock made by a tool (the fix button, a manual move, an AI edit carried
    #: into a child run) sets ``False`` and must satisfy capacity and tags like any placement (review B2)
    lock_trusted: bool = True


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
    constraints: tuple[Constraint, ...]
    days: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)
    periods_per_day: int = 18
    weeks: tuple[int, ...] = tuple(range(1, 15))
    blocks: tuple[Block, ...] = ()
    previous: tuple[Assignment, ...] = ()  # for stability objective
    time_limit_s: float = 60.0
    seed: int = 0
    workers: int = 8
    weights: Mapping[str, int] = field(default_factory=dict)  # soft objective weights by name
    # --- real-data modes (README "Real-data modes"); all off by default = strict semantics -----------
    #: a locked room set is the planner's decision: kept even when smaller than ``size`` (enrolments are
    #: estimates); reported as a ``trusted_lock_capacity`` warning instead of a hard violation
    trust_locked_rooms: bool = False
    #: two fixed-time events sharing a cohort/instructor key at overlapping times: no room choice can fix
    #: that, so the key's no-overlap is dropped for exactly that pair and reported as an ``input_conflict``
    #: warning (flexible events still respect every key against everything)
    fixed_conflicts_as_warnings: bool = False
    #: an infeasible instance still returns the maximum placement (status INFEASIBLE, ``stats.partial``,
    #: ``stats.placed`` / ``stats.unplaced``; hard/soft scores are those of the placed events)
    best_effort: bool = False


@dataclass
class Diagnosis:
    event_ids: list[int]
    constraint_kinds: list[str]
    message: str
    suggestions: list[str]
    severity: str  # error | warning | info
    #: machine-readable category, e.g. ``trusted_lock_capacity``, ``input_conflict``, ``unplaced``,
    #: ``no_room``, ``locked_overlap``, ``pigeonhole``, ``core`` (see app/solver/README.md "Diagnosis codes")
    code: str = ""
    #: structured facts behind the message (rooms, slot, key, sizes ...) so consumers (precheck, run-report
    #: fixes, the AI layer) never parse the wording; keys per code in app/solver/README.md
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if "options" not in self.params:
            from app.solver.options import options_for

            self.params = {**self.params, "options": options_for(self.suggestions, self.message, self.event_ids)}


@dataclass
class SolverResult:
    status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT", "ERROR"]
    assignments: list[Assignment]
    hard_score: int  # 0..100
    soft_score: int  # 0..100
    objective_breakdown: dict[str, int]
    diagnoses: list[Diagnosis]
    stats: dict[str, Any]


CONSTRAINT_KINDS_V1: tuple[str, ...] = (
    "capacity",
    "no_room_overlap",
    "no_cohort_overlap",
    "no_instructor_overlap",
    "fixed_time",
    "room_tags",
    "room_pin",
    "room_forbid",
    "building_preference",
    "room_preference",
    "same_room_across_weeks",
    "same_room_group",
    "min_capacity_waste",
    "exam_gap",
    "max_exams_per_day",
    "stability",
    "room_closed",
    "day_window",
    "evening_programs_in_buildings",
)
