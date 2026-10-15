"""ROADMAP Phase 3 AI backlog: streaming chat (SSE) with ``eager_input_streaming`` + client-side validation.

``POST /runs/{id}/chat/stream`` answers ``text/event-stream``: ``text`` deltas while the model writes, ``tool``
events when a read tool ran or an edit was recorded, then ``done`` with the same body as ``POST /runs/{id}/chat``.
Every tool of a streamed request carries ``eager_input_streaming: true`` (and stays ``strict``). Because the
server no longer validates streamed tool input, the client does: unparseable JSON (``ValueError`` from the
stream) re-issues the turn (bounded), an input that fails the schema gets an ``INVALID_JSON`` error result and
is never executed, a ``max_tokens`` turn with a tool call is never acted on. Nothing is applied either way.
"""

from __future__ import annotations

import json

from app.core.db import get_session_factory
from app.models import ChatMessage
from sqlalchemy import select

from tests.ai.conftest import BadJSON, Block, Message, seed_small, store_key, text, tool, tools
from tests.api_fixtures import login


def _move(aid: int, room: str) -> dict:
    return {
        "assignment_id": aid,
        "day": 0,
        "start_period": 0,
        "end_period": 0,
        "room_codes": [room],
        "weeks": [],
        "update_request": False,
        "reason": "t",
    }


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for chunk in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


async def _setup(client, key: bool = True):
    h = await login(client)
    async with get_session_factory()() as s:
        sd = await seed_small(s)
        if key:
            await store_key(s)
    return h, sd


async def test_stream_emits_text_tools_and_done(client, fake_sdk):
    h, sd = await _setup(client)
    fake_sdk.script = [
        tool("find_assignments", {"query": "NRS 450", "room_code": "", "day": 0, "week": 0, "limit": 5}, say="Bakıyorum."),
        tools(("move_event", _move(sd.assignments["NRS450"], "A 206"))),
        text("NRS 450'yi A 206'ya taşımayı öneriyorum."),
    ]
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/stream", json={"message": "NRS 450 A 206", "lang": "tr"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = _events(r.text)
    kinds = [k for k, _ in ev]
    assert "text" in kinds and kinds[-1] == "done"
    assert "".join(d["text"] for k, d in ev if k == "text").startswith("Bakıyorum.")
    tool_ev = [d for k, d in ev if k == "tool"]
    assert [t["name"] for t in tool_ev] == ["find_assignments", "move_event"] and all(t["ok"] for t in tool_ev)
    done = ev[-1][1]
    assert done["proposed_diff"]["operations"][0]["op"] == "move" and done["message_id"]
    # every request was streamed; every tool eager + strict
    assert all(c["stream"] for c in fake_sdk.calls)
    for t in fake_sdk.calls[0]["tools"]:
        assert t["eager_input_streaming"] is True and t["strict"] is True
    async with get_session_factory()() as s:
        assert len((await s.execute(select(ChatMessage))).scalars().all()) == 2  # stored like POST /chat


async def test_unparseable_stream_is_reissued_and_invalid_input_never_runs(client, fake_sdk):
    h, sd = await _setup(client)
    truncated = {"assignment_id": sd.assignments["NRS450"], "room_codes": ["A 2"]}  # tolerant parse of a cut input
    fake_sdk.script = [
        BadJSON(),  # ValueError from the stream iterator: no tool_use_id to answer -> re-issue the turn
        tools(("move_event", truncated)),
        text("Girdi hatalıydı; tekrar deneyin."),
    ]
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/stream", json={"message": "taşı", "lang": "tr"}, headers=h)
    ev = _events(r.text)
    done = ev[-1]
    assert done[0] == "done" and done[1]["proposed_diff"] is None  # nothing recorded from an invalid input
    assert len(fake_sdk.calls) == 3
    result = fake_sdk.calls[2]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "INVALID_JSON" in json.loads(result["content"])


async def test_max_tokens_tool_turn_is_not_acted_on(client, fake_sdk):
    h, sd = await _setup(client)
    cut = Message(
        [Block("tool_use", name="move_event", input=_move(sd.assignments["NRS450"], "A 206"), id="toolu_cut")],
        stop_reason="max_tokens",
    )
    fake_sdk.script = [cut]
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/stream", json={"message": "taşı", "lang": "tr"}, headers=h)
    kind, done = _events(r.text)[-1]
    assert kind == "done" and done["proposed_diff"] is None


async def test_stream_errors_before_streaming(client, fake_sdk):
    h, sd = await _setup(client, key=False)
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/stream", json={"message": "x"}, headers=h)
    assert r.status_code == 409
    r = await client.post("/api/v1/runs/999999/chat/stream", json={"message": "x"}, headers=h)
    assert r.status_code == 404
    assert not fake_sdk.calls


async def test_upstream_error_mid_stream_is_an_error_event(client, fake_sdk):
    import anthropic
    import httpx

    h, sd = await _setup(client)
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_sdk.script = [anthropic.RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)]
    r = await client.post(f"/api/v1/runs/{sd.run_id}/chat/stream", json={"message": "x"}, headers=h)
    kind, data = _events(r.text)[-1]
    assert kind == "error" and data["status"] == 502 and "rate limited" in data["detail"]
