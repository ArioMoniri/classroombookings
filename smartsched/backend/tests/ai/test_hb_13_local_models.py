"""HB-13 local-model degrade fixes (architecture doc §5.8): a forced single tool per provider, JSON-schema emulation
when the server has no named tool choice, broken tool JSON answered as ``INVALID_JSON``, scanned PDFs as page images
on an OpenAI-compatible vision model, ``max_tokens`` clamped to the context window (``context_too_small`` before
sending), a no-tools model refused for tool calls at call time, and "local" decided by the resolved address.

No network: Anthropic is the scripted fake SDK, every OpenAI-compatible server an ``httpx.MockTransport``, DNS a
patched resolver.
"""

from __future__ import annotations

import io
import json
from typing import Any

import httpx
import pytest
from app.ai import capabilities as caps
from app.ai import catalog
from app.ai import gateway as gw
from app.ai import pipeline
from app.ai.client import AIClient, get_client
from app.ai.context import ai_scope
from app.ai.elicit import elicit_constraints
from app.ai.ingest import extract_preferences
from app.ai.pipeline import AIGuardError
from app.ai.providers import url_guard
from app.ai.providers.base import INVALID_INPUT_KEY
from app.ai.providers.openai_compat import OpenAICompatAdapter
from app.models.ai_usage import AIUsage
from app.services import ai_usage as meter
from pypdf import PdfWriter
from sqlalchemy import select

from tests.ai.conftest import empty_params, empty_selector, enable_intake, proposal, tool

LOCAL = "http://127.0.0.1:11434/v1"


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    pipeline.TEST_TRANSPORT[0] = None
    yield
    pipeline.TEST_TRANSPORT[0] = None
    pipeline.reset_state()
    meter.reset_state()


def _pin(page: int | None = None) -> dict[str, Any]:
    extra = {"source_ref": page} if page is not None else {}
    return {
        "proposals": [
            proposal(
                "room_pin",
                selector=empty_selector(course_codes=["PHAR 240"]),
                params=empty_params(room_codes=["A 206"]),
                **extra,
            )
        ],
        "section_edits": [],
        "unparsed": [],
    }


def _completion(content: str = "", calls: list[dict[str, Any]] | None = None, finish: str | None = None):
    msg: dict[str, Any] = {"content": content}
    if calls:
        msg["tool_calls"] = calls
    return httpx.Response(
        200,
        json={
            "choices": [{"finish_reason": finish or ("tool_calls" if calls else "stop"), "message": msg}],
            "usage": {"prompt_tokens": 400, "completion_tokens": 60},
        },
    )


def _recorder(answer) -> tuple[list[dict[str, Any]], httpx.MockTransport]:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        bodies.append(body)
        return answer(body)

    return bodies, httpx.MockTransport(handler)


async def _route_local(session, feature: str, model: str, capabilities: dict[str, Any] | None) -> None:
    entry: dict[str, Any] = {"id": model}
    if capabilities is not None:
        entry["capabilities"] = caps.record(**capabilities)
    await gw.store_synced_models(session, "openai_compatible", [entry], None)
    await gw.put_json(session, gw.ROUTES_KEY, {"features": {feature: {"provider": "openai_compatible", "model": model}}})
    await gw.put_json(
        session, "ai.provider.openai_compatible.config", {"base_url": LOCAL, "enabled": True, "allow_local": True}
    )
    await session.commit()


async def _rows(session) -> list[AIUsage]:
    q = select(AIUsage).order_by(AIUsage.id).execution_options(populate_existing=True)
    return list((await session.execute(q)).scalars())


# ------------------------------------------------------------------ forced single tool, per provider


