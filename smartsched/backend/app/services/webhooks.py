"""Outgoing webhooks (docs/product/calendar-sync-api.md §4; booking-enhancements A2 and the integrations decision).

Administrators register URLs with a secret and an event list. A ``publish_event`` subscriber turns booking and
approval mutations into ``webhook_deliveries`` rows (one per endpoint, inside the transaction of the change); the
integrations worker POSTs them signed with HMAC-SHA256 over ``"<timestamp>.<body>"``, retries 1 min / 5 min /
30 min / 2 h / 6 h and keeps the outcome as the delivery log. Five deliveries in a row that end ``FAILED`` switch
the endpoint off and tell its creator (in-app notification). Activepieces, n8n and similar tools consume these
without extra code.

Automations send data outside the pod, so ``integrations.webhooks_enabled`` (default off) gates the queueing
(decision text: "Automations that send data outside the pod require their own toggle and are logged"). Payloads
carry no booking notes and no e-mail addresses (KVKK data minimisation).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.security import decrypt_secret, encrypt_secret
from app.importers import normalize as n
from app.models import (
    ApprovalRequest,
    Booking,
    BookingPeriod,
    InAppNotification,
    Program,
    User,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.models.base import utcnow
from app.models.catalog import Room
from app.models.integrations import FAILED, PENDING, RUNNING, SENT
from app.services.bookings_settings import get_value
from app.workers import integrations as worker

EVENT_TYPES: tuple[str, ...] = (
    "booking.created",
    "booking.updated",
    "booking.cancelled",
    "approval.requested",
    "approval.step",
    "approval.approved",
    "approval.rejected",
    "approval.expired",
    "approval.withdrawn",
    "ping",
)
#: ``publish_event`` actions (the audit action names) -> webhook event types
ACTION_TYPES: dict[str, str] = {
    "booking.create": "booking.created",
    "series.create": "booking.created",
    "booking.update": "booking.updated",
    "booking.move": "booking.updated",
    "booking.restore": "booking.updated",
    "booking.cancel": "booking.cancelled",
    "approval.request": "approval.requested",
    "approval.step": "approval.step",
    "approval.approve": "approval.approved",
    "approval.reject": "approval.rejected",
    "approval.expire": "approval.expired",
    "approval.withdraw": "approval.withdrawn",
}
DISABLE_AFTER_FAILURES = 5
TIMEOUT_S = 10.0
USER_AGENT = "SmartSched-Webhooks/1"
_BLOCKED_NETS = (
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, cloud metadata (169.254.169.254)
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fd00:ec2::254/128"),  # AWS IMDS over IPv6
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::/128"),
)
_BLOCKED_HOSTS = frozenset({"metadata.google.internal", "metadata", "instance-data"})


def http_client() -> httpx.AsyncClient:
    """Outbound client for deliveries (tests replace this function with one on an ``httpx.MockTransport``)."""
    return httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False)


async def resolve_host(host: str) -> list[str]:
    """Addresses of ``host`` (empty when it does not resolve; the delivery then fails like any network error)."""
    try:
        infos = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, None), timeout=5)
    except (OSError, TimeoutError, UnicodeError):
        return []
    return sorted({str(i[4][0]) for i in infos})


def _blocked_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in net for net in _BLOCKED_NETS if net.version == ip.version)


def validate_url(value: Any) -> str:
    """``http(s)://host[:port]/path``; no user info; no link-local / metadata targets. Raises ``ValueError``."""
    url = n.clean_text(value) or ""
    if len(url) > 2048:
        raise ValueError("URL too long")
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http"):
        raise ValueError("webhook URL must start with https:// or http://")
    if not parts.hostname:
        raise ValueError("webhook URL needs a host")
    if parts.username or parts.password:
        raise ValueError("webhook URL must not contain user:password")
    host = parts.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS or _blocked_ip(host):
        raise ValueError("link-local and cloud metadata addresses are not allowed")
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError("invalid port") from exc
    return url


