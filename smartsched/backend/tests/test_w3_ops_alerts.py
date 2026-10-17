"""W3-OPS alert relay: Prometheus /api/v1/alerts -> admins through the notification dispatcher (event ``ops.alert``).

Fire once, re-notify after 6 h while still firing, resolve once; nothing is resolved when Prometheus is unreachable;
only admins (``setup.settings`` / ``planning.admin``) receive it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.core.db import get_session_factory
from app.models import InAppNotification, NotificationOutbox, User
from app.services import notify_dispatch, ops_alerts
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.crbs_support import make_user

T0 = datetime(2026, 10, 17, 18, 0, tzinfo=UTC)
ALERT = {
    "labels": {"alertname": "SmartSchedHigh5xx", "severity": "warning"},
    "annotations": {
        "summary_tr": "İsteklerin %2'sinden fazlası 5xx ile bitiyor (10 dk).",
        "summary_en": "More than 2 % 5xx.",
    },
    "state": "firing",
    "activeAt": "2026-10-17T17:50:00Z",
}


class FakeProm:
    def __init__(self) -> None:
        self.alerts: list[dict] = [ALERT]
        self.down = False
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        assert request.url.path == "/api/v1/alerts"
        return httpx.Response(200, json={"status": "success", "data": {"alerts": self.alerts}})


@pytest.fixture
def prom(monkeypatch):
    fake = FakeProm()
    real = httpx.AsyncClient
    monkeypatch.setattr(
        ops_alerts.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(fake.handler), **kw)
    )
    monkeypatch.setenv("OPS_PROMETHEUS_URL", "http://prometheus:9090")
    return fake


async def _bell(email: str) -> list[InAppNotification]:
    async with get_session_factory()() as s:
        uid = (await s.execute(select(User.id).where(User.email == email))).scalar_one()
        q = select(InAppNotification).where(InAppNotification.user_id == uid, InAppNotification.kind == "ops.alert")
        return list((await s.execute(q.order_by(InAppNotification.id))).scalars())


async def _mails() -> int:
    async with get_session_factory()() as s:
        q = select(func.count()).select_from(NotificationOutbox).where(NotificationOutbox.kind == "ops_alert")
        return (await s.execute(q)).scalar_one()


def test_event_is_known_to_the_dispatcher():
    assert "ops.alert" in notify_dispatch.EVENTS
    tr, en = notify_dispatch.EVENTS["ops.alert"]
    assert tr and en


async def test_fire_once_renotify_after_6h_resolve_once(client, prom):
    admin = await login(client)
    await make_user(client, admin, "ogretmen.alert@example.com")

    out = await ops_alerts.poll_once(now=T0)
    assert out == {"firing": 1, "notified": 1, "resolved": 0}
    bell = await _bell("admin@example.com")
    assert len(bell) == 1
    assert bell[0].title.startswith("Uyarı:") and "5xx" in bell[0].body
    assert bell[0].link == "/admin/ops"
    assert (bell[0].data or {})["status"] == "firing"
    assert await _mails() == 1
    assert await _bell("ogretmen.alert@example.com") == []

    # still firing a minute and five hours later: nothing new
    for later in (timedelta(minutes=1), timedelta(hours=5)):
        assert (await ops_alerts.poll_once(now=T0 + later))["notified"] == 0
    assert len(await _bell("admin@example.com")) == 1

    # 6 h after it started (17:50 + 6 h): one reminder
    out = await ops_alerts.poll_once(now=T0 + timedelta(hours=6))
    assert out["notified"] == 1
    assert len(await _bell("admin@example.com")) == 2
    assert (await ops_alerts.poll_once(now=T0 + timedelta(hours=6, minutes=1)))["notified"] == 0

    # Prometheus down: nothing is resolved
    prom.down = True
    assert await ops_alerts.poll_once(now=T0 + timedelta(hours=7)) == {
        "firing": 0,
        "notified": 0,
        "resolved": 0,
        "error": "ConnectError",
    }

    # gone: resolved once
    prom.down = False
    prom.alerts = []
    out = await ops_alerts.poll_once(now=T0 + timedelta(hours=8))
    assert out["resolved"] == 1
    bell = await _bell("admin@example.com")
    assert len(bell) == 3 and bell[-1].title.startswith("Çözüldü:") and (bell[-1].data or {})["status"] == "resolved"
    assert (await ops_alerts.poll_once(now=T0 + timedelta(hours=8, minutes=1)))["resolved"] == 0
    assert len(await _bell("admin@example.com")) == 3
    assert await _mails() == 3


async def test_same_alertname_other_labels_is_another_alert_and_pending_is_ignored(client, prom):
    await login(client)
    other = {**ALERT, "labels": {"alertname": "SmartSchedProbeFailed", "job": "integrations/blackbox/frontend"}}
    other2 = {**ALERT, "labels": {"alertname": "SmartSchedProbeFailed", "job": "integrations/blackbox/proxy"}}
    pending = {**ALERT, "labels": {"alertname": "SmartSchedSlowP95"}, "state": "pending"}
    prom.alerts = [other, other2, pending]
    out = await ops_alerts.poll_once(now=T0)
    assert out == {"firing": 2, "notified": 2, "resolved": 0}


async def test_english_reader_gets_english(client, prom):
    await login(client)
    async with get_session_factory()() as s:
        u = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        u.language = "en"
        await s.commit()
    await ops_alerts.poll_once(now=T0)
    bell = await _bell("admin@example.com")
    assert bell[0].title.startswith("Alert:") and "More than 2 % 5xx." in bell[0].body


async def test_unconfigured_prometheus_is_a_no_op(client, monkeypatch):
    monkeypatch.delenv("OPS_PROMETHEUS_URL", raising=False)
    assert await ops_alerts.poll_once(now=T0) == {"firing": 0, "notified": 0, "resolved": 0, "error": "not_configured"}