async def test_force_tool_on_claude_is_sent_as_auto_with_one_call(session, seed, fake_sdk):
    """Opus 5.5 / Sonnet 5.5 / Fable 5.1 answer a forced ``tool`` choice with a 400: Claude gets ``auto``."""
    fake_sdk.script = [tool("propose_constraints", _pin())]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await elicit_constraints(session, seed.term_id, "PHAR 240 A 206'da olsun", "tr", client=client)
    assert out.proposals and out.proposals[0].status == "ok"
    assert fake_sdk.calls[0]["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}


async def test_force_tool_is_a_named_function_on_a_server_with_tool_choice():
    bodies, transport = _recorder(
        lambda b: _completion(calls=[{"id": "c1", "function": {"name": "propose_constraints", "arguments": "{}"}}])
    )
    adapter = OpenAICompatAdapter("openai_compatible", api_key=None, base_url=LOCAL, transport=transport)
    adapter.capabilities = caps.record(tools=True, tool_choice=True)
    client = AIClient("", "qwen3:14b", adapter=adapter, provider="openai_compatible")
    msg = await client.complete(
        system="s",
        messages=[{"role": "user", "content": "x"}],
        tools=[catalog.PROPOSE_CONSTRAINTS_TOOL],
        force_tool="propose_constraints",
    )
    assert bodies[0]["tool_choice"] == {"type": "function", "function": {"name": "propose_constraints"}}
    assert bodies[0]["parallel_tool_calls"] is False
    assert msg.content[0].type == "tool_use"


async def test_rules_on_an_ollama_like_server_without_tool_choice_produce_proposals(session, seed):
    """No named tool choice: the tool's schema goes out as ``response_format`` and the JSON comes back as the call."""
    await _route_local(session, "rules", "qwen3:14b", {"tools": True, "tool_choice": False, "json_schema": True})
    bodies, transport = _recorder(lambda b: _completion(json.dumps(_pin())))
    pipeline.TEST_TRANSPORT[0] = transport
    client = await get_client(session, feature="rules")
    out = await elicit_constraints(session, seed.term_id, "PHAR 240 A 206'da olsun", "tr", client=client)
    assert [p.status for p in out.proposals] == ["ok"]
    body = bodies[0]
    assert "tools" not in body and body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "propose_constraints"
    [row] = await _rows(session)
    assert (row.feature, row.provider, row.outcome) == ("rules", "openai_compatible", "ok")


async def test_a_server_that_ignores_the_named_choice_gets_one_emulated_retry():
    answers = iter([_completion("Sure, here are the rules: ..."), _completion(json.dumps(_pin()))])
    bodies, transport = _recorder(lambda b: next(answers))
    adapter = OpenAICompatAdapter("openai_compatible", api_key=None, base_url=LOCAL, transport=transport)
    adapter.capabilities = caps.record(tools=True, tool_choice=True)
    client = AIClient("", "m", adapter=adapter, provider="openai_compatible")
    msg = await client.complete(
        system="s",
        messages=[{"role": "user", "content": "x"}],
        tools=[catalog.PROPOSE_CONSTRAINTS_TOOL],
        force_tool="propose_constraints",
    )
    assert len(bodies) == 2 and "response_format" in bodies[1] and "tools" not in bodies[1]
    assert msg.content[0].name == "propose_constraints" and msg.usage.input_tokens == 800


async def test_force_tool_unknown_name_is_not_forced(fake_sdk):
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    fake_sdk.script = [tool("propose_constraints", _pin())]
    await client.complete(
        system="s", messages=[{"role": "user", "content": "x"}], tools=[catalog.PROPOSE_CONSTRAINTS_TOOL],
        force_tool="no_such_tool",
    )  # fmt: skip
    assert fake_sdk.calls[0]["tool_choice"]["type"] == "auto"


# ------------------------------------------------------------------ invalid tool JSON


async def test_broken_tool_arguments_become_an_invalid_json_tool_result():
    bodies, transport = _recorder(
        lambda b: _completion(calls=[{"id": "c1", "function": {"name": "find_sections", "arguments": "{oops"}}])
    )
    adapter = OpenAICompatAdapter("openai_compatible", api_key=None, base_url=LOCAL, transport=transport)
    msg = await adapter.create(
        {"model": "m", "max_tokens": 50, "messages": [{"role": "user", "content": "x"}], "tools": catalog.CHAT_TOOLS}
    )
    [call] = msg.content
    assert call.type == "tool_use" and call.input == {INVALID_INPUT_KEY: "{oops"}
    assert catalog.validate_tool_input("find_sections", call.input)  # refused by the strict schema -> INVALID_JSON


# ------------------------------------------------------------------ scanned PDF on an OpenAI-compatible VLM


def _scan(pages: int = 2) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=280)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


async def test_chat_upload_scanned_pdf_works_on_an_openai_compatible_vlm(session, seed):
    await enable_intake(session, vision=True)
    await _route_local(
        session,
        "intake",
        "qwen2.5vl:7b",
        {"tools": True, "tool_choice": True, "json_schema": True, "vision": True, "pdf": False},
    )
    bodies, transport = _recorder(
        lambda b: _completion(
            calls=[{"id": "c1", "function": {"name": "propose_constraints", "arguments": json.dumps(_pin(2))}}]
        )
    )
    pipeline.TEST_TRANSPORT[0] = transport
    client = await get_client(session, feature="intake")
    with ai_scope("intake"):
        out = await extract_preferences(session, seed.term_id, _scan(2), "tarama.pdf", "tr", client=client)
    assert out.needs_ai is False and out.proposals[0].source_ref["page"] == 2
    parts = bodies[0]["messages"][-1]["content"]
    images = [p for p in parts if p["type"] == "image_url"]
    assert len(images) == 2 and all(p["image_url"]["url"].startswith("data:image/png;base64,") for p in images)
    assert not any(p.get("type") == "document" for p in parts)


