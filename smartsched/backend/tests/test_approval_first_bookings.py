"""Approval-first bookings (owner requirement 2026-10-15): "when someone sends a req for reservation of empty slot it
shows first to admin and they approve or not and put reasons why they didnt and these get notified to users by the
email or other connections they added".

* ``bookings.approval_mode``: ``rules`` (CRBS + P1 rules, the default) or ``all`` (every booking request goes to the
  approvers first); approvers (``approvals.decide``), planning administrators and roles holding
  ``bookings.skip_approval`` book directly.
* A rejection needs a reason (a reason code other than ``other``, or a non-blank text; ``other`` needs the text):
  422 in Turkish and English otherwise.
* Notifications fan out through ``app.services.notify_dispatch`` (in-app + e-mail outbox), per-user channel
  preferences (``/me/notification-preferences``), idempotent per (event, recipient, channel).

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): A 102 is free at P1 (08:30-09:10) every
Thursday; A 201 (TIP) is free on Wednesday 18 Feb 2026 at P3-P5 (10:10-12:30).
"""

from __future__ import annotations

from datetime import date, datetime

from app.core import db as dbmod
from app.models import ApprovalRequest, InAppNotification, NotificationDelivery, NotificationOutbox, User
from app.services import approvals
from app.services import notify_dispatch as nd
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401

THU = date(2026, 2, 19)
WED = date(2026, 2, 18)
APPR = "/api/v1/approvals"
PREFS = "/api/v1/me/notification-preferences"


async def _mode(env, mode: str) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.put("/api/v1/org/settings", json={"approval_mode": mode}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["approval_mode"] == mode


async def _people(env):  # type: ignore[no-untyped-def]  # noqa: F811
    """Gözde Ayrancıgil (administrator, approver for every room) and Ayşe Yılmaz (teacher)."""
    gid, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr",
        role="ADMIN",
        firstname="Gözde",
        lastname="Ayrancıgil",
        approves_for=[{"type": "all"}],
    )
    aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    return gid, gozde, aid, ayse


async def _outbox(user_id: int, kind: str | None = None) -> list[NotificationOutbox]:
    async with dbmod.get_session_factory()() as s:
        q = select(NotificationOutbox).where(NotificationOutbox.user_id == user_id)
        if kind:
            q = q.where(NotificationOutbox.kind == kind)
        return list((await s.execute(q.order_by(NotificationOutbox.id))).scalars())


async def _inapp(user_id: int, kind: str | None = None) -> list[InAppNotification]:
    async with dbmod.get_session_factory()() as s:
        q = select(InAppNotification).where(InAppNotification.user_id == user_id)
        if kind:
            q = q.where(InAppNotification.kind == kind)
        return list((await s.execute(q.order_by(InAppNotification.id))).scalars())


async def _deliveries(user_id: int) -> list[tuple[str, str, str]]:
    async with dbmod.get_session_factory()() as s:
        q = (
            select(NotificationDelivery)
            .where(NotificationDelivery.user_id == user_id)
            .order_by(NotificationDelivery.id)
        )
        return [(d.event, d.channel, d.status) for d in (await s.execute(q)).scalars()]


async def _request(env, ayse):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.book(ayse, "A102", THU, "P1", notes="FZT 132 telafi dersi")
    assert r.status_code == 202 and r.json()["status"] == "PENDING", r.text
    (req,) = (await env.client.get(f"{APPR}/mine", headers=ayse)).json()
    return req


# --------------------------------------------------------------------------------------------------
# mode
# --------------------------------------------------------------------------------------------------


async def test_rules_mode_is_the_default_and_keeps_crbs_booking(env):  # noqa: F811
    c = env.client
    assert (await c.get("/api/v1/org/settings", headers=env.admin)).json()["approval_mode"] == "rules"
    _, _, aid, ayse = await _people(env)
    check = (await c.get(f"{APPR}/rooms/{env.rooms['A102']}/check", headers=ayse)).json()
    assert check["action"] == "book"
    r = await env.book(ayse, "A102", THU, "P1")
    assert r.status_code == 201 and r.json()["status"] == "BOOKED", r.text
    assert await _inapp(aid) == []
    bad = await c.put("/api/v1/org/settings", json={"approval_mode": "hepsi"}, headers=env.admin)
    assert bad.status_code == 422


