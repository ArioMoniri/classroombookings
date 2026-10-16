"""Request bodies of ``/program-drafts`` (P19-W-01..W-08); responses are the documented dicts of
``app/services/program_drafts.py``."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DraftCreateIn(BaseModel):
    term_id: int
    #: the wizard state (snake_case or the wizard's camelCase keys); default empty
    payload: dict[str, Any] | None = None
    step: str | None = Field(default=None, max_length=32)


class DraftOp(BaseModel):
    #: dot path; list items by index, by their ``key`` or ``-`` (append): ``courses.c1.sections.-``
    path: str = Field(min_length=1, max_length=300)
    value: Any = None
    op: Literal["set", "remove"] = "set"


class DraftPatchIn(BaseModel):
    """One field (``path`` + ``value``), several (``ops``) or the whole ``payload``. ``base_version`` is the version
    the client last saw: field ops merge (last write wins, overwritten fields come back), a whole payload with a
    stale version is refused (409)."""

    path: str | None = Field(default=None, max_length=300)
    value: Any = None
    op: Literal["set", "remove"] = "set"
    ops: list[DraftOp] | None = Field(default=None, max_length=500)
    payload: dict[str, Any] | None = None
    base_version: int | None = None
    step: str | None = Field(default=None, max_length=32)


class PasteIn(BaseModel):
    step: Literal["courses", "sections"] = "courses"
    tsv: str = Field(max_length=200_000)


class CommitIn(BaseModel):
    #: none: write only; minimal: then a minimal-change re-solve of the published run (moderation preview)
    solve: Literal["none", "minimal"] = "none"


__all__ = ["CommitIn", "DraftCreateIn", "DraftOp", "DraftPatchIn", "PasteIn"]
