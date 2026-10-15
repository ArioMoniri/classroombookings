"""Persona test 2026-10-15 U-06 (docs/testing/2026-10-15-persona-user.md), backend part: a teacher who asked for a
TIP room saw the slot as free again (``booking_occupancy`` skipped PENDING requests without a tentative hold) and
could send the same request twice. Now the requester and the request's approvers see it in the grid, marked pending;
other users still see the slot free (requests compete until one is approved); an identical repeat request (same
user, room, date, period) answers 409 with the existing request id instead of 202.

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): A 201 carries the TIP tag and is free on
Wednesday 18 Feb 2026 at P3.
"""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401

WED = date(2026, 2, 18)


async def _p3(env, headers):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(
        "/api/v1/bookings/grid",
        params={"display": "room", "date": WED.isoformat(), "room_id": env.rooms["A201"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["slots"] if s["date"] == WED.isoformat() and s["period_id"] == env.periods["P3"])


async def test_own_pending_request_is_shown_and_not_sent_twice(env):  # noqa: F811
    c = env.client
    _, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr",
        role="ADMIN",
        firstname="Gözde",
        lastname="Ayrancıgil",
        approves_for=[{"type": "tag", "tag": "tip"}],
    )
    r = await c.post(
        "/api/v1/approval-rules",
        json={"name": "TIP derslikleri", "entity_type": "tag", "tag": "TIP"},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    _, mehmet = await env.user("mehmet.oz@uni.edu.tr", firstname="Mehmet", lastname="Öz")

    first = await env.book(ayse, "A201", WED, "P3", notes="İç Hastalıkları semineri")
    assert first.status_code == 202 and first.json()["status"] == "PENDING", first.text
    assert first.json()["held_until"] is None  # no tentative hold: it does not block anyone
    request_id = (await c.get("/api/v1/approvals/mine", headers=ayse)).json()[0]["id"]

    # the requester sees it, marked pending
    mine = await _p3(env, ayse)
    assert mine["status"] == "booked" and mine["reason"] == "pending" and mine["pending"] is True
    assert mine["booking"]["status"] == "PENDING" and mine["booking"]["is_owner"] is True
    # ... so does the approver
    seen = await _p3(env, gozde)
    assert seen["pending"] is True and seen["booking"]["id"] == first.json()["id"]
    # another teacher still sees a free slot and may compete for it
    other = await _p3(env, mehmet)
    assert other["status"] == "available" and not other.get("pending")

    again = await env.book(ayse, "A201", WED, "P3", notes="İç Hastalıkları semineri")
    assert again.status_code == 409, again.text
    d = again.json()["detail"]
    assert d["code"] == "duplicate_request" and d["request_id"] == request_id
    assert d["booking_id"] == first.json()["id"] and "zaten" in d["message_tr"]
    assert len((await c.get("/api/v1/approvals/mine", headers=ayse)).json()) == 1

    competing = await env.book(mehmet, "A201", WED, "P3")
    assert competing.status_code == 202, competing.text