async def test_all_mode_teacher_request_is_pending_and_approvers_are_notified_on_both_channels(env):  # noqa: F811
    c = env.client
    await _mode(env, "all")
    gid, gozde, aid, ayse = await _people(env)
    check = (await c.get(f"{APPR}/rooms/{env.rooms['A102']}/check", headers=ayse)).json()
    assert check["action"] == "request" and [a["id"] for a in check["approvers"]] == [gid]
    assert "onay" in check["summary_tr"].lower()
    find = (
        await c.post("/api/v1/rooms/find", json={"date": THU.isoformat(), "start": 1, "end": 1}, headers=ayse)
    ).json()
    assert {x["action"] for x in find["results"] if x["code"] == "A102"} == {"request"}
    req = await _request(env, ayse)
    assert req["rule"]["source"] == "approval_mode" and req["status"] == "PENDING"
    inbox = (await c.get(f"{APPR}/inbox", headers=gozde)).json()
    assert [x["id"] for x in inbox] == [req["id"]] and inbox[0]["requester_name"] == "Ayşe Yılmaz"
    # in-app, with the structured payload
    (note,) = (await c.get("/api/v1/me/notifications", headers=gozde)).json()
    assert note["kind"] == "approval.requested" and "A 102" in note["title"]
    assert note["data"]["room"] == "A 102" and note["data"]["dates"] == ["2026-02-19"]
    assert note["data"]["periods"][0]["name"] == "P1" and note["data"]["periods"][0]["start"] == "08:30"
    assert note["data"]["requester"]["name"] == "Ayşe Yılmaz"
    # e-mail through the outbox
    (mail,) = await _outbox(gid, "approval_requested")
    assert mail.to_email == "gozde.ayrancigil@uni.edu.tr" and "A 102" in mail.subject
    assert "19.02.2026" in mail.body and "Ayşe Yılmaz" in mail.body
    assert sorted(await _deliveries(gid)) == [
        ("approval.requested", "email", "sent"),
        ("approval.requested", "in_app", "sent"),
    ]
    # the requester's own copy of nothing: approvers only
    assert await _inapp(aid) == []


async def test_all_mode_admins_and_skip_approval_roles_book_directly(env):  # noqa: F811
    c = env.client
    await _mode(env, "all")
    r = await env.book(env.admin, "A102", THU, "P1")
    assert r.status_code == 201 and r.json()["status"] == "BOOKED", r.text
    # the planning office holds booking rights but neither approvals.decide nor planning.admin: it asks too
    r = await env.book(env.planner, "A102", THU, "P2")
    assert r.status_code == 202, r.text
    # a role with the explicit "book without approval" permission books directly
    role = await c.post(
        "/api/v1/roles",
        json={"name": "Bölüm başkanı", "permissions": ["room.view", "book_single.create", "bookings.skip_approval"]},
        headers=env.admin,
    )
    assert role.status_code == 201, role.text
    _, baskan = await env.user("bolum.baskani@uni.edu.tr", role=None, role_id=role.json()["id"])
    check = (await c.get(f"{APPR}/rooms/{env.rooms['A102']}/check", headers=baskan)).json()
    assert check["action"] == "book"
    r = await env.book(baskan, "A102", date(2026, 2, 26), "P1")
    assert r.status_code == 201 and r.json()["status"] == "BOOKED", r.text
    # no escalation: a role manager without bookings.skip_approval cannot grant it
    mgr = await c.post(
        "/api/v1/roles",
        json={"name": "Rol yöneticisi", "permissions": ["setup.roles", "setup.users", "room.view"]},
        headers=env.admin,
    )
    _, manager = await env.user("rol.yonetici@uni.edu.tr", role=None, role_id=mgr.json()["id"])
    r = await c.post(
        "/api/v1/roles", json={"name": "Kaçak", "permissions": ["room.view", "bookings.skip_approval"]}, headers=manager
    )
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------------------------------
# reject reasons and requester notifications
# --------------------------------------------------------------------------------------------------


