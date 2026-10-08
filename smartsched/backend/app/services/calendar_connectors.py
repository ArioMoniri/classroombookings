"""Native push connectors: Google Calendar API and Microsoft Graph (docs/product/calendar-sync-api.md §3).

Off until an administrator stores the university's own OAuth client (``integrations.{google,microsoft}_client_id``
and ``…_client_secret``, encrypted like the AI key) and the public URL is known: no client id ships with the
product, and an unconfigured provider reports ``configured: false``.

* Connect: authorization code flow with PKCE (S256) and a single-use ``state`` (stored hashed, 10 minutes, the
  code verifier encrypted). The callback stores the access / refresh tokens encrypted (Fernet, APP_SECRET) and
  redirects the browser to the panel.
* Push: every booking mutation (``app.services.events.publish_event`` subscriber) queues a ``calendar_sync_jobs``
  row per affected connection; the integrations worker reconciles the external calendar with the booking's
  current state (create / update / delete) and stores the external event id in ``calendar_event_links``. Jobs are
  idempotent (state-based, not replayed), deduplicated while pending, retried with backoff.
* Disconnect deletes the stored tokens at once (T6 acceptance) and revokes the Google grant in the background.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.security import decrypt_secret, encrypt_secret
from app.models import (
    Booking,
    CalendarConnection,
    CalendarEventLink,
    CalendarSyncJob,
    OAuthState,
    User,
)
from app.models.base import utcnow
from app.models.booking import BOOKED
from app.models.integrations import DONE, FAILED, PENDING, RUNNING, SKIPPED
from app.services import bookings as booking_svc
from app.services import calendar_feeds as feeds
from app.services import settings_service
from app.services.bookings_settings import get_group
from app.workers import integrations as worker

STATE_TTL = timedelta(minutes=10)
#: bookings pushed by a full sync: from this many days ago onwards
PUSH_PAST_DAYS = 7
HTTP_TIMEOUT_S = 15.0


class NotConfigured(Exception):
    pass


class ProviderError(Exception):
    """``public``: short, safe to show. ``retryable``: network / 429 / 5xx. ``reauth``: the grant is gone."""

    def __init__(self, public: str, *, status: int | None = None, retryable: bool = False, reauth: bool = False):
        super().__init__(public)
        self.public = public[:300]
        self.status = status
        self.retryable = retryable
        self.reauth = reauth


@dataclass(frozen=True)
class ClientConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    tenant: str = "organizations"


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str | None


def http_client() -> httpx.AsyncClient:
    """Outbound client for provider APIs (tests replace this function with one on an ``httpx.MockTransport``)."""
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, follow_redirects=False)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]  # RFC 7636: 43..128 unreserved characters
    return verifier, _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _classify(resp: httpx.Response, what: str) -> ProviderError:
    status = resp.status_code
    try:
        body: Any = resp.json()
    except ValueError:
        body = {}
    detail = ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            detail = str(err.get("message") or err.get("code") or "")
        elif err:
            detail = str(body.get("error_description") or err)
    text = f"{what}: HTTP {status}" + (f" ({detail[:160]})" if detail else "")
    rate_limited = "ratelimit" in detail.replace(" ", "").lower()
    if status == 400 and isinstance(body, dict) and body.get("error") == "invalid_grant":
        return ProviderError(text, status=status, reauth=True)
    return ProviderError(text, status=status, retryable=status in (408, 429) or status >= 500 or rate_limited)


# --------------------------------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------------------------------


class Provider:
    name = ""
    label = ""
    scopes: tuple[str, ...] = ()
    default_calendar: str | None = None

    def authorize_endpoint(self, cfg: ClientConfig) -> str:
        raise NotImplementedError

    def token_endpoint(self, cfg: ClientConfig) -> str:
        raise NotImplementedError

    def authorize_url(self, cfg: ClientConfig, state: str, challenge: str) -> str:
        params = {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            **self.extra_authorize_params(),
        }
        return f"{self.authorize_endpoint(cfg)}?{urlencode(params, quote_via=quote)}"

    def extra_authorize_params(self) -> dict[str, str]:
        return {}

    def _token_form(self, cfg: ClientConfig) -> dict[str, str]:
        return {"client_id": cfg.client_id, "client_secret": cfg.client_secret}

    async def _token(self, client: httpx.AsyncClient, cfg: ClientConfig, form: dict[str, str]) -> TokenSet:
        try:
            resp = await client.post(self.token_endpoint(cfg), data=form, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise ProviderError(f"token endpoint unreachable ({type(exc).__name__})", retryable=True) from exc
        if resp.status_code != 200:
            raise _classify(resp, "token")
        data = resp.json()
        return TokenSet(
            access_token=str(data["access_token"]),
            refresh_token=data.get("refresh_token"),
            expires_in=int(data.get("expires_in") or 3600),
            scope=data.get("scope"),
        )

    async def exchange(self, client: httpx.AsyncClient, cfg: ClientConfig, code: str, verifier: str) -> TokenSet:
        form = {
            **self._token_form(cfg),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.redirect_uri,
            "code_verifier": verifier,
        }
        return await self._token(client, cfg, form)

    async def refresh(self, client: httpx.AsyncClient, cfg: ClientConfig, refresh_token: str) -> TokenSet:
        form = {**self._token_form(cfg), "grant_type": "refresh_token", "refresh_token": refresh_token}
        return await self._token(client, cfg, form)

    async def account(self, api: Api) -> tuple[str | None, str | None]:
        raise NotImplementedError

    async def calendars(self, api: Api) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def upsert(
        self, api: Api, calendar_id: str | None, external_id: str | None, view: feeds.EventView, ctx: PushContext
    ) -> str:
        raise NotImplementedError

    async def delete(self, api: Api, calendar_id: str | None, external_id: str) -> None:
        raise NotImplementedError

    async def revoke(self, client: httpx.AsyncClient, token: str) -> None:
        return None


@dataclass(frozen=True)
class PushContext:
    connection_id: int
    job_id: int
    tz_name: str


class GoogleProvider(Provider):
    name = "google"
    label = "Google Calendar"
    scopes = (
        "openid",
        "email",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    )
    default_calendar = "primary"
    API = "https://www.googleapis.com/calendar/v3"

    def authorize_endpoint(self, cfg: ClientConfig) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth"

    def token_endpoint(self, cfg: ClientConfig) -> str:
        return "https://oauth2.googleapis.com/token"

    def extra_authorize_params(self) -> dict[str, str]:
        # offline + consent: Google returns a refresh token on every connect
        return {"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"}

    async def account(self, api: Api) -> tuple[str | None, str | None]:
        data = (await api.call("GET", "https://openidconnect.googleapis.com/v1/userinfo", what="userinfo")).json()
        return data.get("sub"), data.get("email")

    async def calendars(self, api: Api) -> list[dict[str, Any]]:
        resp = await api.call("GET", f"{self.API}/users/me/calendarList", params={"minAccessRole": "writer"})
        return [
            {
                "id": c["id"],
                "name": c.get("summaryOverride") or c.get("summary") or c["id"],
                "primary": bool(c.get("primary")),
                "can_write": c.get("accessRole") in ("writer", "owner"),
            }
            for c in resp.json().get("items", [])
        ]

    @staticmethod
    def event_id(ctx: PushContext, booking_id: int) -> str:
        # Google event ids: base32hex (0-9, a-v), 5..1024 characters; deterministic, so a retried insert is idempotent
        return f"smartsched{ctx.connection_id}p{booking_id}"

    def body(self, view: feeds.EventView, ctx: PushContext) -> dict[str, Any]:
        return {
            "summary": view.summary,
            "location": view.location,
            "description": view.description or "",
            "start": {"dateTime": view.start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": ctx.tz_name},
            "end": {"dateTime": view.end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": ctx.tz_name},
            "status": "confirmed",
            "transparency": "opaque",
            "extendedProperties": {"private": {"smartsched_booking_id": str(view.booking.id)}},
        }

    def _events(self, calendar_id: str | None) -> str:
        return f"{self.API}/calendars/{quote(calendar_id or 'primary', safe='')}/events"

    async def upsert(
        self, api: Api, calendar_id: str | None, external_id: str | None, view: feeds.EventView, ctx: PushContext
    ) -> str:
        body = self.body(view, ctx)
        base = self._events(calendar_id)
        if external_id:
            resp = await api.call("PUT", f"{base}/{quote(external_id, safe='')}", json=body, ok=(200, 404, 410))
            if resp.status_code == 200:
                return str(resp.json().get("id") or external_id)
        eid = self.event_id(ctx, view.booking.id)
        resp = await api.call("POST", base, json={**body, "id": eid}, ok=(200, 201, 409))
        if resp.status_code == 409:  # the id exists (an earlier attempt, or a deleted event): overwrite it
            resp = await api.call("PUT", f"{base}/{eid}", json=body, ok=(200,))
        return str(resp.json().get("id") or eid)

    async def delete(self, api: Api, calendar_id: str | None, external_id: str) -> None:
        url = f"{self._events(calendar_id)}/{quote(external_id, safe='')}"
        await api.call("DELETE", url, ok=(200, 204, 404, 410))

    async def revoke(self, client: httpx.AsyncClient, token: str) -> None:
        await client.post("https://oauth2.googleapis.com/revoke", data={"token": token})


class MicrosoftProvider(Provider):
    name = "microsoft"
    label = "Outlook / Microsoft 365"
    scopes = ("offline_access", "openid", "email", "User.Read", "Calendars.ReadWrite")
    default_calendar = None  # /me/events = the user's default calendar
    GRAPH = "https://graph.microsoft.com/v1.0"

    def authorize_endpoint(self, cfg: ClientConfig) -> str:
        return f"https://login.microsoftonline.com/{quote(cfg.tenant, safe='')}/oauth2/v2.0/authorize"

    def token_endpoint(self, cfg: ClientConfig) -> str:
        return f"https://login.microsoftonline.com/{quote(cfg.tenant, safe='')}/oauth2/v2.0/token"

    def extra_authorize_params(self) -> dict[str, str]:
        return {"response_mode": "query", "prompt": "select_account"}

    def _token_form(self, cfg: ClientConfig) -> dict[str, str]:
        return {**super()._token_form(cfg), "scope": " ".join(self.scopes)}

    async def account(self, api: Api) -> tuple[str | None, str | None]:
        data = (
            await api.call("GET", f"{self.GRAPH}/me", params={"$select": "id,mail,userPrincipalName"}, what="me")
        ).json()
        return data.get("id"), data.get("mail") or data.get("userPrincipalName")

    async def calendars(self, api: Api) -> list[dict[str, Any]]:
        resp = await api.call(
            "GET", f"{self.GRAPH}/me/calendars", params={"$select": "id,name,isDefaultCalendar,canEdit"}
        )
        return [
            {
                "id": c["id"],
                "name": c.get("name") or c["id"],
                "primary": bool(c.get("isDefaultCalendar")),
                "can_write": bool(c.get("canEdit", True)),
            }
            for c in resp.json().get("value", [])
        ]

    @staticmethod
    def _utc(local: datetime, tz_name: str) -> dict[str, str]:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("Europe/Istanbul")
        at = local.replace(tzinfo=tz).astimezone(UTC)
        return {"dateTime": at.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}

    def body(self, view: feeds.EventView, ctx: PushContext) -> dict[str, Any]:
        return {
            "subject": view.summary,
            "body": {"contentType": "text", "content": view.description or ""},
            "start": self._utc(view.start, ctx.tz_name),
            "end": self._utc(view.end, ctx.tz_name),
            "location": {"displayName": view.location},
            "showAs": "busy",
        }

    async def upsert(
        self, api: Api, calendar_id: str | None, external_id: str | None, view: feeds.EventView, ctx: PushContext
    ) -> str:
        body = self.body(view, ctx)
        if external_id:
            resp = await api.call(
                "PATCH", f"{self.GRAPH}/me/events/{quote(external_id, safe='')}", json=body, ok=(200, 404, 410)
            )
            if resp.status_code == 200:
                return str(resp.json().get("id") or external_id)
        url = (
            f"{self.GRAPH}/me/calendars/{quote(calendar_id, safe='')}/events"
            if calendar_id
            else f"{self.GRAPH}/me/events"
        )
        # transactionId: Graph drops a repeated POST of the same job (a retry after a lost answer)
        resp = await api.call("POST", url, json={**body, "transactionId": f"smartsched-{ctx.job_id}"}, ok=(200, 201))
        return str(resp.json()["id"])

    async def delete(self, api: Api, calendar_id: str | None, external_id: str) -> None:
        await api.call("DELETE", f"{self.GRAPH}/me/events/{quote(external_id, safe='')}", ok=(200, 204, 404, 410))


PROVIDERS: dict[str, Provider] = {p.name: p for p in (GoogleProvider(), MicrosoftProvider())}


# --------------------------------------------------------------------------------------------------
# Configuration and tokens
# --------------------------------------------------------------------------------------------------


def redirect_uri(base: str, provider: Provider) -> str:
    return f"{base}/api/v1/calendar/connectors/{provider.name}/callback"


async def client_config(session: AsyncSession, provider: Provider) -> ClientConfig | None:
    """The administrator's OAuth client, or ``None`` (not configured: no id, no secret or no public URL)."""
    g = await get_group(session, "integrations", reveal=True)
    cid = (g.get(f"{provider.name}_client_id") or "").strip()
    secret = (g.get(f"{provider.name}_client_secret") or "").strip()
    base, _ = await feeds.public_base(session)
    if not (cid and secret and base):
        return None
    return ClientConfig(cid, secret, redirect_uri(base, provider), str(g.get("microsoft_tenant") or "organizations"))


