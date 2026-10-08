"""CRBS (classroombookings) parity: roles/permissions, room groups/ACL/custom fields, booking calendar
(schedules, periods, timetable weeks, holidays) and bookings. Mapping: docs/CRBS_PARITY.md §3.

Reused tables: ``users`` (role/department/username columns), ``rooms`` (group/owner/location/icon),
``programs`` (= CRBS departments), ``terms`` (= CRBS sessions), ``settings``.
"""

from __future__ import annotations

from datetime import date as date_
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

# --------------------------------------------------------------------------------------------------
# Roles and permissions (auth_roles, auth_permissions, auth_roles_permissions, users_constraints)
# --------------------------------------------------------------------------------------------------


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: ADMIN / PLANNER / VIEWER / TEACHER for the seeded roles; NULL for custom roles
    code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_active_bookings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    range_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    range_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recur_max_instances: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    permissions: Mapped[list[Permission]] = relationship(secondary="role_permissions", lazy="selectin")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)  # group.action
    group: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class UserConstraint(Base):
    """Per-user override of the role's booking limits: type R = role value, U = user value, X = unlimited."""

    __tablename__ = "user_constraints"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    max_active_bookings_type: Mapped[str] = mapped_column(String(1), default="R")
    max_active_bookings_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    range_min_type: Mapped[str] = mapped_column(String(1), default="R")
    range_min_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    range_max_type: Mapped[str] = mapped_column(String(1), default="R")
    range_max_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recur_max_instances_type: Mapped[str] = mapped_column(String(1), default="R")
    recur_max_instances_value: Mapped[int | None] = mapped_column(Integer, nullable=True)


# --------------------------------------------------------------------------------------------------
# Rooms: groups, custom fields, ACL
# --------------------------------------------------------------------------------------------------


class RoomGroup(Base):
    __tablename__ = "room_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pos: Mapped[int] = mapped_column(Integer, default=0)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class RoomCustomField(Base):
    __tablename__ = "room_custom_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    #: CRBS: TEXT | CHECKBOX | SELECT; typed features (P10, ``app/services/rooms_features.py``): BOOLEAN | NUMBER |
    #: MULTISELECT as well (CHECKBOX is an alias of BOOLEAN)
    type: Mapped[str] = mapped_column(String(16))
    pos: Mapped[int] = mapped_column(Integer, default=0)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # --- P10 typed features (alembic 0007_room_features)
    filterable: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    public: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # NUMBER only, e.g. "adet"
    #: mirrored into ``rooms.tags`` (the solver's vocabulary: PC, TIP, LAB, AMPHI ...) when the value is true
    solver_tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)  # av|seating|accessibility|lab|other

    options: Mapped[list[RoomCustomFieldOption]] = relationship(
        cascade="all, delete-orphan", order_by="RoomCustomFieldOption.pos", lazy="selectin"
    )


class RoomCustomFieldOption(Base):
    __tablename__ = "room_custom_field_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("room_custom_fields.id", ondelete="CASCADE"), index=True)
    value: Mapped[str] = mapped_column(String(64))
    pos: Mapped[int] = mapped_column(Integer, default=0)


class RoomCustomFieldValue(Base):
    __tablename__ = "room_custom_field_values"
    __table_args__ = (
        UniqueConstraint("room_id", "field_id", name="uq_room_field_value"),
        Index("ix_room_field_values_field_num", "field_id", "value_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("room_custom_fields.id", ondelete="CASCADE"), index=True)
    #: TEXT: the text; CHECKBOX / BOOLEAN: "1"/"0"; SELECT: the option id; NUMBER: the number as text
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: NUMBER: the value (filterable with >= / <=)
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: MULTISELECT: list of option ids
    value_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)


class RoomAcl(Base):
    """Booking permissions granted on a room or room group to a user, role or department."""

    __tablename__ = "room_acl"
    __table_args__ = (Index("ix_room_acl_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # room | room_group
    entity_id: Mapped[int] = mapped_column(Integer)
    context_type: Mapped[str] = mapped_column(String(16))  # user | role | department
    context_id: Mapped[int] = mapped_column(Integer)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    permissions: Mapped[list[Permission]] = relationship(secondary="room_acl_permissions", lazy="selectin")


class RoomAclPermission(Base):
    __tablename__ = "room_acl_permissions"

    acl_id: Mapped[int] = mapped_column(ForeignKey("room_acl.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


# --------------------------------------------------------------------------------------------------
# Booking calendar: schedules, periods, term (session) settings, timetable weeks, dates, holidays
# --------------------------------------------------------------------------------------------------


class BookingSchedule(Base):
    __tablename__ = "booking_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(20), default="periods")
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    periods: Mapped[list[BookingPeriod]] = relationship(
        cascade="all, delete-orphan", order_by="BookingPeriod.time_start", lazy="selectin"
    )


class BookingPeriod(Base):
    __tablename__ = "booking_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("booking_schedules.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(30))
    time_start: Mapped[time] = mapped_column(Time)
    time_end: Mapped[time] = mapped_column(Time)
    bookable: Mapped[bool] = mapped_column(Boolean, default=True)
    days: Mapped[list[Any]] = mapped_column(JSON, default=list)  # ISO weekdays 1..7
    #: the period's span on the 18-period university grid (shared with the solver)
    start_period: Mapped[int] = mapped_column(Integer)
    end_period: Mapped[int] = mapped_column(Integer)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class TermBookingSettings(Base):
    """CRBS session fields that ``terms`` lacks (1:1 with ``terms``; ``is_current`` = ``terms.is_active``)."""

    __tablename__ = "term_booking_settings"

    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), primary_key=True)
    is_selectable: Mapped[bool] = mapped_column(Boolean, default=True)
    default_schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("booking_schedules.id", ondelete="SET NULL"), nullable=True
    )


class TermSchedule(Base):
    """Schedule applied to a room group in a term (CRBS ``session_schedules``)."""

    __tablename__ = "term_schedules"

    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), primary_key=True)
    room_group_id: Mapped[int] = mapped_column(ForeignKey("room_groups.id", ondelete="CASCADE"), primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("booking_schedules.id", ondelete="CASCADE"))


