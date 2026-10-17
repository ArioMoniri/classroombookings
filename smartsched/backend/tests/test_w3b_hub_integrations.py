"""W3-HUB integrations gallery: ``GET /api/v1/integrations/status`` (read-only aggregator, app/api/v1/integrations.py).

Admins only (``setup.settings`` or ``planning.admin``). The aggregator reads every area through the area's own
status function (``integration_status(session)``) when it exposes one, through public functions of the existing
calendar / channel / webhook / AI modules otherwise, and answers ``unknown`` (with an ask) when neither exists. It
never writes, never returns a secret, and every admin sees the same organisation-wide answer with the last change
(who, when).
"""

from __future__ import annotations

from typing import Any

import pytest
from app.api.v1 import integrations as hub
from app.models import AuditEvent, Setting
from app.services import webhooks
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.crbs_support import make_user

URL = "/api/v1/integrations/status"
N8N = "https://n8n.uni.edu.tr/webhook/9c1f-rezervasyon"
ZAPIER = "https://hooks.zapier.com/hooks/catch/123456/abcdef/"
BOT = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1"
TG_SECRET = "zz-telegram-secret-zz"
GOOGLE_SECRET = "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eak"


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    async def public(host: str) -> list[str]:
        return ["203.0.113.10"]  # TEST-NET-3: never a real lookup

    monkeypatch.setattr(webhooks, "resolve_host", public)


@pytest.fixture
def no_contracts(monkeypatch):
    """Identity and e-mail lanes have not exposed their status function (deterministic, whatever is on disk)."""
    monkeypatch.setattr(hub, "contract_for", lambda area: None)


def _cards(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["key"]: c for a in body["areas"] for c in a["cards"]}


