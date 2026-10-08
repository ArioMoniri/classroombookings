"""Exam room sharing in the bridge (``Event.share_room``) and joint-lecture merging, on synthetic rows and
on the real Final fixture (planner's locked definitive rooms)."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest
from app.core.db import get_session_factory
from app.importers.exam_list import import_exam_list
from app.importers.weekly_grid import import_weekly_grid
from app.models import ExamRequest, Program, Room, ScheduleRun, Term
from app.services.solver_bridge import build_solver_input
from app.solver.domains import shares_room
from sqlalchemy import select

from tests.conftest import EXAM_LIST, FINAL_GRID


def _cpsat():
    try:
        from app.solver.cpsat import solve
    except ModuleNotFoundError:  # pragma: no cover
        pytest.skip("cpsat not available")
    return solve


async def _seed_exams(session, sizes: list[int]) -> tuple[Term, Room]:
    term = Term(code="2026-FINAL-T", name="Final", kind="FINAL", start_date=dt.date(2026, 6, 1), week_count=2)
    room = Room(code="A204", display_name="A 204", capacity=156, exam_capacity=60, tags=[])
    session.add_all([term, room])
    await session.flush()
    for i, size in enumerate(sizes):
        prog = Program(name=f"Programme {i}", canonical_name=f"programme {i}")
        session.add(prog)
        await session.flush()
        session.add(
            ExamRequest(
                term_id=term.id,
                course_code=f"PSİ{100 + i}",
                course_name="Sınav",
                program_id=prog.id,
                class_year=1,
                class_years=[1],
                enrolment=size,
                date=dt.date(2026, 6, 3),
                start_period=4,
                end_period=5,
                status="LOCKED",
                definitive_room_ids=[room.id],
                needs_room=True,
            )
        )
    await session.commit()
    return term, room


@pytest.mark.parametrize(("sizes", "feasible"), [([20, 25], True), ([20, 25, 30], False)])
async def test_locked_exams_share_one_room_within_seats(engine, sizes, feasible):
    solve = _cpsat()
    async with get_session_factory()() as s:
        term, _room = await _seed_exams(s, sizes)
        run = ScheduleRun(term_id=term.id, kind="EXAM", horizon="TERM", horizon_params={}, params={})
        inp, _members = await build_solver_input(s, run)
    assert len(inp.events) == len(sizes)
    assert all(e.share_room and e.max_rooms == 1 and shares_room(e) for e in inp.events)
    res = solve(replace(inp, trust_locked_rooms=False, best_effort=False))
    if feasible:  # 45 seats <= 60 exam seats: no "locked assignments overlap" any more
        assert res.status in {"OPTIMAL", "FEASIBLE"}, [d.message for d in res.diagnoses]
        assert len({a.room_ids for a in res.assignments}) == 1
    else:  # 75 > 60: the seat budget is still enforced (strict mode)
        assert res.status == "INFEASIBLE"
        # run default trust_locked_rooms: the planner's over-full room is kept and reported as a warning
        trusted = solve(inp)
        assert trusted.status in {"OPTIMAL", "FEASIBLE"} and trusted.hard_score == 100
        assert any(d.code == "trusted_lock_capacity" and d.params.get("shared") for d in trusted.diagnoses)


async def test_final_fixture_locked_single_room_exams_no_longer_clash(engine):
    """Real Final plan: the planner seats several exams in one room. Before ``share_room`` every such
    pair was reported as "locked assignments overlap"; now no pair of single-room exams is."""
    solve = _cpsat()
    async with get_session_factory()() as s:
        await import_weekly_grid(s, FINAL_GRID, "2026-FINAL", year=2026)
        await import_exam_list(s, EXAM_LIST, "2026-FINAL")
        term = (await s.execute(select(Term).where(Term.code == "2026-FINAL"))).scalar_one()
        run = ScheduleRun(term_id=term.id, kind="EXAM", horizon="TERM", horizon_params={}, params={"time_limit_s": 20})
        inp, _members = await build_solver_input(s, run)
    by_id = {e.id: e for e in inp.events}
    assert all(e.share_room for e in inp.events)
    sharing = [e for e in inp.events if shares_room(e)]
    assert len(sharing) > 200  # locked to one definitive room each
    res = solve(inp)
    overlaps = [d for d in res.diagnoses if d.message.startswith("locked assignments overlap")]
    both_sharing = [d for d in overlaps if all(shares_room(by_id[i]) for i in d.event_ids)]
    assert both_sharing == []
    # what remains involves a split (multi-room) locked exam, which the solver keeps exclusive
    assert all(any(by_id[i].max_rooms > 1 for i in d.event_ids) for d in overlaps)


def test_merge_joint_lectures_keeps_planner_rooms():
    """Güz rows: CSE 101 §1 is listed for three programmes (85 + 50 + 40) at the same time with the same
    instructor; the planner locked two of them to A 204 (156): those two are one event of 135 locked to A 204.
    The unlocked third row shares only the instructor, so it is not chained into the locked lecture (review
    B1): it stays a request of its own (its clash is a reported input conflict).  A different-room pair is
    left alone."""
    from app.services.solver_bridge import merge_joint_lectures
    from app.solver import model as sm

    wk = frozenset({3})

    def ev(i: int, label: str, size: int, rooms: tuple[int, ...] | None, ins: str, start: int = 1) -> sm.Event:
        return sm.Event(
            id=i,
            kind="course",
            label=label,
            size=size,
            duration=3,
            weeks=wk,
            fixed_day=1,
            fixed_start=start,
            allowed_days=frozenset({1}),
            cohort_keys=frozenset({f"PROG:p{i}:Y1"}),
            instructor_keys=frozenset({ins}),
            locked=sm.Assignment(i, 1, start, start + 2, rooms, wk) if rooms else None,
        )

    events = [
        ev(1, "CSE 101 §1", 85, (10,), "INS:7"),
        ev(2, "CSE 101 §1", 50, (10,), "INS:7"),
        ev(3, "CSE 101 §1", 40, None, "INS:7"),
        ev(4, "MAT 101", 60, (11,), "INS:8"),
        ev(5, "MAT 103", 60, (12,), "INS:8"),  # same instructor, different planner room: not merged
        ev(6, "FİZ 111", 30, None, "INS:9", start=5),
    ]
    members = {e.id: [e.id] for e in events}
    out, merged = merge_joint_lectures(events, members, {10: 156, 11: 58, 12: 58})
    assert len(out) == 5 and len(merged) == 1
    joint = next(e for e in out if e.id == 1)
    assert joint.label == "CSE 101 §1" and joint.size == 135 and "clipped_to" not in merged[0]
    assert joint.locked is not None and joint.locked.room_ids == (10,) and joint.lock_trusted
    assert joint.cohort_keys == {"PROG:p1:Y1", "PROG:p2:Y1"}
    assert members[1] == [1, 2] and 2 not in members and members[3] == [3]
    assert {e.id for e in out} == {1, 3, 4, 5, 6}