def validate_events(values: list[Any]) -> list[str]:
    out: list[str] = []
    for v in values:
        name = (n.clean_text(v) or "").lower()
        if name == "*":
            return ["*"]
        if name not in EVENT_TYPES:
            raise ValueError(f"unknown event type {v!r}; one of {', '.join(EVENT_TYPES)} or *")
        if name not in out:
            out.append(name)
    if not out:
        raise ValueError("choose at least one event type (or *)")
    return out


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def secret_of(endpoint: WebhookEndpoint) -> str:
    return decrypt_secret(endpoint.secret_enc)


def set_secret(endpoint: WebhookEndpoint, secret: str) -> None:
    endpoint.secret_enc = encrypt_secret(secret)
    endpoint.secret_hint = secret[-4:]


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def endpoint_out(e: WebhookEndpoint) -> dict[str, Any]:
    return {
        "id": e.id,
        "url": e.url,
        "description": e.description,
        "events": list(e.events or []),
        "active": e.active,
        "consecutive_failures": e.consecutive_failures,
        "disabled_reason": e.disabled_reason,
        "secret_hint": f"…{e.secret_hint}" if e.secret_hint else None,
        "created_at": _iso(e.created_at),
        "updated_at": _iso(e.updated_at),
    }


def delivery_out(d: WebhookDelivery) -> dict[str, Any]:
    return {
        "id": d.id,
        "webhook_id": d.endpoint_id,
        "event_id": d.event_id,
        "event_type": d.event_type,
        "status": d.status,
        "attempts": d.attempts,
        "next_attempt_at": _iso(d.next_attempt_at) if d.status == PENDING else None,
        "response_status": d.response_status,
        "response_ms": d.response_ms,
        "last_error": d.last_error,
        "created_at": _iso(d.created_at),
        "delivered_at": _iso(d.delivered_at),
    }


def subscribed(endpoint: WebhookEndpoint, event_type: str) -> bool:
    events = endpoint.events or []
    return "*" in events or event_type in events


# --------------------------------------------------------------------------------------------------
# Payloads
# --------------------------------------------------------------------------------------------------


def _name(u: User | None) -> str | None:
    return (u.full_name or u.username or f"#{u.id}") if u is not None else None


async def bookings_data(session: AsyncSession, ids: list[int]) -> list[dict[str, Any]]:
    """The bookings as automations see them: no notes, no e-mail addresses."""
    if not ids:
        return []
    rows = (await session.execute(select(Booking).where(Booking.id.in_(ids)).order_by(Booking.id))).scalars()
    out = []
    for b in rows:
        room = await session.get(Room, b.room_id)
        period = await session.get(BookingPeriod, b.period_id)
        user = await session.get(User, b.user_id) if b.user_id else None
        dep = await session.get(Program, b.department_id) if b.department_id else None
        out.append(
            {
                "id": b.id,
                "status": b.status,
                "date": b.date.isoformat(),
                "start": f"{period.time_start:%H:%M}" if period else None,
                "end": f"{period.time_end:%H:%M}" if period else None,
                "period": period.name if period else None,
                "room": {"id": room.id, "code": room.code, "name": room.display_name} if room else None,
                "user": {"id": user.id, "name": _name(user)} if user else None,
                "department": {"id": dep.id, "name": dep.name} if dep else None,
                "term_id": b.term_id,
                "series_id": b.series_id,
            }
        )
    return out


