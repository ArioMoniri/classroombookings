"""BUG-01 (launch video, 2026-10-18): on a Sunday the find-room screen listed rooms as "Boş" and "Rezerve et" then
answered "Bu oda az önce doldu". Root cause: the booking schedule of the stack offers its periods Monday-Friday only
(``scripts/record/setup_api.py``: ``periods/from-grid?days=1,2,3,4,5``), find-room closed holidays, out-of-term dates
and dates without a timetable week but never looked at the weekdays the schedule offers, so a Sunday was "open"; the
room's day grid had no Sunday period, so the reserve step found no slot and toasted "just taken"; a direct POST was
refused as a generic ``calendar`` error with an English-only message.

Real Bahar 2026 data (``tests/crbs_env``), the schedule set to Monday-Friday as on the stack. Sunday 22 Feb 2026 and
Saturday 21 Feb 2026 are in Bahar week 3."""

from __future__ import annotations

from datetime import date

from app.api.v1 import find_room as find_api

from tests.crbs_env import env  # noqa: F401

FIND = "/api/v1/rooms/find"
FRI, SAT, SUN = date(2026, 2, 20), date(2026, 2, 21), date(2026, 2, 22)


async def _weekdays_only(env) -> None:  # noqa: F811
    """The stack's schedule: every period Monday-Friday (setup_api.py ``from-grid?days=1,2,3,4,5``)."""
    for pid in env.periods.values():
        r = await env.client.put(
            f"/api/v1/booking-admin/periods/{pid}", json={"days": [1, 2, 3, 4, 5]}, headers=env.admin
        )
        assert r.status_code == 200, r.text


async def test_sunday_is_a_closed_day_not_free_rooms(env):  # noqa: F811
    find_api.FIND_LIMIT.reset()
    await _weekdays_only(env)
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    body = {"date": SUN.isoformat(), "start": "10.10", "end": "12:30", "headcount": 40}  # dotted time
    r = await env.client.post(FIND, json=body, headers=ayse)
    assert r.status_code == 200, r.text
    out = r.json()
    # no slot is offered on the closed day, and the day is named with a Turkish and an English reason
    assert out["slots"] == []
    assert out["summary"]["free"] == 0 and out["summary"]["open_dates"] == 0
    assert not [x for x in out["results"] if x["status"] in ("free", "requestable", "partial")]
    assert out["alternatives"] == []
    (closed,) = out["closed_dates"]
    assert closed["date"] == "2026-02-22" and closed["reason"] == "closed_day"
    assert (
        closed["label"]["tr"] == "Pazar rezervasyona kapalı"
        and closed["label"]["en"] == "Sunday is closed for bookings"
    )
    # with the busy rooms shown, every room reads "closed", never "free"
    every = (await env.client.post(FIND, json={**body, "include_busy": True}, headers=ayse)).json()
    assert every["results"] and {x["status"] for x in every["results"]} <= {"closed", "too_small", "feature_missing"}
    assert "closed" in {x["status"] for x in every["results"]}


async def test_range_over_a_weekend_keeps_friday_and_closes_saturday_and_sunday(env):  # noqa: F811
    find_api.FIND_LIMIT.reset()
    await _weekdays_only(env)
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    body = {"date_from": FRI.isoformat(), "date_to": SUN.isoformat(), "start": "20:00", "end": "20:40", "headcount": 20}
    out = (await env.client.post(FIND, json=body, headers=ayse)).json()
    assert [s["date"] for s in out["slots"]] == ["2026-02-20"]
    assert {c["date"]: c["reason"] for c in out["closed_dates"]} == {
        "2026-02-21": "closed_day",
        "2026-02-22": "closed_day",
    }
    assert out["closed_dates"][0]["label"]["tr"] == "Cumartesi rezervasyona kapalı"
    free = [x for x in out["results"] if x["status"] == "free"]
    assert free, "Friday evening has free rooms"
    per = {p["date"]: p for p in free[0]["per_date"]}
    assert per["2026-02-20"]["status"] == "free"
    assert per["2026-02-22"] == {"date": "2026-02-22", "status": "closed", "reason": "closed_day"}


async def test_seven_day_schedule_keeps_sunday_open(env):  # noqa: F811
    """No regression: a schedule that offers Sunday (the crbs_env default, from-grid 1..7) still finds rooms."""
    find_api.FIND_LIMIT.reset()
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    out = (
        await env.client.post(FIND, json={"date": SUN.isoformat(), "start": 3, "headcount": 20}, headers=ayse)
    ).json()
    assert out["closed_dates"] == [] and out["summary"]["free"] > 0


async def test_booking_on_a_closed_day_says_the_day_is_closed(env):  # noqa: F811
    await _weekdays_only(env)
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    r = await env.book(ayse, "A102", SUN, "P3")
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "closed_day"
    assert d["message_tr"] == "22.02.2026 Pazar rezervasyona kapalı bir gün"
    assert d["message_en"] == "22.02.2026 is a Sunday, closed for bookings"
    # a holiday is refused as a holiday (Turkish text too), never as "taken"
    hol = await env.client.post(
        "/api/v1/holidays",
        json={
            "term_id": env.term_id,
            "name": "Ulusal Egemenlik ve Çocuk Bayramı",
            "date_start": "2026-04-23",
            "date_end": "2026-04-23",
        },
        headers=env.admin,
    )
    assert hol.status_code == 201, hol.text
    r = await env.book(ayse, "A102", date(2026, 4, 23), "P3")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "holiday"
    assert r.json()["detail"]["message_tr"] == "23.04.2026 tatil (Ulusal Egemenlik ve Çocuk Bayramı)"
