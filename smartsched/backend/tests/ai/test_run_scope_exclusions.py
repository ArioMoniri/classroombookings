"""Review follow-up (2026-10-08): chat "exclude" edits were term-wide only.

``exclude_sections`` / ``include_sections`` take ``scope``: ``term`` (the old behaviour: the meeting requests
stop needing a room, snapshotted) or ``run``: the classes are left out of the child run only, through the
child's sealed run-level snapshot (``params.studio.excluded_event_ids``, the same mechanism a studio draft
uses). The term data is untouched, chat edits of that child inherit the exclusion, and ``include`` with
``scope=run`` brings the classes back for that run.
"""

from __future__ import annotations

from app.ai.chat import apply_diff, handle_chat
from app.ai.client import AIClient
from app.models import Assignment, MeetingRequest, ScheduleRun
from app.services.run_params import trusted_studio_snapshot
from sqlalchemy import select

from tests.ai.conftest import text, tool


def _sections(op: str, code: str, scope: str) -> dict:
    return {
        "section_ids": [],
        "course_codes": [code],
        "program_name": "",
        "section_label": "",
        "scope": scope,
        "reason": f"{op} {code}",
    }


async def _placed(session, run_id: int) -> set[int]:
    rows = (await session.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars().all()
    return {int(a.meeting_request_id) for a in rows if a.meeting_request_id}


async def test_run_scoped_exclusion_leaves_term_data_alone_and_is_inherited(session, seed, fake_sdk):
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    fake_sdk.script = [tool("exclude_sections", _sections("exclude", "PSI 101", "run")), text("Öneriyorum.")]
    out = await handle_chat(session, seed.run_id, "bu çalıştırmada PSI 101'i çıkar", "tr", client=client)
    op = out.proposed_diff.operations[0]
    assert op.op == "section_edit" and op.edit.op == "exclude" and op.scope == "run"

    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert not res.rejected and res.mode == "repair" and res.status in ("OPTIMAL", "FEASIBLE"), res
    child = await session.get(ScheduleRun, res.child_run_id)
    await session.refresh(child)
    snap = trusted_studio_snapshot(child)
    assert snap is not None and seed.mr["PSI101"] in snap["excluded_event_ids"]
    assert seed.mr["PSI101"] not in await _placed(session, child.id)
    assert {seed.mr["PHAR240"], seed.mr["NRS450"]} <= await _placed(session, child.id)
    mr = await session.get(MeetingRequest, seed.mr["PSI101"])
    await session.refresh(mr)
    assert mr.needs_room is True  # term data untouched

    # a chat edit of the child keeps the exclusion ...
    fake_sdk.script = [tool("re_solve", {"stability": True, "reason": "tekrar"}), text("Tamam.")]
    out2 = await handle_chat(session, child.id, "yeniden çöz", "tr", client=client)
    res2 = await apply_diff(session, child.id, diff_id=out2.proposed_diff.id, enqueue=False)
    assert seed.mr["PSI101"] not in await _placed(session, res2.child_run_id)

    # ... and a run-scoped include brings the class back for that run only
    fake_sdk.script = [tool("include_sections", _sections("include", "PSI 101", "run")), text("Tamam.")]
    out3 = await handle_chat(session, res2.child_run_id, "PSI 101 geri gelsin", "tr", client=client)
    res3 = await apply_diff(session, res2.child_run_id, diff_id=out3.proposed_diff.id, enqueue=False)
    assert not res3.rejected, res3
    assert seed.mr["PSI101"] in await _placed(session, res3.child_run_id)
    assert seed.mr["PSI101"] not in await _placed(session, res2.child_run_id)


async def test_term_scope_exclusion_still_changes_term_data(session, seed, fake_sdk):
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    fake_sdk.script = [tool("exclude_sections", _sections("exclude", "PSI 101", "term")), text("Öneriyorum.")]
    out = await handle_chat(session, seed.run_id, "PSI 101 online oldu", "tr", client=client)
    assert out.proposed_diff.operations[0].scope == "term"
    res = await apply_diff(session, seed.run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert not res.rejected
    mr = await session.get(MeetingRequest, seed.mr["PSI101"])
    await session.refresh(mr)
    assert mr.needs_room is False
    child = await session.get(ScheduleRun, res.child_run_id)
    assert trusted_studio_snapshot(child) is None
