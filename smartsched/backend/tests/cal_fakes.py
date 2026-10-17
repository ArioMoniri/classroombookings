"""Provider doubles for the calendar export push tests (CAL-06 / CAL-07), on ``httpx.MockTransport``.

They extend ``tests/integrations_support.FakeGoogle`` / ``FakeGraph`` with what pushing classes into a calendar
SmartSched owns needs: Google ``calendars.insert`` / ``calendars.delete``, ``events.patch`` and ``events.list`` with
``privateExtendedProperty``; Graph ``POST`` / ``DELETE /me/calendars``, listing a calendar's events, ``transactionId``
de-duplication and ``/organization``. Response shapes follow Calendar API v3 and Graph v1.0, trimmed to what the
connectors read. Nothing here is imported by application code."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from tests.integrations_support import GOOGLE_TOKEN, FakeGoogle, FakeGraph, google_error

USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
APP_CREATED = "https://www.googleapis.com/auth/calendar.app.created"


def fake_id_token(claims: dict[str, Any]) -> str:
    def part(obj: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'kid': 'test'})}.{part(claims)}.c2lnbmF0dXJl"


@dataclass
class FakeGoogleCal(FakeGoogle):
    sub: str = "110248495921238986420"
    email: str = "ayse.yilmaz@uni.edu.tr"
    hd: str | None = None
    grant_scope: str | None = None
    calendars: dict[str, str] = field(default_factory=dict)  # id -> summary
    calendar_zone: dict[str, str] = field(default_factory=dict)
    updated: dict[tuple[str, str], str] = field(default_factory=dict)
    cal_serial: int = 0

    def handle(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url == GOOGLE_TOKEN:
            resp = super().handle(req)
            data = resp.json()
            if resp.status_code == 200 and "access_token" in data:
                if self.grant_scope:
                    data["scope"] = self.grant_scope
                claims = {"sub": self.sub, "email": self.email, **({"hd": self.hd} if self.hd else {})}
                data["id_token"] = fake_id_token(claims)
            return httpx.Response(resp.status_code, json=data)
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            return super().handle(req)
        if not self._authorised(req):
            return google_error(401, "authError", "Invalid Credentials")
        if url == USERINFO:
            body = {"sub": self.sub, "email": self.email, "email_verified": True}
            return httpx.Response(200, json={**body, **({"hd": self.hd} if self.hd else {})})
        parts = urlsplit(url)
        path = parts.path.removeprefix("/calendar/v3")
        if path == "/calendars" and req.method == "POST":
            body = self.body(req)
            self.cal_serial += 1
            cid = f"c_smartsched{self.cal_serial:03d}@group.calendar.google.com"
            self.calendars[cid] = body["summary"]
            self.calendar_zone[cid] = body.get("timeZone", "")
            return httpx.Response(200, json={"kind": "calendar#calendar", "id": cid, "summary": body["summary"]})
        if path.startswith("/calendars/"):
            segs = path.removeprefix("/calendars/").split("/")
            cal = unquote(segs[0])
            if cal != "primary" and cal not in self.calendars:
                return google_error(404, "notFound", "Not Found")
            if len(segs) == 1 and req.method == "DELETE":
                del self.calendars[cal]
                for key in [k for k in self.events if k[0] == cal]:
                    del self.events[key]
                return httpx.Response(204)
            if len(segs) == 2 and req.method == "GET":
                q = {k: v[0] for k, v in parse_qs(parts.query).items()}
                want = q.get("privateExtendedProperty", "")
                items = []
                for (c, eid), ev in self.events.items():
                    priv = (ev.get("extendedProperties") or {}).get("private") or {}
                    if c == cal and (not want or f"smartsched={priv.get('smartsched')}" == want):
                        items.append({"id": eid, "updated": self.updated.get((c, eid), "2026-02-16T05:00:00.000Z")})
                return httpx.Response(200, json={"kind": "calendar#events", "items": items})
            if len(segs) == 3 and req.method == "PATCH":
                key = (cal, unquote(segs[2]))
                if key not in self.events:
                    return google_error(404, "notFound", "Not Found")
                self.events[key] = {**self.events[key], **self.body(req)}
                return httpx.Response(200, json=self._event(self.events[key], key[1]))
        return super().handle(req)


@dataclass
class FakeGraphCal(FakeGraph):
    tenant: str = "9188040d-6c67-4c5b-b112-36a304b66dad"
    upn: str = "mehmet.kaya@uni.edu.tr"
    owned: dict[str, str] = field(default_factory=dict)  # calendar id -> name
    transactions: dict[str, str] = field(default_factory=dict)  # transactionId -> event id
    cal_serial: int = 0

    def handle(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.startswith("https://login.microsoftonline.com/") or not self._authorised(req):
            return super().handle(req)
        path = urlsplit(url).path.removeprefix("/v1.0")
        if path == "/me":
            return httpx.Response(200, json={"id": "87d349ed-44d7-43e1-9a83-5f2406dee5bd", "mail": None,
                                             "userPrincipalName": self.upn})  # fmt: skip
        if path == "/organization":
            return httpx.Response(200, json={"value": [{"id": self.tenant}]})
        if path == "/me/calendars" and req.method == "POST":
            self.cal_serial += 1
            cid = f"AAMkADSmartSched{self.cal_serial:03d}="
            self.owned[cid] = self.body(req)["name"]
            return httpx.Response(201, json={"id": cid, "name": self.owned[cid], "canEdit": True})
        if path.startswith("/me/calendars/"):
            segs = path.removeprefix("/me/calendars/").split("/")
            cal = unquote(segs[0])
            if cal not in self.owned:
                return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound", "message": "Not found."}})
            if len(segs) == 1 and req.method == "DELETE":
                del self.owned[cal]
                for key in [k for k in self.events if k[0] == cal]:
                    del self.events[key]
                return httpx.Response(204)
            if len(segs) == 2 and req.method == "GET":
                items = [
                    {"id": eid, "lastModifiedDateTime": "2026-02-16T05:00:00Z"} for c, eid in self.events if c == cal
                ]
                return httpx.Response(200, json={"value": items})
            if len(segs) == 2 and req.method == "POST":
                tid = self.body(req).get("transactionId")
                if tid and tid in self.transactions:  # Graph: the same transactionId does not create a second event
                    eid = self.transactions[tid]
                    return httpx.Response(201, json={"id": eid, **self.events[(cal, eid)]})
                body = self.body(req)
                self.serial += 1
                eid = f"AAMkAGIAAAoZDOFAAA{self.serial:03d}="
                self.events[(cal, eid)] = body
                if tid:
                    self.transactions[tid] = eid
                return httpx.Response(201, json={"id": eid, "subject": body.get("subject")})
        return super().handle(req)
