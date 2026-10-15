"""Persona test 2026-10-15 A-24 (docs/testing/2026-10-15-persona-academician.md): before a run was published, the
booking grid showed every room free on a teaching Monday with no warning, and a teacher booked over PSY 277.

The grid now says ``timetable_state``: ``published`` (an active run covers the visible dates), ``unpublished`` (the
term has meeting requests but no published run covers them) or ``none`` (nothing to publish). Decision (tested
here): in the ``unpublished`` state booking is **warned, not blocked** -- the POST answers 409
``timetable_unpublished`` (TR/EN) until the client resends it with ``confirm_unpublished: true``.

Real Bahar 2026 import (``tests/crbs_env``): the weekly-grid run is published by the fixture; PSY 262 is on the
Bahar board on Mondays P7-P9 (the persona hit PSY 277, a Güz class, the same way).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core import db as dbmod
from app.models import Assignment, BookingPeriod, Room, ScheduleRun, Term
from app.services import bookings as bsvc
from sqlalchemy import select, update

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)


async def _psy262_monday(env) -> tuple[str, str]:  # type: ignore[no-untyped-def]  # noqa: F811
    """(room code, period name) of PSY 262 on Monday 16 Feb on the published board."""
    async with dbmod.get_session_factory()() as s:
        rows = (
            await s.execute(
                select(Assignment).where(
                    Assignment.run_id == env.run_id, Assignment.day == 1, Assignment.label.like("%PSY 262%")
                )
            )
        ).scalars()
        for a in rows:
            if a.weeks and 3 in a.weeks and a.room_ids:
                room = await s.get(Room, int(a.room_ids[0]))
                assert room is not None
                return room.code, f"P{a.start_period}"
    raise AssertionError("PSY 262 is on the Bahar board on Mondays")


async def _grid(env, headers, room_id: int):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(
        "/api/v1/bookings/grid",
        params={"display": "room", "date": MON.isoformat(), "room_id": room_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_unpublished_term_is_announced_and_booking_needs_a_confirm(env):  # noqa: F811
    code, period = await _psy262_monday(env)
    _, teacher = await env.user("akademisyen@uni.edu.tr")
    published = await _grid(env, teacher, env.rooms[code])
    assert published["timetable_state"]["state"] == "published"
    slot = next(s for s in published["slots"] if s["date"] == MON.isoformat() and s["period_id"] == env.periods[period])
    assert slot["status"] == "timetable" and "PSY 262" in slot["label"]

    async with dbmod.get_session_factory()() as s:  # before the planner publishes: no active run
        await s.execute(update(ScheduleRun).where(ScheduleRun.id == env.run_id).values(is_active=False))
        await s.commit()
    grid = await _grid(env, teacher, env.rooms[code])
    state = grid["timetable_state"]
    assert state["state"] == "unpublished" and state["meeting_requests"] > 1000
    assert "yayımlanmadı" in state["message_tr"] and "not been published" in state["message_en"]
    slot = next(s for s in grid["slots"] if s["date"] == MON.isoformat() and s["period_id"] == env.periods[period])
    assert slot["status"] == "available"  # nothing to show yet, hence the banner

    r = await env.book(teacher, code, MON, period)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "timetable_unpublished" and d["confirm_field"] == "confirm_unpublished"
    assert "yayımlanmadı" in d["message_tr"]
    r = await env.book(teacher, code, MON, period, confirm_unpublished=True)
    assert r.status_code == 201, r.text


async def test_published_week_and_a_term_with_nothing_to_publish(env):  # noqa: F811
    _, teacher = await env.user("ogretmen.yayin@uni.edu.tr")
    # published: no confirm needed
    assert (await env.book(teacher, "A101", MON, "P1")).status_code == 201
    async with dbmod.get_session_factory()() as s:
        # a summer session with bookings only (no planning list): nothing to publish
        yaz = Term(
            code="2026-YAZ", name="2026 Yaz", kind="SUMMER", start_date=date(2026, 7, 6), end_date=date(2026, 8, 14)
        )
        s.add(yaz)
        await s.commit()
        st = await bsvc.timetable_state(s, date(2026, 7, 6), date(2026, 7, 12))
        assert st["state"] == "none" and st["meeting_requests"] == 0
        # a week of Bahar outside a WEEK-horizon run counts as unpublished
        run = await s.get(ScheduleRun, env.run_id)
        assert run is not None
        run.is_active = False
        week3 = ScheduleRun(
            term_id=run.term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"week": 3, "weeks": [3]},
            status="FEASIBLE",
            hard_score=100,
            is_active=True,
        )
        s.add(week3)
        await s.commit()
        assert (await bsvc.timetable_state(s, MON, MON + timedelta(days=6)))["state"] == "published"  # week 3
        nxt = MON + timedelta(days=7)
        assert (await bsvc.timetable_state(s, nxt, nxt + timedelta(days=6)))["state"] == "unpublished"
        assert (await s.execute(select(BookingPeriod.id).limit(1))).scalar_one()  # the fixture's real 18 periods
