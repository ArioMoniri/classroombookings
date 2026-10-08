from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RunCreate(BaseModel):
    term_id: int
    kind: str = Field(default="COURSE", pattern="^(COURSE|EXAM)$")
    horizon: str = Field(default="TERM", pattern="^(WEEK|MONTH|TERM)$")
    horizon_params: dict[str, Any] = {}
    params: dict[str, Any] = {}
    prompt: str | None = None
    parent_run_id: int | None = None
    label: str | None = None


class RunOut(ORMModel):
    id: int
    term_id: int
    term_code: str | None = None
    kind: str
    horizon: str
    horizon_params: dict[str, Any]
    status: str
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


class ConstraintIn(BaseModel):
    term_id: int | None = None
    run_id: int | None = None
    kind: str
    params: dict[str, Any] = {}
    hardness: str = Field(default="soft", pattern="^(hard|soft)$")
    weight: int = 1
    source: str = "ADMIN"
    nl_text: str | None = None
    enabled: bool = True


class ConstraintUpdate(BaseModel):
    params: dict[str, Any] | None = None
    hardness: str | None = Field(default=None, pattern="^(hard|soft)$")
    weight: int | None = None
    nl_text: str | None = None
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
