"""P8 booking policies (docs/product/booking-enhancements.md §P8, ROADMAP Phase 17).

``booking_policies``: one rule per row, applied to the rooms of its scope (every room, one room, a room group or a
room type = solver tag such as ``TIP`` / ``PC``) and to the users of its roles (empty = every role). A rule can
limit the notice in working days (holidays aware), how far ahead a booking may be made, the duration of one
person's back-to-back bookings in a room, the active bookings per user, a buffer between bookings, quiet hours on
weekdays and blackout dates. ``effect`` is ``refuse`` (409 with a Turkish and an English reason) or ``request``
(the booking becomes an approval request, P1). No rule exists by default, so bookings behave as in CRBS until an
administrator adds one. Exam-period mode is a setting (group ``policies``), not a row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class BookingPolicy(Base):
    __tablename__ = "booking_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    #: a rule of one term only (None = every term)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(16), default="all")  # all | room | room_group | tag
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: role codes the rule applies to (ADMIN, PLANNER, TEACHER, VIEWER or a custom role's code); [] = everyone
    role_codes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    effect: Mapped[str] = mapped_column(String(10), default="refuse")  # refuse | request
    min_notice_workdays: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_advance_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_active_bookings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buffer_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: [{"weekdays": [1..7], "start": "HH:MM", "end": "HH:MM"}]; start > end wraps past midnight
    quiet_hours: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: [{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "label": "..."}]
    blackouts: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: shown to users next to the refusal ("Neden?")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
