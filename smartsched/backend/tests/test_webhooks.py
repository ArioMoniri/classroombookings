"""Outgoing webhooks (docs/product/calendar-sync-api.md §4) on the real Bahar 2026 import: admin-only CRUD, URL
rules, the off-by-default switch, HMAC-SHA256 signatures checked with the contract's verification snippet,
booking / approval events through ``publish_event``, retries with backoff, the delivery log, redelivery and the
automatic switch-off after five failed deliveries."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, timedelta

import pytest
from app.core import db as dbmod
from app.models import ApprovalRequest, InAppNotification, WebhookDelivery, WebhookEndpoint
from app.models.base import utcnow
from app.services import events, webhooks
from app.workers import integrations as worker
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import Receiver, client_factory

MON = date(2026, 2, 16)
HOOK = "https://otomasyon.uni.edu.tr/api/v1/webhooks/ap-flow-1"


def verify(secret: str, body: bytes, timestamp: str, signature: str, tolerance: int = 300) -> bool:
    """Verbatim from docs/product/calendar-sync-api.md §4 (what receivers run)."""
    if abs(time.time() - int(timestamp)) > tolerance:
        return False
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + mac, signature)


@pytest.fixture
def receiver(monkeypatch) -> Receiver:
    rec = Receiver()
    monkeypatch.setattr(webhooks, "http_client", client_factory(rec))

    async def public_dns(host: str) -> list[str]:
        return ["203.0.113.10"]  # TEST-NET-3: never a real lookup in tests

    monkeypatch.setattr(webhooks, "resolve_host", public_dns)
    return rec


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


async def create_hook(env, events_: list[str] | None = None, url: str = HOOK) -> dict:  # noqa: F811
    r = await env.client.post(
        "/api/v1/webhooks",
        json={"url": url, "events": events_ or ["*"], "description": " Activepieces  akışı "},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def enable(env, on: bool = True) -> None:  # noqa: F811
    r = await env.client.put("/api/v1/calendar/admin/settings", json={"webhooks_enabled": on}, headers=env.admin)
    assert r.status_code == 200, r.text


async def test_admin_only_crud_url_rules_and_secret_shown_once(env, receiver):  # noqa: F811
    c = env.client
    _, teacher = await env.user("webhook.yok@uni.edu.tr")
    assert (await c.get("/api/v1/webhooks", headers=teacher)).status_code == 403
    assert (await c.post("/api/v1/webhooks", json={"url": HOOK, "events": ["*"]}, headers=teacher)).status_code == 403
    for bad in (
        "http://169.254.169.254/latest/meta-data",
        "https://user:pw@hooks.uni.edu.tr/x",
        "ftp://hooks.uni.edu.tr/x",
        "http://[fe80::1]/x",
        "http://metadata.google.internal/x",
    ):
        r = await c.post("/api/v1/webhooks", json={"url": bad, "events": ["*"]}, headers=env.admin)
        assert r.status_code == 422, bad
    r = await c.post("/api/v1/webhooks", json={"url": HOOK, "events": ["booking.deleted"]}, headers=env.admin)
    assert r.status_code == 422
    hook = await create_hook(env, ["BOOKING.CREATED", "booking.cancelled", "booking.created"])
    assert hook["events"] == ["booking.created", "booking.cancelled"] and hook["description"] == "Activepieces akışı"
    assert hook["secret"].startswith("whsec_") and hook["secret_hint"] == "…" + hook["secret"][-4:]
    listed = (await c.get("/api/v1/webhooks", headers=env.admin)).json()
    assert hook["secret"] not in json.dumps(listed) and listed[0]["id"] == hook["id"]
    async with dbmod.get_session_factory()() as s:
        row = await s.get(WebhookEndpoint, hook["id"])
        assert row is not None and hook["secret"] not in row.secret_enc  # encrypted at rest
    upd = await c.put(f"/api/v1/webhooks/{hook['id']}", json={"events": ["*"], "active": False}, headers=env.admin)
    assert upd.json()["events"] == ["*"] and upd.json()["active"] is False
    new_secret = (await c.post(f"/api/v1/webhooks/{hook['id']}/secret", headers=env.admin)).json()["secret"]
    assert new_secret != hook["secret"]
    assert (await c.get("/api/v1/webhooks/event-types", headers=env.admin)).json()[:3] == [
        "booking.created",
        "booking.updated",
        "booking.cancelled",
    ]
    in_pod = await create_hook(env, url="http://activepieces/api/v1/webhooks/abc")  # the optional in-pod engine
    assert in_pod["url"].startswith("http://activepieces/")
    assert (await c.delete(f"/api/v1/webhooks/{hook['id']}", headers=env.admin)).status_code == 204
    assert (await c.get(f"/api/v1/webhooks/{hook['id']}", headers=env.admin)).status_code == 404


async def test_signed_booking_events_when_enabled(env, receiver):  # noqa: F811
    c = env.client
    hook = await create_hook(env)
    _, teacher = await env.user("imzali@uni.edu.tr", displayname="Gülşen Ağaoğlu")
    # switched off by default: bookings queue nothing, a test ping still goes out
    await env.book(teacher, "A101", MON, "P2")
    ping = (await c.post(f"/api/v1/webhooks/{hook['id']}/test", headers=env.admin)).json()
    await worker.wait_idle()
    assert [r.headers["x-smartsched-event"] for r in receiver.received] == ["ping"]
    assert ping["delivery_id"]
    await enable(env)
    b = (await env.book(teacher, "A101", MON, "P1", notes="Gizli not: sınav soruları")).json()
    await c.put(f"/api/v1/bookings/{b['id']}", json={"notes": "Yeni not"}, headers=teacher)
    await c.post(f"/api/v1/bookings/{b['id']}/cancel", json={"reason": "Hasta"}, headers=teacher)
    await worker.wait_idle()
    got = receiver.received[1:]
    assert [r.headers["x-smartsched-event"] for r in got] == ["booking.created", "booking.updated", "booking.cancelled"]
    for r in got:
        assert verify(
            hook["secret"], r.content, r.headers["x-smartsched-timestamp"], r.headers["x-smartsched-signature"]
        )
        assert not verify(
            "whsec_wrong", r.content, r.headers["x-smartsched-timestamp"], r.headers["x-smartsched-signature"]
        )
        assert r.headers["user-agent"] == "SmartSched-Webhooks/1" and r.headers["content-type"] == "application/json"
    created = json.loads(got[0].content)
    assert created["type"] == "booking.created" and created["id"] == got[0].headers["x-smartsched-event-id"]
    [booking] = created["data"]["bookings"]
    assert booking["id"] == b["id"] and booking["room"] == {"id": env.rooms["A101"], "code": "A101", "name": "A 101"}
    assert booking["date"] == "2026-02-16" and booking["start"] == "08:30" and booking["end"] == "09:10"
    assert booking["user"]["name"] == "Gülşen Ağaoğlu" and created["actor"]["name"] == "Gülşen Ağaoğlu"
    raw = b"".join(r.content for r in got).decode()
    assert "Gizli" not in raw and "Yeni not" not in raw and "imzali@uni.edu.tr" not in raw  # no notes, no e-mail
    cancelled = json.loads(got[2].content)
    assert cancelled["reason"] == "Hasta" and cancelled["data"]["bookings"][0]["status"] == "CANCELLED"
    log = (await c.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json()
    assert [d["status"] for d in log] == ["SENT"] * 4 and all(d["response_status"] == 200 for d in log)
    # an endpoint that only wants cancellations gets only those
    only = await create_hook(env, ["booking.cancelled"])
    receiver.received.clear()
    x = (await env.book(teacher, "A101", MON, "P3")).json()
    await c.post(f"/api/v1/bookings/{x['id']}/cancel", json={}, headers=teacher)
    await worker.wait_idle()
    by_hook = {}
    async with dbmod.get_session_factory()() as s:
        for d in (await s.execute(select(WebhookDelivery).where(WebhookDelivery.endpoint_id == only["id"]))).scalars():
            by_hook.setdefault(d.endpoint_id, []).append(d.event_type)
    assert by_hook == {only["id"]: ["booking.cancelled"]}


async def test_retries_backoff_redeliver_and_switch_off_after_five_failures(env, receiver):  # noqa: F811
    c = env.client
    await enable(env)
    hook = await create_hook(env)
    receiver.statuses = [500]
    _, teacher = await env.user("tekrar@uni.edu.tr")
    await env.book(teacher, "A101", MON, "P1")
    await worker.wait_idle()
    [d] = (await c.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json()
    assert (
        d["status"] == "PENDING"
        and d["attempts"] == 1
        and d["response_status"] == 500
        and d["last_error"] == "HTTP 500"
    )
    await worker.drain(now=utcnow() + timedelta(seconds=30))
    assert len(receiver.received) == 1  # not due yet (first retry after 1 minute)
    await worker.drain(now=utcnow() + timedelta(minutes=2))
    [d] = (await c.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json()
    assert d["status"] == "SENT" and d["attempts"] == 2
    assert (
        receiver.received[0].headers["x-smartsched-event-id"] == receiver.received[1].headers["x-smartsched-event-id"]
    )
    again = (await c.post(f"/api/v1/webhooks/deliveries/{d['id']}/redeliver", headers=env.admin)).json()
    await worker.wait_idle()
    assert again["event_id"] == d["event_id"] and len(receiver.received) == 3
    # an unreachable receiver: every delivery runs out of attempts (1 + 5 retries); five in a row switch it off
    receiver.raise_error = True
    for _ in range(5):
        await c.post(f"/api/v1/webhooks/{hook['id']}/test", headers=env.admin)
    await worker.wait_idle()
    later = utcnow()
    for _ in range(6):
        later += timedelta(hours=7)
        await worker.drain(now=later)
    failed = (
        await c.get(f"/api/v1/webhooks/{hook['id']}/deliveries", params={"status": "FAILED"}, headers=env.admin)
    ).json()
    assert len(failed) == 5 and all(f["attempts"] == 6 and f["last_error"] == "ConnectError" for f in failed)
    state = (await c.get(f"/api/v1/webhooks/{hook['id']}", headers=env.admin)).json()
    assert state["active"] is False and "5 deliveries" in state["disabled_reason"]
    async with dbmod.get_session_factory()() as s:
        notes = list(
            (await s.execute(select(InAppNotification).where(InAppNotification.kind == "webhook.disabled"))).scalars()
        )
    assert len(notes) == 1 and HOOK in notes[0].body
    # switched off: new events are not queued for it; switching it on again clears the counter
    before = len((await c.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json())
    await env.book(teacher, "A101", MON, "P2")
    await worker.wait_idle()
    assert len((await c.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json()) == before
    on = (await c.put(f"/api/v1/webhooks/{hook['id']}", json={"active": True}, headers=env.admin)).json()
    assert on["active"] and on["consecutive_failures"] == 0 and on["disabled_reason"] is None


async def test_resolved_metadata_address_is_refused_at_delivery(env, receiver, monkeypatch):  # noqa: F811
    await enable(env)
    hook = await create_hook(env, url="https://hooks.uni.edu.tr/x")

    async def rebinding(host: str) -> list[str]:
        return ["169.254.169.254"]

    monkeypatch.setattr(webhooks, "resolve_host", rebinding)
    await env.client.post(f"/api/v1/webhooks/{hook['id']}/test", headers=env.admin)
    await worker.wait_idle()
    [d] = (await env.client.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json()
    assert d["status"] == "FAILED" and "link-local" in d["last_error"] and receiver.received == []


async def test_approval_events_carry_the_request(env, receiver):  # noqa: F811
    await enable(env)
    hook = await create_hook(env, ["approval.requested", "approval.approved"])
    _, teacher = await env.user("onay.talebi@uni.edu.tr")
    b = (await env.book(teacher, "A101", MON, "P1")).json()
    async with dbmod.get_session_factory()() as s:
        req = ApprovalRequest(
            booking_id=b["id"],
            room_id=env.rooms["A101"],
            term_id=env.term_id,
            status="PENDING",
            step=1,
            rule_snapshot={},
        )
        s.add(req)
        await s.flush()
        await events.publish_event(s, "approval.request", "approval_request", req.id, after={"status": "PENDING"})
        await events.publish_event(s, "approval.reject", "approval_request", req.id, after={"status": "REJECTED"})
        await s.commit()
        req_id = req.id
    await worker.wait_idle()
    assert [r.headers["x-smartsched-event"] for r in receiver.received] == [
        "approval.requested"
    ]  # reject not subscribed
    body = json.loads(receiver.received[0].content)
    assert body["data"]["approval"]["id"] == req_id and body["data"]["approval"]["booking_id"] == b["id"]
    assert [x["id"] for x in body["data"]["bookings"]] == [b["id"]]
    assert verify(
        hook["secret"],
        receiver.received[0].content,
        receiver.received[0].headers["x-smartsched-timestamp"],
        receiver.received[0].headers["x-smartsched-signature"],
    )
