"""Planner-level validation of real runs (``python -m tools.validate_planner``).

Builds SQLite databases from the real workbooks with the importers (cached per term), runs
``solver_bridge.run_schedule`` exactly like ``POST /runs`` and checks the stored run with
:mod:`app.services.planner_check` (the persisted rows against the raw request rows).  Prints one JSON line
per run: the planner-level summary (placed %, hard / strict-view score, violations by rule, accepted
exceptions by cause), the solver's own numbers and the reproduction rate (requests the planner gave a
definitive room in the pool that sit in exactly those rooms).

    cd smartsched/backend
    python -m tools.validate_planner --instances bahar_w3 guz_w3 final bahar_term --time-limit 120 \\
        --workers 4 --cache-dir /tmp/vp --out /tmp/vp/results.json

Exit status 1 when a run has a violation (an unwaived finding or an exception nobody reported).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


@dataclass(frozen=True)
class Spec:
    term: str
    kind: str
    horizon: str
    horizon_params: dict[str, Any]


INSTANCES: dict[str, Spec] = {
    "bahar_w3": Spec("2026-BAHAR", "COURSE", "WEEK", {"weeks": [3]}),
    "bahar_term": Spec("2026-BAHAR", "COURSE", "TERM", {}),
    "guz_w3": Spec("2026-GUZ", "COURSE", "WEEK", {"weeks": [3]}),
    "final": Spec("2026-FINAL", "EXAM", "TERM", {}),
}
FILES: dict[str, tuple[str, str]] = {
    "2026-BAHAR": ("bahar_derslikler_takvimi_2026.xlsx", "bahar_derslik_planlama_listesi_v5.xlsx"),
    "2026-GUZ": ("guz_derslikler_takvimi_2026_2027.xlsx", "guz_derslik_planlama_2026_2027_v2.xlsx"),
    "2026-FINAL": ("final_derslikler_takvimi_2026_v2.xlsx", "final_planlama_listesi_2026_v2.xlsx"),
}


def _env() -> None:
    os.environ.setdefault("APP_SECRET", "validate-planner-validate-planner-000000")
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
    os.environ.setdefault("ADMIN_PASSWORD", "admin1234")


async def import_term(db_path: Path, term: str, fixtures: Path = FIXTURES) -> None:
    """A fresh SQLite DB with the term's grid, planning / exam list and the room master."""
    from app.core import db as dbmod
    from app.importers.exam_list import import_exam_list
    from app.importers.planning_list import import_planning_list
    from app.importers.room_master import import_room_master
    from app.importers.weekly_grid import import_weekly_grid
    from app.models import Base

    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    grid, plan = FILES[term]
    async with dbmod.get_session_factory()() as s:
        await import_weekly_grid(s, fixtures / grid, term, year=2026)
        if term.endswith("FINAL"):
            await import_exam_list(s, fixtures / plan, term)
        else:
            await import_planning_list(s, fixtures / plan, term)
        await import_room_master(s, fixtures / "room_master.csv")
        await s.commit()
    await dbmod.dispose_engine()


