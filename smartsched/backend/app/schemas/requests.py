from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel

from app.schemas.common import ORMModel


class MeetingRequestOut(ORMModel):
    id: int
    section_id: int
    day: int | None
    days: list[Any]
    start_period: int | None
    end_period: int | None
    start_time: dt.time | None
    end_time: dt.time | None
    weeks: list[Any]
    requested_room_text: str | None
    requested_room_ids: list[Any]
    requested_building: str | None
    requested_tags: list[Any]
    requested_capacity: int | None
    flexible_day: bool
    needs_room: bool
    definitive_room_text: str | None
    definitive_room_ids: list[Any]
    status: str
    parse_warnings: list[Any]
    notes: str | None
    archived: bool
    source_row_index: int | None
    course_code: str | None = None
    course_name: str | None = None
    section_label: str | None = None
    program_name: str | None = None
    enrolment: int | None = None
    mode: str | None = None
    instructors: list[str] = []


class MeetingRequestUpdate(BaseModel):
    day: int | None = None
    days: list[int] | None = None
    start_period: int | None = None
    end_period: int | None = None
    weeks: list[int] | None = None
    requested_room_ids: list[int] | None = None
    requested_building: str | None = None
    requested_tags: list[str] | None = None
    requested_capacity: int | None = None
    flexible_day: bool | None = None
    needs_room: bool | None = None
    definitive_room_ids: list[int] | None = None
    definitive_room_text: str | None = None
    status: str | None = None
    notes: str | None = None
    archived: bool | None = None


class CheckRoomIn(BaseModel):
    room_ids: list[int]


class CheckRoomOut(BaseModel):
    ok: bool
    conflicts: list[dict[str, Any]]


class ExamRequestOut(ORMModel):
    id: int
    term_id: int
    course_code: str
    course_name: str | None
    program_id: int | None
    faculty_text: str | None
    class_year: int | None
    class_years: list[Any]
    enrolment: int | None
    instructor_text: str | None
    date: dt.date | None
    date_end: dt.date | None
    start_time: dt.time | None
    end_time: dt.time | None
    start_period: int | None
    end_period: int | None
    requested_venue_text: str | None
    requested_room_ids: list[Any]
    requested_building: str | None
    requested_room_count: int | None
    requested_min_capacity: int | None
    requested_tags: list[Any]
    invigilators_requested: int | None
    on_campus_written: bool
    no_exam: bool
    needs_room: bool
    definitive_room_text: str | None
    definitive_room_ids: list[Any]
    merge_key: str | None
    status: str
    parse_warnings: list[Any]
    notes: str | None
    archived: bool
    program_name: str | None = None


class ExamRequestUpdate(BaseModel):
    date: dt.date | None = None
    start_period: int | None = None
    end_period: int | None = None
    requested_room_ids: list[int] | None = None
    requested_room_count: int | None = None
    requested_min_capacity: int | None = None
    requested_tags: list[str] | None = None
    needs_room: bool | None = None
    definitive_room_ids: list[int] | None = None
    definitive_room_text: str | None = None
    merge_key: str | None = None
    status: str | None = None
    notes: str | None = None
    archived: bool | None = None


class ExamCohortOut(BaseModel):
    merge_key: str
    course_code: str
    course_name: str | None
    date: dt.date | None
    start_period: int | None
    end_period: int | None
    start_time: dt.time | None
    end_time: dt.time | None
    enrolment: int
    programs: list[str]
    request_ids: list[int]
    definitive_room_ids: list[int]
    status: str
