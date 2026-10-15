"""ROADMAP Phase 11: e-mail delivery used to run inside the request (bounded only by the SMTP timeout). Booking and
approval notifications are now queued: the outbox row is ``PENDING`` when the request returns, the integrations
worker sends it after the commit, a failure is retried with backoff (1 min, 5 min, 30 min, 2 h, 6 h) and ends
``FAILED``. Password-reset codes and the SMTP test still go out at once (their callers need the result), and
without SMTP or an address the row is ``UNSENT`` immediately as before.

Real Bahar 2026 data (``tests/crbs_env``): an approval request for the TIP room A 201 e-mails its approver.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.core import db as dbmod
from app.models import NotificationOutbox
from app.models.base import utcnow
from app.services import bookings_notify
from app.workers import integrations as worker
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.test_crbs_users import FakeSMTP

WED = date(2026, 2, 18)


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


async def _rows(kind: str) -> list[NotificationOutbox]:
    async with dbmod.get_session_factory()() as s:
        q = select(NotificationOutbox).where(NotificationOutbox.kind == kind).order_by(NotificationOutbox.id)
        return list((await s.execute(q)).scalars())


async def _setup(env, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(bookings_notify.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent, FakeSMTP.fail = [], False
    r = await env.client.put(
        "/api/v1/org/smtp",
        json={
            "host": "smtp.uni.edu.tr",
            "username": "bildirim",
            "password": "smtp-gizli",
            "from_address": "bildirim@uni.edu.tr",
        },
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    await env.user("gozde.ayrancigil@uni.edu.tr", role="ADMIN", approves_for=[{"type": "tag", "tag": "tip"}])
    r = await env.client.post(
        "/api/v1/approval-rules", json={"name": "TIP", "entity_type": "tag", "tag": "TIP"}, headers=env.admin
    )
    assert r.status_code == 201, r.text
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    return ayse


async def test_notifications_are_queued_and_sent_after_the_commit(env, monkeypatch):  # noqa: F811
    ayse = await _setup(env, monkeypatch)
    r = await env.book(ayse, "A201", WED, "P3")
    assert r.status_code == 202, r.text
    (row,) = await _rows("approval_requested")
    assert row.status in ("PENDING", "RUNNING", "SENT") and row.to_email == "gozde.ayrancigil@uni.edu.tr"
    await worker.wait_idle()
    (row,) = await _rows("approval_requested")
    assert row.status == "SENT" and row.attempts == 1 and row.sent_at is not None
    assert FakeSMTP.sent[-1]["To"] == "gozde.ayrancigil@uni.edu.tr"


async def test_failures_back_off_then_fail(env, monkeypatch):  # noqa: F811
    ayse = await _setup(env, monkeypatch)
    FakeSMTP.fail = True
    assert (await env.book(ayse, "A201", WED, "P3")).status_code == 202
    await worker.wait_idle()
    (row,) = await _rows("approval_requested")
    assert row.status == "PENDING" and row.attempts == 1 and "connection refused" in (row.error or "")
    assert row.next_attempt_at is not None and row.next_attempt_at - utcnow() > timedelta(seconds=30)
    # the retries come due; the fifth and sixth attempts fail too -> FAILED, no more attempts
    later = utcnow()
    for _ in range(worker.MAX_ATTEMPTS + 2):
        later += timedelta(hours=7)
        await worker.drain(now=later)
    (row,) = await _rows("approval_requested")
    assert row.status == "FAILED" and row.attempts == worker.MAX_ATTEMPTS
    # an administrator's manual retry still sends at once
    FakeSMTP.fail = False
    r = await env.client.post(f"/api/v1/booking-admin/outbox/{row.id}/retry", headers=env.admin)
    assert r.status_code == 200 and r.json()["status"] == "SENT", r.text


async def test_smtp_test_message_is_still_sent_at_once(env, monkeypatch):  # noqa: F811
    await _setup(env, monkeypatch)
    t = (await env.client.post("/api/v1/org/smtp/test", json={"to": "Hoca@Uni.edu.tr"}, headers=env.admin)).json()
    assert t["status"] == "SENT" and FakeSMTP.sent[-1]["To"] == "hoca@uni.edu.tr"
