"""P1 approval workflows on the real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00).

Fixture facts: A 201, A 202 and A 203 carry the TIP tag (reserved for the Faculty of Medicine, "Planlama için
Gözde Ayrancıgil"); on Wednesday 18 Feb 2026 they are free at P3-P5 (every other 90+ room has a class); A 102 is
free at P1 every Thursday; 23 Nisan 2026 is a Thursday.
"""

from __future__ import annotations

from datetime import date, datetime

from app.core import db as dbmod
from app.models import BookingSlot, NotificationOutbox
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401

WED = date(2026, 2, 18)
RULES = "/api/v1/approval-rules"
APPR = "/api/v1/approvals"


async def _approver(env, email: str, scopes: list[dict]):  # type: ignore[no-untyped-def]  # noqa: F811
    """An administrator designated as approver when the account is created (user decision 2026-10-08)."""
    uid, headers = await env.user(email, role="ADMIN", firstname="Gözde", lastname="Ayrancıgil", approves_for=scopes)
    return uid, headers


async def _slots(booking_id: int) -> int:
    async with dbmod.get_session_factory()() as s:
        q = select(func.count()).select_from(BookingSlot).where(BookingSlot.booking_id == booking_id)
        return int((await s.execute(q)).scalar_one())


async def _outbox(kind: str) -> list[NotificationOutbox]:
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(NotificationOutbox).where(NotificationOutbox.kind == kind))).scalars())


async def test_crbs_default_no_room_needs_approval(env):  # noqa: F811
    _, ayse = await env.user("ayse@uni.edu.tr")
    r = await env.book(ayse, "A201", WED, "P3")
    assert r.status_code == 201 and r.json()["status"] == "BOOKED"
    assert (await env.client.get(RULES, headers=env.admin)).json() == []
    check = (await env.client.get(f"{APPR}/rooms/{env.rooms['A202']}/check", headers=ayse)).json()
    assert check["action"] == "book" and check["rule"] is None


