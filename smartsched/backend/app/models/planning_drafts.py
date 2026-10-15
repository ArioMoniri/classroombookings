"""Phase 19 backend gaps (docs/design/v2/phase19-program-wizard.md P19-W-01, phase19-priority-policy.md P19-P-04).

* ``program_drafts``: the program wizard's server-side draft, one JSON payload per user + target term. Autosaved
  (``PATCH`` with a path, last write wins per field, ``meta.paths`` remembers who wrote each path at which
  version), resumable from the "Taslaklar" list, and never touching the term: only ``commit`` writes the
  programme, its courses, people, sections and meeting requests, in one transaction
  (``app/services/program_drafts.py``).
* ``priority_overrides``: the coordinator priority of a person (instructor) or a programme for one term. The
  effective priority of a request is the most specific one set: request > section > person > programme > 0
  (``app/services/solver_bridge.stored_priorities``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

DRAFT_STATUSES = ("draft", "committed")
PRIORITY_SUBJECTS = ("person", "program")


class ProgramDraft(Base):
    __tablename__ = "program_drafts"
    __table_args__ = (
        Index("ix_program_drafts_owner_term", "owner_id", "term_id"),
        Index("ix_program_drafts_term_status", "term_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    #: the programme name once typed (the resume list's title)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: the step the coordinator left on ("Kaldığınız yer")
    step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    #: {"paths": {path: {"v": version, "by": user id, "at": iso}}} for the per-field merge
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    #: after commit: the programme it created and the ``program.create`` audit event (the undo handle)
    program_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_audit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PriorityOverride(Base):
    __tablename__ = "priority_overrides"
    __table_args__ = (
        UniqueConstraint("term_id", "subject_type", "subject_id", name="uq_priority_overrides_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"))
    #: person (instructor id) | program (programme id)
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


__all__ = ["DRAFT_STATUSES", "PRIORITY_SUBJECTS", "PriorityOverride", "ProgramDraft"]