async def event_payload(
    session: AsyncSession, event_type: str, ev: Any, booking_ids: list[int], event_id: str
) -> dict[str, Any]:
    actor = await session.get(User, ev.actor_id) if ev.actor_id else None
    data: dict[str, Any] = {"bookings": await bookings_data(session, booking_ids)}
    if ev.entity_type == "approval_request" and str(ev.entity_id or "").isdigit():
        req = await session.get(ApprovalRequest, int(ev.entity_id))
        if req is not None:
            data["approval"] = {
                "id": req.id,
                "status": req.status,
                "step": req.step,
                "booking_id": req.booking_id,
                "series_id": req.series_id,
                "room_id": req.room_id,
                "requested_by": req.requested_by,
            }
    return {
        "id": event_id,
        "type": event_type,
        "created_at": utcnow().isoformat(timespec="seconds") + "Z",
        "actor": {"id": actor.id, "name": _name(actor)} if actor else None,
        "reason": ev.reason,
        "audit_id": ev.audit_id,
        "data": data,
    }


async def enabled(session: AsyncSession) -> bool:
    return bool(await get_value(session, "integrations", "webhooks_enabled"))


async def queue_delivery(
    session: AsyncSession, endpoint: WebhookEndpoint, event_type: str, payload: dict[str, Any]
) -> WebhookDelivery:
    d = WebhookDelivery(
        endpoint_id=endpoint.id,
        event_id=str(payload.get("id") or uuid.uuid4()),
        event_type=event_type,
        payload=payload,
        status=PENDING,
        next_attempt_at=utcnow(),
    )
    session.add(d)
    await session.flush()
    worker.kick_after_commit(session)
    return d


async def on_event(session: AsyncSession, ev: Any, booking_ids: list[int]) -> int:
    """Queue one delivery per subscribed active endpoint (called by the ``publish_event`` subscriber)."""
    event_type = ACTION_TYPES.get(ev.action)
    if event_type is None or not await enabled(session):
        return 0
    endpoints = [
        e
        for e in (await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.active.is_(True)))).scalars()
        if subscribed(e, event_type)
    ]
    if not endpoints:
        return 0
    payload = await event_payload(session, event_type, ev, booking_ids, str(uuid.uuid4()))
    for e in endpoints:
        await queue_delivery(session, e, event_type, payload)
    return len(endpoints)


async def ping(session: AsyncSession, endpoint: WebhookEndpoint, actor: User) -> WebhookDelivery:
    event_id = str(uuid.uuid4())
    payload = {
        "id": event_id,
        "type": "ping",
        "created_at": utcnow().isoformat(timespec="seconds") + "Z",
        "actor": {"id": actor.id, "name": _name(actor)},
        "reason": None,
        "audit_id": None,
        "data": {"webhook_id": endpoint.id},
    }
    return await queue_delivery(session, endpoint, "ping", payload)


async def redeliver(session: AsyncSession, d: WebhookDelivery) -> WebhookDelivery:
    copy = WebhookDelivery(
        endpoint_id=d.endpoint_id,
        event_id=d.event_id,
        event_type=d.event_type,
        payload=d.payload,
        status=PENDING,
        next_attempt_at=utcnow(),
    )
    session.add(copy)
    await session.flush()
    worker.kick_after_commit(session)
    return copy


async def delete_endpoint(session: AsyncSession, endpoint: WebhookEndpoint) -> None:
    await session.execute(delete(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint.id))
    await session.delete(endpoint)
    await session.flush()


# --------------------------------------------------------------------------------------------------
# Delivery (worker)
# --------------------------------------------------------------------------------------------------


async def _disable(session: AsyncSession, endpoint: WebhookEndpoint) -> None:
    endpoint.active = False
    endpoint.disabled_reason = f"{DISABLE_AFTER_FAILURES} deliveries in a row failed"
    endpoint.updated_at = utcnow()
    if endpoint.created_by:
        session.add(
            InAppNotification(
                user_id=endpoint.created_by,
                kind="webhook.disabled",
                title="Webhook kapatıldı / Webhook switched off",
                body=f"{endpoint.url}: {endpoint.disabled_reason}",
                link="/admin/integrations",
            )
        )


