from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

#: every ``ScheduleRun.status``.  ``FEASIBLE_PARTIAL``: a best-effort run that stored a partial timetable
#: (some requests cannot be placed, every placed one satisfies the hard rules; ``stats.partial`` /
#: ``placed`` / ``unplaced`` / ``events_total`` give the numbers, ``stats.partial`` stays for older clients)
RUN_STATUSES: tuple[str, ...] = (
    "QUEUED",
    "RUNNING",
    "OPTIMAL",
    "FEASIBLE",
    "FEASIBLE_PARTIAL",
    "INFEASIBLE",
    "TIMEOUT",
    "FAILED",
    "CANCELLED",
    "ERROR",
)
#: a run in one of these states will not change any more (SSE streams end, the UI stops polling)
TERMINAL_STATUSES: frozenset[str] = frozenset(RUN_STATUSES) - {"QUEUED", "RUNNING"}
#: runs with a usable timetable (dashboard utilisation, "last good run"); partial ones after complete ones
USABLE_STATUSES: tuple[str, ...] = ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL")


class RunCreate(BaseModel):
    term_id: int
    kind: str = Field(default="COURSE", pattern="^(COURSE|EXAM)$")
    horizon: str = Field(default="TERM", pattern="^(WEEK|MONTH|TERM)$")
    horizon_params: dict[str, Any] = {}
    params: dict[str, Any] = {}
    prompt: str | None = Field(default=None, max_length=4000)
    parent_run_id: int | None = None
    label: str | None = Field(default=None, max_length=255)

    @field_validator("horizon_params")
    @classmethod
    def _week_list(cls, v: dict[str, Any]) -> dict[str, Any]:
        """``{"week": 3}`` (API/CLI shorthand) is stored as ``{"weeks": [3], "week": 3}`` so every reader that
        only looks at ``weeks`` (run view, runs list, dashboard, calendar) shows the right horizon."""
        hp = dict(v or {})
        week = hp.get("week")
        if isinstance(week, int) and not isinstance(week, bool) and not hp.get("weeks"):
            hp["weeks"] = [week]
        return hp


class RunOut(ORMModel):
    id: int
    term_id: int
    term_code: str | None = None
    kind: str
    horizon: str
    horizon_params: dict[str, Any]
    status: str = Field(description="one of " + ", ".join(RUN_STATUSES))
    params: dict[str, Any]
    objective_value: float | None
    soft_score: int | None
    hard_score: int | None
    stats: dict[str, Any]
    diagnosis: list[Any]
    parent_run_id: int | None
    prompt_text: str | None
    label: str | None
    is_active: bool
    error: str | None
    created_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    objective_breakdown: dict[str, int] = {}
    progress: int = 0
    #: placement of the stored timetable (FEASIBLE_PARTIAL: placed < events_total; the hard score is the one
    #: of the *placed* events, so a partial run must be shown as "placed/total", never as a plain 100/100)
    placed: int | None = None
    events_total: int | None = None
    partial: bool = False


class RunCreated(BaseModel):
    run_id: int
    status: str


class AssignmentOut(ORMModel):
    id: int
    run_id: int
    meeting_request_id: int | None
    exam_request_id: int | None
    week: int | None
    weeks: list[Any]
    day: int
    date: dt.date | None
    start_period: int
    end_period: int
    room_ids: list[Any]
    label: str | None
    course_codes: list[Any]
    tags: list[Any]
    notes: str | None
    is_locked: bool
    origin: str
    archived: bool
    display_label: str | None = None
    room_codes: list[str] = []
    # enrichment (see services.grid.enrich_assignments)
    course_code: str | None = None
    course_name: str | None = None
    section_label: str | None = None
    program_name: str | None = None
    class_year: int | None = None
    size: int = 0
    enrolment: int | None = None
    instructors: list[str] = []
    instructor: str | None = None
    capacity: int | None = None
    week_set: list[int] = []
    is_conflict: bool = False
    conflict_reasons: list[str] = []


class MoveIn(BaseModel):
    day: int | None = None
    start_period: int | None = None
    end_period: int | None = None
    room_ids: list[int] | None = None
    week: int | None = None
    force: bool = False


class MoveOut(BaseModel):
    ok: bool
    assignment: AssignmentOut | None = None
    conflicts: list[dict[str, Any]] = []
    #: the run after the move, re-validated at planner level (``app.services.planner_check``): hard score,
    #: status and the rule violations (a forced double booking lowers the hard score, review M4)
    hard_score: int | None = None
    status: str | None = None
    violations: list[dict[str, Any]] = []


class DiagnosisApplyIn(BaseModel):
    option_index: int = 0
    re_solve: bool = True
    label: str | None = None


class DiagnosisApplyOut(BaseModel):
    run_id: int
    child_run_id: int | None = None
    action: str
    message: str
    details: dict[str, Any] = {}
    constraint_id: int | None = None


#: ``constraints.source`` values a client may write through ``/constraints`` (review M10); AI, UPLOAD,
#: GRID_IMPORT, CRBS and BUILTIN rows are written by the server only
CLIENT_CONSTRAINT_SOURCES = ("ADMIN", "FILE")
CONSTRAINT_WEIGHT_MAX = 10


class ConstraintIn(BaseModel):
    term_id: int | None = None
    run_id: int | None = None
    kind: str = Field(max_length=64)
    params: dict[str, Any] = {}
    hardness: str = Field(default="soft", pattern="^(hard|soft)$")
    weight: int = Field(default=1, ge=0, le=CONSTRAINT_WEIGHT_MAX)
    source: str = Field(default="ADMIN", pattern="^(" + "|".join(CLIENT_CONSTRAINT_SOURCES) + ")$")
    nl_text: str | None = Field(default=None, max_length=2000)
    enabled: bool = True


class ConstraintUpdate(BaseModel):
    params: dict[str, Any] | None = None
    hardness: str | None = Field(default=None, pattern="^(hard|soft)$")
    weight: int | None = Field(default=None, ge=0, le=CONSTRAINT_WEIGHT_MAX)
    nl_text: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class ConstraintOut(ORMModel):
    id: int
    term_id: int | None
    run_id: int | None
    kind: str
    params: dict[str, Any]
    hardness: str
    weight: int
    source: str
    nl_text: str | None
    enabled: bool
    created_by: int | None
    source_ref: dict[str, Any] | None = None


class ImportJobOut(ORMModel):
    id: int
    kind: str
    filename: str | None
    term_code: str | None
    status: str
    summary: dict[str, Any]
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


class DataIssueItem(BaseModel):
    """One diagnosis of the run in a data-issues group, with every request (class) involved."""

    diagnosis_index: int
    code: str
    severity: str
    message: str
    message_tr: str
    suggestions: list[str]
    event_ids: list[int]
    request_ids: list[int]
    unplaced: bool
    params: dict[str, Any]
    classes: list[dict[str, Any]]


class DataIssueGroup(BaseModel):
    code: str
    title: dict[str, str]
    hint: dict[str, str]
    count: int
    requests: int
    items: list[DataIssueItem]


class DataIssuesOut(BaseModel):
    run_id: int
    term_id: int
    kind: str
    status: str
    totals: dict[str, Any]
    groups: list[DataIssueGroup]
