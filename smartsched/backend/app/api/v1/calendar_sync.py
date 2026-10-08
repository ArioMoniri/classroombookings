"""Calendar sync API (docs/product/calendar-sync-api.md): subscription feeds with per-user secret tokens, the
Google Calendar / Microsoft 365 push connectors and the administrator's integration settings."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api.deps import DB, CurrentAccess, require_permission
from app.core import throttle
from app.importers import normalize as n
from app.models import CalendarConnection, CalendarSyncJob, User
from app.models.base import utcnow
from app.services import audit
from app.services import calendar_connectors as conn_svc
from app.services import calendar_feeds as feeds
from app.services.bookings_perms import load_access
from app.services.bookings_settings import get_group, set_group

router = APIRouter(prefix="/calendar", tags=["calendar-sync"])

SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]


# --------------------------------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------------------------------


@router.get("/sync")
async def sync_status(db: DB, access: CurrentAccess) -> dict[str, Any]:
    return {
        "enabled": await feeds.sync_enabled(db),
        "feeds": {
            "tokens": [feeds.token_out(t) for t in await feeds.list_tokens(db, access.user_id)],
            "url_templates": await feeds.url_templates(db),
        },
        "connectors": await conn_svc.connectors_out(db, access.user),
    }


# --------------------------------------------------------------------------------------------------
# Feed links
# --------------------------------------------------------------------------------------------------


class TokenIn(BaseModel):
    label: str | None = Field(default=None, max_length=200)


async def _created(db: DB, row: Any, token: str) -> dict[str, Any]:
    urls = await feeds.url_templates(db, token)
    return {**feeds.token_out(row), "token": token, "urls": urls, "subscribe": feeds.subscribe_links(urls["mine"])}


@router.post("/feeds/tokens", status_code=201)
async def create_feed_token(db: DB, access: CurrentAccess, body: TokenIn | None = None) -> dict[str, Any]:
    try:
        row, token = await feeds.create_token(db, access.user, body.label if body else None)
    except OverflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return await _created(db, row, token)


@router.post("/feeds/reset", status_code=201)
async def reset_feed_tokens(db: DB, access: CurrentAccess, body: TokenIn | None = None) -> dict[str, Any]:
    row, token = await feeds.reset_tokens(db, access.user, body.label if body else None)
    await db.commit()
    return await _created(db, row, token)


@router.delete("/feeds/tokens/{token_id}", status_code=204)
async def revoke_feed_token(token_id: int, db: DB, access: CurrentAccess) -> Response:
    if not await feeds.revoke_token(db, access.user, token_id):
        raise HTTPException(404, "calendar link not found")
    await db.commit()
    return Response(status_code=204)


@router.get("/feeds/options")
async def feed_options(db: DB, access: CurrentAccess) -> dict[str, Any]:
    return await feeds.feed_options(db, access)


# --------------------------------------------------------------------------------------------------
# The feeds (the token in the path is the credential)
# --------------------------------------------------------------------------------------------------


def _not_found() -> HTTPException:
    return HTTPException(404, "feed not found")


def _too_many(key: str, limiter: throttle.Throttle) -> HTTPException:
    return HTTPException(429, "too many calendar requests", headers={"Retry-After": str(limiter.retry_after(key) or 1)})


async def token_access_or_404(request: Request, db: DB, token: str) -> Any:
    """Rate limits, the KVKK switch and the token -> the owner's :class:`Access` (also used by ``/ics/{token}``)."""
    address = request.client.host if request.client else "?"
    if throttle.FEED_PER_ADDRESS.hit(f"ip:{address}"):
        raise _too_many(f"ip:{address}", throttle.FEED_PER_ADDRESS)
    key = feeds.hash_token(token or "")
    if throttle.FEED_PER_TOKEN.hit(key):
        raise _too_many(key, throttle.FEED_PER_TOKEN)
    if not await feeds.sync_enabled(db):
        raise _not_found()
    try:
        user = await feeds.resolve_token(db, token)
    except feeds.FeedNotFound as exc:
        raise _not_found() from exc
    return await load_access(db, user)


def ics_response(request: Request, feed: feeds.Feed) -> Response:
    headers = {
        "ETag": feed.etag,
        "Cache-Control": "private, max-age=300",
        "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow",
    }
    if feeds.etag_matches(request.headers.get("if-none-match"), feed.etag):
        return Response(status_code=304, headers=headers)
    headers["Content-Disposition"] = f'inline; filename="{feed.filename}"'
    return Response(feed.text.encode("utf-8"), media_type="text/calendar; charset=utf-8", headers=headers)


async def serve_feed(request: Request, db: DB, token: str, kind: str, scope_id: int | None) -> Response:
    access = await token_access_or_404(request, db, token)
    scope = feeds.FeedScope(kind, scope_id if scope_id is not None else access.user_id)
    try:
        feed = await feeds.build_feed(db, access, scope)
    except feeds.FeedNotFound as exc:
        raise _not_found() from exc
    return ics_response(request, feed)


