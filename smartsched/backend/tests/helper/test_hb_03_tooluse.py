"""The model's tool calls are validated before anything runs (HB-03 / HB-06 seam, ``app.ai.helper.tooluse``).

The turn loop (lane HB-B) hands every assistant message to :func:`tooluse.apply_message`. These tests drive it with
real ``anthropic`` SDK message objects (the SDK is mocked: no network) on the Bahar 2026 data:

* a refusal / max_tokens stop runs no tool;
* a tool that was not offered this turn (a write after taint, an unknown name) is refused, nothing runs;
* invalid input (an extra field, a wrong type: RA-05 / RA-15) answers ``invalid_args`` and writes nothing;
* a read answers its card; a write answers a ``confirm`` card, and the confirm token never reaches the model;
* every card validates against ``helper.card.v1``; all results go back in **one** user message.

A live smoke test sends the strict tool list to Claude and checks every tool input it returns against the registry
models; it is skipped unless ``ANTHROPIC_API_KEY`` is set.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import pytest
from anthropic.types import Message
from app.ai.helper import schema, tooluse
from app.ai.helper.actions import registry as reg
from app.core import db as dbmod
from app.models import Booking, User
from app.models.helper import HelperActionInvocation
from app.services.bookings_perms import load_access
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.helper.support import personas

THU = date(2026, 2, 19)
MODEL = "claude-opus-5-5"


def _msg(*blocks: dict[str, Any], stop: str = "tool_use") -> Message:
    return Message.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": MODEL,
            "content": list(blocks),
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
    )


def _use(i: int, name: str, inp: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{i:02d}", "name": name, "input": inp}


class _FakeMessages:
    """``client.messages`` of a mocked SDK client: scripted replies, the requests kept for the asserts."""

    def __init__(self, replies: list[Message]) -> None:
        self.replies, self.requests = list(replies), []  # type: list[Message], list[dict[str, Any]]

    async def create(self, **kw: Any) -> Message:
        self.requests.append(kw)
        return self.replies.pop(0)


async def _count(model, *where) -> int:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(model).where(*where))).scalar_one())


async def test_hb_03_tool_calls_are_validated_before_they_run(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    async with dbmod.get_session_factory()() as session:
        user = await session.get(User, people["teacher"].uid)
        assert user is not None
        access = await load_access(session, user)
        ctx = reg.Ctx(session, access)
        tools = reg.tools_for(access)
        offered = tooluse.offered(tools)
        assert "create_booking" in offered and "decide_approval" not in offered
        for t in tools:  # the strict tool shape the Messages API takes
            assert t["strict"] is True and t["input_schema"]["additionalProperties"] is False

        # stop reasons are checked before any tool runs
        for stop in ("refusal", "max_tokens"):
            with pytest.raises(tooluse.TurnStopped) as stopped:
                await tooluse.apply_message(ctx, _msg(_use(1, "my_bookings", {}), stop=stop), offered=offered)
            assert stopped.value.stop_reason == stop

        before = await _count(Booking)
        fake = _FakeMessages(
            [
                _msg(
                    {"type": "text", "text": "Bakıyorum."},
                    _use(
                        1,
                        "find_free_rooms",
                        {
                            "date": THU.isoformat(),
                            "start": "08:30",
                            "end": "09:20",
                            "headcount": 0,
                            "building": "",
                            "text": "",
                        },
                    ),
                    _use(
                        2,
                        "create_booking",
                        {"room": "A 102", "date": THU.isoformat(), "period_id": env.periods["P1"], "notes": ""},
                    ),
                    _use(
                        3,
                        "create_booking",
                        {"room": "A 102", "date": THU.isoformat(), "period_id": "P1", "notes": "", "on_behalf_of": 7},
                    ),
                    _use(
                        4, "decide_approval", {"request_id": 1, "decision": "approve", "reason_code": "", "reason": ""}
                    ),
                    _use(5, "drop_all_tables", {}),
                    _use(6, "my_bookings", "not an object"),  # type: ignore[arg-type]
                )
            ]
        )
        reply = await fake.create(model=MODEL, max_tokens=4000, tools=tools, messages=[])
        out = await tooluse.apply_message(ctx, reply, offered=offered)

    assert [o.tool_use_id for o in out] == [f"toolu_{i:02d}" for i in range(1, 7)]
    by = {o.tool_use_id: o for o in out}
    for o in out:
        schema.validate_card(o.card)
    assert by["toolu_01"].card["type"] == "list" and not by["toolu_01"].is_error
    c = by["toolu_02"].card
    assert c["type"] == "confirm" and c["token"] and not by["toolu_02"].is_error
    seen = by["toolu_02"].model_content()
    assert c["token"] not in seen and "token" not in json.loads(seen)
    assert json.loads(seen)["waiting_for"] == "the_user_button"
    for bad, code in (
        ("toolu_03", "invalid_args"),
        ("toolu_04", "not_offered"),
        ("toolu_05", "not_offered"),
        ("toolu_06", "invalid_args"),
    ):
        assert by[bad].is_error and by[bad].card["code"] == code, (bad, by[bad].card)
    assert "on_behalf_of" in by["toolu_03"].model_content()  # the model learns what to fix (RA-15)
    # nothing was written by the model's turn: no booking, no invocation row (only the button writes)
    assert await _count(Booking) == before and await _count(HelperActionInvocation) == 0

    msg = tooluse.tool_results(out)
    assert msg["role"] == "user" and len(msg["content"]) == 6  # all results in ONE user message
    assert all(b["type"] == "tool_result" for b in msg["content"])
    assert [b["is_error"] for b in msg["content"]] == [False, False, True, True, True, True]
    assert all(c["token"] not in b["content"] for b in msg["content"])


async def test_hb_03_tainted_reads_drop_writes_for_the_rest_of_the_turn(env) -> None:  # noqa: F811
    reg.RATE.reset()
    people = await personas(env)
    async with dbmod.get_session_factory()() as session:
        user = await session.get(User, people["approver"].uid)
        assert user is not None
        access = await load_access(session, user)
        ctx = reg.Ctx(session, access)
        tainting = [a.name for a in reg.permitted(access) if a.taints]
        assert tainting, "an action that returns other people's free text is marked taints (RA-02)"
        offered = tooluse.offered(reg.tools_for(access))
        out = await tooluse.apply_message(ctx, _msg(_use(1, tainting[0], {})), offered=offered)
        assert out[0].taints is True
        assert tooluse.writes_allowed_after(out) is False
        assert not any(reg.get(n).kind == "write" for n in tooluse.offered(reg.tools_for(access, allow_writes=False)))  # type: ignore[union-attr]


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="live smoke test: set ANTHROPIC_API_KEY")
def test_hb_03_live_strict_tools_smoke() -> None:
    """Claude accepts the strict tool list and every tool input it returns passes the registry models."""
    import anthropic

    class _Access:
        perms = frozenset({"room.view", "book_single.create"})

    tools = reg.tools_for(_Access())  # type: ignore[arg-type]
    client = anthropic.Anthropic()
    msg = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system="You are Yardımcı, the SmartSched helper. Use a tool for every request.",
        tools=tools,  # type: ignore[arg-type]
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": "19 Şubat 2026 perşembe ilk ders saatinde A 102'yi rezerve et."}],
    )
    if msg.stop_reason == "refusal":
        pytest.skip("the model declined (stop_reason refusal)")
    uses = [b for b in msg.content if b.type == "tool_use"]
    assert msg.stop_reason == "tool_use" and uses, msg
    names = tooluse.offered(tools)
    for b in uses:
        assert b.name in names
        a = reg.get(b.name)
        assert a is not None
        reg.parse_args(a, b.input)  # the model's output is validated before anything could run
