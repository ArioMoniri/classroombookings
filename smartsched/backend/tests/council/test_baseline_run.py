"""Schedule map -> baseline IMPORT run (P19-I5) on the real Güz board + planning list.

Committing both files gives one IMPORT run whose assignments are matched to the meeting requests; a solve with
that run as its parent keeps the placements (stability); uploading both files again in a new job (and the
board once more as ICS) creates no duplicate row."""

from __future__ import annotations

from collections import Counter

import pytest
from app.core.db import get_session_factory
from app.models import Assignment, MeetingRequest, ScheduleRun, Section
from app.services.solver_bridge import run_schedule
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.council.conftest import GUZ_GRID, GUZ_LIST
from tests.council.test_formats_api import upload

TERM = {"code": "2026-GUZ", "name": "Güz 2026-2027", "week_count": 14}


async def _commit(client, h, job_id: int, **extra) -> dict:
    body = {"files": [0, 1], "term": TERM, "allow_pending": True, **extra}
    r = await client.post(f"/api/v1/council/jobs/{job_id}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _rows() -> dict[str, int]:
    async with get_session_factory()() as s:
        return {
            m.__tablename__: int((await s.execute(select(func.count()).select_from(m))).scalar_one())
            for m in (ScheduleRun, Assignment, MeetingRequest, Section)
        }


@pytest.mark.slow  # the real Güz week-1 CP-SAT solve (one worker): about 6 minutes with the uploads
async def test_guz_board_and_list_give_a_baseline_run_that_a_child_solve_keeps(client):
    h = await login(client)
    files = [(GUZ_GRID.name, GUZ_GRID.read_bytes()), (GUZ_LIST.name, GUZ_LIST.read_bytes())]
    job = await upload(client, h, *files)
    assert [f["route"] for f in job["files"]] == ["fast:weekly-grid", "fast:planning-list"]
    dry = await _commit(client, h, job["id"], dry_run=True)
    out = await _commit(client, h, job["id"])
    base = out["baseline_run"]
    assert base["run_created"] and base["created"] > 500 and base["linked"] >= 0.8 * base["created"], base
    assert dry["counts"]["assignments"]["create"] == out["changes"]["assignments"]["create"]

    async with get_session_factory()() as s:
        run = await s.get(ScheduleRun, base["run_id"])
        assert run is not None and run.label == "Baseline: imported schedule" and run.kind == "COURSE"
        assert run.params["source"] == "COUNCIL_BASELINE"
        assert [x["file"] for x in run.params["sources"]] == [GUZ_GRID.name]  # the file the entries came from
        rows = list((await s.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars())
        assert {a.origin for a in rows} == {"IMPORT"} and {a.week for a in rows} == {1, 2}
        linked = {a.meeting_request_id: a for a in rows if a.meeting_request_id and a.week == 1}
        # the child: week 1 re-solved from the baseline (deterministic, one worker)
        child = ScheduleRun(
            term_id=run.term_id,
            kind="COURSE",
            horizon="WEEK",
            horizon_params={"week": 1, "weeks": [1]},
            params={"time_limit_s": 90.0, "workers": 1, "seed": 0},
            parent_run_id=run.id,
            status="QUEUED",
        )
        s.add(child)
        await s.commit()
        child_id = child.id
    await run_schedule(get_session_factory(), child_id)
    async with get_session_factory()() as s:
        child = await s.get(ScheduleRun, child_id)
        assert child is not None and child.status in ("OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"), child.error
        placed = list((await s.execute(select(Assignment).where(Assignment.run_id == child_id))).scalars())
    kept = Counter()
    for a in placed:
        b = linked.get(a.meeting_request_id)
        if b is None:
            continue
        same_time = (a.day, a.start_period) == (b.day, b.start_period)
        kept["same_slot" if same_time else "moved"] += 1
        kept["same_room" if same_time and list(a.room_ids) == list(b.room_ids) else "other_room"] += 1
    total = kept["same_slot"] + kept["moved"]
    assert total >= 0.8 * len(linked), (total, len(linked))
    assert kept["same_slot"] >= 0.95 * total and kept["same_room"] >= 0.9 * total, kept

    # the same two files in a new job: nothing is duplicated, the run is the same one
    before = await _rows()
    job2 = await upload(client, h, *files)
    again = await _commit(client, h, job2["id"])
    assert again["baseline_run"]["run_id"] == base["run_id"] and again["baseline_run"]["created"] == 0
    assert again["baseline_run"]["unchanged"] == base["created"]
    after = await _rows()
    # the board importer's own "Grid import" runs and their rows are re-used too
    assert after == before, (before, after)
    async with get_session_factory()() as s:
        run = await s.get(ScheduleRun, base["run_id"])
        assert run is not None and len(run.params["sources"]) == 1  # the same board twice: one source (sha256)
