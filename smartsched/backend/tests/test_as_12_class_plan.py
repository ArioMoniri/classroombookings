"""AS-12 exams vs the class plan: an exam run reads the published COURSE run of the same term on its exam dates as
blocks (a midterm in lecture week 8 can no longer take the room a class holds then), and a course run gets the
reverse warning when a published exam sits in one of its rooms."""

from __future__ import annotations

import datetime as dt

from app.core.db import get_session_factory
from app.models import (
    Assignment,
    Course,
    ExamRequest,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    Term,
    Week,
)
from app.services import exam_class_plan as ecp
from app.services.solver_bridge import build_solver_input
from app.solver import model as sm
from app.solver.cpsat import solve
from sqlalchemy import select

TERM_START = dt.date(2026, 2, 16)  # a Monday: week 8 Monday is 6 April 2026
WEEK8_MON = TERM_START + dt.timedelta(weeks=7)


async def _seed(s, *, publish_course: bool = True, exam_date: dt.date = WEEK8_MON) -> dict[str, int]:  # type: ignore[no-untyped-def]
    term = Term(code="T-MID", name="Bahar", week_count=14, start_date=TERM_START)
    s.add(term)
    await s.flush()
    for i in range(1, 15):
        s.add(Week(term_id=term.id, index=i, start_date=TERM_START + dt.timedelta(weeks=i - 1), kind="LECTURE"))
    a101 = Room(code="A101", display_name="A101", capacity=60, exam_capacity=30, tags=[], is_bookable=True)
    a102 = Room(code="A102", display_name="A102", capacity=60, exam_capacity=30, tags=[], is_bookable=True)
    s.add_all([a101, a102])
    prog = Program(name="Fizik", canonical_name="fizik")
    s.add(prog)
    await s.flush()
    course = Course(code="FIZ101", display_code="FIZ 101")
    s.add(course)
    await s.flush()
    sec = Section(
        term_id=term.id,
        course_id=course.id,
        program_id=prog.id,
        class_year=1,
        class_years=[1],
        enrolment=40,
        source_key="FIZ101-1",
    )
    s.add(sec)
    await s.flush()
    mr = MeetingRequest(
        section_id=sec.id, day=1, days=[1], start_period=3, end_period=4, weeks=list(range(1, 15)), status="PARSED"
    )
    s.add(mr)
    await s.flush()
    course_run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", status="OPTIMAL", is_active=publish_course)
    s.add(course_run)
    await s.flush()
    s.add(
        Assignment(
            run_id=course_run.id,
            meeting_request_id=mr.id,
            weeks=list(range(1, 15)),
            day=1,
            start_period=3,
            end_period=4,
            room_ids=[a101.id],
            label="FIZ 101",
        )
    )
    ex = ExamRequest(
        term_id=term.id,
        course_code="KIM101",
        course_name="Vize",
        program_id=prog.id,
        class_year=2,
        class_years=[2],
        enrolment=25,
        date=exam_date,
        start_period=3,
        end_period=4,
        requested_room_ids=[a101.id],  # the coordinator would like A101 ...
        needs_room=True,
    )
    s.add(ex)
    await s.commit()
    return {"term": term.id, "a101": a101.id, "a102": a102.id, "exam": ex.id, "course_run": course_run.id, "mr": mr.id}


