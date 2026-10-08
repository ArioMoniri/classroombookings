"""Ingestion Council blackboard: jobs, per-file/per-agent steps, typed artifacts (append-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utcnow


class CouncilJob(TimestampMixin, Base):
    """One onboarding run over N uploaded files.

    status: QUEUED -> RUNNING -> REVIEW (blocking review items) | READY -> COMMITTED; FAILED.
    ``files`` holds one entry per upload: index, filename, stored name, size, sha256, format, language,
    route (``fast:<shape>`` | ``general`` | ``vision`` | ``error``), status, message, record counts.
    """

    __tablename__ = "council_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    mode: Mapped[str] = mapped_column(String(16), default="auto")  # auto | general
    ai_mode: Mapped[str] = mapped_column(String(16), default="heuristic")  # llm | heuristic
    lang: Mapped[str] = mapped_column(String(8), default="en")
    year_hint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files: Mapped[list[Any]] = mapped_column(JSON, default=list)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    commits: Mapped[list[Any]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CouncilStep(Base):
    """One agent working on one file (``file_index``) or on all files (``file_index`` NULL)."""

    __tablename__ = "council_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("council_jobs.id", ondelete="CASCADE"), index=True)
    file_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent: Mapped[str] = mapped_column(String(32))  # intake | router | structure | extract | ...
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")  # RUNNING | DONE | SKIPPED | FAILED
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CouncilArtifact(Base):
    """Typed output of a step (rendered summary, structure, records, rules, dataset, plan, issues, review,
    commit). Append-only: a re-run or a review edit adds a newer artifact; the latest one per
    (job, file, kind) is current, the older ones are the audit trail."""

    __tablename__ = "council_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("council_jobs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[int | None] = mapped_column(ForeignKey("council_steps.id", ondelete="SET NULL"), nullable=True)
    file_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
