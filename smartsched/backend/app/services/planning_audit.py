"""Audit rows for planning edits (review 2026-10-15 D5 / P19-02).

Bookings and the administration tables were already audited (P7); the planning side was not: request edits,
manual moves (single, bulk, forced), locks and restores of a run's assignments. These helpers turn those edits
into ``audit_events`` rows with before/after through :func:`app.services.events.publish_event`, inside the
transaction of the change. A forced edit carries the conflicts it overrode in ``reason``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, AuditEvent, ScheduleRun, User
from app.services.audit import jsonable, snapshot
from app.services.events import Item, publish_event

ASSIGNMENT_FIELDS = (
    "run_id",
    "meeting_request_id",
    "exam_request_id",
    "week",
    "weeks",
    "day",
    "date",
    "start_period",
    "end_period",
    "room_ids",
    "is_locked",
    "origin",
)


def assignment_snapshot(a: Assignment) -> dict[str, Any]:
    return snapshot(a, ASSIGNMENT_FIELDS)


def snapshot_from_undo(s: Any) -> dict[str, Any]:
    """The before-state of an assignment from a calendar undo ``Snapshot`` (same keys as ``assignment_snapshot``
    where the snapshot holds them)."""
    data = s.model_dump() if hasattr(s, "model_dump") else dict(s)
    return {k: jsonable(v) for k, v in data.items() if k in ASSIGNMENT_FIELDS}


def changed_fields(obj: Any, data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(before, after) of the fields of ``data`` whose value differs from ``obj``'s current one."""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for k, v in data.items():
        old = jsonable(getattr(obj, k, None))
        new = jsonable(v)
        if old != new:
            before[k], after[k] = old, new
    return before, after


def forced_reason(conflicts: Iterable[Any]) -> str:
    msgs = [str(c.get("message") if isinstance(c, Mapping) else c) for c in conflicts]
    head = "; ".join(m for m in msgs[:5] if m)
    return f"forced despite {len(msgs)} conflict(s)" + (f": {head}" if head else "")


async def record_assignments(
    session: AsyncSession,
    action: str,
    run: ScheduleRun,
    items: list[Item],
    *,
    actor: User | None,
    reason: str | None = None,
    parent_after: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """One row for one assignment, else a parent on the run plus one child per assignment. Returns the row an
    override should cite (the single row, or the parent)."""
    if not items:
        return None
    if len(items) == 1:
        eid, before, after = items[0]
        return await publish_event(
            session,
            action,
            "assignment",
            eid,
            before=before,
            after=after,
            actor=actor,
            reason=reason,
            term_id=run.term_id,
        )
    return await publish_event(
        session,
        action,
        "run",
        run.id,
        items=items,
        item_type="assignment",
        parent_after=parent_after,
        actor=actor,
        reason=reason,
        term_id=run.term_id,
    )


__all__ = [
    "ASSIGNMENT_FIELDS",
    "assignment_snapshot",
    "changed_fields",
    "forced_reason",
    "record_assignments",
    "snapshot_from_undo",
]