async def test_midterm_in_lecture_week_8_avoids_the_room_a_class_holds(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        ids = await _seed(s)
        run = ScheduleRun(term_id=ids["term"], kind="EXAM", horizon="TERM", params={"seed": 0, "workers": 1})
        inp, _m = await build_solver_input(s, run)
    assert sm.Block(ids["a101"], 8, 1, 3, 4) in inp.blocks
    assert run.stats[ecp.STATS_KEY]["status"] == "applied"
    assert run.stats[ecp.STATS_KEY]["course_run_id"] == ids["course_run"]
    assert run.stats[ecp.STATS_KEY]["dates"] == [WEEK8_MON.isoformat()]
    res = solve(inp)
    assert res.hard_score == 100, [d.message for d in res.diagnoses]
    (a,) = res.assignments
    assert a.room_ids == (ids["a102"],)  # ... but a class holds it on that date


async def test_without_a_published_course_run_nothing_is_blocked_and_it_says_so(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        ids = await _seed(s, publish_course=False)
        run = ScheduleRun(term_id=ids["term"], kind="EXAM", horizon="TERM", params={"seed": 0, "workers": 1})
        inp, _m = await build_solver_input(s, run)
    assert not [b for b in inp.blocks if b.room_id == ids["a101"]]
    assert run.stats[ecp.STATS_KEY] == {"status": "not_published", "exam_dates": 1}
    (a,) = solve(inp).assignments
    assert a.room_ids == (ids["a101"],)  # the preference wins when no class is known


async def test_class_plan_blocks_only_the_exam_weekday_of_the_exam_week(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        ids = await _seed(s, exam_date=WEEK8_MON + dt.timedelta(days=1))  # Tuesday: the class meets on Mondays
        term = await s.get(Term, ids["term"])
        assert term is not None
        weeks_rows = list((await s.execute(select(Week).where(Week.term_id == term.id))).scalars())
        ev = sm.Event(
            id=ids["exam"],
            kind="exam",
            label="KIM101",
            size=25,
            duration=2,
            weeks=frozenset({8}),
            fixed_day=2,
            fixed_start=3,
            allowed_days=frozenset({2}),
            fixed_date=WEEK8_MON + dt.timedelta(days=1),
        )
        blocks, stats = await ecp.course_blocks(s, term, weeks_rows, [ev])
    assert blocks == [] and stats["status"] == "applied" and stats["blocks"] == 0


async def test_course_run_gets_the_reverse_warning_for_a_published_exam_in_its_room(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        ids = await _seed(s)
        exam_run = ScheduleRun(term_id=ids["term"], kind="EXAM", horizon="TERM", status="OPTIMAL", is_active=True)
        s.add(exam_run)
        await s.flush()
        s.add(
            Assignment(
                run_id=exam_run.id,
                exam_request_id=ids["exam"],
                weeks=[8],
                day=1,
                date=WEEK8_MON,
                start_period=4,
                end_period=5,
                room_ids=[ids["a101"]],
                label="KIM101",
            )
        )
        await s.commit()
        course_run = await s.get(ScheduleRun, ids["course_run"])
        assert course_run is not None
        items = await ecp.exam_overlaps(s, course_run)
    (it,) = items
    assert it["code"] == "exam_overlap" and it["severity"] == "warning"
    assert it["params"]["week"] == 8 and it["params"]["date"] == WEEK8_MON.isoformat()
    assert it["message_tr"].startswith("FIZ 101 (A101, 3.–4. ders) 8. hafta 6 Nisan 2026 Pazartesi")
    assert "KIM101" in it["message_tr"] and "KIM101" in it["message"]
    assert sorted(it["request_ids"]) == sorted([ids["mr"], ids["exam"]])


async def test_exams_in_exam_weeks_or_a_finals_term_see_no_class_plan(engine):  # type: ignore[no-untyped-def]
    """Final exams sit in EXAM weeks (no classes then): no block, no warning, nothing in the stats."""
    async with get_session_factory()() as s:
        ids = await _seed(s)
        week8 = (await s.execute(select(Week).where(Week.term_id == ids["term"], Week.index == 8))).scalar_one()
        week8.kind = "EXAM"
        await s.commit()
        term = await s.get(Term, ids["term"])
        assert term is not None
        weeks_rows = list((await s.execute(select(Week).where(Week.term_id == term.id))).scalars())
        ev = sm.Event(
            id=ids["exam"],
            kind="exam",
            label="KIM101",
            size=25,
            duration=2,
            weeks=frozenset({8}),
            fixed_day=1,
            fixed_start=3,
            allowed_days=frozenset({1}),
            fixed_date=WEEK8_MON,
        )
        assert await ecp.course_blocks(s, term, weeks_rows, [ev]) == ([], {})
        term.kind = "FINAL"
        week8.kind = "LECTURE"
        assert await ecp.course_blocks(s, term, weeks_rows, [ev]) == ([], {})
