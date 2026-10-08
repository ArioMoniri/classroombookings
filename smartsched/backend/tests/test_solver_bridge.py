"""Solver bridge: DB -> SolverInput -> stub solve -> persisted assignments, on a small synthetic term."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import Assignment, Block, Course, ExamRequest, MeetingRequest, Program, Room, ScheduleRun, Section, Term
from app.services.solver_bridge import build_solver_input, run_schedule
from app.solver import model as sm
from app.solver.stub import solve
from sqlalchemy import select


async def _seed(session) -> tuple[Term, dict[str, Room], list[MeetingRequest]]:
    term = Term(code="T1", name="t1", week_count=4)
    session.add(term)
    await session.flush()
    rooms = {}
    for code, cap, tags in (("A101", 58, []), ("A204", 156, []), ("A201", 96, ["TIP"]), ("B207", 60, ["PC"])):
        r = Room(code=code, display_name=code, capacity=cap, exam_capacity=cap // 2, tags=tags)
        session.add(r)
        rooms[code] = r
    prog = Program(name="Psikoloji", canonical_name="psikoloji")
    c1 = Course(code="PSI101", display_code="PSI 101")
    c2 = Course(code="PSI201", display_code="PSI 201")
    c3 = Course(code="BIL101", display_code="BIL 101")
    session.add_all([prog, c1, c2, c3])
    await session.flush()
    s1 = Section(
        term_id=term.id,
        course_id=c1.id,
        program_id=prog.id,
        class_year=1,
        class_years=[1],
        enrolment=120,
        source_key="s1",
    )
    s2 = Section(
        term_id=term.id,
        course_id=c2.id,
        program_id=prog.id,
        class_year=2,
        class_years=[2],
        enrolment=50,
        source_key="s2",
    )
    s3 = Section(
        term_id=term.id,
        course_id=c3.id,
        program_id=prog.id,
        class_year=3,
        class_years=[3],
        enrolment=40,
        source_key="s3",
    )
    session.add_all([s1, s2, s3])
    await session.flush()
    m1 = MeetingRequest(
        section_id=s1.id,
        day=1,
        days=[1],
        start_period=4,
        end_period=6,
        weeks=[1, 2, 3, 4],
        status="LOCKED",
        definitive_room_ids=[rooms["A204"].id],
        needs_room=True,
    )
    m2 = MeetingRequest(
        section_id=s2.id,
        day=1,
        days=[1],
        start_period=4,
        end_period=5,
        weeks=[3, 4],
        status="PARSED",
        requested_room_ids=[rooms["A101"].id],
        needs_room=True,
    )
    m3 = MeetingRequest(
        section_id=s3.id,
        day=1,
        days=[1],
        start_period=4,
        end_period=4,
        weeks=[1, 2],
        status="PARSED",
        requested_tags=["PC"],
        needs_room=True,
    )
    m4 = MeetingRequest(
        section_id=s3.id,
        day=2,
        days=[2],
        start_period=1,
        end_period=2,
        weeks=[1, 2, 3, 4],
        status="PARSED",
        needs_room=False,
    )
    session.add_all([m1, m2, m3, m4])
    session.add(
        Block(
            term_id=term.id,
            room_id=rooms["A101"].id,
            day=1,
            start_period=1,
            end_period=6,
            weeks=[2],
            label="HAZIRLIK",
            source="GRID_IMPORT",
        )
    )
    await session.commit()
    return term, rooms, [m1, m2, m3, m4]


async def test_build_input_and_run(engine, stub_solver):
    factory = get_session_factory()
    async with factory() as s:
        term, rooms, mrs = await _seed(s)
        run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", params={"time_limit_s": 5, "solver": "cpsat"})
        s.add(run)
        await s.commit()
        inp, members = await build_solver_input(s, run)
        assert len(inp.rooms) == 4 and len(inp.events) == 3  # m4 needs no room
        ev = {e.id: e for e in inp.events}
        assert ev[mrs[0].id].locked is not None and ev[mrs[0].id].locked.room_ids == (rooms["A204"].id,)
        assert ev[mrs[1].id].preferred_room_ids == (rooms["A101"].id,) and ev[mrs[1].id].forbidden_tags == frozenset(
            {"TIP"}
        )
        assert ev[mrs[2].id].required_tags == frozenset({"PC"}) and ev[mrs[2].id].weeks == frozenset({1, 2})
        assert "PROG:psikoloji:Y1" in ev[mrs[0].id].cohort_keys and "PROG:psikoloji:Y3" in ev[mrs[2].id].cohort_keys
        assert len(inp.blocks) == 1 and inp.blocks[0].week == 2 and inp.weeks == (1, 2, 3, 4)
        run_id = run.id
    result = await run_schedule(factory, run_id)
    assert result["status"] == "FEASIBLE" and result["assignments"] == 3
    async with factory() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run.status == "FEASIBLE" and run.hard_score == 100 and run.stats["progress"] == 100
        rows = {
            a.meeting_request_id: a
            for a in (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars()
        }
        assert rows[mrs[0].id].room_ids == [rooms["A204"].id] and rows[mrs[0].id].weeks == [1, 2, 3, 4]
        # m2 gets its preferred A 101 (free in weeks 3-4; the HAZIRLIK block only covers week 2)
        assert rows[mrs[1].id].room_ids == [rooms["A101"].id] and rows[mrs[1].id].weeks == [3, 4]
        assert rows[mrs[2].id].room_ids == [rooms["B207"].id]
        assert all(a.origin == "SOLVER" and a.day == 1 for a in rows.values())
        # re-solve replaces solver assignments without duplicating
        await run_schedule(factory, run_id)
        assert len((await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars().all()) == 3


async def test_infeasible_diagnosis(engine, stub_solver):
    factory = get_session_factory()
    async with factory() as s:
        term, rooms, mrs = await _seed(s)
        sec = await s.get(Section, mrs[1].section_id)
        sec.enrolment = 500  # no room is big enough
        run = ScheduleRun(
            term_id=term.id, kind="COURSE", horizon="WEEK", horizon_params={"week": 3}, params={"solver": "cpsat"}
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    result = await run_schedule(factory, run_id)
    assert result["status"] == "INFEASIBLE"
    async with factory() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run.status == "INFEASIBLE" and run.hard_score < 100
        assert (
            run.diagnosis
            and "capacity" in run.diagnosis[0]["constraint_kinds"]
            and run.diagnosis[0]["event_ids"] == [mrs[1].id]
        )
        assert run.diagnosis[0]["suggestions"]


async def test_exam_cohorts_merge_and_split(engine, stub_solver):
    factory = get_session_factory()
    async with factory() as s:
        term, rooms, _ = await _seed(s)
        term.kind = "FINAL"
        from datetime import date

        for i, (_prog, enrol) in enumerate((("a", 60), ("b", 40), ("c", 30))):
            s.add(
                ExamRequest(
                    term_id=term.id,
                    course_code="BME419",
                    enrolment=enrol,
                    date=date(2026, 6, 1),
                    start_period=7,
                    end_period=9,
                    merge_key="K",
                    status="PARSED",
                    source_key=f"e{i}",
                    needs_room=True,
                    requested_room_count=3,
                )
            )
        await s.commit()
        run = ScheduleRun(term_id=term.id, kind="EXAM", horizon="TERM", params={"solver": "cpsat"})
        s.add(run)
        await s.commit()
        inp, members = await build_solver_input(s, run)
        assert (
            len(inp.events) == 1
            and inp.events[0].size == 130
            and inp.events[0].max_rooms == 3
            and inp.events[0].fixed_day == 1
        )
        assert len(members[inp.events[0].id]) == 3
        run_id = run.id
    res = await run_schedule(factory, run_id)
    assert res["status"] == "FEASIBLE" and res["assignments"] == 3
    async with factory() as s:
        rows = (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars().all()
        # 130 seats vs exam capacities A204 78 + A101 30 + B207 30 (A201 is TIP) -> split over 3 rooms
        assert len(rows) == 3 and all(len(a.room_ids) == 3 for a in rows) and all(a.exam_request_id for a in rows)
        assert all(str(a.date) == "2026-06-01" for a in rows)


def test_stub_solver_pure():
    rooms = (sm.Room(1, "A101", 58, 30, "A", frozenset()), sm.Room(2, "A204", 156, 74, "A", frozenset()))
    ev = sm.Event(
        id=1,
        kind="course",
        label="X",
        size=100,
        duration=2,
        weeks=frozenset({1}),
        fixed_day=1,
        fixed_start=1,
        allowed_days=frozenset({1}),
    )
    ev2 = sm.Event(
        id=2,
        kind="course",
        label="Y",
        size=100,
        duration=2,
        weeks=frozenset({1}),
        fixed_day=1,
        fixed_start=1,
        allowed_days=frozenset({1}),
    )
    res = solve(sm.SolverInput(rooms=rooms, events=(ev, ev2), constraints=(), weeks=(1,)))
    assert res.status == "INFEASIBLE" and len(res.assignments) == 1 and res.assignments[0].room_ids == (2,)
    assert res.diagnoses[0].event_ids == [2] and "no_room_overlap" in res.diagnoses[0].constraint_kinds
    flex = sm.Event(
        id=3,
        kind="course",
        label="Z",
        size=100,
        duration=2,
        weeks=frozenset({1}),
        fixed_day=None,
        fixed_start=None,
        allowed_days=frozenset({1, 2}),
    )
    res = solve(sm.SolverInput(rooms=rooms, events=(ev, flex), constraints=(), weeks=(1,)))
    assert res.status == "FEASIBLE" and {a.event_id: (a.day, a.start) for a in res.assignments}[3] in {(1, 3), (2, 1)}


async def test_cpsat_engine_if_available(engine):
    """Smoke: the real CP-SAT solver (built by the solver-engineer) runs through the same bridge."""
    import importlib.util

    import pytest

    if importlib.util.find_spec("app.solver.cpsat") is None:
        pytest.skip("app.solver.cpsat not available yet")
    factory = get_session_factory()
    async with factory() as s:
        term, rooms, mrs = await _seed(s)
        run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", params={"time_limit_s": 5, "solver": "cpsat"})
        s.add(run)
        await s.commit()
        run_id = run.id
    result = await run_schedule(factory, run_id)
    assert result["solver"] == "app.solver.cpsat"
    assert result["status"] in {"FEASIBLE", "OPTIMAL", "INFEASIBLE", "TIMEOUT"}
    async with factory() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run.stats["solver"] == "app.solver.cpsat" and run.stats["progress"] == 100


def test_merged_joint_lecture_with_definitive_hints_uses_the_planners_seats():
    """definitive_rooms=prefer: two programme rows of one joint lecture (same instructor, same slot)
    whose planner rooms seat 156 are one event of at most 156 (and may use both planner rooms)."""
    from app.services.solver_bridge import merge_joint_lectures
    from app.solver import model as sm

    def ev(i: int, size: int) -> sm.Event:
        return sm.Event(
            id=i,
            kind="course",
            label=f"MAT 112 §{i}",
            size=size,
            duration=2,
            weeks=frozenset({1}),
            fixed_day=4,
            fixed_start=7,
            allowed_days=frozenset({4}),
            instructor_keys=frozenset({"INS:1"}),
            preferred_room_ids=(10,),
        )

    from app.services.solver_bridge import clip_to_planner_rooms

    members = {1: [1], 2: [2]}
    out, merged = merge_joint_lectures([ev(1, 120), ev(2, 116)], members, {10: 156, 11: 90}, {1: [10], 2: [10, 11]})
    assert len(out) == 1 and members == {1: [1, 2]}
    assert out[0].size == 236 and out[0].max_rooms == 2 and merged[0]["planner_rooms"] == [10, 11]
    rooms = tuple(
        sm.Room(r, f"R{r}", c, c // 2, "A", frozenset()) for r, c in ((10, 156), (11, 90), (12, 60), (13, 300))
    )
    clipped, cases = clip_to_planner_rooms(out, {1: [10, 11]}, {10: 156, 11: 90, 12: 60, 13: 300}, rooms)
    assert cases == [] and clipped[0].size == 236  # 246 seats suffice: nothing clipped
    out2, merged2 = merge_joint_lectures([ev(1, 120), ev(2, 116)], {1: [1], 2: [2]}, {10: 156}, {1: [10], 2: [10]})
    assert out2[0].size == 236 and "clipped_to" not in merged2[0]  # the merge never clips (review B1)
    clipped2, cases2 = clip_to_planner_rooms(out2, {1: [10]}, {10: 156, 11: 90, 12: 60, 13: 300}, rooms)
    # D1 for hints: 156 in the planner's room only; every other room must seat all 236 (13 does, 11/12 not)
    assert cases2 == [(1, 236, 156, [10])] and clipped2[0].size == 156
    assert clipped2[0].forbidden_room_ids == frozenset({11, 12})
