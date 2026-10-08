"""Strict solver review (docs/review/2026-10-08-solver-review.md), bridge / API side: joint-lecture merges
(B1), untrusted carried locks and the fix button (B2), missing enrolments (M1), manual moves re-scored and
split by week (M4), the data-issues report (M6), the cancel race, empty scopes, and the orchestrator's
R1 (one lecture listed twice in prefer mode) and "same lecture listed twice" label.  Each run is checked at
planner level with :mod:`app.services.planner_check`."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.db import get_session_factory
from app.models import (
    Assignment,
    Course,
    ExamRequest,
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
from app.services.planner_check import check_run
from app.services.solver_bridge import (
    _member_placements,
    build_solver_input,
    merge_joint_lectures,
    run_schedule,
)
from app.solver import model as sm
from sqlalchemy import select

from tests.api_fixtures import login


class Seed:
    """A one-week course term with rooms, one programme and instructors."""

    def __init__(self, session: Any) -> None:
        self.s = session
        self.ids: dict[str, int] = {}

    async def term(self, code: str = "T-REV", weeks: int = 1) -> int:
        term = Term(code=code, name=code, week_count=weeks)
        self.s.add(term)
        await self.s.flush()
        self.ids["term"] = term.id
        self.prog = Program(name="Psikoloji", canonical_name="psikoloji")
        self.s.add(self.prog)
        await self.s.flush()
        return term.id

    async def rooms(self, *spec: tuple[str, int, list[str], bool]) -> None:
        for code, cap, tags, bookable in spec:
            r = Room(
                code=code, display_name=code, capacity=cap, exam_capacity=cap // 2, tags=tags, is_bookable=bookable
            )
            self.s.add(r)
            await self.s.flush()
            self.ids[f"room:{code}"] = r.id

    async def instructor(self, name: str) -> int:
        ins = Instructor(full_name=name, canonical_name=name.lower())
        self.s.add(ins)
        await self.s.flush()
        return ins.id

    async def meeting(
        self,
        key: str,
        code: str,
        *,
        section: str | None = None,
        size: int | None = 30,
        year: int = 1,
        day: int = 1,
        start: int = 1,
        end: int = 2,
        locked: list[str] | None = None,
        instructor: int | None = None,
        weeks: list[int] | None = None,
    ) -> int:
        course = (await self.s.execute(select(Course).where(Course.code == code.replace(" ", "")))).scalar_one_or_none()
        if course is None:
            course = Course(code=code.replace(" ", ""), display_code=code)
            self.s.add(course)
            await self.s.flush()
        sec = Section(
            term_id=self.ids["term"],
            course_id=course.id,
            program_id=self.prog.id,
            label=section,
            class_year=year,
            class_years=[year],
            enrolment=size,
            source_key=key,
        )
        self.s.add(sec)
        await self.s.flush()
        if instructor is not None:
            self.s.add(SectionInstructor(section_id=sec.id, instructor_id=instructor, role="PRIMARY"))
        mr = MeetingRequest(
            section_id=sec.id,
            day=day,
            days=[day],
            start_period=start,
            end_period=end,
            weeks=weeks or [1],
            status="LOCKED" if locked else "PARSED",
            definitive_room_ids=[self.ids[f"room:{r}"] for r in locked or []],
            needs_room=True,
        )
        self.s.add(mr)
        await self.s.flush()
        self.ids[key] = mr.id
        return mr.id


async def _solve(term_id: int, kind: str = "COURSE", **params: Any) -> ScheduleRun:
    factory = get_session_factory()
    async with factory() as s:
        run = ScheduleRun(
            term_id=term_id, kind=kind, horizon="TERM", params={"time_limit_s": 10, "workers": 2, **params}
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    await run_schedule(factory, run_id)
    async with factory() as s:
        out = await s.get(ScheduleRun, run_id)
        assert out is not None
        return out


async def _planner_ok(run: ScheduleRun) -> Any:
    async with get_session_factory()() as s:
        row = await s.get(ScheduleRun, run.id)
        assert row is not None
        res = await check_run(s, row)
    assert res.violations == [], [f.as_dict() for f in res.violations]
    return res


# --------------------------------------------------------------------------- M1: missing enrolment


async def test_missing_enrolment_gets_a_reported_fallback_size(engine):
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term()
        await seed.rooms(("A101", 58, [], True), ("A204", 156, [], True))
        await seed.meeting("s1", "MAT 101", section="1", size=120, day=1)
        await seed.meeting("s2", "MAT 101", section="2", size=None, day=2)  # no enrolment: like §1 (120)
        await s.commit()
        probe = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={})
        inp, _m = await build_solver_input(s, probe)
    ev = {e.id: e for e in inp.events}
    assert ev[seed.ids["s2"]].size == 120  # not 0: the capacity check stays on
    fb = probe.stats["enrolment_fallbacks"][str(seed.ids["s2"])]
    assert fb == {"size": 120, "source": "course_sections"}
    waste = [c for c in inp.constraints if c.kind == "min_capacity_waste"]
    assert waste and waste[0].params["exclude_event_ids"] == [seed.ids["s2"]]
    run = await _solve(tid)
    d = next(d for d in run.diagnosis if d["code"] == "missing_enrolment")
    assert d["params"]["sources"] == ["course_sections"] and "120 students" in d["text"]["en"]
    async with get_session_factory()() as s:
        row = await s.get(ScheduleRun, run.id)
        assert row is not None
        rep = await build_data_issues(s, row)
        a = (await s.execute(select(Assignment).where(Assignment.meeting_request_id == seed.ids["s2"]))).scalar_one()
    assert a.room_ids == [seed.ids["room:A204"]]  # 120 students do not go into A 101 (58)
    group = next(g for g in rep["groups"] if g["code"] == "missing_enrolment")
    assert group["count"] == 1 and group["items"][0]["request_ids"] == [seed.ids["s2"]]
    res = await _planner_ok(run)
    assert res.exceptions_by_cause() == {"missing_enrolment": 1}


# --------------------------------------------------------------------------- B1: merges


async def test_joint_lecture_merge_keeps_locks_and_members_keep_their_own_rows(engine):
    """Two programme rows locked to A 101 at P1-P2 and P1-P3 (one lecture listed twice): one event of 70
    in A 101 (58 seats, trusted lock: reported); each request is stored with its own periods.  A third
    row of the same course with the same instructor but no lock is not chained into the locked lecture."""
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term()
        await seed.rooms(("A101", 58, [], True), ("A204", 156, [], True))
        ins = await seed.instructor("Dr. Ayşe Kaya")
        await seed.meeting("a", "CSE 101", section="1", size=40, end=2, locked=["A101"], instructor=ins)
        await seed.meeting("b", "CSE 101", section="1", size=30, year=2, end=3, locked=["A101"], instructor=ins)
        await seed.meeting("c", "CSE 101", section="1", size=20, year=3, end=2, instructor=ins)
        await s.commit()
    run = await _solve(tid)
    members = run.stats["event_members"]
    assert members == {str(seed.ids["a"]): [seed.ids["a"], seed.ids["b"]]}
    assert any(d["code"] == "trusted_lock_capacity" and d["params"]["size"] == 70 for d in run.diagnosis)
    async with get_session_factory()() as s:
        rows = {
            a.meeting_request_id: a
            for a in (await s.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars()
        }
    assert (rows[seed.ids["a"]].start_period, rows[seed.ids["a"]].end_period) == (1, 2)
    assert (rows[seed.ids["b"]].start_period, rows[seed.ids["b"]].end_period) == (1, 3)
    assert rows[seed.ids["a"]].room_ids == rows[seed.ids["b"]].room_ids == [seed.ids["room:A101"]]
    assert rows[seed.ids["c"]].room_ids == [seed.ids["room:A204"]]  # a request of its own
    assert any(d["code"] == "input_conflict" for d in run.diagnosis)  # same instructor at one time: reported
    res = await _planner_ok(run)
    assert res.exceptions_by_cause()["D1"] == 1


def _ev(i: int, label: str, *, start: int = 1, dur: int = 2, locked: tuple[int, ...] | None = None) -> sm.Event:
    wk = frozenset({1})
    return sm.Event(
        id=i,
        kind="course",
        label=label,
        size=30,
        duration=dur,
        weeks=wk,
        fixed_day=5,
        fixed_start=start,
        allowed_days=frozenset({5}),
        locked=sm.Assignment(i, 5, start, start + dur - 1, locked, wk) if locked else None,
    )


def test_same_lecture_rules_in_lock_and_prefer_mode():
    """BME 528 (P8-10) and BME 528 §1 (P7-9) both locked to B 204: one lecture; SYS 18 and SYS 018 §1 with the
    same planner room in prefer mode (no locks): one lecture too (orchestrator R1)."""
    members = {1: [1], 2: [2]}
    out, merged = merge_joint_lectures(
        [_ev(1, "BME 528", start=8, dur=3, locked=(24,)), _ev(2, "BME 528 §1", start=7, dur=3, locked=(24,))],
        members,
    )
    assert len(out) == 1 and members == {1: [1, 2]} and merged[0]["span"] == [7, 10]
    assert out[0].locked is not None and out[0].locked.room_ids == (24,)
    members2 = {1: [1], 2: [2], 3: [3]}
    out2, _m2 = merge_joint_lectures(
        [_ev(1, "SYS 18"), _ev(2, "SYS 018 §1"), _ev(3, "SYS 19")], members2, planner_sets={1: [7], 2: [7], 3: [8]}
    )
    assert len(out2) == 2 and members2[1] == [1, 2] and members2[3] == [3]
    # without the planner's rooms (and no shared instructor) nothing is merged
    out3, _m3 = merge_joint_lectures([_ev(1, "SYS 18"), _ev(2, "SYS 018 §1")], {1: [1], 2: [2]})
    assert len(out3) == 2


def test_member_placements_keep_own_periods_weeks_and_planner_rooms():
    a = sm.Assignment(1, 1, 3, 5, (10, 11, 12), frozenset({15}))
    info = {
        1: {"start": 3, "end": 4, "date": None, "weeks": None, "locked": True, "definitive": [10, 99]},
        2: {"start": 3, "end": 5, "date": None, "weeks": None, "locked": True, "definitive": [11, 12]},
        3: {"start": 3, "end": 5, "date": None, "weeks": None, "locked": False, "definitive": []},
    }
    out = _member_placements(a, [1, 2, 3], info, {1: [99]})
    assert out == [
        (1, 3, 4, (10, 99), frozenset({15})),  # its own room (+ its room outside the pool)
        (2, 3, 5, (11, 12), frozenset({15})),
        (3, 3, 5, (10, 11, 12), frozenset({15})),  # unlocked member: the group's rooms
    ]
    moved = sm.Assignment(1, 1, 6, 8, (13,), frozenset({15}))
    shifted = _member_placements(moved, [1, 2], info, {})
    assert shifted == [(1, 6, 7, (13,), frozenset({15})), (2, 6, 8, (13,), frozenset({15}))]


async def test_exam_cohort_group_spans_the_latest_end_and_keeps_partial_locks(engine):
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term("F-REV", weeks=16)
        await seed.rooms(("C301", 80, [], True), ("C201", 80, [], True))
        common = {"term_id": tid, "course_code": "ING302", "date": date(2026, 6, 3), "start_period": 2}
        e1 = ExamRequest(
            **common,
            end_period=3,
            enrolment=30,
            status="LOCKED",
            merge_key="k",
            definitive_room_ids=[seed.ids["room:C301"]],
        )
        e2 = ExamRequest(**common, end_period=4, enrolment=25, status="PARSED", merge_key="k")
        s.add_all([e1, e2])
        await s.commit()
        probe = ScheduleRun(term_id=tid, kind="EXAM", horizon="TERM", params={})
        inp, members = await build_solver_input(s, probe)
    (ev,) = inp.events
    assert ev.duration == 3 and ev.locked is not None and ev.locked.room_ids == (seed.ids["room:C301"],)
    assert members[ev.id] == [e1.id, e2.id] and ev.size == 55


# --------------------------------------------------------------------------- B2: carried locks, fix button


async def test_fix_button_lock_is_not_trusted_in_the_child_run(engine):
    """ING 302 (135) was placed by the fix button into A 107 (58): the child run checks capacity (no
    "planner's room is kept"), reports the carried lock, and stays valid at planner level."""
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term()
        await seed.rooms(("A107", 58, [], True), ("A204", 156, [], True))
        mid = await seed.meeting("ing", "ING 302", section="1", size=135)
        parent = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={}, status="FEASIBLE")
        s.add(parent)
        await s.flush()
        s.add(
            Assignment(
                run_id=parent.id,
                meeting_request_id=mid,
                weeks=[1],
                week=1,
                day=1,
                start_period=1,
                end_period=2,
                room_ids=[seed.ids["room:A107"]],
                is_locked=True,
                origin="MANUAL",
            )
        )
        await s.commit()
        child = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={}, parent_run_id=parent.id)
        inp, _m = await build_solver_input(s, child)
    (ev,) = inp.events
    assert ev.locked is not None and ev.lock_trusted is False
    assert any(d["code"] == "manual_lock" for d in child.stats["bridge_diagnoses"])
    async with get_session_factory()() as s:
        run = ScheduleRun(
            term_id=tid, kind="COURSE", horizon="TERM", params={"time_limit_s": 5}, parent_run_id=parent.id
        )
        s.add(run)
        await s.commit()
        rid = run.id
    await run_schedule(get_session_factory(), rid)
    async with get_session_factory()() as s:
        out = await s.get(ScheduleRun, rid)
        assert out is not None
    codes = {d["code"] for d in out.diagnosis}
    assert "trusted_lock_capacity" not in codes and "locked_ineligible" in codes
    await _planner_ok(out)


async def test_fix_refuses_a_room_set_that_cannot_seat_the_class(engine):
    from app.services.diagnosis_fixes import FixError, apply_option

    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term()
        await seed.rooms(("A107", 58, [], True), ("A101", 100, [], True), ("A204", 156, [], True))
        mid = await seed.meeting("ing", "ING 302", section="1", size=135)
        run = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={}, status="FEASIBLE_PARTIAL")
        s.add(run)
        await s.commit()
        run_id = run.id

        def diag(text: str) -> dict[str, Any]:
            from app.solver.options import options_for

            return {
                "event_ids": [mid],
                "message": "",
                "suggestions": [text],
                "params": {"options": options_for([text], "", [mid])},
            }

        try:
            await apply_option(s, run, diag("use A107 at day 1 P1-P2"), 0)
            raise AssertionError("A107 (58) must be refused for 135 students")
        except FixError as exc:
            assert "58" in str(exc) and "135" in str(exc)
        await s.rollback()
        run = await s.get(ScheduleRun, run_id, populate_existing=True)
        assert run is not None
        res = await apply_option(s, run, diag("use A101+A107 at day 1 P1-P2"), 0)
        await s.commit()
        assert res.details["room_ids"] == [seed.ids["room:A101"], seed.ids["room:A107"]]


# --------------------------------------------------------------------------- M4: manual moves


async def test_manual_move_rescores_and_splits_by_week(client, stub_solver):
    h = await login(client)
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term("T-MOVE", weeks=4)
        await seed.rooms(("A101", 58, [], True), ("A102", 58, [], True))
        await seed.meeting("x", "MAT 101", size=30, day=1, weeks=[1, 2, 3, 4], locked=["A101"])
        await seed.meeting("y", "FIZ 101", size=30, day=1, start=5, end=6, weeks=[1, 2, 3, 4], locked=["A102"])
        await s.commit()
    from app.workers.queue import get_queue

    r = await client.post("/api/v1/runs", json={"term_id": tid, "kind": "COURSE", "params": {}}, headers=h)
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    rows = (await client.get(f"/api/v1/runs/{run_id}/assignments", headers=h)).json()
    y = next(a for a in rows if a["meeting_request_id"] == seed.ids["y"])
    # forced double booking: y onto x's room and time -> the run is re-scored below 100
    body = {"day": 1, "start_period": 1, "end_period": 2, "room_ids": [seed.ids["room:A101"]], "force": True}
    moved = (await client.post(f"/api/v1/runs/{run_id}/assignments/{y['id']}/move", json=body, headers=h)).json()
    assert moved["ok"] and moved["hard_score"] < 100
    assert any(v["rule"] == "room_double_booking" for v in moved["violations"])
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["hard_score"] == moved["hard_score"] and run["stats"]["planner_check"]["violations"] >= 1
    # a move "in week 2" moves only week 2: the row keeps weeks 1, 3, 4
    x = next(a for a in rows if a["meeting_request_id"] == seed.ids["x"])
    body = {"day": 2, "start_period": 3, "end_period": 4, "week": 2, "room_ids": [seed.ids["room:A102"]]}
    r = await client.post(f"/api/v1/runs/{run_id}/assignments/{x['id']}/move", json=body, headers=h)
    assert r.json()["ok"], r.json()
    after = [
        a
        for a in (await client.get(f"/api/v1/runs/{run_id}/assignments", headers=h)).json()
        if a["meeting_request_id"] == seed.ids["x"]
    ]
    assert sorted(sorted(a["weeks"]) for a in after) == [[1, 3, 4], [2]]
    assert next(a for a in after if a["weeks"] == [2])["origin"] == "MANUAL"


# --------------------------------------------------------------------------- cancel race, data issues


async def test_result_commit_loses_against_a_cancel(engine):
    from app.workers.run_jobs import commit_unless_cancelled

    factory = get_session_factory()
    async with factory() as s:
        seed = Seed(s)
        tid = await seed.term()
        run = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={}, status="RUNNING")
        s.add(run)
        await s.commit()
        rid = run.id
    async with factory() as worker, factory() as api:
        wrun = await worker.get(ScheduleRun, rid)
        assert wrun is not None
        wrun.hard_score = 100  # the result being written ...
        arun = await api.get(ScheduleRun, rid)
        assert arun is not None
        arun.status = "CANCELLED"  # ... while the planner cancels
        await api.commit()
        assert await commit_unless_cancelled(worker, wrun, "FEASIBLE") is False
    async with factory() as s:
        final = await s.get(ScheduleRun, rid)
        assert final is not None and final.status == "CANCELLED" and final.hard_score is None


async def test_prefer_mode_report_keeps_the_list_checks_and_labels_duplicates(engine):
    async with get_session_factory()() as s:
        seed = Seed(s)
        tid = await seed.term()
        await seed.rooms(("A101", 58, [], True), ("A102", 58, [], True), ("A103", 58, ["PC"], True))
        await seed.meeting("p", "PSI 101", size=30, year=1, locked=["A101"])
        await seed.meeting("q", "MAT 205", size=30, year=2, locked=["A101"])  # same room, same time: overlap
        await seed.meeting("d1", "HEM 334", section="1", size=20, year=3, day=2)  # listed twice
        await seed.meeting("d2", "HEM 334", section="1", size=20, year=3, day=2)
        await s.commit()
    run = await _solve(tid, definitive_rooms="prefer")
    async with get_session_factory()() as s:
        row = await s.get(ScheduleRun, run.id)
        assert row is not None
        rep = await build_data_issues(s, row)
    groups = {g["code"]: g for g in rep["groups"]}
    overlap = groups["locked_room_overlap"]["items"]
    assert any(set(it["request_ids"]) == {seed.ids["p"], seed.ids["q"]} for it in overlap)
    twice = groups["same_lecture_twice"]["items"]
    assert twice and "listed twice" in twice[0]["message"]
    assert groups["fixed_cohort_clash"]["count"] == 0  # not reported as a cohort clash as well
    await _planner_ok(run)
