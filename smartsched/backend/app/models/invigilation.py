"""Invigilator assignment for exam runs (``app/services/invigilation.py``, ``app/solver/invigilation.py``).

* ``invigilator_pool``: who may invigilate besides the course instructors, and the per-person rules of anyone in the
  pool (an instructor row carries their unavailability and limits): staff / research assistants, unavailability,
  duty limits, a load factor; ``term_id`` null = every term;
* ``invigilation_plans``: one solve of an exam run (status, scores, diagnosis, params, parent plan for a re-run,
  at most one published plan per exam run);
* ``invigilation_duties``: one person at one post (a room at one time of one date) of a plan; ``is_locked`` duties
  are kept by the next re-run.
"""

from __future__ import annotations

from datetime import date as date_
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

POOL_KINDS = ("STAFF", "ASSISTANT", "INSTRUCTOR", "OTHER")


class InvigilatorPoolMember(Base):
    __tablename__ = "invigilator_pool"
    __table_args__ = (Index("ix_invigilator_pool_term_canonical", "term_id", "canonical_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), nullable=True, index=True)
    instructor_id: Mapped[int | None] = mapped_column(
        ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    canonical_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default="STAFF")  # STAFF | ASSISTANT | INSTRUCTOR | OTHER
    max_duties: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: percent of the average share this person is expected to take (200 = twice)
    load_factor: Mapped[int] = mapped_column(Integer, default=100)
    #: [{"date": "2026-06-03"} | {"day": 1..7}, "start_period"?, "end_period"?, "note"?]; no period = the whole day
    unavailable: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: false: never drawn (also excludes the linked instructor from the instructor pool)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class InvigilationPlan(Base):
    __tablename__ = "invigilation_plans"
    __table_args__ = (
        Index(
            "uq_invigilation_plans_active",
            "exam_run_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    exam_run_id: Mapped[int] = mapped_column(ForeignKey("schedule_runs.id", ondelete="CASCADE"), index=True)
    parent_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("invigilation_plans.id", ondelete="SET NULL"), nullable=True
    )
    #: QUEUED | RUNNING | OPTIMAL | FEASIBLE | INFEASIBLE | FAILED
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    diagnosis: Mapped[list[Any]] = mapped_column(JSON, default=list)
    hard_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soft_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # the queue job's liveness beat and its last reported phase / percentage (alembic 0033)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    progress_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)

    duties: Mapped[list[InvigilationDuty]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class InvigilationDuty(Base):
    __tablename__ = "invigilation_duties"
    __table_args__ = (Index("ix_invigilation_duties_plan_post", "plan_id", "post_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("invigilation_plans.id", ondelete="CASCADE"), index=True)
    post_key: Mapped[str] = mapped_column(String(64))
    date: Mapped[date_] = mapped_column(Date, index=True)
    start_period: Mapped[int] = mapped_column(Integer)
    end_period: Mapped[int] = mapped_column(Integer)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    exam_request_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: "INS:<instructor id>" | "STAFF:<pool id>"
    person_key: Mapped[str] = mapped_column(String(32), index=True)
    person_name: Mapped[str] = mapped_column(String(255))
    instructor_id: Mapped[int | None] = mapped_column(
        ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("invigilator_pool.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    origin: Mapped[str] = mapped_column(String(8), default="SOLVER")  # SOLVER | LOCK | MANUAL

    plan: Mapped[InvigilationPlan] = relationship(back_populates="duties")
