"""Pydantic schemas for the AI layer (elicitation, chat, proposed diffs, explanations)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Lang = Literal["tr", "en"]


# ---------------------------------------------------------------------------
# Token / cost accounting
# ---------------------------------------------------------------------------


class UsageOut(BaseModel):
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    requests: int = 0
    estimated_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Constraint elicitation (pre-generation)
# ---------------------------------------------------------------------------


class ResolvedEntity(BaseModel):
    """One name the model used, resolved (or not) to a database id. Ids are never invented by the model."""

    type: Literal["room", "program", "course", "event", "instructor", "building", "date", "section", "assignment"]
    text: str
    resolved_id: int | None = None
    resolved_label: str | None = None
    confidence: float = 0.0
    candidates: list[dict[str, Any]] = []


class SourceRef(BaseModel):
    """Where a proposal came from: the prompt, or a row/paragraph/page of an uploaded file."""

    filename: str | None = None
    kind: Literal["prompt", "row", "paragraph", "page", "line"] = "prompt"
    ref: int | None = None  # 1-based row / paragraph / page / line number
    sheet: str | None = None
    excerpt: str | None = None

    @property
    def label(self) -> str:
        if self.filename is None:
            return "prompt"
        return f"{self.filename}{' [' + self.sheet + ']' if self.sheet else ''} {self.kind} {self.ref}"

    def to_ref(self) -> dict[str, Any] | None:
        """Compact ``source_ref`` stored with proposals / constraints:
        ``{"file": "prefs.xlsx", "row": 12, "sheet": "Bahar", "excerpt": "..."}``."""
        if self.filename is None:
            return None
        out: dict[str, Any] = {"file": self.filename}
        if self.ref is not None:
            out[self.kind] = self.ref
        if self.sheet:
            out["sheet"] = self.sheet
        if self.excerpt:
            out["excerpt"] = self.excerpt
        return out


#: ``AI`` = from the free-text prompt or chat, ``UPLOAD`` = from an uploaded preference file.
ProposalSource = Literal["AI", "UPLOAD"]


class ProposedConstraint(BaseModel):
    kind: str
    params: dict[str, Any] = {}
    hardness: Literal["hard", "soft"] = "soft"
    weight: int = 1
    nl_text: str = ""
    rationale: str = ""
    confidence: float = 0.0
    title: str | None = None
    status: Literal["ok", "needs_review", "rejected"] = "ok"
    issues: list[str] = []
    entities: list[ResolvedEntity] = []
    source: ProposalSource = "AI"
    source_ref: dict[str, Any] | None = None  # {"file": ..., "row"|"paragraph"|"page"|"line": n, ...}


SectionField = Literal["enrolment", "day", "time", "mode", "preferred_rooms"]
SectionMode = Literal["F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"]


class SectionChanges(BaseModel):
    """Field changes for ``set_field`` (``None`` = keep)."""

    enrolment: int | None = Field(default=None, ge=0, le=5000)
    day: int | None = Field(default=None, ge=1, le=7)
    start_period: int | None = Field(default=None, ge=1, le=18)
    end_period: int | None = Field(default=None, ge=1, le=18)
    mode: SectionMode | None = None
    preferred_room_ids: list[int] | None = None


class ProposedSectionEdit(BaseModel):
    """Data edit on sections (include/exclude from room planning, or field changes). Never auto-applied."""

    op: Literal["include", "exclude", "set_field"]
    section_ids: list[int] = []
    changes: SectionChanges = SectionChanges()
    nl_text: str = ""
    rationale: str = ""
    confidence: float = 0.0
    status: Literal["ok", "needs_review", "rejected"] = "ok"
    issues: list[str] = []
    entities: list[ResolvedEntity] = []
    labels: list[str] = []  # human labels of the targeted sections ("PHAR 240 §1 (eczacılık)")
    source: ProposalSource = "AI"
    source_ref: dict[str, Any] | None = None


class ElicitIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    lang: Lang = "tr"


class ElicitOut(BaseModel):
    proposals: list[ProposedConstraint]
    section_edits: list[ProposedSectionEdit] = []
    unparsed: list[dict[str, Any]] = []
    assistant_message: str = ""
    usage: UsageOut = UsageOut()


class IngestOut(ElicitOut):
    filename: str
    file_kind: Literal["xlsx", "csv", "docx", "pdf", "txt"]
    units: int = 0  # rows / paragraphs / pages read
    chunks: int = 0
    truncated: bool = False
    detected_columns: dict[str, str] = {}  # role -> header text (tabular files)
    warnings: list[str] = []


class AcceptIn(BaseModel):
    proposals: list[ProposedConstraint] = []
    section_edits: list[ProposedSectionEdit] = []
    run_id: int | None = None  # attach constraints to a run instead of the term


class AcceptOut(BaseModel):
    created: list[int]
    rejected: list[dict[str, Any]] = []
    section_edits_applied: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Chat on a run: proposed diff operations (never applied automatically)
# ---------------------------------------------------------------------------


class MoveOp(BaseModel):
    op: Literal["move"] = "move"
    assignment_id: int
    day: int | None = None
    start_period: int | None = None
    end_period: int | None = None
    room_ids: list[int] | None = None
    weeks: list[int] | None = None
    label: str | None = None
    reason: str = ""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    preview_conflicts: list[dict[str, Any]] = []


class SwapOp(BaseModel):
    op: Literal["swap"] = "swap"
    assignment_id_a: int
    assignment_id_b: int
    label: str | None = None
    reason: str = ""
    preview_conflicts: list[dict[str, Any]] = []


class LockOp(BaseModel):
    op: Literal["lock", "unlock"]
    assignment_id: int
    label: str | None = None
    reason: str = ""


class AddConstraintOp(BaseModel):
    op: Literal["add_constraint"] = "add_constraint"
    constraint: ProposedConstraint


class RemoveConstraintOp(BaseModel):
    op: Literal["remove_constraint"] = "remove_constraint"
    constraint_id: int
    label: str | None = None
    reason: str = ""


class SetWeightOp(BaseModel):
    op: Literal["set_weight"] = "set_weight"
    constraint_id: int
    weight: int | None = None
    hardness: Literal["hard", "soft"] | None = None
    label: str | None = None
    reason: str = ""


class SectionEditOp(BaseModel):
    op: Literal["section_edit"] = "section_edit"
    edit: ProposedSectionEdit


DiffOp = Annotated[
    MoveOp | SwapOp | LockOp | AddConstraintOp | RemoveConstraintOp | SetWeightOp | SectionEditOp,
    Field(discriminator="op"),
]


class ProposedDiff(BaseModel):
    id: str
    run_id: int
    operations: list[DiffOp] = []
    re_solve: bool = False
    stability: bool = True
    summary: str = ""
    warnings: list[str] = []

    @property
    def is_empty(self) -> bool:
        return not self.operations and not self.re_solve


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    lang: Lang = "tr"


class ChatOut(BaseModel):
    message_id: int
    assistant_message: str
    proposed_diff: ProposedDiff | None = None
    explanations: list[dict[str, Any]] = []
    usage: UsageOut = UsageOut()


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    tool_calls: list[Any] = []
    created_at: Any = None


class ApplyIn(BaseModel):
    diff_id: str | None = None
    diff: ProposedDiff | None = None
    label: str | None = None


class ApplyOut(BaseModel):
    child_run_id: int | None
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    constraints_created: list[int] = []
    re_solve_queued: bool = False
    mode: Literal["patch", "repair", "full", "none"] = "none"
    status: str | None = None
    hard_score: int | None = None
    soft_score: int | None = None


class ExplainIn(BaseModel):
    lang: Lang = "tr"
    use_model: bool = True


class ExplainOut(BaseModel):
    text: str
    sections: list[dict[str, Any]] = []
    source: Literal["model", "template"] = "template"
    usage: UsageOut = UsageOut()


class CatalogKindOut(BaseModel):
    kind: str
    title: dict[str, str]
    description: dict[str, str]
    params_schema: dict[str, Any]
    examples: list[dict[str, Any]] = []
    allowed_hardness: list[str]
    default_hardness: str
    implicit: bool = False
    registered: bool = True


class CatalogOut(BaseModel):
    kinds: list[CatalogKindOut]
    tools: list[dict[str, Any]]
    selectors: dict[str, Any]
