"""Fakes for the notification-channel tests (no network anywhere).

* Apprise: ``apprise.Apprise.notify`` is replaced. Apprise still parses every URL (a malformed sender URL fails like
  in production); the fake records ``(url, title, body)`` and returns ``net.apprise_ok``. On failure it logs through
  the ``apprise`` logger the way the library does, URL included, so the redaction can be checked.
* pywebpush: the payload encryption (RFC 8291) is real; the POST to the push service goes to an
  ``httpx.MockTransport`` through ``app.services.channels.transport.http_client``.
* Telegram Bot API and the WhatsApp Web bridge: the same mock transport, routed by host.
* DNS: ``app.services.webhooks.resolve_host`` answers from ``net.dns`` (a public address by default).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

PUBLIC_IP = "52.95.110.1"
# every fake credential is built at runtime: a literal shaped like a provider secret trips GitHub push protection
BOT_TOKEN = "7712345678" + ":" + "AAH" + "k9-fake-telegram-key-" + "xyz012345"
TWILIO_SID = "AC" + "0123456789abcdef" * 2  # built at runtime: a literal trips GitHub push protection
TWILIO_TOKEN = "f00dfeed" * 4
WA_TOKEN = "EAAG" + "fakeWhatsAppCloudToken" + "0123456789"
OFFICER = "KVKK irtibat kişisi Elif Şahin"
SLACK_URL = "https://hooks.slack.com/services/" + "/".join(("T" + "0123ABCD", "B" + "0456EFGH", "fakeSlackHookPart" + "0123"))
TEAMS_URL = (
    "https://prod-12.westeurope.logic.azure.com:443/workflows/4f1c2b9a7d6e/triggers/manual/paths/invoke"
    + "?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig="
    + "fakeSignature-"
    + "0123456789abcdef"
)
LEGAL = "KVKK m. 9 (7499 s. Kanun) standart sözleşme, Kurula bildirildi 2026-10-14"


@dataclass
class FakeNet:
    sent: list[tuple[str, str, str]] = field(default_factory=list)  # (apprise url, title, body)
    apprise_ok: bool = True
    requests: list[httpx.Request] = field(default_factory=list)
    dns: dict[str, list[str]] = field(default_factory=dict)
    push_status: int = 201
    telegram_updates: list[dict[str, Any]] = field(default_factory=list)
    bridge_logged_in: bool = False
    routes: dict[str, Callable[[httpx.Request], httpx.Response]] = field(default_factory=dict)

    def bodies(self) -> list[str]:
        return [b for _u, _t, b in self.sent]

    def telegram_calls(self, method: str) -> list[dict[str, Any]]:
        out = []
        for r in self.requests:
            if r.url.host == "api.telegram.org" and r.url.path.endswith("/" + method):
                out.append(json.loads(r.content or b"{}"))
        return out

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        if host in self.routes:
            return self.routes[host](request)
        if host == "api.telegram.org":
            method = request.url.path.rsplit("/", 1)[-1]
            if method == "getMe":
                return httpx.Response(200, json={"ok": True, "result": {"id": 7712345678, "username": "SmartSchedUniBot"}})
            if method == "setWebhook":
                return httpx.Response(200, json={"ok": True, "result": True})
            if method == "getUpdates":
                updates, self.telegram_updates = self.telegram_updates, []
                return httpx.Response(200, json={"ok": True, "result": updates})
            return httpx.Response(404, json={"ok": False})
        if host == "wa-bridge":
            path = request.url.path
            if path == "/session/connect":
                return httpx.Response(200, json={"code": 200, "data": {"details": "Connected!"}, "success": True})
            if path == "/session/qr":
                return httpx.Response(
                    200, json={"code": 200, "data": {"QRCode": "data:image/png;base64,iVBORw0KGgo="}, "success": True}
                )
            if path == "/session/status":
                return httpx.Response(
                    200,
                    json={"code": 200, "data": {"connected": True, "loggedIn": self.bridge_logged_in}, "success": True},
                )
            if path == "/chat/send/text":
                return httpx.Response(200, json={"code": 200, "data": {"Details": "Sent"}, "success": True})
            if path == "/session/logout":
                return httpx.Response(200, json={"code": 200, "data": {"Details": "Logged out"}, "success": True})
        # a browser push service
        return httpx.Response(self.push_status)


@pytest.fixture
def net(monkeypatch) -> Iterator[FakeNet]:  # type: ignore[no-untyped-def]
    import apprise
    from app.services import webhooks
    from app.services.channels import transport

    fake = FakeNet()

    def notify(self, body="", title="", **_kw):  # type: ignore[no-untyped-def]
        urls = [s.url(privacy=False) for s in self]
        for u in urls:
            fake.sent.append((u, title, body))
        if not fake.apprise_ok:
            logging.getLogger("apprise").warning("Failed to send notification to %s: HTTP 500", urls[0])
        return fake.apprise_ok

    async def resolve(host: str) -> list[str]:
        return fake.dns.get(host, [PUBLIC_IP])

    def client(**_kw: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(fake.handle), timeout=5)

    monkeypatch.setattr(apprise.Apprise, "notify", notify)
    monkeypatch.setattr(webhooks, "resolve_host", resolve)
    monkeypatch.setattr(transport, "http_client", client)
    monkeypatch.setattr(transport, "bridge_client", client)
    monkeypatch.setenv("WHATSAPP_BRIDGE_URL", "http://wa-bridge:8080")
    from app.services.channels import outbox

    monkeypatch.setattr(outbox, "_schedule", lambda delay=0.0: None)  # tests drain explicitly (no background race)
    from app.services import channels

    channels.register()  # the start-up hook (explicit; nothing registers on import)
    yield fake
    channels.unregister()


async def enable(  # type: ignore[no-untyped-def]
    client,
    admin: dict[str, str],
    kind: str,
    *,
    secrets: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
    content_mode: str = "link_only",
    sign: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {"enabled": True, "content_mode": content_mode, **extra}
    if secrets is not None:
        body["secrets"] = secrets
    if options is not None:
        body["options"] = options
    if sign:
        body["kvkk_signoff"] = {"signed": True, "legal_basis": LEGAL, "officer": OFFICER}
    r = await client.put(f"/api/v1/channels/admin/{kind}", json=body, headers=admin)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def enable_telegram(client, admin, **kw: Any) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return await enable(
        client, admin, "telegram", secrets={"bot_token": BOT_TOKEN}, options={"bot_username": "SmartSchedUniBot"}, **kw
    )


async def drain() -> int:
    from app.models.base import utcnow
    from app.services.channels import outbox

    return await outbox.drain_due(utcnow(), 200)


async def link_telegram(client, net: FakeNet, headers: dict[str, str], chat_id: int = 5550001) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Link through the deep link and the bot webhook, as Telegram would deliver ``/start <code>``."""
    from app.core import db as dbmod
    from app.services.channels import config

    r = await client.post("/api/v1/me/channels/telegram/link", headers=headers)
    assert r.status_code == 201, r.text
    code = r.json()["deep_link"].split("start=", 1)[1]
    async with dbmod.get_session_factory()() as s:
        secret = (await config.load(s, "telegram")).secrets["webhook_secret"]
    update = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": chat_id, "type": "private"}, "text": f"/start {code}"},
    }
    r = await client.post(
        "/api/v1/channels/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": secret}
    )
    assert r.status_code == 200, r.text
    return dict(r.json())
