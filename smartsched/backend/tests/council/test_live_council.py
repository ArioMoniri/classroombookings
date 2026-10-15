"""Live council test against the real Claude API. Skipped unless ANTHROPIC_API_KEY is set (costs cents).

Checks what mocks cannot: the four council tool schemas compile under ``strict: true``, and a real model
labels a real sheet (the English CSV of the Bahar list) the way the heuristic voter does.
"""

from __future__ import annotations

import os

import pytest
from app.ai.client import DEFAULT_MODEL, AIClient
from app.council import llm
from app.council.render import render_file
from app.council.structure import analyze

from tests.council.conftest import EN_CSV, MEMO_DOCX

pytestmark = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")

MODEL = os.environ.get("SMARTSCHED_LIVE_MODEL", DEFAULT_MODEL)


async def test_live_structure_vote_agrees_on_a_real_sheet():
    client = AIClient(os.environ["ANTHROPIC_API_KEY"], MODEL)
    rendered = render_file(EN_CSV.read_bytes(), EN_CSV.name)
    votes, messages = await llm.vote_structure(client, rendered.grids[0], EN_CSV.name)
    assert votes, messages
    vote = votes[0]
    assert vote["kind"] == "request_list"
    fields = {c["index"]: c["field"] for c in vote["columns"]}
    assert fields.get(0) == "course_code" and fields.get(7) == "day"
    merged = llm.merge_votes(analyze(rendered)[0], votes, 0.75)
    assert merged.source == "consensus" and merged.confidence >= 0.9


async def test_live_judge_and_extract_schemas_compile():
    client = AIClient(os.environ["ANTHROPIC_API_KEY"], MODEL)
    rendered = render_file(MEMO_DOCX.read_bytes(), MEMO_DOCX.name)
    records, msg = await llm.extract_free_text(client, rendered, rendered.units[:6])
    assert msg == "" or "did not call" not in msg
    row = "Room=A 101 | Seats=58 | Exam seats=30 | Building=A"
    verdicts, msg = await llm.judge(client, [("0:0", {"code": "A101", "capacity": 58}, row)])
    assert verdicts and verdicts[0]["verdict"] in ("ok", "unsure"), msg