# ------------------------------------------------------------------ context window


async def test_max_tokens_is_clamped_to_the_context_window(session):
    await _route_local(session, "rules", "small", {"tools": True, "json_schema": True, "context_window": 8192})
    bodies, transport = _recorder(lambda b: _completion("Tamam."))
    pipeline.TEST_TRANSPORT[0] = transport
    client = await get_client(session, feature="rules")
    with ai_scope("rules"):
        await client.complete(system="Map rules.", messages=[{"role": "user", "content": "PHAR 240"}], max_tokens=32000)
    assert 1000 < bodies[0]["max_tokens"] < 8192


async def test_context_too_small_is_refused_before_sending(session):
    await _route_local(session, "rules", "tiny", {"tools": True, "json_schema": True, "context_window": 2048})
    bodies, transport = _recorder(lambda b: _completion("never"))
    pipeline.TEST_TRANSPORT[0] = transport
    client = await get_client(session, feature="rules")
    long_text = "PHAR 240 pazartesi A 206 dersliğinde olsun. " * 400  # ~ 5 000 tokens
    with ai_scope("rules"), pytest.raises(AIGuardError) as exc:
        await client.complete(system="Map rules.", messages=[{"role": "user", "content": long_text}], max_tokens=4000)
    assert exc.value.status_code == 422 and exc.value.code == "context_too_small"
    assert exc.value.detail["message_tr"] and exc.value.detail["message_en"]
    assert bodies == []
    [row] = await _rows(session)
    assert row.outcome == "refused_by_guardrail" and row.reason_code == "context_too_small"


def test_fit_context_counts_images_and_pages_not_base64():
    big_pdf = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "A" * 400_000}}
    kwargs = {"system": "s", "messages": [{"role": "user", "content": [big_pdf, {"type": "text", "text": "read"}]}]}
    assert caps.estimate_input_tokens(kwargs) < 20_000
    assert caps.fit_context({"context_window": 32768}, kwargs, 64000) is not None
    assert caps.fit_context({"context_window": None}, kwargs, 64000) == 64000


# ------------------------------------------------------------------ a no-tools model at call time


async def test_a_tool_call_to_a_model_without_tools_is_refused_at_call_time(session):
    await _route_local(session, "chat", "llava:7b", {"tools": False, "json_schema": False, "vision": True})
    gw_routes = await gw.get_routes(session)
    assert gw_routes["features"]["chat"]["model"] == "llava:7b"  # stored before the route check existed
    bodies, transport = _recorder(lambda b: _completion("never"))
    pipeline.TEST_TRANSPORT[0] = transport
    await gw.put_json(session, "ai.provider.openai_compatible.transfer", {"kvkk_mechanism": "domestic"})
    await session.commit()
    client = await get_client(session, feature="chat")
    with ai_scope("chat"), pytest.raises(AIGuardError) as exc:
        await client.complete(
            system="s", messages=[{"role": "user", "content": "PHAR 240"}], tools=catalog.CHAT_TOOLS, max_tokens=500
        )
    assert exc.value.status_code == 422 and exc.value.code == "model_lacks_capability"
    assert "araç" in exc.value.detail["message_tr"] and bodies == []


# ------------------------------------------------------------------ local by resolved address


def _resolver(answer: list[str]):
    def resolve(host: str, port: int) -> list[str]:
        return answer

    return resolve


def test_is_local_url_decides_by_the_resolved_address():
    assert not gw.is_local_url("http://gpu.local:11434/v1", resolver=_resolver(["93.184.216.34"]))
    assert gw.is_local_url("https://llm.uni.edu.tr/v1", resolver=_resolver(["10.1.2.3"]))
    assert not gw.is_local_url("https://llm.uni.edu.tr/v1", resolver=_resolver(["10.1.2.3", "93.184.216.34"]))
    assert not gw.is_local_url("http://nowhere.invalid/v1", resolver=_resolver([]))


@pytest.mark.parametrize(("address", "needs_record"), [("93.184.216.34", True), ("192.168.1.20", False)])
async def test_transfer_record_follows_the_resolved_address(session, monkeypatch, address, needs_record):
    monkeypatch.setattr(url_guard, "_resolve", _resolver([address]))
    await gw.store_synced_models(session, "openai_compatible", [{"id": "m"}], None)
    await gw.put_json(session, gw.ROUTES_KEY, {"features": {"chat": {"provider": "openai_compatible", "model": "m"}}})
    await gw.put_json(
        session,
        "ai.provider.openai_compatible.config",
        {"base_url": "http://gpu.local:11434/v1", "enabled": True, "allow_local": True},
    )
    await session.commit()
    client = await get_client(session, feature="chat")
    assert client.gateway is not None
    assert client.gateway.transfer["openai_compatible"] is (not needs_record)
