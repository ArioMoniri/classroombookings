from __future__ import annotations

from app.api.v1 import settings as settings_api

from tests.api_fixtures import login


async def test_health_and_login_flow(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["db"] is True and "solver" not in r.json()
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert r.status_code == 401
    h = await login(client)
    r = await client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200 and r.json()["role"] == "ADMIN" and r.json()["email"] == "admin@example.com"
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    r = await client.get("/api/v1/metrics")
    assert r.status_code == 401  # review MINOR 5: not anonymous
    r = await client.get("/api/v1/metrics", headers=h)
    assert r.status_code == 200 and "terms" in r.json()


async def test_settings_mask_secret_and_test_ai(client, monkeypatch):
    h = await login(client)
    r = await client.get("/api/v1/settings", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["anthropic_api_key"]["set"] is False and body["anthropic_model"]
    r = await client.put(
        "/api/v1/settings",
        json={
            "anthropic_api_key": "sk-ant-api03-SECRETVALUE-xyz",
            "anthropic_model": "claude-opus-5-5",
            "solver_default_time_limit": 30,
        },
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["anthropic_api_key"]["set"] is True
    assert "SECRETVALUE" not in body["anthropic_api_key"]["masked"] and body["anthropic_api_key"]["masked"].startswith(
        "sk-a"
    )
    assert body["anthropic_model"] == "claude-opus-5-5" and body["solver_default_time_limit"] == 30.0
    # stored encrypted
    from app.core.db import get_session_factory
    from app.models import Setting
    from sqlalchemy import select

    async with get_session_factory()() as s:
        row = (await s.execute(select(Setting).where(Setting.key == "anthropic_api_key"))).scalar_one()
        assert row.is_secret and "SECRETVALUE" not in (row.value or "")

    calls: list[tuple[str, str]] = []

    async def fake_probe(key: str, model: str) -> tuple[bool, str]:
        calls.append((key, model))
        return key.endswith("good"), "ok" if key.endswith("good") else "AuthenticationError"

    monkeypatch.setattr(settings_api, "_probe_ai", fake_probe)
    r = await client.post("/api/v1/settings/test-ai", json={}, headers=h)
    assert (
        r.json()["used_key"] == "stored" and r.json()["ok"] is False and calls[-1][0] == "sk-ant-api03-SECRETVALUE-xyz"
    )
    r = await client.post("/api/v1/settings/test-ai", json={"api_key": "sk-ant-transient-0123456789-good"}, headers=h)
    assert r.json()["used_key"] == "transient" and r.json()["ok"] is True and r.json()["model"] == "claude-opus-5-5"
    # transient key was not saved
    r = await client.get("/api/v1/settings", headers=h)
    assert (
        r.json()["anthropic_api_key"]["masked"].startswith("sk-a")
        and "tran" not in r.json()["anthropic_api_key"]["masked"]
    )


async def test_role_guard(client):
    h = await login(client)
    from app.core.db import get_session_factory
    from app.core.security import hash_password
    from app.models import User

    async with get_session_factory()() as s:
        s.add(User(email="viewer@example.com", password_hash=hash_password("viewer123"), role="VIEWER"))
        await s.commit()
    hv = await login(client, "viewer@example.com", "viewer123")
    assert (await client.get("/api/v1/terms", headers=hv)).status_code == 200
    assert (await client.post("/api/v1/terms", json={"code": "X"}, headers=hv)).status_code == 403
    assert (await client.get("/api/v1/settings", headers=hv)).status_code == 403
    assert (
        await client.post("/api/v1/terms", json={"code": "2026-TEST", "name": "Test"}, headers=h)
    ).status_code == 201
