"""ORM models. Import this package to register all tables on ``Base.metadata``."""

from app.models.base import Base
from app.models.catalog import Building, Course, Faculty, Instructor, Program, Room, Term, Week
from app.models.runs import Assignment, ChatMessage, ScheduleRun
from app.models.scheduling import (
    Block,
    ConstraintRow,
    ExamRequest,
    MeetingRequest,
    Section,
    SectionInstructor,
)
from app.models.system import ImportJob, Setting, User

__all__ = [
    "Assignment",
    "Base",
    "Block",
    "Building",
    "ChatMessage",
    "ConstraintRow",
    "Course",
    "ExamRequest",
    "Faculty",
    "ImportJob",
    "Instructor",
    "MeetingRequest",
    "Program",
    "Room",
    "ScheduleRun",
    "Section",
    "SectionInstructor",
    "Setting",
    "Term",
    "User",
    "Week",
]
