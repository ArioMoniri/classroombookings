"""ROADMAP Phase 3 AI backlog: "move + update the request" as one diff operation.

A meeting with a requested (fixed) day/time cannot be moved to another day: the validator reports
``fixed_time``. With ``update_request`` the same move also rewrites the meeting request's day/periods (term data,
snapshotted for revert) so the move is valid; it is applied only if the moved placement passes the validator,
otherwise the request is left exactly as it was.
"""

from __future__ import annotations

from app.ai.chat import apply_diff, handle_chat
from app.ai.client import AIClient
from app.models import Assignment, ImportedSnapshot, MeetingRequest
from app.schemas.ai import ProposedDiff
from sqlalchemy import select

from tests.ai.conftest import text, tool


def _move(aid: int, *, day: int, start: int = 0, room: str = "", update: bool) -> dict:
    return {
        "assignment_id": aid,
        "day": day,
        "start_period": start,
        "end_period": 0,
        "room_codes": [room] if room else [],
        "weeks": [],
        "update_request": update,
        "reason": "t",
    }


async def test_move_with_request_update_is_one_valid_patch(session, seed, fake_sdk):
    fake_sdk.script = [
        tool("move_event", _move(seed.assignments["NRS450"], day=4, start=7, update=True)),
        text("NRS 450'yi perşembeye taşıyıp talebi güncellemeyi öneriyorum."),
    ]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await handle_chat(session, seed.run_id, "NRS 450 perşembe P7'ye", "tr", client=client)
    op = out.proposed_diff.operations[0]
    assert op.op == "move" and op.update_request is True and op.day == 4

    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert res.mode == "patch" and not res.rejected, res
    assert res.status == "FEASIBLE" and res.hard_score == 100
    assert res.applied[0]["request_updated"] is True
    mr = await session.get(MeetingRequest, seed.mr["NRS450"])
    await session.refresh(mr)
    assert (mr.day, mr.days, mr.start_period, mr.end_period) == (4, [4], 7, 8)
    snap = (
        await session.execute(
            select(ImportedSnapshot).where(ImportedSnapshot.entity == "meeting", ImportedSnapshot.entity_id == mr.id)
        )
    ).scalar_one()
    assert snap is not None  # revertable
    a = (
        await session.execute(
            select(Assignment).where(Assignment.run_id == res.child_run_id, Assignment.meeting_request_id == mr.id)
        )
    ).scalar_one()
    assert (a.day, a.start_period, a.end_period, a.origin) == (4, 7, 8, "AI_EDIT")


async def test_without_update_the_fixed_time_move_is_still_rejected(session, seed):
    diff = ProposedDiff(
        id="d-fixed",
        run_id=seed.run_id,
        operations=[{"op": "move", "assignment_id": seed.assignments["NRS450"], "day": 4}],
    )
    res = await apply_diff(session, seed.run_id, diff=diff, enqueue=False)
    assert res.status == "REJECTED"
    assert any("update_request" in r for r in res.rejected[0]["reasons"])


async def test_rejected_move_leaves_the_request_untouched(session, seed):
    before = await session.get(MeetingRequest, seed.mr["PHAR240"])
    old = (before.day, list(before.days), before.start_period, before.end_period)
    diff = ProposedDiff(
        id="d-cap",
        run_id=seed.run_id,
        operations=[
            # 50 students into a 20-seat room on another day: capacity fails, the request must not change
            {
                "op": "move",
                "assignment_id": seed.assignments["PHAR240"],
                "day": 4,
                "room_ids": [seed.rooms["A101"]],
                "update_request": True,
            },
            {"op": "lock", "assignment_id": seed.assignments["PSI101"]},
        ],
    )
    res = await apply_diff(session, seed.run_id, diff=diff, enqueue=False)
    assert res.rejected and res.rejected[0]["index"] == 0
    assert any("capacity" in r for r in res.rejected[0]["reasons"])
    assert res.mode == "patch" and res.hard_score == 100
    mr = await session.get(MeetingRequest, seed.mr["PHAR240"])
    await session.refresh(mr)
    assert (mr.day, list(mr.days), mr.start_period, mr.end_period) == old
