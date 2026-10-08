"""Review M9 (secrets), MINOR 5 (/metrics auth, login rate limit, generic JWT errors)."""

from __future__ import annotations

import jwt
import pytest
from app.core.config import DEFAULT_APP_SECRET, Settings, assert_secure, get_settings

from tests.api_fixtures import login

GOOD_A = "a" * 24 + "-app-secret-0123456789"
GOOD_J = "j" * 24 + "-jwt-secret-0123456789"


@pytest.mark.parametrize(
    "app_secret,jwt_secret,reason",
    [
        (DEFAULT_APP_SECRET, GOOD_J, "APP_SECRET is a placeholder"),
        ("short-secret", GOOD_J, "APP_SECRET is shorter"),
        (GOOD_A, None, "JWT_SECRET is not set"),
        (GOOD_A, "__GENERATE__", "JWT_SECRET is a placeholder"),
        (GOOD_A, GOOD_A, "must differ"),
    ],
)
def test_m9_prod_refuses_insecure_secrets(app_secret, jwt_secret, reason):
    s = Settings(environment="prod", app_secret=app_secret, jwt_secret=jwt_secret)
    with pytest.raises(RuntimeError, match=reason):
        assert_secure(s)


def test_m9_prod_accepts_strong_distinct_secrets_and_dev_falls_back():
    assert_secure(Settings(environment="prod", app_secret=GOOD_A, jwt_secret=GOOD_J))
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
