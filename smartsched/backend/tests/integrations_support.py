"""Test-only provider doubles for the calendar connectors and webhook receivers, on ``httpx.MockTransport``.

The response bodies are shaped like the real Google OAuth / Calendar API v3 and Microsoft identity platform /
Graph v1.0 answers (field names, error envelopes, status codes), trimmed to what the connectors read. Nothing here
is imported by application code."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_API = "https://www.googleapis.com/calendar/v3"
GRAPH = "https://graph.microsoft.com/v1.0"


def challenge_of(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def google_error(code: int, reason: str, message: str) -> httpx.Response:
    return httpx.Response(
        code,
        json={
            "error": {
                "errors": [{"domain": "global", "reason": reason, "message": message}],
                "code": code,
                "message": message,
            }
        },
    )


@dataclass
class FakeProvider:
    """Records every request; ``fail_next`` = list of (method, url-substring, response) consumed first."""

    challenge: str | None = None
    codes: dict[str, str] = field(default_factory=dict)  # code -> expected challenge
    events: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)  # (calendar, id) -> body
    requests: list[httpx.Request] = field(default_factory=list)
    fail_next: list[tuple[str, str, httpx.Response]] = field(default_factory=list)
    access_tokens: set[str] = field(default_factory=set)
    refresh_ok: bool = True
    serial: int = 0

    def calls(self, method: str, contains: str = "") -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and contains in str(r.url)]

    def form(self, req: httpx.Request) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(req.content.decode()).items()}

    def body(self, req: httpx.Request) -> dict[str, Any]:
        return json.loads(req.content.decode() or "{}")

    def _new_access(self) -> str:
        self.serial += 1
        token = f"ya29.a0AfB_byTest{self.serial:04d}"
        self.access_tokens.add(token)
        return token

    def _authorised(self, req: httpx.Request) -> bool:
        return req.headers.get("authorization", "").removeprefix("Bearer ") in self.access_tokens

    async def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        for i, (method, part, resp) in enumerate(self.fail_next):
            if req.method == method and part in str(req.url):
                del self.fail_next[i]
                return resp
        return self.handle(req)

    def handle(self, req: httpx.Request) -> httpx.Response:  # pragma: no cover - overridden
        raise NotImplementedError


class FakeGoogle(FakeProvider):
    def handle(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url == GOOGLE_TOKEN:
            f = self.form(req)
            if f.get("grant_type") == "authorization_code":
                expected = self.codes.pop(f.get("code", ""), None)
                if expected is None or challenge_of(f.get("code_verifier", "")) != expected:
                    return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Bad Request"})
                return httpx.Response(
                    200,
                    json={
                        "access_token": self._new_access(),
                        "expires_in": 3599,
                        "refresh_token": "1//0gLkXtestRefreshTokenGoogle",
                        "scope": "openid https://www.googleapis.com/auth/calendar.events "
                        "https://www.googleapis.com/auth/userinfo.email "
                        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                        "token_type": "Bearer",
                        "id_token": "eyJhbGciOiJSUzI1NiJ9.e30.sig",
                    },
                )
            if f.get("grant_type") == "refresh_token":
                if not self.refresh_ok:
                    return httpx.Response(
                        400, json={"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
                    )
                return httpx.Response(
                    200,
                    json={
                        "access_token": self._new_access(),
                        "expires_in": 3599,
                        "scope": "https://www.googleapis.com/auth/calendar.events",
                        "token_type": "Bearer",
                    },
                )
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            return httpx.Response(200, json={})
        if not self._authorised(req):
            return google_error(401, "authError", "Invalid Credentials")
        if url == "https://openidconnect.googleapis.com/v1/userinfo":
            return httpx.Response(
                200, json={"sub": "110248495921238986420", "email": "ayse.yilmaz@uni.edu.tr", "email_verified": True}
            )
        if url.startswith(f"{GOOGLE_API}/users/me/calendarList"):
            return httpx.Response(
                200,
                json={
                    "kind": "calendar#calendarList",
                    "etag": '"p32g9nb5bt6fva0g"',
                    "items": [
                        {
                            "kind": "calendar#calendarListEntry",
                            "id": "ayse.yilmaz@uni.edu.tr",
                            "summary": "ayse.yilmaz@uni.edu.tr",
                            "timeZone": "Europe/Istanbul",
                            "accessRole": "owner",
                            "primary": True,
                        },
                        {
                            "kind": "calendar#calendarListEntry",
                            "id": "c_8f1e2d@group.calendar.google.com",
                            "summary": "Dersler",
                            "summaryOverride": "Derslik rezervasyonları",
                            "accessRole": "owner",
                        },
                    ],
                },
            )
        prefix = f"{GOOGLE_API}/calendars/"
        if url.startswith(prefix):
            rest = urlsplit(url).path.removeprefix("/calendar/v3/calendars/")
            parts = rest.split("/")
            calendar = unquote(parts[0])
            event_id = unquote(parts[2]) if len(parts) > 2 else None
            if req.method == "POST" and event_id is None:
                body = self.body(req)
                key = (calendar, body["id"])
                if key in self.events:
                    return google_error(409, "duplicate", "The requested identifier already exists.")
                self.events[key] = body
                return httpx.Response(200, json=self._event(body, body["id"]))
            assert event_id is not None
            key = (calendar, event_id)
            if req.method == "PUT":
                if key not in self.events:
                    return google_error(404, "notFound", "Not Found")
                self.events[key] = {**self.body(req), "id": event_id}
                return httpx.Response(200, json=self._event(self.events[key], event_id))
            if req.method == "DELETE":
                if self.events.pop(key, None) is None:
                    return google_error(410, "deleted", "Resource has been deleted")
                return httpx.Response(204)
        return google_error(404, "notFound", "Not Found")

    @staticmethod
    def _event(body: dict[str, Any], event_id: str) -> dict[str, Any]:
        return {
            "kind": "calendar#event",
            "etag": '"3417829345278000"',
            "id": event_id,
            "status": "confirmed",
            "htmlLink": f"https://www.google.com/calendar/event?eid={event_id}",
            "iCalUID": f"{event_id}@google.com",
            "sequence": 0,
            "summary": body.get("summary"),
            "start": body.get("start"),
            "end": body.get("end"),
            "reminders": {"useDefault": True},
            "eventType": "default",
        }


class FakeGraph(FakeProvider):
    def handle(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.startswith("https://login.microsoftonline.com/") and url.endswith("/oauth2/v2.0/token"):
            f = self.form(req)
            if f.get("grant_type") == "authorization_code":
                expected = self.codes.pop(f.get("code", ""), None)
                if expected is None or challenge_of(f.get("code_verifier", "")) != expected:
                    return httpx.Response(
                        400,
                        json={
                            "error": "invalid_grant",
                            "error_description": "AADSTS54005: OAuth2 Authorization code was already redeemed.",
                        },
                    )
            elif f.get("grant_type") == "refresh_token" and not self.refresh_ok:
                return httpx.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_codes": [70000],
                        "error_description": "AADSTS70000: The provided value for the 'refresh_token' is not valid.",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "token_type": "Bearer",
                    "scope": "Calendars.ReadWrite User.Read profile openid email",
                    # 60 s: the connector stores it as already expiring, so the first API call refreshes
                    "expires_in": 60,
                    "ext_expires_in": 60,
                    "access_token": self._new_access(),
                    "refresh_token": f"0.AXkA-refresh-{self.serial}",
                },
            )
        if not self._authorised(req):
            return httpx.Response(
                401,
                json={
                    "error": {
                        "code": "InvalidAuthenticationToken",
                        "message": "Access token has expired or is not yet valid.",
                    }
                },
            )
        path = urlsplit(url).path.removeprefix("/v1.0")
        if path == "/me":
            return httpx.Response(
                200,
                json={
                    "@odata.context": f"{GRAPH}/$metadata#users(id,mail,userPrincipalName)/$entity",
                    "id": "87d349ed-44d7-43e1-9a83-5f2406dee5bd",
                    "mail": None,
                    "userPrincipalName": "mehmet.kaya@uni.edu.tr",
                },
            )
        if path == "/me/calendars":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "AAMkAGViNDU7zAAAAAAEGAAA=",
                            "name": "Calendar",
                            "isDefaultCalendar": True,
                            "canEdit": True,
                        },
                        {
                            "id": "AAMkAGViNDU7zAAAAAAEHBBB=",
                            "name": "Rezervasyonlar",
                            "isDefaultCalendar": False,
                            "canEdit": True,
                        },
                    ]
                },
            )
        if req.method == "POST" and path.endswith("/events"):
            body = self.body(req)
            self.serial += 1
            event_id = f"AAMkAGIAAAoZDOFAAA{self.serial:03d}="
            calendar = path.split("/")[3] if path.startswith("/me/calendars/") else "default"
            self.events[(calendar, event_id)] = body
            return httpx.Response(
                201,
                json={
                    "@odata.etag": 'W/"ZlnW4RIAV06KYYwlrfNZvQAAKGWwbw=="',
                    "id": event_id,
                    "subject": body.get("subject"),
                    "start": body.get("start"),
                    "end": body.get("end"),
                    "transactionId": body.get("transactionId"),
                },
            )
        if path.startswith("/me/events/"):
            event_id = unquote(path.removeprefix("/me/events/"))
            key = next((k for k in self.events if k[1] == event_id), None)
            if key is None:
                return httpx.Response(
                    404,
                    json={
                        "error": {
                            "code": "ErrorItemNotFound",
                            "message": "The specified object was not found in the store.",
                        }
                    },
                )
            if req.method == "PATCH":
                self.events[key] = {**self.events[key], **self.body(req)}
                return httpx.Response(200, json={"id": event_id, **self.events[key]})
            if req.method == "DELETE":
                del self.events[key]
                return httpx.Response(204)
        return httpx.Response(404, json={"error": {"code": "ResourceNotFound", "message": "Resource not found."}})


@dataclass
class Receiver:
    """A webhook receiver: answers ``statuses`` in order (then 200) and records what it got."""

    statuses: list[int] = field(default_factory=list)
    received: list[httpx.Request] = field(default_factory=list)
    raise_error: bool = False

    async def __call__(self, req: httpx.Request) -> httpx.Response:
        self.received.append(req)
        if self.raise_error:
            raise httpx.ConnectError("connection refused", request=req)
        status = self.statuses.pop(0) if self.statuses else 200
        return httpx.Response(status, json={"ok": status < 300})


def client_factory(handler: Any) -> Any:
    def make() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)

    return make
