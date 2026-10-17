"""Real-fixture databases for the planning-analytics tests (scenario comparison, heatmaps, invigilators).

Two SQLite files are built once per test session and copied per test:

* ``bahar``: the 2026 Bahar planning list + room master; run A = week 3 solved like ``POST /runs``; run B = the
  same week with the busiest room of A closed on Wednesday (a real scenario: "what if A's busiest room is shut on
  Wednesdays?"), so classes move between the two runs;
* ``final``: the Bahar list (the instructors and their teaching), the room master, the Final board and the Final
  exam list; the Bahar term gets its real calendar (16 Feb 2026, 15 weeks, so the May exam dates fall in weeks
  13-15 of teaching), Bahar week 13 is solved and published (the teaching the invigilators have during the
  exams), the Final exam run is solved like ``POST /runs`` (A) and again with A's busiest exam room closed on
  its busiest date (B).
"""

from __future__ import annotations

import datetime as dt
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from app.core import db as dbmod
from app.models import Assignment, Base, ConstraintRow, ScheduleRun, Term
from sqlalchemy import select

from tests.conftest import BAHAR_LIST, EXAM_LIST, FINAL_GRID, FIXTURES

_CACHE: dict[str, tuple[Path, dict[str, Any]]] = {}
COURSE_PARAMS = {"time_limit_s": 30.0, "seed": 0, "solver": "cpsat", "publish_candidate": True, "workers": 8}
EXAM_PARAMS = {"time_limit_s": 30.0, "seed": 0, "solver": "cpsat", "workers": 8}
BAHAR_START = dt.date(2026, 2, 16)


async def _solve(factory: Any, run: ScheduleRun) -> int:
    from app.services.solver_bridge import run_schedule

    async with factory() as s:
        s.add(run)
        await s.commit()
        rid = run.id
    await run_schedule(factory, rid)
    async with factory() as s:
        row = await s.get(ScheduleRun, rid)
        assert row is not None and row.status in ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"), (
            row.status if row else None
        )
    return rid


async def _busiest_room(factory: Any, run_id: int, day: int | None = None) -> int:
    async with factory() as s:
        rows = (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars().all()
    c: Counter[int] = Counter()
    for a in rows:
        if day is not None and a.day != day:
            continue
        for r in a.room_ids or []:
            c[int(r)] += a.end_period - a.start_period + 1
    return min(c, key=lambda r: (-c[r], r))


async def build_bahar(workdir: Path) -> tuple[Path, dict[str, Any]]:
    if "bahar" in _CACHE:
        return _CACHE["bahar"]
    from app.importers.planning_list import import_planning_list
    from app.importers.room_master import import_room_master

    path = workdir / "bahar.db"
    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = dbmod.get_session_factory()
    async with factory() as s:
        await import_planning_list(s, BAHAR_LIST, "2026-BAHAR")
        await import_room_master(s, FIXTURES / "room_master.csv")
        await s.commit()
        term_id = (await s.execute(select(Term.id).where(Term.code == "2026-BAHAR"))).scalar_one()
    a_id = await _solve(
        factory,
        ScheduleRun(
            term_id=term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [3]},
            params=dict(COURSE_PARAMS),
            label="Bahar 3. hafta",
        ),
    )
    room = await _busiest_room(factory, a_id, day=3)
    async with factory() as s:
        b = ScheduleRun(
            term_id=term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [3]},
            params=dict(COURSE_PARAMS),
            label="Bahar 3. hafta, en yoğun derslik çarşamba kapalı",
        )
        s.add(b)
        await s.flush()
        s.add(
            ConstraintRow(
                term_id=None,
                run_id=b.id,
                kind="room_closed",
                params={"room_id": room, "day": 3, "start": 1, "end": 18, "weeks": [3]},
                hardness="hard",
                weight=1,
                source="ADMIN",
                nl_text="En yoğun derslik çarşamba kapalı",
            )
        )
        await s.commit()
        b_id = b.id
    from app.services.solver_bridge import run_schedule

    await run_schedule(factory, b_id)
    async with factory() as s:
        row = await s.get(ScheduleRun, b_id)
        assert row is not None and row.status in ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"), row and row.status
        ra = await s.get(ScheduleRun, a_id)
        assert ra is not None
        ra.is_active = True
        await s.commit()
    await dbmod.dispose_engine()
    _CACHE["bahar"] = (path, {"term_id": term_id, "a": a_id, "b": b_id, "closed_room": room})
    return _CACHE["bahar"]


