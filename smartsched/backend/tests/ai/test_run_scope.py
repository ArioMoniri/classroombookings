"""ROADMAP Phase 3 AI backlog: chat rules "only for this run".

``add_constraint`` takes ``scope`` = ``term`` (default: every later run of the term) or ``run``: the rule is
created on the child run only (``constraints.run_id``), the term's other runs never see it, and later chat
edits of that child inherit it (the grandchild gets its own copy, so removing it there leaves the child as it
was).
"""

from __future__ import annotations

from app.ai.chat import apply_diff, handle_chat
from app.ai.client import AIClient
from app.models import Assignment, ConstraintRow
from sqlalchemy import select

from tests.ai.conftest import empty_params, empty_selector, proposal, text, tool


def _forbid(scope: str) -> dict:
    return {
        **proposal(
            "room_forbid",
            selector=empty_selector(course_codes=["PSI 101"]),
            params=empty_params(room_codes=["A 204"]),
            nl_text="bu çalıştırmada PSI 101 A 204'te olmasın",
        ),
        "scope": scope,
    }


async def _rooms(session, run_id: int, mr_id: int) -> list[int]:
    a = (
        await session.execute(
            select(Assignment).where(Assignment.run_id == run_id, Assignment.meeting_request_id == mr_id)
        )
    ).scalar_one()
    return list(a.room_ids or [])


async def test_run_scoped_rule_stays_on_the_child_and_is_inherited(session, seed, fake_sdk):
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    fake_sdk.script = [tool("add_constraint", _forbid("run")), text("Öneriyorum.")]
    out = await handle_chat(
        session, seed.run_id, "sadece bu çalıştırma için PSI 101 A 204'te olmasın", "tr", client=client
    )
    op = out.proposed_diff.operations[0]
    assert op.op == "add_constraint" and op.scope == "run" and op.constraint.status == "ok"

    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert res.mode == "repair" and res.status in ("OPTIMAL", "FEASIBLE")
    child_id = res.child_run_id
    row = await session.get(ConstraintRow, res.constraints_created[0])
    assert row.run_id == child_id and row.term_id is None and row.source == "AI"
    assert seed.rooms["A204"] not in await _rooms(session, child_id, seed.mr["PSI101"])
    # no term-wide rule: other runs of the term are not affected
    term_rules = (await session.execute(select(ConstraintRow).where(ConstraintRow.term_id == seed.term_id))).all()
    assert term_rules == []

    # a chat edit of the child inherits the run rule (own copy) ...
    fake_sdk.script = [
        tool("remove_constraint", {"constraint_id": row.id, "reason": "artık gerekmiyor"}),
        text("Tamam."),
    ]
    out2 = await handle_chat(session, child_id, "A 204 yasağını kaldır", "tr", client=client)
    assert out2.proposed_diff is not None and out2.proposed_diff.operations[0].op == "remove_constraint"
    res2 = await apply_diff(session, child_id, diff_id=out2.proposed_diff.id, enqueue=False)
    assert res2.child_run_id and not res2.rejected
    copies = list(
        (await session.execute(select(ConstraintRow).where(ConstraintRow.run_id == res2.child_run_id))).scalars()
    )
    assert len(copies) == 1 and copies[0].source_ref["inherited_from"] == row.id and copies[0].kind == "room_forbid"
    # ... and removing it there disables only the grandchild's copy
    assert copies[0].enabled is False
    await session.refresh(row)
    assert row.enabled is True


async def test_inherited_rule_applies_to_the_grandchild(session, seed, fake_sdk):
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    fake_sdk.script = [tool("add_constraint", _forbid("run")), text("Öneriyorum.")]
    out = await handle_chat(session, seed.run_id, "sadece bu çalıştırma", "tr", client=client)
    child_id = (await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)).child_run_id
    fake_sdk.script = [tool("re_solve", {"stability": False, "reason": "baştan"}), text("Tamam.")]
    out2 = await handle_chat(session, child_id, "yeniden çöz", "tr", client=client)
    res2 = await apply_diff(session, child_id, diff_id=out2.proposed_diff.id, enqueue=False)
    assert res2.mode == "full" and res2.status in ("OPTIMAL", "FEASIBLE")
    assert seed.rooms["A204"] not in await _rooms(session, res2.child_run_id, seed.mr["PSI101"])


async def test_term_scope_is_the_default_behaviour(session, seed, fake_sdk):
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    fake_sdk.script = [tool("add_constraint", _forbid("term")), text("Öneriyorum.")]
    out = await handle_chat(session, seed.run_id, "PSI 101 A 204'te olmasın", "tr", client=client)
    assert out.proposed_diff.operations[0].scope == "term"
    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)
    row = await session.get(ConstraintRow, res.constraints_created[0])
    assert row.term_id == seed.term_id and row.run_id is None
