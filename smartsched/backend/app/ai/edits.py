"""Applying reviewed section edits (include / exclude / field changes) to the term's data.

Used by ``POST /terms/{id}/elicit/accept`` (file-ingestion proposals) and by the chat ``apply`` step.
Every section and room id is re-checked against the database; nothing the model or the browser
sent is trusted. Edits change term data (they affect every later run), which is why they are only
ever applied after the planner accepted them.

Semantics
* ``exclude``: every meeting request of the section stops needing a room (``needs_room = False``);
  the section, its requests and past runs are kept, so ``include`` restores it.
* ``include``: ``needs_room = True`` on the section's (non-archived) meeting requests.
* ``set_field``: ``enrolment`` / ``mode`` on the section (remote modes ONLINE/UZEM/ASYNC also set
  ``needs_room = False``, face-to-face modes set it back to ``True``); ``day`` / periods on the
  section's single meeting request (sections with several meetings must be moved per assignment);
  ``preferred_room_ids`` -> ``requested_room_ids`` of every meeting request.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers.normalize import PERIODS
from app.models import Room, Section
from app.schemas.ai import ProposedSectionEdit

REMOTE_MODES = frozenset({"ONLINE", "UZEM", "ASYNC"})
PERIODS_PER_DAY = len(PERIODS)


def blocking_issues(edit: ProposedSectionEdit) -> list[str]:
    issues = [f"unresolved {e.type} '{e.text}'" for e in edit.entities if e.resolved_id is None]
    if edit.status == "rejected":
        issues.append("edit was rejected")
    if not edit.section_ids:
        issues.append("no section targeted")
    if edit.op == "set_field" and not edit.changes.model_dump(exclude_none=True):
        issues.append("set_field without any change")
    return issues


async def apply_section_edits(
    session: AsyncSession, term_id: int, edits: list[ProposedSectionEdit], *, commit: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply accepted edits; returns ``(applied, rejected)`` with per-edit details."""
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for i, edit in enumerate(edits):
        issues = blocking_issues(edit)
        sections: list[Section] = []
        if not issues:
            sections = list(
                (
                    await session.execute(
                        select(Section)
                        .where(Section.id.in_(edit.section_ids), Section.term_id == term_id)
                        .options(selectinload(Section.meeting_requests), selectinload(Section.course))
                    )
                ).scalars()
            )
            missing = sorted(set(edit.section_ids) - {s.id for s in sections})
            if missing:
                issues.append(f"sections not in this term: {missing}")
        ch = edit.changes
        if not issues and ch.preferred_room_ids:
            found = set((await session.execute(select(Room.id).where(Room.id.in_(ch.preferred_room_ids)))).scalars())
            bad = [r for r in ch.preferred_room_ids if r not in found]
            if bad:
                issues.append(f"room ids do not exist: {bad}")
        if not issues and edit.op == "set_field" and (ch.day or ch.start_period or ch.end_period):
            for s in sections:
                active = [m for m in s.meeting_requests if not m.archived]
                if len(active) != 1:
                    issues.append(
                        f"{s.course.display_code} has {len(active)} meetings; move a single assignment instead"
                    )
        if issues:
            rejected.append({"index": i, "op": edit.op, "issues": issues})
            continue
        changed: list[str] = []
        for s in sections:
            active = [m for m in s.meeting_requests if not m.archived]
            label = f"{s.course.display_code}{' §' + s.label if s.label else ''}"
            if edit.op in ("include", "exclude"):
                for m in active:
                    m.needs_room = edit.op == "include"
                changed.append(f"{label}: {'included' if edit.op == 'include' else 'excluded'}")
                continue
            if ch.enrolment is not None:
                s.enrolment = ch.enrolment
                changed.append(f"{label}: enrolment={ch.enrolment}")
            if ch.mode is not None:
                s.mode = ch.mode
                for m in active:
                    m.needs_room = ch.mode not in REMOTE_MODES
                changed.append(f"{label}: mode={ch.mode}")
            if ch.preferred_room_ids is not None:
                for m in active:
                    m.requested_room_ids = list(ch.preferred_room_ids)
                changed.append(f"{label}: preferred rooms={ch.preferred_room_ids}")
            if ch.day or ch.start_period or ch.end_period:
                m = active[0]
                start = ch.start_period or m.start_period or 1
                duration = (m.end_period - m.start_period) if m.end_period and m.start_period else 0
                end = ch.end_period or min(PERIODS_PER_DAY, start + duration)
                if end < start:
                    rejected.append({"index": i, "op": edit.op, "issues": [f"{label}: end period before start"]})
                    continue
                if ch.day:
                    m.day = ch.day
                    m.days = [ch.day]
                m.start_period, m.end_period = start, end
                m.start_time, m.end_time = PERIODS[start - 1].start, PERIODS[end - 1].end
                changed.append(f"{label}: day={m.day} P{start}-P{end}")
        applied.append({"index": i, "op": edit.op, "section_ids": [s.id for s in sections], "changes": changed})
    if commit and applied:
        await session.commit()
    elif applied:
        await session.flush()
    return applied, rejected


__all__ = ["REMOTE_MODES", "apply_section_edits", "blocking_issues"]
