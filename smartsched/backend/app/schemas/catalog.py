from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel

TERM_KIND = "^(REGULAR|FINAL|BUT|SUMMER)$"


def _check_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise ValueError("end_date is before start_date")


class TermIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=128)
    kind: str = Field(default="REGULAR", pattern=TERM_KIND)
    start_date: date | None = None
    end_date: date | None = None
    week_count: int = Field(default=14, ge=1, le=60)
    periods_json: list[Any] | None = None
    is_active: bool = False

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = " ".join(v.replace("\xa0", " ").split())  # NBSP / stray spaces from copy-paste
        if not v:
            raise ValueError("code must not be blank")
        return v

    @model_validator(mode="after")
    def _dates(self) -> TermIn:
        _check_dates(self.start_date, self.end_date)
        return self


class TermUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    kind: str | None = Field(default=None, pattern=TERM_KIND)
    start_date: date | None = None
    end_date: date | None = None
    week_count: int | None = Field(default=None, ge=1, le=60)
    periods_json: list[Any] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _dates(self) -> TermUpdate:
        _check_dates(self.start_date, self.end_date)
        return self


class TermOut(ORMModel):
    id: int
    code: str
    name: str
    kind: str
    start_date: date | None
    end_date: date | None
    week_count: int
    periods_json: list[Any] | None
    is_active: bool


class WeekIn(BaseModel):
    index: int
    start_date: date | None = None
    kind: str = "LECTURE"
    label: str | None = None


class WeekOut(ORMModel):
    id: int
    term_id: int
    index: int
    start_date: date | None
    kind: str
    label: str | None


class BuildingIn(BaseModel):
    code: str
    name: str


class BuildingOut(ORMModel):
    id: int
    code: str
    name: str


class RoomIn(BaseModel):
    code: str
    display_name: str | None = None
    building_id: int | None = None
    floor: str | None = None
    capacity: int = 0
    exam_capacity: int = 0
    tags: list[str] = []
    is_bookable: bool = True
    notes: str | None = None
    room_group: str | None = None
    custom_fields: dict[str, Any] = {}


class RoomUpdate(BaseModel):
    display_name: str | None = None
    building_id: int | None = None
    floor: str | None = None
    capacity: int | None = None
    exam_capacity: int | None = None
    tags: list[str] | None = None
    is_bookable: bool | None = None
    notes: str | None = None
    room_group: str | None = None
    custom_fields: dict[str, Any] | None = None


class RoomOut(ORMModel):
    id: int
    building_id: int | None
    code: str
    display_name: str
    floor: str | None
    capacity: int
    exam_capacity: int
    tags: list[Any]
    is_bookable: bool
    notes: str | None
    photo_url: str | None
    legacy_crbs_room_id: int | None
    room_group: str | None
    custom_fields: dict[str, Any]


class FacultyOut(ORMModel):
    id: int
    name: str
    canonical_name: str


class ProgramOut(ORMModel):
    id: int
    faculty_id: int | None
    name: str
    canonical_name: str
    is_evening: bool


class InstructorOut(ORMModel):
    id: int
    full_name: str
    canonical_name: str
    title: str | None
    email: str | None


class CourseOut(ORMModel):
    id: int
    code: str
    display_code: str
    name: str | None
    t_hours: int | None
    u_hours: int | None
    l_hours: int | None
    credits: float | None
    ects: float | None


class SectionOut(ORMModel):
    id: int
    term_id: int
    course_id: int
    program_id: int | None
    label: str | None
    class_year: int | None
    class_years: list[Any]
    semester_no: int | None
    enrolment: int | None
    mode: str
    remote_pct: int | None
    whole_term_in_room: bool | None
    notes: str | None
    archived: bool
    course_code: str | None = None
    course_name: str | None = None
    program_name: str | None = None
