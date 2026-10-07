"""Schedule runs, assignments and chat messages."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class ScheduleRun(Base):
    __tablename__ = "schedule_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8), default="COURSE")  # COURSE | EXAM
    horizon: Mapped[str] = mapped_column(String(8), default="TERM")  # WEEK | MONTH | TERM
    horizon_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    objective_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    soft_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hard_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    diagnosis: Mapped[list[Any]] = mapped_column(JSON, default=list)
    parent_run_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_runs.id"), nullable=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    assignments: Mapped[list[Assignment]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("schedule_runs.id", ondelete="CASCADE"), index=True)
    meeting_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("meeting_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    exam_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    week: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # null = all weeks in pattern
    weeks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    day: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_period: Mapped[int] = mapped_column(Integer)
    end_period: Mapped[int] = mapped_column(Integer)
    room_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)  # ordered
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    course_codes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    origin: Mapped[str] = mapped_column(String(8), default="SOLVER")  # SOLVER, AI_EDIT, MANUAL, IMPORT
    source_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    run: Mapped[ScheduleRun] = relationship(back_populates="assignments")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("schedule_runs.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
