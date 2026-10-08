"""Term runs through the bridge solve in week segments: a planner lock whose room is blocked by the grid
in one week keeps the room in every other week and moves only that week (one Assignment row per room
set, the original request id everywhere)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import (
    Assignment,
    Block,
    Course,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    Term,
)
from app.services.solver_bridge import MODE_DEFAULTS, run_schedule
from sqlalchemy import select


async def _seed(session) -> dict[str, int]:  # type: ignore[no-untyped-def]
    term = Term(code="T-WEEKS", name="t", week_count=3)
    session.add(term)
    await session.flush()
    rooms = {
        code: Room(code=code, display_name=code, capacity=cap, exam_capacity=cap // 2, tags=[], is_bookable=True)
        for code, cap in (("A101", 58), ("A102", 58))
    }
    session.add_all(rooms.values())
    prog = Program(name="Fizyoterapi", canonical_name="fizyoterapi")
    course = Course(code="MAT112", display_code="MAT 112")
    session.add_all([prog, course])
    await session.flush()
    sec = Section(
        term_id=term.id,
        course_id=course.id,
        program_id=prog.id,
        class_year=1,
        class_years=[1],
        enrolment=40,
        source_key="MAT112",
    )
    session.add(sec)
    await session.flush()
    mr = MeetingRequest(
        section_id=sec.id,
        day=1,
        days=[1],
        start_period=1,
        end_period=2,
        weeks=[1, 2, 3],
        status="LOCKED",
        definitive_room_ids=[rooms["A101"].id],
        needs_room=True,
    )
    session.add(mr)
    # the planner's grid: an ETKİNLİK in A101 on Monday P1-P2 of week 2
    session.add(
        Block(
            term_id=term.id, room_id=rooms["A101"].id, day=1, start_period=1, end_period=2, weeks=[2], label="ETKİNLİK"
        )
    )
    await session.commit()
    return {"term": term.id, "mr": mr.id, "A101": rooms["A101"].id, "A102": rooms["A102"].id}


async def _run(term_id: int, **params) -> int:  # type: ignore[no-untyped-def]
    factory = get_session_factory()
    async with factory() as s:
        run = ScheduleRun(
            term_id=term_id,
            kind="COURSE",
            horizon="TERM",
            params={"time_limit_s": 10, "solver": "cpsat", "workers": 2, **params},
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    await run_schedule(factory, run_id)
    return run_id


async def test_term_run_moves_only_the_blocked_week(engine):
    assert MODE_DEFAULTS["split_blocked_weeks"] is True
    async with get_session_factory()() as s:
        ids = await _seed(s)
    run_id = await _run(ids["term"])
    async with get_session_factory()() as s:
        run = await s.get(ScheduleRun, run_id)
        rows = list((await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars())
    assert run is not None and run.status in {"OPTIMAL", "FEASIBLE"} and run.hard_score == 100, run.diagnosis
    got = sorted((sorted(a.weeks), a.room_ids, a.meeting_request_id) for a in rows)
    assert got == [([1, 3], [ids["A101"]], ids["mr"]), ([2], [ids["A102"]], ids["mr"])]
    split = next(d for d in run.diagnosis if d["code"] == "week_split")
    assert split["event_ids"] == [ids["mr"]] and split["params"]["moved_weeks"] == [2]
    assert "MAT 112 keeps A101 in week(s) 1, 3" in split["message"]
    assert run.stats["week_split"]["events_split"] == 1 and run.stats["placed"] == 1
    assert all(i > 0 for d in run.diagnosis for i in d["event_ids"])  # segment ids never leak


async def test_split_can_be_switched_off(engine):
    async with get_session_factory()() as s:
        ids = await _seed(s)
    run_id = await _run(ids["term"], split_blocked_weeks=False)
    async with get_session_factory()() as s:
        run = await s.get(ScheduleRun, run_id)
    assert run is not None and run.status == "INFEASIBLE"  # the lock is ineligible for the whole term
    assert any(d["code"] == "locked_ineligible" for d in run.diagnosis)
