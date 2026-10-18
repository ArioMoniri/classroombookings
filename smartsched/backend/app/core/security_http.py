"""HTTP-level hardening (wave 3 W3-SEC, docs/SECURITY.md §5): request rate limits, a body-size fence and the
security headers of the API's own responses. One pure ASGI middleware (SSE streams pass through untouched).

Rate limits (in-process sliding windows, :class:`app.core.throttle.Throttle`; per worker like the login limiter):

* per **user** (the ``uid`` of a valid bearer token) for the AI routes, the uploads and the own password change;
* per **client address** for the unauthenticated sign-in / reset / SSO exchange routes and as a ceiling on the AI
  and upload routes. The client address is the TCP peer, or, when the peer is a trusted proxy hop
  (``FORWARDED_ALLOW_IPS``: loopback and the Docker bridge range 172.16.0.0/12 by default), the rightmost
  ``X-Forwarded-For`` entry that is not a hop (:func:`client_address`; nginx -> the Next.js route handler -> here).
  A hop that forwards nothing is not limited per address; the per-account limits still apply behind it.

Over a limit the answer is 429 ``{code: rate_limited, message, message_en, message_tr, retry_after}`` with a
``Retry-After`` header. The test environment does not enforce them unless :data:`LIMITS` ``.enforce_in_tests`` is set
(the suites reuse user ids across tests; tests/test_w3_sec_hardening.py switches it on).
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.throttle import Throttle

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

API = "/api/v1"


@dataclass
class Rule:
    """``methods`` + ``path`` (regex on the path below ``/api/v1``) → per-user and / or per-address windows."""

    name: str
    methods: frozenset[str]
    path: re.Pattern[str]
    per_user: Throttle | None = None
    per_address: Throttle | None = None

    def matches(self, method: str, sub: str) -> bool:
        return method in self.methods and bool(self.path.match(sub))


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern + r"/?$")


WRITE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
POST = frozenset({"POST"})

#: AI routes: anything that may call a model (chat edits, explanations, AI intake, the W3-AI gateway's own routes)
AI_PATHS = (
    r"/runs/\d+/chat(/stream|/apply)?",
    r"/runs/\d+/explain",
    r"/runs/\d+/assignments/\d+/explain",
    r"/terms/\d+/preferences/upload",
    r"/terms/\d+/studio/(proposals|preferences)(/[a-z_-]+)?",
    r"/ai/[a-z0-9/_-]+",
    r"/council/jobs(/\d+/rerun)?",
)
#: uploads: every multipart intake
UPLOAD_PATHS = (
    r"/imports/[a-z-]+",
    r"/rooms/\d+/photo",
    r"/room-admin/rooms/\d+/photo",
    r"/users/import",
    r"/org/logo",
    r"/council/jobs",
)


@dataclass
class Limits:
    enforce_in_tests: bool = False
    rules: list[Rule] = field(default_factory=list)

    def reset(self) -> None:
        for r in self.rules:
            for t in (r.per_user, r.per_address):
                if t is not None:
                    t.reset()


def _default_rules() -> list[Rule]:
    return [
        Rule("login", POST, _rx(r"/auth/login"), per_address=Throttle(300, 60)),
        Rule("reset_confirm", POST, _rx(r"/auth/password-reset/confirm"), per_address=Throttle(900, 20)),
        Rule("sso_exchange", POST, _rx(r"/auth/sso/exchange"), per_address=Throttle(300, 60)),
        Rule("change_password", POST, _rx(r"/auth/change-password"), per_user=Throttle(900, 10)),
        # AU-B two-step sign-in (docs/research/2026-10-18-auth-backend.md §6): the second step, passkey-only sign-in
        # and the enrolment the policy forces are unauthenticated; the per-account lockout lives in app/services/mfa.py
        Rule(
            "mfa_verify", POST, _rx(r"/auth/mfa/(verify|passkey/options|passkey/verify)"), per_address=Throttle(300, 30)
        ),
        Rule("passkey_sign_in", POST, _rx(r"/auth/passkey/(options|verify)"), per_address=Throttle(300, 60)),
        Rule("mfa_setup", POST, _rx(r"/auth/mfa/setup/[a-z]+/[a-z]+"), per_address=Throttle(300, 30)),
        Rule(
            "mfa_reauth",
            POST,
            _rx(r"/auth/(mfa/(totp/start|disable|recovery-codes)|passkeys/(register/options|\d+/remove))"),
            per_user=Throttle(900, 10),
        ),
        Rule(
            "ai",
            WRITE,
            _rx("(" + "|".join(AI_PATHS) + ")"),
            per_user=Throttle(60, 20),
            per_address=Throttle(60, 120),
        ),
        Rule(
            "upload",
            POST,
            _rx("(" + "|".join(UPLOAD_PATHS) + ")"),
            per_user=Throttle(600, 30),
            per_address=Throttle(600, 120),
        ),
    ]


LIMITS = Limits(rules=_default_rules())

_NETS_CACHE: dict[str, tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] = {}


def _proxy_nets() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """The trusted proxy hops (``FORWARDED_ALLOW_IPS``; default loopback + 172.16.0.0/12, the Docker bridge range)."""
    raw = get_settings().forwarded_allow_ips
    nets = _NETS_CACHE.get(raw)
    if nets is None:
        parsed = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                parsed.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                continue  # a malformed entry trusts nothing
        nets = _NETS_CACHE[raw] = tuple(parsed)
    return nets


def is_proxy_hop(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True  # "testclient", "?" ...: not a client address
    return any(ip in net for net in _proxy_nets())


def _valid_ip(value: str) -> str | None:
    host = value.strip()
    if host.startswith("[") and "]" in host:  # [v6]:port
        host = host[1 : host.index("]")]
    elif host.count(":") == 1:  # v4:port
        host = host.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def client_address(scope: Scope) -> str:
    """The client's address: the TCP peer, or, when the peer is a trusted proxy hop (nginx, the Next.js route
    handler), the rightmost ``X-Forwarded-For`` entry that is not itself a hop. A browser that writes the header
    is not believed (its peer address is not a hop). F3: without this every browser shared the frontend's address.
    """
    client = scope.get("client")
    peer = str(client[0]) if client else "?"
    if not is_proxy_hop(peer):
        return peer
    values = [v.decode("latin-1") for k, v in scope.get("headers") or () if k == b"x-forwarded-for"]
    if not values:
        return peer
    chain = [h for h in (_valid_ip(p) for p in ",".join(values).split(",")) if h]
    if not chain:
        return peer
    for host in reversed(chain):
        if not is_proxy_hop(host):
            return host
    return chain[0]


def _uid(scope: Scope) -> int | None:
    """The ``uid`` of a *valid* bearer token (signature and expiry checked; revocation is the route's job)."""
    for k, v in scope.get("headers") or ():
        if k == b"authorization":
            raw = v.decode("latin-1")
            if not raw.lower().startswith("bearer "):
                return None
            from app.core.security import decode_access_token

            try:
                uid = decode_access_token(raw[7:].strip()).get("uid")
                return int(uid) if uid else None
            except Exception:
                return None
    return None


def _header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers") or ():
        if k == name:
            return str(v.decode("latin-1"))
    return None


def check(method: str, path: str, address: str, uid: int | None) -> tuple[str, int] | None:
    """``(rule name, retry after s)`` when the request is over a limit (and records it otherwise)."""
    if not path.startswith(API):
        return None
    sub = path[len(API) :] or "/"
    for rule in LIMITS.rules:
        if not rule.matches(method, sub):
            continue
        keys: list[tuple[Throttle, str]] = []
        if rule.per_user is not None and uid is not None:
            keys.append((rule.per_user, f"u:{uid}"))
        if rule.per_address is not None and not is_proxy_hop(address):
            keys.append((rule.per_address, f"ip:{address}"))
        for t, key in keys:
            if t.blocked(key):
                return rule.name, max(1, t.retry_after(key))
        for t, key in keys:
            t.hit(key)
    return None


def _limit_body(rule: str, retry: int) -> bytes:
    mins = max(1, (retry + 59) // 60)
    return json.dumps(
        {
            "detail": {
                "code": "rate_limited",
                "limit": rule,
                "retry_after": retry,
                "message": "too many requests; try again later",
                "message_en": f"Too many requests. Try again in {mins} minute(s).",
                "message_tr": f"Çok fazla istek gönderildi. {mins} dakika sonra yeniden deneyin.",
            }
        },
        ensure_ascii=False,
    ).encode("utf-8")


#: headers on every API response the backend answers itself (nginx adds the page CSP / HSTS / frame rules)
API_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-frame-options", b"DENY"),
)


def max_body_bytes() -> int:
    s = get_settings()
    return int(max(float(s.upload_max_mb), float(s.council_max_job_mb)) * 1024 * 1024) + 1024 * 1024


class SecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        length = _header(scope, b"content-length")
        if length and length.isdigit() and int(length) > max_body_bytes():
            await _answer(
                send,
                413,
                json.dumps(
                    {
                        "detail": {
                            "code": "too_large",
                            "message": "request body too large",
                            "message_en": "The upload is too large.",
                            "message_tr": "Yüklenen dosya çok büyük.",
                        }
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            return
        client = scope.get("client")
        address = client_address(scope)
        if client and address != client[0]:
            # every later reader (the login failure cap in app.core.ratelimit, the audit's client network) sees
            # the browser, not the proxy hop
            scope["client"] = (address, client[1] if len(client) > 1 else 0)
        settings = get_settings()
        if settings.environment != "test" or LIMITS.enforce_in_tests:
            hit = check(method, path, address, _uid(scope))
            if hit is not None:
                rule, retry = hit
                await _answer(send, 429, _limit_body(rule, retry), [(b"retry-after", str(retry).encode())])
                return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start" and path.startswith("/api/"):
                have = {k.lower() for k, _ in message.get("headers") or ()}
                extra = [(k, v) for k, v in API_HEADERS if k not in have]
                if extra:
                    message["headers"] = list(message.get("headers") or ()) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def _answer(send: Send, status: int, body: bytes, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
                *API_HEADERS,
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = ["LIMITS", "Rule", "SecurityMiddleware", "check", "client_address", "is_proxy_hop", "max_body_bytes"]
