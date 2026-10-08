"""``FEASIBLE_PARTIAL``: a best-effort run that stored a partial timetable is its own terminal status
(``stats.partial`` stays for older clients); list filters, the dashboard and the SSE stream know it."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.db import get_session_factory
from app.models import ScheduleRun, Term
from app.schemas.runs import RUN_STATUSES, TERMINAL_STATUSES
from app.services.dashboard import utilisation_run
from app.services.solver_bridge import PARTIAL_STATUS, run_status
from app.solver.model import Assignment, SolverResult

from tests.api_fixtures import login


def _result(status: str, partial: bool, n: int) -> SolverResult:
    a = [Assignment(i, 1, 1, 2, (1,), frozenset({1})) for i in range(n)]
    return SolverResult(status, a, 100, 90, {}, [], {"partial": True} if partial else {})  # type: ignore[arg-type]


def test_run_status_maps_partial_results() -> None:
    assert PARTIAL_STATUS == "FEASIBLE_PARTIAL" and PARTIAL_STATUS in RUN_STATUSES and PARTIAL_STATUS in TERMINAL_STATUSES
    assert len(PARTIAL_STATUS) <= 16  # ScheduleRun.status is String(16)
    assert run_status(_result("INFEASIBLE", True, 3)) == "FEASIBLE_PARTIAL"
    assert run_status(_result("INFEASIBLE", True, 0)) == "INFEASIBLE"  # nothing stored: plain infeasible
    assert run_status(_result("INFEASIBLE", False, 0)) == "INFEASIBLE"
    assert run_status(_result("OPTIMAL", False, 3)) == "OPTIMAL"
    assert {"QUEUED", "RUNNING"}.isdisjoint(TERMINAL_STATUSES)


async def _add_run(status: str, **kw) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        term = (await s.execute(Term.__table__.select().where(Term.code == "T-PART"))).first()
        if term is None:
            t = Term(code="T-PART", name="partial", week_count=1)
            s.add(t)
            await s.flush()
            term_id = t.id
        else:
            term_id = term.id
        run = ScheduleRun(
            term_id=term_id,
            kind="COURSE",
            horizon="TERM",
            params={},
            status=status,
            stats={"partial": True, "placed": 5, "unplaced": 1, "events_total": 6, "progress": 100},
            hard_score=100,
            soft_score=80,
            finished_at=datetime.now(UTC).replace(tzinfo=None),
            **kw,
        )
        s.add(run)
        await s.commit()
        return term_id, run.id


async def test_partial_run_is_listed_filtered_and_used_by_the_dashboard(client):
    h = await login(client)
    term_id, run_id = await _add_run("FEASIBLE_PARTIAL")
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["status"] == "FEASIBLE_PARTIAL" and run["progress"] == 100 and run["stats"]["partial"] is True
    listed = (await client.get("/api/v1/runs", params={"status": "FEASIBLE_PARTIAL"}, headers=h)).json()
    assert [r["id"] for r in listed] == [run_id]
    async with get_session_factory()() as s:
        picked = await utilisation_run(s, term_id)
    assert picked is not None and picked.id == run_id  # a partial timetable still has a utilisation
    _t, full_id = await _add_run("FEASIBLE")
    _t, newer_partial = await _add_run("FEASIBLE_PARTIAL")
    async with get_session_factory()() as s:
        picked = await utilisation_run(s, term_id)
    assert picked is not None and picked.id == full_id and newer_partial > full_id  # complete runs first


async def test_sse_stream_terminates_on_feasible_partial(client):
    """A finished partial run closes the stream at once; a running one closes when it turns partial."""
    h = await login(client)
    _term, done_id = await _add_run("FEASIBLE_PARTIAL")
    r = await asyncio.wait_for(client.get(f"/api/v1/runs/{done_id}/events", headers=h), timeout=10)
    assert r.status_code == 200 and '"status": "FEASIBLE_PARTIAL"' in r.text

    _term, live_id = await _add_run("RUNNING")

    async def finish_later() -> None:
        await asyncio.sleep(0.5)
        async with get_session_factory()() as s:
            row = await s.get(ScheduleRun, live_id)
            assert row is not None
            row.status = "FEASIBLE_PARTIAL"
            await s.commit()

    task = asyncio.create_task(finish_later())
    r = await asyncio.wait_for(client.get(f"/api/v1/runs/{live_id}/events", headers=h), timeout=15)
    await task
    assert "event: done" in r.text and '"status": "FEASIBLE_PARTIAL"' in r.text.split("event: done", 1)[1]
