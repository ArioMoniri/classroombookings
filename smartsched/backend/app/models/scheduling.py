"""Sections, meeting/exam requests, blocks and constraint objects."""

from __future__ import annotations

from datetime import date as date_
from datetime import time
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.catalog import Course, Instructor, Program, Room, Term


class Section(TimestampMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("term_id", "source_key", name="uq_sections_term_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)  # şube
    class_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_years: Mapped[list[Any]] = mapped_column(JSON, default=list)
    semester_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrolment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="F2F")
    remote_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    whole_term_in_room: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_row: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_key: Mapped[str] = mapped_column(String(255))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    term: Mapped[Term] = relationship()
    course: Mapped[Course] = relationship()
    program: Mapped[Program | None] = relationship()
    instructors: Mapped[list[SectionInstructor]] = relationship(back_populates="section", cascade="all, delete-orphan")
    meeting_requests: Mapped[list[MeetingRequest]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class SectionInstructor(Base):
    __tablename__ = "section_instructors"

    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("instructors.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="PRIMARY")

    section: Mapped[Section] = relationship(back_populates="instructors")
    instructor: Mapped[Instructor] = relationship()


class MeetingRequest(TimestampMixin, Base):
    __tablename__ = "meeting_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days: Mapped[list[Any]] = mapped_column(JSON, default=list)  # candidate days when flexible
    start_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    weeks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    requested_room_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_room_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    requested_building: Mapped[str | None] = mapped_column(String(16), nullable=True)
    requested_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    requested_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flexible_day: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_room: Mapped[bool] = mapped_column(Boolean, default=True)
    definitive_room_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    definitive_room_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="NEW")  # NEW, PARSED, NEEDS_REVIEW, LOCKED
    parse_warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    source_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    section: Mapped[Section] = relationship(back_populates="meeting_requests")


class ExamRequest(TimestampMixin, Base):
    __tablename__ = "exam_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"), nullable=True)
    course_code: Mapped[str] = mapped_column(String(32), index=True)
    course_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"), nullable=True, index=True)
    faculty_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    class_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_years: Mapped[list[Any]] = mapped_column(JSON, default=list)
    enrolment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instructor_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    date_end: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    start_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_venue_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_room_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    requested_building: Mapped[str | None] = mapped_column(String(16), nullable=True)
    requested_room_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_min_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    invigilators_requested: Mapped[int | None] = mapped_column(Integer, nullable=True)
    on_campus_written: Mapped[bool] = mapped_column(Boolean, default=False)
    no_exam: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_room: Mapped[bool] = mapped_column(Boolean, default=True)
    definitive_room_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    definitive_room_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    merge_key: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="NEW")
    parse_warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_row: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    source_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    term: Mapped[Term] = relationship()
    program: Mapped[Program | None] = relationship()


class Block(TimestampMixin, Base):
    """Pre-occupied room slots (prep school, distance-ed, events, legacy bookings)."""

    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    start_period: Mapped[int] = mapped_column(Integer)
    end_period: Mapped[int] = mapped_column(Integer)
    weeks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(255))
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="ADMIN")  # GRID_IMPORT, ADMIN, CRBS
    source_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    term: Mapped[Term] = relationship()
    room: Mapped[Room] = relationship()


#: allowed ``constraints.source`` values (``BUILTIN`` rows are read-only switches of always-on rules)
CONSTRAINT_SOURCES = ("FILE", "ADMIN", "AI", "UPLOAD", "BUILTIN")


class ConstraintRow(TimestampMixin, Base):
    __tablename__ = "constraints"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    hardness: Mapped[str] = mapped_column(String(8), default="soft")  # hard | soft
    weight: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(8), default="ADMIN")  # FILE, ADMIN, AI, UPLOAD, BUILTIN
    #: provenance: {"file", "sheet", "row"|"paragraph"|"page"|"line", "excerpt"} for UPLOAD rows,
    #: {"draft_id"} for BUILTIN rows (built-in rule switched off in one studio draft),
    #: {"copied_from": {...}} / {"preset_id"} for copied / preset rules
    source_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    nl_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
