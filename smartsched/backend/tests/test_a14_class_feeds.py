"""Persona test 2026-10-15 A-14 (docs/testing/2026-10-15-persona-academician.md): room calendar feeds held only
bookings, so the A 308 feed was empty although classes run there. Room, room-group and department feeds now carry
the published (active) run's class meetings as busy events named by course code and section -- never instructor
names (KVKK). Personal feeds get classes once users are linked to instructors (P19-L1).

Real Bahar 2026 import (``tests/crbs_env``; clock Monday 16 Feb 2026): PSY 262 (Psikoloji) is on the published
board on Mondays P7-P9 (13:30-15:50).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import icalendar
import pytest
from app.core import db as dbmod
from app.models import Assignment, Course, Instructor, MeetingRequest, Room, Section, SectionInstructor
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import kvkk_sign_off


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    """Calendar sync needs the administrator's KVKK sign-off (M-18); these tests start from a signed-off stack."""
    await kvkk_sign_off(env)


MON = date(2026, 2, 16)
IST = ZoneInfo("Europe/Istanbul")


async def _psy262(env):  # type: ignore[no-untyped-def]  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        a = (
            (
                await s.execute(
                    select(Assignment).where(
                        Assignment.run_id == env.run_id, Assignment.day == 1, Assignment.label.like("%PSY 262%")
                    )
                )
            )
            .scalars()
            .first()
        )
        assert a is not None and a.room_ids
        room = await s.get(Room, int(a.room_ids[0]))
        sec = (
            (
                await s.execute(
                    select(Section)
                    .join(Course, Course.id == Section.course_id)
                    .where(Section.term_id == env.term_id, Course.code == "PSY262")
                )
            )
            .scalars()
            .first()
        )
        assert room is not None and sec is not None and sec.program_id
        names = list(
            (
                await s.execute(
                    select(Instructor.full_name)
                    .join(SectionInstructor, SectionInstructor.instructor_id == Instructor.id)
                    .where(SectionInstructor.section_id == sec.id)
                )
            ).scalars()
        )
        assert (await s.execute(select(MeetingRequest.id).where(MeetingRequest.section_id == sec.id))).first()
    return room, sec.program_id, names


async def _feed(env, path: str) -> tuple[str, list[icalendar.Event]]:  # type: ignore[no-untyped-def]  # noqa: F811
    _, teacher = await env.user("akademisyen.takvim@uni.edu.tr")
    tok = (await env.client.post("/api/v1/calendar/feeds/tokens", json={}, headers=teacher)).json()["token"]
    r = await env.client.get(f"/api/v1/calendar/feeds/{tok}/{path}")
    assert r.status_code == 200, r.text
    return r.text, list(icalendar.Calendar.from_ical(r.text).walk("VEVENT"))


def _monday_psy262(evs: list[icalendar.Event]) -> icalendar.Event:
    return next(
        e
        for e in evs
        if "PSY 262" in str(e["SUMMARY"]) and e.decoded("DTSTART") == datetime(2026, 2, 16, 13, 30, tzinfo=IST)
    )


async def test_room_feed_has_the_published_classes(env):  # noqa: F811
    room, _, names = await _psy262(env)
    text, evs = await _feed(env, f"room/{room.id}.ics")
    ev = _monday_psy262(evs)
    assert ev.decoded("DTEND") == datetime(2026, 2, 16, 15, 50, tzinfo=IST)
    assert str(ev["LOCATION"]) == room.display_name and str(ev["STATUS"]) == "CONFIRMED"
    assert str(ev["UID"]).startswith("class-") and str(ev.get("TRANSP", "OPAQUE")) == "OPAQUE"
    assert names and not any(nm and nm in text for nm in names)  # KVKK: no instructor names


async def test_department_feed_has_its_classes_without_instructors(env):  # noqa: F811
    room, program_id, names = await _psy262(env)
    text, evs = await _feed(env, f"department/{program_id}.ics")
    ev = _monday_psy262(evs)
    assert str(ev["LOCATION"]) == room.display_name
    assert not any(nm and nm in text for nm in names)


async def test_unpublished_run_leaves_the_feed(env):  # noqa: F811
    from app.models import ScheduleRun
    from sqlalchemy import update

    room, _, _ = await _psy262(env)
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(ScheduleRun).where(ScheduleRun.id == env.run_id).values(is_active=False))
        await s.commit()
    _, evs = await _feed(env, f"room/{room.id}.ics")
    assert not [e for e in evs if str(e["UID"]).startswith("class-")]
