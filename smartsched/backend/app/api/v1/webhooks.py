"""Outgoing webhooks administration (docs/product/calendar-sync-api.md §4); ``setup.settings`` only."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api.deps import DB, require_permission
from app.importers import normalize as n
from app.models import User, WebhookDelivery, WebhookEndpoint
from app.models.base import utcnow
from app.schemas import messages
from app.services import audit
from app.services import webhooks as svc

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]


#: Turkish text of the URL guard's English sentences (``app.services.webhooks.validate_url``; T-R1-31)
URL_TR: dict[str, str] = {
    "URL too long": "Adres çok uzun (en çok 2048 karakter).",
    "webhook URL must start with https:// or http://": "Webhook adresi https:// ya da http:// ile başlamalı.",
    "webhook URL needs a host": "Webhook adresinde sunucu adı eksik.",
    "webhook URL must not contain user:password": "Webhook adresi kullanıcı adı ve parola içeremez.",
    "invalid port": "Adresteki kapı (port) numarası geçersiz.",
    svc.BLOCKED_MESSAGE: (
        "Bu adres bu sunucunun kendisine, yerel ağa ya da bulut meta veri adresine gidiyor; "
        "webhook yalnızca dış adreslere gönderilebilir."
    ),
}
BLOCKED_TR = URL_TR[svc.BLOCKED_MESSAGE]
EVENT_TR: dict[str, str] = {
    "unknown event type": "Bilinmeyen olay türü; listedekilerden birini ya da “*” (hepsi) seçin.",
    "choose at least one event type (or *)": "En az bir olay türü seçin (ya da “*” ile hepsini).",
}


def _url_code(exc: ValueError) -> str:
    return "webhook_url_blocked" if str(exc) == svc.BLOCKED_MESSAGE else "webhook_url_invalid"


def _clean_url(v: str) -> str:
    try:
        return svc.validate_url(v)
    except ValueError as exc:
        raise messages.coded(_url_code(exc), URL_TR.get(str(exc)), str(exc)) from exc


def _clean_events(v: list[str]) -> list[str]:
    return messages.validated(svc.validate_events, v, code="webhook_events_invalid", tr_by_text=EVENT_TR)


class WebhookIn(BaseModel):
    url: str = Field(max_length=2048)
    events: list[str] = Field(min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=255)
    active: bool = True

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _clean_url(v)

    @field_validator("events")
    @classmethod
    def _events(cls, v: list[str]) -> list[str]:
        return _clean_events(v)

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return n.clean_text(v) if v is not None else None


class WebhookPatch(BaseModel):
    url: str | None = Field(default=None, max_length=2048)
    events: list[str] | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=255)
    active: bool | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _clean_url(v) if v is not None else None

    @field_validator("events")
    @classmethod
    def _events(cls, v: list[str] | None) -> list[str] | None:
        return _clean_events(v) if v is not None else None

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return n.clean_text(v) if v is not None else None


def _snap(e: WebhookEndpoint) -> dict[str, Any]:
    return {"url": e.url, "events": list(e.events or []), "description": e.description, "active": e.active}


async def _check_target(url: str) -> None:
    """Save-time DNS check (M-41): every address the host resolves to must be allowed; 422 otherwise."""
    try:
        await svc.check_resolved(url)
    except ValueError as exc:
        host = (urlsplit(url).hostname or "").lower()
        raise messages.problem(
            422,
            "webhook_host_blocked",
            f"{host} adresi engellenen bir ağ adresine çözümleniyor. {BLOCKED_TR}",
            str(exc),
            field="url",
        ) from exc


async def _endpoint(db: DB, webhook_id: int) -> WebhookEndpoint:
    e = await db.get(WebhookEndpoint, webhook_id)
    if e is None:
        raise HTTPException(404, "webhook not found")
    return e


@router.get("/event-types")
async def event_types(_: SettingsAdmin) -> list[str]:
    return list(svc.EVENT_TYPES)


@router.get("")
async def list_webhooks(db: DB, _: SettingsAdmin) -> list[dict[str, Any]]:
    rows = (await db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.id))).scalars()
    return [svc.endpoint_out(e) for e in rows]


@router.post("", status_code=201)
async def create_webhook(body: WebhookIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    await _check_target(body.url)
    secret = svc.new_secret()
    e = WebhookEndpoint(
        url=body.url, events=body.events, description=body.description, active=body.active, created_by=admin.id
    )
    svc.set_secret(e, secret)
    db.add(e)
    await db.flush()
    await audit.record(db, "webhook.create", "webhook", e.id, after=_snap(e), actor=admin)
    await db.commit()
    return {**svc.endpoint_out(e), "secret": secret}


@router.get("/{webhook_id}")
async def get_webhook(webhook_id: int, db: DB, _: SettingsAdmin) -> dict[str, Any]:
    return svc.endpoint_out(await _endpoint(db, webhook_id))


@router.put("/{webhook_id}")
async def update_webhook(webhook_id: int, body: WebhookPatch, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    e = await _endpoint(db, webhook_id)
    before = _snap(e)
    data = body.model_dump(exclude_unset=True)
    if data.get("url") is not None:
        await _check_target(data["url"])
    for key in ("url", "events", "description"):
        if key in data and (data[key] is not None or key == "description"):
            setattr(e, key, data[key])
    if data.get("active") is not None:
        if data["active"] and not e.active:
            e.consecutive_failures, e.disabled_reason = 0, None
        e.active = bool(data["active"])
    e.updated_at = utcnow()
    await audit.record(db, "webhook.update", "webhook", e.id, before=before, after=_snap(e), actor=admin)
    await db.commit()
    return svc.endpoint_out(e)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: int, db: DB, admin: SettingsAdmin) -> Response:
    e = await _endpoint(db, webhook_id)
    await audit.record(db, "webhook.delete", "webhook", e.id, before=_snap(e), actor=admin)
    await svc.delete_endpoint(db, e)
    await db.commit()
    return Response(status_code=204)


@router.post("/{webhook_id}/secret")
async def rotate_secret(webhook_id: int, db: DB, admin: SettingsAdmin) -> dict[str, str]:
    e = await _endpoint(db, webhook_id)
    secret = svc.new_secret()
    svc.set_secret(e, secret)
    e.updated_at = utcnow()
    await audit.record(db, "webhook.secret", "webhook", e.id, after={"secret": "rotated"}, actor=admin)
    await db.commit()
    return {"secret": secret}


@router.post("/{webhook_id}/test", status_code=202)
async def test_webhook(webhook_id: int, db: DB, admin: SettingsAdmin) -> dict[str, int]:
    e = await _endpoint(db, webhook_id)
    d = await svc.ping(db, e, admin)
    await db.commit()
    return {"delivery_id": d.id}


@router.get("/{webhook_id}/deliveries")
async def deliveries(
    webhook_id: int,
    db: DB,
    _: SettingsAdmin,
    status: str | None = Query(default=None, pattern="^(PENDING|RUNNING|SENT|FAILED)$"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    await _endpoint(db, webhook_id)
    q = select(WebhookDelivery).where(WebhookDelivery.endpoint_id == webhook_id)
    if status:
        q = q.where(WebhookDelivery.status == status)
    rows = (await db.execute(q.order_by(WebhookDelivery.id.desc()).limit(limit))).scalars()
    return [svc.delivery_out(d) for d in rows]


@router.post("/deliveries/{delivery_id}/redeliver", status_code=202)
async def redeliver(delivery_id: int, db: DB, _: SettingsAdmin) -> dict[str, Any]:
    d = await db.get(WebhookDelivery, delivery_id)
    if d is None:
        raise HTTPException(404, "delivery not found")
    copy = await svc.redeliver(db, d)
    await db.commit()
    return svc.delivery_out(copy)