async def test_reject_needs_a_reason_and_the_requester_gets_it_in_app_and_by_email(env):  # noqa: F811
    c = env.client
    await _mode(env, "all")
    gid, gozde, aid, ayse = await _people(env)
    req = await _request(env, ayse)
    url = f"{APPR}/{req['id']}/decide"
    for body in (
        {"decision": "reject"},
        {"decision": "reject", "note": "   "},  # NBSP only: blank after normalisation
        {"decision": "reject", "reason_code": "other"},
        {"decision": "reject", "reason_code": "other", "reason": " "},
    ):
        r = await c.post(url, json=body, headers=gozde)
        assert r.status_code == 422, (body, r.text)
        detail = r.json()["detail"]
        assert detail["code"] == "reason_required" and detail["message_tr"] and detail["message"]
    r = await c.post(url, json={"decision": "reject", "reason_code": "bilinmiyor", "reason": "x"}, headers=gozde)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "reason_code"
    assert (await c.get(f"{APPR}/{req['id']}", headers=ayse)).json()["status"] == "PENDING"

    reason = "A 102 o saatte  bölüm toplantısına ayrıldı"
    r = await c.post(
        url, json={"decision": "reject", "reason_code": "room_unavailable", "reason": reason}, headers=gozde
    )
    assert r.status_code == 200, r.text
    out = r.json()
    clean = "A 102 o saatte bölüm toplantısına ayrıldı"
    assert out["status"] == "REJECTED" and out["reason"] == clean and out["reason_code"] == "room_unavailable"
    assert out["decided_by"] == {"id": gid, "name": "Gözde Ayrancıgil"}
    assert out["decisions"][0]["reason_code"] == "room_unavailable" and out["decisions"][0]["note"] == clean
    mine = (await c.get(f"{APPR}/mine", headers=ayse)).json()[0]
    assert mine["reason"] == clean and mine["decided_by"]["name"] == "Gözde Ayrancıgil"

    (note,) = (await c.get("/api/v1/me/notifications", headers=ayse)).json()
    assert note["kind"] == "approval.rejected"
    assert clean in note["body"] and "Gözde Ayrancıgil" in note["body"] and "Oda uygun değil" in note["body"]
    data = note["data"]
    assert data["decision"] == "rejected" and data["reason"] == clean and data["reason_code"] == "room_unavailable"
    assert data["decided_by"]["name"] == "Gözde Ayrancıgil" and data["room"] == "A 102"
    assert data["dates"] == ["2026-02-19"] and [p["name"] for p in data["periods"]] == ["P1"]
    (mail,) = await _outbox(aid, "approval_rejected")
    assert mail.to_email == "ayse.yilmaz@uni.edu.tr"
    assert clean in mail.body and "Gözde Ayrancıgil" in mail.body and "19.02.2026" in mail.body and "P1" in mail.body
    # a reason code alone is a reason (free text only required for "other")
    req2 = (await env.book(ayse, "A102", date(2026, 2, 26), "P1")).json()
    rq2 = await approvals_request_id(req2["id"])
    r = await c.post(f"{APPR}/{rq2}/decide", json={"decision": "reject", "reason_code": "capacity"}, headers=gozde)
    assert r.status_code == 200 and r.json()["reason"] == "Kapasite yetersiz / not enough seats", r.text


async def approvals_request_id(booking_id: int) -> int:
    async with dbmod.get_session_factory()() as s:
        q = select(ApprovalRequest.id).where(ApprovalRequest.booking_id == booking_id)
        return int((await s.execute(q)).scalar_one())


async def test_approve_and_withdraw_notify_the_requester(env):  # noqa: F811
    c = env.client
    await _mode(env, "all")
    gid, gozde, aid, ayse = await _people(env)
    req = await _request(env, ayse)
    r = await c.post(f"{APPR}/{req['id']}/decide", json={"decision": "approve", "note": "İyi dersler"}, headers=gozde)
    assert r.status_code == 200 and r.json()["status"] == "APPROVED", r.text
    (note,) = await _inapp(aid, "approval.approved")
    assert "Gözde Ayrancıgil" in note.body and "İyi dersler" in note.body and "A 102" in note.title
    assert note.data and note.data["decision"] == "approved" and note.data["decided_by"]["id"] == gid
    (mail,) = await _outbox(aid, "approval_approved")
    assert "Gözde Ayrancıgil" in mail.body and "19.02.2026" in mail.body
    # withdraw: the requester gets the confirmation on both channels
    r = await env.book(ayse, "A102", date(2026, 2, 26), "P1")
    rid = await approvals_request_id(r.json()["id"])
    assert (await c.post(f"{APPR}/{rid}/withdraw", headers=ayse)).status_code == 200
    (wn,) = await _inapp(aid, "approval.withdrawn")
    assert wn.data and wn.data["decision"] == "withdrawn" and "26.02.2026" in wn.body
    assert len(await _outbox(aid, "approval_withdrawn")) == 1


