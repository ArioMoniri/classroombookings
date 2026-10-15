"""I/O schemas of the from-scratch catalogue API (P19-C1 / P19-C2, ``app/api/v1/catalog_admin.py``).

Inputs accept the forms coordinators paste from the planning lists: NBSP and stray whitespace, Turkish capitals
(``İ``/``ı``), comma decimals (``"4,5"``), dotted times (``"09.20"``) and Turkish mode words (``"Yüz yüze"``).
The normalisation itself lives in :mod:`app.importers.normalize` and :mod:`app.services.patterns`; these models
only bound sizes and shapes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.catalog import CourseOut, SectionOut
from app.schemas.requests import MeetingRequestOut

_STRICT = ConfigDict(extra="forbid")

#: free text loosely typed on purpose: the service parses it (``"80"``, ``"80 kişi"``, ``"4,5"``)
Loose = str | int | float | None


class FacultyIn(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1, max_length=255)


class FacultyUpdate(BaseModel):
    model_config = _STRICT
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ProgramIn(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1, max_length=255)
    faculty_id: int | None = None
    #: evening programme (İÖ); default: detected from the name ("Hemşirelik (İÖ)")
    is_evening: bool | None = None
    description: str | None = Field(default=None, max_length=255)


class ProgramUpdate(BaseModel):
    model_config = _STRICT
    name: str | None = Field(default=None, min_length=1, max_length=255)
    faculty_id: int | None = None
    is_evening: bool | None = None
    description: str | None = Field(default=None, max_length=255)


class CourseIn(BaseModel):
    model_config = _STRICT
    code: str = Field(min_length=2, max_length=32)
    name: str | None = Field(default=None, max_length=255)
    t_hours: Loose = None
    u_hours: Loose = None
    l_hours: Loose = None
    credits: Loose = None
    ects: Loose = None


class CourseUpdate(CourseIn):
    code: str | None = Field(default=None, min_length=2, max_length=32)  # type: ignore[assignment]


class CourseCodeCheckOut(BaseModel):
    """``GET /courses/code-check``: the canonical forms of a typed code and the course it collides with."""

    input: str
    code: str | None
    display_code: str | None
    key: str | None
    duplicate: CourseOut | None = None
    message: str | None = None


class InstructorIn(BaseModel):
    model_config = _STRICT
    full_name: str = Field(min_length=2, max_length=255)
    title: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)


class InstructorUpdate(BaseModel):
    model_config = _STRICT
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    title: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)


class SectionInstructorIn(BaseModel):
    model_config = _STRICT
    instructor_id: int
    role: str = Field(default="PRIMARY", pattern="^(PRIMARY|SECONDARY)$")


class SectionInstructorOut(BaseModel):
    instructor_id: int
    full_name: str
    title: str | None
    role: str


class SectionIn(BaseModel):
    model_config = _STRICT
    term_id: int
    course_id: int
    program_id: int | None = None
    label: Loose = None  # şube: "1", "A", "B1+Int"
    class_years: list[int] | Loose = None  # [1, 2], "1. Sınıf", "1,2"
    semester_no: int | None = Field(default=None, ge=0, le=20)
    enrolment: Loose = None
    mode: str = Field(default="F2F", max_length=64)  # F2F / ONLINE / ... or "Yüz yüze", "Çevrimiçi", "Hibrit"
    remote_pct: Loose = None
    whole_term_in_room: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)
    #: empty = "Belirlenmedi" (not yet assigned): no instructor-clash check for the section
    instructors: list[SectionInstructorIn] = Field(default_factory=list, max_length=20)


class SectionUpdate(BaseModel):
    model_config = _STRICT
    program_id: int | None = None
    label: Loose = None
    class_years: list[int] | Loose = None
    semester_no: int | None = Field(default=None, ge=0, le=20)
    enrolment: Loose = None
    mode: str | None = Field(default=None, max_length=64)
    remote_pct: Loose = None
    whole_term_in_room: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)
    instructors: list[SectionInstructorIn] | None = Field(default=None, max_length=20)


class SectionAdminOut(SectionOut):
    source_key: str
    instructors: list[SectionInstructorOut] = []  # type: ignore[assignment]
    meeting_count: int = 0


#: a scalar or list of day / time values ("TUE|THU", ["Salı", "Perşembe"], "09.20", ["09.20", 7])
DayOrTime = str | int | list[str | int] | None


class RoomNeedsIn(BaseModel):
    model_config = _STRICT
    tags: list[str] | str | None = None
    building: str | None = Field(default=None, max_length=16)
    preferred_room: str | None = Field(default=None, max_length=32)
    capacity: int | None = None


class SlotIn(BaseModel):
    model_config = _STRICT
    day: str | int
    start: str | int


class PatternIn(BaseModel):
    """``POST /sections/{id}/pattern``: see :mod:`app.services.patterns` for the semantics."""

    model_config = _STRICT
    theory: int | None = Field(default=None, ge=0, le=40)
    practice: int | None = Field(default=None, ge=0, le=40)
    lab: int | None = Field(default=None, ge=0, le=40)
    block_size: int | list[int] | None = None
    practice_blocks: list[int] | None = None
    lab_blocks: list[int] | None = None
    days: DayOrTime = None
    start: DayOrTime = None
    slots: list[SlotIn] | None = Field(default=None, max_length=40)
    weeks: str | list[int] | None = None
    room_needs: RoomNeedsIn | None = None
    room_needs_by_kind: dict[str, RoomNeedsIn] | None = None
    #: archive the section's earlier hand-made meetings first (re-applying a pattern replaces it)
    replace: bool = True

    def pattern(self) -> dict[str, Any]:
        """The plain mapping :func:`app.services.patterns.build_spec` validates (unset keys left out)."""
        return self.model_dump(exclude_unset=True, exclude_none=True, exclude={"replace"})


class PatternOut(BaseModel):
    section_id: int
    created: list[MeetingRequestOut]
    archived_ids: list[int]
    warnings: list[str] = []
    audit_id: int | None = None


class MeetingCreateIn(BaseModel):
    """``POST /requests/meetings``: one meeting by hand (a one-block pattern)."""

    model_config = _STRICT
    section_id: int
    days: DayOrTime = None
    start: str | int | None = None
    periods: int | None = Field(default=None, ge=1, le=18)
    end: str | None = None  # alternative to ``periods``: the end clock time ("13:20")
    weeks: str | list[int] | None = None
    room_needs: RoomNeedsIn | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ExamCreateIn(BaseModel):
    model_config = _STRICT
    term_id: int
    course_code: str | None = Field(default=None, max_length=32)  # default: the section's course
    course_name: str | None = Field(default=None, max_length=255)
    section_id: int | None = None
    program_id: int | None = None
    class_years: list[int] | Loose = None
    enrolment: Loose = None
    instructor_text: str | None = Field(default=None, max_length=255)
    date: dt.date | None = None
    start: str | None = None  # "09.00", "13:30"
    end: str | None = None
    requested_room_count: int | None = Field(default=None, ge=1, le=20)
    requested_min_capacity: int | None = Field(default=None, ge=1, le=2000)
    requested_tags: list[str] | str | None = None
    requested_building: str | None = Field(default=None, max_length=16)
    on_campus_written: bool = False
    no_exam: bool = False
    notes: str | None = Field(default=None, max_length=4000)


class DeleteOut(BaseModel):
    id: int
    action: str  # archived | deleted
    audit_id: int | None = None


__all__ = [
    "CourseCodeCheckOut",
    "CourseIn",
    "CourseUpdate",
    "DeleteOut",
    "ExamCreateIn",
    "FacultyIn",
    "FacultyUpdate",
    "InstructorIn",
    "InstructorUpdate",
    "MeetingCreateIn",
    "PatternIn",
    "PatternOut",
    "ProgramIn",
    "ProgramUpdate",
    "RoomNeedsIn",
    "SectionAdminOut",
    "SectionIn",
    "SectionInstructorIn",
    "SectionInstructorOut",
    "SectionUpdate",
    "SlotIn",
]
