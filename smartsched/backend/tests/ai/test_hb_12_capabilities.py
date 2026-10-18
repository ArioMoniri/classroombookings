"""HB-12 capability detection on model sync and route validation (architecture doc §5.8).

No network: every server is an ``httpx.MockTransport`` shaped like Ollama, vLLM, LM Studio or llama.cpp; the
SSRF case patches the socket layer and proves nothing is sent to a blocked address.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.ai import capabilities as caps
from app.ai import gateway as gw
from app.ai import pipeline
from app.ai.providers.base import ModelInfo, ProviderError
from app.ai.providers.openai_compat import OpenAICompatAdapter
from app.core.db import get_session_factory
from app.models import AuditEvent
from app.models.ai_usage import AIUsage
from app.services import ai_usage as meter
from sqlalchemy import select

from tests.api_fixtures import login


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    yield
    pipeline.TEST_TRANSPORT[0] = None
    pipeline.reset_state()
    meter.reset_state()


def _completion(content: str = "OK", calls: list[dict[str, Any]] | None = None) -> httpx.Response:
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


def server(kind: str, seen: list[httpx.Request] | None = None):
    """A mock local server of ``kind``: ``ollama`` | ``vllm`` | ``lmstudio`` | ``llamacpp``."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        path = request.url.path
        if path == "/v1/models":
            if kind == "vllm":
                return httpx.Response(
                    200, json={"data": [{"id": "Qwen/Qwen3-14B", "owned_by": "vllm", "max_model_len": 32768}]}
                )
            return httpx.Response(200, json={"data": [{"id": "qwen3:14b"}, {"id": "llava:7b"}]})
        if kind == "ollama" and path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.3"})
        if kind == "ollama" and path == "/api/show":
            name = json.loads(request.content)["model"]
            vision = name.startswith("llava")
            return httpx.Response(
                200,
                json={
                    "capabilities": ["completion", "vision"] if vision else ["completion", "tools", "thinking"],
                    "model_info": {"qwen3.context_length": 40960} if not vision else {"llama.context_length": 4096},
                    "parameters": "num_ctx 16384\ntemperature 0.6" if not vision else "",
                },
            )
        if kind == "lmstudio" and path == "/api/v0/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "qwen3:14b", "type": "llm", "capabilities": ["tool_use"], "max_context_length": 32768},
                        {"id": "llava:7b", "type": "vlm", "max_context_length": 4096},
                    ]
                },
            )
        if kind == "llamacpp" and path == "/props":
            return httpx.Response(
                200,
                json={
                    "default_generation_settings": {"n_ctx": 8192},
                    "chat_template": "{{ messages }}",
                    "chat_template_caps": {"supports_tools": True, "supports_parallel_tool_calls": False},
                    "modalities": {"vision": False},
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def _adapter(kind: str, seen: list[httpx.Request] | None = None) -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        "openai_compatible",
        api_key=None,
        base_url="http://127.0.0.1:11434/v1",
        transport=server(kind, seen),
        allow_local=True,
    )


async def _sync(adapter: OpenAICompatAdapter) -> dict[str, dict[str, Any]]:
    models = await adapter.list_models()
    detected = await adapter.sniff(models)
    out = {m.id: dict(m.capabilities or {}) for m in models}
    out["_server"] = {"kind": detected}
    return out


# ------------------------------------------------------------------ sniffing per server type


async def test_ollama_like_server():
    got = await _sync(_adapter("ollama"))
    assert got["_server"]["kind"] == "ollama"
    q = got["qwen3:14b"]
    assert (q["tools"], q["tool_choice"], q["strict_tools"], q["json_schema"], q["vision"]) == (
        True,
        False,
        False,
        True,
        False,
    )
    assert q["context_window"] == 16384  # num_ctx served, not the model's 40960
    assert q["pdf"] is False and q["parallel_tools"] is False and q["source"] == "provider" and q["checked_at"]
    v = got["llava:7b"]
    assert v["vision"] is True and v["tools"] is False and v["context_window"] == 4096


async def test_vllm_like_server():
    got = await _sync(_adapter("vllm"))
    m = got["Qwen/Qwen3-14B"]
    assert got["_server"]["kind"] == "vllm"
    assert m["context_window"] == 32768 and m["tool_choice"] is True and m["json_schema"] is True
    assert m["tools"] is None  # depends on --enable-auto-tool-choice: unknown until probed


async def test_lmstudio_like_server():
    got = await _sync(_adapter("lmstudio"))
    assert got["_server"]["kind"] == "lmstudio"
    assert got["qwen3:14b"]["tools"] is True and got["qwen3:14b"]["context_window"] == 32768
    assert got["llava:7b"]["vision"] is True and got["llava:7b"]["tools"] is False


async def test_llamacpp_like_server():
    got = await _sync(_adapter("llamacpp"))
    assert got["_server"]["kind"] == "llamacpp"
    m = got["qwen3:14b"]
    assert m["context_window"] == 8192 and m["tools"] is True and m["vision"] is False
    assert m["parallel_tools"] is False and m["json_schema"] is True


async def test_unknown_server_keeps_capabilities_unknown():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "mystery"}]})
        # answers everything else with a chat completion (like the W3 stubs): never mistaken for a server type
        return _completion()

    adapter = OpenAICompatAdapter(
        "openai_compatible", api_key=None, base_url="http://127.0.0.1:9/v1", transport=httpx.MockTransport(handler)
    )
    models = await adapter.list_models()
    assert await adapter.sniff(models) is None
    c = models[0].capabilities or {}
    assert c["tools"] is None and c["vision"] is None and c["pdf"] is False


