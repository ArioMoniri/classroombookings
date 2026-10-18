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
* Disconnect deletes the stored tokens at once (T6 acceptance), removes the pushed events and revokes the Google grant
  in the background (or awaited, for a KVKK erasure, which records the provider's answer; :func:`disconnect`).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
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
from app.services import audit, settings_service
from app.services import bookings as booking_svc
from app.services import calendar_feeds as feeds
from app.services.bookings_settings import get_group
from app.workers import integrations as worker

log = logging.getLogger(__name__)

STATE_TTL = timedelta(minutes=10)
#: bookings pushed by a full sync: from this many days ago onwards
PUSH_PAST_DAYS = 7
HTTP_TIMEOUT_S = 15.0


class NotConfigured(Exception):
    pass


class ProviderError(Exception):
    """``public``: short, safe to show. ``retryable``: network / 429 / 5xx. ``reauth``: the grant is gone."""

    def __init__(
        self,
        public: str,
        *,
        status: int | None = None,
        retryable: bool = False,
        reauth: bool = False,
        retry_after: int | None = None,
    ):
        super().__init__(public)
        self.public = public[:300]
        self.status = status
        self.retryable = retryable
        self.reauth = reauth
        #: seconds the provider asked us to wait (``Retry-After`` on 429 / 503); the job backs off at least this long
        self.retry_after = retry_after


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
    #: the OpenID id_token of the code exchange (CAL-07 reads ``hd`` / ``tid`` from it; received over TLS from the
    #: token endpoint, so its claims are trusted without a signature check, OIDC Core §3.1.3.7)
    id_token: str | None = None


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
    retry_after: int | None = None
    raw = resp.headers.get("retry-after")
    if raw and raw.strip().isdigit():
        retry_after = min(int(raw.strip()), 24 * 3600)
    return ProviderError(
        text,
        status=status,
        retryable=status in (408, 429) or status >= 500 or rate_limited,
        retry_after=retry_after,
    )


# --------------------------------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------------------------------


class Provider:
    name = ""
    label = ""
    scopes: tuple[str, ...] = ()
    default_calendar: str | None = None
    #: sent with every API call of this provider
    api_headers: dict[str, str] = {}
    #: the provider has an endpoint that revokes the user's grant (:meth:`revoke`)
    can_revoke = False

    def authorize_endpoint(self, cfg: ClientConfig) -> str:
        raise NotImplementedError

    def token_endpoint(self, cfg: ClientConfig) -> str:
        raise NotImplementedError

    #: CAL-06: the scopes of a new connection that pushes into a calendar SmartSched creates (least privilege)
    owned_scopes: tuple[str, ...] = ()
    #: the dedicated calendar's name (research §3.6)
    OWNED_NAME = "SmartSched – Derslerim"

    def authorize_url(
        self, cfg: ClientConfig, state: str, challenge: str, scopes: tuple[str, ...] | None = None
    ) -> str:
        params = {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes or self.scopes),
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
            id_token=data.get("id_token"),
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

    async def account_info(self, api: Api, tokens: TokenSet) -> AccountInfo:
        """CAL-07: who the provider account is (subject, e-mail, Google ``hd``, Entra ``tid``)."""
        subject, email = await self.account(api)
        claims = id_token_claims(tokens.id_token)
        return AccountInfo(
            subject=subject or claims.get("sub"),
            email=email or claims.get("email"),
            hosted_domain=claims.get("hd"),
            tenant=claims.get("tid"),
        )

    async def calendars(self, api: Api) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def create_calendar(self, api: Api, name: str, tz_name: str) -> str:
        raise NotImplementedError

    async def delete_calendar(self, api: Api, calendar_id: str) -> None:
        raise NotImplementedError

    async def upsert_class(
        self, api: Api, calendar_id: str, external_id: str | None, item: ClassItem, ctx: PushContext
    ) -> str:
        raise NotImplementedError

    async def list_owned(self, api: Api, calendar_id: str) -> dict[str, datetime | None] | None:
        """The SmartSched events in the owned calendar (``external id -> last change``); ``None`` when the
        calendar is gone (the user deleted it)."""
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


@dataclass(frozen=True)
class AccountInfo:
    subject: str | None
    email: str | None
    hosted_domain: str | None = None  # Google Workspace ``hd``
    tenant: str | None = None  # Entra ``tid``


@dataclass(frozen=True)
class ClassItem:
    """One class event to push (CAL-06): the same content as the feeds (``calendar_classes``)."""

    uid: str
    start: datetime
    end: datetime
    summary: str
    location: str
    description: str | None
    fingerprint: str  # of the pushed content (the occurrence's fingerprint + the description)


def id_token_claims(token: str | None) -> dict[str, Any]:
    """The payload of an id_token (no signature check; see :class:`TokenSet`); ``{}`` when absent or unreadable."""
    import json

    if not token or token.count(".") < 2:
        return {}
    part = token.split(".")[1]
    try:
        data = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def class_event_key(connection_id: int, uid: str) -> str:
    return hashlib.sha1(f"{connection_id}|{uid}".encode()).hexdigest()[:24]  # noqa: S324 - an id, not a secret


class GoogleProvider(Provider):
    name = "google"
    label = "Google Calendar"
    scopes = (
        "openid",
        "email",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    )
    #: owner decision 2026-10-17 (6): new connections only reach the calendars SmartSched creates
    owned_scopes = ("openid", "email", "https://www.googleapis.com/auth/calendar.app.created")
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

    async def account_info(self, api: Api, tokens: TokenSet) -> AccountInfo:
        data = (await api.call("GET", "https://openidconnect.googleapis.com/v1/userinfo", what="userinfo")).json()
        claims = id_token_claims(tokens.id_token)
        return AccountInfo(
            subject=data.get("sub") or claims.get("sub"),
            email=data.get("email") or claims.get("email"),
            hosted_domain=data.get("hd") or claims.get("hd"),
        )

    async def create_calendar(self, api: Api, name: str, tz_name: str) -> str:
        resp = await api.call("POST", f"{self.API}/calendars", json={"summary": name, "timeZone": tz_name},
                              what="calendars.insert")  # fmt: skip
        return str(resp.json()["id"])

    async def delete_calendar(self, api: Api, calendar_id: str) -> None:
        await api.call(
            "DELETE", f"{self.API}/calendars/{quote(calendar_id, safe='')}", ok=(200, 204, 404, 410),
            what="calendars.delete",
        )  # fmt: skip

    @staticmethod
    def class_event_id(ctx: PushContext, uid: str) -> str:
        return f"smartsched{ctx.connection_id}c{class_event_key(ctx.connection_id, uid)}"  # base32hex

    def class_body(self, item: ClassItem, ctx: PushContext) -> dict[str, Any]:
        return {
            "summary": item.summary,
            "location": item.location,
            "description": item.description or "",
            "start": {"dateTime": item.start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": ctx.tz_name},
            "end": {"dateTime": item.end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": ctx.tz_name},
            "status": "confirmed",
            "transparency": "opaque",
            "extendedProperties": {"private": {"smartsched": "1", "smartsched_uid": item.uid}},
        }

    async def upsert_class(
        self, api: Api, calendar_id: str, external_id: str | None, item: ClassItem, ctx: PushContext
    ) -> str:
        body = self.class_body(item, ctx)
        base = self._events(calendar_id)
        if external_id:
            resp = await api.call("PATCH", f"{base}/{quote(external_id, safe='')}", json=body, ok=(200, 404, 410))
            if resp.status_code == 200:
                return str(resp.json().get("id") or external_id)
        eid = self.class_event_id(ctx, item.uid)
        resp = await api.call("POST", base, json={**body, "id": eid}, ok=(200, 201, 409))
        if resp.status_code == 409:  # an earlier attempt inserted it (or it was deleted): overwrite, no duplicate
            resp = await api.call("PATCH", f"{base}/{eid}", json=body, ok=(200,))
        return str(resp.json().get("id") or eid)

    async def list_owned(self, api: Api, calendar_id: str) -> dict[str, datetime | None] | None:
        out: dict[str, datetime | None] = {}
        params = {"privateExtendedProperty": "smartsched=1", "maxResults": "2500", "showDeleted": "false"}
        while True:
            resp = await api.call("GET", self._events(calendar_id), params=params, ok=(200, 404, 410),
                                  what="events.list")  # fmt: skip
            if resp.status_code != 200:
                return None
            data = resp.json()
            for e in data.get("items", []):
                out[str(e["id"])] = _parse_stamp(e.get("updated"))
            token = data.get("nextPageToken")
            if not token:
                return out
            params = {**params, "pageToken": str(token)}

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

    can_revoke = True

    async def revoke(self, client: httpx.AsyncClient, token: str) -> None:
        """Revoke the grant; a token Google no longer knows (``invalid_token``: revoked or expired) is revoked."""
        try:
            resp = await client.post("https://oauth2.googleapis.com/revoke", data={"token": token})
        except httpx.HTTPError as exc:
            raise ProviderError(f"revoke: {type(exc).__name__}", retryable=True) from exc
        if resp.status_code == 200:
            return
        if resp.status_code == 400 and "invalid_token" in resp.text:
            return
        raise _classify(resp, "revoke")


class MicrosoftProvider(Provider):
    name = "microsoft"
    label = "Outlook / Microsoft 365"
    scopes = ("offline_access", "openid", "email", "User.Read", "Calendars.ReadWrite")
    #: Graph has nothing narrower than Calendars.ReadWrite to create a calendar (research §2.4)
    owned_scopes = scopes
    default_calendar = None  # /me/events = the user's default calendar
    # immutable ids: an event keeps its id when the user moves it to another folder / calendar
    api_headers = {"Prefer": 'IdType="ImmutableId"'}
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

    async def account_info(self, api: Api, tokens: TokenSet) -> AccountInfo:
        subject, email = await self.account(api)
        claims = id_token_claims(tokens.id_token)
        tenant = claims.get("tid")
        if not tenant:  # no id_token: the directory of the signed-in user (User.Read covers /organization)
            try:
                org = await api.call("GET", f"{self.GRAPH}/organization", params={"$select": "id"},
                                     ok=(200, 403, 404), what="organization")  # fmt: skip
                if org.status_code == 200:
                    value = org.json().get("value") or []
                    tenant = value[0].get("id") if value else None
            except ProviderError:
                tenant = None
        return AccountInfo(subject=subject or claims.get("oid"), email=email, tenant=tenant)

    async def create_calendar(self, api: Api, name: str, tz_name: str) -> str:
        resp = await api.call("POST", f"{self.GRAPH}/me/calendars", json={"name": name}, ok=(200, 201),
                              what="calendars.create")  # fmt: skip
        return str(resp.json()["id"])

    async def delete_calendar(self, api: Api, calendar_id: str) -> None:
        await api.call("DELETE", f"{self.GRAPH}/me/calendars/{quote(calendar_id, safe='')}",
                       ok=(200, 204, 404, 410), what="calendars.delete")  # fmt: skip

    def class_body(self, item: ClassItem, ctx: PushContext) -> dict[str, Any]:
        return {
            "subject": item.summary,
            "body": {"contentType": "text", "content": item.description or ""},
            "start": self._utc(item.start, ctx.tz_name),
            "end": self._utc(item.end, ctx.tz_name),
            "location": {"displayName": item.location},
            "showAs": "busy",
            "categories": ["SmartSched"],
        }

    async def upsert_class(
        self, api: Api, calendar_id: str, external_id: str | None, item: ClassItem, ctx: PushContext
    ) -> str:
        body = self.class_body(item, ctx)
        if external_id:
            resp = await api.call(
                "PATCH", f"{self.GRAPH}/me/events/{quote(external_id, safe='')}", json=body, ok=(200, 404, 410)
            )
            if resp.status_code == 200:
                return str(resp.json().get("id") or external_id)
        url = f"{self.GRAPH}/me/calendars/{quote(calendar_id, safe='')}/events"
        # transactionId: the same occurrence + content is created once, however often the job is retried
        tid = "smartsched-" + hashlib.sha1(f"{ctx.connection_id}|{item.uid}|{item.fingerprint}".encode()).hexdigest()  # noqa: S324
        resp = await api.call("POST", url, json={**body, "transactionId": tid}, ok=(200, 201))
        return str(resp.json()["id"])

    async def list_owned(self, api: Api, calendar_id: str) -> dict[str, datetime | None] | None:
        out: dict[str, datetime | None] = {}
        url: str | None = f"{self.GRAPH}/me/calendars/{quote(calendar_id, safe='')}/events"
        params: dict[str, str] | None = {"$select": "id,lastModifiedDateTime", "$top": "500"}
        while url:
            resp = await api.call("GET", url, params=params, ok=(200, 404, 410), what="events.list")
            if resp.status_code != 200:
                return None
            data = resp.json()
            for e in data.get("value", []):
                out[str(e["id"])] = _parse_stamp(e.get("lastModifiedDateTime"))
            url, params = data.get("@odata.nextLink"), None
        return out

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


def _parse_stamp(value: Any) -> datetime | None:
    """RFC 3339 (``2026-02-16T08:00:00.000Z``) -> naive UTC; ``None`` when absent or unreadable."""
    if not value:
        return None
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return at.astimezone(UTC).replace(tzinfo=None) if at.tzinfo else at


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
    tenant = str(g.get("microsoft_tenant") or "organizations")
    base, _ = await feeds.public_base(session)
    if not (cid and secret) and g.get("calendar_client_source") == "identity":
        found = await identity_client(session, provider)
        if found is not None:
            cid, secret, tenant = found[0], found[1], found[2] or tenant
    if not (cid and secret and base):
        return None
    return ClientConfig(cid, secret, redirect_uri(base, provider), tenant)


#: SsoProvider.kind per push provider (app/services/identity/kinds.py)
IDP_KIND = {"google": "google_workspace", "microsoft": "entra"}


async def identity_client(session: AsyncSession, provider: Provider) -> tuple[str, str, str | None] | None:
    """CAL-07 ``integrations.calendar_client_source = identity``: reuse the enabled sign-in provider's OAuth client
    (W3-IDP's ``sso_providers`` row, read only) -- ``(client id, secret, Entra tenant)``. The administrator adds
    SmartSched's calendar callback to that app registration's redirect URIs."""
    from app.models.sso import SsoProvider

    q = select(SsoProvider).where(SsoProvider.kind == IDP_KIND.get(provider.name, ""), SsoProvider.enabled.is_(True))
    for row in (await session.execute(q.order_by(SsoProvider.sort_order, SsoProvider.id))).scalars():
        if not (row.client_id and row.client_secret_enc):
            continue
        try:
            secret = decrypt_secret(row.client_secret_enc)
        except ValueError:
            continue
        return row.client_id, secret, row.tenant_id
    return None


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
            token = await self.token() if attempt == 1 else await self.refresh()
            headers = {**self.provider.api_headers, "Authorization": f"Bearer {token}"}
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
# CAL-07: verified accounts
# --------------------------------------------------------------------------------------------------

#: personal mailbox providers: never "the institution's domain", whatever the person's SmartSched e-mail is
CONSUMER_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "yandex.com",
        "yandex.com.tr",
        "mail.ru",
        "proton.me",
        "protonmail.com",
        "hotmail.com.tr",
        "windowslive.com",
    }
)


@dataclass(frozen=True)
class Verdict:
    """``kind``: sso_identity | tenant | domain | email (None = not verified); ``domain``: what to ask for."""

    kind: str | None
    domain: str | None


def _domain(email: str | None) -> str | None:
    text = (email or "").strip().casefold()
    return text.rsplit("@", 1)[1] if "@" in text else None


def clean_domains(values: Any) -> list[str]:
    """Admin-allowed e-mail domains: trimmed (NBSP too), lower-cased, ``@`` dropped, de-duplicated."""
    from app.importers import normalize as n

    out: list[str] = []
    for raw in values or []:
        text = (n.clean_text(str(raw)) or "").casefold().lstrip("@").strip()
        if text and "." in text and " " not in text and text not in out:
            out.append(text)
    return out


async def push_verified_only(session: AsyncSession) -> bool:
    g = await get_group(session, "integrations")
    return bool(g.get("push_verified_only", True))


async def verify_account(session: AsyncSession, user: User | None, provider: Provider, info: AccountInfo) -> Verdict:
    """Owner decision 2026-10-17 (3): the provider account counts as the person's when (a) its subject is one of the
    person's sign-in identities (W3-IDP ``user_identities``, read only), (b) its Entra tenant is the sign-in
    provider's tenant, (c) its Google ``hd`` is the Workspace provider's hosted domain, (d) its e-mail is the
    person's own sign-in e-mail, or (e) its e-mail domain is one the admin allows or the institution domain of the
    person's own e-mail (never a personal mailbox provider such as gmail.com)."""
    from app.models.sso import SsoProvider, UserIdentity

    if user is None:
        return Verdict(None, None)
    own = _domain(user.email)
    institution = own if own and own not in CONSUMER_DOMAINS else None
    g = await get_group(session, "integrations")
    allowed = clean_domains(g.get("push_allowed_domains"))
    idps = list(
        (
            await session.execute(select(SsoProvider).where(SsoProvider.enabled.is_(True)).order_by(SsoProvider.id))
        ).scalars()
    )
    hosted = [
        str(d).casefold()
        for p in idps
        if p.kind == "google_workspace"
        for d in (p.options or {}).get("hosted_domains") or []
    ]
    hint = (hosted[0] if hosted else None) or institution or (allowed[0] if allowed else None)
    if info.subject:
        q = select(UserIdentity.id).where(UserIdentity.user_id == user.id, UserIdentity.subject == info.subject)
        if (await session.execute(q.limit(1))).first() is not None:
            return Verdict("sso_identity", hint)
    if provider.name == "microsoft" and info.tenant:
        tenants = {str(p.tenant_id).casefold() for p in idps if p.kind == "entra" and p.tenant_id}
        if info.tenant.casefold() in tenants:
            return Verdict("tenant", hint)
    if provider.name == "google" and info.hosted_domain and info.hosted_domain.casefold() in hosted:
        return Verdict("domain", hint)
    email = (info.email or "").strip().casefold()
    if email and user.email and email == user.email.strip().casefold():
        return Verdict("email", hint)
    dom = _domain(email)
    if dom and dom not in CONSUMER_DOMAINS and (dom in allowed or dom == institution):
        return Verdict("domain", hint)
    return Verdict(None, hint)


def not_verified_detail(domain: str | None) -> dict[str, Any]:
    """The refusal the panel shows after the callback (``reason=account_not_verified&domain=…``)."""
    what = domain or "kurumsal"
    return {
        "code": "account_not_verified",
        "message_tr": f"Bu hesap kurumunuzun doğrulanmış hesabı değil. {what} uzantılı hesabınızla bağlanın.",
        "message_en": f"This is not your institution's verified account. Connect with your {domain or 'institution'} "
        "account.",
        "domain": domain,
    }


# --------------------------------------------------------------------------------------------------
# Connect / disconnect
# --------------------------------------------------------------------------------------------------


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def get_connection(session: AsyncSession, user_id: int, provider: str) -> CalendarConnection | None:
    q = select(CalendarConnection).where(CalendarConnection.user_id == user_id, CalendarConnection.provider == provider)
    return (await session.execute(q)).scalar_one_or_none()


async def start_authorization(
    session: AsyncSession,
    user: User,
    provider: Provider,
    return_path: str | None,
    export_scopes: list[str] | None = None,
) -> str:
    """The provider's consent screen URL. Without the person's active ``calendar_sync`` consent (sync on) the 409
    ``consent_required`` :class:`~app.services.kvkk.KvkkError` comes first, before any state row is written.
    ``export_scopes`` (CAL-06, already checked by :func:`check_export_scopes`): a new connection that pushes into a
    calendar SmartSched creates, asked with the least scopes (Google ``calendar.app.created``); ``None`` keeps the
    legacy bookings-only connect into a chosen calendar."""
    await feeds.require_sync_consent(session, user)
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
            export_scopes=export_scopes,
        )
    )
    await session.flush()
    return provider.authorize_url(cfg, state, challenge, provider.owned_scopes if export_scopes else None)


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
    path, user_id, export_scopes = row.return_path, row.user_id, row.export_scopes
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
    if conn is not None and export_scopes and not conn.owned_calendar:
        # a legacy connection reconnected with fewer permissions: its pushed events go with the old grant first
        await disconnect(session, conn)
        await session.commit()
        conn = None
    is_new = conn is None
    if conn is None:
        conn = CalendarConnection(user_id=user_id, provider=provider.name)
    async with http_client() as client:
        try:
            tokens = await provider.exchange(client, cfg, code, verifier)
            _store_tokens(conn, tokens)
            info = await provider.account_info(Api(conn, provider, cfg, client), tokens)
        except (ProviderError, KeyError, ValueError):
            await session.rollback()
            return fail("exchange")
        verdict = await verify_account(session, user, provider, info)
        if verdict.kind is None and await push_verified_only(session):
            # CAL-07: not the person's institution account -- nothing is stored, the grant is given back
            await session.rollback()
            grant = tokens.refresh_token or tokens.access_token
            if provider.can_revoke and grant:
                try:
                    await provider.revoke(client, grant)
                except (ProviderError, httpx.HTTPError):
                    log.warning("calendar connect refused: revoking the unverified grant failed")
            refused = await session.get(User, user_id)
            await audit.record(
                session,
                "calendar.push_refused",
                "calendar_connection",
                None,
                after={"provider": provider.name, "reason": "account_not_verified", "domain": verdict.domain},
                actor=refused,
            )
            await session.commit()
            return _panel(base, path, calendar="error", provider=provider.name, reason="account_not_verified",
                          domain=verdict.domain or "")  # fmt: skip
    subject, email = info.subject, info.email
    if not is_new and conn.account_subject and subject and conn.account_subject != subject:
        # another account: the old links point into a calendar we can no longer reach
        await session.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
        conn.calendar_id = conn.calendar_name = None
    conn.account_subject, conn.account_email = subject, email
    conn.status, conn.last_error, conn.updated_at = "ACTIVE", None, utcnow()
    conn.account_verified = verdict.kind or "none"
    if export_scopes:
        conn.export_scopes = list(export_scopes)
        conn.owned_calendar = True
    session.add(conn)
    await session.flush()
    await audit.record(
        session,
        "calendar.push_connect",
        "calendar_connection",
        conn.id,
        after={
            "provider": provider.name,
            "account_verified": conn.account_verified,
            "verified_only": await push_verified_only(session),
            "export_scopes": list(conn.export_scopes or ["my_bookings"]),
            "owned_calendar": conn.owned_calendar,
        },
        actor=user,
    )
    await queue_full_sync(session, conn)
    if is_new and user is not None:  # RF-11: "Google takviminiz bağlandı" (mandatory legal notice)
        from app.services import mail_senders

        await mail_senders.calendar_connection(
            session, user, provider=provider.name, connected=True, connection_id=conn.id
        )
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


