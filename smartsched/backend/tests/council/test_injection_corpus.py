"""Injection corpus through the council (P19-A4): the red-team upload cases of tests/ai/redteam_cases.json go
through the whole council (upload -> AI intake -> rule miner -> review -> commit) with a model stand-in that
*obeyed* the injected text (``replay_compromised``) and invents values. A careless reviewer accepts everything.

Required: 0 structural, untargeted or hard rules written, 0 invented values (records and rules that cite no
source line are dropped), nothing of the injected markup or contact data in what is sent. A hard rule is written
only when a person sets ``hardness=hard`` on it, and then it cites its source line."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from app.ai.redteam import load_cases
from app.core.db import get_session_factory
from app.importers.planning_list import import_planning_list
from app.models import ConstraintRow, Room, Term
from app.solver.constraints import STRUCTURAL
from sqlalchemy import select

from tests.ai.conftest import FakeSDK, _Endpoint, enable_intake, store_key, tool
from tests.ai.test_redteam import _model_input
from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST
from tests.council.test_ai_rows import accept_ai_rows
from tests.council.test_formats_api import upload

CASES = [
    c
    for c in load_cases(Path(__file__).resolve().parent.parent / "ai" / "redteam_cases.json")
    if c["category"] == "injection_upload"
]
EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@pytest.fixture
def by_tool(monkeypatch):
    """The stand-in answers by the tool the council asks for (the order of the calls does not matter)."""
    import anthropic

    answers: dict[str, Any] = {}
    FakeSDK.instances, FakeSDK.script, FakeSDK.calls = [], [], []

    def _next(self: _Endpoint, kwargs: dict[str, Any], *, stream: bool) -> Any:
        import copy

        self.owner.calls.append({"stream": stream, **copy.deepcopy(kwargs)})
        name = kwargs["tools"][0]["name"]
        return answers[name]

    monkeypatch.setattr(_Endpoint, "_next", _next)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeSDK)
    return answers


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_injected_uploads_change_no_structural_or_hard_rule(client, by_tool, case):
    h = await login(client)
    async with get_session_factory()() as s:
        await store_key(s)
        await enable_intake(s)
        await import_planning_list(s, BAHAR_LIST, "2026-BAHAR")
        tid = (await s.execute(select(Term.id).where(Term.code == "2026-BAHAR"))).scalar_one()
        rooms_before = {r.code for r in (await s.execute(select(Room))).scalars()}
    compromised = _model_input(case["replay_compromised"])
    # and a rule citing no line, the classic "the document says so" invention
    compromised["proposals"].append({**compromised["proposals"][0], "source_ref": 99, "title": "invented"})
    by_tool["propose_constraints"] = tool("propose_constraints", compromised)
    invented = {"type": "room", "unit": 1, "room": "Z 999", "capacity": 500}
    blank = {
        k: ""
        for k in (
            "course_code",
            "course_name",
            "section",
            "program",
            "instructor",
            "day",
            "start",
            "end",
            "date",
            "label",
        )
    }
    by_tool["report_records"] = tool("report_records", {"records": [{**blank, "enrolment": 0, **invented}]})
    by_tool["report_structure"] = tool(
        "report_structure", {"kind": "other", "confidence": 0.5, "header_rows": [], "columns": [], "notes": ""}
    )
    by_tool["judge_records"] = tool("judge_records", {"verdicts": []})

    data = "\n".join(case["lines"]).encode("utf-8")
    job = await upload(client, h, (case["filename"], data), ai="true")
    assert job["ai_mode"] == "llm" and job["files"][0]["route_kind"] == "ai", job

    sent = json.dumps([c["messages"] for c in FakeSDK.calls], ensure_ascii=False)
    assert "</document>" not in sent.replace("\\n</document>", "")  # only the council's own closing tag
    assert sent.count("</document>") == sent.count("<document>")
    assert not EMAIL_RX.search(sent) and "0532 123" not in sent

    # the careless reviewer: accept every item and every row
    review = (await client.get(f"/api/v1/council/jobs/{job['id']}/review", headers=h)).json()
    rule_items = [it for it in review["items"] if it["kind"] == "rule"]
    assert rule_items and all(it["source"] for it in rule_items)  # the source_ref=99 invention was dropped by the miner
    decisions = [{"id": it["id"], "action": "accept"} for it in review["items"] if it["kind"] != "ai_rows"]
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/review", headers=h, json={"decisions": decisions})
    assert r.status_code == 200
    await accept_ai_rows(client, h, job["id"])
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"term_id": tid, "files": [0]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["constraints_created"] == [], out["constraints_rejected"]
    async with get_session_factory()() as s:
        rows = (await s.execute(select(ConstraintRow).where(ConstraintRow.source == "UPLOAD"))).scalars().all()
        rooms_after = {r.code for r in (await s.execute(select(Room))).scalars()}
    assert rows == []
    assert "Z999" not in rooms_after and rooms_after == rooms_before  # the invented room value was not traced

    # a person may still take the real rule, by choosing hardness=hard; it cites its line of the file
    legit = [it for it in rule_items if (it["current"] or {}).get("hardness") == "hard"]
    if not legit:
        return
    edit = [{"id": legit[0]["id"], "action": "edit", "value": {"hardness": "hard"}}]
    await client.post(f"/api/v1/council/jobs/{job['id']}/review", headers=h, json={"decisions": edit})
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={"term_id": tid, "files": [0]})
    out = r.json()
    async with get_session_factory()() as s:
        made = [await s.get(ConstraintRow, i) for i in out["constraints_created"]]
    assert len(made) == 1, out["constraints_rejected"]
    for row in made:
        assert row is not None and row.hardness == "hard" and not (row.kind in STRUCTURAL and row.hardness == "soft")
        assert row.source_ref["excerpt"] and row.source_ref["excerpt"] in "\n".join(case["lines"])
        assert row.params.get("event_ids")  # targeted: never the whole term
