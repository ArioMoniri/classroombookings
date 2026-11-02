"""Publish the imported weekly boards (owner report 2026-11-02 item 4).

A weekly-grid import creates the term's board as a finished run (``params.source = GRID_IMPORT``) but never
publishes it. The deploy seed loaded the owner's workbooks and stopped there, so the live site had no published
timetable: the occupancy heatmap's default source ("Yayındaki program" = the published runs) was empty, and
bookings ignored the classes of the imported grid. The e2e and recording stacks always published the board after
the import (deploy/pod-ci/gates/e2e-seed-analytics.py, scripts/record/stack.sh); this does the same for a real
install: ``python -m app.cli publish-imported-boards`` (seed step ``publish-boards``).

Per term and kind (COURSE, EXAM): when nothing is published yet, the newest finished grid-import run becomes the
published run, audited as ``run.activate`` (actor system). A term or kind that already has a published run (a
planner published a solver run, or an earlier seed did this) is left alone, so running it again changes nothing."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScheduleRun, Term
from app.services.events import publish_event

GRID_IMPORT = "GRID_IMPORT"
#: statuses a published run may have (app/api/v1/runs.py PUBLISHABLE)
FINISHED = ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL")


def is_grid_import(run: ScheduleRun) -> bool:
    return (run.params or {}).get("source") == GRID_IMPORT


async def publish_imported_boards(session: AsyncSession, term_code: str | None = None) -> list[dict[str, Any]]:
    """Publish every term's grid-import board where its term and kind have no published run. One row per
    (term, kind) with ``action`` = ``published`` / ``kept`` (already published) / ``none`` (no imported board)."""
    q = select(Term).order_by(Term.id)
    if term_code:
        q = q.where(Term.code == term_code)
    out: list[dict[str, Any]] = []
    for term in (await session.execute(q)).scalars():
        runs = list((await session.execute(select(ScheduleRun).where(ScheduleRun.term_id == term.id))).scalars())
        for kind in ("COURSE", "EXAM"):
            mine = [r for r in runs if r.kind == kind]
            active = next((r for r in mine if r.is_active), None)
            row: dict[str, Any] = {"term": term.code, "kind": kind}
            if active is not None:
                out.append({**row, "action": "kept", "run_id": active.id})
                continue
            boards = sorted((r for r in mine if is_grid_import(r) and r.status in FINISHED), key=lambda r: r.id)
            if not boards:
                out.append({**row, "action": "none", "run_id": None})
                continue
            board = boards[-1]
            board.is_active = True
            await session.flush()
            await publish_event(
                session,
                "run.activate",
                "run",
                board.id,
                before={"active_run_id": None},
                after={"active_run_id": board.id, "status": board.status, "label": board.label},
                reason="imported weekly board published (publish-imported-boards)",
                term_id=term.id,
            )
            out.append({**row, "action": "published", "run_id": board.id})
    return out


__all__ = ["GRID_IMPORT", "is_grid_import", "publish_imported_boards"]
