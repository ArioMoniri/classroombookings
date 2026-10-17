"""Calendar sync API (docs/product/calendar-sync-api.md): subscription feeds with per-user secret tokens, the
Google Calendar / Microsoft 365 push connectors and the administrator's integration settings."""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.api.deps import DB, CurrentAccess, require_permission
from app.core import throttle
from app.importers import normalize as n
from app.models import AuditEvent, CalendarConnection, CalendarSyncJob, User
from app.models.base import utcnow
from app.services import audit, kvkk
from app.services import calendar_classes as cc
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
        # consent gates: with sync on, links and connections need the person's calendar_sync consent
        "consent": await feeds.consent_state(db, access.user),
    }


def consent_refused(exc: kvkk.KvkkError) -> HTTPException:
    """409 ``consent_required``: ``detail = {code, message, message_en, message_tr, purpose, label_tr, label_en,
    grant_path, grant_api}`` (``app.services.kvkk.require_consent``)."""
    return HTTPException(exc.status, exc.as_detail())


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
    except kvkk.KvkkError as exc:
        raise consent_refused(exc) from exc
    await db.commit()
    return await _created(db, row, token)


@router.post("/feeds/reset", status_code=201)
async def reset_feed_tokens(db: DB, access: CurrentAccess, body: TokenIn | None = None) -> dict[str, Any]:
    try:
        row, token = await feeds.reset_tokens(db, access.user, body.label if body else None)
    except kvkk.KvkkError as exc:
        raise consent_refused(exc) from exc
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


def _http_date(at: datetime) -> str:
    return format_datetime(at.replace(tzinfo=UTC), usegmt=True)


def _not_modified_since(header: str | None, last_modified: datetime | None) -> bool:
    if not header or last_modified is None:
        return False
    try:
        since = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return False
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return last_modified.replace(tzinfo=UTC, microsecond=0) <= since


def ics_response(request: Request, feed: feeds.Feed, *, attachment: bool = False) -> Response:
    headers = {
        "ETag": feed.etag,
        "Cache-Control": "private, no-store" if attachment else "private, max-age=300",
        "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow",
    }
    if feed.last_modified is not None:
        headers["Last-Modified"] = _http_date(feed.last_modified)
    if not attachment:
        inm = request.headers.get("if-none-match")
        if feeds.etag_matches(inm, feed.etag) or (
            inm is None and _not_modified_since(request.headers.get("if-modified-since"), feed.last_modified)
        ):
            return Response(status_code=304, headers=headers)
    disposition = "attachment" if attachment else "inline"
    headers["Content-Disposition"] = f'{disposition}; filename="{feed.filename}"'
    return Response(feed.text.encode("utf-8"), media_type="text/calendar; charset=utf-8", headers=headers)


#: CAL-05: token hash -> (version key, Last-Modified of the last full build), to answer If-Modified-Since cheaply
_LAST_BUILDS: OrderedDict[str, tuple[str, datetime | None]] = OrderedDict()
_LAST_BUILDS_MAX = 4096


async def serve_feed(request: Request, db: DB, token: str, kind: str, scope_id: int | None) -> Response:
    """Rate limits, the KVKK switch, the token bound to its scope (CAL-03: any other path is a 404), then the CAL-05
    conditional GET: a version key (the link, the scope, the newest audit event -- every booking, run, move,
    setting, role and term change writes one -- and the day) is compared before anything is built, so an unchanged
    feed costs three queries; the full build follows otherwise."""
    address = request.client.host if request.client else "?"
    if throttle.FEED_PER_ADDRESS.hit(f"ip:{address}"):
        raise _too_many(f"ip:{address}", throttle.FEED_PER_ADDRESS)
    key = feeds.hash_token(token or "")
    if throttle.FEED_PER_TOKEN.hit(key):
        raise _too_many(key, throttle.FEED_PER_TOKEN)
    switches = await feeds.feed_switches(db)
    if not switches["enabled"]:
        raise _not_found()
    try:
        row, user = await feeds.resolve_token_row(db, token)
    except feeds.FeedNotFound as exc:
        raise _not_found() from exc
    if not feeds.token_serves(row, kind, scope_id) or not switches.get(row.scope_kind or "", True):
        raise _not_found()  # another scope's path, or a scope the administrator switched off
    newest = (await db.execute(select(func.max(AuditEvent.id)))).scalar_one_or_none()
    day = datetime.now(UTC).astimezone(ZoneInfo("Europe/Istanbul")).date()
    version = hashlib.sha256(f"v1|{row.id}|{kind}|{scope_id}|{newest}|{day}".encode()).hexdigest()
    etag = '"' + version[:32] + '"'
    cached = _LAST_BUILDS.get(key)
    inm = request.headers.get("if-none-match")
    if feeds.etag_matches(inm, etag) or (
        inm is None
        and cached is not None
        and cached[0] == version
        and _not_modified_since(request.headers.get("if-modified-since"), cached[1])
    ):
        headers = {"ETag": etag, "Cache-Control": "private, max-age=300", "Referrer-Policy": "no-referrer"}
        if cached is not None and cached[0] == version and cached[1] is not None:
            headers["Last-Modified"] = _http_date(cached[1])
        return Response(status_code=304, headers=headers)
    access = await load_access(db, user)
    target = scope_id if scope_id is not None else access.user_id
    scope = feeds.FeedScope(kind, target)
    base, _ = await feeds.public_base(db)
    path = feeds.scoped_path(row)
    source = f"{base}/api/v1/calendar/feeds/{token}/{path}" if base and path else None
    try:
        feed = await feeds.build_feed(db, access, scope, source=source)
    except feeds.FeedNotFound as exc:
        raise _not_found() from exc
    feed.version = version
    _LAST_BUILDS[key] = (version, feed.last_modified)
    _LAST_BUILDS.move_to_end(key)
    while len(_LAST_BUILDS) > _LAST_BUILDS_MAX:
        _LAST_BUILDS.popitem(last=False)
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


