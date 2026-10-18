"""VO-04 voice administration: only AI admins read or change voice settings; sync, route and the speech test call
with the bundled Turkish clip (transcript preview ≤ 60 characters, metered as ``test`` with its audio length);
``PUT /ai/admin/voice`` is validated and audited; every admin sees the same settings (the shared ``settings``
table); the KVKK transfer record carries ``processes_voice`` / ``audio_retention``; the limits take audio
seconds."""

from __future__ import annotations

import httpx
import pytest
from app.ai import pipeline
from app.core.db import get_session_factory
from app.models import AuditEvent
from app.models.ai_usage import AIUsage
from app.services import ai_usage as meter
from sqlalchemy import select

from tests.ai.voice_support import KEY, add_user, clip, configure, openai_stub, response
from tests.api_fixtures import login


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    yield
    pipeline.TEST_TRANSPORT[0] = None
    pipeline.reset_state()
    meter.reset_state()


async def test_teachers_and_planners_cannot_manage_voice(client):
    await add_user("teacher@example.com", "TEACHER")
    await add_user("planner@example.com", "PLANNER")
    for email in ("teacher@example.com", "planner@example.com"):
        hh = await login(client, email, "parola-1234")
        assert (await client.get("/api/v1/ai/admin/voice", headers=hh)).status_code == 403
        assert (await client.put("/api/v1/ai/admin/voice", json={"enabled": True}, headers=hh)).status_code == 403
    assert (await client.get("/api/v1/ai/admin/voice")).status_code == 401


async def test_defaults_validation_audit_and_a_second_admin_sees_the_same(client):
    h = await login(client)
    r = await client.get("/api/v1/ai/admin/voice", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["settings"] == {
        "enabled": False,
        "language": "tr",
        "max_seconds": 120,
        "vocabulary": "catalog",
        "live_captions": "on_device",
        "prices_per_min": {},
    }
    assert d["fixed"] == {"retention_days": 0, "review_before_send": True, "max_seconds_cap": 120, "consent": "voice"}
    assert d["route"]["source"] == "none"
    for bad in ({"max_seconds": 121}, {"max_seconds": 2}, {"vocabulary": "names"}, {"language": "de"}):
        r = await client.put("/api/v1/ai/admin/voice", json=bad, headers=h)
        assert r.status_code == 422, bad
    r = await client.put(
        "/api/v1/ai/admin/voice",
        json={"enabled": True, "max_seconds": 60, "prices_per_min": {"deepgram:nova-3": 0.0048}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["max_seconds"] == 60
    async with get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "ai.voice"))).scalars().all()
    assert len(ev) == 1 and ev[0].after["max_seconds"] == 60 and ev[0].before["max_seconds"] == 120
    await add_user("admin2@example.com", "ADMIN")
    h2 = await login(client, "admin2@example.com", "parola-1234")
    d2 = (await client.get("/api/v1/ai/admin/voice", headers=h2)).json()
    assert d2["settings"]["max_seconds"] == 60 and d2["settings"]["enabled"] is True
    st = (await client.get("/api/v1/ai/voice/status", headers=h2)).json()
    assert st["max_seconds"] == 60


async def test_sync_route_and_test_with_the_bundled_turkish_clip(client):
    seen = openai_stub()
    h = await configure(client, enable=False, consent=False)
    r = await client.post("/api/v1/ai/admin/providers/openai/test", json={"model": "gpt-4o-mini-transcribe"}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["kind"] == "stt" and out["model"] == "gpt-4o-mini-transcribe"
    assert out["transcript_preview"].startswith("Şu cümle") and len(out["transcript_preview"]) <= 60
    sent = [q for q in seen if q.url.path.endswith("/audio/transcriptions")][-1]
    assert clip() in sent.content
    # the text test call still works for a chat model of the same provider
    r = await client.post("/api/v1/ai/admin/providers/openai/test", json={"model": "gpt-5"}, headers=h)
    assert r.json()["ok"] is True and r.json()["kind"] == "text"
    async with get_session_factory()() as s:
        rows = list((await s.execute(select(AIUsage).where(AIUsage.feature == "test"))).scalars())
    stt = [x for x in rows if x.modality == "audio_in"]
    assert len(stt) == 1 and 5000 <= stt[0].audio_ms <= 5300 and stt[0].outcome == "ok"
    listing = (await client.get("/api/v1/ai/admin/providers", headers=h)).json()["providers"]
    oa = next(p for p in listing if p["id"] == "openai")
    assert oa["last_test"]["kind"] == "text"
    assert oa["capabilities"] == ["stt", "text"] and KEY not in str(listing)
    vo = (await client.get("/api/v1/ai/admin/voice", headers=h)).json()
    assert vo["route"]["provider"] == "openai" and vo["route"]["source"] == "feature"
    assert vo["route"]["usable"] is True and vo["route"]["transfer_ok"] is True


async def test_speech_only_provider_sync_and_test(client):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response("deepgram"))

    pipeline.TEST_TRANSPORT[0] = httpx.MockTransport(handler)
    h = await login(client)
    r = await client.put(
        "/api/v1/ai/admin/providers/deepgram",
        json={
            "api_key": KEY,
            "transfer": {
                "region": "eu",
                "kvkk_mechanism": "standard_contract",
                "processes_voice": True,
                "audio_retention": "silinir (sözleşme)",
            },
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    t = r.json()["transfer"]
    assert t["processes_voice"] is True and t["audio_retention"] == "silinir (sözleşme)"
    assert r.json()["config"]["base_url"] == "https://api.eu.deepgram.com"
    r = await client.post("/api/v1/ai/admin/providers/deepgram/sync", headers=h)
    assert r.status_code == 200 and r.json()["ok"]
    assert {m["id"]: m["modalities"] for m in r.json()["models"]} == {"nova-3": ["stt"], "nova-2": ["stt"]}
    assert seen == []  # a static model list: no request
    r = await client.post("/api/v1/ai/admin/providers/deepgram/test", json={}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["kind"] == "stt"
    assert seen and seen[0].url.host == "api.eu.deepgram.com"
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"voice_stt": {"provider": "deepgram", "model": "nova-3"}}},
        headers=h,
    )
    assert r.status_code == 200, r.text


async def test_a_failing_speech_test_is_short_and_stored(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "whisper-1"}]})
        return httpx.Response(401, json={"error": f"bad key {KEY}"})

    pipeline.TEST_TRANSPORT[0] = httpx.MockTransport(handler)
    h = await login(client)
    await client.put("/api/v1/ai/admin/providers/openai", json={"api_key": KEY}, headers=h)
    await client.post("/api/v1/ai/admin/providers/openai/sync", headers=h)
    r = await client.post("/api/v1/ai/admin/providers/openai/test", json={}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["kind"] == "stt"
    assert "API key" in r.json()["detail"] and KEY not in r.text


async def test_limits_take_audio_seconds(client):
    h = await login(client)
    r = await client.get("/api/v1/ai/admin/limits", headers=h)
    d = r.json()
    assert (d["user_daily_audio_s"], d["user_monthly_audio_s"], d["org_monthly_audio_s"]) == (600, 6000, 0)
    r = await client.put(
        "/api/v1/ai/admin/limits",
        json={"user_daily_audio_s": 900, "roles": {"ADMIN": {"daily": 0, "audio_daily": 3600, "audio_monthly": 0}}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_daily_audio_s"] == 900 and r.json()["roles"]["ADMIN"]["audio_daily"] == 3600
    r = await client.put("/api/v1/ai/admin/limits", json={"user_daily_audio_s": -1}, headers=h)
    assert r.status_code == 422
