"""The channel adapters behind ``app.services.notify_dispatch`` on the real Bahar 2026 data (``tests/crbs_env``).

Ayşe Yılmaz (teacher) asks for A 102 on Thursday 19 Feb 2026 at P1 (08:30-09:10) with approval mode ``all``; Gözde
Ayrancıgil (administrator, approver for every room) rejects it with a reason. The decision reaches every channel Ayşe
linked, through the dispatcher's ledger (idempotent per occurrence x recipient x channel) and the channels outbox
(sent by the worker with retries). Network boundaries are faked (tests/test_channels_support.py).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core import db as dbmod
from app.models import ChannelDelivery, NotificationDelivery, Program, User
from app.models.base import utcnow
from app.services import notify_dispatch as nd
from app.services.channels import outbox
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.test_channels_support import BOT_TOKEN, drain, enable, enable_telegram, link_telegram, net  # noqa: F401

THU = date(2026, 2, 19)
APPR = "/api/v1/approvals"
REASON = "A 102 o saatte bölüm toplantısına ayrıldı"
NAMES = ("Gözde", "Ayrancıgil", "Ayşe", "Yılmaz", "gozde", "ayse")


async def _setup(env, net, mode: str = "link_only"):  # type: ignore[no-untyped-def]  # noqa: F811
    c = env.client
    r = await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)
    assert r.status_code == 200, r.text
    await c.put("/api/v1/calendar/admin/settings", json={"public_url": "https://smartsched.uni.edu.tr"}, headers=env.admin)
    gid, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr", role="ADMIN", firstname="Gözde", lastname="Ayrancıgil", approves_for=[{"type": "all"}]
    )
    aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    await enable_telegram(c, env.admin, content_mode=mode)
    await link_telegram(c, net, ayse)
    return gid, gozde, aid, ayse


async def _reject(env, gozde, ayse) -> int:  # type: ignore[no-untyped-def]  # noqa: F811
    c = env.client
    r = await env.book(ayse, "A102", THU, "P1", notes="FZT 132 telafi dersi")
    assert r.status_code == 202, r.text
    (req,) = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    r = await c.post(
        f"{APPR}/{req['id']}/decide",
        json={"decision": "reject", "reason_code": "room_unavailable", "reason": REASON},
        headers=gozde,
    )
    assert r.status_code == 200, r.text
    return int(req["id"])


async def _ledger(user_id: int, channel: str) -> list[tuple[str, str]]:
    async with dbmod.get_session_factory()() as s:
        q = select(NotificationDelivery).where(
            NotificationDelivery.user_id == user_id, NotificationDelivery.channel == channel
        )
        return [(d.event, d.status) for d in (await s.execute(q.order_by(NotificationDelivery.id))).scalars()]


async def _outbox_rows(user_id: int) -> list[ChannelDelivery]:
    async with dbmod.get_session_factory()() as s:
        q = select(ChannelDelivery).where(ChannelDelivery.user_id == user_id).order_by(ChannelDelivery.id)
        return list((await s.execute(q)).scalars())


async def test_the_adapters_are_registered_with_notify_dispatch(env):  # noqa: F811
    names = [a.name for a in nd.channels()]
    assert names[:2] == ["in_app", "email"]
    assert {"webpush", "telegram", "whatsapp", "sms", "teams", "slack"} <= set(names)
    prefs = (await env.client.get("/api/v1/me/notification-preferences", headers=env.admin)).json()
    tg = next(ch for ch in prefs["channels"] if ch["name"] == "telegram")
    assert tg["label_tr"] == "Telegram" and tg["available"] is False  # nothing linked, nothing configured


async def test_link_only_rejection_reaches_telegram_without_names_rooms_dates_or_the_reason(env, net):  # noqa: F811
    gid, gozde, aid, ayse = await _setup(env, net, "link_only")
    rid = await _reject(env, gozde, ayse)
    assert ("approval.rejected", "sent") in await _ledger(aid, "telegram")
    # the approver had nothing linked: skipped, never failed
    assert ("approval.requested", "skipped") in await _ledger(gid, "telegram")
    assert await drain() == 1
    ((url, _title, body),) = [s for s in net.sent if "5550001" in s[0]]
    assert url.startswith("tgram://") and BOT_TOKEN in url
    assert "SmartSched" in body and f"https://smartsched.uni.edu.tr/bookings/mine?request={rid}" in body
    for leak in (*NAMES, "A 102", "A102", "19.02.2026", "2026-02-19", "08:30", "P1", "FZT", "toplantı", "Oda uygun"):
        assert leak not in body, (leak, body)
    # the outbox keeps only the link in link_only mode (minimisation at rest too)
    (row,) = await _outbox_rows(aid)
    assert row.status == "SENT" and set(row.payload) <= {"event", "lang", "mode", "link"}
    # idempotent: the same occurrence dispatched again sends nothing new
    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, aid)
        assert user is not None
        out = await nd.dispatch(
            s, user, nd.Notice(event="approval.rejected", key=f"approval_request:{rid}:rejected", title="t", body="b")
        )
        await s.commit()
    assert {d.channel: d.status for d in out}["telegram"] == "duplicate"
    assert await drain() == 0 and len([s for s in net.sent if "5550001" in s[0]]) == 1


async def test_full_mode_carries_room_dates_periods_and_reason_but_no_person_names(env, net):  # noqa: F811
    gid, gozde, aid, ayse = await _setup(env, net, "full")
    await _reject(env, gozde, ayse)
    await drain()
    ((_url, _title, body),) = [s for s in net.sent if "5550001" in s[0]]
    assert "reddedildi" in body and "A 102" in body and "19.02.2026" in body and "P1 08:30-09:10" in body
    assert "Gerekçe: Oda uygun değil: " + REASON in body
    for leak in (*NAMES, "FZT 132", "telafi"):
        assert leak not in body, (leak, body)
    # English for a user who reads English
    async with dbmod.get_session_factory()() as s:
        u = await s.get(User, aid)
        assert u is not None
        u.language = "english"
        await s.commit()
    r = await env.book(ayse, "A102", date(2026, 2, 26), "P1")
    (req,) = [x for x in (await env.client.get(f"{APPR}/mine", headers=ayse)).json() if x["status"] == "PENDING"]
    await env.client.post(f"{APPR}/{req['id']}/decide", json={"decision": "approve"}, headers=gozde)
    await drain()
    body = [s for s in net.sent if "5550001" in s[0]][-1][2]
    assert "Your room request was approved: A 102, 26.02.2026 P1 08:30-09:10" in body and "Gözde" not in body
    _ = (gid, r)


async def test_a_failing_channel_is_recorded_and_retried_and_never_breaks_the_decision(env, net):  # noqa: F811
    gid, gozde, aid, ayse = await _setup(env, net)
    net.apprise_ok = False
    await _reject(env, gozde, ayse)  # 200 although the channel is down
    await drain()
    (row,) = await _outbox_rows(aid)
    assert row.status == "PENDING" and row.attempts == 1 and row.next_attempt_at is not None
    assert row.last_error and BOT_TOKEN not in row.last_error
    # every retry fails: after the last back-off step the row is FAILED, nothing is raised anywhere
    when = utcnow()
    for _ in range(8):
        when += timedelta(hours=7)
        await outbox.drain_due(when, 200)
    (row,) = await _outbox_rows(aid)
    assert row.status == "FAILED" and row.attempts == 6 and row.next_attempt_at is None
    # the e-mail and in-app copies were unaffected
    assert ("approval.rejected", "sent") in await _ledger(aid, "email")
    assert ("approval.rejected", "sent") in await _ledger(aid, "in_app")


async def test_no_channel_sends_without_configuration_and_sign_off(env, net):  # noqa: F811
    gid, gozde, aid, ayse = await _setup(env, net)
    # the KVKK officer withdraws the sign-off: the linked address stays, nothing is queued or sent
    r = await env.client.put(
        "/api/v1/channels/admin/telegram", json={"kvkk_signoff": {"signed": False}}, headers=env.admin
    )
    assert r.status_code == 200 and r.json()["enabled"] is False
    await _reject(env, gozde, ayse)
    assert ("approval.rejected", "skipped") in await _ledger(aid, "telegram")
    assert await _outbox_rows(aid) == [] and await drain() == 0
    assert [s for s in net.sent if "5550001" in s[0]] == []
    # a row queued while the channel was on is skipped at send time once the sign-off is gone
    await env.client.put("/api/v1/channels/admin/telegram", json={"kvkk_signoff": {"signed": True, "legal_basis": "KVKK m. 9", "officer": "Elif Şahin"}}, headers=env.admin)
    (linked,) = (await env.client.get("/api/v1/me/channels", headers=ayse)).json()["linked"]
    await env.client.post(f"/api/v1/me/channels/{linked['id']}/test", headers=ayse)
    await env.client.put("/api/v1/channels/admin/telegram", json={"enabled": False}, headers=env.admin)
    await drain()
    (row,) = await _outbox_rows(aid)
    assert row.status == "SKIPPED" and "not configured" in (row.last_error or "")
    assert [s for s in net.sent if "5550001" in s[0]] == []


async def test_department_channel_gets_one_link_only_post_per_new_request_for_its_approvers(env, net):  # noqa: F811
    c = env.client
    r = await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)
    await c.put("/api/v1/calendar/admin/settings", json={"public_url": "https://smartsched.uni.edu.tr"}, headers=env.admin)
    async with dbmod.get_session_factory()() as s:
        dept = (await s.execute(select(Program).order_by(Program.id).limit(1))).scalar_one()
        dept_id, dept_name = dept.id, dept.name
    for email, first in (("gozde.ayrancigil@uni.edu.tr", "Gözde"), ("ilker.ozturk@uni.edu.tr", "İlker")):
        await env.user(email, role="ADMIN", firstname=first, lastname="Onaycı", approves_for=[{"type": "all"}], department_id=dept_id)
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    await enable(c, env.admin, "teams")
    url = (
        "https://prod-12.westeurope.logic.azure.com:443/workflows/4f1c2b9a7d6e/triggers/manual/paths/invoke"
        "?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=s1GnAtUrE-0123456789abcdef"
    )
    assert (await c.put(f"/api/v1/channels/admin/teams/departments/{dept_id}", json={"url": url}, headers=env.admin)).status_code == 200
    r = await env.book(ayse, "A102", THU, "P1")
    assert r.status_code == 202, r.text
    await drain()
    posts = [s for s in net.sent if s[0].startswith("workflow")]
    assert len(posts) == 1, posts  # two approvers in the department, one post in its channel
    body = posts[0][2]
    assert "https://smartsched.uni.edu.tr/approvals?request=" in body
    for leak in (*NAMES, "İlker", "A 102", dept_name):
        assert leak not in body, (leak, body)
    # a decision about one person never goes to a shared department channel
    (req,) = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    _ = req
