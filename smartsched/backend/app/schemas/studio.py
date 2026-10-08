"""Pydantic I/O for the Generator Studio (``/api/v1/terms/{id}/studio*``, ``/studio/*``, ``/presets``)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

StudioKind = Literal["COURSE", "EXAM"]
Horizon = Literal["WEEK", "MONTH", "TERM"]
Text2 = dict[str, str]  # {"tr": ..., "en": ...}


# --------------------------------------------------------------------------- draft


class Pin(BaseModel):
    """Draft-only pin: the event keeps one of ``room_ids`` and/or sits at ``day`` / ``start_period``."""

    event_id: int
    room_ids: list[int] = []
    day: int | None = Field(default=None, ge=1, le=7)
    start_period: int | None = Field(default=None, ge=1, le=18)


class RuleOverride(BaseModel):
    hardness: Literal["hard", "soft"] | None = None
    weight: int | None = Field(default=None, ge=1, le=10)


class DraftIn(BaseModel):
    """Partial update; omitted fields keep their value. ``version`` (or ``If-Match``) is required."""

    version: int | None = None
    kind: StudioKind = "COURSE"
    horizon: Horizon | None = None
    horizon_params: dict[str, Any] | None = None
    excluded_event_ids: list[int] | None = None
    pins: list[Pin] | None = None
    disabled_builtin_kinds: list[str] | None = None
    disabled_rule_ids: list[int] | None = None
    rule_overrides: dict[str, RuleOverride] | None = None
    preset_id: int | None = None
    last_step: Literal["scope", "classes", "rules", "check", "run"] | None = None
    params: dict[str, Any] | None = None


class ScopeOut(BaseModel):
    horizon: str
    horizon_params: dict[str, Any]
    weeks: list[int]
    holiday_weeks: list[int] = []


class DraftOut(BaseModel):
    draft_id: int
    term_id: int
    user_id: int
    kind: str
    version: int
    etag: str
    scope: ScopeOut
    excluded_event_ids: list[int]
    pins: list[dict[str, Any]]
    disabled_builtin_kinds: list[str]
    disabled_rule_ids: list[int]
    rule_overrides: dict[str, dict[str, Any]]
    rule_ids: list[int]  # constraint ids in play for this draft (enabled term rules minus per-draft offs)
    preset_id: int | None
    last_step: str | None
    params: dict[str, Any]
    updated_at: dt.datetime


# --------------------------------------------------------------------------- class list


class ChangedField(BaseModel):
    field: str
    imported: Any = None
    current: Any = None


class ClassRow(BaseModel):
    id: int  # meeting_request id (COURSE) or exam_request id (EXAM)
    kind: StudioKind
    section_id: int | None = None
    course_code: str | None = None
    course_name: str | None = None
    section_label: str | None = None
    program_id: int | None = None
    program_name: str | None = None
    faculty_id: int | None = None
    faculty_name: str | None = None
    is_evening: bool = False
    class_year: int | None = None
    class_years: list[int] = []
    day: int | None = None
    days: list[int] = []
    start_period: int | None = None
    end_period: int | None = None
    time_label: str | None = None  # "13:30-15:50"
    date: dt.date | None = None  # exams
    weeks: list[int] = []
    enrolment: int | None = None
    mode: str | None = None
    needs_room: bool = True
    flexible_day: bool = False
    requested_room_ids: list[int] = []
    requested_room_codes: list[str] = []
    requested_building: str | None = None
    requested_tags: list[str] = []
    definitive_room_ids: list[int] = []
    definitive_room_codes: list[str] = []
    requested_room_count: int | None = None  # exams
    status: str
    locked: bool = False
    instructors: list[str] = []
    included: bool = True
    schedulable: bool = True  # has day/time (or date) and needs a room: the solver will see it
    pinned: bool = False
    changed_fields: list[ChangedField] = []
    rule_ids: list[int] = []  # targeted rules (in play) that select this class


class ClassPage(BaseModel):
    items: list[ClassRow]
    total: int
    limit: int
    offset: int
    counts: dict[str, int]  # whole-term counts for the footer / quick chips


# --------------------------------------------------------------------------- edits


class MeetingPatch(BaseModel):
    enrolment: int | None = Field(default=None, ge=0, le=5000)
    mode: Literal["F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"] | None = None
    day: int | None = Field(default=None, ge=1, le=7)
    days: list[int] | None = None
    flexible_day: bool | None = None
    start_period: int | None = Field(default=None, ge=1, le=18)
    end_period: int | None = Field(default=None, ge=1, le=18)
    weeks: list[int] | None = None
    requested_room_ids: list[int] | None = None
    requested_building: str | None = None
    requested_tags: list[str] | None = None
    definitive_room_ids: list[int] | None = None
    needs_room: bool | None = None
    locked: bool | None = None


class BulkItem(BaseModel):
    id: int
    patch: MeetingPatch


class BulkEditIn(BaseModel):
    """Either one ``patch`` for every id in ``ids`` or per-row ``items``."""

    ids: list[int] = []
    patch: MeetingPatch | None = None
    items: list[BulkItem] = []
    dry_run: bool = False


class BulkRowResult(BaseModel):
    id: int
    ok: bool
    errors: list[str] = []
    changed: list[str] = []
    warnings: list[str] = []  # e.g. "A 103 has 47 seats, this class has 60"


class BulkEditOut(BaseModel):
    results: list[BulkRowResult]
    updated: int
    failed: int
    rows: list[ClassRow] = []


class RevertIn(BaseModel):
    fields: list[str] | None = None  # None = every changed field


class BulkRevertIn(RevertIn):
    ids: list[int]


# --------------------------------------------------------------------------- pre-check


class FixOut(BaseModel):
    option: str
    label: Text2
    action: dict[str, Any]  # {type: exclude|meeting_update|exam_update|rule_override|rule_off|builtin_off, payload}
    admin_only: bool = False


class PrecheckItem(BaseModel):
    id: str
    category: Literal["impossible", "clash", "no_match", "info"]
    severity: Literal["error", "warning", "info"]
    group: str  # capacity | room_tags | locked_ineligible | pigeonhole | instructor_clash | rule_no_match | ...
    title: Text2
    message: Text2
    detail: str = ""  # the solver's own sentence (advanced layer)
    event_ids: list[int] = []
    classes: list[dict[str, Any]] = []  # [{event_id, label, request_ids}]
    constraint_kinds: list[str] = []
    constraint_ids: list[int] = []
    fixes: list[FixOut] = []


class PrecheckOut(BaseModel):
    draft_id: int
    version: int
    readiness: Literal["ready", "needs_look", "blocked"]
    counts: dict[str, int]
    groups: list[dict[str, Any]] = []  # [{group, title, severity, count}] for "> 20 issues: grouped by cause"
    items: list[PrecheckItem]
    estimate_s: dict[str, Any]
    summary: Text2
    duration_s: float


class FixIn(BaseModel):
    item_id: str
    option: str


class FixResultOut(BaseModel):
    applied: dict[str, Any]
    draft: DraftOut
    precheck: PrecheckOut


# --------------------------------------------------------------------------- rules


class PreviewIn(BaseModel):
    term_id: int
    kind: str
    params: dict[str, Any] = {}
    hardness: Literal["hard", "soft"] = "soft"
    draft_kind: StudioKind = "COURSE"
    sample: int = Field(default=8, ge=0, le=50)


class PreviewOut(BaseModel):
    affected_count: int
    total: int
    percent: float
    targeted: bool
    sample: list[dict[str, Any]]
    issues: list[str]
    notes: list[str]


class CopyIn(BaseModel):
    to_term_id: int
    from_run_id: int | None = None
    from_term_id: int | None = None
    constraint_ids: list[int] | None = None
    dry_run: bool = False


class CopyItem(BaseModel):
    source_id: int
    kind: str
    hardness: str
    weight: int
    nl_text: str | None = None
    params: dict[str, Any]
    affected_count: int
    reasons: list[str] = []
    created_id: int | None = None


class CopyOut(BaseModel):
    will_match: list[CopyItem]
    needs_review: list[CopyItem]
    cannot_match: list[CopyItem]
    created: list[int]
    dry_run: bool


class AcceptIn(BaseModel):
    """Same as ``POST /terms/{id}/elicit/accept`` but ``source_ref`` lands in ``constraints.source_ref``."""

    proposals: list[dict[str, Any]] = []
    section_edits: list[dict[str, Any]] = []


class RuleOut(BaseModel):
    id: int
    kind: str
    params: dict[str, Any]
    hardness: str
    weight: int
    source: str
    source_ref: dict[str, Any] | None = None
    nl_text: str | None = None
    enabled: bool
    in_play: bool
    override: dict[str, Any] | None = None
    title: Text2
    affected_count: int | None = None


class RulesOut(BaseModel):
    rules: list[RuleOut]
    builtins: list[dict[str, Any]]
    counts: dict[str, int]


# --------------------------------------------------------------------------- presets


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    kind: StudioKind = "COURSE"
    rules: list[dict[str, Any]] | None = None
    scope: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    disabled_builtin_kinds: list[str] | None = None
    from_term_id: int | None = None  # snapshot the caller's draft + that term's rules


class PresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    rules: list[dict[str, Any]] | None = None
    scope: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    disabled_builtin_kinds: list[str] | None = None


class PresetOut(BaseModel):
    id: int
    name: str
    description: str | None
    kind: str
    rules: list[dict[str, Any]]
    scope: dict[str, Any]
    filters: dict[str, Any]
    disabled_builtin_kinds: list[str]
    created_by: int | None
    author: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class PresetApplyIn(BaseModel):
    term_id: int
    dry_run: bool = False


class PresetApplyOut(BaseModel):
    add: list[dict[str, Any]]
    change: list[dict[str, Any]]
    turn_off: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    scope: dict[str, Any] | None
    excluded_count: int
    dry_run: bool
    created: list[int] = []
    draft: DraftOut | None = None


# --------------------------------------------------------------------------- generate / summary / meta


class GenerateIn(BaseModel):
    label: str | None = None
    params: dict[str, Any] = {}  # time_limit_s, seed, workers, weights, solver
    parent_run_id: int | None = None
    stability: bool | None = None  # keep changes small vs parent_run_id (default: on when a parent is given)


class GenerateOut(BaseModel):
    run_id: int
    status: str
    draft_id: int
    draft_version: int
    events: int
    excluded: int
    prompt_text: str
