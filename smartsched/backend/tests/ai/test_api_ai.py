"""API-level behaviour of the AI layer: auth, 409 without key, test-ai, catalogue, explain."""

from __future__ import annotations

import json
import logging

import anthropic
import httpx
from app.ai.client import AIClient, AIUpstreamError
from app.ai.client import test_connection as probe_connection
from app.core.db import get_session_factory
from app.core.security import hash_password
from app.models import ScheduleRun, User

from tests.ai.conftest import Message, seed_small, store_key, text
from tests.api_fixtures import login


async def _seed(client, key: bool = True):
    h = await login(client)
    async with get_session_factory()() as s:
        sd = await seed_small(s)
        if key:
            await store_key(s)
    return h, sd


async def test_409_without_key_and_planner_role_required(client, fake_sdk):
    h, sd = await _seed(client, key=False)
    for path, body in (
        (f"/api/v1/runs/{sd.run_id}/chat", {"message": "hi", "lang": "tr"}),
        (f"/api/v1/terms/{sd.term_id}/elicit", {"text": "TIP derslikleri sadece Tıp için", "lang": "tr"}),
    ):
        r = await client.post(path, json=body, headers=h)
        assert r.status_code == 409 and "Settings > AI" in r.json()["detail"], (path, r.text)
    r = await client.post(
        f"/api/v1/terms/{sd.term_id}/preferences/upload",
        files={"file": ("a.txt", b"PHAR 240 A 206", "text/plain")},
        headers=h,
    )
    assert r.status_code == 409
    assert not fake_sdk.calls

    async with get_session_factory()() as s:
        s.add(User(email="viewer@example.com", password_hash=hash_password("viewer1234"), role="VIEWER"))
        await s.commit()
    hv = await login(client, "viewer@example.com", "viewer1234")
    assert (await client.get("/api/v1/ai/catalog", headers=hv)).status_code == 403
    assert (await client.post(f"/api/v1/runs/{sd.run_id}/chat", json={"message": "x"}, headers=hv)).status_code == 403
    assert (await client.get("/api/v1/ai/catalog")).status_code == 401


async def test_catalog_endpoint(client):
    h = await login(client)
    r = await client.get("/api/v1/ai/catalog", headers=h)
    assert r.status_code == 200
    body = r.json()
    kinds = {k["kind"]: k for k in body["kinds"]}
    assert "room_pin" in kinds and kinds["room_pin"]["title"]["tr"] and kinds["room_pin"]["description"]["en"]
    assert {t["name"] for t in body["tools"]} >= {"propose_constraints", "move_event", "set_section_field", "re_solve"}


async def test_test_ai_with_transient_key(client, fake_sdk, caplog):
    h = await login(client)
    secret = "sk-ant-transient-SECRET-1234"
    fake_sdk.script = [text("OK")]
    with caplog.at_level(logging.DEBUG):
        r = await client.post(
            "/api/v1/settings/test-ai", json={"api_key": secret, "model": "claude-opus-5-5"}, headers=h
        )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["used_key"] == "transient" and out["model"] == "claude-opus-5-5"
    assert fake_sdk.instances[-1].api_key == secret
    call = fake_sdk.calls[-1]
    assert call["max_tokens"] <= 16 and not call["beta"] and "tools" not in call
    assert secret not in caplog.text and secret not in r.text
    # not saved
    settings = (await client.get("/api/v1/settings", headers=h)).json()
    assert settings["anthropic_api_key"]["set"] is False


async def test_test_connection_reports_auth_errors_without_the_key(fake_sdk):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_sdk.script = [
        anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=req), body=None)
    ]
    ok, detail = await probe_connection("sk-ant-bad-key-9999", "claude-opus-5-5")
    assert ok is False and "authentication" in detail and "9999" not in detail
    assert "9999" not in repr(AIClient("sk-ant-bad-key-9999", "claude-opus-5-5"))[:-6]


async def test_upstream_errors_map_to_502(client, fake_sdk):
    h, sd = await _seed(client)
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_sdk.script = [anthropic.RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)]
    r = await client.post(f"/api/v1/terms/{sd.term_id}/elicit", json={"text": "x", "lang": "en"}, headers=h)
    assert r.status_code == 502 and "rate limited" in r.json()["detail"]
    refusal = Message([], stop_reason="refusal")
    fake_sdk.script = [refusal]
    r = await client.post(f"/api/v1/terms/{sd.term_id}/elicit", json={"text": "x", "lang": "en"}, headers=h)
    assert r.status_code == 422
    assert issubclass(AIUpstreamError, Exception)


async def test_explain_template_model_and_grounding(client, fake_sdk):
    h, sd = await _seed(client, key=False)
    async with get_session_factory()() as s:
        run = await s.get(ScheduleRun, sd.run_id)
        run.status, run.hard_score = "INFEASIBLE", 67
        run.diagnosis = [
            {
                "event_ids": [1],
                "constraint_kinds": ["capacity"],
                "message": "BME 419 needs 102 seats on Wed P7-P9 but only A 204 (156) is free",
                "suggestions": ["release A 204"],
                "severity": "error",
            }
        ]
        await s.commit()
    r = await client.post(f"/api/v1/runs/{sd.run_id}/explain", json={"lang": "tr", "use_model": True}, headers=h)
    out = r.json()
    assert r.status_code == 200 and out["source"] == "template"  # no key -> deterministic template
    assert "INFEASIBLE" in out["text"] and "BME 419" in out["text"] and "release A 204" in out["text"]

    async with get_session_factory()() as s:
        await store_key(s)
    grounded = {
        "headline": "Run 1 is INFEASIBLE (67/100).",
        "paragraphs": ["BME 419 needs 102 seats; A 204 has 156."],
        "suggestions": ["release A 204"],
    }
    fake_sdk.script = [text(json.dumps(grounded))]
    out = (await client.post(f"/api/v1/runs/{sd.run_id}/explain", json={"lang": "en"}, headers=h)).json()
    assert out["source"] == "model" and out["text"].startswith("Run 1 is INFEASIBLE")
    assert fake_sdk.calls[-1]["output_config"]["format"]["type"] == "json_schema"

    invented = {**grounded, "paragraphs": ["BME 419 needs 999 seats."]}
    fake_sdk.script = [text(json.dumps(invented))]
    out = (await client.post(f"/api/v1/runs/{sd.run_id}/explain", json={"lang": "en"}, headers=h)).json()
    assert out["source"] == "template"  # an ungrounded number falls back to the template