@router.get("/feeds/{token}/mine.ics")
async def feed_mine(token: str, request: Request, db: DB) -> Response:
    return await serve_feed(request, db, token, "mine", None)


@router.get("/feeds/{token}/room/{room_id}.ics")
async def feed_room(token: str, room_id: int, request: Request, db: DB) -> Response:
    return await serve_feed(request, db, token, "room", room_id)


@router.get("/feeds/{token}/department/{department_id}.ics")
async def feed_department(token: str, department_id: int, request: Request, db: DB) -> Response:
    return await serve_feed(request, db, token, "department", department_id)


@router.get("/feeds/{token}/room-group/{group_id}.ics")
async def feed_room_group(token: str, group_id: int, request: Request, db: DB) -> Response:
    return await serve_feed(request, db, token, "room_group", group_id)


# --------------------------------------------------------------------------------------------------
# Push connectors
# --------------------------------------------------------------------------------------------------


def _provider(provider: str) -> conn_svc.Provider:
    p = conn_svc.PROVIDERS.get(provider)
    if p is None:
        raise HTTPException(404, "unknown calendar provider")
    return p


class ConnectIn(BaseModel):
    return_path: str | None = Field(default=None, max_length=255)

    @field_validator("return_path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        v = n.clean_text(v) if v is not None else None
        if v is None:
            return None
        if not v.startswith("/") or v.startswith("//") or "\\" in v or "://" in v:
            raise ValueError("return_path must be a path on the panel, e.g. /profile/calendar")
        return v


@router.get("/connectors")
async def list_connectors(db: DB, access: CurrentAccess) -> list[dict[str, Any]]:
    return await conn_svc.connectors_out(db, access.user)


@router.post("/connectors/{provider}/connect")
async def connect(provider: str, db: DB, access: CurrentAccess, body: ConnectIn | None = None) -> dict[str, str]:
    p = _provider(provider)
    if not await feeds.sync_enabled(db):
        raise HTTPException(403, "calendar sync is turned off")
    try:
        url = await conn_svc.start_authorization(db, access.user, p, body.return_path if body else None)
    except conn_svc.NotConfigured as exc:
        raise HTTPException(409, f"{p.label} is not configured by the administrator") from exc
    await db.commit()
    return {"authorize_url": url}


@router.get("/connectors/{provider}/callback")
async def oauth_callback(
    provider: str,
    db: DB,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """The provider redirects the browser here (no JWT): the hashed ``state`` identifies the user."""
    p = _provider(provider)
    location = await conn_svc.finish_authorization(db, p, code=code, state=state, error=error)
    return RedirectResponse(location, status_code=302)


async def _connection(db: DB, user: User, provider: str) -> CalendarConnection:
    _provider(provider)
    row = await conn_svc.get_connection(db, user.id, provider)
    if row is None:
        raise HTTPException(404, "not connected")
    return row


@router.get("/connectors/{provider}/calendars")
async def list_calendars(provider: str, db: DB, access: CurrentAccess) -> list[dict[str, Any]]:
    row = await _connection(db, access.user, provider)
    try:
        out = await conn_svc.list_calendars(db, row)
    except conn_svc.ProviderError as exc:
        await db.commit()
        raise HTTPException(502, f"{_provider(provider).label}: {exc.public}") from exc
    await db.commit()
    return out


class CalendarChoice(BaseModel):
    calendar_id: str = Field(min_length=1, max_length=1024)
    calendar_name: str | None = Field(default=None, max_length=255)


@router.put("/connectors/{provider}")
async def choose_calendar(provider: str, body: CalendarChoice, db: DB, access: CurrentAccess) -> dict[str, Any]:
    row = await _connection(db, access.user, provider)
    await conn_svc.choose_calendar(db, row, body.calendar_id.strip(), n.clean_text(body.calendar_name))
    await db.commit()
    conn_svc.schedule_drain()
    return next(c for c in await conn_svc.connectors_out(db, access.user) if c["provider"] == provider)


@router.post("/connectors/{provider}/resync", status_code=202)
async def resync(provider: str, db: DB, access: CurrentAccess) -> dict[str, int]:
    row = await _connection(db, access.user, provider)
    if not await feeds.sync_enabled(db):
        raise HTTPException(403, "calendar sync is turned off")
    queued = await conn_svc.queue_full_sync(db, row)
    await db.commit()
    conn_svc.schedule_drain()
    return {"queued": queued}


@router.delete("/connectors/{provider}", status_code=204)
async def disconnect(provider: str, db: DB, access: CurrentAccess) -> Response:
    row = await _connection(db, access.user, provider)
    await conn_svc.disconnect(db, row)
    await db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------------------------------
# Administrator settings
# --------------------------------------------------------------------------------------------------

_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,63}$")


def _clean(v: str | None) -> str | None:
    """Trim spaces / NBSP pasted around ids and secrets (Turkish keyboards and copied console text)."""
    if v is None:
        return None
    return n.clean_text(v) or ""


class IntegrationSettingsIn(BaseModel):
    calendar_sync_enabled: bool | None = None
    webhooks_enabled: bool | None = None
    public_url: str | None = Field(default=None, max_length=255)
    feed_past_days: int | None = Field(default=None, ge=0, le=730)
    feed_cancelled_grace_days: int | None = Field(default=None, ge=0, le=90)
    google_client_id: str | None = Field(default=None, max_length=255)
    google_client_secret: str | None = Field(default=None, max_length=512)
    microsoft_client_id: str | None = Field(default=None, max_length=255)
    microsoft_client_secret: str | None = Field(default=None, max_length=512)
    microsoft_tenant: str | None = Field(default=None, max_length=64)

    @field_validator("google_client_id", "microsoft_client_id", "google_client_secret", "microsoft_client_secret")
    @classmethod
    def _trim(cls, v: str | None) -> str | None:
        return _clean(v)

    @field_validator("public_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return None if v is None else feeds.clean_public_url(v)

    @field_validator("microsoft_tenant")
    @classmethod
    def _tenant(cls, v: str | None) -> str | None:
        v = _clean(v)
        if v in (None, ""):
            return v
        if not _TENANT.match(v):
            raise ValueError("tenant: organizations, common, a tenant id (GUID) or a domain")
        return v


async def settings_out(db: DB) -> dict[str, Any]:
    g = await get_group(db, "integrations")
    base, source = await feeds.public_base(db)
    out: dict[str, Any] = {
        "calendar_sync_enabled": g["calendar_sync_enabled"],
        "calendar_sync_signoff": g["calendar_sync_signoff"],
        "webhooks_enabled": g["webhooks_enabled"],
        "public_url": base,
        "public_url_source": source,
        "feed_past_days": g["feed_past_days"],
        "feed_cancelled_grace_days": g["feed_cancelled_grace_days"],
    }
    for p in conn_svc.PROVIDERS.values():
        cfg = await conn_svc.client_config(db, p)
        item: dict[str, Any] = {
            "client_id": g[f"{p.name}_client_id"] or "",
            "client_secret": g[f"{p.name}_client_secret"],
            "configured": cfg is not None,
            "redirect_uri": conn_svc.redirect_uri(base, p),
        }
        if p.name == "microsoft":
            item["tenant"] = g["microsoft_tenant"] or "organizations"
        out[p.name] = item
    return out


@router.get("/admin/settings")
async def get_integration_settings(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    return await settings_out(db)


@router.put("/admin/settings")
async def put_integration_settings(body: IntegrationSettingsIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    data = {k: v for k, v in data.items() if v is not None or k == "public_url"}
    if "public_url" in data and data["public_url"] is None:
        data["public_url"] = ""
    before = await get_group(db, "integrations")
    if "calendar_sync_enabled" in data and bool(data["calendar_sync_enabled"]) != bool(before["calendar_sync_enabled"]):
        enabled = bool(data["calendar_sync_enabled"])
        data["calendar_sync_signoff"] = {
            "enabled": enabled,
            "by": audit.user_label(admin),
            "by_user_id": admin.id,
            "at": utcnow().isoformat(timespec="seconds") + "Z",
            "features": ["calendar_sync"],
            "legal_basis": "KVKK Art. 9 as amended by Law 7499 (cross-border transfer)",
        }
        await audit.record(
            db,
            "integrations.calendar_sync",
            "setting",
            "integrations.calendar_sync_enabled",
            before={"enabled": bool(before["calendar_sync_enabled"])},
            after={"enabled": enabled},
            actor=admin,
        )
    await set_group(db, "integrations", data)
    await db.commit()
    if data.get("calendar_sync_enabled") is True:
        conn_svc.schedule_drain()
    return await settings_out(db)


@router.get("/admin/jobs")
async def sync_jobs(
    db: DB,
    _: SettingsAdmin,
    status: str | None = Query(default=None, pattern="^(PENDING|RUNNING|DONE|FAILED|SKIPPED)$"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    q = (
        select(CalendarSyncJob, CalendarConnection)
        .join(CalendarConnection, CalendarConnection.id == CalendarSyncJob.connection_id)
        .order_by(CalendarSyncJob.id.desc())
        .limit(limit)
    )
    if status:
        q = q.where(CalendarSyncJob.status == status)
    return [
        {
            "id": j.id,
            "provider": c.provider,
            "user_id": c.user_id,
            "booking_id": j.booking_id,
            "kind": j.kind,
            "status": j.status,
            "attempts": j.attempts,
            "next_attempt_at": j.next_attempt_at.isoformat() if j.next_attempt_at else None,
            "last_error": j.last_error,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "done_at": j.done_at.isoformat() if j.done_at else None,
        }
        for j, c in (await db.execute(q)).all()
    ]
