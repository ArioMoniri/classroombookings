"""Adaptive scheduling tables (docs/research/2026-10-17-adaptive-scheduling.md; AS-03, AS-05; one shared migration).

* ``season_profiles``: versioned per-season configuration a run and the booking rules pick up. A row applies to
  ``applies_to`` = ``[{"season": BAHAR|GUZ|YAZ|FINAL|BUT|*, "period_kind": LECTURE|EXAM|...|*}]`` and carries a
  sparse override of the solver weights, booking-policy overlays and the peak threshold. Status ``draft`` →
  ``active`` (one active version per key; activating retires the previous one) → ``retired``. Editing an active
  profile makes a new draft version (``parent_id``); "Geri al" re-activates the parent. The built-in profiles
  (``standard``, ``exam_week``) live in code (``app/services/seasons.py``), not in this table.
* ``season_segments``: admin-defined period segments of a term (add/drop, midterm weeks ...) that nothing in the
  imported data marks; ``status = draft`` for segments proposed after an import (AS-18), ``active`` once approved.
* ``demand_events``: the find-room / booking demand ledger. **Aggregate only (KVKK):** no user id, no free text,
  only the time cell, a headcount band, the requested features, the building filter, the number of results and
  the outcome. Purged after ``demand.retention_days`` (default 400) by the daily KVKK purge.

None of these tables holds per-person rows, so none of them gets a row-level-security policy (``app/core/rls.py``,
alembic 0035): the RLS role reaches them through the default privileges, like the other catalogue tables.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utcnow

PROFILE_STATUSES = ("draft", "active", "retired")
#: period kinds of a term's calendar (``seasons.periods``); ``*`` in ``applies_to`` matches every kind
PERIOD_KINDS = ("LECTURE", "ADD_DROP", "MIDTERM", "EXAM", "MAKEUP", "HOLIDAY", "SUMMER", "BREAK")
SEASONS = ("BAHAR", "GUZ", "YAZ", "FINAL", "BUT")
DEMAND_OUTCOMES = ("searched", "booked", "none")


class SeasonProfile(TimestampMixin, Base):
    __tablename__ = "season_profiles"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_season_profiles_key_version"),
        Index("ix_season_profiles_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name_tr: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str] = mapped_column(String(128))
    applies_to: Mapped[list[Any]] = mapped_column(JSON, default=list)
    solver_weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    booking_overlays: Mapped[list[Any]] = mapped_column(JSON, default=list)
    peak_threshold_pct: Mapped[int] = mapped_column(SmallInteger, default=85)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    #: the version this one was made from (an edit of an active profile, a learned proposal)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("season_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: admin | learned (AS-14 weight learning) | proposed (a draft offered by the product, e.g. the PC-lab cap)
    origin: Mapped[str] = mapped_column(String(16), default="admin")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: {"tr": ..., "en": ...}: why the profile exists (a learned draft says which evidence moved which weight)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    #: the numbers behind a learned or proposed draft (run ids, counts, deltas; never a person's name)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SeasonSegment(TimestampMixin, Base):
    __tablename__ = "season_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # one of PERIOD_KINDS
    week_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    label_tr: Mapped[str] = mapped_column(String(128))
    label_en: Mapped[str] = mapped_column(String(128))
    #: draft (proposed after an import, AS-18) | active (an admin's segment)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class DemandEvent(Base):
    """One find-room search or booking, as an aggregate cell. No user id and no free text (KVKK)."""

    __tablename__ = "demand_events"
    __table_args__ = (
        Index("ix_demand_events_ts", "ts"),
        Index("ix_demand_events_cell", "term_id", "weekday", "start_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="SET NULL"), nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekday: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    start_period: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    end_period: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    period_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    headcount_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: required room features (tag codes / feature keys), sorted
    features: Mapped[list[Any]] = mapped_column(JSON, default=list)
    building: Mapped[str | None] = mapped_column(String(16), nullable=True)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(16), default="searched")
    #: find_room | booking
    source: Mapped[str] = mapped_column(String(16), default="find_room")


__all__ = [
    "DEMAND_OUTCOMES",
    "PERIOD_KINDS",
    "PROFILE_STATUSES",
    "SEASONS",
    "DemandEvent",
    "SeasonProfile",
    "SeasonSegment",
]
