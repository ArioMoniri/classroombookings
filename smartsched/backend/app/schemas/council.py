"""I/O schemas of the Ingestion Council API (``/api/v1/council``)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CouncilStepOut(ORMModel):
    id: int
    file_index: int | None
    agent: str
    status: str
    attempt: int
    started_at: dt.datetime
    finished_at: dt.datetime | None
    duration_ms: int | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    message: str | None


class CouncilFileOut(BaseModel):
    index: int
    filename: str
    size: int
    status: str
    format: str | None = None
    language: str | None = None
    route: str | None = None
    kinds: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    rule_texts: int = 0
    message: str | None = None
    steps: list[CouncilStepOut] = Field(default_factory=list)


class CouncilJobOut(BaseModel):
    id: int
    status: str
    mode: str
    ai_mode: str
    lang: str
    year_hint: int | None
    progress: int
    phase: str | None
    files: list[CouncilFileOut]
    cross_steps: list[CouncilStepOut]
    plan: dict[str, Any] | None
    summary: dict[str, Any]
    usage: dict[str, Any]
    commits: list[dict[str, Any]]
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


class CouncilJobBrief(BaseModel):
    id: int
    status: str
    files: int
    ai_mode: str
    created_at: dt.datetime
    summary: dict[str, Any]


class ReviewDecisionIn(BaseModel):
    id: str
    action: Literal["accept", "reject", "edit"]
    value: dict[str, Any] | None = None


class ReviewIn(BaseModel):
    decisions: list[ReviewDecisionIn] = Field(min_length=1, max_length=500)


class ReviewOut(BaseModel):
    job_id: int
    status: str
    blocking: int
    items: list[dict[str, Any]]
    plan: dict[str, Any] | None
    threshold: float
    saved: int | None = None
    errors: list[str] = Field(default_factory=list)
    rerun_files: list[int] = Field(default_factory=list)


class TermSpec(BaseModel):
    code: str | None = Field(default=None, max_length=32)
    name: str | None = Field(default=None, max_length=128)
    kind: Literal["REGULAR", "FINAL", "BUT", "SUMMER"] | None = None
    week_count: int | None = Field(default=None, ge=1, le=60)
    start_date: dt.date | None = None
    year: int | None = Field(default=None, ge=1990, le=2100)


class CommitIn(BaseModel):
    group: int | None = Field(default=None, ge=0, description="planner term group index")
    term_id: int | None = Field(default=None, description="existing term to write into")
    term: TermSpec | None = Field(default=None, description="new term (overrides the group's proposal)")
    files: list[int] | None = Field(default=None, description="file indexes (default: the group's files)")
    include_rules: bool = True
    allow_pending: bool = Field(default=False, description="commit although blocking review items are open")


class RerunIn(BaseModel):
    mode: Literal["auto", "general"] | None = None
    ai: bool | None = None
