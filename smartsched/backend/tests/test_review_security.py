"""Review M9 (secrets), MINOR 5 (/metrics auth, login rate limit, generic JWT errors)."""

from __future__ import annotations

import jwt
import pytest
from app.core.config import DEFAULT_APP_SECRET, Settings, assert_secure, get_settings

from tests.api_fixtures import login

# no "secret"/"change-me" in a real value: placeholder words are refused (no-placeholder audit M2)
GOOD_A = "a" * 24 + "-app-key-0123456789abc"
GOOD_J = "j" * 24 + "-jwt-key-0123456789abc"


@pytest.mark.parametrize(
    "app_secret,jwt_secret,reason",
    [
        (DEFAULT_APP_SECRET, GOOD_J, "APP_SECRET is a placeholder"),
        ("short-value-0123", GOOD_J, "APP_SECRET is shorter"),
        (GOOD_A, None, "JWT_SECRET is not set"),
        (GOOD_A, "__GENERATE__", "JWT_SECRET is a placeholder"),
        (GOOD_A, GOOD_A, "must differ"),
    ],
)
def test_m9_prod_refuses_insecure_secrets(app_secret, jwt_secret, reason):
    s = Settings(environment="prod", app_secret=app_secret, jwt_secret=jwt_secret, admin_password=None)
    with pytest.raises(RuntimeError, match=reason):
        assert_secure(s)


def test_m9_prod_accepts_strong_distinct_secrets_and_dev_falls_back():
    assert_secure(Settings(environment="prod", app_secret=GOOD_A, jwt_secret=GOOD_J, admin_password=None))
    assert_secure(Settings(environment="dev"))  # dev keeps working with the default
    assert Settings(environment="dev", app_secret=GOOD_A).signing_key == GOOD_A
    assert Settings(environment="prod", app_secret=GOOD_A, jwt_secret=GOOD_J).signing_key == GOOD_J


async def test_m9_tokens_are_signed_with_jwt_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", GOOD_J)
    h = await login(client)
    token = h["Authorization"].split()[1]
    assert jwt.decode(token, GOOD_J, algorithms=["HS256"])["sub"]
    # a token forged with APP_SECRET (the old signing key) is rejected
    forged = jwt.encode({"sub": "admin@example.com", "uid": 1, "exp": 9999999999}, get_settings().app_secret, "HS256")
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401 and r.json()["detail"] == "invalid token"  # generic, no library text


