"""Persona test 2026-10-15 U-04 (docs/testing/2026-10-15-persona-user.md): a teacher could book a period of *today*
that had already started or ended (``check_window`` compared dates only), and then could not cancel it (403: the
owner may cancel only until the period ends). Decision: such bookings are not creatable -- a period whose start is
before "now" in the organisation's time zone is refused (409 ``past``, TR/EN message) unless the user may cancel
other people's bookings at role level (administrators), who can also cancel it afterwards. The grid marks those
cells ``past``. An own booking made before its period started stays cancellable until the period ends.

Real Bahar 2026 data (``tests/crbs_env``): Monday 16 Feb 2026, A 101 is free at P1-P3 (P1 08:30-09:10,
P3 10:10-10:50); the clock is the organisation's local time.
"""

from __future__ import annotations

from datetime import date, datetime

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)


async def _grid(env, headers):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(
        "/api/v1/bookings/grid",
        params={"display": "room", "date": MON.isoformat(), "room_id": env.rooms["A101"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return {(s["date"], s["period_id"]): s for s in r.json()["slots"]}


async def test_a_started_period_of_today_cannot_be_booked_by_a_teacher(env):  # noqa: F811
    _, teacher = await env.user("ogretmen.gecmis@uni.edu.tr")
    env.set_now(datetime(2026, 2, 16, 9, 0))  # P1 started at 08:30 and is still running
    r = await env.book(teacher, "A101", MON, "P1")
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "past" and d["period_start"] == "2026-02-16T08:30:00"
    assert "geçmiş" in d["message_tr"] and "already started" in d["message_en"]
    # the next period is still ahead: bookable
    assert (await env.book(teacher, "A101", MON, "P2")).status_code == 201
    slots = await _grid(env, teacher)
    p1, p3 = slots[(MON.isoformat(), env.periods["P1"])], slots[(MON.isoformat(), env.periods["P3"])]
    assert p1["past"] is True and p1["status"] == "unavailable" and p1["reason"] == "past"
    assert p3["past"] is False and p3["status"] == "available"
    # yesterday-and-before were already refused by date for single-only users; still so
    env.set_now(datetime(2026, 2, 17, 8, 0))
    r = await env.book(teacher, "A101", MON, "P3")
    assert r.status_code == 409 and r.json()["detail"]["code"] in ("range_min", "past"), r.text


async def test_an_administrator_may_record_a_past_period_and_cancel_it(env):  # noqa: F811
    env.set_now(datetime(2026, 2, 16, 11, 0))  # P1-P3 are over
    r = await env.book(env.admin, "A101", MON, "P1", notes="Telafi (kayıt için)")
    assert r.status_code == 201, r.text
    slots = await _grid(env, env.admin)
    assert slots[(MON.isoformat(), env.periods["P2"])]["past"] is True
    assert slots[(MON.isoformat(), env.periods["P2"])]["status"] == "available"
    r = await env.client.post(f"/api/v1/bookings/{r.json()['id']}/cancel", json={}, headers=env.admin)
    assert r.status_code == 200, r.text


async def test_an_own_booking_made_in_time_stays_cancellable_until_its_period_ends(env):  # noqa: F811
    _, teacher = await env.user("ogretmen.iptal@uni.edu.tr")
    env.set_now(datetime(2026, 2, 16, 8, 0))
    r = await env.book(teacher, "A101", MON, "P3")  # 10:10-10:50
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    env.set_now(datetime(2026, 2, 16, 10, 20))  # started, not ended: the owner may still cancel
    r = await env.client.post(f"/api/v1/bookings/{bid}/cancel", json={"reason": "Ders iptal"}, headers=teacher)
    assert r.status_code == 200, r.text
