"""RF-11 (audit 2026-10-17 A6/A8): the six e-mail kinds that could only be previewed are now sent, each through
``app.services.notify_dispatch`` (the recipient's channel preferences, the delivery ledger, the outbox).

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): A 102 is free at P1 (08:30) every
Thursday. For every sender the test asserts that the e-mail goes once (a second run, a retried hook or a repeated
action sends nothing more), that its plain text and subject are the shipped Turkish template filled with the real
room, date and period, and that switching the event's e-mail off in the person's preferences stops it.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from app.core import db as dbmod
from app.models import Booking, InAppNotification, NotificationOutbox
from app.services import bookings_notify
from app.workers import integrations as worker
from app.workers import reminders
from sqlalchemy import select, update

from tests.crbs_env import env  # noqa: F401
from tests.test_crbs_users import FakeSMTP

THU = date(2026, 2, 19)
APPR = "/api/v1/approvals"
CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
CHROME_WIN_NEXT = CHROME_WIN.replace("Chrome/129.0.0.0", "Chrome/130.0.6723.58")
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.6 Mobile/15E148 Safari/604.1"
)


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


async def _rows(kind: str, user_id: int | None = None) -> list[NotificationOutbox]:
    async with dbmod.get_session_factory()() as s:
        q = select(NotificationOutbox).where(NotificationOutbox.kind == kind)
        if user_id is not None:
            q = q.where(NotificationOutbox.user_id == user_id)
        return list((await s.execute(q.order_by(NotificationOutbox.id))).scalars())


async def _bell(user_id: int, kind: str) -> list[InAppNotification]:
    async with dbmod.get_session_factory()() as s:
        q = select(InAppNotification).where(InAppNotification.user_id == user_id, InAppNotification.kind == kind)
        return list((await s.execute(q.order_by(InAppNotification.id))).scalars())


async def _smtp(env, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(bookings_notify.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent, FakeSMTP.fail = [], False
    r = await env.client.put(
        "/api/v1/mail/settings",
        json={
            "host": "smtp.uni.edu.tr",
            "username": "bildirim",
            "password": "smtp-gizli",
            "from_address": "bildirim@uni.edu.tr",
        },
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    r = await env.client.put(
        "/api/v1/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=env.admin
    )
    assert r.status_code == 200, r.text


def _sent(addr: str, kind_subject: str | None = None):  # type: ignore[no-untyped-def]
    out = [m for m in FakeSMTP.sent if m["To"] == addr]
    return [m for m in out if kind_subject is None or kind_subject in str(m["Subject"])]


def _plain(msg) -> str:  # type: ignore[no-untyped-def]
    return msg.get_body(preferencelist=("plain",)).get_content()


async def _opt_out(env, headers, event: str) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.put(
        "/api/v1/me/notification-preferences", json={"events": {event: {"email": False}}}, headers=headers
    )
    assert r.status_code == 200, r.text


async def _mute_email(env, headers) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """Every e-mail off (the channel's master switch) -- mandatory security / legal mails still go."""
    r = await env.client.put(
        "/api/v1/me/notification-preferences", json={"channels": {"email": False}}, headers=headers
    )
    assert r.status_code == 200, r.text


async def _not_switchable(env, headers, event: str) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """A mandatory event is not in the preferences screen and cannot be switched off (emails.md §8)."""
    prefs = (await env.client.get("/api/v1/me/notification-preferences", headers=headers)).json()
    assert event not in {e["event"] for e in prefs["events"]}
    r = await env.client.put(
        "/api/v1/me/notification-preferences", json={"events": {event: {"email": False}}}, headers=headers
    )
    assert r.status_code == 422, r.text


async def _age(booking_id: int, when: datetime) -> None:
    """The booking was made ``when`` (UTC), before the reminder window opened."""
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(Booking).where(Booking.id == booking_id).values(created_at=when))
        await s.commit()


# --------------------------------------------------------------------------------------------------
# 1. booking reminder (periodic worker job, admin lead time, ledger idempotent)
# --------------------------------------------------------------------------------------------------


