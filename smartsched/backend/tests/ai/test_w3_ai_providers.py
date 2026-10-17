"""W3-AI provider adapters: request translation, response normalisation, model listing and error mapping.

No network: OpenAI-compatible and Gemini go through ``httpx.MockTransport``; Anthropic and Bedrock get a scripted
stand-in for the SDK client.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from app.ai.providers import PROVIDERS, has_credentials, make_adapter
from app.ai.providers.anthropic_adapter import AnthropicAdapter, BedrockAdapter, bedrock_model_id
from app.ai.providers.base import ProviderError, ProviderUnsupported
from app.ai.providers.gemini import GeminiAdapter
from app.ai.providers.openai_compat import OpenAICompatAdapter

TOOL = {
    "name": "propose_constraints",
    "description": "propose rules",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"kind": {"type": "string"}},
        "required": ["kind"],
        "additionalProperties": False,
    },
}

CONVERSATION: dict[str, Any] = {
    "model": "gpt-5-mini",
    "max_tokens": 900,
    "system": [{"type": "text", "text": "You map rules.", "cache_control": {"type": "ephemeral"}}],
    "messages": [
        {"role": "user", "content": "NRS 450 C 301'de kalsın"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "x"},
                {"type": "text", "text": "Bakıyorum"},
                {"type": "tool_use", "id": "toolu_1", "name": "propose_constraints", "input": {"kind": "room_pin"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"ok": true}'},
                {"type": "text", "text": "devam"},
            ],
        },
    ],
    "tools": [TOOL],
    "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
    "output_config": {"effort": "low"},
}


def _mock(handler):
    calls: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), calls


# ------------------------------------------------------------------ registry


def test_registry_lists_every_provider_and_credentials_rule():
    assert set(PROVIDERS) == {
        "anthropic",
        "openai",
        "azure_openai",
        "openrouter",
        "openai_compatible",
        "gemini",
        "bedrock",
    }
    assert has_credentials("openai_compatible", {})  # a local Ollama needs no key
    assert not has_credentials("openai", {})
    assert has_credentials("bedrock", {"aws_access_key_id": "AKIA", "aws_secret_access_key": "s"})
    assert not has_credentials("bedrock", {"aws_access_key_id": "AKIA"})
    with pytest.raises(ProviderError):
        make_adapter("openai", model="gpt-5", secrets={})
    with pytest.raises(ProviderError):
        make_adapter("azure_openai", model="gpt-5", secrets={"api_key": "k"})  # base URL required
    with pytest.raises(ProviderError):
        make_adapter("nope", model="x", secrets={})


# ------------------------------------------------------------------ OpenAI-compatible


def test_openai_payload_translation():
    a = OpenAICompatAdapter("openai", api_key="sk-test")
    p = a.build_payload(CONVERSATION)
    assert p["messages"][0] == {"role": "system", "content": "You map rules."}
    assert p["messages"][1] == {"role": "user", "content": "NRS 450 C 301'de kalsın"}
    asst = p["messages"][2]
    assert asst["role"] == "assistant" and asst["content"] == "Bakıyorum"  # thinking dropped
    assert asst["tool_calls"][0]["function"] == {"name": "propose_constraints", "arguments": '{"kind": "room_pin"}'}
    # tool results come first, then the user's text of the same turn
    assert p["messages"][3] == {"role": "tool", "tool_call_id": "toolu_1", "content": '{"ok": true}'}
    assert p["messages"][4] == {"role": "user", "content": "devam"}
    fn = p["tools"][0]["function"]
    assert fn["strict"] is True and fn["parameters"]["additionalProperties"] is False
    assert p["tool_choice"] == "auto" and p["parallel_tool_calls"] is False
    assert p["max_completion_tokens"] == 900 and "max_tokens" not in p
    assert p["reasoning_effort"] == "low" and "temperature" not in p  # reasoning model


def test_openai_compatible_uses_max_tokens_and_temperature():
    a = OpenAICompatAdapter("openai_compatible", api_key=None, temperature=0.2)
    p = a.build_payload({**CONVERSATION, "model": "llama3.1"})
    assert p["max_tokens"] == 900 and p["temperature"] == 0.2 and "reasoning_effort" not in p
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
        "additionalProperties": False,
    }
    p2 = a.build_payload(
        {
            "model": "m",
            "max_tokens": 10,
            "messages": [],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
    )
    assert p2["response_format"]["json_schema"]["schema"] == schema


def test_openai_pdf_document_is_refused():
    a = OpenAICompatAdapter("openai", api_key="sk")
    doc = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "AAA"}}
    with pytest.raises(ProviderUnsupported):
        a.build_payload({"model": "gpt-5", "max_tokens": 5, "messages": [{"role": "user", "content": [doc]}]})


async def test_openai_create_parses_tool_calls_usage_and_auth_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "gpt-5-mini",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_9",
                                    "type": "function",
                                    "function": {"name": "propose_constraints", "arguments": '{"kind":"capacity"}'},
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 30},
                },
            },
        )

    transport, calls = _mock(handler)
    a = OpenAICompatAdapter("openai", api_key="sk-test", transport=transport)
    msg = await a.create(CONVERSATION)
    assert msg.stop_reason == "tool_use"
    assert msg.content[0].type == "tool_use" and msg.content[0].input == {"kind": "capacity"}
    assert msg.content[0].model_dump() == {
        "type": "tool_use",
        "id": "call_9",
        "name": "propose_constraints",
        "input": {"kind": "capacity"},
    }
    assert (msg.usage.input_tokens, msg.usage.output_tokens, msg.usage.cache_read_input_tokens) == (70, 20, 30)
    assert msg._request_id == "chatcmpl-1" and len(calls) == 1


async def test_openai_content_filter_is_a_refusal_and_bad_json_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"finish_reason": "content_filter", "message": {"content": ""}}]})

    transport, _ = _mock(handler)
    msg = await OpenAICompatAdapter("openrouter", api_key="k", transport=transport).create(CONVERSATION)
    assert msg.stop_reason == "refusal" and msg.stop_details.category == "provider_safety"

    def bad(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {"tool_calls": [{"id": "c", "function": {"name": "x", "arguments": "{oops"}}]},
                    }
                ]
            },
        )

    transport, _ = _mock(bad)
    with pytest.raises(ProviderError):
        await OpenAICompatAdapter("openrouter", api_key="k", transport=transport).create(CONVERSATION)


@pytest.mark.parametrize(
    ("status", "needle"), [(401, "authentication"), (404, "not found"), (429, "rate limited"), (500, "500")]
)
async def test_openai_status_errors_never_echo_the_body(status, needle):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "secret prompt echoed sk-abcdef123456"}})

    transport, _ = _mock(handler)
    with pytest.raises(ProviderError) as info:
        await OpenAICompatAdapter("openai", api_key="sk", transport=transport).create(CONVERSATION)
    assert needle in str(info.value) and "secret prompt" not in str(info.value)


async def test_openai_list_models_and_openrouter_pricing_and_azure_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "anthropic/claude-sonnet-5-5",
                        "name": "Claude Sonnet 5.5",
                        "context_length": 1000000,
                        "pricing": {"prompt": "0.000002", "completion": "0.00001"},
                    },
                    {"id": "gpt-5-mini", "created": 1700000000},
                    {"object": "junk"},
                ]
            },
        )

    transport, calls = _mock(handler)
    models = await OpenAICompatAdapter("openrouter", api_key="k", transport=transport).list_models()
    assert [m.id for m in models] == ["anthropic/claude-sonnet-5-5", "gpt-5-mini"]
    assert models[0].price_in == 2.0 and models[0].price_out == 10.0 and models[0].context_window == 1000000

    transport, calls = _mock(handler)
    azure = OpenAICompatAdapter(
        "azure_openai", api_key="az-key", base_url="https://r.openai.azure.com/openai/v1/", transport=transport
    )
    await azure.list_models()
    assert calls[0].headers["api-key"] == "az-key" and "authorization" not in calls[0].headers
    assert str(calls[0].url) == "https://r.openai.azure.com/openai/v1/models"


async def test_openai_connection_error_maps():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    transport, _ = _mock(handler)
    a = OpenAICompatAdapter("openai_compatible", api_key=None, transport=transport)
    with pytest.raises(httpx.ConnectError) as info:
        await a.create(CONVERSATION)
    mapped = a.translate_error(info.value, "m")
    assert isinstance(mapped, ProviderError) and "could not reach" in str(mapped)


async def test_default_stream_replays_events():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "Merhaba"}}], "usage": {}}
        )

    transport, _ = _mock(handler)
    events: list[dict[str, Any]] = []

    async def sink(e: dict[str, Any]) -> None:
        events.append(e)

    msg = await OpenAICompatAdapter("openai", api_key="k", transport=transport).stream(CONVERSATION, sink)
    assert msg.stop_reason == "end_turn" and events == [{"type": "text", "text": "Merhaba"}]


# ------------------------------------------------------------------ Gemini


def test_gemini_payload_translation():
    g = GeminiAdapter(api_key="g-key")
    doc = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "AAA"}}
    conv = {**CONVERSATION, "messages": [*CONVERSATION["messages"], {"role": "user", "content": [doc]}]}
    p = g.build_payload(conv)
    assert p["systemInstruction"] == {"parts": [{"text": "You map rules."}]}
    roles = [c["role"] for c in p["contents"]]
    assert roles == ["user", "model", "user", "user"]
    model_parts = p["contents"][1]["parts"]
    assert model_parts[1]["functionCall"] == {
        "id": "toolu_1",
        "name": "propose_constraints",
        "args": {"kind": "room_pin"},
    }
    fr = p["contents"][2]["parts"][0]["functionResponse"]
    assert fr["name"] == "propose_constraints" and fr["response"] == {"result": '{"ok": true}'}
    assert p["contents"][3]["parts"][0] == {"inlineData": {"mimeType": "application/pdf", "data": "AAA"}}
    decl = p["tools"][0]["functionDeclarations"][0]
    assert decl["parametersJsonSchema"] == TOOL["input_schema"]
    assert p["generationConfig"]["maxOutputTokens"] == 900
    assert p["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


async def test_gemini_create_and_list_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "g-key"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-3-pro",
                            "displayName": "Gemini 3 Pro",
                            "inputTokenLimit": 1048576,
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
                    ]
                },
            )
        assert request.url.path.endswith("/models/gemini-3-pro:generateContent")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "thinking...", "thought": True},
                                {"functionCall": {"name": "propose_constraints", "args": {"kind": "room_pin"}}},
                            ]
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 7, "thoughtsTokenCount": 3},
            },
        )

    transport, _ = _mock(handler)
    g = GeminiAdapter(api_key="g-key", transport=transport)
    msg = await g.create({**CONVERSATION, "model": "gemini-3-pro"})
    assert msg.stop_reason == "tool_use" and msg.content[0].name == "propose_constraints"
    assert len(msg.content) == 1  # the thought part is not content
    assert (msg.usage.input_tokens, msg.usage.output_tokens) == (50, 10)
    models = await g.list_models()
    assert [m.id for m in models] == ["gemini-3-pro"] and models[0].context_window == 1048576


async def test_gemini_safety_block_is_refusal():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    transport, _ = _mock(handler)
    msg = await GeminiAdapter(api_key="k", transport=transport).create({**CONVERSATION, "model": "gemini-3-pro"})
    assert msg.stop_reason == "refusal"


# ------------------------------------------------------------------ Anthropic / Bedrock


@dataclass
class _Model:
    id: str
    display_name: str
    max_input_tokens: int = 1_000_000
    max_tokens: int = 128_000
    created_at: str = "2026-09-01"


class _Pager:
    def __init__(self, items: list[_Model]) -> None:
        self.items = items

    def __aiter__(self):
        async def gen():
            for i in self.items:
                yield i

        return gen()


class _Models:
    def __init__(self, items: list[_Model] | Exception) -> None:
        self.items = items

    def list(self) -> _Pager:
        if isinstance(self.items, Exception):
            raise self.items
        return _Pager(self.items)


class _Messages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True, **kwargs}


class _Raw:
    def __init__(self, models: list[_Model] | Exception) -> None:
        self.models = _Models(models)
        self.messages = _Messages()


async def test_anthropic_list_models_uses_models_endpoint():
    raw = _Raw([_Model("claude-opus-5-5", "Claude Opus 5.5"), _Model("claude-haiku-5-5", "Claude Haiku 5.5")])
    a = AnthropicAdapter("sk-ant-x", "claude-opus-5-5", raw=raw)
    models = await a.list_models()
    assert [m.id for m in models] == ["claude-opus-5-5", "claude-haiku-5-5"]
    assert models[0].context_window == 1_000_000 and models[0].max_output == 128_000


async def test_bedrock_prefixes_model_ids_and_has_no_fallbacks():
    assert bedrock_model_id("claude-opus-5-5") == "anthropic.claude-opus-5-5"
    assert bedrock_model_id("us.anthropic.claude-opus-5-5") == "us.anthropic.claude-opus-5-5"
    raw = _Raw([])
    b = BedrockAdapter(region="eu-central-1", api_key="br-key", raw=raw)
    assert b.use_fallbacks is False
    await b.create({"model": "claude-sonnet-5-5", "max_tokens": 1, "messages": []})
    assert raw.messages.calls[0]["model"] == "anthropic.claude-sonnet-5-5"
    with pytest.raises(ProviderError):
        BedrockAdapter(region="", api_key="k", raw=raw)


async def test_bedrock_lists_through_boto3_when_mantle_cannot():
    class Boto:
        def list_foundation_models(self, byProvider: str) -> dict[str, Any]:
            assert byProvider == "Anthropic"
            return {
                "modelSummaries": [
                    {
                        "modelId": "anthropic.claude-opus-5-5",
                        "modelName": "Claude Opus 5.5",
                        "outputModalities": ["TEXT"],
                    },
                    {"modelId": "anthropic.embed", "modelName": "x", "outputModalities": ["EMBEDDING"]},
                ]
            }

    b = BedrockAdapter(region="us-east-1", api_key="k", raw=_Raw(RuntimeError("no /v1/models")), boto_client=Boto())
    models = await b.list_models()
    assert [m.id for m in models] == ["anthropic.claude-opus-5-5"]


def test_anthropic_errors_map_to_short_texts():
    import anthropic

    a = AnthropicAdapter("sk-ant-x", "claude-opus-5-5", raw=_Raw([]))
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.AuthenticationError("bad key sk-ant-123", response=httpx.Response(401, request=req), body=None)
    assert "authentication" in str(a.translate_error(exc, "claude-opus-5-5"))
    other = ValueError("x")
    assert a.translate_error(other, "m") is other
    assert json.dumps(PROVIDERS["bedrock"].to_dict())
