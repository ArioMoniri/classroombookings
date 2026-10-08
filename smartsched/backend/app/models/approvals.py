"""P1 approval workflows (docs/product/booking-enhancements.md §4.3 and the user's decisions of 2026-10-08).

* ``approver_scopes``: administrators designated as approvers when their account is created ("approves for":
  every room, room groups, rooms, or room types = solver tags such as TIP / PC).
* ``approval_rules``: a room, room group or room type (tag) that requires approval, with its steps, an optional
  tentative hold, a lead time and an expiry. No rule exists by default, so bookings behave exactly like CRBS until
  an administrator adds one.
* ``approval_requests``: one per PENDING booking or series, with a snapshot of the rule it was created under.
* ``approval_decisions``: every approve / reject (with an optional suggested alternative).
* ``inapp_notifications``: the shell's notification list (requester and approvers), next to the e-mail outbox.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class ApproverScope(Base):
    __tablename__ = "approver_scopes"
    __table_args__ = (Index("ix_approver_scopes_scope", "scope_type", "scope_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope_type: Mapped[str] = mapped_column(String(16))  # all | room | room_group | tag
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ApprovalRule(Base):
    __tablename__ = "approval_rules"
    __table_args__ = (Index("ix_approval_rules_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # room | room_group | tag
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), nullable=True)
    #: [{"approvers": {"type": "designated"} | {"type": "users", "ids": [..]}, "min_approvals": 1}, ...]
    steps: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: > 0: a request holds its slots tentatively for this many minutes (never past the booking's start)
    hold_minutes: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_workdays: Mapped[int] = mapped_column(Integer, default=0)
    #: the request expires this many minutes before the booking starts
    expires_before_start_minutes: Mapped[int] = mapped_column(Integer, default=0)
    allow_self_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("booking_series.id", ondelete="CASCADE"), nullable=True, index=True
    )
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), nullable=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("approval_rules.id", ondelete="SET NULL"), nullable=True)
    #: the rule as it was when the request was made (a later edit of the rule does not change open requests)
    rule_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    step: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(10), default="PENDING", index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    #: local time (Europe/Istanbul, like booking dates) at which the request expires
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # the last decision's note, for the requester
    #: a rejection's suggested alternative {room_id, date, start_period, end_period, ...}
    suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True)
    step: Mapped[int] = mapped_column(Integer)
    approver_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision: Mapped[str] = mapped_column(String(10))  # APPROVED | REJECTED
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternative: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InAppNotification(Base):
    __tablename__ = "inapp_notifications"
    __table_args__ = (Index("ix_inapp_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))  # approval.requested | approval.decided | approval.expired ...
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    booking_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
