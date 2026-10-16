# ruff: noqa: RUF001, RUF002, RUF003  (the Turkish run labels the spec looks up)
"""Seed the runs the planning-analytics specs read (e2e/analytics.spec.ts) and publish the imported board.

E2E stack only (e2e-backend-entry.sh, after the Bahar imports, the room master and the full-term solve; the Final
board and exam list are imported by the entry script with the CLI). Mirrors tests/planning_analytics_support.py
on the e2e database, with the labels the spec looks up:

  "Bahar 3. hafta (A)"                                     Bahar week 3, solved like POST /runs
  "Bahar 3. hafta, en yoğun derslik çarşamba kapalı (B)"   week 3 again with A's busiest Wednesday room closed
  "Final (A)"                                              the 2026-FINAL exam run
and the week-3 run calendar.spec.ts edits ("e2e: Bahar 3. hafta (takvim düzenlemeleri)").

    python e2e-seed-analytics.py            (cwd: smartsched/backend; DATABASE_URL as for the CLI)

Env: E2E_ANALYTICS_TIME_LIMIT (seconds per solve, default 60).
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from typing import Any

TIME_LIMIT = float(os.environ.get("E2E_ANALYTICS_TIME_LIMIT", "60"))
USABLE = ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL")


async def main() -> int:
    sys.path.insert(0, os.getcwd())  # app/ lives in the backend directory
    from app.core.config import get_settings
    from app.core.db import configure_engine, create_all, get_session_factory
    from app.models import Assignment, ConstraintRow, ScheduleRun, Term
    from app.services.solver_bridge import run_schedule
    from sqlalchemy import select

    configure_engine(get_settings().database_url)
    await create_all()
    factory = get_session_factory()

    async def term_id(code: str) -> int:
        async with factory() as s:
            tid = (await s.execute(select(Term.id).where(Term.code == code))).scalar_one_or_none()
        if tid is None:
            raise SystemExit(f"term {code} is not imported")
        return int(tid)

    async def solve(run: ScheduleRun, closure: dict[str, Any] | None = None, *, need: tuple[str, ...] = USABLE) -> int:
        async with factory() as s:
            s.add(run)
            await s.flush()
            if closure is not None:
                s.add(
                    ConstraintRow(
                        term_id=None,
                        run_id=run.id,
                        kind="room_closed",
                        params=closure,
                        hardness="hard",
                        weight=1,
                        source="ADMIN",
                        nl_text="En yoğun derslik çarşamba kapalı",
                    )
                )
            await s.commit()
            rid = int(run.id)
        await run_schedule(factory, rid)
        async with factory() as s:
            row = await s.get(ScheduleRun, rid)
            status = row.status if row else None
        print(f"e2e analytics seed: run #{rid} {run.label!r} -> {status}", flush=True)
        if status not in need:
            raise SystemExit(f"run #{rid} {run.label!r} finished {status}")
        return rid

    def course(tid: int, label: str) -> ScheduleRun:
        return ScheduleRun(
            term_id=tid,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"week": 3, "weeks": [3]},
            params={"time_limit_s": TIME_LIMIT, "solver": "cpsat", "publish_candidate": True},
            label=label,
        )

    bahar = await term_id("2026-BAHAR")
    a_id = await solve(course(bahar, "Bahar 3. hafta (A)"))
    # A's busiest room on Wednesday (most occupied periods; ties by id), closed for scenario B
    async with factory() as s:
        rows = (await s.execute(select(Assignment).where(Assignment.run_id == a_id))).scalars().all()
    use: Counter[int] = Counter()
    for a in rows:
        if a.day == 3:
            for r in a.room_ids or []:
                use[int(r)] += a.end_period - a.start_period + 1
    room = min(use, key=lambda r: (-use[r], r))
    await solve(
        course(bahar, "Bahar 3. hafta, en yoğun derslik çarşamba kapalı (B)"),
        {"room_id": room, "day": 3, "start": 1, "end": 18, "weeks": [3]},
    )
    # the term's imported weekly board is its published timetable (the heatmap's "Yayındaki program"), as on a real
    # install after the grid import; not A: a week-3 run as the published plan would leave every other week empty
    # for the specs that read the published plan (room pages, booking grid, moderation)
    async with factory() as s:
        runs = (
            (
                await s.execute(
                    select(ScheduleRun)
                    .where(ScheduleRun.term_id == bahar, ScheduleRun.kind == "COURSE")
                    .order_by(ScheduleRun.id)
                )
            )
            .scalars()
            .all()
        )
        board = next((r for r in runs if (r.params or {}).get("source") == "GRID_IMPORT"), None)
        if board is None:
            raise SystemExit("2026-BAHAR has no grid-import board run")
        for r in runs:  # off first: one active run per (term, kind) is a unique index
            r.is_active = False
        await s.flush()
        board.is_active = True
        await s.commit()
        print(f"e2e analytics seed: board run #{board.id} published", flush=True)

    # the run calendar.spec.ts moves classes in (move + undo leaves it "edited", and an edited run is re-checked
    # against the bookings on publishing): its own run, so the full-term run stays publishable for wave2.spec.ts 1
    # and reserve.spec.ts 14 whatever ran before them (e2e/global-setup.ts sets E2E_EDIT_RUN from this label)
    await solve(course(bahar, "e2e: Bahar 3. hafta (takvim düzenlemeleri)"))

    final = await term_id("2026-FINAL")
    await solve(
        ScheduleRun(
            term_id=final,
            kind="EXAM",
            horizon="TERM",
            horizon_params={},
            params={"time_limit_s": TIME_LIMIT, "solver": "cpsat"},
            label="Final (A)",
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
