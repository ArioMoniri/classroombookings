"""A4 KVKK on the real Bahar 2026 import (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): privacy notices and
acknowledgements, consents, the export zip, the erasure queue (bookings, notifications, channel links and deliveries,
SSO identities, learned observations, audit pseudonymisation) and audit-row retention through the triggers."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timedelta

import pytest
from app.core import db as dbmod
from app.models import (
    AuditEvent,
    Booking,
    InAppNotification,
    LearnedObservation,
    NotificationDelivery,
    NotificationOutbox,
    Setting,
    User,
)
from app.models.base import utcnow
from app.models.channels import ChannelDelivery, UserChannel
from app.models.kvkk import DsrRequest
from app.models.sso import UserIdentity
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from tests.api_fixtures import login
from tests.crbs_env import env  # noqa: F401
from tests.wave2_support import free_rooms

NOT = "/api/v1/admin/privacy-notices"


async def _notice(env, lang: str, title: str, body: str) -> dict:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.post(NOT, json={"language": lang, "title": title, "body_md": body}, headers=env.admin)
    assert r.status_code == 201, r.text
    r = await env.client.post(f"{NOT}/{r.json()['id']}/publish", headers=env.admin)
    assert r.status_code == 200
    return r.json()


async def test_notices_acknowledgement_and_consents(env):  # noqa: F811
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    r = await env.client.get("/api/v1/me/privacy", headers=ayse)
    assert r.json()["notice"] is None and r.json()["needs_ack"] is False
    v1 = await _notice(env, "tr", "Aydınlatma Metni", "Kişisel verileriniz 6698 sayılı KVKK kapsamında işlenir.")
    r = await env.client.post(
        NOT, json={"language": "en", "title": "Privacy notice", "body_md": "Processed under KVKK.", "version": 1},
        headers=env.admin,
    )
    assert r.status_code == 201
    await env.client.post(f"{NOT}/{r.json()['id']}/publish", headers=env.admin)
    # published notices are never edited
    r = await env.client.put(f"{NOT}/{v1['id']}", json={"title": "x", "body_md": "y"}, headers=env.admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "published"
    me = (await env.client.get("/api/v1/me/privacy", headers=ayse)).json()
    assert me["needs_ack"] is True and me["notice"]["language"] == "tr" and me["notice"]["version"] == 1
    # the login page reads it without signing in
    assert (await env.client.get("/api/v1/public/privacy-notice", params={"lang": "en"})).json()["title"] == (
        "Privacy notice"
    )
    r = await env.client.post("/api/v1/me/privacy/ack", json={"notice_id": v1["id"]}, headers=ayse)
    assert r.status_code == 200
    assert (await env.client.get("/api/v1/me/privacy", headers=ayse)).json()["needs_ack"] is False
    await _notice(env, "tr", "Aydınlatma Metni (2)", "Güncellendi.")
    assert (await env.client.get("/api/v1/me/privacy", headers=ayse)).json()["needs_ack"] is True

    # consent: withdrawing SMS deletes the phone at once, other channels stay
    assert (await env.client.post("/api/v1/me/consents/sms", headers=ayse)).status_code == 200
    async with dbmod.get_session_factory()() as s:
        for kind in ("sms", "telegram"):
            s.add(UserChannel(user_id=uid, kind=kind, address_enc="enc", address_hash=kind * 8, display_hint="•••"))
        await s.commit()
    r = await env.client.delete("/api/v1/me/consents/sms", headers=ayse)
    assert r.status_code == 200 and r.json()["removed_channels"] == 1
    assert next(c for c in r.json()["consents"] if c["purpose"] == "sms")["granted"] is False
    async with dbmod.get_session_factory()() as s:
        kinds = set((await s.execute(select(UserChannel.kind).where(UserChannel.user_id == uid))).scalars())
        assert kinds == {"telegram"}
    assert (await env.client.post("/api/v1/me/consents/tracking", headers=ayse)).status_code == 404


async def test_export_zip_has_my_data_and_no_one_elses_address(env):  # noqa: F811
    uid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", full_name="Ayşe Yılmaz")
    _, mehmet = await env.user("mehmet.oz@uni.edu.tr", full_name="Mehmet Öz")
    day = date(2026, 2, 18)
    rooms = await free_rooms(day, 13, 14, limit=3)
    assert (await env.book(ayse, rooms[0], day, "P13", notes="Proje toplantısı")).status_code == 201
    # the planner books for Ayşe: she gets a notification; the planner appears only as "another user"
    r = await env.book(env.planner, rooms[1], day, "P13", user_id=uid)
    assert r.status_code == 201, r.text
    assert (await env.book(mehmet, rooms[2], day, "P13", notes="Mehmet'in dersi")).status_code == 201
    r = await env.client.post("/api/v1/me/data-requests", json={"kind": "export"}, headers=ayse)
    assert r.status_code == 201 and r.json()["status"] == "DONE" and r.json()["downloadable"] is True
    rid = r.json()["id"]
    r = await env.client.get(f"/api/v1/me/data-requests/{rid}/download", headers=ayse)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"data.json", "profile.csv", "bookings.csv", "notifications.csv", "audit_as_actor.csv"} <= names
    data = json.loads(z.read("data.json"))
    assert data["profile"][0]["email"] == "ayse.yilmaz@uni.edu.tr"
    assert {b["notes"] for b in data["bookings"]} >= {"Proje toplantısı"}
    assert {b["booked_by"] for b in data["bookings"]} == {"kendim / myself", "başka bir kullanıcı / another user"}
    whole = "\n".join(z.read(n).decode("utf-8") for n in names)
    async with dbmod.get_session_factory()() as s:
        others = [u for u in (await s.execute(select(User).where(User.id != uid))).scalars() if u.email]
    assert others
    for u in others:
        assert u.email.lower() not in whole.lower(), u.email
    assert "Mehmet" not in whole and "Fatih Bey" not in whole
    # other users cannot download it; after 7 days it is gone
    assert (await env.client.get(f"/api/v1/me/data-requests/{rid}/download", headers=mehmet)).status_code == 404
    async with dbmod.get_session_factory()() as s:
        row = await s.get(DsrRequest, rid)
        row.download_expires_at = utcnow() - timedelta(minutes=1)
        await s.commit()
    r = await env.client.get(f"/api/v1/me/data-requests/{rid}/download", headers=ayse)
    assert r.status_code == 410 and "süresi doldu" in r.json()["detail"]["message_tr"]


async def test_erasure_goes_through_the_admin_queue(env):  # noqa: F811
    uid, mehmet = await env.user("mehmet.oz@uni.edu.tr", full_name="Mehmet Öz")
    day = date(2026, 2, 19)
    room = (await free_rooms(day, 13, 13))[0]
    r = await env.book(mehmet, room, day, "P13", notes="Mehmet Öz danışmanlık saati")
    assert r.status_code == 201
    future_id = r.json()["id"]
    # personal settings, notifications, channel link + delivery, SSO identity, a learned observation, a past booking
    async with dbmod.get_session_factory()() as s:
        fb = await s.get(Booking, future_id)
        s.add(Booking(term_id=fb.term_id, period_id=fb.period_id, room_id=fb.room_id, user_id=uid, created_by=uid,
                      date=date(2026, 2, 3), start_period=13, end_period=13, notes="geçmiş", status="BOOKED"))
        s.add(Setting(key=f"user.{uid}.notification_prefs", value="{}", is_secret=False))
        s.add(InAppNotification(user_id=uid, kind="booking.created", title="t", body="b"))
        s.add(NotificationDelivery(event="booking.created", event_key="k1", user_id=uid, channel="in_app",
                                   status="sent"))
        ch = UserChannel(user_id=uid, kind="telegram", address_enc="enc", address_hash="h" * 16, display_hint="•")
        s.add(ch)
        await s.flush()
        s.add(ChannelDelivery(kind="telegram", event="booking.created", dedupe_key="d1", user_id=uid,
                              user_channel_id=ch.id))
        s.add(UserIdentity(user_id=uid, provider="entra", issuer="https://login.microsoftonline.com/x/v2.0",
                           tenant_id="t" * 36, subject="oid-1", email_at_login="mehmet.oz@uni.edu.tr",
                           display_name="Mehmet Öz"))
        s.add(LearnedObservation(ts=utcnow(), kind="room", subject_type="user", subject_key=str(uid),
                                 attribute="room", value="A101", source_table="bookings", source_id=future_id))
        await s.commit()
    r = await env.client.post("/api/v1/me/data-requests", json={"kind": "erase", "note": "Kurumdan ayrıldım"},
                              headers=mehmet)
    assert r.status_code == 201 and r.json()["status"] == "OPEN" and r.json()["days_left"] == 30
    rid = r.json()["id"]
    dup = await env.client.post("/api/v1/me/data-requests", json={"kind": "erase"}, headers=mehmet)
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "duplicate"
    assert (await env.client.get("/api/v1/admin/dsr", headers=mehmet)).status_code == 403
    q = (await env.client.get("/api/v1/admin/dsr", headers=env.admin)).json()
    assert [x["id"] for x in q] == [rid] and q[0]["overdue"] is False and q[0]["subject"] == "Mehmet Öz"

    r = await env.client.post(f"/api/v1/admin/dsr/{rid}/complete", json={"note": "KVKK birimi onayı"},
                              headers=env.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "DONE" and out["result"]["partial"] is True
    c = out["result"]["counts"]
    assert c["bookings_cancelled"] == 1 and c["bookings_anonymised"] == 1 and c["user_identities"] == 1
    assert c["user_channels"] == 1 and c["inapp_notifications"] >= 1 and c["learning_user"] == 1
    assert out["subject"].startswith("Silinmiş kullanıcı #")
    async with dbmod.get_session_factory()() as s:
        u = await s.get(User, uid)
        assert u.email is None and u.full_name is None and not u.is_active and u.username.startswith("silinmis-")
        fb = await s.get(Booking, future_id)
        assert fb.status == "CANCELLED" and "KVKK" in fb.cancel_reason and fb.user_id is None and fb.notes is None
        for model in (InAppNotification, NotificationDelivery, ChannelDelivery, UserChannel, UserIdentity):
            assert (await s.execute(select(func.count()).where(model.user_id == uid))).scalar_one() == 0
        assert (await s.execute(select(func.count()).where(Setting.key.like(f"user.{uid}.%")))).scalar_one() == 0
        assert (await s.execute(select(func.count()).where(AuditEvent.actor_id == uid))).scalar_one() == 0
        rows = list((await s.execute(select(AuditEvent))).scalars())
        blob = json.dumps(
            [[e.actor_label, e.before, e.after, e.diff, e.reason] for e in rows], ensure_ascii=False, default=str
        ).lower()
        assert "mehmet" not in blob and "öz danışmanlık" not in blob
        assert any(e.action == "kvkk.erase" for e in rows)
        # the confirmation goes to the former address once, and is not linked to the account
        mails = list(
            (await s.execute(select(NotificationOutbox).where(NotificationOutbox.kind == "kvkk_request"))).scalars()
        )
        assert len(mails) == 1 and mails[0].user_id is None
        dsr = await s.get(DsrRequest, rid)
        assert dsr.user_id is None and dsr.subject_label.startswith("Silinmiş kullanıcı #")
    # the old password no longer works
    r = await env.client.post("/api/v1/auth/login", json={"email": "mehmet.oz@uni.edu.tr", "password": "parola-1234"})
    assert r.status_code == 401
    # the room is free again
    assert (await env.book(env.planner, room, day, "P13")).status_code == 201


async def test_refusal_needs_a_reason_and_admins_do_not_erase_themselves(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    r = await env.client.post("/api/v1/me/data-requests", json={"kind": "rectify", "note": "Soyadım yanlış"},
                              headers=ayse)
    rid = r.json()["id"]
    r = await env.client.post(f"/api/v1/admin/dsr/{rid}/refuse", json={}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "reason"
    r = await env.client.post(f"/api/v1/admin/dsr/{rid}/refuse", json={"reason": "Nüfus kaydıyla uyumlu"},
                              headers=env.admin)
    assert r.status_code == 200 and r.json()["status"] == "REFUSED"
    mine = (await env.client.get("/api/v1/me/data-requests", headers=ayse)).json()
    assert mine[0]["refusal_reason"] == "Nüfus kaydıyla uyumlu"
    r = await env.client.post("/api/v1/me/data-requests", json={"kind": "erase"}, headers=env.admin)
    r = await env.client.post(f"/api/v1/admin/dsr/{r.json()['id']}/complete", json={}, headers=env.admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "own_request"


async def test_audit_retention_floor_window_and_legal_hold(env):  # noqa: F811
    r = await env.client.get("/api/v1/admin/retention", headers=env.admin)
    pol = {p["data_class"]: p for p in r.json()}
    assert set(pol) == {"booking", "audit", "notification"} and not any(p["enabled"] for p in pol.values())
    r = await env.client.put("/api/v1/admin/retention/audit", json={"retain_days": 100}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "below_floor" and "365" in r.json()["detail"]["message_tr"]
    old, recent = datetime(2024, 3, 1, 9, 0), utcnow() - timedelta(days=30)
    async with dbmod.get_session_factory()() as s:
        for ts in (old, old, recent):
            s.add(AuditEvent(ts=ts, actor_type="system", action="test.event", entity_type="test", reversible=False))
        uid = (await s.execute(select(User.id).where(User.email == "admin@example.com"))).scalar_one()
        s.add(InAppNotification(user_id=uid, kind="x", title="eski", body="b", created_at=datetime(2024, 1, 1)))
        s.add(InAppNotification(user_id=uid, kind="x", title="yeni", body="b"))
        await s.commit()
        # without a window the database refuses even old rows
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("delete from audit_events where action = 'test.event'"))
        await s.rollback()
    for cls, days in (("audit", 365), ("notification", 30)):
        r = await env.client.put(f"/api/v1/admin/retention/{cls}", json={"retain_days": days, "enabled": True},
                                 headers=env.admin)
        assert r.status_code == 200 and r.json()["enabled"] is True
    r = await env.client.post("/api/v1/admin/retention/run", headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["audit"]["audit_events"] == 2 and r.json()["notification"]["inapp_notifications"] == 1
    async with dbmod.get_session_factory()() as s:
        left = list((await s.execute(select(AuditEvent.ts).where(AuditEvent.action == "test.event"))).scalars())
        assert len(left) == 1
        evs = list((await s.execute(select(AuditEvent).where(AuditEvent.action == "kvkk.retention"))).scalars())
        assert {e.entity_id for e in evs} == {"audit", "notification"}
        # the recent row is still protected
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("delete from audit_events where action = 'test.event'"))
        await s.rollback()
        assert (await s.execute(text("select count(*) from audit_purge_windows"))).scalar_one() == 0
    # a legal hold stops the class
    r = await env.client.put("/api/v1/admin/retention/notification", json={"legal_hold": True}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "legal_hold_reason"
    r = await env.client.put(
        "/api/v1/admin/retention/notification",
        json={"legal_hold": True, "legal_hold_reason": "Yargı süreci 2026/123"},
        headers=env.admin,
    )
    assert r.status_code == 200
    r = await env.client.post("/api/v1/admin/retention/run", headers=env.admin)
    assert r.json()["notification"] == {"skipped": "legal_hold"}
    inv = (await env.client.get("/api/v1/admin/kvkk/inventory", headers=env.admin)).json()
    codes = {c["code"] for c in inv["classes"]}
    assert {"account", "booking", "audit", "notification", "phone", "checkin", "ai_prompt"} <= codes
    assert all(c["legal_basis"] for c in inv["classes"])
    assert (await login(env.client)) is not None
