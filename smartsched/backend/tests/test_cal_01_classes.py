"""CAL-01 (docs/ROADMAP.md "Calendar export & sync for academicians"; research doc §3.3): stable class identity and
revisions on the real Bahar 2026 import.

A class occurrence's UID no longer contains the run, the assignment or the room (``class-<sha1>@host``), so a room
move and a re-publish keep it; the fingerprint (date, times, rooms, codes, section, title, department, status) lives
in ``calendar_class_revisions`` and a change bumps SEQUENCE / LAST-MODIFIED; an occurrence that leaves the published
plan stays as ``STATUS:CANCELLED`` for ``feed_cancelled_grace_days`` and is gone after; the old
``class-{assignment}-{room}-{date}`` UIDs are cancelled once in room / department feeds.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from app.core import db as dbmod
from app.models import Assignment, CalendarClassRevision, ScheduleRun
from app.services import run_copy
from sqlalchemy import delete, select, update

from tests.cal_support import IST, by_start, events, lint_ics, psy262
from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, kvkk_sign_off


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    await kvkk_sign_off(env)


async def _token(env, department_id: int) -> str:  # noqa: F811
    """A legacy multi-scope link of a Psikoloji teacher (the department rule lets the own department in)."""
    _, teacher = await env.user("akademisyen.takvim@uni.edu.tr", department_id=department_id)
    await calendar_consent(env.client, teacher)
    return (await env.client.post("/api/v1/calendar/feeds/tokens", json={}, headers=teacher)).json()["token"]


async def _get(env, tok: str, path: str) -> str:  # noqa: F811
    r = await env.client.get(f"/api/v1/calendar/feeds/{tok}/{path}")
    assert r.status_code == 200, r.text
    return r.text


async def test_cal_01_uid_survives_a_move_and_a_republish_and_sequence_rises(env):  # noqa: F811
    p = await psy262(env)
    tok = await _token(env, p.program_id)
    dep_path = f"department/{p.program_id}.ics"
    text = await _get(env, tok, dep_path)
    lint_ics(text, forbidden=p.instructor_names)
    week5 = by_start(events(text), datetime(2026, 3, 2, 13, 30, tzinfo=IST))
    assert len(week5) == 1
    ev = week5[0]
    uid = str(ev["UID"])
    assert uid.startswith("class-") and uid.endswith("@smartsched")
    assert str(p.week5_assignment_id) not in uid.split("@")[0] and str(p.room.id) not in uid.split("@")[0]
    assert int(ev["SEQUENCE"]) == 0 and str(ev["LOCATION"]) == p.room.display_name
    assert "PSY 262" in str(ev["SUMMARY"])
    # polling again changes nothing (same revision, byte-identical body)
    assert await _get(env, tok, dep_path) == text

    # a re-publish of an identical copy (new run id, new assignment ids) keeps UID and SEQUENCE
    async with dbmod.get_session_factory()() as s:
        live = await s.get(ScheduleRun, env.run_id)
        assert live is not None
        draft, id_map = await run_copy.clone_as_draft(s, live, actor=None, reason="CAL-01 test")
        await s.commit()
        draft_id = draft.id
        # the planner moves week 5 in the draft: Tuesday P3-P5 in A 101
        await s.execute(
            update(Assignment)
            .where(Assignment.id == id_map[p.week5_assignment_id])
            .values(date=date(2026, 3, 3), day=2, start_period=3, end_period=5, room_ids=[env.rooms["A101"]])
        )
        await s.commit()
    # T19: a draft changes nothing
    assert await _get(env, tok, dep_path) == text
    r = await env.client.post(
        f"/api/v1/runs/{draft_id}/activate",
        json={"confirm_forced_breaks": True, "confirm_scope_reduction": True},
        headers=env.planner,
    )
    assert r.status_code == 200, r.text
    moved_text = await _get(env, tok, dep_path)
    lint_ics(moved_text, forbidden=p.instructor_names)
    evs = events(moved_text)
    same = [e for e in evs if str(e["UID"]) == uid]
    assert len(same) == 1
    moved = same[0]
    assert int(moved["SEQUENCE"]) == 1
    assert moved.decoded("DTSTART") == datetime(2026, 3, 3, 10, 10, tzinfo=IST)
    assert str(moved["LOCATION"]) == "A 101" and str(moved["STATUS"]) == "CONFIRMED"
    assert moved.decoded("LAST-MODIFIED") >= ev.decoded("LAST-MODIFIED")
    # the other weeks keep SEQUENCE 0 under the new run
    week4 = by_start(evs, datetime(2026, 2, 23, 13, 30, tzinfo=IST))
    assert len(week4) == 1 and int(week4[0]["SEQUENCE"]) == 0
    # the room feed of A 308 says the class left the room (CANCELLED, same UID, higher SEQUENCE)
    room_evs = events(await _get(env, tok, f"room/{p.room.id}.ics"))
    gone = [e for e in room_evs if str(e["UID"]) == uid]
    assert len(gone) == 1 and str(gone[0]["STATUS"]) == "CANCELLED" and int(gone[0]["SEQUENCE"]) >= 1


async def test_cal_01_removed_meeting_is_a_tombstone_then_gone_after_the_grace(env):  # noqa: F811
    p = await psy262(env)
    tok = await _token(env, p.program_id)
    dep_path = f"department/{p.program_id}.ics"
    first = events(await _get(env, tok, dep_path))
    week6 = by_start(first, datetime(2026, 3, 9, 13, 30, tzinfo=IST))
    assert len(week6) == 1
    uid = str(week6[0]["UID"])
    async with dbmod.get_session_factory()() as s:
        await s.execute(delete(Assignment).where(Assignment.id == p.week6_assignment_id))
        await s.commit()
    second = events(await _get(env, tok, dep_path))
    tomb = [e for e in second if str(e["UID"]) == uid]
    assert len(tomb) == 1
    assert str(tomb[0]["STATUS"]) == "CANCELLED" and int(tomb[0]["SEQUENCE"]) == 1
    assert str(tomb[0].get("TRANSP")) == "TRANSPARENT"
    async with dbmod.get_session_factory()() as s:
        rev = await s.get(CalendarClassRevision, uid)
        assert rev is not None and rev.ended_at is not None and rev.sequence == 1
        old = rev.ended_at - timedelta(days=30)
        await s.execute(
            update(CalendarClassRevision)
            .where(CalendarClassRevision.uid == uid)
            .values(ended_at=old, last_modified=old)
        )
        await s.commit()
    third = events(await _get(env, tok, dep_path))
    assert not [e for e in third if str(e["UID"]) == uid]
    # the other weeks are untouched
    assert len(by_start(third, datetime(2026, 3, 2, 13, 30, tzinfo=IST))) == 1


async def test_cal_01_old_uids_are_cancelled_once_in_room_feeds(env):  # noqa: F811
    p = await psy262(env)
    tok = await _token(env, p.program_id)
    evs = events(await _get(env, tok, f"room/{p.room.id}.ics"))
    old_uid = f"class-{p.week5_assignment_id}-{p.room.id}-20260302@smartsched"
    old = [e for e in evs if str(e["UID"]) == old_uid]
    assert len(old) == 1 and str(old[0]["STATUS"]) == "CANCELLED" and int(old[0]["SEQUENCE"]) == 1
    live = by_start([e for e in evs if str(e["STATUS"]) == "CONFIRMED"], datetime(2026, 3, 2, 13, 30, tzinfo=IST))
    assert len(live) == 1 and str(live[0]["UID"]) != old_uid
    async with dbmod.get_session_factory()() as s:
        legacy = (
            await s.execute(select(CalendarClassRevision).where(CalendarClassRevision.uid == old_uid))
        ).scalar_one()
        assert legacy.legacy is True and legacy.ended_at is not None