async def test_minor5_metrics_needs_admin_or_token(client, monkeypatch):
    assert (await client.get("/api/v1/metrics")).status_code == 401
    monkeypatch.setattr(get_settings(), "metrics_token", "scrape-token-0123456789")
    r = await client.get("/api/v1/metrics", headers={"Authorization": "Bearer scrape-token-0123456789"})
    assert r.status_code == 200 and "runs_by_status" in r.json()
    r = await client.get("/api/v1/metrics", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert (await client.get("/api/v1/metrics", headers=await login(client))).status_code == 200


async def test_minor5_login_failures_are_rate_limited(client):
    bad = {"email": "admin@example.com", "password": "wrong-password"}
    codes = [(await client.post("/api/v1/auth/login", json=bad)).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    r = await client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin1234"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0  # even the right password waits
    other = await client.post("/api/v1/auth/login", json={"email": "someone@example.com", "password": "x"})
    assert other.status_code == 401  # another account from the same address is not blocked yet


async def test_u4_saved_key_is_unverified_until_a_real_probe_succeeds(client, monkeypatch):
    from app.api.v1 import settings as settings_api

    h = await login(client)
    fake = "sk-ant-api03-" + "x" * 40
    assert (await client.put("/api/v1/settings", json={"anthropic_api_key": fake}, headers=h)).status_code == 200
    st = (await client.get("/api/v1/settings", headers=h)).json()["anthropic_api_key"]
    assert st["set"] and st["status"] == "unverified"  # saved is not "connected"

    async def rejected(_key, _model):
        return False, f"Anthropic rejected the API key (authentication error) for {fake}"

    monkeypatch.setattr(settings_api, "_probe_ai", rejected)
    r = (await client.post("/api/v1/settings/test-ai", json={}, headers=h)).json()
    assert r["ok"] is False and fake not in r["detail"] and "sk-ant-***" in r["detail"]
    st = (await client.get("/api/v1/settings", headers=h)).json()["anthropic_api_key"]
    assert st["status"] == "failed" and st["checked_at"]

    async def accepted(_key, _model):
        return True, "ok (claude-opus-5-5, 8 in / 1 out)"

    monkeypatch.setattr(settings_api, "_probe_ai", accepted)
    assert (await client.post("/api/v1/settings/test-ai", json={}, headers=h)).json()["ok"] is True
    assert (await client.get("/api/v1/settings", headers=h)).json()["anthropic_api_key"]["status"] == "ok"
    # a different key is unverified again
    await client.put("/api/v1/settings", json={"anthropic_api_key": "sk-ant-api03-" + "y" * 40}, headers=h)
    assert (await client.get("/api/v1/settings", headers=h)).json()["anthropic_api_key"]["status"] == "unverified"


async def test_u4_probe_only_reports_ok_on_a_successful_call(monkeypatch):
    """``test_connection`` makes the real call; an authentication error is never "ok"."""
    import anthropic
    import httpx
    from app.ai import client as ai_client

    async def boom(self, kwargs):
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=req), body=None)

    monkeypatch.setattr(ai_client.AIClient, "_send", boom)
    ok, detail = await ai_client.test_connection("sk-ant-api03-" + "z" * 40)
    assert ok is False and "rejected" in detail


async def test_minor3_api_keys_with_control_characters_are_refused(client):
    h = await login(client)
    for bad in ("sk-ant-api03-abc\ndef" + "x" * 30, "sk-ant api03 " + "x" * 30, "short"):
        r = await client.put("/api/v1/settings", json={"anthropic_api_key": bad}, headers=h)
        assert r.status_code == 422, bad
        r = await client.post("/api/v1/settings/test-ai", json={"api_key": bad}, headers=h)
        assert r.status_code == 422


def test_minor3_log_lines_never_carry_a_key(caplog):
    import logging

    import app.ai.client  # noqa: F401 - installs the redaction filter

    with caplog.at_level(logging.DEBUG, logger="httpx"):
        logging.getLogger("httpx").debug("headers: x-api-key=%s", "sk-ant-api03-SECRETSECRETSECRET")
    assert "SECRETSECRET" not in caplog.text and "sk-ant-***" in caplog.text


async def test_minor14_room_photo_checks_bytes_and_size(client, monkeypatch):
    from app.api.v1 import rooms as rooms_api

    h = await login(client)
    r = await client.post("/api/v1/rooms", json={"code": "A 101", "capacity": 58}, headers=h)
    assert r.status_code in (200, 201), r.text
    rid = r.json()["id"]
    url = f"/api/v1/rooms/{rid}/photo"
    html = b"<html><script>alert(1)</script></html>"
    assert (await client.post(url, files={"file": ("x.png", html, "image/png")}, headers=h)).status_code == 400
    gif_as_png = b"GIF89a" + b"0" * 32
    r = await client.post(url, files={"file": ("x.png", gif_as_png, "image/png")}, headers=h)
    assert r.status_code == 400 and "gif" in r.json()["detail"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    assert (await client.post(url, files={"file": ("x.png", png, "text/html")}, headers=h)).status_code == 400
    r = await client.post(url, files={"file": ("x.png", png, "image/png")}, headers=h)
    assert r.status_code == 200 and r.json()["photo_url"].endswith(".png")
    monkeypatch.setattr(rooms_api, "PHOTO_MAX_BYTES", 16)
    assert (await client.post(url, files={"file": ("x.png", png, "image/png")}, headers=h)).status_code == 413