async def test_reminder_goes_once_inside_the_lead_time(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    tid, teacher = await env.user("hatice.ozturk@uni.edu.tr", firstname="Hatice", lastname="Öztürk")
    r = await env.book(teacher, "A102", THU, "P1")
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    await _age(bid, datetime(2026, 2, 16, 6, 0))
    settings = (await env.client.get("/api/v1/org/settings", headers=env.admin)).json()
    assert settings["reminder_lead_hours"] == 24  # default: one day before

    env.set_now(datetime(2026, 2, 18, 8, 0))  # 24.5 h before Thursday 08:30: not yet
    assert await reminders.sweep_once() == 0
    env.set_now(datetime(2026, 2, 18, 9, 0))  # 23.5 h before
    assert await reminders.sweep_once() == 1
    assert await reminders.sweep_once() == 0  # the ledger: the same occurrence is never sent twice
    await worker.wait_idle()
    (row,) = await _rows("booking_reminder")
    assert row.to_email == "hatice.ozturk@uni.edu.tr" and row.status == "SENT" and row.booking_id == bid
    assert row.subject.startswith("Yarın: A 102 · P1 ")
    (msg,) = _sent("hatice.ozturk@uni.edu.tr")
    text = _plain(msg)
    assert text.startswith("Merhaba Hatice Öztürk, rezervasyonunuz: A 102, ") and "19 Şubat 2026" in text
    assert "Rezervasyonu görüntüle: https://plan.uni.edu.tr/bookings/mine" in text
    assert text.count("Gerekmiyorsa iptal edin") == 1  # the note once (the composed re-render does not repeat it)
    assert len(await _bell(tid, "booking.reminder")) == 1


async def test_reminder_lead_time_and_opt_out(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    r = await env.client.put("/api/v1/org/settings", json={"reminder_lead_hours": 2}, headers=env.admin)
    assert r.status_code == 200 and r.json()["reminder_lead_hours"] == 2, r.text
    tid, teacher = await env.user("hatice.ozturk@uni.edu.tr", firstname="Hatice", lastname="Öztürk")
    oid, other = await env.user("ozge.ince@uni.edu.tr", firstname="Özge", lastname="İnce")
    r = await env.book(teacher, "A102", THU, "P1")
    assert r.status_code == 201, r.text
    a = r.json()["id"]
    r = await env.book(other, "A201", date(2026, 2, 18), "P3")  # Wednesday 10:10
    assert r.status_code == 201, r.text
    b = r.json()["id"]
    await _opt_out(env, other, "booking.reminder")
    for bid in (a, b):
        await _age(bid, datetime(2026, 2, 16, 6, 0))
    env.set_now(datetime(2026, 2, 18, 8, 0))
    assert await reminders.sweep_once() == 0  # 2 h 10 min before 10:10; Thursday is a day away
    env.set_now(datetime(2026, 2, 18, 8, 30))
    assert await reminders.sweep_once() == 1  # her bell; her e-mail is off
    env.set_now(datetime(2026, 2, 19, 7, 0))
    assert await reminders.sweep_once() == 1
    await worker.wait_idle()
    (row,) = await _rows("booking_reminder")  # the opted-out owner gets no e-mail
    assert row.user_id == tid and row.subject == "08:30 başlıyor: A 102"
    assert await _rows("booking_reminder", oid) == []
    assert len(await _bell(oid, "booking.reminder")) == 1  # only her e-mail is off
    r = await env.client.put("/api/v1/org/settings", json={"reminder_lead_hours": 0}, headers=env.admin)
    assert r.status_code == 200, r.text  # 0 switches reminders off


async def test_reminder_skips_a_booking_made_inside_the_window(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    _, teacher = await env.user("hatice.ozturk@uni.edu.tr")
    bid = (await env.book(teacher, "A102", THU, "P1")).json()["id"]
    await _age(bid, datetime(2026, 2, 18, 7, 0))  # 10:00 Istanbul on Wednesday: booked the day before
    env.set_now(datetime(2026, 2, 18, 11, 0))
    assert await reminders.sweep_once() == 0
    assert await _rows("booking_reminder") == []


# --------------------------------------------------------------------------------------------------
# 2. series created / changed
# --------------------------------------------------------------------------------------------------


def _series(user_id: int, end: str = "2026-03-12") -> dict[str, object]:
    return {
        "room_id": 0,
        "period_id": 0,
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": end,
        "user_id": user_id,
    }


async def test_series_created_goes_to_the_owner_once(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    tid, _ = await env.user("hatice.ozturk@uni.edu.tr", firstname="Hatice", lastname="Öztürk")
    body = {**_series(tid), "room_id": env.rooms["A102"], "period_id": env.periods["P1"]}
    r = await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)
    assert r.status_code == 201, r.text
    sid = r.json()["series_id"]
    await worker.wait_idle()
    (row,) = await _rows("series_created")
    assert row.to_email == "hatice.ozturk@uni.edu.tr" and row.status == "SENT"
    assert row.subject == "Yinelenen rezervasyon: A 102 · her Perşembe P1"
    assert row.link == f"/bookings/mine?series={sid}"
    assert await _rows("booking_created") == []  # no longer the single-booking mail
    (msg,) = _sent("hatice.ozturk@uni.edu.tr")
    text = _plain(msg)
    assert "sizin için A 102 dersliğinde her Perşembe P1 rezervasyon oluşturdu" in text
    assert text.count("A 102, ") == 4  # 19 Feb, 26 Feb, 5 Mar, 12 Mar
    assert msg["References"] == f"<series-{sid}@uni.edu.tr>"
    assert len(await _bell(tid, "series.created")) == 1


async def test_series_created_by_the_owner_and_opt_out(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    pid = (await env.client.get("/api/v1/auth/me", headers=env.planner)).json()["id"]
    body = {**_series(pid), "room_id": env.rooms["A102"], "period_id": env.periods["P1"]}
    assert (await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).status_code == 201
    await worker.wait_idle()
    (row,) = await _rows("series_created")
    assert row.user_id == pid and "Yinelenen rezervasyonunuz oluşturuldu" not in row.body
    assert row.body.startswith("A 102 dersliğinde her Perşembe P1 yinelenen rezervasyonunuz oluşturuldu")
    tid, teacher = await env.user("hatice.ozturk@uni.edu.tr")
    await _opt_out(env, teacher, "series.created")
    body = {
        **_series(tid),
        "date": "2026-03-19",
        "start": "2026-03-19",
        "end": "2026-03-26",
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
    }
    r = await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)
    assert r.status_code == 201, r.text
    await worker.wait_idle()
    assert await _rows("series_created", tid) == []
    assert len(await _bell(tid, "series.created")) == 1


async def test_series_changed_goes_to_the_owner_once_and_respects_opt_out(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    c = env.client
    tid, teacher = await env.user("hatice.ozturk@uni.edu.tr", firstname="Hatice", lastname="Öztürk")
    body = {**_series(tid), "room_id": env.rooms["A102"], "period_id": env.periods["P1"]}
    out = (await c.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).json()
    ids = [x["id"] for x in out["created"]]
    r = await c.put(
        f"/api/v1/bookings/{ids[2]}", params={"scope": "future"}, json={"notes": "Ders kaydırıldı"}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    (row,) = await _rows("series_changed")
    assert row.to_email == "hatice.ozturk@uni.edu.tr" and row.subject == f"Seri #{out['series_id']} değişti: A 102"
    assert 'not "Ders kaydırıldı" oldu' in row.body and row.body.count("A 102, ") == 2
    # the owner's own change: nothing; a scope "one" edit is not a series change
    r = await c.put(f"/api/v1/bookings/{ids[0]}", json={"notes": "tek"}, headers=env.planner)
    assert r.status_code == 200, r.text
    await _opt_out(env, teacher, "series.changed")
    r = await c.put(
        f"/api/v1/bookings/{ids[0]}", params={"scope": "all"}, json={"notes": "Yeni not"}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    assert len(await _rows("series_changed")) == 1
    assert len(await _bell(tid, "series.changed")) == 2


async def test_series_changed_reaches_the_approver_who_approved_it(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    c = env.client
    assert (await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)).status_code == 200
    gid, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr",
        role="ADMIN",
        firstname="Gözde",
        lastname="Ayrancıgil",
        approves_for=[{"type": "all"}],
    )
    roles = (await c.get("/api/v1/roles", headers=env.admin)).json()
    teacher_perms = next(r for r in roles if r["code"] == "TEACHER")["permissions"]
    perms = sorted({p if isinstance(p, str) else p["name"] for p in teacher_perms} | {"book_recur.create"})
    r = await c.post("/api/v1/roles", json={"name": "Seri ayıran akademisyen", "permissions": perms}, headers=env.admin)
    assert r.status_code == 201, r.text
    aid, ayse = await env.user(
        "ayse.yilmaz@uni.edu.tr", role=None, role_id=r.json()["id"], firstname="Ayşe", lastname="Yılmaz"
    )
    body = {**_series(aid, "2026-03-05"), "room_id": env.rooms["A102"], "period_id": env.periods["P1"]}
    body.pop("user_id")
    r = await c.post("/api/v1/bookings/recurring", json=body, headers=ayse)
    assert r.status_code in (201, 202), r.text
    (req,) = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    r = await c.post(f"{APPR}/{req['id']}/decide", json={"decision": "approve"}, headers=gozde)
    assert r.status_code == 200, r.text
    mine = (await c.get("/api/v1/bookings/mine", headers=ayse)).json()
    first = min((b for b in mine if b["series_id"]), key=lambda b: b["date"])
    r = await c.put(
        f"/api/v1/bookings/{first['id']}", params={"scope": "all"}, json={"notes": "Laboratuvar"}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    rows = await _rows("series_changed")
    assert {x.user_id for x in rows} == {aid, gid}
    to_gozde = next(x for x in rows if x.user_id == gid)
    assert to_gozde.link and to_gozde.link.startswith("/bookings?series=")
    (msg,) = _sent("gozde.ayrancigil@uni.edu.tr", "değişti")
    assert "onayladığınız seri #" in _plain(msg) and "Laboratuvar" in _plain(msg)


# --------------------------------------------------------------------------------------------------
# 3. approval submitted (receipt to the submitter)
# --------------------------------------------------------------------------------------------------


async def test_approval_submitted_receipt_once_and_opt_out(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    c = env.client
    assert (await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)).status_code == 200
    await env.user(
        "gozde.ayrancigil@uni.edu.tr",
        role="ADMIN",
        firstname="Gözde",
        lastname="Ayrancıgil",
        approves_for=[{"type": "all"}],
    )
    aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    r = await env.book(ayse, "A102", THU, "P1")
    assert r.status_code == 202, r.text
    (req,) = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    await worker.wait_idle()
    (row,) = await _rows("approval_submitted")
    assert row.to_email == "ayse.yilmaz@uni.edu.tr" and row.status == "SENT"
    assert row.subject.startswith("Talebiniz alındı: A 102, 19.02.2026 P1 ")
    assert row.link == f"/bookings/mine?request={req['id']}"
    (msg,) = _sent("ayse.yilmaz@uni.edu.tr")
    assert _plain(msg).startswith("Talebiniz onaycılara gönderildi: A 102, 19.02.2026 P1")
    assert msg["References"] == f"<request-{req['id']}@uni.edu.tr>"
    assert len(await _rows("approval_requested")) == 1  # the approver's notice is unchanged
    # the decision moves nothing back to "submitted"; a second request after the opt-out sends no receipt
    oid, ozge = await env.user("ozge.ince@uni.edu.tr")
    await _opt_out(env, ozge, "approval.submitted")
    r = await env.book(ozge, "A201", date(2026, 2, 18), "P3")
    assert r.status_code == 202, r.text
    await worker.wait_idle()
    assert await _rows("approval_submitted", oid) == []
    assert len(await _bell(oid, "approval.submitted")) == 1
    assert len(await _rows("approval_submitted")) == 1


# --------------------------------------------------------------------------------------------------
# 4. calendar-sync consent (given / withdrawn)
# --------------------------------------------------------------------------------------------------


async def test_calendar_consent_mail_on_grant_and_withdraw(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    c = env.client
    tid, teacher = await env.user("hatice.ozturk@uni.edu.tr", firstname="Hatice", lastname="Öztürk")
    assert (await c.post("/api/v1/me/consents/calendar_sync", headers=teacher)).status_code == 200
    assert (await c.post("/api/v1/me/consents/calendar_sync", headers=teacher)).status_code == 200  # already given
    await worker.wait_idle()
    (row,) = await _rows("calendar_consent")
    assert row.to_email == "hatice.ozturk@uni.edu.tr" and row.subject == "Takvim eşitleme izniniz kaydedildi"
    assert row.link == "/profile#privacy"
    assert (await c.delete("/api/v1/me/consents/calendar_sync", headers=teacher)).status_code == 200
    assert (await c.delete("/api/v1/me/consents/calendar_sync", headers=teacher)).status_code == 200  # harmless twice
    await worker.wait_idle()
    on, off = await _rows("calendar_consent")
    assert off.subject == "Takvim eşitleme izninizi geri çektiniz"
    assert "artık Google ya da Microsoft takviminize aktarılmıyor" in off.body
    assert len(_sent("hatice.ozturk@uni.edu.tr")) == 2
    # a legal notice (emails.md §8): the "kapatılamaz" footer, no preferences link
    assert "Bu e-posta yasal bir bildirimdir (KVKK); kapatılamaz." in _plain(_sent("hatice.ozturk@uni.edu.tr")[0])
    assert "profile?tab=notifications" not in _plain(_sent("hatice.ozturk@uni.edu.tr")[0])
    # another purpose sends nothing; it is mandatory: no opt-out, and it goes with every e-mail switched off
    assert (await c.post("/api/v1/me/consents/photo", headers=teacher)).status_code == 200
    oid, ozge = await env.user("ozge.ince@uni.edu.tr")
    await _not_switchable(env, ozge, "calendar.consent")
    await _mute_email(env, ozge)
    assert (await c.post("/api/v1/me/consents/calendar_sync", headers=ozge)).status_code == 200
    await worker.wait_idle()
    assert len(await _rows("calendar_consent", oid)) == 1 and len(await _rows("calendar_consent")) == 3
    assert len(await _bell(oid, "calendar.consent")) == 1


# --------------------------------------------------------------------------------------------------
# 5. new-device sign-in (user-agent family + IP /24, hashed; switchable per organisation)
# --------------------------------------------------------------------------------------------------


async def _login(env, email: str, ua: str, ip: str) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "parola-1234"},
        headers={"User-Agent": ua, "X-Forwarded-For": ip},
    )
    assert r.status_code == 200, r.text


async def test_new_device_sign_in_once_per_device(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    email = "hatice.ozturk@uni.edu.tr"
    tid, _ = await env.user(email, firstname="Hatice", lastname="Öztürk")  # signs in once (the first device)
    await _login(env, email, CHROME_WIN, "85.105.12.40")
    await _login(env, email, CHROME_WIN_NEXT, "85.105.12.77")  # same browser family, same /24: known
    await worker.wait_idle()
    rows = await _rows("new_device_sign_in", tid)
    assert len(rows) == 1 and rows[0].subject == "Yeni bir cihazdan giriş yapıldı"
    assert "Cihaz: Chrome, Windows" in rows[0].body and rows[0].link == "/profile#security"
    assert "Zaman: " in rows[0].body
    await _login(env, email, SAFARI_IPHONE, "85.105.12.40")  # another browser and OS
    await _login(env, email, CHROME_WIN, "212.156.4.9")  # another network
    await _login(env, email, SAFARI_IPHONE, "85.105.12.41")
    await worker.wait_idle()
    rows = await _rows("new_device_sign_in", tid)
    assert len(rows) == 3 and "Safari, iPhone" in rows[1].body
    (msg,) = [m for m in _sent(email) if "Safari, iPhone" in _plain(m)]
    assert "Bu ben değilim: https://plan.uni.edu.tr/profile#security" in _plain(msg)
    async with dbmod.get_session_factory()() as s:
        from app.models import Setting

        stored = (await s.get(Setting, f"user.{tid}.known_devices")).value
    assert "85.105" not in stored and "Chrome" not in stored and "Safari" not in stored  # hashed only


async def test_new_device_org_switch_and_no_personal_opt_out(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    settings = (await env.client.get("/api/v1/org/settings", headers=env.admin)).json()
    assert settings["new_device_sign_in_mail"] is True
    r = await env.client.put("/api/v1/org/settings", json={"new_device_sign_in_mail": False}, headers=env.admin)
    assert r.status_code == 200 and r.json()["new_device_sign_in_mail"] is False
    email = "hatice.ozturk@uni.edu.tr"
    tid, teacher = await env.user(email)
    await _login(env, email, SAFARI_IPHONE, "85.105.12.40")
    await worker.wait_idle()
    assert await _rows("new_device_sign_in", tid) == [] and await _bell(tid, "new_device.sign_in") == []
    r = await env.client.put("/api/v1/org/settings", json={"new_device_sign_in_mail": True}, headers=env.admin)
    assert r.status_code == 200, r.text
    # a security mail (emails.md §8): not switchable per person, sent with every e-mail switched off
    await _not_switchable(env, teacher, "new_device.sign_in")
    await _mute_email(env, teacher)
    await _login(env, email, CHROME_WIN, "212.156.4.9")
    await worker.wait_idle()
    (row,) = await _rows("new_device_sign_in", tid)
    assert row.status == "SENT" and len(await _bell(tid, "new_device.sign_in")) == 1
    (msg,) = _sent(email)
    assert "Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz." in _plain(msg)


async def test_known_devices_are_in_the_kvkk_export_and_erased(env, monkeypatch):  # noqa: F811
    from app.models import Setting, User
    from app.services import kvkk

    await _smtp(env, monkeypatch)
    email = "hatice.ozturk@uni.edu.tr"
    tid, _ = await env.user(email)
    await _login(env, email, SAFARI_IPHONE, "85.105.12.40")
    await _login(env, email, SAFARI_IPHONE, "85.105.12.99")  # the same device again: one row, last seen moves
    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, tid)
        assert user is not None
        rows = (await kvkk.export_data(s, user))["known_devices"]
        assert len(rows) == 2 and all(len(r["device"]) == 32 for r in rows)  # the HMAC only, never the address
        assert all(r["first_seen"] and r["last_seen"] and r["first_seen"] <= r["last_seen"] for r in rows)
        assert "85.105" not in str(rows) and "Safari" not in str(rows)
        assert "known_devices" in kvkk.EXPORT_FILES and "known_devices" in kvkk.DATA_CLASSES
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        res = await kvkk.erase_user(s, admin, user)
        await s.commit()
        assert res["counts"]["known_devices"] == 2
        assert await s.get(Setting, f"user.{tid}.known_devices") is None


async def test_calendar_provider_connect_and_disconnect_mails(env, monkeypatch):  # noqa: F811
    from app.services import calendar_connectors

    from tests.integrations_support import FakeGoogle, client_factory, kvkk_sign_off
    from tests.test_calendar_connectors import configure, connect

    await _smtp(env, monkeypatch)
    await kvkk_sign_off(env)
    fake = FakeGoogle()
    monkeypatch.setattr(calendar_connectors, "http_client", client_factory(fake))
    await configure(env, "google")
    uid, teacher = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    await connect(env, fake, teacher, "google")
    await worker.wait_idle()
    subjects = [r.subject for r in await _rows("calendar_consent", uid)]
    assert subjects.count("Google takviminiz bağlandı") == 1
    (msg,) = [m for m in _sent("ayse.yilmaz@uni.edu.tr") if m["Subject"] == "Google takviminiz bağlandı"]
    assert "Google sunucuları yurt dışındadır" in _plain(msg) and "kapatılamaz" in _plain(msg)
    r = await env.client.delete("/api/v1/calendar/connectors/google", headers=teacher)
    assert r.status_code == 204, r.text
    await worker.wait_idle()
    subjects = [r.subject for r in await _rows("calendar_consent", uid)]
    assert subjects.count("Google takviminizin bağlantısı kaldırıldı") == 1
    assert subjects.count("Google takviminiz bağlandı") == 1


# --------------------------------------------------------------------------------------------------
# 6. /admin/email: what is actually sent
# --------------------------------------------------------------------------------------------------


async def test_every_kind_is_reported_as_sent(env):  # noqa: F811
    from app.emails import KINDS

    assert {k for k, s in KINDS.items() if s.sender != "wired"} == set()
    for kind in ("invitation", "account_created", "ops_alert", "booking_reminder", "new_device_sign_in"):
        assert KINDS[kind].sender == "wired"
