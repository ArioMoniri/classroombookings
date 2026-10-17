"""Shared helpers of the calendar export tests (``tests/test_cal_*``; docs/research/2026-10-17-calendar-export.md).

Real Bahar 2026 import (``tests/crbs_env``; clock Monday 16 Feb 2026): PSY 262 "Klinik Psikolojiye Giriş" (Psikoloji,
section 1, instructor Ezgi Soncu Büyükişcan) is on the published board on Mondays P7-P9 (13:30-15:50) in room 47 (C 504), one
dated board row per teaching week (weeks 1-15)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import icalendar
from app.core import db as dbmod
from app.models import Assignment, Course, Instructor, Room, Section, SectionInstructor
from sqlalchemy import select, update

IST = ZoneInfo("Europe/Istanbul")
WEEK5_MON = date(2026, 3, 2)
#: properties that could carry a person: never in a SmartSched class event
PII_PROPS = ("ATTENDEE", "ORGANIZER", "CONTACT", "X-MS-OLK-SENDER", "COMMENT")


@dataclass
class Psy262:
    room: Room
    program_id: int
    section_id: int
    instructor_id: int
    instructor_names: list[str]
    week5_assignment_id: int
    week6_assignment_id: int


async def psy262(env: Any) -> Psy262:
    async with dbmod.get_session_factory()() as s:
        rows = list(
            (
                await s.execute(
                    select(Assignment)
                    .where(Assignment.run_id == env.run_id, Assignment.label == "PSY 262")
                    .order_by(Assignment.date)
                )
            ).scalars()
        )
        by_date = {a.date: a for a in rows}
        a5 = by_date[WEEK5_MON]
        room = await s.get(Room, int(a5.room_ids[0]))
        sec = (
            (
                await s.execute(
                    select(Section)
                    .join(Course, Course.id == Section.course_id)
                    .where(Section.term_id == env.term_id, Course.code == "PSY262")
                )
            )
            .scalars()
            .one()
        )
        inst = list(
            (
                await s.execute(
                    select(Instructor)
                    .join(SectionInstructor, SectionInstructor.instructor_id == Instructor.id)
                    .where(SectionInstructor.section_id == sec.id)
                )
            ).scalars()
        )
        assert room is not None and sec.program_id and inst
        return Psy262(
            room=room,
            program_id=int(sec.program_id),
            section_id=sec.id,
            instructor_id=inst[0].id,
            instructor_names=[i.full_name for i in inst],
            week5_assignment_id=a5.id,
            week6_assignment_id=by_date[date(2026, 3, 9)].id,
        )


async def link_instructor(user_id: int, instructor_id: int) -> None:
    """P19-L1 link (``Instructor.user_id``), as ``sso.set_instructor`` would store it."""
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(Instructor).where(Instructor.id == instructor_id).values(user_id=user_id))
        await s.commit()


def events(text: str) -> list[icalendar.Event]:
    return list(icalendar.Calendar.from_ical(text).walk("VEVENT"))


def by_start(evs: list[icalendar.Event], when: datetime) -> list[icalendar.Event]:
    return [e for e in evs if e.decoded("DTSTART") == when]


def lint_ics(text: str, *, forbidden: list[str] | None = None) -> icalendar.Calendar:
    """RFC 5545 hygiene: CRLF, folded at 75 octets, one VTIMEZONE per TZID used, unique UIDs, DTSTAMP on every
    VEVENT, no property that names a person and none of ``forbidden`` (names) anywhere. Returns the parsed calendar
    (icalendar 7.3.0)."""
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line
    cal = icalendar.Calendar.from_ical(text)
    tzids = {str(tz["TZID"]) for tz in cal.walk("VTIMEZONE")}
    used = set(re.findall(r";TZID=([^:;]+)", text))
    assert used <= tzids and len(list(cal.walk("VTIMEZONE"))) == len(tzids)
    uids = [str(e["UID"]) for e in cal.walk("VEVENT")]
    assert len(uids) == len(set(uids)), "duplicate UID"
    for e in cal.walk("VEVENT"):
        assert e.get("DTSTAMP") is not None and e.get("SEQUENCE") is not None
        for prop in PII_PROPS:
            assert prop not in e, prop
    for name in forbidden or []:
        assert name not in text, name
    return cal
