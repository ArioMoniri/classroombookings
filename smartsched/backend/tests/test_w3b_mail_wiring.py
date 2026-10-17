"""W3-MAIL: every existing send path goes through the themed renderer without changing who gets what.

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): A 102 is free at P1 every Thursday, A 201
(TIP) on Wednesday 18 Feb at P3. For each path the test asserts the recipients, that the outbox body is still the
bell's text, that the e-mail's plain-text part *starts with* that body (the content is equivalent; the themed footer
follows), and that the HTML part is the themed layout in the reader's language with the button on the deep link.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.core import db as dbmod
from app.models import InAppNotification, NotificationOutbox
from app.services import bookings_notify
from app.workers import integrations as worker
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.test_crbs_users import FakeSMTP

THU = date(2026, 2, 19)
APPR = "/api/v1/approvals"


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


async def _rows(kind: str) -> list[NotificationOutbox]:
    async with dbmod.get_session_factory()() as s:
        q = select(NotificationOutbox).where(NotificationOutbox.kind == kind).order_by(NotificationOutbox.id)
        return list((await s.execute(q)).scalars())


async def _bell(user_id: int, kind: str) -> list[InAppNotification]:
    async with dbmod.get_session_factory()() as s:
        q = select(InAppNotification).where(InAppNotification.user_id == user_id, InAppNotification.kind == kind)
        return list((await s.execute(q.order_by(InAppNotification.id))).scalars())


def _parts(msg):  # type: ignore[no-untyped-def]
    plain = msg.get_body(preferencelist=("plain",)).get_content()
    html = msg.get_body(preferencelist=("html",)).get_content()
    return plain, html


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
            "reply_to": "planlama@uni.edu.tr",
        },
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    r = await env.client.put(
        "/api/v1/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=env.admin
    )
    assert r.status_code == 200, r.text  # the panel's public URL lives with the calendar settings


def _sent_to(addr: str):  # type: ignore[no-untyped-def]
    return [m for m in FakeSMTP.sent if m["To"] == addr]


async def test_approval_paths_keep_recipients_and_text(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    c = env.client
    r = await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)
    assert r.status_code == 200, r.text
    gid, gozde = await env.user(
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
    req_id = req["id"]
    await worker.wait_idle()
    # approvers: the approver only (never the requester), plain text = the bell body, themed HTML in Turkish
    (row,) = await _rows("approval_requested")
    (bell,) = await _bell(gid, "approval.requested")
    assert row.to_email == "gozde.ayrancigil@uni.edu.tr" and row.body == bell.body and row.subject == bell.title
    assert row.status == "SENT" and row.link and row.link.startswith("/approvals?request=") and row.locale == "tr"
    (msg,) = _sent_to("gozde.ayrancigil@uni.edu.tr")
    assert not _sent_to("ayse.yilmaz@uni.edu.tr")
    plain, html = _parts(msg)
    assert plain.startswith(bell.body.strip()) and "Talebi incele: https://plan.uni.edu.tr/approvals?request=" in plain
    assert '<html lang="tr"' in html and "Onay bekliyor" in html and "/decide" not in html
    assert msg["Subject"] == bell.title and msg["References"] == f"<request-{req_id}@uni.edu.tr>"
    assert msg["Reply-To"] == "planlama@uni.edu.tr"
    # rejection with a reason: the requester only; the reason is a callout, the text unchanged
    r = await c.post(
        f"{APPR}/{req_id}/decide",
        json={"decision": "reject", "reason_code": "capacity", "note": "102 kişilik BME 419 sığmaz"},
        headers=gozde,
    )
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    (rej,) = await _rows("approval_rejected")
    (bell,) = await _bell(aid, "approval.rejected")
    assert rej.to_email == "ayse.yilmaz@uni.edu.tr" and rej.body == bell.body
    (msg,) = _sent_to("ayse.yilmaz@uni.edu.tr")
    plain, html = _parts(msg)
    assert plain.startswith(bell.body.strip())
    assert 'data-block="reason"' in html and "BME 419" in html and "Reddedildi" in html
    assert len(_sent_to("gozde.ayrancigil@uni.edu.tr")) == 1  # nothing more to the approver


async def test_booking_created_and_cancelled_keep_recipients_and_text(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    c = env.client
    tid, teacher = await env.user("hatice.ozturk@uni.edu.tr", firstname="Hatice", lastname="Öztürk")
    r = await c.put("/api/v1/auth/profile", json={"language": "en"}, headers=teacher)
    assert r.status_code == 200, r.text
    r = await env.book(env.planner, "A102", THU, "P1", user_id=tid)
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    await worker.wait_idle()
    (row,) = await _rows("booking_created")
    (bell,) = await _bell(tid, "booking.created")
    assert row.to_email == "hatice.ozturk@uni.edu.tr" and row.body == bell.body
    (msg,) = _sent_to("hatice.ozturk@uni.edu.tr")
    plain, html = _parts(msg)
    assert plain.startswith(bell.body.strip()) and "A 102" in plain
    assert '<html lang="en"' in html and 'data-block="item"' in html and "A 102" in html and "Booked" in html
    # cancelled by the planner with a reason: the owner gets it, the reason decoded
    r = await c.post(
        f"/api/v1/bookings/{bid}/cancel", json={"scope": "one", "reason": "Bölüm toplantısı"}, headers=env.planner
    )
    assert r.status_code == 200, r.text
    await worker.wait_idle()
    (cx,) = await _rows("booking_cancelled")
    (bell,) = await _bell(tid, "booking.cancelled")
    assert cx.to_email == "hatice.ozturk@uni.edu.tr" and cx.body == bell.body
    msg = _sent_to("hatice.ozturk@uni.edu.tr")[-1]
    plain, html = _parts(msg)
    assert plain.startswith(bell.body.strip())
    assert "Bölüm toplantısı" in bell.body and 'data-block="reason"' in html and "Cancelled" in html


async def test_password_reset_is_the_themed_code_mail_and_keeps_no_code(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    uid, _ = await env.user("unutkan@uni.edu.tr", firstname="Ümit", lastname="Işık")
    issued = (await env.client.post(f"/api/v1/users/{uid}/reset-token", headers=env.admin)).json()
    assert issued["emailed"] is True
    (msg,) = _sent_to("unutkan@uni.edu.tr")
    plain, html = _parts(msg)
    code = next(line for line in plain.splitlines() if line and " " not in line)
    assert 'data-block="code"' in html and code in html and "Ümit Işık" in plain
    assert "güvenlik e-postasıdır" in plain and "profile?tab=notifications" not in html
    assert msg["Subject"] == "Parola sıfırlama kodunuz"
    (row,) = await _rows("password_reset")
    assert code not in row.body and row.locale == "tr"
    ok = await env.client.post("/api/v1/auth/password-reset/confirm", json={"token": code, "password": "yeni-parola-9"})
    assert ok.status_code == 200


async def test_rendering_failure_still_sends_plain_text(env, monkeypatch):  # noqa: F811
    await _smtp(env, monkeypatch)
    from app.services import mail

    async def broken(*a, **kw):  # type: ignore[no-untyped-def]
        raise RuntimeError("template bug")

    monkeypatch.setattr(mail, "render_for", broken)
    tid, _ = await env.user("hatice.ozturk@uni.edu.tr")
    assert (await env.book(env.planner, "A102", THU, "P1", user_id=tid)).status_code == 201
    await worker.wait_idle()
    (row,) = await _rows("booking_created")
    assert row.status == "SENT"
    (msg,) = _sent_to("hatice.ozturk@uni.edu.tr")
    assert not msg.is_multipart() and msg.get_content().startswith(row.body.strip()[:20])
