"""ROADMAP Phase 3 AI backlog: exam runs get exam-request edits in chat.

``set_exam_field`` (exam runs only) changes an exam request's enrolment and/or the number of rooms it may be
split across (``requested_room_count``). Applying it snapshots the old values, changes the term data and
re-solves the child run (repair), so a grown exam is split over enough rooms with hard rules intact.
"""

from __future__ import annotations

from datetime import date

from app.ai.chat import apply_diff, handle_chat
from app.ai.client import AIClient
from app.models import Assignment, ExamRequest, ImportedSnapshot, Room, ScheduleRun
from sqlalchemy import select

from tests.ai.conftest import text, tool


async def _exam_run(session, seed) -> tuple[int, int, int]:
    ex = ExamRequest(
        term_id=seed.term_id,
        course_code="PHAR240",
        course_name="Pharmacology",
        program_id=seed.programs["eczacılık"],
        class_year=2,
        class_years=[2],
        enrolment=50,
        date=date(2026, 4, 6),  # a Monday in week 9
        start_period=2,
        end_period=4,
        requested_room_count=1,
        status="PARSED",
    )
    session.add(ex)
    await session.flush()
    run = ScheduleRun(
        term_id=seed.term_id,
        kind="EXAM",
        horizon="TERM",
        status="OPTIMAL",
        hard_score=100,
        soft_score=95,
        params={"time_limit_s": 10, "workers": 2},
        stats={"events": 1},
        diagnosis=[],
    )
    session.add(run)
    await session.flush()
    a = Assignment(
        run_id=run.id,
        exam_request_id=ex.id,
        weeks=[9],
        day=1,
        date=date(2026, 4, 6),
        start_period=2,
        end_period=4,
        room_ids=[seed.rooms["A204"]],
        origin="SOLVER",
    )
    session.add(a)
    await session.commit()
    return run.id, ex.id, a.id


def _edit(aid: int, enrolment: int = 0, rooms: int = 0) -> dict:
    return {"assignment_id": aid, "enrolment": enrolment, "room_count": rooms, "reason": "kayıt arttı"}


async def test_exam_enrolment_and_room_split_edit(session, seed, fake_sdk):
    run_id, ex_id, aid = await _exam_run(session, seed)
    fake_sdk.script = [
        tool("set_exam_field", _edit(aid, enrolment=120, rooms=2)),
        text("PHAR 240 sınavını 120 kişi ve 2 salon olarak güncellemeyi öneriyorum."),
    ]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await handle_chat(session, run_id, "PHAR 240 sınavı 120 kişi, iki salona böl", "tr", client=client)
    op = out.proposed_diff.operations[0]
    assert op.op == "exam_edit" and op.exam_request_id == ex_id and op.enrolment == 120 and op.room_count == 2

    res = await apply_diff(session, run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert not res.rejected and res.mode == "repair", res
    assert res.applied[0]["before"] == {"enrolment": 50, "requested_room_count": 1}
    ex = await session.get(ExamRequest, ex_id)
    await session.refresh(ex)
    assert (ex.enrolment, ex.requested_room_count) == (120, 2)
    snap = (
        await session.execute(
            select(ImportedSnapshot).where(ImportedSnapshot.entity == "exam", ImportedSnapshot.entity_id == ex_id)
        )
    ).scalar_one()
    assert snap.values == {"enrolment": 50, "requested_room_count": 1}
    child = await session.get(ScheduleRun, res.child_run_id)
    await session.refresh(child)
    assert child.status in ("OPTIMAL", "FEASIBLE"), (child.status, child.diagnosis)
    assert child.hard_score == 100
    rows = (await session.execute(select(Assignment).where(Assignment.run_id == child.id))).scalars().all()
    room_ids = {int(rid) for r in rows for rid in r.room_ids or []}
    rooms = (await session.execute(select(Room).where(Room.id.in_(room_ids)))).scalars().all()
    assert len(room_ids) >= 2 and sum(r.exam_capacity for r in rooms) >= 120


async def test_exam_edit_is_refused_on_course_runs_and_bad_values(session, seed, fake_sdk):
    run_id, _ex_id, aid = await _exam_run(session, seed)
    fake_sdk.script = [
        tool("set_exam_field", _edit(seed.assignments["PHAR240"], enrolment=60)),  # a course run's assignment
        text("Yapamadım."),
    ]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await handle_chat(session, seed.run_id, "sınavı büyüt", "tr", client=client)
    assert out.proposed_diff is None
    result = fake_sdk.calls[1]["messages"][-1]["content"][0]  # the tool_result sent back to the model
    assert result.get("is_error") and "exam" in result["content"]

    fake_sdk.script = [tool("set_exam_field", _edit(aid)), text("Değişiklik yok.")]
    out = await handle_chat(session, run_id, "aynı kalsın", "tr", client=client)
    assert out.proposed_diff is None  # nothing to change


async def test_room_count_only_edit_is_re_solved(session, seed, fake_sdk):
    """A room-count change adds no hard violation by itself: the edited exam must still be freed for the repair."""
    run_id, ex_id, aid = await _exam_run(session, seed)
    fake_sdk.script = [tool("set_exam_field", _edit(aid, rooms=2)), text("Öneriyorum.")]
    client = AIClient("sk-ant-test", "claude-opus-5-5")
    out = await handle_chat(session, run_id, "iki salona böl", "tr", client=client)
    res = await apply_diff(session, run_id, diff_id=out.proposed_diff.id, enqueue=False)
    assert res.mode == "repair" and not res.rejected
    child = await session.get(ScheduleRun, res.child_run_id)
    await session.refresh(child)
    assert child.hard_score == 100
    assert ex_id in child.stats["ai"]["freed_event_ids"]  # the exam event was re-placed by the repair