async def _attempt(endpoint: WebhookEndpoint, d: WebhookDelivery, client: httpx.AsyncClient) -> tuple[bool, bool]:
    """POST once. Returns (delivered, retryable); fills the response fields on ``d``."""
    host = (urlsplit(endpoint.url).hostname or "").lower()
    addresses = await resolve_host(host)
    if host in _BLOCKED_HOSTS or any(_blocked_ip(a) for a in [host, *addresses]):
        d.last_error = "the URL resolves to a link-local / metadata address"
        return False, False
    body = json.dumps(d.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-SmartSched-Event": d.event_type,
        "X-SmartSched-Delivery": str(d.id),
        "X-SmartSched-Event-Id": d.event_id,
        "X-SmartSched-Timestamp": ts,
        "X-SmartSched-Signature": sign(secret_of(endpoint), ts, body),
    }
    started = time.monotonic()
    try:
        resp = await client.post(endpoint.url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        d.response_ms = int((time.monotonic() - started) * 1000)
        d.response_status, d.last_error = None, f"{type(exc).__name__}"[:300]
        return False, True
    d.response_ms = int((time.monotonic() - started) * 1000)
    d.response_status = resp.status_code
    if 200 <= resp.status_code < 300:
        d.last_error = None
        return True, False
    d.last_error = f"HTTP {resp.status_code}"
    return False, True


async def _deliver(session: AsyncSession, d: WebhookDelivery, client: httpx.AsyncClient, now: datetime) -> None:
    endpoint = await session.get(WebhookEndpoint, d.endpoint_id)
    if endpoint is None:
        d.status, d.last_error = FAILED, "webhook deleted"
        return
    if not endpoint.active and d.event_type != "ping":
        d.status, d.last_error = FAILED, "webhook switched off"
        return
    d.attempts += 1
    try:
        ok, retryable = await _attempt(endpoint, d, client)
    except ValueError as exc:  # the secret cannot be decrypted (APP_SECRET changed)
        ok, retryable = False, False
        d.last_error = str(exc)[:300]
    if ok:
        d.status, d.delivered_at, d.locked_until = SENT, now, None
        endpoint.consecutive_failures = 0
        return
    retry_at = worker.next_attempt(d.attempts, now) if retryable else None
    if retry_at is not None:
        d.status, d.next_attempt_at, d.locked_until = PENDING, retry_at, None
        return
    d.status, d.locked_until = FAILED, None
    endpoint.consecutive_failures = (endpoint.consecutive_failures or 0) + 1
    if endpoint.active and endpoint.consecutive_failures >= DISABLE_AFTER_FAILURES:
        await _disable(session, endpoint)


async def drain_due(now: datetime, limit: int) -> int:
    factory = get_session_factory()
    async with factory() as session:
        q = worker.due(WebhookDelivery, now).order_by(WebhookDelivery.id).limit(limit)
        ids = list((await session.execute(q)).scalars())
    done = 0
    async with http_client() as client:
        for did in ids:
            async with factory() as session:
                if not await worker.claim(session, WebhookDelivery, did, now):
                    continue
                d = await session.get(WebhookDelivery, did)
                if d is None:
                    continue
                try:
                    await _deliver(session, d, client, now)
                except Exception as exc:  # noqa: BLE001 - never leave a row RUNNING because of a bug
                    await session.rollback()
                    d = await session.get(WebhookDelivery, did)
                    if d is None:
                        continue
                    d.attempts += 1
                    d.last_error = f"internal error: {type(exc).__name__}"
                    retry_at = worker.next_attempt(d.attempts, now)
                    d.status = PENDING if retry_at else FAILED
                    d.next_attempt_at = retry_at or d.next_attempt_at
                    d.locked_until = None
                if d.status == RUNNING:  # pragma: no cover
                    d.status = FAILED
                await session.commit()
                done += 1
    return done


async def next_due() -> datetime | None:
    async with get_session_factory()() as session:
        q = select(func.min(WebhookDelivery.next_attempt_at)).where(WebhookDelivery.status == PENDING)
        return (await session.execute(q)).scalar_one_or_none()


worker.register()  # the publish_event subscriber (calendar push + webhooks), once per process
