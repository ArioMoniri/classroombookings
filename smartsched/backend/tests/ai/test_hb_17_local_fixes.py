"""HB-17 local-model bench fixes (docs/testing/hb-17-local-bench-2026-10-18.md), gateway side.

* bug 2: Ollama serves ``OLLAMA_CONTEXT_LENGTH`` (``GET /api/ps`` ``context_length``), not the model's maximum
  (``/api/show`` ``model_info.*.context_length``): sync and the end of the probe store the smaller of the two, and a
  route whose served window is not known yet carries a ``context_unverified`` warning;
* bug 3: the helper's first message says what day it is (``bookings.now_local``, weekday in Turkish and English);
* bug 4: probe facts are stored only when the probe reached the server, and the forced tool call uses a neutral
  message, so a server that ignores ``tool_choice`` (and only calls the tool when asked to) reports ``false``.

No network: every server is an ``httpx.MockTransport``; Anthropic is the scripted fake SDK.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import pytest
from app.ai import capabilities as caps
from app.ai import gateway as gw
from app.ai import helper_turn as ht
from app.ai import pipeline
from app.ai.client import get_client
from app.ai.context import ai_scope
from app.ai.pipeline import AIGuardError
from app.ai.providers.openai_compat import OpenAICompatAdapter
from app.core.db import get_session_factory
from app.core.security import hash_password
from app.models import User
from app.services import ai_usage as meter
from app.services import bookings as bsvc
from app.services import kvkk
from app.services import settings_service as ss
from app.services.bookings_perms import load_access

from tests.ai.conftest import text
from tests.api_fixtures import login

LOCAL = "http://127.0.0.1:11434/v1"
MODEL = "qwen2.5:14b-instruct"


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    pipeline.TEST_TRANSPORT[0] = None
    yield
    pipeline.TEST_TRANSPORT[0] = None
    pipeline.reset_state()
    meter.reset_state()


def _completion(content: str = "", calls: list[dict[str, Any]] | None = None) -> httpx.Response:
    msg: dict[str, Any] = {"content": content}
    if calls:
        msg["tool_calls"] = calls
    return httpx.Response(
        200,
        json={
            "choices": [{"finish_reason": "tool_calls" if calls else "stop", "message": msg}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 8},
        },
    )


def _colour_call() -> list[dict[str, Any]]:
    return [
        {"id": "c1", "function": {"name": "report_colour", "arguments": json.dumps({"colour": "blue", "count": 2})}}
    ]


class Ollama:
    """A mock Ollama 0.40: ``/api/show`` reports the model's maximum (32768, ``parameters: null`` as in the bench),
    ``/api/ps`` the window it serves once loaded (``served``; ``None`` = not loaded). ``honours_choice=False`` is
    the real Ollama: it ignores ``tool_choice`` and calls the tool only when the message asks for it."""

    def __init__(self, *, served: int | None = 16384, maximum: int = 32768, honours_choice: bool = False) -> None:
        self.served, self.maximum, self.honours_choice = served, maximum, honours_choice
        self.chat: list[dict[str, Any]] = []
        self.down = False
        self.loads_on_chat = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": MODEL}]})
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.6"})
        if path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "capabilities": ["completion", "tools"],
                    "model_info": {"general.architecture": "qwen2", "qwen2.context_length": self.maximum},
                    "parameters": None,
                },
            )
        if path == "/api/ps":
            models = []
            if self.served is not None:
                models.append(
                    {"name": MODEL, "model": MODEL, "size_vram": 12_050_000_000, "context_length": self.served}
                )
            return httpx.Response(200, json={"models": models})
        if path.endswith("/chat/completions"):
            if self.down:
                raise httpx.ConnectError("connection refused")
            body = json.loads(request.content)
            self.chat.append(body)
            if self.loads_on_chat and self.served is None:
                self.served = 16384
            if body.get("tools"):
                asked = "report_colour" in json.dumps(body["messages"])
                named = isinstance(body.get("tool_choice"), dict)  # {"type": "function", ...}; "auto" is a string
                if asked or (self.honours_choice and named):
                    return _completion("", _colour_call())
                return _completion("Merhaba.")
            if body.get("response_format"):
                return _completion(json.dumps({"answer": "ok"}))
            return _completion("I see nothing.")
        return httpx.Response(404, json={"error": "not found"})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _adapter(server: Ollama) -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        "openai_compatible", api_key=None, base_url=LOCAL, transport=server.transport(), allow_local=True
    )


async def _sniffed(server: Ollama) -> dict[str, Any]:
    adapter = _adapter(server)
    models = await adapter.list_models()
    assert await adapter.sniff(models) == "ollama"
    [m] = models
    return dict(m.capabilities or {}) | {"_listed_window": m.context_window}


# ------------------------------------------------------------------ bug 2: the served context window


async def test_sniff_takes_the_served_window_from_api_ps():
    got = await _sniffed(Ollama(served=16384))
    assert got["context_window"] == 16384 and got["_listed_window"] == 16384
    assert got["context_verified"] is True


async def test_sniff_never_goes_above_the_model_maximum():
    got = await _sniffed(Ollama(served=65536, maximum=32768))
    assert got["context_window"] == 32768 and got["context_verified"] is True


async def test_a_model_that_is_not_loaded_keeps_the_maximum_and_warns_unverified():
    got = await _sniffed(Ollama(served=None))
    assert got["context_window"] == 32768 and got["context_verified"] is False
    errors, warnings = caps.route_issues("helper", got)
    assert errors == []
    [w] = [w for w in warnings if w["code"] == "context_unverified"]
    assert w["message_tr"] and w["message_en"] and "Test" in w["message_tr"]
    # an admin override of the window is a known window: no warning
    merged = caps.merge(got, {"context_window": 16384, "source": "admin"})
    assert not [w for w in caps.route_issues("helper", merged)[1] if w["code"] == "context_unverified"]


async def _admin_local(client) -> dict[str, str]:  # type: ignore[no-untyped-def]
    h = await login(client)
    r = await client.put(
        "/api/v1/ai/admin/providers/openai_compatible",
        json={"base_url": LOCAL, "enabled": True, "allow_local": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    return h


async def test_sync_stores_the_served_window_and_a_20k_helper_call_is_context_too_small(client):
    h = await _admin_local(client)
    server = Ollama(served=16384)
    pipeline.TEST_TRANSPORT[0] = server.transport()
    r = await client.post("/api/v1/ai/admin/providers/openai_compatible/sync", headers=h)
    assert r.status_code == 200 and r.json()["server_kind"] == "ollama", r.text
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"helper": {"provider": "openai_compatible", "model": MODEL}}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert not [w for w in r.json()["warnings"] if w["code"] == "context_unverified"]
    async with get_session_factory()() as s:
        assert (await gw.model_capabilities(s, "openai_compatible"))[MODEL]["context_window"] == 16384
        helper = await get_client(s, feature="helper")
        long_prompt = "Salon B 406 perşembe 13:30 için uygun mu, rezervasyon kuralları nelerdir? " * 800  # ~20k tokens
        assert 18_000 < len(long_prompt) // 3 < 22_000
        with ai_scope("helper"), pytest.raises(AIGuardError) as exc:
            await helper.complete(
                system="Yardımcı.", messages=[{"role": "user", "content": long_prompt}], max_tokens=4000
            )
    assert exc.value.code == "context_too_small" and exc.value.status_code == 422
    assert server.chat == []  # refused before anything was sent (the 32768 maximum would have let it through)


async def test_route_warns_until_the_probe_reads_the_served_window(client):
    h = await _admin_local(client)
    server = Ollama(served=None)
    server.loads_on_chat = True  # the probe's first call loads the model; /api/ps then shows 16384
    pipeline.TEST_TRANSPORT[0] = server.transport()
    assert (await client.post("/api/v1/ai/admin/providers/openai_compatible/sync", headers=h)).status_code == 200
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"helper": {"provider": "openai_compatible", "model": MODEL}}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert [w["code"] for w in r.json()["warnings"] if w["code"] == "context_unverified"] == ["context_unverified"]
    card = await _provider_card(client, h)
    [w] = [w for w in card["warnings"] if w["code"] == "context_unverified"]
    assert MODEL in w["message_tr"] and "32768" in w["message_tr"] and w["message_en"]
    r = await client.post(
        "/api/v1/ai/admin/providers/openai_compatible/test?probe=true", json={"model": MODEL}, headers=h
    )
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert r.json()["capabilities"]["context_window"] == 16384
    eff = r.json()["effective"]
    assert eff["context_window"] == 16384 and eff["context_verified"] is True
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"helper": {"provider": "openai_compatible", "model": MODEL}}},
        headers=h,
    )
    assert not [w for w in r.json()["warnings"] if w["code"] == "context_unverified"]
    assert not [w for w in (await _provider_card(client, h))["warnings"] if w["code"] == "context_unverified"]


async def _provider_card(client, h) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    r = await client.get("/api/v1/ai/admin/providers", headers=h)
    assert r.status_code == 200, r.text
    return next(p for p in r.json()["providers"] if p["id"] == "openai_compatible")


# ------------------------------------------------------------------ bug 4: probe facts


async def test_forced_call_is_neutral_so_ignoring_tool_choice_reports_false():
    server = Ollama(honours_choice=False)
    found, usage = await caps.probe(_adapter(server), MODEL)
    assert found["tool_choice"] is False and found["tools"] is True and usage.calls >= 2
    forced = server.chat[0]
    assert isinstance(forced.get("tool_choice"), dict)  # the named choice was sent ...
    assert "report_colour" not in json.dumps(forced["messages"])  # ... with a message that does not ask for it


async def test_a_server_that_honours_tool_choice_still_reports_true():
    server = Ollama(honours_choice=True)
    found, _ = await caps.probe(_adapter(server), MODEL)
    assert found["tool_choice"] is True and found["tools"] is True and found["strict_tools"] is True


async def test_probe_facts_are_not_stored_when_the_server_is_unreachable(client):
    h = await _admin_local(client)
    server = Ollama(served=16384)
    pipeline.TEST_TRANSPORT[0] = server.transport()
    assert (await client.post("/api/v1/ai/admin/providers/openai_compatible/sync", headers=h)).status_code == 200
    server.down = True  # an outage during "Test"
    r = await client.post(
        "/api/v1/ai/admin/providers/openai_compatible/test?probe=true", json={"model": MODEL}, headers=h
    )
    assert r.status_code == 200 and r.json()["ok"] is False, r.text
    async with get_session_factory()() as s:
        assert MODEL not in await gw.get_json(s, "ai.provider.openai_compatible.probe", {})
        eff = (await gw.model_capabilities(s, "openai_compatible"))[MODEL]
    assert eff["tools"] is True and eff["source"] == "provider"  # sync's facts stand; routing is not blocked
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"helper": {"provider": "openai_compatible", "model": MODEL}}},
        headers=h,
    )
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ bug 3: today's date in the first message


async def test_the_first_helper_message_says_what_day_it_is(session, fake_sdk, monkeypatch):
    async def fake_now(_session):  # type: ignore[no-untyped-def]
        return datetime(2026, 2, 16, 8, 0)

    monkeypatch.setattr(bsvc, "now_local", fake_now)
    u = User(email="ayse@uni.edu.tr", password_hash=hash_password("parola-1234"), role="TEACHER", full_name="Ayşe")
    session.add(u)
    await session.commit()
    await kvkk.grant(session, u, "ai_personal")
    await ss.set_value(session, "anthropic_api_key", "sk-ant-test-0000")
    await gw.put_json(
        session, gw.ROUTES_KEY, {"features": {"helper": {"provider": "anthropic", "model": "claude-opus-5-5"}}}
    )
    await session.commit()
    fake_sdk.script = [text("Perşembe için boş derslikleri bulabilirim.")]
    access = await load_access(session, u)
    result = await ht.run_turn(session, access, "perşembe boş derslik var mı?", "tr")
    assert result.mode == "ai" and result.model_calls == 1
    first = fake_sdk.calls[0]["messages"][0]
    assert first["role"] == "user"
    body = first["content"] if isinstance(first["content"], str) else json.dumps(first["content"], ensure_ascii=False)
    assert "Today is 2026-02-16 (Pazartesi" in body and "Monday" in body and "08:00" in body


# ------------------------------------------------------------------ P2: an answer that drifts into another script


async def test_a_cjk_drift_answer_is_replaced_by_the_index_answer(session, fake_sdk):
    u = User(email="ayse2@uni.edu.tr", password_hash=hash_password("parola-1234"), role="TEACHER", full_name="Ayşe")
    session.add(u)
    await session.commit()
    await kvkk.grant(session, u, "ai_personal")
    await ss.set_value(session, "anthropic_api_key", "sk-ant-test-0000")
    await gw.put_json(
        session, gw.ROUTES_KEY, {"features": {"helper": {"provider": "anthropic", "model": "claude-opus-5-5"}}}
    )
    await session.commit()
    drift = "Şifrenizi değiştirmek için 您可以在个人资料页面中找到密码设置并进行修改，然后保存即可完成。"
    fake_sdk.script = [text(drift)]
    result = await ht.run_turn(session, await load_access(session, u), "şifremi nasıl değiştiririm?", "tr")
    answer = next(c for c in result.cards if c["type"] == "answer")
    assert answer["source"] == "index" and "您" not in answer["text"]
    assert any(c["type"] == "nav" for c in result.cards)