async def test_group_reject_needs_a_reason_stores_it_per_period_and_notifies_once(env):  # noqa: F811
    c = env.client
    gid, gozde, aid, ayse = await _people(env)
    await c.post("/api/v1/approval-rules", json={"entity_type": "tag", "tag": "TIP"}, headers=env.admin)
    slots = [
        {"date": WED.isoformat(), "period_id": env.periods[p], "room_id": env.rooms["A201"]} for p in ("P3", "P4", "P5")
    ]
    mb = (await c.post("/api/v1/bookings/multi", json={"slots": slots}, headers=ayse)).json()
    r = await c.post(
        f"/api/v1/bookings/multi/{mb['id']}/create",
        json={"type": "single", "slots": [{"mbs_id": s["mbs_id"]} for s in mb["slots"]]},
        headers=ayse,
    )
    assert r.status_code in (200, 201, 202), r.text
    url = f"{APPR}/groups/{mb['id']}/decide"
    r = await c.post(url, json={"decision": "reject"}, headers=gozde)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "reason_required"
    r = await c.post(
        url, json={"decision": "reject", "reason_code": "policy", "reason": "Tıp Fakültesi sınavı"}, headers=gozde
    )
    assert r.status_code == 200 and [x["ok"] for x in r.json()["results"]] == [True, True, True], r.text
    mine = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    assert {(m["status"], m["reason"], m["reason_code"]) for m in mine} == {
        ("REJECTED", "Tıp Fakültesi sınavı", "policy")
    }
    assert all(len(m["decisions"]) == 1 and m["decisions"][0]["reason_code"] == "policy" for m in mine)
    # one notification for the submission, listing its three periods
    (note,) = await _inapp(aid, "approval.rejected")
    assert note.data and [p["name"] for p in note.data["periods"]] == ["P3", "P4", "P5"]
    assert len(note.data["request_ids"]) == 3 and note.data["group_id"] == mb["id"]
    assert "10:10-12:30" in note.body and "Tıp Fakültesi sınavı" in note.body
    assert len(await _outbox(aid, "approval_rejected")) == 1
    # retrying the group decision changes nothing and notifies nobody again
    again = await c.post(url, json={"decision": "reject", "reason_code": "policy", "reason": "x"}, headers=gozde)
    assert again.status_code == 200 and again.json()["results"] == []
    assert len(await _inapp(aid, "approval.rejected")) == 1


# --------------------------------------------------------------------------------------------------
# preferences and idempotency
# --------------------------------------------------------------------------------------------------


async def test_preferences_email_off_means_in_app_only(env):  # noqa: F811
    c = env.client
    await _mode(env, "all")
    gid, gozde, aid, ayse = await _people(env)
    prefs = (await c.get(PREFS, headers=ayse)).json()
    assert [ch["name"] for ch in prefs["channels"]] == ["in_app", "email"]
    assert all(ch["enabled"] for ch in prefs["channels"])
    email = next(ch for ch in prefs["channels"] if ch["name"] == "email")
    assert email["available"] is True and email["label_tr"] == "E-posta"
    rejected = next(e for e in prefs["events"] if e["event"] == "approval.rejected")
    assert rejected["channels"] == {"in_app": True, "email": True} and rejected["label_tr"]
    # validation (TR/EN)
    r = await c.put(PREFS, json={"channels": {"sms": False}}, headers=ayse)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_channel" and r.json()["detail"]["message_tr"]
    r = await c.put(PREFS, json={"events": {"booking.party": {"email": False}}}, headers=ayse)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_event"
    r = await c.put(PREFS, json={"channels": {"email": False}}, headers=ayse)
    assert r.status_code == 200, r.text
    assert next(ch for ch in r.json()["channels"] if ch["name"] == "email")["enabled"] is False
    assert next(e for e in r.json()["events"] if e["event"] == "approval.rejected")["channels"]["email"] is False
    # per event: the approver keeps e-mail for new requests but not in-app
    r = await c.put(PREFS, json={"events": {"approval.requested": {"in_app": False}}}, headers=gozde)
    assert r.status_code == 200
    req = await _request(env, ayse)
    assert await _inapp(gid) == [] and len(await _outbox(gid, "approval_requested")) == 1
    r = await c.post(
        f"{APPR}/{req['id']}/decide", json={"decision": "reject", "reason": "Salon bakımda"}, headers=gozde
    )
    assert r.status_code == 200, r.text
    assert len(await _inapp(aid, "approval.rejected")) == 1
    assert await _outbox(aid) == []
    assert ("approval.rejected", "email", "sent") not in await _deliveries(aid)
    # switching e-mail back on (other settings kept)
    r = await c.put(PREFS, json={"channels": {"email": True}}, headers=ayse)
    assert next(ch for ch in r.json()["channels"] if ch["name"] == "email")["enabled"] is True


