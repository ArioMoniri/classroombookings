"""Real-data feasibility (docs/testing/2026-10-08-real-data-feasibility.md): the bridge's run modes
(``trust_locked_rooms`` D1, ``fixed_conflicts_as_warnings`` D2, ``best_effort`` D3, ``definitive_rooms``)
on a small synthetic term, the real Bahar static check, and — with ``SMARTSCHED_SLOW=1`` — the real
Bahar week-3 solve."""

from __future__ import annotations

import os

import pytest
from app.core.db import get_session_factory
from app.importers.planning_list import import_planning_list
from app.importers.room_master import import_room_master
from app.importers.weekly_grid import import_weekly_grid
from app.models import (
    Assignment,
    Course,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
)
from app.services.data_issues import build_data_issues
from app.services.solver_bridge import MODE_DEFAULTS, build_solver_input, run_schedule
from sqlalchemy import select

from tests.conftest import BAHAR_GRID, BAHAR_LIST, FIXTURES

SLOW = pytest.mark.skipif(os.environ.get("SMARTSCHED_SLOW") != "1", reason="slow; set SMARTSCHED_SLOW=1")


async def _seed(session) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """ACU 132 (122 students) locked to A 207 (120); MAT 101 / MAT 205 fixed at overlapping times with one
    instructor; MAT 300 free; LAB 1 locked to a lab outside the room pool (no capacity, not bookable)."""
    term = Term(code="T-REAL", name="t", week_count=1)
    session.add(term)
    await session.flush()
    rooms = {
        code: Room(code=code, display_name=code, capacity=cap, exam_capacity=cap // 2, tags=[], is_bookable=book)
        for code, cap, book in (("A207", 120, True), ("A204", 156, True), ("A101", 58, True), ("A701", 0, False))
    }
    session.add_all(rooms.values())
    prog = Program(name="Odyoloji", canonical_name="odyoloji")
    ins = Instructor(full_name="Dr. Ayşe Kaya", canonical_name="ayse kaya")
    session.add_all([prog, ins])
    await session.flush()
    ids: dict[str, int] = {f"room:{k}": r.id for k, r in rooms.items()}

    async def meeting(code: str, year: int, size: int, day: int, start: int, end: int, locked: str | None):  # type: ignore[no-untyped-def]
        course = Course(code=code.replace(" ", ""), display_code=code)
        session.add(course)
        await session.flush()
        sec = Section(
            term_id=term.id,
            course_id=course.id,
            program_id=prog.id,
            class_year=year,
            class_years=[year],
            enrolment=size,
            source_key=code,
        )
        session.add(sec)
        await session.flush()
        session.add(SectionInstructor(section_id=sec.id, instructor_id=ins.id, role="PRIMARY"))
        mr = MeetingRequest(
            section_id=sec.id,
            day=day,
            days=[day],
            start_period=start,
            end_period=end,
            weeks=[1],
            status="LOCKED" if locked else "PARSED",
            definitive_room_ids=[rooms[locked].id] if locked else [],
            needs_room=True,
        )
        session.add(mr)
        await session.flush()
        ids[code] = mr.id

    await meeting("ACU 132", 1, 122, 1, 3, 4, "A207")
    await meeting("MAT 101", 2, 40, 2, 3, 5, None)
    await meeting("MAT 205", 3, 40, 2, 4, 5, None)  # same instructor, overlaps P4-P5
    await meeting("MAT 300", 4, 30, 3, 1, 2, None)
    await meeting("LAB 1", 4, 20, 4, 1, 2, "A701")
    await session.commit()
    ids["term"] = term.id
    return ids


async def _run(factory, term_id: int, **params) -> ScheduleRun:  # type: ignore[no-untyped-def]
    async with factory() as s:
        run = ScheduleRun(
            term_id=term_id, kind="COURSE", horizon="TERM", params={"time_limit_s": 10, "solver": "cpsat", **params}
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    await run_schedule(factory, run_id)
    async with factory() as s:
        out = await s.get(ScheduleRun, run_id)
        assert out is not None
        return out


async def test_bridge_modes_default_on_and_real_data_run_is_feasible(engine):
    factory = get_session_factory()
    async with factory() as s:
        ids = await _seed(s)
        probe = ScheduleRun(term_id=ids["term"], kind="COURSE", horizon="TERM", params={})
        inp, _members = await build_solver_input(s, probe)
    assert MODE_DEFAULTS["trust_locked_rooms"] and MODE_DEFAULTS["fixed_conflicts_as_warnings"]
    assert inp.trust_locked_rooms and inp.fixed_conflicts_as_warnings and inp.best_effort
    ev = {e.label: e for e in inp.events}
    assert ev["LAB 1"].needs_room is False and ev["LAB 1"].locked is None  # A 701 is outside the pool
    run = await _run(factory, ids["term"])
    assert run.status in {"OPTIMAL", "FEASIBLE"} and run.hard_score == 100, run.diagnosis
    codes = {d["code"] for d in run.diagnosis}
    assert {"trusted_lock_capacity", "input_conflict", "outside_room_pool"} <= codes
    acu = next(d for d in run.diagnosis if d["code"] == "trusted_lock_capacity")
    assert "ACU 132 expects 122 students but is locked to A207 (60 exam / 120 lecture seats)" in acu["message"]
    clash = next(d for d in run.diagnosis if d["code"] == "input_conflict")
    assert "Dr. Ayşe Kaya" in clash["message"]  # instructor keys are humanised
    assert run.stats["warnings_by_code"]["input_conflict"] == 1 and run.stats["errors_by_code"] == {}
    async with factory() as s:
        rows = {
            a.meeting_request_id: a
            for a in (await s.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars()
        }
    assert rows[ids["ACU 132"]].room_ids == [ids["room:A207"]]
    assert rows[ids["LAB 1"]].room_ids == [ids["room:A701"]]  # the planner's room, kept
    assert (rows[ids["MAT 101"]].start_period, rows[ids["MAT 205"]].start_period) == (3, 4)


async def test_strict_modes_give_a_best_effort_partial_run(engine):
    factory = get_session_factory()
    async with factory() as s:
        ids = await _seed(s)
    run = await _run(factory, ids["term"], trust_locked_rooms=False, fixed_conflicts_as_warnings=False)
    assert run.status == "FEASIBLE_PARTIAL" and run.stats["partial"] is True  # stats.partial kept for old clients
    assert run.stats["events_total"] == 5 and run.stats["placed"] == 3 and run.stats["unplaced"] == 2
    assert run.hard_score == 100  # the placed events satisfy every hard rule
    async with factory() as s:
        n = len((await s.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars().all())
    assert n == 3  # F6: the partial timetable is stored, the grid shows it
    codes = [d["code"] for d in run.diagnosis]
    assert codes[0] == "partial" and "locked_ineligible" in codes and "fixed_conflict" in codes
    assert run.stats["errors_by_code"]["fixed_conflict"] == 1
    off = await _run(
        factory, ids["term"], trust_locked_rooms=False, fixed_conflicts_as_warnings=False, best_effort=False
    )
    assert off.status == "INFEASIBLE" and "partial" not in off.stats
    async with factory() as s:
        assert not (await s.execute(select(Assignment).where(Assignment.run_id == off.id))).scalars().all()


async def test_definitive_rooms_as_hints(engine):
    factory = get_session_factory()
    async with factory() as s:
        ids = await _seed(s)
        run = ScheduleRun(term_id=ids["term"], kind="COURSE", horizon="TERM", params={"definitive_rooms": "prefer"})
        inp, _m = await build_solver_input(s, run)
    acu = next(e for e in inp.events if e.label == "ACU 132")
    assert acu.locked is None and acu.preferred_room_ids[0] == ids["room:A207"]
    assert acu.size == 120  # D1 for hints: the planner seats 122 expected students in 120 seats
    assert "trusted_hint_capacity" in {d["code"] for d in run.stats["bridge_diagnoses"]}
    # only the choice inside the pool becomes a hint: LAB 1 keeps its lab outside the pool (as with locks)
    # instead of competing for pooled rooms it never used
    lab = next(e for e in inp.events if e.label == "LAB 1")
    assert lab.needs_room is False and lab.locked is None
    assert "outside_room_pool" in {d["code"] for d in run.stats["bridge_diagnoses"]}
    res = await _run(factory, ids["term"], definitive_rooms="prefer")
    assert res.status in {"OPTIMAL", "FEASIBLE"}  # the hint holds: ACU 132 stays in A 207
    strict = await _run(factory, ids["term"], definitive_rooms="prefer", trust_definitive_capacity=False)
    assert strict.status in {"OPTIMAL", "FEASIBLE"}  # full capacity required: ACU 132 moves to A 204 (156)
    async with factory() as s:
        rooms = {}
        for rid in (res.id, strict.id):
            a = (
                await s.execute(
                    select(Assignment).where(Assignment.run_id == rid, Assignment.meeting_request_id == ids["ACU 132"])
                )
            ).scalar_one()
            rooms[rid] = a.room_ids
        lab_rows = (
            await s.execute(
                select(Assignment).where(Assignment.run_id == res.id, Assignment.meeting_request_id == ids["LAB 1"])
            )
        ).scalar_one()
    assert rooms == {res.id: [ids["room:A207"]], strict.id: [ids["room:A204"]]}
    assert lab_rows.room_ids == [ids["room:A701"]]
    # data-issues report: the clipped hint is listed once, per class, in "planned rooms too small"
    async with factory() as s:
        run_row = await s.get(ScheduleRun, res.id)
        assert run_row is not None
        report = await build_data_issues(s, run_row)
    small = next(g for g in report["groups"] if g["code"] == "locked_room_too_small")
    acu_items = [it for it in small["items"] if ids["ACU 132"] in it["request_ids"]]
    assert [it["code"] for it in acu_items] == ["trusted_hint_capacity"], acu_items
    assert acu_items[0]["message_tr"].startswith("ACU 132: beklenen 122 öğrenci, planlayıcının dersliği A207 120")


async def _import_bahar(session) -> int:  # type: ignore[no-untyped-def]
    await import_weekly_grid(session, BAHAR_GRID, "2026-BAHAR", year=2026)
    await import_planning_list(session, BAHAR_LIST, "2026-BAHAR")
    await import_room_master(session, FIXTURES / "room_master.csv")
    return (await session.execute(select(Term.id).where(Term.code == "2026-BAHAR"))).scalar_one()


async def test_real_bahar_week3_static_check_has_no_blockers_from_locks_or_fixed_clashes(engine):
    """With the defaults, the planner's locked rooms and fixed-vs-fixed clashes are warnings; PC-lab
    requests have eligible rooms (F2); what remains as errors is real (locked overlaps in the data)."""
    from app.solver.build import prepare
    from app.solver.diagnose import static_check

    async with get_session_factory()() as s:
        term_id = await _import_bahar(s)
        run = ScheduleRun(term_id=term_id, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]}, params={})
        inp, _m = await build_solver_input(s, run)
    diags = static_check(prepare(inp))
    errors = [d for d in diags if d.severity == "error"]
    warns = [d for d in diags if d.severity == "warning"]
    assert not [d for d in errors if d.code in {"locked_ineligible", "fixed_conflict"}]
    assert not [d for d in errors if d.code == "no_room" and d.params.get("reason") == "tags"]  # PC labs exist
    assert sum(1 for d in warns if d.code == "input_conflict") > 50
    assert sum(1 for d in warns if d.code == "trusted_lock_capacity") > 10
    assert {d.code for d in errors} <= {"locked_overlap", "pigeonhole", "no_room", "no_time"}
    assert len(errors) < 20
    pc = [e for e in inp.events if "PC" in e.required_tags]
    assert pc and all(any("PC" in r.tags for r in inp.rooms) for _ in pc)
    # planner text of the real trusted_lock_tags case (run-5 payload shape): the room code is filled in
    from dataclasses import asdict

    from app.services.data_issues import TextContext, planner_text

    tags = next(asdict(d) for d in warns if d.code == "trusted_lock_tags")
    labels = {e.id: e.label for e in inp.events}
    codes = {r.id: r.code for r in inp.rooms}
    text = planner_text(tags, TextContext(labels=labels, rooms=codes))
    room = tags["params"]["room_codes"][0]
    assert f"kilitli dersliği {room} " in text["tr"] and "  " not in text["tr"], text
    assert f"is locked to {room}" in text["en"] and "#" not in text["tr"]
    # without room_codes (older stored payloads) the ids are resolved through the context
    old = {**tags, "params": {k: v for k, v in tags["params"].items() if k != "room_codes"}}
    assert f"kilitli dersliği {room} " in planner_text(old, TextContext(labels=labels, rooms=codes))["tr"]


@SLOW
async def test_real_bahar_week3_places_planner_rooms_with_hard_100(engine):
    """SMARTSCHED_SLOW=1: Bahar week 3 (cpsat, defaults): hard 100, >= 98 % of the planner-roomed events
    (LOCKED definitive rooms in the pool) placed, >= 95 % of all room-needing events, every unplaced one
    explained."""
    factory = get_session_factory()
    async with factory() as s:
        term_id = await _import_bahar(s)
        run = ScheduleRun(
            term_id=term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [3]},
            params={"time_limit_s": 120, "solver": "cpsat", "seed": 0},
        )
        s.add(run)
        await s.commit()
        run_id = run.id
        probe = ScheduleRun(term_id=term_id, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]}, params={})
        inp, members = await build_solver_input(s, probe)
        locked = {e.id for e in inp.events if e.locked is not None}
        roomed = {e.id for e in inp.events if e.needs_room}
    await run_schedule(factory, run_id)
    async with factory() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run is not None
        placed_requests = {
            a.meeting_request_id
            for a in (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars()
        }
    assert run.hard_score == 100, run.diagnosis[:3]
    placed = {h for h, ms in members.items() if set(ms) & placed_requests}
    assert len(placed & locked) >= 0.98 * len(locked), (len(placed & locked), len(locked))
    assert len(placed & roomed) >= 0.95 * len(roomed), (len(placed & roomed), len(roomed))
    unplaced = set(run.stats.get("unplaced_ids") or [])
    assert unplaced == {e.id for e in inp.events} - placed
    explained = {i for d in run.diagnosis if d["severity"] == "error" for i in d["event_ids"]}
    assert unplaced <= explained


async def test_real_final_locked_plan_validates(engine):
    """F5: the planner's locked Final plan (split exams sharing room pairs, over-full trusted rooms) is
    kept and validates; only exams whose locked room is blocked by the planner's own grid stay unplaced."""
    from app.importers.exam_list import import_exam_list
    from app.solver.cpsat import solve
    from app.solver.repair import validate

    from tests.conftest import EXAM_LIST, FINAL_GRID

    async with get_session_factory()() as s:
        await import_weekly_grid(s, FINAL_GRID, "2026-FINAL", year=2026)
        await import_exam_list(s, EXAM_LIST, "2026-FINAL")
        await import_room_master(s, FIXTURES / "room_master.csv")
        term_id = (await s.execute(select(Term.id).where(Term.code == "2026-FINAL"))).scalar_one()
        run = ScheduleRun(term_id=term_id, kind="EXAM", horizon="TERM", params={"time_limit_s": 60, "workers": 4})
        inp, _m = await build_solver_input(s, run)
    split_shared = [e for e in inp.events if e.share_room and e.locked is not None and len(e.locked.room_ids) > 1]
    assert len(split_shared) > 50
    res = solve(inp)
    assert res.hard_score == 100, [d.message for d in res.diagnoses if d.code == "internal"]
    placed = {a.event_id for a in res.assignments}
    assert len(placed) >= 0.97 * len(inp.events), (len(placed), len(inp.events))
    sub = type(inp)(**{**inp.__dict__, "events": tuple(e for e in inp.events if e.id in placed)})
    assert not [v for v in validate(sub, res.assignments) if v.hard]
    errors = {d.code for d in res.diagnoses if d.severity == "error"}
    assert errors <= {"no_room", "locked_ineligible", "unplaced", "unplaced_summary"}, errors
    assert any(d.code == "trusted_lock_capacity" and d.params.get("shared") for d in res.diagnoses)


@SLOW
async def test_real_bahar_full_term_keeps_planner_locks_through_blocked_weeks(engine):
    """SMARTSCHED_SLOW=1: Bahar *full term* (cpsat, defaults, week segments on).  Before week segments, 14
    locked lectures whose room the grid blocks in one week (ETKİNLİK, HAZIRLIK ...) were lost for the
    whole term (648/684 placed, roomed 94.0 %, planner-roomed 96.2 %).  Now: hard 100, >= 97.5 % of the
    planner-locked events placed in *every* week, >= 95.5 % of all room-needing events.  Measured
    2026-10-08 13:50 (300 s, 4 workers): 643/669 events (96.1 %), roomed 562/588, locked 511/523 = 97.7 %
    with the relaxation and phase 2 both OPTIMAL; 8 of the 12 lost locks are the planner's own locked-room
    overlaps / a lock on a room blocked at all its times, the other 4 give way to more placed events.
    (98 % held for the 532 locks before joint lectures with the same locked rooms were merged.)  Week 1
    alone admits at most 578/603 room-needing events, so the week-3 rate is not reachable for "every week
    of every event" on this data."""
    factory = get_session_factory()
    async with factory() as s:
        term_id = await _import_bahar(s)
        run = ScheduleRun(
            term_id=term_id,
            kind="COURSE",
            horizon="TERM",
            params={"time_limit_s": 300, "solver": "cpsat", "seed": 0},
        )
        s.add(run)
        await s.commit()
        run_id = run.id
        probe = ScheduleRun(term_id=term_id, kind="COURSE", horizon="TERM", params={})
        inp, _members = await build_solver_input(s, probe)
        locked = {e.id for e in inp.events if e.locked is not None}
        roomed = {e.id for e in inp.events if e.needs_room}
    await run_schedule(factory, run_id)
    async with factory() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run is not None
        rows = list((await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars())
    assert run.hard_score == 100, run.diagnosis[:3]
    assert run.status == "FEASIBLE_PARTIAL" and run.stats["events_total"] == len(inp.events)
    unplaced = set(run.stats["unplaced_ids"])  # not placed in every week (partially placed included)
    full = {e.id for e in inp.events} - unplaced
    assert len(full & locked) >= 0.975 * len(locked), (len(full & locked), len(locked))
    assert len(full & roomed) >= 0.955 * len(roomed), (len(full & roomed), len(roomed))
    assert len(full) >= 0.96 * len(inp.events), (len(full), len(inp.events))  # phase 9 target
    splits = [d for d in run.diagnosis if d["code"] == "week_split"]
    assert sum(1 for d in splits if d["params"]["reason"] == "blocked") >= 10
    assert sum(1 for d in run.diagnosis if d["code"] == "locked_ineligible") <= 3  # true double locks only
    by_request: dict[int, list[Assignment]] = {}
    for a in rows:
        by_request.setdefault(a.meeting_request_id or 0, []).append(a)
    moved = [v for v in by_request.values() if len(v) > 1]
    assert moved and all(len({(a.day, a.start_period, a.end_period) for a in v}) == 1 for v in moved)  # same time
    explained = {i for d in run.diagnosis if d["severity"] == "error" for i in d["event_ids"]}
    assert unplaced <= explained