#: how long a waiting disconnect (KVKK erasure) talks to the provider before the rest goes to the background
WAIT_CLEANUP_S = 20.0


async def disconnect(
    session: AsyncSession,
    conn: CalendarConnection,
    *,
    remove_events: bool = True,
    wait: bool = False,
    timeout: float | None = None,
    notify: bool = False,
) -> dict[str, Any]:
    """:func:`_disconnect`; ``notify`` (the person removed it themselves: ``DELETE /calendar/connectors/{provider}``)
    sends them "… takviminizin bağlantısı kaldırıldı" (RF-11, mandatory legal notice). A KVKK withdrawal or erasure
    and a reconnect with fewer permissions do not: the withdrawal has its own message."""
    user_id, provider_name, conn_id = conn.user_id, conn.provider, conn.id
    out = await _disconnect(session, conn, remove_events=remove_events, wait=wait, timeout=timeout)
    user = await session.get(User, user_id) if notify and user_id else None
    if user is not None and user.is_active:
        from app.services import mail_senders

        await mail_senders.calendar_connection(
            session, user, provider=provider_name, connected=False, connection_id=conn_id
        )
    return out


async def _disconnect(
    session: AsyncSession,
    conn: CalendarConnection,
    *,
    remove_events: bool = True,
    wait: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Delete the stored tokens, links and jobs now; delete the events SmartSched pushed into the user's calendar
    (``remove_events``; ROADMAP calendar-sync follow-up) and then revoke the grant at the provider -- in the
    background, or awaited first with ``wait=True`` (the KVKK erasure records what the provider answered; after
    ``timeout`` seconds, default :data:`WAIT_CLEANUP_S`, the rest is finished in the background).

    The outcome: ``{provider, events, events_removed, events_failed, revoke, errors}``; ``revoke`` is ``queued``
    (background), ``done``, ``failed``, ``not_supported`` (Microsoft has no grant revocation endpoint: deleting the
    tokens is what SmartSched can do), ``unreadable`` (the stored grant cannot be decrypted, e.g. a rotated
    ``APP_SECRET``: nothing can be revoked or removed) or ``none`` (no grant was stored)."""
    provider = PROVIDERS[conn.provider]
    timeout = WAIT_CLEANUP_S if timeout is None else timeout
    plain: dict[str, str] = {}
    unreadable = False
    for name, enc in (("refresh", conn.refresh_token_enc), ("access", conn.access_token_enc)):
        if not enc:
            continue
        try:
            plain[name] = decrypt_secret(enc)
        except ValueError:
            unreadable = True
    links = [
        (link.calendar_id, link.external_id)
        for link in (
            await session.execute(select(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
        ).scalars()
    ]
    owned = conn.calendar_id if (conn.owned_calendar and conn.calendar_id and remove_events) else None
    # CAL-06: SmartSched's own calendar goes in one call (with every event in it), unlike AutoCalEx (research §2.2)
    targets = [] if owned else (links if remove_events else [])
    cfg = await client_config(session, provider) if (targets or owned) else None
    # a detached copy of the credentials: the row itself is deleted below
    ghost = CalendarConnection(
        provider=conn.provider,
        user_id=conn.user_id,
        access_token_enc=conn.access_token_enc,
        refresh_token_enc=conn.refresh_token_enc,
        token_expires_at=conn.token_expires_at,
    )
    key = f"integrations:revoke:{conn.provider}:{conn.user_id}"
    out: dict[str, Any] = {
        "provider": conn.provider,
        "events": len(targets),
        "events_removed": 0,
        "events_failed": 0,
        "revoke": "none",
        "errors": [],
    }
    if owned is not None:  # the outcome keeps its shape for legacy connections (KVKK erasure records it)
        out["calendar_deleted"] = False
    token = plain.get("refresh") or plain.get("access")

    async def cleanup(res: dict[str, Any], items: list[tuple[str, str]]) -> None:
        """Remove ``items`` from the external calendar, then revoke the grant; ``res`` is updated as it goes (a
        timed-out wait keeps the counts so far)."""
        async with http_client() as client:
            if owned is not None and cfg is not None:
                try:
                    await provider.delete_calendar(Api(ghost, provider, cfg, client), owned)
                    res["calendar_deleted"] = True
                except (ProviderError, httpx.HTTPError) as exc:
                    res["errors"].append(str(exc)[:200] or type(exc).__name__)
            if items and cfg is None:
                res["events_failed"] += len(items)
                res["errors"].append(f"{provider.label} is not configured any more: the pushed events stay")
            elif items and cfg is not None:
                api = Api(ghost, provider, cfg, client)
                for calendar_id, external_id in items:
                    try:
                        await provider.delete(api, calendar_id, external_id)
                        res["events_removed"] += 1
                    except (ProviderError, httpx.HTTPError) as exc:
                        res["events_failed"] += 1  # the grant no longer works, or the provider is down
                        if len(res["errors"]) < 5:
                            res["errors"].append(str(exc)[:200] or type(exc).__name__)
            if not provider.can_revoke:
                res["revoke"] = "not_supported"
                return
            try:
                await provider.revoke(client, token or "")
                res["revoke"] = "done"
            except (ProviderError, httpx.HTTPError) as exc:
                res["revoke"] = "failed"
                res["errors"].append(str(exc)[:200] or type(exc).__name__)

    def in_background(items: list[tuple[str, str]]) -> None:
        async def job() -> None:
            res: dict[str, Any] = {**out, "events": len(items), "events_removed": 0, "events_failed": 0, "errors": []}
            await cleanup(res, items)
            if res["events_failed"] or res["revoke"] == "failed":
                log.warning("calendar disconnect %s: %s", key, res)

        worker.run_detached(job, key)

    if owned is not None and token and not wait:
        out["revoke"] = "queued"
        in_background([])
        await session.execute(delete(CalendarSyncJob).where(CalendarSyncJob.connection_id == conn.id))
        await session.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
        await session.delete(conn)
        await session.flush()
        return out
    if wait and token:
        # before the rows go: no write is pending in this transaction while the provider answers
        try:
            await asyncio.wait_for(cleanup(out, targets), timeout)
        except TimeoutError:
            out["errors"].append(f"the provider did not finish within {timeout:g} s: finishing in the background")
            out["revoke"] = "queued"
            in_background(targets[out["events_removed"] + out["events_failed"] :])
    await session.execute(delete(CalendarSyncJob).where(CalendarSyncJob.connection_id == conn.id))
    await session.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
    await session.delete(conn)
    await session.flush()
    if not token:
        out["revoke"] = "unreadable" if unreadable else "none"
        if targets:
            out["events_failed"] = len(targets)
            out["errors"].append("the stored grant cannot be read: the pushed events stay")
    elif not wait:
        out["revoke"] = "queued"
        in_background(targets)
    return out


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
    owners = dict((await session.execute(select(Booking.id, Booking.user_id).where(Booking.id.in_(ids)))).all())
    user_ids = {u for u in owners.values() if u is not None}
    conns_by_user: dict[int, list[int]] = {}
    if user_ids:
        q = select(CalendarConnection.user_id, CalendarConnection.id, CalendarConnection.export_scopes).where(
            CalendarConnection.user_id.in_(user_ids), CalendarConnection.status == "ACTIVE"
        )
        for uid, cid, scopes in (await session.execute(q)).all():
            if pushes_bookings(scopes):  # CAL-06: a classes-only connection gets no booking events
                conns_by_user.setdefault(uid, []).append(cid)
    linked: dict[int, set[int]] = {}
    q2 = select(CalendarEventLink.booking_id, CalendarEventLink.connection_id).where(
        CalendarEventLink.booking_id.in_(ids)
    )
    for bid, cid in (await session.execute(q2)).all():
        if bid is not None:
            linked.setdefault(int(bid), set()).add(cid)
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


def pushes_bookings(scopes: Any) -> bool:
    return scopes is None or "my_bookings" in scopes


#: CAL-13: pushed through the class reconcile too (``class:exam-…`` item keys)
UID_SCOPES = ("my_classes", "my_duties")


def class_scopes(scopes: Any) -> list[str]:
    return [str(x) for x in scopes or [] if str(x) in UID_SCOPES or str(x).startswith("department_classes:")]


async def _expand_full(session: AsyncSession, conn: CalendarConnection) -> None:
    since = await booking_svc.today(session) - timedelta(days=PUSH_PAST_DAYS)
    ids: set[int] = set()
    if pushes_bookings(conn.export_scopes):
        q = select(Booking.id).where(Booking.user_id == conn.user_id, Booking.status == BOOKED, Booking.date >= since)
        ids = set((await session.execute(q)).scalars())
    q2 = select(CalendarEventLink.booking_id).where(
        CalendarEventLink.connection_id == conn.id, CalendarEventLink.booking_id.is_not(None)
    )
    ids |= {int(b) for b in (await session.execute(q2)).scalars() if b is not None}
    for bid in sorted(ids):
        await _queue_job(session, conn.id, bid)
    has_class_links = (
        await session.execute(
            select(CalendarEventLink.id)
            .where(CalendarEventLink.connection_id == conn.id, CalendarEventLink.item_key.like("class:%"))
            .limit(1)
        )
    ).first() is not None
    if class_scopes(conn.export_scopes) or has_class_links:
        await _queue_job(session, conn.id, None, "classes")


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
        link = CalendarEventLink(
            connection_id=conn.id, booking_id=b.id, item_key=f"booking:{b.id}", calendar_id=target_calendar or ""
        )
        session.add(link)
    link.external_id, link.fingerprint, link.synced_at = external_id, view.fingerprint, utcnow()
    link.calendar_id = target_calendar or ""


#: the owner deleted SmartSched's calendar twice (the nightly repair recreated it once): the panel asks the user
CAL_DELETED = "CAL_DELETED"


async def ensure_calendar(session: AsyncSession, api: Api, conn: CalendarConnection, tz_name: str) -> str:
    """The dedicated "SmartSched – Derslerim" calendar of an owned connection, created on first use."""
    if conn.calendar_id:
        return conn.calendar_id
    cal_id = await api.provider.create_calendar(api, Provider.OWNED_NAME, tz_name)
    conn.calendar_id, conn.calendar_name, conn.updated_at = cal_id, Provider.OWNED_NAME, utcnow()
    await session.flush()
    return cal_id


async def desired_classes(session: AsyncSession, conn: CalendarConnection) -> dict[str, ClassItem]:
    """``uid -> ClassItem`` of the connection's class scopes, as the person may see them now (the department rule is
    re-checked; a scope the person lost pushes nothing, so its events are deleted)."""
    from app.services import calendar_classes as cc
    from app.services.bookings_perms import load_access

    scopes = class_scopes(conn.export_scopes)
    user = await session.get(User, conn.user_id)
    if not scopes or user is None or not user.is_active:
        return {}
    access = await load_access(session, user)
    own = await cc.linked_instructor_ids(session, user.id)
    filters: list[cc.ScopeFilter] = []
    duties = False
    for scope in scopes:
        if scope == "my_duties":
            duties = bool(own)
            continue
        if scope == "my_classes":
            if own:
                filters.append(cc.ScopeFilter(instructor_ids=frozenset(own)))
            continue
        raw = scope.split(":", 1)[1]
        if raw.isdigit() and await cc.department_allowed(session, access, int(raw)):
            filters.append(cc.ScopeFilter(program_id=int(raw)))
    if not filters and not duties:
        return {}
    today = await booking_svc.today(session)
    since, horizon = today - timedelta(days=PUSH_PAST_DAYS), await cc.horizon_end(session, today)
    snaps = await cc.snapshots(session, since, horizon) if filters else []
    base, _ = await feeds.public_base(session)
    ctx = cc.EventContext(fields=await cc.fields_setting(session), own_instructor_ids=frozenset(own), base_url=base)
    out: dict[str, ClassItem] = {}
    if duties:  # CAL-13 "Sınav görevlerim"
        from app.services import calendar_duties as cd

        dctx = cd.duty_context(ctx)
        dsel = await cd.select_duties(session, frozenset(own), since, cd.horizon(today), grace_days=0)
        for o, _rev in dsel.live:
            desc = cc.description(o, dctx)
            fp = hashlib.sha256(f"{o.fingerprint}|{desc or ''}".encode()).hexdigest()
            out[o.uid] = ClassItem(o.uid, o.start, o.end, o.summary(), o.location, desc, fp)
    for flt in filters:
        sel = await cc.select_classes(session, flt, since, horizon, grace_days=0, snaps=snaps)
        for o, _rev in sel.live:
            if o.uid in out:
                continue
            desc = cc.description(o, ctx)
            fp = hashlib.sha256(f"{o.fingerprint}|{desc or ''}".encode()).hexdigest()
            out[o.uid] = ClassItem(o.uid, o.start, o.end, o.summary(), o.location, desc, fp)
    return out


async def _reconcile_classes(
    session: AsyncSession, api: Api, conn: CalendarConnection, job: CalendarSyncJob, tz_name: str
) -> dict[str, int]:
    """CAL-06: make the owned calendar match the class scopes -- insert what is missing (deterministic Google id /
    Graph ``transactionId``), PATCH what changed, DELETE what left the published plan or the scopes. State-based and
    idempotent: a retried job finds the links it already wrote."""
    provider = api.provider
    want = await desired_classes(session, conn)
    links = {
        link.item_key: link
        for link in (
            await session.execute(
                select(CalendarEventLink).where(
                    CalendarEventLink.connection_id == conn.id, CalendarEventLink.item_key.like("class:%")
                )
            )
        ).scalars()
        if link.item_key
    }
    counts = {"inserted": 0, "updated": 0, "deleted": 0}
    target = conn.calendar_id if conn.owned_calendar else (conn.calendar_id or provider.default_calendar)
    ctx = PushContext(connection_id=conn.id, job_id=job.id, tz_name=tz_name)
    for uid, item in sorted(want.items(), key=lambda kv: (kv[1].start, kv[0])):
        key = f"class:{uid}"
        link = links.pop(key, None)
        if link is not None and link.fingerprint == item.fingerprint and (link.calendar_id or None) == (target or None):
            continue
        if link is not None and (link.calendar_id or None) != (target or None):
            await provider.delete(api, link.calendar_id or None, link.external_id)
            await session.delete(link)
            await session.flush()
            link = None
        external_id = await provider.upsert_class(api, target or "", link.external_id if link else None, item, ctx)
        if link is None:
            link = CalendarEventLink(connection_id=conn.id, booking_id=None, item_key=key, calendar_id=target or "")
            session.add(link)
            counts["inserted"] += 1
        else:
            counts["updated"] += 1
        link.external_id, link.fingerprint, link.synced_at = external_id, item.fingerprint, utcnow()
        link.calendar_id = target or ""
        await session.flush()
    for link in links.values():
        await provider.delete(api, link.calendar_id or None, link.external_id)
        await session.delete(link)
        counts["deleted"] += 1
    await session.flush()
    return counts


async def _nightly(
    session: AsyncSession, api: Api, conn: CalendarConnection, job: CalendarSyncJob, tz_name: str
) -> None:
    """CAL-06 nightly repair (03:30 Istanbul) of an owned calendar: events the user deleted are re-created, events
    the user edited are overwritten, strays are removed; a deleted calendar is re-created once, after that the
    connection waits for the user (status ``CAL_DELETED``)."""
    provider = api.provider
    if not conn.owned_calendar or not conn.calendar_id:
        await _reconcile_classes(session, api, conn, job, tz_name)
        return
    remote = await provider.list_owned(api, conn.calendar_id)
    now = utcnow()
    if remote is None:
        await session.execute(delete(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
        if conn.calendar_recreated_at is not None:
            conn.status = CAL_DELETED
            conn.last_error = "SmartSched takvimi silinmiş. Yeniden eklemek için bağlantıyı yenileyin."
            conn.calendar_id = None
            return
        conn.calendar_id, conn.calendar_recreated_at = None, now
        await ensure_calendar(session, api, conn, tz_name)
        await _queue_job(session, conn.id, None, "full")
    else:
        links = list(
            (
                await session.execute(select(CalendarEventLink).where(CalendarEventLink.connection_id == conn.id))
            ).scalars()
        )
        known = {link.external_id for link in links}
        for link in links:
            changed = remote.get(link.external_id, "missing")
            if changed == "missing":
                await session.delete(link)  # deleted by the user: the diff below re-creates it
            elif isinstance(changed, datetime) and link.synced_at and changed > link.synced_at + timedelta(seconds=5):
                link.fingerprint = None  # edited by the user: the diff below overwrites it
        for external_id in sorted(set(remote) - known):
            await provider.delete(api, conn.calendar_id, external_id)  # a stray SmartSched event
        await session.flush()
        if pushes_bookings(conn.export_scopes):
            await _queue_job(session, conn.id, None, "full")
    await _reconcile_classes(session, api, conn, job, tz_name)
    conn.last_reconciled_at = now


def check_export_scopes(raw: list[str]) -> list[tuple[str, int | None]]:
    """``["my_classes", "department_classes:12", "my_bookings"]`` -> ``[(kind, id)]``; ``ValueError`` otherwise."""
    out: list[tuple[str, int | None]] = []
    for item in raw:
        text = str(item).strip()
        kind, _, ident = text.partition(":")
        if kind in ("my_classes", "my_bookings", "my_duties") and not ident:
            out.append((kind, None))
        elif kind == "department_classes" and ident.isdigit():
            out.append((kind, int(ident)))
        else:
            raise ValueError(
                f"unknown push scope {text!r}: my_classes, my_bookings, my_duties or department_classes:<id>"
            )
    if not out:
        raise ValueError("at least one scope")
    return list(dict.fromkeys(out))


def scope_strings(scopes: list[tuple[str, int | None]]) -> list[str]:
    return [k if i is None else f"{k}:{i}" for k, i in scopes]


async def queue_classes(
    session: AsyncSession,
    *,
    user_ids: set[int] | None = None,
    programs: set[int] | None = None,
    duties_only: bool = False,
) -> int:
    """One ``classes`` job per affected connection (diff-based, so a re-publish of 600 classes is one job per
    connection): every connection with a class scope, or only those of ``user_ids`` (my_classes) and ``programs``
    (department_classes:<id>) when the change is known to be narrower. ``duties_only`` (CAL-13): only the
    connections that push ``my_duties`` (an invigilation plan was published or edited)."""
    if not await feeds.sync_enabled(session):
        return 0
    q = select(CalendarConnection).where(CalendarConnection.status == "ACTIVE")
    added = 0
    for conn in (await session.execute(q)).scalars():
        scopes = class_scopes(conn.export_scopes)
        if not scopes or (duties_only and "my_duties" not in scopes):
            continue
        if user_ids is not None or programs is not None:
            mine = ("my_duties" if duties_only else "my_classes") in scopes and conn.user_id in (user_ids or set())
            dep = any(s.split(":", 1)[1] in {str(p) for p in programs or set()} for s in scopes if ":" in s)
            if not (mine or dep):
                continue
        added += int(await _queue_job(session, conn.id, None, "classes"))
    if added:
        worker.kick_after_commit(session)
    return added


async def queue_nightly(session: AsyncSession) -> int:
    """The nightly repair: one ``nightly`` job per active connection with an owned calendar or class scopes."""
    if not await feeds.sync_enabled(session):
        return 0
    added = 0
    q = select(CalendarConnection).where(CalendarConnection.status == "ACTIVE")
    for conn in (await session.execute(q)).scalars():
        if conn.owned_calendar or class_scopes(conn.export_scopes):
            added += int(await _queue_job(session, conn.id, None, "nightly"))
    return added


async def set_export_scopes(session: AsyncSession, conn: CalendarConnection, scopes: list[str]) -> list[str]:
    """``PUT /calendar/connectors/{provider}/scopes`` after the approval step; queues a full reconcile."""
    before = list(conn.export_scopes or ["my_bookings"])
    conn.export_scopes, conn.updated_at = list(scopes), utcnow()
    await session.flush()
    await queue_full_sync(session, conn)
    return before


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
    if conn.status == CAL_DELETED:
        return skip("the SmartSched calendar was deleted by its owner")
    if job.kind == "full":
        await _expand_full(session, conn)
        job.status, job.done_at, job.last_error = DONE, now, None
        return
    tz_name = str(await settings_service.get_value(session, "timezone") or "Europe/Istanbul")
    api = Api(conn, provider, cfg, client)
    job.attempts += 1
    try:
        if conn.owned_calendar:
            await ensure_calendar(session, api, conn, tz_name)
        if job.kind == "classes":
            await _reconcile_classes(session, api, conn, job, tz_name)
        elif job.kind == "nightly":
            await _nightly(session, api, conn, job, tz_name)
        else:
            await _reconcile(session, api, conn, job, tz_name)
    except ProviderError as exc:
        job.last_error = exc.public
        conn.last_error = exc.public
        if exc.reauth:
            conn.status = "REAUTH"
            job.status, job.done_at = FAILED, now
            return
        retry_at = worker.next_attempt(job.attempts, now) if exc.retryable else None
        if retry_at is not None and exc.retry_after:  # 429 / 503: never earlier than the provider asked
            retry_at = max(retry_at, now + timedelta(seconds=exc.retry_after))
        if retry_at is None:
            job.status, job.done_at = FAILED, now
        else:
            job.status, job.next_attempt_at, job.locked_until = PENDING, retry_at, None
        return
    job.status, job.done_at, job.last_error = DONE, now, None
    if conn.status != CAL_DELETED:
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
                ).all()
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


#: Google scopes broader than SmartSched needs (every calendar of the account): flagged, never forced to reconnect
BROAD_GOOGLE_SCOPES = ("https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar ")


def least_privilege(conn: CalendarConnection) -> bool:
    """Owner decision 2026-10-17 (6): a Google grant on every calendar (``calendar.events``) is flagged "Daha az
    izinle yeniden bağlan"; Microsoft's ``Calendars.ReadWrite`` is already the least Graph offers."""
    if conn.provider != "google":
        return True
    granted = f"{conn.scopes or ''} "
    return not any(s in granted for s in BROAD_GOOGLE_SCOPES)


async def push_out(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    """The person's push connections for ``GET /calendar/subscriptions`` (CAL-06/07; ``connectors_out`` keeps its
    shape for W3-HUB)."""
    out: list[dict[str, Any]] = []
    for p in PROVIDERS.values():
        conn = await get_connection(session, user.id, p.name)
        if conn is None:
            continue
        lean = least_privilege(conn)
        out.append(
            {
                "channel": f"push:{p.name}",
                "provider": p.name,
                "label": p.label,
                "status": conn.status,
                "export_scopes": list(conn.export_scopes or ["my_bookings"]),
                "owned_calendar": bool(conn.owned_calendar),
                "calendar_name": conn.calendar_name,
                "account_email": conn.account_email,
                "account_verified": conn.account_verified,
                "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
                "last_reconciled_at": conn.last_reconciled_at.isoformat() if conn.last_reconciled_at else None,
                "least_privilege": lean,
                "reconnect_tr": None if lean else "Daha az izinle yeniden bağlan",
                "reconnect_en": None if lean else "Reconnect with fewer permissions",
            }
        )
    return out
