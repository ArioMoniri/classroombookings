"""Schemas for the calendar v2 / all-classes read models (docs/design/v2/calendar.md §17,
docs/design/v2/all-classes.md §16): calendar index, heat, free rooms, scoped and bulk moves, per-assignment
explanations, the term-wide classes read model and saved views."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Lang = Literal["tr", "en"]
Severity = Literal["hard", "soft"]
MoveScope = Literal["all", "week", "from"]


class Text2(BaseModel):
    """A planner-facing sentence in both UI languages."""

    tr: str
    en: str


class Issue(BaseModel):
    code: str
    severity: Severity
    text: Text2
    with_assignment_id: int | None = None
    with_label: str | None = None
    room_code: str | None = None
    weeks: list[int] = []


# ------------------------------------------------------------------ calendar index


class IndexRoom(BaseModel):
    id: int
    code: str
    name: str
    building: str
    capacity: int
    exam_capacity: int
    tags: list[str] = []
    bookable: bool = True
    photo_url: str | None = None


class IndexWeek(BaseModel):
    index: int
    start_date: str | None
    kind: str
    label: str | None


class IndexAssignment(BaseModel):
    """Compact assignment row (one per DB row; ``weeks`` = weeks it occupies its room(s))."""

    id: int
    mr: int | None = None
    ex: int | None = None
    label: str
    code: str | None = None
    name: str | None = None
    sec: str | None = None
    prog: str | None = None
    prog_id: int | None = None
    fac: int | None = None
    slot: int = 8
    year: int | None = None
    evening: bool = False
    instr: list[str] = []
    instr_ids: list[int] = []
    size: int = 0
    cap: int | None = None
    weeks: list[int] = []
    day: int
    date: str | None = None
    sp: int
    ep: int
    rooms: list[int] = []
    locked: bool = False
    origin: str = "SOLVER"
    reasons: list[str] = []
    tags: list[str] = []
    needs_pc: bool = False


class IndexBlock(BaseModel):
    id: int
    room: int
    day: int
    sp: int
    ep: int
    weeks: list[int] = []
    label: str
    source: str


class IndexBooking(BaseModel):
    id: int
    room: int
    date: str
    week: int | None
    day: int
    sp: int
    ep: int
    title: str
    owner: str | None = None


class IndexUnplaced(BaseModel):
    mr: int
    label: str
    code: str
    prog: str | None = None
    slot: int = 8
    year: int | None = None
    size: int = 0
    day: int | None = None
    sp: int | None = None
    ep: int | None = None
    weeks: list[int] = []
    room_text: str | None = None


class IndexFaculty(BaseModel):
    id: int
    name: str
    slot: int


class IndexRun(BaseModel):
    id: int
    term_id: int
    kind: str
    status: str
    label: str | None = None
    horizon: str
    weeks: list[int] = []
    is_active: bool = False
    origin_import: bool = False


class CalendarIndexOut(BaseModel):
    run: IndexRun
    rooms: list[IndexRoom]
    weeks: list[IndexWeek]
    periods: list[dict[str, Any]]
    faculties: list[IndexFaculty]
    assignments: list[IndexAssignment]
    blocks: list[IndexBlock]
    bookings: list[IndexBooking] = []
    unplaced: list[IndexUnplaced] = []
    bookings_enabled: bool = False
    today: str


# ------------------------------------------------------------------ heat


class HeatCell(BaseModel):
    week: int | None
    day: int
    date: str | None
    in_term: bool = True
    occupied: int = 0
    blocked: int = 0
    capacity: int = 0
    occupancy: float = 0.0
    conflicts: int = 0
    by_building: dict[str, float] = {}


class HeatOut(BaseModel):
    run_id: int
    scale: Literal["term", "month"]
    month: str | None = None
    room_id: int | None = None
    cells: list[HeatCell]
    weekly: list[dict[str, Any]] = []


# ------------------------------------------------------------------ free rooms


class FreeRoom(BaseModel):
    room_id: int
    code: str
    building: str
    capacity: int
    tags: list[str] = []
    status: Literal["free", "too_small", "busy", "blocked", "not_bookable", "tag_mismatch"]
    fit: float | None = None
    reason: Text2 | None = None
    with_label: str | None = None


class FreeRoomsOut(BaseModel):
    run_id: int
    day: int
    start_period: int
    end_period: int
    weeks: list[int]
    size: int
    rooms: list[FreeRoom]


# ------------------------------------------------------------------ moves


class MoveItemIn(BaseModel):
    aid: int
    day: int | None = None
    start_period: int | None = None
    end_period: int | None = None
    room_ids: list[int] | None = None
    scope: MoveScope = "all"
    week: int | None = None


class BulkMoveIn(BaseModel):
    moves: list[MoveItemIn] = Field(min_length=1, max_length=500)
    atomic: bool = True
    dry_run: bool = False
    force: bool = False
    lang: Lang = "tr"


class MovePreviewIn(BaseModel):
    day: int | None = None
    start_period: int | None = None
    end_period: int | None = None
    room_ids: list[int] | None = None
    scope: MoveScope = "all"
    week: int | None = None


class Snapshot(BaseModel):
    """Exact state of one assignment row before a move (for undo)."""

    id: int
    day: int
    start_period: int
    end_period: int
    room_ids: list[int]
    week: int | None
    weeks: list[int]
    is_locked: bool
    origin: str


class UndoToken(BaseModel):
    snapshots: list[Snapshot] = []
    delete_ids: list[int] = []


class MovePlanItem(BaseModel):
    aid: int
    label: str
    ok: bool
    hard: list[Issue] = []
    soft: list[Issue] = []
    day: int
    start_period: int
    end_period: int
    room_ids: list[int]
    room_codes: list[str]
    weeks: list[int]
    moved_ids: list[int] = []
    split_ids: list[int] = []


class BulkMoveOut(BaseModel):
    ok: bool
    applied: bool
    dry_run: bool
    items: list[MovePlanItem]
    ok_count: int
    conflict_count: int
    assignments: list[IndexAssignment] = []
    undo: UndoToken = UndoToken()


class RestoreIn(BaseModel):
    snapshots: list[Snapshot] = []
    delete_ids: list[int] = []


class BulkLockIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)
    locked: bool = True


# ------------------------------------------------------------------ explain


class ExplainAssignmentIn(BaseModel):
    lang: Lang = "tr"
    use_model: bool = True


class ExplainSection(BaseModel):
    key: Literal["why", "alternatives", "impact", "checks"]
    title: str
    lines: list[str]


class AssignmentExplainOut(BaseModel):
    assignment_id: int
    text: str
    sections: list[ExplainSection]
    checks: list[dict[str, Any]] = []
    source: Literal["model", "template"] = "template"


# ------------------------------------------------------------------ classes read model


class ClassInstructor(BaseModel):
    id: int | None = None
    name: str


class ClassRequest(BaseModel):
    day: int | None = None
    days: list[int] = []
    date: str | None = None
    start_period: int | None = None
    end_period: int | None = None
    weeks: list[int] = []
    room_text: str | None = None
    room_ids: list[int] = []
    room_codes: list[str] = []
    building: str | None = None
    tags: list[str] = []
    capacity: int | None = None
    flexible_day: bool = False
    status: str = "NEW"
    warnings: list[str] = []
    notes: str | None = None
    room_count: int | None = None


class ClassDefinitive(BaseModel):
    text: str | None = None
    room_ids: list[int] = []
    room_codes: list[str] = []


class ClassPlacement(BaseModel):
    assignment_ids: list[int]
    day: int
    date: str | None = None
    start_period: int
    end_period: int
    room_ids: list[int]
    room_codes: list[str]
    capacity: int | None = None
    weeks_placed: list[int] = []
    locked: bool = False
    origin: str = "SOLVER"
    matched: Literal["request", "board"] = "request"


class ClassChange(BaseModel):
    field: str
    source: Literal["import", "manual", "run", "compare"]
    from_: Any = Field(default=None, alias="from")
    to: Any = None

    model_config = {"populate_by_name": True}


class ClassProvenance(BaseModel):
    kind: str
    import_job_id: int | None = None
    file_name: str | None = None
    sheet: str | None = None
    row: int | None = None
    source_key: str | None = None


class ClassRow(BaseModel):
    id: int
    kind: Literal["meeting", "exam"]
    course_code: str
    course_name: str | None = None
    section: str | None = None
    faculty_id: int | None = None
    faculty_name: str | None = None
    faculty_slot: int = 8
    program_id: int | None = None
    program_name: str | None = None
    is_evening: bool = False
    class_years: list[int] = []
    instructors: list[ClassInstructor] = []
    enrolment: int | None = None
    mode: str = "F2F"
    needs_room: bool = True
    merge_key: str | None = None
    req: ClassRequest
    definitive: ClassDefinitive
    placement: ClassPlacement | None = None
    placement_status: Literal["placed", "partial", "unplaced", "conflict", "no_room_needed", "no_run"]
    issues: list[Issue] = []
    changed: list[ClassChange] = []
    provenance: ClassProvenance
    updated_at: str | None = None


class ClassesOut(BaseModel):
    term_id: int
    kind: Literal["meetings", "exams"]
    run_id: int | None
    compare_run_id: int | None = None
    total: int
    items: list[ClassRow]
    facets: dict[str, dict[str, int]]


class RunPlacement(BaseModel):
    run_id: int
    run_label: str | None = None
    status: str
    is_active: bool = False
    room_codes: list[str] = []
    day: int | None = None
    start_period: int | None = None
    end_period: int | None = None
    locked: bool = False


class ClassDetailOut(BaseModel):
    row: ClassRow
    raw_row: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = []
    history: list[RunPlacement] = []


# ------------------------------------------------------------------ saved views


Surface = Literal["classes", "calendar"]


class SavedViewIn(BaseModel):
    surface: Surface
    name: str = Field(min_length=1, max_length=80)
    state: dict[str, Any] = {}
    shared: bool = False


class SavedViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    state: dict[str, Any] | None = None
    shared: bool | None = None


class SavedViewOut(BaseModel):
    id: str
    surface: Surface
    name: str
    state: dict[str, Any]
    shared: bool
    owner_id: int
    owner_name: str | None = None
    mine: bool = True
    created_at: str
    updated_at: str