async def test_no_duplicate_notifications_on_retry(env):  # noqa: F811
    c = env.client
    await _mode(env, "all")
    gid, gozde, aid, ayse = await _people(env)
    req = await _request(env, ayse)
    r = await c.post(
        f"{APPR}/{req['id']}/decide", json={"decision": "reject", "reason": "Salon bakımda"}, headers=gozde
    )
    assert r.status_code == 200
    # the same occurrence dispatched again (a retried job, a second worker): nothing new on either channel
    async with dbmod.get_session_factory()() as s:
        rq = await s.get(ApprovalRequest, req["id"])
        approver = await s.get(User, gid)
        assert rq is not None and approver is not None
        await approvals.notify_requester(s, rq, "approval.rejected", approver)
        user = await s.get(User, aid)
        assert user is not None
        notice = nd.Notice(event="approval.rejected", key=f"approval_request:{rq.id}:rejected", title="t", body="b")
        out = await nd.dispatch(s, user, notice)
        assert {d.channel: d.status for d in out} == {"in_app": "duplicate", "email": "duplicate"}
        await s.commit()
    assert len(await _inapp(aid, "approval.rejected")) == 1 and len(await _outbox(aid, "approval_rejected")) == 1
    # the expiry sweep run twice notifies once
    r = await env.book(ayse, "A102", date(2026, 2, 26), "P1")
    assert r.status_code == 202
    env.set_now(datetime(2026, 2, 26, 9, 0))
    assert (await c.post(f"{APPR}/sweep", headers=gozde)).json()["expired"] == 1
    assert (await c.post(f"{APPR}/sweep", headers=gozde)).json()["expired"] == 0
    async with dbmod.get_session_factory()() as s:
        rid = await approvals_request_id(r.json()["id"])
        rq = await s.get(ApprovalRequest, rid)
        assert rq is not None
        await approvals.notify_requester(s, rq, "approval.expired", None)
        await s.commit()
    (exp,) = await _inapp(aid, "approval.expired")
    assert exp.data and exp.data["decision"] == "expired" and exp.data["decided_by"] is None
    assert len(await _outbox(aid, "approval_expired")) == 1
    async with dbmod.get_session_factory()() as s:
        q = select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.user_id == aid)
        assert (await s.execute(q)).scalar_one() == 4  # rejected + expired, two channels each


def test_channel_registry_is_the_extension_point():
    """Only the two built-in channels ship; a third is one ChannelAdapter subclass passed to register_channel."""
    assert [a.name for a in nd.channels()] == ["in_app", "email"]
    assert set(nd.EVENTS) == {
        "approval.requested",
        "approval.approved",
        "approval.rejected",
        "approval.withdrawn",
        "approval.expired",
        # the CRBS booking e-mails, through the dispatcher since the follow-ups (tests/test_approval_first_followups.py)
        "booking.created",
        "booking.cancelled",
        "room_owner.booking",
        # the Phase 19 publish digest (app.services.moderation.publish_digest)
        "timetable.published",
    }

    class Probe(nd.ChannelAdapter):
        name = "probe"
        label_tr = label_en = "Probe"
        default_enabled = False

        async def send(self, session, user, notice):  # type: ignore[no-untyped-def]
            return nd.Delivery(self.name, "sent")

    probe = Probe()
    nd.register_channel(probe)
    try:
        assert [a.name for a in nd.channels()] == ["in_app", "email", "probe"]
        prefs = nd.Preferences.parse(None)
        assert prefs.enabled("approval.rejected", probe) is False
        assert prefs.enabled("approval.rejected", nd.channel("email")) is True
    finally:
        nd.unregister_channel("probe")
    assert [a.name for a in nd.channels()] == ["in_app", "email"]
