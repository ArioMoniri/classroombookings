"""Reference data: terms, weeks, buildings, rooms, faculties, programs, instructors, courses."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Term(TimestampMixin, Base):
    __tablename__ = "terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # 2026-BAHAR
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="REGULAR")  # REGULAR, FINAL, BUT, SUMMER
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    week_count: Mapped[int] = mapped_column(Integer, default=14)
    periods_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)  # grid definition
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_crbs_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    weeks: Mapped[list[Week]] = relationship(back_populates="term", cascade="all, delete-orphan")


class Week(Base):
    __tablename__ = "weeks"
    __table_args__ = (UniqueConstraint("term_id", "index", name="uq_weeks_term_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="LECTURE")  # LECTURE, EXAM, HOLIDAY, MAKEUP
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    term: Mapped[Term] = relationship(back_populates="weeks")


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(128))

    rooms: Mapped[list[Room]] = relationship(back_populates="building")


class Room(TimestampMixin, Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # A101 canonical
    display_name: Mapped[str] = mapped_column(String(64))  # A 101
    floor: Mapped[str | None] = mapped_column(String(8), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    exam_capacity: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)  # TIP, PC, LAB, AMPHI
    is_bookable: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    legacy_crbs_room_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    room_group: Mapped[str | None] = mapped_column(String(64), nullable=True)  # legacy CRBS group label
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    pos: Mapped[int] = mapped_column(Integer, default=0)
    # CRBS parity: booking-side room properties (docs/CRBS_PARITY.md)
    room_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("room_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)

    building: Mapped[Building | None] = relationship(back_populates="rooms")


class Faculty(Base):
    __tablename__ = "faculties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int | None] = mapped_column(ForeignKey("faculties.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_evening: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_crbs_department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # CRBS parity: a programme is the CRBS "department" users and bookings belong to
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)

    faculty: Mapped[Faculty | None] = relationship()


class Instructor(Base):
    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # MAT112
    display_code: Mapped[str] = mapped_column(String(32))  # MAT 112
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    t_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    u_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    l_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits: Mapped[float | None] = mapped_column(Float, nullable=True)
    ects: Mapped[float | None] = mapped_column(Float, nullable=True)