class TimetableWeek(Base):
    """CRBS timetable week (rotation such as Week A / Week B), not a calendar week."""

    __tablename__ = "timetable_weeks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))
    bgcol: Mapped[str] = mapped_column(String(6))  # hex without '#'
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class TermDate(Base):
    """Date -> timetable week assignment of a term (CRBS ``dates.week_id``)."""

    __tablename__ = "term_dates"

    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date_] = mapped_column(Date, primary_key=True)
    timetable_week_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_weeks.id", ondelete="SET NULL"), nullable=True, index=True
    )


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    date_start: Mapped[date_] = mapped_column(Date)
    date_end: Mapped[date_] = mapped_column(Date)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


# --------------------------------------------------------------------------------------------------
# Bookings
# --------------------------------------------------------------------------------------------------

BOOKED = "BOOKED"
CANCELLED = "CANCELLED"
#: P1 approvals (``app/services/approvals.py``): a request waiting for a designated approver; it holds its slots only
#: while ``held_until`` lies ahead (the rule's ``hold_minutes``)
PENDING = "PENDING"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"
WITHDRAWN = "WITHDRAWN"


class _Audit:
    status: Mapped[str] = mapped_column(String(10), default=BOOKED, index=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class BookingSeries(_Audit, Base):
    """Recurring booking (CRBS ``bookings_repeat``): a period + room on one weekday of one timetable week."""

    __tablename__ = "booking_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("booking_periods.id", ondelete="CASCADE"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id", ondelete="SET NULL"), nullable=True)
    timetable_week_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_weeks.id", ondelete="SET NULL"), nullable=True
    )
    weekday: Mapped[int] = mapped_column(Integer)  # 1..7
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class MultiBooking(Base):
    """A selection of many grid slots that is turned into bookings in one go (CRBS ``multi_bookings``)."""

    __tablename__ = "multi_bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"))
    timetable_week_id: Mapped[int | None] = mapped_column(
        ForeignKey("timetable_weeks.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    slots: Mapped[list[MultiBookingSlot]] = relationship(
        cascade="all, delete-orphan", order_by="MultiBookingSlot.id", lazy="selectin"
    )


class MultiBookingSlot(Base):
    __tablename__ = "multi_booking_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    mb_id: Mapped[int] = mapped_column(ForeignKey("multi_bookings.id", ondelete="CASCADE"), index=True)
    date: Mapped[date_] = mapped_column(Date)
    period_id: Mapped[int] = mapped_column(ForeignKey("booking_periods.id", ondelete="CASCADE"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))


class Booking(_Audit, Base):
    __tablename__ = "bookings"
    __table_args__ = (Index("ix_bookings_room_date", "room_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("booking_series.id", ondelete="CASCADE"), nullable=True, index=True
    )
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("booking_periods.id", ondelete="CASCADE"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id", ondelete="SET NULL"), nullable=True)
    date: Mapped[date_] = mapped_column(Date, index=True)
    #: span on the 18-period grid, copied from the period when booked
    start_period: Mapped[int] = mapped_column(Integer)
    end_period: Mapped[int] = mapped_column(Integer)
    multi_booking_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: id of the row in a migrated CRBS database (``app/importers/crbs_legacy.py``; re-imports update it)
    legacy_crbs_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # --- T1 find-a-room (alembic 0008_find_room): what the booking was searched for (P2 ranks alternatives)
    headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_features: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    # --- P1 approvals (alembic 0010_approvals): a PENDING request holds its slots until this local time
    held_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BookingSlot(Base):
    """One row per grid period held by an active booking. The unique key is the DB-level guarantee that
    two bookings never hold the same room at the same time; rows are deleted when a booking is cancelled
    or moved."""

    __tablename__ = "booking_slots"
    __table_args__ = (UniqueConstraint("room_id", "date", "period", name="uq_booking_slots_room_date_period"),)

    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    date: Mapped[date_] = mapped_column(Date)


# --------------------------------------------------------------------------------------------------
# Auth support, notifications, translations
# --------------------------------------------------------------------------------------------------


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex; the token is never stored
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class NotificationOutbox(Base):
    """Every notification. ``SENT`` only after the SMTP server accepted it; ``UNSENT`` when no SMTP is
    configured; ``FAILED`` with the error otherwise."""

    __tablename__ = "notification_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    booking_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="UNSENT", index=True)  # UNSENT | SENT | FAILED
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Translation(Base):
    """Admin overrides of UI strings (CRBS ``lang`` table)."""

    __tablename__ = "translations"
    __table_args__ = (UniqueConstraint("language", "set", "key", name="uq_translations_lang_set_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(String(32))
    set: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
