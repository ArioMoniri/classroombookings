"""Persona test 2026-10-15 A-12 (docs/testing/2026-10-15-persona-academician.md): one multi-period submission (a
make-up lab over three consecutive periods) became three rows in my bookings, three approval requests decided one by
one and three VEVENTs; the dashboard counted periods, not sessions.

Every booking of one submission carries its ``group_id`` (the multi-booking id). The approval inbox can list the
submission as one entry (``?grouped=1``) and decide it in one action (``POST /approvals/groups/{id}/decide``) while
per-period decisions stay possible; the dashboard totals count sessions (``*_periods`` keep the CRBS row counts);
the ICS feed shows one VEVENT per contiguous block.

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): A 201 is a TIP room free on Wednesday
18 Feb 2026 at P3-P5 (10:10-12:30).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import icalendar
import pytest

from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import calendar_consent, kvkk_sign_off


@pytest.fixture(autouse=True)
async def _kvkk_signed(env):  # noqa: F811
    """Calendar sync needs the administrator's KVKK sign-off (M-18); these tests start from a signed-off stack."""
    await kvkk_sign_off(env)


WED = date(2026, 2, 18)
IST = ZoneInfo("Europe/Istanbul")


async def _setup(env):  # type: ignore[no-untyped-def]  # noqa: F811
    c = env.client
    _, gozde = await env.user("gozde.ayrancigil@uni.edu.tr", role="ADMIN", approves_for=[{"type": "tag", "tag": "tip"}])
    r = await c.post(
        "/api/v1/approval-rules",
        json={"name": "TIP derslikleri", "entity_type": "tag", "tag": "TIP"},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    slots = [
        {"date": WED.isoformat(), "period_id": env.periods[p], "room_id": env.rooms["A201"]} for p in ("P3", "P4", "P5")
    ]
    mb = (await c.post("/api/v1/bookings/multi", json={"slots": slots}, headers=ayse)).json()
    r = await c.post(
        f"/api/v1/bookings/multi/{mb['id']}/create",
        json={
            "type": "single",
            "slots": [{"mbs_id": s["mbs_id"], "notes": "Telafi: FZT 132 laboratuvarı"} for s in mb["slots"]],
        },
        headers=ayse,
    )
    assert r.status_code in (200, 201, 202), r.text
    return gozde, ayse, mb["id"]


async def _vevents(env, headers):  # type: ignore[no-untyped-def]  # noqa: F811
    await calendar_consent(env.client, headers)
    tok = (await env.client.post("/api/v1/calendar/feeds/tokens", json={}, headers=headers)).json()["token"]
    r = await env.client.get(f"/api/v1/calendar/feeds/{tok}/mine.ics")
    assert r.status_code == 200, r.text
    return [e for e in icalendar.Calendar.from_ical(r.text).walk("VEVENT") if e.decoded("DTSTART").date() == WED]


async def test_one_submission_is_one_group_one_inbox_entry_one_decision_one_event(env):  # noqa: F811
    c = env.client
    gozde, ayse, gid = await _setup(env)
    mine = (await c.get("/api/v1/bookings/mine", params={"status": "ALL"}, headers=ayse)).json()
    assert len(mine) == 3 and {b["group_id"] for b in mine} == {gid}
    totals = (await c.get("/api/v1/bookings/dashboard", headers=ayse)).json()["totals"]
    # W3-SLOT (round-3 academician, orchestrator 2026-10-17): an open submission is shown apart, as one, not as a booking
    assert totals["pending"] == 1 and totals["all"] == 0 and totals["all_periods"] == 0

    grouped = (await c.get("/api/v1/approvals/inbox", params={"grouped": 1}, headers=gozde)).json()
    (entry,) = grouped
    assert entry["group_id"] == gid and len(entry["requests"]) == 3
    assert (entry["start_period"], entry["end_period"]) == (3, 5) and entry["room_name"] == "A 201"
    assert entry["requester_name"] == "Ayşe Yılmaz"
    # the flat inbox is unchanged (three requests), each naming its group
    flat = (await c.get("/api/v1/approvals/inbox", headers=gozde)).json()
    assert len(flat) == 3 and {x["group_id"] for x in flat} == {gid}

    r = await c.post(f"/api/v1/approvals/groups/{gid}/decide", json={"decision": "approve"}, headers=gozde)
    assert r.status_code == 200, r.text
    assert [x["ok"] for x in r.json()["results"]] == [True, True, True]
    assert (await c.get("/api/v1/approvals/inbox", headers=gozde)).json() == []

    (ev,) = await _vevents(env, ayse)
    assert ev.decoded("DTSTART") == datetime(2026, 2, 18, 10, 10, tzinfo=IST)
    assert ev.decoded("DTEND") == datetime(2026, 2, 18, 12, 30, tzinfo=IST)
    assert str(ev["STATUS"]) == "CONFIRMED"


async def test_per_period_decisions_stay_possible(env):  # noqa: F811
    c = env.client
    gozde, ayse, gid = await _setup(env)
    (entry,) = (await c.get("/api/v1/approvals/inbox", params={"grouped": 1}, headers=gozde)).json()
    p5 = next(r for r in entry["requests"] if r["bookings"][0]["period_name"] == "P5")
    r = await c.post(
        f"/api/v1/approvals/{p5['id']}/decide", json={"decision": "reject", "note": "P5 dolu"}, headers=gozde
    )
    assert r.status_code == 200, r.text
    r = await c.post(f"/api/v1/approvals/groups/{gid}/decide", json={"decision": "approve"}, headers=gozde)
    assert r.status_code == 200 and len(r.json()["results"]) == 2  # only the open ones
    booked = [e for e in await _vevents(env, ayse) if str(e["STATUS"]) == "CONFIRMED"]
    (block,) = booked  # P3 + P4 merged
    assert block.decoded("DTSTART") == datetime(2026, 2, 18, 10, 10, tzinfo=IST)
    assert block.decoded("DTEND") == datetime(2026, 2, 18, 11, 40, tzinfo=IST)
    r = await c.post(f"/api/v1/approvals/groups/{gid}/decide", json={"decision": "approve"}, headers=ayse)
    assert r.status_code == 403  # not an approver
