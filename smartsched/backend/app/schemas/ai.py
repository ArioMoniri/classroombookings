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

    type: Literal["room", "program", "course", "event", "instructor", "building", "date"]
    text: str
    resolved_id: int | None = None
    resolved_label: str | None = None
    confidence: float = 0.0
    candidates: list[dict[str, Any]] = []


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


class ElicitIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    lang: Lang = "tr"


class ElicitOut(BaseModel):
    proposals: list[ProposedConstraint]
    unparsed: list[dict[str, str]] = []
    assistant_message: str = ""
    usage: UsageOut = UsageOut()


class AcceptIn(BaseModel):
    proposals: list[ProposedConstraint]
    run_id: int | None = None  # attach to a run instead of the term


class AcceptOut(BaseModel):
    created: list[int]
    rejected: list[dict[str, Any]] = []


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
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    preview_conflicts: list[dict[str, Any]] = []


class SwapOp(BaseModel):
    op: Literal["swap"] = "swap"
    assignment_id_a: int
    assignment_id_b: int
    label: str | None = None
    preview_conflicts: list[dict[str, Any]] = []


class LockOp(BaseModel):
    op: Literal["lock", "unlock"]
    assignment_id: int
    label: str | None = None


class AddConstraintOp(BaseModel):
    op: Literal["add_constraint"] = "add_constraint"
    constraint: ProposedConstraint


class RemoveConstraintOp(BaseModel):
    op: Literal["remove_constraint"] = "remove_constraint"
    constraint_id: int
    label: str | None = None


class SetWeightOp(BaseModel):
    op: Literal["set_weight"] = "set_weight"
    constraint_id: int
    weight: int | None = None
    hardness: Literal["hard", "soft"] | None = None
    label: str | None = None


DiffOp = Annotated[
    MoveOp | SwapOp | LockOp | AddConstraintOp | RemoveConstraintOp | SetWeightOp,
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
    status: str | None = None


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