async def reproduction(session: Any, run: Any) -> dict[str, Any]:
    """Requests the planner gave a LOCKED definitive room set inside the pool: how many are placed in
    exactly that set (every row of the request)."""
    from app.models import Assignment, ExamRequest, MeetingRequest, Room
    from sqlalchemy import select

    exam = run.kind == "EXAM"
    pool = {
        int(r.id)
        for r in (await session.execute(select(Room))).scalars()
        if r.is_bookable and ((r.exam_capacity or r.capacity) if exam else r.capacity)
    }
    model = ExamRequest if exam else MeetingRequest
    planner: dict[int, frozenset[int]] = {}
    for r in (await session.execute(select(model).where(model.status == "LOCKED"))).scalars():
        rooms = frozenset(int(x) for x in r.definitive_room_ids or [] if int(x) in pool)
        if rooms:
            planner[int(r.id)] = rooms
    rows: dict[int, list[frozenset[int]]] = {}
    for a in (await session.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars():
        rid = a.exam_request_id if exam else a.meeting_request_id
        if rid is not None:
            rows.setdefault(int(rid), []).append(frozenset(int(x) for x in a.room_ids or [] if int(x) in pool))
    placed = [rid for rid in planner if rid in rows]
    exact = sum(1 for rid in placed if all(rs == planner[rid] for rs in rows[rid]))
    overlap = sum(1 for rid in placed if all(rs & planner[rid] for rs in rows[rid]))
    n = max(1, len(placed))
    return {
        "planner_requests": len(planner),
        "planner_placed": len(placed),
        "repro_exact_pct": round(100.0 * exact / n, 1),
        "repro_overlap_pct": round(100.0 * overlap / n, 1),
    }


async def run_instance(
    db_path: Path, name: str, *, time_limit: float, workers: int, seed: int, params: dict[str, Any]
) -> dict[str, Any]:
    """Create a run like ``POST /runs``, solve it with ``run_schedule`` and check it at planner level."""
    from app.core import db as dbmod
    from app.models import ScheduleRun, Term
    from app.services.planner_check import check_run
    from app.services.solver_bridge import run_schedule
    from sqlalchemy import select

    spec = INSTANCES[name]
    dbmod.configure_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = dbmod.get_session_factory()
    async with factory() as s:
        term_id = (await s.execute(select(Term.id).where(Term.code == spec.term))).scalar_one()
        run = ScheduleRun(
            term_id=term_id,
            kind=spec.kind,
            horizon=spec.horizon,
            horizon_params=dict(spec.horizon_params),
            params={"time_limit_s": time_limit, "workers": workers, "seed": seed, "solver": "cpsat", **params},
        )
        s.add(run)
        await s.commit()
        run_id = run.id
    t0 = time.perf_counter()
    await run_schedule(factory, run_id)
    wall = round(time.perf_counter() - t0, 1)
    async with factory() as s:
        stored = await s.get(ScheduleRun, run_id)
        assert stored is not None
        result = await check_run(s, stored)
        repro = await reproduction(s, stored)
        stats = stored.stats or {}
        out = {
            "instance": name,
            "params": params,
            "time_limit_s": time_limit,
            "workers": workers,
            "seed": seed,
            "wall_s": wall,
            "status": stored.status,
            "solver_hard": stored.hard_score,
            "events_placed": stats.get("placed"),
            "events_total": stats.get("events_total"),
            "relax_status": stats.get("relax_status"),
            "phase2_status": stats.get("phase2_status"),
            "planner": result.summary(),
            "reproduction": repro,
            "violations_sample": [f.as_dict() for f in result.violations[:15]],
        }
    await dbmod.dispose_engine()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instances", nargs="*", default=["bahar_w3", "guz_w3", "final"], choices=sorted(INSTANCES))
    ap.add_argument("--time-limit", type=float, default=120.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--params", default="{}", help='extra run params as JSON, e.g. {"definitive_rooms": "prefer"}')
    ap.add_argument("--cache-dir", type=Path, help="keep the imported term databases here (reused when present)")
    ap.add_argument("--out", type=Path, help="append the JSON lines to this file")
    ap.add_argument("--fixtures", type=Path, default=FIXTURES, help="the workbooks + room_master.csv")
    ap.add_argument("--keep-db", type=Path, help="copy each solved run's database into this directory")
    args = ap.parse_args(argv)
    _env()
    params = json.loads(args.params)
    tmp = Path(tempfile.mkdtemp(prefix="validate-planner-"))
    cache = args.cache_dir or tmp
    cache.mkdir(parents=True, exist_ok=True)
    failed = False
    try:
        for name in args.instances:
            term = INSTANCES[name].term
            base = cache / f"{term}.db"
            if not base.exists():
                part = cache / f"{term}.importing.db"
                part.unlink(missing_ok=True)
                asyncio.run(import_term(part, term, args.fixtures))
                part.replace(base)  # a failed import never leaves a half-built cache behind
            work = tmp / f"{name}.db"
            shutil.copyfile(base, work)
            res = asyncio.run(
                run_instance(
                    work, name, time_limit=args.time_limit, workers=args.workers, seed=args.seed, params=params
                )
            )
            if args.keep_db:
                args.keep_db.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work, args.keep_db / f"{name}.db")
            line = json.dumps(res, ensure_ascii=False, default=str)
            print(line, flush=True)
            if args.out:
                with args.out.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            failed = failed or bool(res["planner"]["violations"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
