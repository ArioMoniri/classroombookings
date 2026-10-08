"""Planner-level regression tests on the real workbooks (strict solver review B1, B2, M1, M2; orchestrator R2).

Each test builds the term from the fixtures with the importers, runs ``solver_bridge.run_schedule`` exactly
like ``POST /runs`` and checks the **stored** run against the raw request rows with
:mod:`app.services.planner_check`: it fails on any violation, i.e. any unwaived finding or any accepted
exception (D1 trusted planner room, D2 fixed-time clash, D3 unplaced, week split, outside the pool, manual
placement, missing enrolment) that the run does not report.  ``tests/conftest.py`` lists them in
``SLOW_TESTS`` (``make test-slow``); the Bahar full term needs ``SMARTSCHED_SLOW=1``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from app.core import db as dbmod
from app.models import Assignment, ExamRequest, ScheduleRun
from app.services.planner_check import PlannerCheck, check_run
from sqlalchemy import select
from tools.validate_planner import INSTANCES, import_term

#: (term code) -> imported DB; (instance) -> (solved DB, run id); shared by the tests of this module
_TERMS: dict[str, Path] = {}
_RUNS: dict[str, tuple[Path, int]] = {}
WEEK_LIMIT = 120.0
WORKERS = 4


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("planner_level")


async def _term_db(workdir: Path, term: str) -> Path:
    if term not in _TERMS:
        path = workdir / f"{term}.db"
        await import_term(path, term)
        _TERMS[term] = path
    return _TERMS[term]


async def _solve(db: Path, name: str, *, time_limit: float, params: dict[str, Any] | None = None) -> int:
    from app.models import Term
    from app.services.solver_bridge import run_schedule

    spec = INSTANCES[name]
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    factory = dbmod.get_session_factory()
    async with factory() as s:
        term_id = (await s.execute(select(Term.id).where(Term.code == spec.term))).scalar_one()
        run = ScheduleRun(
            term_id=term_id,
            kind=spec.kind,
            horizon=spec.horizon,
            horizon_params=dict(spec.horizon_params),
            params={"time_limit_s": time_limit, "workers": WORKERS, "seed": 0, "solver": "cpsat", **(params or {})},
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    await run_schedule(factory, run_id)
    return run_id


async def _solved(workdir: Path, name: str, time_limit: float = WEEK_LIMIT) -> tuple[Path, int]:
    if name not in _RUNS:
        base = await _term_db(workdir, INSTANCES[name].term)
        db = workdir / f"{name}.db"
        shutil.copyfile(base, db)
        _RUNS[name] = (db, await _solve(db, name, time_limit=time_limit))
    return _RUNS[name]


async def _check(db: Path, run_id: int) -> tuple[ScheduleRun, PlannerCheck]:
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run is not None
        return run, await check_run(s, run)


def _assert_valid(run: ScheduleRun, res: PlannerCheck) -> None:
    sample = [f.as_dict() for f in res.violations[:10]]
    assert res.violations == [], f"run {run.id} {run.status}: {len(res.violations)} planner-level violations {sample}"
    assert res.hard_score == 100


async def _rows(db: Path, run_id: int, exam: bool) -> list[tuple[Any, ...]]:
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db}")
    async with dbmod.get_session_factory()() as s:
        rows = (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars()
        return sorted(
            (
                a.exam_request_id if exam else a.meeting_request_id,
                a.day,
                a.start_period,
                a.end_period,
                tuple(a.room_ids or []),
                tuple(sorted(a.weeks or [])),
            )
            for a in rows
        )


async def test_bahar_week3_is_valid_at_planner_level(workdir: Path) -> None:
    """B1 / M1: merged joint lectures keep the planner's rooms, no group sits over capacity unreported, every
    missing enrolment has a reported fallback size, every unplaced class is named."""
    db, run_id = await _solved(workdir, "bahar_w3")
    run, res = await _check(db, run_id)
    _assert_valid(run, res)
    causes = res.exceptions_by_cause()
    assert causes.get("missing_enrolment", 0) > 30 and causes.get("D3", 0) == res.requests_total - res.requests_placed
    assert res.placed_pct >= 94.0, res.summary()
    assert run.stats["accepted_exceptions"]  # the partial summary lists them by cause (M3)
    partial = next(d for d in run.diagnosis if d["code"] == "partial")
    assert "accepted exception" in partial["message"] and partial["params"]["exceptions"]
    await dbmod.dispose_engine()


async def test_bahar_week3_is_deterministic(workdir: Path) -> None:
    """M2: the same input and seed give the same timetable (canonical stages: one worker, deterministic
    time) — compared row by row with a second run."""
    db, run_id = await _solved(workdir, "bahar_w3")
    first = await _rows(db, run_id, exam=False)
    second_id = await _solve(db, "bahar_w3", time_limit=WEEK_LIMIT)
    second = await _rows(db, second_id, exam=False)
    assert len(first) == len(second) and first == second
    await dbmod.dispose_engine()


async def test_final_is_valid_at_planner_level(workdir: Path) -> None:
    """B1 for exams (each programme row keeps its own room of a split exam), M1 and R2: the size-0 Final
    exams TDS102 / BES250 / DYZ146 get a fallback size and a room."""
    db, run_id = await _solved(workdir, "final")
    run, res = await _check(db, run_id)
    _assert_valid(run, res)
    assert res.placed_pct >= 97.0, res.summary()
    async with dbmod.get_session_factory()() as s:
        codes = {"TDS102", "BES250", "DYZ146"}
        ids = {
            int(i)
            for i, c in (await s.execute(select(ExamRequest.id, ExamRequest.course_code))).all()
            if c.replace(" ", "") in codes
        }
        placed = {
            int(a.exam_request_id)
            for a in (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars()
            if a.exam_request_id is not None
        }
    assert ids and ids <= placed, sorted(ids - placed)
    await dbmod.dispose_engine()


async def test_fix_button_cases_leave_planner_valid_runs(workdir: Path) -> None:
    """B2 (the reviewer's fix cases T1-T4): apply the first four applicable move / release fixes of the
    Bahar week-3 run, each on its own copy, and solve the child run: every applied fix leaves a run that
    is valid at planner level; a fix whose rooms cannot seat the class is refused (422) instead."""
    from app.services.diagnosis_fixes import FixError, apply_option, structure_diagnosis

    db, run_id = await _solved(workdir, "bahar_w3")
    run, _res = await _check(db, run_id)
    cases: list[tuple[int, int]] = []
    for idx, d in enumerate(run.diagnosis):
        if d.get("code") != "unplaced":
            continue
        opts = structure_diagnosis(d, idx, run.kind)["suggestions"]
        hit = next((o for o in opts if o["applicable"] and o["action"] in ("move", "release_room")), None)
        if hit is not None:
            cases.append((idx, int(hit["index"])))
        if len(cases) == 4:
            break
    assert cases, "the Bahar week-3 run has no applicable move / release fix"
    applied = refused = 0
    for n, (idx, opt) in enumerate(cases):
        case_db = workdir / f"fix{n}.db"
        shutil.copyfile(db, case_db)
        dbmod.configure_engine(f"sqlite+aiosqlite:///{case_db}")
        factory = dbmod.get_session_factory()
        async with factory() as s:
            parent = await s.get(ScheduleRun, run_id)
            assert parent is not None
            try:
                await apply_option(s, parent, parent.diagnosis[idx], opt)
            except FixError as exc:
                await s.rollback()
                refused += 1
                assert "seat" in str(exc) or "room" in str(exc), str(exc)
                continue
            child = ScheduleRun(
                term_id=parent.term_id,
                kind=parent.kind,
                horizon=parent.horizon,
                horizon_params=dict(parent.horizon_params or {}),
                params={**dict(parent.params or {}), "time_limit_s": 40.0},
                parent_run_id=parent.id,
            )
            s.add(child)
            await s.commit()
            child_id = child.id
        from app.services.solver_bridge import run_schedule

        await run_schedule(factory, child_id)
        child_run, res = await _check(case_db, child_id)
        _assert_valid(child_run, res)
        applied += 1
        await dbmod.dispose_engine()
    assert applied + refused == len(cases)


@pytest.mark.skipif(os.environ.get("SMARTSCHED_SLOW") != "1", reason="Bahar full term (300 s); SMARTSCHED_SLOW=1")
async def test_bahar_term_is_valid_at_planner_level(workdir: Path) -> None:
    db, run_id = await _solved(workdir, "bahar_term", time_limit=300.0)
    run, res = await _check(db, run_id)
    _assert_valid(run, res)
    await dbmod.dispose_engine()
