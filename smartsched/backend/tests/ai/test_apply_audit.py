"""ROADMAP Phase 3 AI backlog: the model id and the verifier result are persisted per applied diff on the child
run (``stats["ai"]``, RESEARCH §4.3 step 6) - patch and repair paths, and browser-edited diffs."""

from __future__ import annotations

from app.ai.chat import apply_diff, handle_chat
from app.ai.client import AIClient
from app.models import ScheduleRun
from app.schemas.ai import ProposedDiff

from tests.ai.conftest import empty_params, empty_selector, proposal, text, tool, tools


def _move(aid: int, room: str) -> dict:
    return {
        "assignment_id": aid,
        "day": 0,
        "start_period": 0,
        "end_period": 0,
        "room_codes": [room],
        "weeks": [],
        "reason": "t",
    }


async def test_patch_apply_records_model_and_verifier(session, seed, fake_sdk):
    fake_sdk.script = [
        tools(
            ("move_event", _move(seed.assignments["PHAR240"], "A 101")),  # 50 students into 20 seats: rejected
            ("move_event", _move(seed.assignments["NRS450"], "A 206")),
        ),
        text("Öneriyorum."),
    ]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await handle_chat(session, seed.run_id, "taşı", "tr", client=client, user_id=None)
    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, user_id=None, enqueue=False)
    assert res.mode == "patch"
    child = await session.get(ScheduleRun, res.child_run_id)
    ai = child.stats["ai"]
    assert ai["diff_id"] == out.proposed_diff.id and ai["model"] == "claude-opus-5-5" and ai["edited"] is False
    assert ai["applied_ops"] == 1 and ai["rejected_ops"] == 1
    assert ai["rejected"][0]["index"] == 0 and any("capacity" in r for r in ai["rejected"][0]["reasons"])
    v = ai["verifier"]
    assert v["validator"] == "app.solver.repair.validate" and v["mode"] == "patch"
    assert v["status"] == "FEASIBLE" and v["hard_score"] == 100 and v["hard_violations"] == 0
    assert ai["applied_at"]


async def test_repair_apply_records_final_verifier(session, seed, fake_sdk):
    fake_sdk.script = [
        tool(
            "add_constraint",
            {
                **proposal(
                    "room_forbid",
                    selector=empty_selector(course_codes=["PSI 101"]),
                    params=empty_params(room_codes=["A 204"]),
                ),
                "scope": "term",
            },
        ),
        text("Öneriyorum."),
    ]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await handle_chat(session, seed.run_id, "PSI 101 A 204'te olmasın", "tr", client=client)
    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert res.mode == "repair"
    child = await session.get(ScheduleRun, res.child_run_id)
    await session.refresh(child)
    v = child.stats["ai"]["verifier"]
    assert child.stats["ai"]["model"] == "claude-opus-5-5"
    assert v["mode"] == "repair" and v["status"] == child.status and v["hard_score"] == child.hard_score
    assert v["status"] in ("OPTIMAL", "FEASIBLE")


async def test_browser_edited_diff_has_no_model(session, seed):
    diff = ProposedDiff(
        id="edited-1",
        run_id=seed.run_id,
        operations=[{"op": "lock", "assignment_id": seed.assignments["PSI101"]}],
    )
    res = await apply_diff(session, seed.run_id, diff=diff, enqueue=False)
    child = await session.get(ScheduleRun, res.child_run_id)
    assert child.stats["ai"]["model"] is None and child.stats["ai"]["edited"] is True
