"""P7 audit log responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: int
    ts: str | None
    actor_type: str
    actor_id: int | None
    actor_label: str | None
    action: str
    entity_type: str
    entity_id: str | None
    term_id: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    #: {field: [old, new]} for updates
    diff: dict[str, Any] | None
    reason: str | None
    reversible: bool
    undo_of: int | None
    parent_id: int | None
    #: an undo event points at this one
    undone: bool = False
    #: only with audit.view
    request_id: str | None = None
    ip_hash: str | None = None
    children: list[dict[str, Any]] | None = None


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    #: pass as ``cursor`` for the next (older) page; null on the last page
    next_cursor: int | None


class UndoOut(BaseModel):
    undone: int
    action: str
    booking_ids: list[int]
