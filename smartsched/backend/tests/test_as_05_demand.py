"""AS-05: the aggregate demand ledger, on the real Bahar 2026 import (``tests/crbs_env``; clock Monday 16 Feb 2026).

* a find-room search adds one ``demand_events`` row with no user id and no free text; a search with no free room
  is ``none``; a booking adds ``booked``;
* ``GET /analytics/demand`` shows cells under 5 as ``"<5"``;
* the daily KVKK purge deletes rows older than ``demand.retention_days`` (default 400);
* the KVKK export of the searching person carries nothing from the ledger.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core import db as dbmod
from app.models import Setting
from app.models.base import utcnow
from app.models.seasons import DemandEvent
from app.services import kvkk
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.wave2_support import free_rooms

WED = date(2026, 2, 18)


async def _rows() -> list[DemandEvent]:
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(DemandEvent).order_by(DemandEvent.id))).scalars())


async def test_as_05_find_room_and_booking_write_aggregate_rows(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    r = await env.client.post(
        "/api/v1/rooms/find",
        json={
            "date": WED.isoformat(),
            "start": "10.10",
            "end": "11:40",
            "headcount": 40,
            "text": "Ayşe'nin semineri PC",
        },
        headers=ayse,
    )
    assert r.status_code == 200, r.text
    rows = await _rows()
    assert len(rows) == 1
    e = rows[0]
    assert (e.weekday, e.start_period, e.end_period, e.headcount_band) == (3, 3, 4, "31–60")
    assert e.period_kind == "LECTURE" and e.term_id == env.term_id and e.source == "find_room"
    assert e.features == ["PC"]  # the tag the text asked for, never the text itself
    assert e.outcome == ("searched" if r.json()["summary"]["free"] > 0 else "none")
    assert not hasattr(e, "user_id") and "Ayşe" not in repr(e.__dict__)
    # nothing fits 400 people: none
    r = await env.client.post(
        "/api/v1/rooms/find", json={"date": WED.isoformat(), "start": 4, "headcount": 400}, headers=ayse
    )
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["free"] == 0
    assert (await _rows())[-1].outcome == "none" and (await _rows())[-1].headcount_band == "151+"
    # a booking
    room = (await free_rooms(WED, 13, 13))[0]
    assert (await env.book(ayse, room, WED, "P13")).status_code == 201
    last = (await _rows())[-1]
    assert (last.outcome, last.source, last.start_period) == ("booked", "booking", 13)
    # the KVKK export of the person has no ledger section and no ledger values
    async with dbmod.get_session_factory()() as s:
        from app.models import User

        user = (await s.execute(select(User).where(User.email == "ayse.yilmaz@uni.edu.tr"))).scalar_one()
        data = await kvkk.export_data(s, user)
    assert "demand_events" not in data and "demand" not in {k.lower() for k in data}


async def test_as_05_cells_under_five_are_suppressed(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    for _ in range(5):
        r = await env.client.post(
            "/api/v1/rooms/find", json={"date": WED.isoformat(), "start": 8, "headcount": 30}, headers=ayse
        )
        assert r.status_code == 200
    r = await env.client.post(
        "/api/v1/rooms/find", json={"date": WED.isoformat(), "start": 1, "headcount": 30}, headers=ayse
    )
    out = (await env.client.get("/api/v1/analytics/demand", params={"term_id": env.term_id}, headers=env.admin)).json()
    cells = {tuple(c["key"]): c for c in out["cells"]}
    assert cells[(3, 8)]["searches"] == 5 and cells[(3, 8)]["suppressed"] is False
    assert cells[(3, 1)]["searches"] == "<5" and cells[(3, 1)]["suppressed"] is True
    assert cells[(3, 8)]["label"]["tr"] == "Çarşamba 8. ders"
    assert out["min_cell"] == 5 and out["events"] == 6 and out["definitions"]["kvkk"]["tr"]
    by_band = (
        await env.client.get(
            "/api/v1/analytics/demand", params={"term_id": env.term_id, "group_by": "headcount_band"}, headers=env.admin
        )
    ).json()
    assert {tuple(c["key"]): c["searches"] for c in by_band["cells"]} == {("≤30",): 6}


async def test_as_05_empty_ledger_says_what_it_needs(env):  # noqa: F811
    out = (await env.client.get("/api/v1/analytics/demand", headers=env.admin)).json()
    assert out["cells"] == [] and out["confidence"] == "none" and out["needs"]["tr"]


async def test_as_05_retention_purge(env):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        now = utcnow()
        s.add_all(
            [
                DemandEvent(ts=now - timedelta(days=401), weekday=3, start_period=4, end_period=4, features=[]),
                DemandEvent(ts=now - timedelta(days=10), weekday=3, start_period=4, end_period=4, features=[]),
            ]
        )
        await s.commit()
        out = await kvkk.purge_expired(s)
        await s.commit()
        assert out["demand"] == {"demand_events": 1}
        assert (await s.execute(select(func.count(DemandEvent.id)))).scalar_one() == 1
        s.add(Setting(key="demand.retention_days", value="5"))
        await s.commit()
        assert (await kvkk.purge_expired(s))["demand"] == {"demand_events": 0}  # floor of 30 days