async def test_designation_rules_requests_competition_and_approval(env):  # noqa: F811
    c = env.client
    gid, gozde = await _approver(env, "gozde.ayrancigil@uni.edu.tr", [{"type": "tag", "tag": "tip"}])
    assert (await c.get(f"/api/v1/users/{gid}", headers=env.admin)).json()["approves_for"] == [
        {"type": "tag", "id": None, "tag": "TIP"}
    ]
    # only administrators holding approvals.decide can be approvers
    r = await c.post(
        "/api/v1/users",
        json={
            "email": "hoca@uni.edu.tr",
            "role": "TEACHER",
            "password": "parola-1234",
            "approves_for": [{"type": "all"}],
        },
        headers=env.admin,
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_an_administrator"
    r = await c.post(RULES, json={"name": "TIP derslikleri", "entity_type": "tag", "tag": "TIP"}, headers=env.admin)
    assert r.status_code == 201, r.text
    _, ayse = await env.user("ayse@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    _, mehmet = await env.user("mehmet@uni.edu.tr", firstname="Mehmet", lastname="Öz")
    check = (await c.get(f"{APPR}/rooms/{env.rooms['A201']}/check", headers=ayse)).json()
    assert check["action"] == "request" and [a["id"] for a in check["approvers"]] == [gid]
    # the finder offers the TIP rooms as "requestable"
    find = (
        await c.post(
            "/api/v1/rooms/find", json={"date": WED.isoformat(), "start": 3, "end": 5, "headcount": 90}, headers=ayse
        )
    ).json()
    assert {x["code"]: x["action"] for x in find["results"] if x["status"] == "requestable"} == {
        "A201": "request",
        "A202": "request",
        "A203": "request",
    }
    # two competing requests for the same slot: 202 PENDING, no slot held (hold_minutes = 0)
    r1 = await env.book(ayse, "A201", WED, "P3", headcount=90)
    r2 = await env.book(mehmet, "A201", WED, "P3")
    assert r1.status_code == 202 and r1.json()["status"] == "PENDING", r1.text
    assert r2.status_code == 202
    assert await _slots(r1.json()["id"]) == 0
    inbox = (await c.get(f"{APPR}/inbox", headers=gozde)).json()
    assert len(inbox) == 2 and inbox[0]["requester_name"] == "Ayşe Yılmaz"
    assert inbox[0]["competing"] == [inbox[1]["id"]]
    assert (await c.get(f"{APPR}/inbox", headers=env.admin)).json() == []  # not designated for TIP rooms
    assert len(await _outbox("approval_requested")) == 2
    notes = (await c.get("/api/v1/me/notifications?unread=true", headers=gozde)).json()
    assert notes[0]["kind"] == "approval.requested" and "A 201" in notes[0]["title"]
    # a teacher cannot decide; the approver approves Ayşe's request; Mehmet's competing one loses
    req1, req2 = inbox[0]["id"], inbox[1]["id"]
    assert (await c.post(f"{APPR}/{req1}/decide", json={"decision": "approve"}, headers=mehmet)).status_code == 403
    r = await c.post(
        f"{APPR}/{req1}/decide", json={"decision": "approve", "note": "Anatomi pratiği için uygun"}, headers=gozde
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED" and r.json()["bookings"][0]["status"] == "BOOKED"
    assert await _slots(r1.json()["id"]) == 1
    lost = (await c.get(f"{APPR}/{req2}", headers=mehmet)).json()
    assert lost["status"] == "REJECTED" and "başka bir talebe" in lost["note"]
    mine = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    assert mine[0]["decisions"][0]["decision"] == "APPROVED" and mine[0]["decisions"][0]["note"].startswith("Anatomi")
    assert len(await _outbox("approval_approved")) == 1 and len(await _outbox("approval_rejected")) == 1
    actions = [
        e["action"]
        for e in (await c.get("/api/v1/audit", params={"action": "approval."}, headers=env.admin)).json()["items"]
    ]
    assert sorted(actions) == ["approval.approve", "approval.reject", "approval.request", "approval.request"]
    # the decision is final
    again = await c.post(f"{APPR}/{req1}/decide", json={"decision": "reject"}, headers=gozde)
    assert again.status_code == 409


async def test_self_approval_reject_with_suggestion_and_withdraw(env):  # noqa: F811
    c = env.client
    _, gozde = await _approver(env, "gozde@uni.edu.tr", [{"type": "tag", "tag": "TIP"}])
    _, murat = await env.user("murat@uni.edu.tr", role="ADMIN", approves_for=[{"type": "all"}])
    await c.post(RULES, json={"entity_type": "tag", "tag": "TIP"}, headers=env.admin)
    own = await env.book(gozde, "A202", WED, "P3")
    assert own.status_code == 202
    req = (await c.get(f"{APPR}/mine", headers=gozde)).json()[0]
    r = await c.post(f"{APPR}/{req['id']}/decide", json={"decision": "approve"}, headers=gozde)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "self_approval"
    assert (await c.post(f"{APPR}/{req['id']}/decide", json={"decision": "approve"}, headers=murat)).status_code == 200
    # reject with a suggested alternative (A 203, same slot)
    _, ayse = await env.user("ayse@uni.edu.tr")
    await env.book(ayse, "A201", WED, "P3")
    req = (await c.get(f"{APPR}/mine", headers=ayse)).json()[0]
    r = await c.post(
        f"{APPR}/{req['id']}/decide",
        json={"decision": "reject", "note": "Tıp Fakültesi sınavı", "alternative": {"room_id": env.rooms["A203"]}},
        headers=gozde,
    )
    assert r.status_code == 200, r.text
    mine = (await c.get(f"{APPR}/mine", headers=ayse)).json()[0]
    assert mine["status"] == "REJECTED" and mine["suggestion"]["room_name"] == "A 203"
    note = (await c.get("/api/v1/me/notifications", headers=ayse)).json()[0]
    assert note["kind"] == "approval.rejected" and "A 203" in note["body"]
    # reject without an alternative: free rooms are suggested automatically
    await env.book(ayse, "A201", WED, "P4")
    req = (await c.get(f"{APPR}/mine", headers=ayse)).json()[0]
    await c.post(f"{APPR}/{req['id']}/decide", json={"decision": "reject"}, headers=gozde)
    mine = (await c.get(f"{APPR}/mine", headers=ayse)).json()[0]
    assert mine["suggestion"]["alternatives"] and all(a["code"] != "A201" for a in mine["suggestion"]["alternatives"])
    # withdraw an open request
    await env.book(ayse, "A201", WED, "P5")
    req = (await c.get(f"{APPR}/mine", headers=ayse)).json()[0]
    r = await c.post(f"{APPR}/{req['id']}/withdraw", headers=ayse)
    assert r.status_code == 200 and r.json()["status"] == "WITHDRAWN"
    read = await c.post("/api/v1/me/notifications/read", json={"all": True}, headers=ayse)
    assert read.json()["read"] >= 2
    assert (await c.get("/api/v1/me/notifications?unread=true", headers=ayse)).json() == []


async def test_hold_blocks_the_slot_until_it_runs_out_then_expiry(env):  # noqa: F811
    c = env.client
    _, gozde = await _approver(env, "gozde@uni.edu.tr", [{"type": "room", "id": env.rooms["A202"]}])
    r = await c.post(
        RULES,
        json={
            "entity_type": "room",
            "entity_id": env.rooms["A202"],
            "hold_minutes": 60,
            "expires_before_start_minutes": 30,
        },
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    _, ayse = await env.user("ayse@uni.edu.tr")
    _, mehmet = await env.user("mehmet@uni.edu.tr")
    r = await env.book(ayse, "A202", WED, "P3")
    assert r.status_code == 202 and r.json()["held_until"] == "2026-02-16T09:00:00"
    assert await _slots(r.json()["id"]) == 1
    clash = await env.book(mehmet, "A202", WED, "P3")
    assert clash.status_code == 409 and clash.json()["detail"]["conflict"]["kind"] == "booking"
    grid = (
        await c.get("/api/v1/bookings/grid", params={"display": "day", "date": WED.isoformat()}, headers=mehmet)
    ).json()
    slot = next(s for s in grid["slots"] if s["room_id"] == env.rooms["A202"] and s["period_id"] == env.periods["P3"])
    assert slot["status"] == "booked" and slot["booking"]["status"] == "PENDING"
    # the hold runs out: the slot is free again (the request stays open, competing now)
    env.set_now(datetime(2026, 2, 16, 9, 30))
    r2 = await env.book(mehmet, "A202", WED, "P3")
    assert r2.status_code == 202, r2.text
    # 30 min before Wednesday P3 (10:10) both requests expire; the requesters are told
    env.set_now(datetime(2026, 2, 18, 9, 45))
    mine = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    assert mine[0]["status"] == "EXPIRED" and mine[0]["bookings"][0]["status"] == "EXPIRED"
    assert len(await _outbox("approval_expired")) == 2
    assert (await c.get(f"{APPR}/inbox", headers=gozde)).json() == []


async def test_approval_rechecks_the_calendar_and_request_only_permissions(env):  # noqa: F811
    c = env.client
    _, gozde = await _approver(env, "gozde@uni.edu.tr", [{"type": "room", "id": env.rooms["A102"]}])
    # a custom role that may only *request* A 102 (room ACL), no rule: requests go to the designated approver
    r = await c.post("/api/v1/roles", json={"name": "Asistan", "permissions": []}, headers=env.admin)
    rid = r.json()["id"]
    r = await c.post(
        "/api/v1/room-admin/acl",
        json={
            "entity_type": "room",
            "entity_id": env.rooms["A102"],
            "context_type": "role",
            "context_id": rid,
            "permissions": ["room.view", "book_single.request", "book_recur.request"],
        },
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    _, asistan = await env.user("asistan@uni.edu.tr", role_id=rid)
    r = await env.book(asistan, "A102", date(2026, 4, 23), "P1")
    assert r.status_code == 202, r.text
    # without any booking permission: 403 as in CRBS
    _, guest = await env.user("misafir@uni.edu.tr", role="VIEWER")
    assert (await env.book(guest, "A102", date(2026, 4, 23), "P2")).status_code == 403
    # 23 Nisan becomes a holiday after the request: approving it fails with the reason
    hol = await c.post(
        "/api/v1/holidays",
        json={
            "term_id": env.term_id,
            "name": "Ulusal Egemenlik ve Çocuk Bayramı",
            "date_start": "2026-04-23",
            "date_end": "2026-04-23",
        },
        headers=env.admin,
    )
    assert hol.status_code == 201
    req = (await c.get(f"{APPR}/inbox", headers=gozde)).json()[0]
    r = await c.post(f"{APPR}/{req['id']}/decide", json={"decision": "approve"}, headers=gozde)
    assert r.status_code == 409 and r.json()["detail"]["problems"][0]["reason"] == "holiday"
    assert (await c.get(f"{APPR}/{req['id']}", headers=asistan)).json()["status"] == "PENDING"
    # a recurring request: the approver approves two of the Thursdays; the others are declined
    r = await c.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": env.rooms["A102"],
            "period_id": env.periods["P1"],
            "date": "2026-02-19",
            "start": "2026-02-19",
            "end": "2026-03-12",
        },
        headers=asistan,
    )
    assert r.status_code == 202 and r.json()["status"] == "PENDING", r.text
    series_req = next(x for x in (await c.get(f"{APPR}/inbox", headers=gozde)).json() if x["series_id"])
    r = await c.post(
        f"{APPR}/{series_req['id']}/decide",
        json={"decision": "approve", "instances": ["2026-02-19", "2026-03-05"]},
        headers=gozde,
    )
    assert r.status_code == 200, r.text
    status = {b["date"]: b["status"] for b in r.json()["bookings"]}
    assert status == {
        "2026-02-19": "BOOKED",
        "2026-02-26": "REJECTED",
        "2026-03-05": "BOOKED",
        "2026-03-12": "REJECTED",
    }