async def test_no_request_reaches_a_blocked_address(monkeypatch):
    sent: list[str] = []

    async def spy(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        sent.append(str(url))
        raise AssertionError("no request may leave")

    monkeypatch.setattr(httpx.AsyncClient, "request", spy)
    adapter = OpenAICompatAdapter(
        "openai_compatible", api_key=None, base_url="http://169.254.169.254/v1", allow_local=True
    )
    with pytest.raises(ProviderError):
        await adapter.list_models()
    assert await adapter.sniff([ModelInfo(id="x")]) is None
    assert sent == []


def test_static_capabilities_per_provider():
    c = caps.for_listing("anthropic", "claude-opus-5-5", None, 1_000_000)
    assert all(c[k] is True for k in caps.BOOL_KEYS) and c["context_window"] == 1_000_000
    o = caps.for_listing("openrouter", "meta/llama", {"supported_parameters": ["tools"], "context_length": 8000}, None)
    assert (o["tools"], o["tool_choice"], o["json_schema"], o["context_window"]) == (True, False, False, 8000)
    assert caps.for_listing("openai", "gpt-5-mini", None, None)["vision"] is True


def test_merge_layers_admin_wins_and_unknown_never_overwrites():
    sync = caps.record(tools=True, context_window=4096)
    probe = caps.record("probe", tools=False, vision=True)
    admin = {"tools": True, "source": "admin", "checked_at": "2026-10-18T08:00:00+00:00"}
    got = caps.merge(sync, probe, admin, {"tools": None})
    assert got["tools"] is True and got["vision"] is True and got["context_window"] == 4096
    assert got["source"] == "admin"


# ------------------------------------------------------------------ route validation


def test_chat_route_to_a_no_tools_model_is_refused_in_turkish_and_english():
    synced = {"openai_compatible": {"llava:7b", "qwen3:14b"}}
    capmap = {
        "openai_compatible": {
            "llava:7b": caps.record(tools=False, json_schema=True, context_window=32768),
            "qwen3:14b": caps.record(tools=True, context_window=8192),
        }
    }
    errs = gw.validate_route(
        {"provider": "openai_compatible", "model": "llava:7b"}, synced, feature="chat", capabilities=capmap
    )
    assert [e["code"] for e in errs] == ["model_lacks_capability"]
    assert "araç çağırmayı desteklemiyor" in errs[0]["message_tr"] and "cannot call tools" in errs[0]["message_en"]
    errs = gw.validate_route(
        {"provider": "openai_compatible", "model": "qwen3:14b"}, synced, feature="chat", capabilities=capmap
    )
    assert [e["code"] for e in errs] == ["context_too_small"]
    # rules accept JSON-schema emulation, vision needs image input
    assert gw.validate_route(
        {"provider": "openai_compatible", "model": "llava:7b"}, synced, feature="rules", capabilities=capmap
    ) == []
    errs = gw.validate_route(
        {"provider": "openai_compatible", "model": "qwen3:14b"}, synced, feature="vision", capabilities=capmap
    )
    assert errs == []  # vision unknown is a warning, not a refusal
    w = gw.route_warnings(
        {"provider": "openai_compatible", "model": "qwen3:14b"}, feature="vision", capabilities=capmap
    )
    assert [x["code"] for x in w] == ["capability_unknown"]
    # the fallback is checked too
    errs = gw.validate_route(
        {
            "provider": "openai_compatible",
            "model": "qwen3:14b",
            "fallback_provider": "openai_compatible",
            "fallback_model": "llava:7b",
        },
        synced,
        feature="rules",
        capabilities=capmap,
    )
    assert errs == []
    errs = gw.validate_route(
        {
            "provider": "anthropic",
            "model": "claude-opus-5-5",
            "fallback_provider": "openai_compatible",
            "fallback_model": "llava:7b",
        },
        {**synced, "anthropic": {"claude-opus-5-5"}},
        feature="chat",
        capabilities=capmap,
    )
    assert [(e["field"], e["code"]) for e in errs] == [("fallback_model", "model_lacks_capability")]


# ------------------------------------------------------------------ admin API: sync, probe, override


def _install(kind: str, probe: dict[str, Any] | None = None) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    base = server(kind)
    probe = probe or {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            if body.get("tools"):
                if probe.get("tools", True):
                    return _completion(
                        "",
                        [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "report_colour",
                                    "arguments": json.dumps({"colour": "blue", "count": 2}),
                                },
                            }
                        ],
                    )
                return _completion("I cannot call tools.")
            if body.get("response_format"):
                return _completion(json.dumps({"answer": "ok"}))
            content = body["messages"][-1]["content"]
            if isinstance(content, list):
                return _completion("Red." if probe.get("vision") else "I see nothing.")
            return _completion("OK")
        return base.handle_request(request)

    pipeline.TEST_TRANSPORT[0] = httpx.MockTransport(handler)
    return seen


