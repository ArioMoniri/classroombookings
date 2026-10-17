"""P2 conflict resolver after publishing (docs/product/booking-enhancements.md §4.4).

``booking_conflicts``: one row per (published run, booking) whose slot the run's timetable now holds. Rows are
written by :func:`app.services.booking_conflicts.detect` when a run is activated (``run.activate``) and closed by the
resolver (``RESOLVED`` with the action taken, or ``IGNORED`` for an administrator's override, a clash that went away
or a plan another published run replaced).
"""

from __future__ import annotations

from datetime import date as date_
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

OPEN = "OPEN"
RESOLVED = "RESOLVED"
IGNORED = "IGNORED"


class BookingConflict(Base):
    __tablename__ = "booking_conflicts"
    __table_args__ = (
        UniqueConstraint("run_id", "booking_id", name="uq_booking_conflicts_run_booking"),
        Index("ix_booking_conflicts_run_status", "run_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("schedule_runs.id", ondelete="CASCADE"))
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: the booking's slot when the clash was found
    room_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[date_] = mapped_column(Date)
    start_period: Mapped[int] = mapped_column(Integer)
    end_period: Mapped[int] = mapped_column(Integer)
    #: what holds the slot in the published timetable: {assignment_id, label, start_period, end_period}
    held: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(10), default=OPEN)
    #: {action, option_id, scope, reason, booking_ids, to, by, at}
    resolution: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
