"""Live smoke test against the real Claude API. Skipped unless ANTHROPIC_API_KEY is set (costs a few cents).

Checks what mocks cannot: the key works, and the strict tool schemas compile on the API side
(``propose_constraints`` and the full chat tool set in one request).
"""

from __future__ import annotations

import os

import pytest
from app.ai.chat import handle_chat
from app.ai.client import DEFAULT_MODEL, AIClient
from app.ai.client import test_connection as probe_connection
from app.ai.elicit import elicit_constraints

pytestmark = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")

MODEL = os.environ.get("SMARTSCHED_LIVE_MODEL", DEFAULT_MODEL)


async def test_live_connection():
    ok, detail = await probe_connection(os.environ["ANTHROPIC_API_KEY"], MODEL)
    assert ok, detail


async def test_live_elicit_and_chat(session, seed):
    client = AIClient(os.environ["ANTHROPIC_API_KEY"], MODEL)
    out = await elicit_constraints(
        session,
        seed.term_id,
        "PHAR 240 A 206'da kalsın; Psikoloji 1. sınıf A 204'e girmesin; Z 999 dersliğini kullanma.",
        "tr",
        client=client,
    )
    assert out.proposals, out.assistant_message
    assert any(p.status == "ok" for p in out.proposals)
    chat = await handle_chat(
        session, seed.run_id, "NRS 450 neden C 301'de? Daha küçük bir derslik öner.", "tr", client=client
    )
    assert chat.assistant_message