async def test_sync_stores_capabilities_and_the_probe_result(client):
    h = await login(client)
    r = await client.put(
        "/api/v1/ai/admin/providers/openai_compatible",
        json={"base_url": "http://127.0.0.1:11434/v1", "enabled": True, "allow_local": True},
        headers=h,
    )
    assert r.status_code == 200
    _install("ollama", {"tools": True, "vision": False})
    r = await client.post("/api/v1/ai/admin/providers/openai_compatible/sync", headers=h)
    body = r.json()
    assert r.status_code == 200 and body["ok"] and body["server_kind"] == "ollama"
    by_id = {m["id"]: m for m in body["models"]}
    assert by_id["llava:7b"]["capabilities"]["tools"] is False
    # chat to llava is refused with 422 TR/EN
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"chat": {"provider": "openai_compatible", "model": "llava:7b"}}},
        headers=h,
    )
    assert r.status_code == 422
    err = r.json()["detail"]["errors"][0]
    assert err["code"] == "model_lacks_capability" and err["message_tr"] and err["message_en"]
    # rules to qwen3 is accepted (tools known)
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"rules": {"provider": "openai_compatible", "model": "qwen3:14b"}}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    # probe: forced tool works, JSON schema works, the image is not read
    r = await client.post(
        "/api/v1/ai/admin/providers/openai_compatible/test?probe=true", json={"model": "qwen3:14b"}, headers=h
    )
    assert r.status_code == 200, r.text
    got = r.json()["capabilities"]
    assert got["source"] == "probe" and got["tools"] is True and got["strict_tools"] is True
    assert got["json_schema"] is True and got["vision"] is False
    async with get_session_factory()() as s:
        rows = list((await s.execute(select(AIUsage))).scalars())
        stored = await gw.model_capabilities(s, "openai_compatible")
    [row] = rows
    assert row.feature == "test" and row.input_tokens + row.output_tokens < 1000
    eff = stored["qwen3:14b"]
    assert eff["vision"] is False and eff["context_window"] == 16384 and eff["source"] == "probe"


async def test_admin_override_is_audited_and_wins(client):
    h = await login(client)
    await client.put(
        "/api/v1/ai/admin/providers/openai_compatible",
        json={"base_url": "http://127.0.0.1:11434/v1", "enabled": True, "allow_local": True},
        headers=h,
    )
    _install("ollama")
    await client.post("/api/v1/ai/admin/providers/openai_compatible/sync", headers=h)
    r = await client.put(
        "/api/v1/ai/admin/providers/openai_compatible/capabilities",
        json={"model": "llava:7b", "capabilities": {"tools": True, "context_window": 32768}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["capabilities"]["tools"] is True and r.json()["capabilities"]["source"] == "admin"
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"chat": {"provider": "openai_compatible", "model": "llava:7b"}}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    bad = await client.put(
        "/api/v1/ai/admin/providers/openai_compatible/capabilities",
        json={"model": "not-synced", "capabilities": {"tools": True}},
        headers=h,
    )
    assert bad.status_code == 422
    async with get_session_factory()() as s:
        actions = [a.action for a in (await s.execute(select(AuditEvent))).scalars()]
    assert "ai.provider.capabilities" in actions