async def build_final(workdir: Path) -> tuple[Path, dict[str, Any]]:
    if "final" in _CACHE:
        return _CACHE["final"]
    from app.importers.exam_list import import_exam_list
    from app.importers.planning_list import import_planning_list
    from app.importers.room_master import import_room_master
    from app.importers.weekly_grid import import_weekly_grid

    path = workdir / "final.db"
    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = dbmod.get_session_factory()
    async with factory() as s:
        await import_planning_list(s, BAHAR_LIST, "2026-BAHAR")
        await import_room_master(s, FIXTURES / "room_master.csv")
        await import_weekly_grid(s, FINAL_GRID, "2026-FINAL", year=2026)
        await import_exam_list(s, EXAM_LIST, "2026-FINAL")
        bahar = (await s.execute(select(Term).where(Term.code == "2026-BAHAR"))).scalar_one()
        bahar.start_date = BAHAR_START
        bahar.week_count = 15
        bahar.end_date = BAHAR_START + dt.timedelta(weeks=15) - dt.timedelta(days=3)
        final_id = (await s.execute(select(Term.id).where(Term.code == "2026-FINAL"))).scalar_one()
        await s.commit()
        bahar_id = bahar.id
    teach_id = await _solve(
        factory,
        ScheduleRun(
            term_id=bahar_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"weeks": [13]},
            params=dict(COURSE_PARAMS),
            label="Bahar 13. hafta (yayında)",
        ),
    )
    async with factory() as s:
        row = await s.get(ScheduleRun, teach_id)
        assert row is not None
        row.is_active = True
        await s.commit()
    exam_id = await _solve(
        factory,
        ScheduleRun(
            term_id=final_id, kind="EXAM", horizon="TERM", horizon_params={}, params=dict(EXAM_PARAMS), label="Final"
        ),
    )
    # scenario B of the exams: the busiest exam room of run A closed on its busiest exam date
    async with factory() as s:
        rows = (await s.execute(select(Assignment).where(Assignment.run_id == exam_id))).scalars().all()
    use: Counter[tuple[int, dt.date]] = Counter()
    for a in rows:
        for r in a.room_ids or []:
            if a.date is not None:
                use[(int(r), a.date)] += 1
    (room, day), _n = min(use.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
    async with factory() as s:
        final = await s.get(Term, final_id)
        assert final is not None
        from app.services.calendar import week_index_for_date

        week = week_index_for_date(final, day)
        b = ScheduleRun(
            term_id=final_id,
            kind="EXAM",
            horizon="TERM",
            horizon_params={},
            params=dict(EXAM_PARAMS),
            label="Final, en yoğun sınav salonu bir gün kapalı",
        )
        s.add(b)
        await s.flush()
        s.add(
            ConstraintRow(
                term_id=None,
                run_id=b.id,
                kind="room_closed",
                params={"room_id": room, "day": day.isoweekday(), "start": 1, "end": 18, "weeks": [week]},
                hardness="hard",
                weight=1,
                source="ADMIN",
                nl_text="En yoğun sınav salonu bir gün kapalı",
            )
        )
        await s.commit()
        exam_b = b.id
    from app.services.solver_bridge import run_schedule

    await run_schedule(factory, exam_b)
    async with factory() as s:
        row = await s.get(ScheduleRun, exam_b)
        assert row is not None and row.status in ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL", "INFEASIBLE"), row
    await dbmod.dispose_engine()
    _CACHE["final"] = (
        path,
        {
            "bahar_id": bahar_id,
            "final_id": final_id,
            "teach_run": teach_id,
            "exam_run": exam_id,
            "exam_run_b": exam_b,
            "exam_closed": {"room_id": room, "date": day.isoformat()},
        },
    )
    return _CACHE["final"]


def copy_db(base: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "api.db"
    shutil.copyfile(base, dst)
    return dst


#: a short deterministic budget for the test plans (the production default is 20 s)
PLAN_PARAMS = {"time_limit_s": 4.0}


async def build_final_plan(workdir: Path) -> tuple[Path, dict[str, Any]]:
    """``final`` plus one invigilation plan of the Final exam run (default rules, solved like the queue job)."""
    if "final_plan" in _CACHE:
        return _CACHE["final_plan"]
    from app.models import User
    from app.services import invigilation as svc
    from app.services.seed import seed_admin

    base, ids = await build_final(workdir)
    path = workdir / "final_plan.db"
    shutil.copyfile(base, path)
    dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    factory = dbmod.get_session_factory()
    async with factory() as s:
        await seed_admin(s)
        admin = (await s.execute(select(User).order_by(User.id))).scalars().first()
        assert admin is not None
        plan = await svc.create_plan(s, ids["exam_run"], dict(PLAN_PARAMS), admin, label="Final gözetmenleri")
        plan_id = plan.id
    await svc.run_plan(factory, plan_id)
    await dbmod.dispose_engine()
    _CACHE["final_plan"] = (path, {**ids, "plan": plan_id})
    return _CACHE["final_plan"]
