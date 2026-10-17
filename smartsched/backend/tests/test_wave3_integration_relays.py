"""Wave-3 integration (W3-HUB follow-up): the integrations alert pass (``integration.error`` /
``integration.secret_expiring``) starts next to the Prometheus alert relay, once per process and never in tests,
and both stop at shutdown; both events are switchable notification events."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.v1 import integrations
from app.core import config
from app.core import observability as obs
from app.services import notify_dispatch, ops_alerts


def _record(monkeypatch, env: str) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(environment=env))
    monkeypatch.setattr(ops_alerts, "start", lambda *a, **k: calls.append("ops"))
    monkeypatch.setattr(integrations, "start_alert_relay", lambda *a, **k: calls.append("integrations"))
    monkeypatch.setattr(obs, "_relay_started", False)
    return calls


def test_both_relays_start_outside_tests(monkeypatch):
    calls = _record(monkeypatch, "prod")
    obs._start_relay()
    assert calls == ["ops", "integrations"] and obs._relay_started is True


def test_no_relay_in_tests(monkeypatch):
    calls = _record(monkeypatch, "test")
    obs._start_relay()
    assert calls == []


async def test_stop_relays_stops_both(monkeypatch):
    calls: list[str] = []

    async def ops_stop() -> None:
        calls.append("ops")

    async def hub_stop() -> None:
        calls.append("integrations")

    monkeypatch.setattr(ops_alerts, "stop", ops_stop)
    monkeypatch.setattr(integrations, "stop_alert_relay", hub_stop)
    await obs.stop_relays()
    assert calls == ["ops", "integrations"]


def test_integration_events_are_registered():
    assert notify_dispatch.EVENTS["integration.error"] == (
        "Entegrasyon hataları (yöneticiler)",
        "Integration errors (administrators)",
    )
    assert notify_dispatch.EVENTS["integration.secret_expiring"] == (
        "Süresi dolacak gizli anahtarlar (yöneticiler)",
        "Expiring client secrets (administrators)",
    )
