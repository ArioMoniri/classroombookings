"""AI-layer records that are not solver input.

``ai_proposal_decisions``: one row per reviewed AI / upload / learned proposal and what happened to it
(``accepted`` with the created constraint, ``rejected`` by the server with the reasons, ``declined`` by the
planner in review). The learning lane reads it; the solver never does. Rows are ordinary (deletable) rows so a
KVKK erasure or a memory reset can remove them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class AIProposalDecision(Base):
    __tablename__ = "ai_proposal_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    decision: Mapped[str] = mapped_column(String(16), index=True)  # accepted | rejected | declined
    kind: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    hardness: Mapped[str] = mapped_column(String(8))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(16))  # AI | UPLOAD | LEARNED
    source_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    nl_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # the proposal's review status
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    constraint_id: Mapped[int | None] = mapped_column(ForeignKey("constraints.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # no FK: outlives the account
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
