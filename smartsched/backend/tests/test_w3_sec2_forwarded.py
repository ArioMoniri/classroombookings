"""Security follow-up (wave3-sec2, docs/SECURITY.md F3 / F8): the real client address behind the proxies.

nginx sends ``X-Forwarded-For: $remote_addr`` to the Next.js route handler, which forwards it to FastAPI. The backend
believes that header only when the TCP peer is a proxy hop (loopback, the compose bridge range): the per-address
sign-in caps then count the browser's address, not the frontend container's. uvicorn in the image trusts the same
hops (``FORWARDED_ALLOW_IPS``) instead of ``'*'``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.core import security_http as sh
from app.core.throttle import Throttle
from httpx import ASGITransport, AsyncClient

from tests.api_fixtures import client  # noqa: F401

BACKEND = Path(__file__).resolve().parent.parent
DEPLOY = BACKEND.parent / "deploy"
ENTRYPOINT = (BACKEND / "docker-entrypoint.sh").read_text(encoding="utf-8")
COMPOSE = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
LOGIN = {"email": "admin@example.com", "password": "admin1234"}


@pytest.fixture
def limits(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sh.LIMITS, "enforce_in_tests", True)
    sh.LIMITS.reset()
    yield sh.LIMITS
    sh.LIMITS.reset()


def _rule(name: str) -> sh.Rule:
    return next(r for r in sh.LIMITS.rules if r.name == name)


def _client(peer: str) -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app, client=(peer, 41000)), base_url="http://test")


def test_forwarded_address_is_read_only_from_a_proxy_hop() -> None:
    hop = [(b"x-forwarded-for", b"203.0.113.9")]
    assert sh.client_address({"client": ("172.18.0.4", 5), "headers": hop}) == "203.0.113.9"
    assert sh.client_address({"client": ("127.0.0.1", 5), "headers": hop}) == "203.0.113.9"
    # a browser that writes the header itself is not believed
    assert sh.client_address({"client": ("198.51.100.7", 5), "headers": hop}) == "198.51.100.7"
    # the rightmost address that is not a hop wins (a chain the client prefixed is ignored)
    chain = [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.9, 172.18.0.9")]
    assert sh.client_address({"client": ("172.18.0.4", 5), "headers": chain}) == "203.0.113.9"
    # garbage in the header falls back to the peer
    junk = [(b"x-forwarded-for", b"not-an-ip")]
    assert sh.client_address({"client": ("172.18.0.4", 5), "headers": junk}) == "172.18.0.4"
    # no header: the peer
    assert sh.client_address({"client": ("172.18.0.4", 5), "headers": []}) == "172.18.0.4"


async def test_sign_in_cap_counts_the_browser_behind_the_frontend_hop(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    """Before: every browser shared the frontend container's address (and was never limited per address)."""
    monkeypatch.setattr(_rule("login"), "per_address", Throttle(300, 2))
    async with _client("172.18.0.4") as c:
        for _ in range(2):
            r = await c.post("/api/v1/auth/login", json=LOGIN, headers={"x-forwarded-for": "203.0.113.9"})
            assert r.status_code == 200, r.text
        r = await c.post("/api/v1/auth/login", json=LOGIN, headers={"x-forwarded-for": "203.0.113.9"})
        assert r.status_code == 429
        # another browser behind the same frontend container is not affected
        r = await c.post("/api/v1/auth/login", json=LOGIN, headers={"x-forwarded-for": "203.0.113.10"})
        assert r.status_code == 200


async def test_a_spoofed_header_from_a_public_peer_is_ignored(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(_rule("login"), "per_address", Throttle(300, 1))
    async with _client("198.51.100.7") as c:
        r = await c.post("/api/v1/auth/login", json=LOGIN, headers={"x-forwarded-for": "203.0.113.50"})
        assert r.status_code == 200
        # rotating the header does not give the same peer a fresh bucket
        r = await c.post("/api/v1/auth/login", json=LOGIN, headers={"x-forwarded-for": "203.0.113.51"})
        assert r.status_code == 429


async def test_the_login_failure_cap_sees_the_forwarded_client(client, limits):  # type: ignore[no-untyped-def]  # noqa: F811
    """app.core.ratelimit keys failed sign-ins on request.client: the rewritten scope reaches it, so one attacker's
    50 failures no longer lock out every password sign-in behind the frontend container."""
    from app.core import ratelimit

    ratelimit.reset()
    try:
        async with _client("172.18.0.4") as c:
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": "admin@example.com", "password": "wrong-password"},
                headers={"x-forwarded-for": "203.0.113.77"},
            )
            assert r.status_code == 401
        assert "ip:203.0.113.77" in ratelimit._fails and "ip:172.18.0.4" not in ratelimit._fails
    finally:
        ratelimit.reset()


def test_uvicorn_trusts_only_the_proxy_hops() -> None:
    assert "--forwarded-allow-ips='*'" not in ENTRYPOINT and '--forwarded-allow-ips="*"' not in ENTRYPOINT
    m = re.search(r'FORWARDED_ALLOW_IPS:=([^}"]+)\}', ENTRYPOINT)
    assert m, "the entrypoint defaults FORWARDED_ALLOW_IPS"
    default = {p.strip() for p in m.group(1).split(",")}
    assert default == {"127.0.0.1", "::1", "172.16.0.0/12"}
    assert '--forwarded-allow-ips="${FORWARDED_ALLOW_IPS}"' in ENTRYPOINT
    # compose passes the same default to the backend (uvicorn and the app read one variable)
    assert "FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-127.0.0.1,::1,172.16.0.0/12}" in COMPOSE
    from app.core.config import Settings

    assert {p.strip() for p in Settings().forwarded_allow_ips.split(",")} == default


def test_trusted_hops_follow_the_setting(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "127.0.0.1,10.9.0.0/16")
    get_settings.cache_clear()
    try:
        assert sh.is_proxy_hop("10.9.3.4") and not sh.is_proxy_hop("172.18.0.4")
    finally:
        monkeypatch.delenv("FORWARDED_ALLOW_IPS")
        get_settings.cache_clear()
    assert sh.is_proxy_hop("172.18.0.4")
