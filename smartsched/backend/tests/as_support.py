"""Shared helpers for the adaptive-scheduling tests (AS-01..AS-18): small terms seeded from *real* fixture rows.

Rows come from the session-cached parsed workbooks (``tests/conftest.py``); room capacities are the ones of the
room master (docs/DATA_ANALYSIS.md, "Room master")."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.importers.planning_list import PlanningRow
from app.models import Course, MeetingRequest, Program, Room, Section, Term, Week
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

#: lecture capacities of the room master (docs/DATA_ANALYSIS.md)
ROOM_CAPS = {
    "A101": 58,
    "A103": 47,
    "A104": 41,
    "A105": 60,
    "A204": 156,
    "B207": 60,
    "C403": 45,
    "C501": 72,
    "C601": 72,
    "C102": 40,
    "D202": 64,
    "D204": 64,
}
PC_ROOMS = {"A103", "A104", "A105", "B207"}


def row_of(parsed: Any, row_no: int) -> PlanningRow:
    """The parsed planning-list row with Excel row number ``row_no``."""
    return next(r for r in parsed.rows if r.row == row_no)


async def add_rooms(s: AsyncSession, *codes: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for code in codes:
        cap = ROOM_CAPS[code]
        tags = ["PC"] if code in PC_ROOMS else []
        r = Room(code=code, display_name=f"{code[0]} {code[1:]}", capacity=cap, exam_capacity=cap // 2, tags=tags)
        s.add(r)
        await s.flush()
        out[code] = r.id
    return out


async def add_term(
    s: AsyncSession,
    code: str,
    *,
    week_kinds: list[str] | None = None,
    start: date | None = None,
    kind: str = "REGULAR",
) -> Term:
    """A term with one ``Week`` row per entry of ``week_kinds`` (weekly start dates from ``start``)."""
    from datetime import timedelta

    kinds = week_kinds or []
    term = Term(code=code, name=code, kind=kind, week_count=len(kinds) or 14, start_date=start)
    s.add(term)
    await s.flush()
    for i, k in enumerate(kinds, start=1):
        s.add(
            Week(
                term_id=term.id,
                index=i,
                kind=k,
                start_date=(start + timedelta(weeks=i - 1)) if start else None,
            )
        )
    await s.flush()
    return term


async def add_meeting(
    s: AsyncSession,
    term: Term,
    row: PlanningRow,
    rooms: dict[str, int],
    *,
    locked: bool = False,
    weeks: list[int] | None = None,
) -> int:
    """One meeting request built from a parsed planning-list row: course, section, enrolment, day, periods, the
    requested room (``venue.room_codes``) and, when ``locked``, the planner's definitive room."""
    code = row.course_code or "X000"
    course = (await s.execute(select(Course).where(Course.code == code))).scalar_one_or_none()
    if course is None:
        course = Course(code=code, display_code=code, name=row.course_name)
        s.add(course)
        await s.flush()
    prog_name = row.program or "Program"
    prog = (await s.execute(select(Program).where(Program.name == prog_name))).scalar_one_or_none()
    if prog is None:
        prog = Program(name=prog_name, canonical_name=prog_name.lower())
        s.add(prog)
        await s.flush()
    years = row.class_years or [1]
    sec = Section(
        term_id=term.id,
        course_id=course.id,
        program_id=prog.id,
        label=row.label,
        class_year=years[0],
        class_years=years,
        enrolment=row.enrolment,
        source_key=f"{term.code}:{row.row}",
    )
    s.add(sec)
    await s.flush()
    day = row.day.days[0]
    mr = MeetingRequest(
        section_id=sec.id,
        day=day,
        days=[day],
        start_period=row.periods.start_period,
        end_period=row.periods.end_period,
        weeks=weeks if weeks is not None else ([] if row.weeks.all_weeks else list(row.weeks.weeks)),
        requested_room_ids=[rooms[c] for c in row.venue.room_codes if c in rooms],
        requested_tags=list(row.venue.tags),
        status="LOCKED" if locked else "PARSED",
        definitive_room_ids=[rooms[c] for c in row.definitive.room_codes if c in rooms] if locked else [],
        needs_room=True,
    )
    s.add(mr)
    await s.flush()
    return mr.id


async def add_grid_term(s: AsyncSession, code: str, parsed_grid: Any, *, kind: str = "REGULAR") -> Term:
    """A term whose ``Week`` rows are the sheets of a parsed weekly grid (index, kind, start date and name), as
    ``import_weekly_grid`` writes them."""
    sheets = sorted(parsed_grid.sheets, key=lambda sh: sh.week_index)
    first = next((sh.start_date for sh in sheets if sh.start_date), None)
    term = Term(code=code, name=code, kind=kind, week_count=len(sheets), start_date=first)
    s.add(term)
    await s.flush()
    for sh in sheets:
        s.add(Week(term_id=term.id, index=sh.week_index, kind=sh.kind, start_date=sh.start_date, label=sh.name[:128]))
    await s.flush()
    return term