@router.get("/feeds/{token}/classes.ics")
async def feed_my_classes(token: str, request: Request, db: DB) -> Response:
    """CAL-02 "Derslerim": the published classes of the instructor record(s) linked to the link's owner."""
    return await serve_feed(request, db, token, "my_classes", None)


@router.get("/feeds/{token}/department-classes/{department_id}.ics")
async def feed_department_classes(token: str, department_id: int, request: Request, db: DB) -> Response:
    """CAL-03 "Bölümümün dersleri": a department's published classes (the department rule on every poll)."""
    return await serve_feed(request, db, token, "department_classes", department_id)


# --------------------------------------------------------------------------------------------------
# CAL-03 subscriptions (scope-bound links) and the export options
# --------------------------------------------------------------------------------------------------

ScopeKind = Literal["my_classes", "department_classes", "my_bookings", "room", "room_group"]


class SubscriptionIn(BaseModel):
    scope_kind: ScopeKind
    scope_id: int | None = Field(default=None, ge=1)
    label: str | None = Field(default=None, max_length=200)


def scope_refused(exc: cc.ScopeError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


async def _deny(db: DB, user_id: int, kind: str, scope_id: int | None, exc: cc.ScopeError) -> HTTPException:
    """``calendar.scope_denied`` for a refused department (403) is audited, then the refusal is returned."""
    if exc.code == "department_not_allowed":
        # a rotate rolled back first: reload the (expired) actor before it is written into the audit row
        user = await db.get(User, user_id, populate_existing=True)
        await audit.record(
            db,
            "calendar.scope_denied",
            "calendar_subscription",
            None,
            after={"scope_kind": kind, "scope_id": scope_id, "code": exc.code},
            actor=user,
        )
        await db.commit()
    return scope_refused(exc)


async def _links_out(db: DB, row: Any, token: str) -> dict[str, Any]:
    base, _ = await feeds.public_base(db)
    path = feeds.scoped_path(row) or "mine.ics"
    url = f"{base}/api/v1/calendar/feeds/{token}/{path}"
    label_tr, _ = await feeds.scope_label(db, row.scope_kind, row.scope_id)
    links = feeds.subscribe_links(url, f"SmartSched – {label_tr}")
    owner = await db.get(User, row.user_id)
    assert owner is not None
    access = await load_access(db, owner)
    return {
        **await feeds.subscription_out(db, row),
        "token": token,
        "url": url,
        "urls": {"https": url, **links},
        "preview": await feeds.preview(db, access, row.scope_kind or "my_bookings", row.scope_id),
        "note_tr": "Bağlantıyı açmayın, abone olun; açarsanız güncellenmeyen bir kopya oluşur.",
        "note_en": "Subscribe to the link rather than opening it; opening it makes a copy that never updates.",
    }


@router.post("/subscriptions", status_code=201)
async def create_subscription(body: SubscriptionIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """Tap 3 "Onayla ve ekle" for a link: a token bound to one scope, shown once (CAL-03)."""
    try:
        row, token = await feeds.create_subscription(db, access, body.scope_kind, body.scope_id, body.label)
    except cc.ScopeError as exc:  # refused before anything was written
        raise await _deny(db, access.user_id, body.scope_kind, body.scope_id, exc) from exc
    except kvkk.KvkkError as exc:
        raise consent_refused(exc) from exc
    except OverflowError as exc:
        raise HTTPException(
            409,
            {
                "code": "too_many_links",
                "message": str(exc),
                "message_en": f"At most {feeds.MAX_TOKENS_PER_USER} calendar links; remove one first.",
                "message_tr": f"En çok {feeds.MAX_TOKENS_PER_USER} takvim bağlantınız olabilir; önce birini kaldırın.",
            },
        ) from exc
    await audit.record(
        db,
        "calendar.subscription_create",
        "calendar_subscription",
        row.id,
        after={
            "scope_kind": row.scope_kind,
            "scope_id": row.scope_id,
            "channel": "link",
            "consent_id": row.consent_id,
            "fields": row.fields,
            "hint": row.hint,
        },
        actor=access.user,
    )
    await db.commit()
    return await _links_out(db, row, token)


async def _own_subscription(db: DB, user: User, sub_id: int) -> Any:
    from app.models import CalendarFeedToken

    row = await db.get(CalendarFeedToken, sub_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(
            404, {"code": "not_found", "message_en": "calendar link not found", "message_tr": "Takvim bağlantısı yok"}
        )
    return row


@router.get("/subscriptions")
async def list_subscriptions(db: DB, access: CurrentAccess) -> dict[str, Any]:
    """The person's links (scope, "en son çekti") and push connections (scopes, "Son eşitleme")."""
    links = [await feeds.subscription_out(db, t) for t in await feeds.list_tokens(db, access.user_id)]
    return {"links": links, "push": await conn_svc.push_out(db, access.user)}


@router.delete("/subscriptions/{sub_id}", status_code=204)
async def revoke_subscription(sub_id: int, db: DB, access: CurrentAccess) -> Response:
    row = await _own_subscription(db, access.user, sub_id)
    before = {"scope_kind": row.scope_kind, "scope_id": row.scope_id, "hint": row.hint}
    await db.delete(row)
    await audit.record(
        db, "calendar.subscription_revoke", "calendar_subscription", sub_id, before=before, actor=access.user
    )
    await db.commit()
    return Response(status_code=204)


@router.post("/subscriptions/{sub_id}/rotate", status_code=201)
async def rotate_subscription(sub_id: int, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """ "Bağlantıyı yenile": a new link for the same scope; the old one stops at once."""
    row = await _own_subscription(db, access.user, sub_id)
    kind, scope_id, uid = row.scope_kind, row.scope_id, access.user_id
    try:
        new, token = await feeds.rotate_subscription(db, access, row)
    except cc.ScopeError as exc:
        await db.rollback()  # the old link stays
        raise await _deny(db, uid, kind or "", scope_id, exc) from exc
    except kvkk.KvkkError as exc:
        raise consent_refused(exc) from exc
    await audit.record(
        db,
        "calendar.subscription_rotate",
        "calendar_subscription",
        new.id,
        before={"id": sub_id},
        after={"id": new.id, "scope_kind": kind, "scope_id": scope_id, "hint": new.hint},
        actor=access.user,
    )
    await db.commit()
    return await _links_out(db, new, token)


@router.get("/export/options")
async def export_options(db: DB, access: CurrentAccess) -> dict[str, Any]:
    """Tap 1 / 2 of "Takvimime ekle": what the person may export, how, and a preview per scope."""
    return await feeds.export_options(db, access)


# --------------------------------------------------------------------------------------------------
# CAL-04 one-off .ics files (same engine and UIDs as the links)
# --------------------------------------------------------------------------------------------------


async def _term_slug(db: DB) -> str:
    runs = await cc.course_runs(db)
    if not runs:
        return "takvim"
    from app.models import Term

    term = await db.get(Term, runs[-1].term_id)
    return cc.ascii_slug(term.code if term is not None else None)


async def _file(request: Request, db: DB, access: Any, kind: str, scope_id: int | None, filename: str) -> Response:
    try:
        await feeds.check_scope(db, access, kind, scope_id)
    except cc.ScopeError as exc:
        raise await _deny(db, access.user_id, kind, scope_id, exc) from exc
    feed_kind = feeds.SCOPE_FEED_KIND[kind]
    target = scope_id if scope_id is not None else access.user_id
    try:
        feed = await feeds.build_feed(db, access, feeds.FeedScope(feed_kind, target), attachment=True)
    except feeds.FeedNotFound as exc:
        raise _not_found() from exc
    feed.filename = filename
    return ics_response(request, feed, attachment=True)


@router.get("/export/classes.ics")
async def export_my_classes(request: Request, db: DB, access: CurrentAccess) -> Response:
    return await _file(request, db, access, "my_classes", None, f"derslerim-{await _term_slug(db)}.ics")


@router.get("/export/department/{department_id}.ics")
async def export_department(department_id: int, request: Request, db: DB, access: CurrentAccess) -> Response:
    from app.models import Program

    dep = await db.get(Program, department_id)
    slug = cc.ascii_slug(dep.name if dep is not None else str(department_id))
    name = f"bolum-{slug}-{await _term_slug(db)}.ics"
    return await _file(request, db, access, "department_classes", department_id, name)


@router.get("/export/bookings.ics")
async def export_my_bookings(request: Request, db: DB, access: CurrentAccess) -> Response:
    return await _file(request, db, access, "my_bookings", None, "rezervasyonlarim.ics")


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
    #: CAL-06: what to push (``my_classes``, ``my_bookings``, ``department_classes:<id>``); given = a new connection
    #: into a calendar SmartSched creates, asked with the least scopes; omitted = the legacy bookings-only connect
    scopes: list[str] | None = Field(default=None, max_length=12)

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
    scopes = await _checked_scopes(db, access, body.scopes) if body and body.scopes is not None else None
    try:
        url = await conn_svc.start_authorization(db, access.user, p, body.return_path if body else None, scopes)
    except conn_svc.NotConfigured as exc:
        raise HTTPException(409, f"{p.label} is not configured by the administrator") from exc
    except kvkk.KvkkError as exc:
        raise consent_refused(exc) from exc
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
    before = {"provider": row.provider, "export_scopes": list(row.export_scopes or ["my_bookings"])}
    conn_id = row.id
    out = await conn_svc.disconnect(db, row)
    await audit.record(
        db,
        "calendar.push_disconnect",
        "calendar_connection",
        conn_id,
        before=before,
        after={"revoke": out["revoke"], "calendar_deleted": out.get("calendar_deleted")},
        actor=access.user,
    )
    await db.commit()
    return Response(status_code=204)


async def _checked_scopes(db: DB, access: Any, raw: list[str]) -> list[str]:
    """Push scopes after the switch / link / department checks (each refusal as the subscription API gives it)."""
    try:
        parsed = conn_svc.check_export_scopes(raw)
    except ValueError as exc:
        raise HTTPException(
            422,
            {
                "code": "unknown_scope",
                "message": str(exc),
                "message_en": str(exc),
                "message_tr": "Bilinmeyen takvim kapsamı",
            },  # fmt: skip
        ) from exc
    for kind, scope_id in parsed:
        try:
            await feeds.check_scope(db, access, kind, scope_id)
        except cc.ScopeError as exc:
            raise await _deny(db, access.user_id, kind, scope_id, exc) from exc
    return conn_svc.scope_strings(parsed)


class ScopesIn(BaseModel):
    scopes: list[str] = Field(max_length=12)


@router.put("/connectors/{provider}/scopes")
async def put_push_scopes(provider: str, body: ScopesIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    """Tap 3 for push on an existing connection: replace what is pushed and reconcile. An empty list disconnects
    (the owned calendar is deleted, the grant revoked). A legacy connection (into a calendar SmartSched did not
    create) cannot take classes: 409 ``reconnect_required`` ("Daha az izinle yeniden bağlan")."""
    row = await _connection(db, access.user, provider)
    if not await feeds.sync_enabled(db):
        raise HTTPException(403, {"code": "calendar_sync_off", "message_en": "Calendar sync is turned off.",
                                  "message_tr": "Takvim eşitleme kurumunuz tarafından kapalı."})  # fmt: skip
    try:
        await feeds.require_sync_consent(db, access.user)
    except kvkk.KvkkError as exc:
        raise consent_refused(exc) from exc
    if not body.scopes:
        await disconnect(provider, db, access)
        return {"provider": provider, "connected": False, "export_scopes": []}
    scopes = await _checked_scopes(db, access, body.scopes)
    if not row.owned_calendar and conn_svc.class_scopes(scopes):
        raise HTTPException(
            409,
            {
                "code": "reconnect_required",
                "message_en": "Reconnect with fewer permissions to add your classes: SmartSched then creates its own "
                "calendar.",
                "message_tr": "Derslerinizi eklemek için daha az izinle yeniden bağlanın; SmartSched kendi takvimini "
                "oluşturur.",
            },
        )
    before = await conn_svc.set_export_scopes(db, row, scopes)
    await audit.record(
        db,
        "calendar.push_scopes",
        "calendar_connection",
        row.id,
        before={"export_scopes": before},
        after={"export_scopes": scopes, "consent_id": await feeds.active_consent_id(db, access.user_id)},
        actor=access.user,
    )
    await db.commit()
    conn_svc.schedule_drain()
    return next(x for x in await conn_svc.push_out(db, access.user) if x["provider"] == provider)


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


class ExportSettingsIn(BaseModel):
    """CAL-09 admin panel (Ayarlar › Takvim): scopes, event fields, push verification and the client source."""

    export_my_classes: bool | None = None
    export_department_classes: bool | None = None
    export_my_bookings: bool | None = None
    export_field_course_title: bool | None = None
    export_field_department: bool | None = None
    export_field_co_instructors: bool | None = None
    export_field_link: bool | None = None
    push_verified_only: bool | None = None
    push_allowed_domains: list[str] | None = Field(default=None, max_length=50)
    calendar_client_source: Literal["own", "identity"] | None = None

    @field_validator("push_allowed_domains")
    @classmethod
    def _domains(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = conn_svc.clean_domains(v)
        bad = [d for d in cleaned if d in conn_svc.CONSUMER_DOMAINS]
        if bad:
            raise ValueError(f"personal mailbox domains cannot be trusted: {', '.join(bad)}")
        return cleaned


EXPORT_KEYS = tuple(ExportSettingsIn.model_fields)


async def export_settings_out(db: DB) -> dict[str, Any]:
    from app.models import CalendarFeedToken
    from app.models.sso import SsoProvider

    g = await get_group(db, "integrations")
    links = dict(
        (
            await db.execute(
                select(CalendarFeedToken.scope_kind, func.count(CalendarFeedToken.id)).group_by(
                    CalendarFeedToken.scope_kind
                )
            )
        ).all()
    )
    conns = list((await db.execute(select(CalendarConnection))).scalars())
    by_scope: dict[str, int] = {}
    for c in conns:
        for sc in c.export_scopes or ["my_bookings"]:
            key = str(sc).split(":", 1)[0]
            by_scope[key] = by_scope.get(key, 0) + 1
    failed = (
        await db.execute(select(func.count(CalendarSyncJob.id)).where(CalendarSyncJob.status == "FAILED"))
    ).scalar_one()
    idps = {
        str(kind)
        for kind, cid in (
            await db.execute(select(SsoProvider.kind, SsoProvider.client_id).where(SsoProvider.enabled.is_(True)))
        )  # fmt: skip
        if cid
    }
    return {
        **{k: g.get(k) for k in EXPORT_KEYS},
        "push_allowed_domains": conn_svc.clean_domains(g.get("push_allowed_domains")),
        "fields_always": ["course_code", "section", "room", "time"],
        "identity_clients": {name: kind in idps for name, kind in conn_svc.IDP_KIND.items()},
        "status": {
            "links": {("legacy" if k is None else str(k)): int(v) for k, v in links.items()},
            "connections": {
                p: sum(1 for c in conns if c.provider == p and c.status == "ACTIVE") for p in conn_svc.PROVIDERS
            },
            "connections_by_scope": by_scope,
            "needs_attention": sum(1 for c in conns if c.status != "ACTIVE"),
            "least_privilege_flagged": sum(1 for c in conns if not conn_svc.least_privilege(c)),
            "failed_jobs": int(failed),
            "nightly_reconcile": g.get("nightly_reconcile_at"),
        },
    }


@router.get("/admin/export-settings")
async def get_export_settings(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    return await export_settings_out(db)


@router.put("/admin/export-settings")
async def put_export_settings(body: ExportSettingsIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    before = await get_group(db, "integrations")
    changed = {k: v for k, v in data.items() if before.get(k) != v}
    if changed:
        await set_group(db, "integrations", changed)
        await audit.record(
            db,
            "integrations.calendar_export",
            "setting",
            "integrations.calendar_export",
            before={k: before.get(k) for k in changed},
            after=changed,
            actor=admin,
        )
        await db.commit()
        if any(k.startswith("export_") for k in changed):
            await conn_svc.queue_classes(db)  # new fields or scopes: the pushed events follow
            await db.commit()
    return await export_settings_out(db)


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