def _store_tokens(conn: CalendarConnection, tokens: TokenSet) -> None:
    conn.access_token_enc = encrypt_secret(tokens.access_token)
    if tokens.refresh_token:
        conn.refresh_token_enc = encrypt_secret(tokens.refresh_token)
    conn.token_expires_at = utcnow() + timedelta(seconds=max(60, tokens.expires_in) - 60)
    if tokens.scope:
        conn.scopes = tokens.scope


class Api:
    """Authorised calls for one connection: refreshes an expiring token first and once more after a 401."""

    def __init__(self, conn: CalendarConnection, provider: Provider, cfg: ClientConfig, client: httpx.AsyncClient):
        self.conn, self.provider, self.cfg, self.client = conn, provider, cfg, client

    def _access(self) -> str | None:
        try:
            return decrypt_secret(self.conn.access_token_enc) if self.conn.access_token_enc else None
        except ValueError:
            return None

    async def refresh(self) -> str:
        try:
            refresh = decrypt_secret(self.conn.refresh_token_enc) if self.conn.refresh_token_enc else None
        except ValueError:
            refresh = None
        if not refresh:
            raise ProviderError("no refresh token; reconnect the calendar", reauth=True)
        tokens = await self.provider.refresh(self.client, self.cfg, refresh)
        _store_tokens(self.conn, tokens)
        return tokens.access_token

    async def token(self) -> str:
        access = self._access()
        expires = self.conn.token_expires_at
        if access and expires is not None and expires > utcnow():
            return access
        return await self.refresh()

    async def call(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: dict[str, str] | None = None,
        ok: tuple[int, ...] = (200,),
        what: str | None = None,
    ) -> httpx.Response:
        label = what or f"{method} {url.split('?')[0].rsplit('/', 2)[-2]}"
        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {await self.token() if attempt == 1 else await self.refresh()}"}
            try:
                resp = await self.client.request(method, url, json=json, params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise ProviderError(f"{label}: {type(exc).__name__}", retryable=True) from exc
            if resp.status_code == 401 and attempt == 1:
                continue
            if resp.status_code in ok:
                return resp
            err = _classify(resp, label)
            if resp.status_code == 401:
                err.reauth = True
            raise err
        raise ProviderError(f"{label}: unauthorised", reauth=True)  # pragma: no cover - loop always returns/raises


# --------------------------------------------------------------------------------------------------
# Connect / disconnect
# --------------------------------------------------------------------------------------------------


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def get_connection(session: AsyncSession, user_id: int, provider: str) -> CalendarConnection | None:
    q = select(CalendarConnection).where(CalendarConnection.user_id == user_id, CalendarConnection.provider == provider)
    return (await session.execute(q)).scalar_one_or_none()


async def start_authorization(session: AsyncSession, user: User, provider: Provider, return_path: str | None) -> str:
    cfg = await client_config(session, provider)
    if cfg is None:
        raise NotConfigured(provider.name)
    now = utcnow()
    await session.execute(
        delete(OAuthState).where((OAuthState.expires_at < now) | (OAuthState.user_id == user.id))
    )  # one pending authorisation per user; expired ones of everybody go too
    state = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    session.add(
        OAuthState(
            state_hash=_hash(state),
            user_id=user.id,
            provider=provider.name,
            code_verifier_enc=encrypt_secret(verifier),
            return_path=return_path,
            expires_at=now + STATE_TTL,
        )
    )
    await session.flush()
    return provider.authorize_url(cfg, state, challenge)


def _panel(base: str, path: str | None, **params: str) -> str:
    target = path or "/profile"
    sep = "&" if "?" in target else "?"
    return f"{base}{target}{sep}{urlencode(params)}"


async def finish_authorization(
    session: AsyncSession, provider: Provider, *, code: str | None, state: str | None, error: str | None
) -> str:
    """Handle the provider's redirect; returns where to send the browser (always the panel)."""
    base, _ = await feeds.public_base(session)
    row = None
    if state:
        row = (
            await session.execute(select(OAuthState).where(OAuthState.state_hash == _hash(state)))
        ).scalar_one_or_none()
    if row is None or row.provider != provider.name or row.expires_at < utcnow():
        if row is not None:
            await session.delete(row)
            await session.commit()
        return _panel(base, None, calendar="error", provider=provider.name, reason="state")
    path, user_id = row.return_path, row.user_id
    try:
        verifier = decrypt_secret(row.code_verifier_enc)
    except ValueError:
        verifier = ""
    await session.delete(row)  # single use
    await session.commit()

    def fail(reason: str) -> str:
        return _panel(base, path, calendar="error", provider=provider.name, reason=reason)

    if error or not code:
        return fail("denied" if error == "access_denied" or not code else "exchange")
    if not await feeds.sync_enabled(session):
        return fail("disabled")
    cfg = await client_config(session, provider)
    user = await session.get(User, user_id)
    if cfg is None:
        return fail("not_configured")
    if user is None or not user.is_active or not verifier:
        return fail("state")
    conn = await get_connection(session, user_id, provider.name)
    is_new = conn is None
    if conn is None:
        conn = CalendarConnection(user_id=user_id, provider=provider.name)
    async with http_client() as client:
        try:
            tokens = await provider.exchange(client, cfg, code, verifier)
            _store_tokens(conn, tokens)
            subject, email = await provider.account(Api(conn, provider, cfg, client))
        except (ProviderError, KeyError, ValueError):
            await session.rollback()
            return fail("exchange")
    if not is_new and conn.account_subject and subject and conn.account_subject != subject:
        # another account: the old links point into a calendar we can no longer reach
        await session.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
        conn.calendar_id = conn.calendar_name = None
    conn.account_subject, conn.account_email = subject, email
    conn.status, conn.last_error, conn.updated_at = "ACTIVE", None, utcnow()
    session.add(conn)
    await session.flush()
    await queue_full_sync(session, conn)
    await session.commit()
    worker.schedule_drain()
    return _panel(base, path, calendar="connected", provider=provider.name)


async def list_calendars(session: AsyncSession, conn: CalendarConnection) -> list[dict[str, Any]]:
    provider = PROVIDERS[conn.provider]
    cfg = await client_config(session, provider)
    if cfg is None:
        raise ProviderError("not configured")
    async with http_client() as client:
        try:
            return await provider.calendars(Api(conn, provider, cfg, client))
        except ProviderError as exc:
            if exc.reauth:
                conn.status, conn.last_error = "REAUTH", exc.public
            raise


async def choose_calendar(session: AsyncSession, conn: CalendarConnection, calendar_id: str, name: str | None) -> None:
    if conn.calendar_id != calendar_id:
        conn.calendar_id, conn.calendar_name = calendar_id, name
        conn.updated_at = utcnow()
        await queue_full_sync(session, conn)
    elif name:
        conn.calendar_name = name


async def disconnect(session: AsyncSession, conn: CalendarConnection) -> None:
    """Delete the stored tokens, links and jobs now; revoke the grant at the provider in the background."""
    provider = PROVIDERS[conn.provider]
    tokens = [t for t in (conn.refresh_token_enc, conn.access_token_enc) if t]
    plain: list[str] = []
    for t in tokens:
        try:
            plain.append(decrypt_secret(t))
        except ValueError:
            continue
    await session.execute(delete(CalendarSyncJob).where(CalendarSyncJob.connection_id == conn.id))
    await session.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
    await session.delete(conn)
    await session.flush()
    if plain:

        async def revoke() -> None:
            async with http_client() as client:
                try:
                    await provider.revoke(client, plain[0])
                except httpx.HTTPError:
                    pass

        worker.run_detached(revoke, f"integrations:revoke:{conn.provider}:{conn.user_id}")


# --------------------------------------------------------------------------------------------------
# Queueing
# --------------------------------------------------------------------------------------------------


async def _queue_job(session: AsyncSession, conn_id: int, booking_id: int | None, kind: str = "booking") -> bool:
    q = select(CalendarSyncJob.id).where(
        CalendarSyncJob.connection_id == conn_id,
        CalendarSyncJob.kind == kind,
        CalendarSyncJob.status == PENDING,
        CalendarSyncJob.attempts == 0,
    )
    q = q.where(CalendarSyncJob.booking_id == booking_id) if booking_id is not None else q
    if (await session.execute(q.limit(1))).first() is not None:
        return False  # an untouched pending job reconciles the latest state anyway
    session.add(CalendarSyncJob(connection_id=conn_id, booking_id=booking_id, kind=kind, next_attempt_at=utcnow()))
    await session.flush()
    return True


async def queue_full_sync(session: AsyncSession, conn: CalendarConnection) -> int:
    added = await _queue_job(session, conn.id, None, "full")
    worker.kick_after_commit(session)
    return int(added)


async def queue_bookings(session: AsyncSession, booking_ids: list[int]) -> int:
    """One job per (connection, booking) for the bookings' owners and for connections that hold an event of it."""
    ids = sorted({int(i) for i in booking_ids})
    if not ids or not await feeds.sync_enabled(session):
        return 0
    owners = dict(
        (await session.execute(select(Booking.id, Booking.user_id).where(Booking.id.in_(ids)))).tuples().all()
    )
    user_ids = {u for u in owners.values() if u is not None}
    conns_by_user: dict[int, list[int]] = {}
    if user_ids:
        q = select(CalendarConnection.user_id, CalendarConnection.id).where(
            CalendarConnection.user_id.in_(user_ids), CalendarConnection.status == "ACTIVE"
        )
        for uid, cid in (await session.execute(q)).tuples():
            conns_by_user.setdefault(uid, []).append(cid)
    linked: dict[int, set[int]] = {}
    q2 = select(CalendarEventLink.booking_id, CalendarEventLink.connection_id).where(
        CalendarEventLink.booking_id.in_(ids)
    )
    for bid, cid in (await session.execute(q2)).tuples():
        linked.setdefault(bid, set()).add(cid)
    added = 0
    for bid in ids:
        targets = set(conns_by_user.get(owners.get(bid) or -1, [])) | linked.get(bid, set())
        for cid in sorted(targets):
            added += int(await _queue_job(session, cid, bid))
    if added:
        worker.kick_after_commit(session)
    return added


# --------------------------------------------------------------------------------------------------
# The worker side
# --------------------------------------------------------------------------------------------------


async def _expand_full(session: AsyncSession, conn: CalendarConnection) -> None:
    since = await booking_svc.today(session) - timedelta(days=PUSH_PAST_DAYS)
    q = select(Booking.id).where(Booking.user_id == conn.user_id, Booking.status == BOOKED, Booking.date >= since)
    ids = set((await session.execute(q)).scalars())
    q2 = select(CalendarEventLink.booking_id).where(CalendarEventLink.connection_id == conn.id)
    ids |= set((await session.execute(q2)).scalars())
    for bid in sorted(ids):
        await _queue_job(session, conn.id, bid)


async def _reconcile(
    session: AsyncSession, api: Api, conn: CalendarConnection, job: CalendarSyncJob, tz_name: str
) -> None:
    provider = api.provider
    assert job.booking_id is not None
    b = await session.get(Booking, job.booking_id)
    link = (
        await session.execute(
            select(CalendarEventLink).where(
                CalendarEventLink.connection_id == conn.id, CalendarEventLink.booking_id == job.booking_id
            )
        )
    ).scalar_one_or_none()
    target_calendar = conn.calendar_id or provider.default_calendar
    since = await booking_svc.today(session) - timedelta(days=PUSH_PAST_DAYS)
    wanted = b is not None and b.user_id == conn.user_id and b.status == BOOKED and b.date >= since
    if link is not None and (not wanted or (link.calendar_id or None) != (target_calendar or None)):
        await provider.delete(api, link.calendar_id or None, link.external_id)
        await session.delete(link)
        await session.flush()
        link = None
    if not wanted or b is None:
        return
    view = await feeds.event_view(feeds._Cache(session), None, b)
    if view is None:
        return
    if link is not None and link.fingerprint == view.fingerprint:
        return  # the external event already shows this state
    ctx = PushContext(connection_id=conn.id, job_id=job.id, tz_name=tz_name)
    external_id = await provider.upsert(api, target_calendar, link.external_id if link else None, view, ctx)
    if link is None:
        link = CalendarEventLink(connection_id=conn.id, booking_id=b.id, calendar_id=target_calendar or "")
        session.add(link)
    link.external_id, link.fingerprint, link.synced_at = external_id, view.fingerprint, utcnow()
    link.calendar_id = target_calendar or ""


async def _process(session: AsyncSession, job: CalendarSyncJob, client: httpx.AsyncClient, now: datetime) -> None:
    conn = await session.get(CalendarConnection, job.connection_id)
    if conn is None:
        job.status, job.done_at = DONE, now
        return
    provider = PROVIDERS.get(conn.provider)
    cfg = await client_config(session, provider) if provider else None

    def skip(reason: str) -> None:
        job.status, job.last_error, job.done_at = SKIPPED, reason, now

    if not await feeds.sync_enabled(session):
        return skip("calendar sync is turned off")
    if provider is None or cfg is None:
        return skip("provider not configured")
    if conn.status == "REAUTH":
        return skip("the calendar must be reconnected")
    if job.kind == "full":
        await _expand_full(session, conn)
        job.status, job.done_at, job.last_error = DONE, now, None
        return
    tz_name = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    api = Api(conn, provider, cfg, client)
    job.attempts += 1
    try:
        await _reconcile(session, api, conn, job, tz_name)
    except ProviderError as exc:
        job.last_error = exc.public
        conn.last_error = exc.public
        if exc.reauth:
            conn.status = "REAUTH"
            job.status, job.done_at = FAILED, now
            return
        retry_at = worker.next_attempt(job.attempts, now) if exc.retryable else None
        if retry_at is None:
            job.status, job.done_at = FAILED, now
        else:
            job.status, job.next_attempt_at, job.locked_until = PENDING, retry_at, None
        return
    job.status, job.done_at, job.last_error = DONE, now, None
    conn.last_synced_at, conn.last_error, conn.status = now, None, "ACTIVE"


async def drain_due(now: datetime, limit: int) -> int:
    factory = get_session_factory()
    async with factory() as session:
        ids = list(
            (
                await session.execute(worker.due(CalendarSyncJob, now).order_by(CalendarSyncJob.id).limit(limit))
            ).scalars()
        )
    done = 0
    async with http_client() as client:
        for job_id in ids:
            async with factory() as session:
                if not await worker.claim(session, CalendarSyncJob, job_id, now):
                    continue
                job = await session.get(CalendarSyncJob, job_id)
                if job is None:
                    continue
                try:
                    await _process(session, job, client, now)
                except Exception as exc:  # noqa: BLE001 - a bug must not wedge the row in RUNNING
                    await session.rollback()
                    job = await session.get(CalendarSyncJob, job_id)
                    if job is None:
                        continue
                    job.attempts += 1
                    job.last_error = f"internal error: {type(exc).__name__}"
                    retry_at = worker.next_attempt(job.attempts, now)
                    job.status = PENDING if retry_at else FAILED
                    job.next_attempt_at = retry_at or job.next_attempt_at
                    job.locked_until = None
                if job.status == RUNNING:  # pragma: no cover - _process always decides
                    job.status = DONE
                await session.commit()
                done += 1
    if done:
        # a full sync may have queued booking jobs: run them in this pass too
        async with factory() as session:
            more = (await session.execute(worker.due(CalendarSyncJob, now).limit(1))).first()
        if more is not None:
            worker.schedule_drain()
    return done


async def next_due() -> datetime | None:
    async with get_session_factory()() as session:
        q = select(func.min(CalendarSyncJob.next_attempt_at)).where(CalendarSyncJob.status == PENDING)
        return (await session.execute(q)).scalar_one_or_none()


def schedule_drain() -> None:
    worker.schedule_drain()


# --------------------------------------------------------------------------------------------------
# Status for the panel
# --------------------------------------------------------------------------------------------------


async def connectors_out(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in PROVIDERS.values():
        item: dict[str, Any] = {
            "provider": p.name,
            "label": p.label,
            "configured": await client_config(session, p) is not None,
            "connected": False,
        }
        conn = await get_connection(session, user.id, p.name)
        if conn is not None:
            counts = dict(
                (
                    await session.execute(
                        select(CalendarSyncJob.status, func.count(CalendarSyncJob.id))
                        .where(CalendarSyncJob.connection_id == conn.id)
                        .group_by(CalendarSyncJob.status)
                    )
                ).tuples()
            )
            item.update(
                connected=True,
                status=conn.status,
                account_email=conn.account_email,
                calendar_id=conn.calendar_id or p.default_calendar,
                calendar_name=conn.calendar_name,
                last_synced_at=conn.last_synced_at.isoformat() if conn.last_synced_at else None,
                last_error=conn.last_error,
                pending_jobs=int(counts.get(PENDING, 0)) + int(counts.get(RUNNING, 0)),
                failed_jobs=int(counts.get(FAILED, 0)),
            )
        out.append(item)
    return out
