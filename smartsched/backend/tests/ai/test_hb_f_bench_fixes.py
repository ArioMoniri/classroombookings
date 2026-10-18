"""HB-F: the re-bench after HB-E (docs/testing/hb-17-local-bench-2026-10-18.md, "Re-bench after HB-E"), gateway side.

* bug A: the probe gives each call 512 output tokens (a thinking model such as ``qwen3:14b`` spends 64 on reasoning
  and stops at ``length`` with no tool call), and a ``max_tokens`` stop with no content is *unknown* (``None``), so
  sync's ``tools: true`` stays and the helper route is not refused;
* bug C: the helper's first message lists the next 7 days with their dates, so the model never computes
  weekday -> date itself ("perşembe" on Monday 2026-02-16 is 2026-02-19);
* bug D: a probe call that fails on the transport (connection lost, timeout) or with a 5xx is unknown, not ``False``;
  a 4xx is still a fact (``False``).

No network: servers are ``httpx.MockTransport`` / scripted fakes; Anthropic is the scripted fake SDK.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from app.ai import capabilities as caps
from app.ai import gateway as gw
from app.ai import helper_turn as ht
from app.ai import pipeline
from app.ai.providers.openai_compat import _status_error
from app.core.db import get_session_factory
from app.core.security import hash_password
from app.models import User
from app.services import ai_usage as meter
from app.services import bookings as bsvc
from app.services import kvkk
from app.services import settings_service as ss
from app.services.bookings_perms import load_access

from tests.ai.conftest import text
from tests.ai.test_hb_17_local_fixes import MODEL, Ollama, _adapter, _admin_local

PROBE_KEYS = ("tools", "tool_choice", "strict_tools", "json_schema", "vision")


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    pipeline.TEST_TRANSPORT[0] = None
    yield
    pipeline.TEST_TRANSPORT[0] = None
    pipeline.reset_state()
    meter.reset_state()


class ThinkingOllama(Ollama):
    """A thinking model (qwen3 on Ollama): it reasons for ``thinks`` tokens before answering. A call with a smaller
    ``max_tokens`` ends at ``finish_reason: length`` with empty ``content`` (the reasoning is not content)."""

    def __init__(self, *, thinks: int, **kw: Any) -> None:
        super().__init__(**kw)
        self.thinks = thinks

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions") and not self.down:
            body = json.loads(request.content)
            if int(body.get("max_tokens") or 0) < self.thinks:
                self.chat.append(body)
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"finish_reason": "length", "message": {"content": "", "reasoning": "Hmm, the user…"}}
                        ],
                        "usage": {"prompt_tokens": 40, "completion_tokens": body.get("max_tokens") or 0},
                    },
                )
        return super().handler(request)


class FlakyOllama(Ollama):
    """Answers the first ``ok_calls`` chat calls, then the connection drops (the bench's lost tunnel)."""

    def __init__(self, *, ok_calls: int, **kw: Any) -> None:
        super().__init__(**kw)
        self.ok_calls = ok_calls

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions") and len(self.chat) >= self.ok_calls:
            raise httpx.ConnectError("connection reset")
        return super().handler(request)


class Scripted:
    """A bare adapter: each ``create`` pops the next item; an exception is raised, anything else returned."""

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.capabilities: dict[str, Any] | None = None
        self.sent: list[dict[str, Any]] = []

    async def create(self, kwargs: dict[str, Any]) -> Any:
        self.sent.append(kwargs)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, BaseException):
            raise item
        return item


def _cut_off() -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="max_tokens", content=[], usage=SimpleNamespace(input_tokens=40, output_tokens=512)
    )


# ------------------------------------------------------------------ bug A: thinking models and max_tokens


async def test_every_probe_call_gets_512_output_tokens():
    adapter = Scripted(_cut_off())
    await caps.probe(adapter, MODEL)
    assert adapter.sent and {k["max_tokens"] for k in adapter.sent} == {512}


async def test_a_max_tokens_stop_with_no_content_is_unknown_not_false():
    found, usage = await caps.probe(Scripted(_cut_off()), MODEL)
    assert usage.calls >= 3
    assert {k: found[k] for k in PROBE_KEYS} == dict.fromkeys(PROBE_KEYS)