async def _status(client, headers) -> dict[str, Any]:
    r = await client.get(URL, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_admins_only(client, no_contracts):
    admin = await login(client)
    assert (await client.get(URL)).status_code == 401
    _, teacher = await make_user(client, admin, "ogretmen.hub@example.com")
    r = await client.get(URL, headers=teacher)
    assert r.status_code == 403
    _, planner = await make_user(client, admin, "planlamaci.hub@example.com", role="PLANNER")
    assert (await client.get(URL, headers=planner)).status_code == 403
    assert (await client.get(URL, headers=admin)).status_code == 200


async def test_fresh_install_shape_unknown_areas_and_asks(client, no_contracts):
    body = await _status(client, await login(client))
    assert [a["key"] for a in body["areas"]] == ["identity", "email", "calendar", "channels", "automation", "ai"]
    for a in body["areas"]:
        assert a["label_tr"] and a["label_en"] and a["cards"], a["key"]
    cards = _cards(body)
    # identity / e-mail: no status function yet -> one unknown card each, with the setup link still usable
    for key in ("identity.providers", "email.smtp"):
        c = cards[key]
        assert c["status"] == "unknown" and c["source"] == "missing", c
        assert c["setup_href"].startswith("/admin/integrations?tab=")
        assert c["detail_tr"] and c["detail_en"]
    asks = {a["area"]: a for a in body["asks"]}
    assert set(asks) == {"identity", "email"}
    assert asks["identity"]["lane"] == "W3-IDP" and "integration_status" in asks["identity"]["function"]
    assert asks["email"]["lane"] == "W3-MAIL"
    # built-in readers: nothing is configured on a fresh install
    for key in ("calendar.google", "calendar.microsoft", "channels.telegram", "channels.teams", "automation.webhooks"):
        assert cards[key]["status"] == "not_configured", cards[key]
        assert cards[key]["source"] == "builtin"
    for key in ("automation.n8n", "automation.activepieces", "automation.pipedream", "automation.zapier"):
        assert cards[key]["status"] == "not_configured" and cards[key]["toggle"] is None
    assert cards["ai.providers"]["setup_href"] == "/admin/ai"
    assert body["counts"]["unknown"] == 2
    assert sum(body["counts"].values()) == len(cards)
    # every card speaks Turkish first and has one sentence of what it does
    for c in cards.values():
        assert c["name_tr"] and c["name_en"] and c["summary_tr"].endswith(".") and c["summary_en"].endswith(".")
        assert c["status"] in hub.STATUSES


async def test_contract_fakes_are_normalised_and_failures_isolated(client, monkeypatch):
    async def identity(session) -> list[dict[str, Any]]:
        return [
            {
                "key": "identity.entra",
                "name_tr": "Microsoft Entra ID",
                "name_en": "Microsoft Entra ID",
                "summary_tr": "Kurum hesabıyla oturum açma.",
                "summary_en": "Sign in with the institution account.",
                "status": "connected",
                "enabled": True,
                "last_check_at": "2026-10-17T18:00:00Z",
                "last_check_ok": True,
                "changed_by": "Ayşe Yılmaz",
                "changed_at": "2026-10-17T17:00:00Z",
                "toggle": {"method": "PUT", "path": "/identity/admin/providers/entra", "field": "enabled"},
                "client_secret": "must-be-dropped",
            },
            {"key": "identity.saml", "name_tr": "SAML", "name_en": "SAML", "status": "bogus"},
        ]

    async def email(session) -> list[dict[str, Any]]:
        raise RuntimeError("smtp password=hunter2 exploded")

    fakes = {"identity": identity, "email": email}
    monkeypatch.setattr(hub, "contract_for", lambda area: fakes.get(area))
    body = await _status(client, await login(client))
    cards = _cards(body)
    entra = cards["identity.entra"]
    assert entra["status"] == "connected" and entra["source"] == "contract" and entra["area"] == "identity"
    assert entra["changed_by"] == "Ayşe Yılmaz" and entra["last_check_ok"] is True
    assert entra["toggle"] == {
        "method": "PUT",
        "path": "/identity/admin/providers/entra",
        "field": "enabled",
        "enable_in_setup": False,
    }
    assert "client_secret" not in entra and "must-be-dropped" not in str(body)
    # an invalid status reads as unknown; a summary is filled in
    assert cards["identity.saml"]["status"] == "unknown" and cards["identity.saml"]["summary_tr"]
    # a failing area: one unknown card, no exception text (it may carry a secret)
    smtp = cards["email.smtp"]
    assert smtp["status"] == "unknown" and smtp["source"] == "contract"
    assert "hunter2" not in str(body)
    assert {a["area"] for a in body["asks"]} == set()
    # the other areas still answer
    assert cards["calendar.google"]["status"] == "not_configured"


async def test_contract_toggle_paths_are_relative_api_paths_only(client, monkeypatch):
    async def identity(session) -> list[dict[str, Any]]:
        return [
            {
                "key": "identity.x",
                "name_tr": "X",
                "name_en": "X",
                "status": "connected",
                "toggle": {"method": "PUT", "path": "https://evil.example/steal", "field": "enabled"},
                "setup_href": "javascript:alert(1)",
            }
        ]

    monkeypatch.setattr(hub, "contract_for", lambda area: identity if area == "identity" else None)
    card = _cards(await _status(client, await login(client)))["identity.x"]
    assert card["toggle"] is None
    assert card["setup_href"] == "/admin/integrations?tab=identity"


async def test_builtin_readers_on_real_settings_shared_by_admins(client, no_contracts):
    admin = await login(client)
    c = client
    r = await c.put(
        "/api/v1/calendar/admin/settings",
        json={
            "public_url": "https://planlama.uni.edu.tr",
            "google_client_id": "1234-abc.apps.googleusercontent.com",
            "google_client_secret": GOOGLE_SECRET,
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    r = await c.put(
        "/api/v1/channels/admin/telegram",
        json={
            "enabled": True,
            "secrets": {"bot_token": BOT},
            "options": {"bot_username": "uni_planlama_bot"},
            "kvkk_signoff": {"signed": True, "legal_basis": "KVKK md. 5/2-c", "officer": "Veri sorumlusu"},
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    hook = await c.post(
        "/api/v1/webhooks", json={"url": N8N, "events": ["*"], "description": "n8n akışı"}, headers=admin
    )
    assert hook.status_code == 201, hook.text
    hook_id, secret = hook.json()["id"], hook.json()["secret"]
    zap = await c.post("/api/v1/webhooks", json={"url": ZAPIER, "events": ["*"], "active": False}, headers=admin)
    assert zap.status_code == 201, zap.text

    # a second administrator sees the same organisation-wide state, with who changed it
    uid, other = await make_user(c, admin, "ikinci.yonetici@example.com", role="ADMIN")
    assert uid
    events_before = (await _count(c, AuditEvent), await _count(c, Setting))
    body = await _status(c, other)
    assert (await _count(c, AuditEvent), await _count(c, Setting)) == events_before  # read-only
    cards = _cards(body)

    g = cards["calendar.google"]
    assert g["status"] == "disabled" and g["enabled"] is False  # configured, calendar sync not switched on
    assert g["changed_by"] and g["changed_at"]
    assert g["toggle"]["path"] == "/calendar/admin/settings" and g["toggle"]["field"] == "calendar_sync_enabled"
    assert g["toggle"]["enable_in_setup"] is True  # switching on records a KVKK sign-off: done in the setup sheet
    assert cards["calendar.microsoft"]["status"] == "not_configured"

    tg = cards["channels.telegram"]
    assert tg["status"] == "connected" and tg["enabled"] is True, tg
    assert tg["toggle"] == {
        "method": "PUT",
        "path": "/channels/admin/telegram",
        "field": "enabled",
        "enable_in_setup": True,
    }
    assert tg["changed_by"]

    hooks = cards["automation.webhooks"]
    assert hooks["status"] == "disabled"  # endpoints exist, the global switch is off
    assert hooks["toggle"]["field"] == "webhooks_enabled"
    n8n = cards["automation.n8n"]
    assert n8n["ref"] == {"webhook_id": hook_id} and n8n["status"] == "disabled"
    assert n8n["toggle"]["path"] == f"/webhooks/{hook_id}" and n8n["toggle"]["field"] == "active"
    assert cards["automation.zapier"]["enabled"] is False
    assert cards["automation.pipedream"]["status"] == "not_configured"

    text = str(body)
    for leaked in (secret, GOOGLE_SECRET, BOT, "whsec_"):
        assert leaked not in text

    # switch webhooks on: n8n becomes connected; a failed delivery turns it into an error with the last check
    assert (
        await c.put("/api/v1/calendar/admin/settings", json={"webhooks_enabled": True}, headers=admin)
    ).status_code == 200
    cards = _cards(await _status(c, admin))
    assert cards["automation.n8n"]["status"] == "connected"
    assert cards["automation.webhooks"]["status"] == "connected"
    await _fail_delivery(hook_id)
    cards = _cards(await _status(c, admin))
    assert cards["automation.n8n"]["status"] == "error"
    assert cards["automation.n8n"]["last_check_ok"] is False and cards["automation.n8n"]["last_check_at"]
    assert cards["automation.n8n"]["detail_tr"]


async def test_area_reader_crash_is_unknown_not_500(client, no_contracts, monkeypatch):
    async def boom(session):
        raise RuntimeError("calendar reader broke")

    monkeypatch.setattr(hub, "BUILTINS", {**hub.BUILTINS, "calendar": boom})
    body = await _status(client, await login(client))
    cal = next(a for a in body["areas"] if a["key"] == "calendar")
    assert [c["status"] for c in cal["cards"]] == ["unknown"]
    assert "broke" not in str(body)


async def _count(client, model) -> int:  # noqa: ARG001
    from app.core import db as dbmod

    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


async def _fail_delivery(endpoint_id: int) -> None:
    from app.core import db as dbmod
    from app.models import WebhookDelivery
    from app.models.base import utcnow

    async with dbmod.get_session_factory()() as s:
        s.add(
            WebhookDelivery(
                endpoint_id=endpoint_id,
                event_id="00000000-0000-0000-0000-000000000001",
                event_type="ping",
                payload={},
                status="FAILED",
                attempts=1,
                response_status=500,
                last_error="HTTP 500",
                created_at=utcnow(),
            )
        )
        await s.commit()


async def test_live_area_contracts_feed_the_gallery(client):
    """Whatever area modules expose ``integration_status`` today answer through the hub (W3-MAIL ships
    app.services.mail_status); an area without one is listed in ``asks`` instead."""
    import importlib.util

    body = await _status(client, await login(client))
    cards = _cards(body)
    asked = {a["area"] for a in body["asks"]}
    for area, (_lane, modules) in hub.CONTRACTS.items():
        exposed = any(
            importlib.util.find_spec(m) is not None
            and callable(getattr(importlib.import_module(m), hub.CONTRACT_FN, None))
            for m in modules
        )
        area_cards = [c for c in cards.values() if c["area"] == area]
        assert area_cards, area
        if exposed:
            assert all(c["source"] == "contract" for c in area_cards), area
            assert area not in asked
        elif area in hub.BUILTINS:
            assert all(c["source"] == "builtin" for c in area_cards), area
        else:
            assert area in asked and [c["status"] for c in area_cards] == ["unknown"]
    smtp = cards["email.smtp"]
    assert smtp["status"] in hub.STATUSES and smtp["name_tr"] == "E-posta (SMTP)"


async def test_alert_relay_bell_events_once_per_occurrence_admins_only(client, monkeypatch):
    """integration.error / integration.secret_expiring through the dispatcher: once per occurrence and admin,
    never to a teacher, and nothing (no error) while the events are not registered in notify_dispatch.EVENTS."""
    from datetime import date

    from app.core import db as dbmod
    from app.models import InAppNotification
    from app.services import notify_dispatch

    async def identity(session) -> list[dict[str, Any]]:
        return [
            {
                "key": "identity.okta",
                "name_tr": "Okta",
                "name_en": "Okta",
                "status": "error",
                "detail_tr": "İstemci gizli anahtarı yanlış ya da süresi dolmuş.",
                "detail_en": "The client secret is wrong or expired.",
                "last_check_at": "2026-10-17T18:00:00Z",
                "secret_expires_at": "2026-11-01",
                "setup_href": "/admin/integrations?area=identity&setup=identity.okta",
            }
        ]

    monkeypatch.setattr(hub, "contract_for", lambda area: identity if area == "identity" else None)
    admin = await login(client)
    _, _teacher = await make_user(client, admin, "ogretmen.alert@example.com")

    async def run() -> dict[str, int]:
        async with dbmod.get_session_factory()() as s:
            return await hub.alert_pass(s, today=date(2026, 10, 17))

    # not registered yet (the integrator adds them): skipped, no exception
    events = dict(notify_dispatch.EVENTS)
    events.pop(hub.EVENT_ERROR, None)
    events.pop(hub.EVENT_SECRET, None)
    monkeypatch.setattr(notify_dispatch, "EVENTS", events)
    assert (await run())["skipped_unregistered"] == 2

    monkeypatch.setattr(
        notify_dispatch,
        "EVENTS",
        {
            **events,
            hub.EVENT_ERROR: ("Entegrasyon hataları (yöneticiler)", "Integration errors (administrators)"),
            hub.EVENT_SECRET: ("Süresi dolacak gizli anahtarlar (yöneticiler)", "Expiring secrets (administrators)"),
        },
    )
    first = await run()
    assert first["error"] == 1 and first["secret"] == 1
    again = await run()
    assert again["error"] == 0 and again["secret"] == 0  # the dispatcher's ledger: once per occurrence

    async with dbmod.get_session_factory()() as s:
        rows = list((await s.execute(select(InAppNotification))).scalars())
    titles = sorted(r.title for r in rows)
    assert titles == [
        "Entegrasyon hatası: Okta",
        "Okta: istemci gizli anahtarının süresi 15 gün sonra doluyor",
    ], titles
    assert {r.user_id for r in rows} == {1}  # the seeded administrator only, never the teacher
    assert all(r.link == "/admin/integrations?area=identity&setup=identity.okta" for r in rows)