async def test_a_thinking_model_that_needs_300_tokens_is_probed_correctly():
    server = ThinkingOllama(thinks=300)  # more than the old 64, less than 512
    found, _ = await caps.probe(_adapter(server), MODEL)
    assert found["tools"] is True and found["json_schema"] is True
    assert found["tool_choice"] is False  # Ollama ignores the named choice: still a fact


async def test_a_cut_off_probe_keeps_syncs_tools_and_the_route_is_accepted(client):
    h = await _admin_local(client)
    server = ThinkingOllama(thinks=10**6)  # every probe call ends at max_tokens with empty content
    pipeline.TEST_TRANSPORT[0] = server.transport()
    assert (await client.post("/api/v1/ai/admin/providers/openai_compatible/sync", headers=h)).status_code == 200
    r = await client.post(
        "/api/v1/ai/admin/providers/openai_compatible/test?probe=true", json={"model": MODEL}, headers=h
    )
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert all(r.json()["capabilities"][k] is None for k in PROBE_KEYS), r.json()["capabilities"]
    assert server.chat and all(b["max_tokens"] == 512 for b in server.chat)
    assert r.json()["effective"]["tools"] is True  # sync's fact stands
    async with get_session_factory()() as s:
        assert (await gw.model_capabilities(s, "openai_compatible"))[MODEL]["tools"] is True
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"helper": {"provider": "openai_compatible", "model": MODEL}}},
        headers=h,
    )
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ bug D: transport errors are unknown


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("connection reset"),
        httpx.ReadTimeout("timed out"),
        TimeoutError(),
        _status_error(502, "openai_compatible"),
        _status_error(503, "openai_compatible"),
        anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")),
        anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")),
    ],
    ids=["connect", "read-timeout", "timeout", "502", "503", "sdk-connection", "sdk-timeout"],
)
async def test_a_transport_error_timeout_or_5xx_is_unknown(exc: Exception):
    found, _ = await caps.probe(Scripted(exc), MODEL)
    assert {k: found[k] for k in PROBE_KEYS} == dict.fromkeys(PROBE_KEYS)


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_a_4xx_is_still_a_fact(status: int):
    found, _ = await caps.probe(Scripted(_status_error(status, "openai_compatible")), MODEL)
    assert found["tool_choice"] is False and found["tools"] is False
    assert found["json_schema"] is False and found["vision"] is False


async def test_a_server_lost_midway_keeps_what_it_proved_and_leaves_the_rest_unknown():
    # the forced call (2 requests: the adapter's emulated retry after the prose answer) and the auto retry answer,
    # then the tunnel drops
    server = FlakyOllama(ok_calls=3)
    found, usage = await caps.probe(_adapter(server), MODEL)
    assert usage.calls == 2
    assert found["tools"] is True and found["tool_choice"] is False
    assert found["json_schema"] is None and found["vision"] is None


# ------------------------------------------------------------------ bug C: the next 7 days with dates


async def test_the_first_helper_message_lists_the_next_seven_days(session, fake_sdk, monkeypatch):
    async def fake_now(_session):  # type: ignore[no-untyped-def]
        return datetime(2026, 2, 16, 8, 0)  # Monday

    monkeypatch.setattr(bsvc, "now_local", fake_now)
    u = User(email="hbf@uni.edu.tr", password_hash=hash_password("parola-1234"), role="TEACHER", full_name="Ayşe")
    session.add(u)
    await session.commit()
    await kvkk.grant(session, u, "ai_personal")
    await ss.set_value(session, "anthropic_api_key", "sk-ant-test-0000")
    await gw.put_json(
        session, gw.ROUTES_KEY, {"features": {"helper": {"provider": "anthropic", "model": "claude-opus-5-5"}}}
    )
    await session.commit()
    fake_sdk.script = [text("Perşembe için boş derslikleri bulabilirim.")]
    result = await ht.run_turn(session, await load_access(session, u), "perşembe boş derslik var mı?", "tr")
    assert result.mode == "ai"
    first = fake_sdk.calls[0]["messages"][0]
    body = first["content"] if isinstance(first["content"], str) else json.dumps(first["content"], ensure_ascii=False)
    assert "Today is 2026-02-16 (Pazartesi" in body  # HB-17 bug 3 line kept
    assert "Perşembe 2026-02-19" in body and "Thursday" in body
    assert "Salı 2026-02-17" in body and "Pazartesi 2026-02-23" in body  # tomorrow ... a week from today
    assert "2026-02-24" not in body
