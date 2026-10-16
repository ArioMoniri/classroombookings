"""Commit ``baseline`` modes and the dry run's ``result.baseline_run`` (batch 4, 2026-10-16) on the real Güz board.

``baseline.mode``: ``auto`` (default: the term's one baseline run), ``skip`` (the schedule map is not written) or
``run`` + ``run_id`` (another COURSE run of the term). The dry run reports the same ``baseline_run`` the commit
would (``run_id`` null while the run would be new), so the Fark step reads it directly."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.council.baseline import LABEL, SOURCE
from app.models import Assignment, ScheduleRun, Term
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.council.conftest import GUZ_GRID
from tests.council.test_formats_api import upload

TERM = {"code": "2026-GUZ", "name": "Güz 2026-2027", "week_count": 14}


async def _post(client, h, job_id: int, **extra):
    body = {"files": [0], "term": TERM, "allow_pending": True, **extra}
    return await client.post(f"/api/v1/council/jobs/{job_id}/commit", headers=h, json=body)


async def _ok(client, h, job_id: int, **extra) -> dict:
    r = await _post(client, h, job_id, **extra)
    assert r.status_code == 200, r.text
    return r.json()


async def _baseline_runs() -> list[ScheduleRun]:
    async with get_session_factory()() as s:
        return list((await s.execute(select(ScheduleRun).where(ScheduleRun.label == LABEL))).scalars())


async def _assignments(run_id: int) -> int:
    async with get_session_factory()() as s:
        q = select(func.count()).select_from(Assignment).where(Assignment.run_id == run_id)
        return int((await s.execute(q)).scalar_one())


async def test_dry_run_reports_the_baseline_run_and_commit_modes_skip_run_auto(client):
    h = await login(client)
    job = await upload(client, h, (GUZ_GRID.name, GUZ_GRID.read_bytes()))
    assert job["files"][0]["route"] == "fast:weekly-grid"

    # Fark: a new term has no baseline run yet -> run_created, no id (rolled back), the counts it would write
    dry = await _ok(client, h, job["id"], dry_run=True)
    base = dry["result"]["baseline_run"]
    assert base["run_created"] is True and base["run_id"] is None and base["mode"] == "auto"
    assert base["created"] > 500 and base["entries"] > 0
    skip = (await _ok(client, h, job["id"], dry_run=True, baseline={"mode": "skip"}))["result"]["baseline_run"]
    assert skip == {"run_id": None, "run_created": False, "mode": "skip", "skipped": True, "entries": base["entries"]}
    assert await _baseline_runs() == []

    # validation: run needs run_id; run_id only with run
    assert (await _post(client, h, job["id"], baseline={"mode": "run"})).status_code == 422
    assert (await _post(client, h, job["id"], baseline={"mode": "skip", "run_id": 3})).status_code == 422

    # Kaydet with skip: the requests and rooms are written, the schedule map is not
    out = await _ok(client, h, job["id"], baseline={"mode": "skip"})
    assert out["baseline_run"]["skipped"] is True and await _baseline_runs() == []

    # a target run of the term (a finished solver run, not the active schedule)
    async with get_session_factory()() as s:
        term = (await s.execute(select(Term).where(Term.code == "2026-GUZ"))).scalar_one()
        other = Term(code="2027-BAHAR", name="Bahar 2027", kind="REGULAR", week_count=14)
        target = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", status="FEASIBLE", label="Plan A")
        active = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", status="FEASIBLE", is_active=True)
        exam = ScheduleRun(term_id=term.id, kind="EXAM", horizon="TERM", status="FEASIBLE")
        s.add_all([other, target, active, exam])
        await s.flush()
        foreign = ScheduleRun(term_id=other.id, kind="COURSE", horizon="TERM", status="FEASIBLE")
        s.add(foreign)
        await s.commit()
        ids = {"target": target.id, "active": active.id, "exam": exam.id, "foreign": foreign.id}
    for name in ("active", "exam", "foreign"):
        r = await _post(client, h, job["id"], baseline={"mode": "run", "run_id": ids[name]})
        assert r.status_code == 409, (name, r.text)
    assert await _assignments(ids["target"]) == 0

    dry_run_target = await _ok(client, h, job["id"], dry_run=True, baseline={"mode": "run", "run_id": ids["target"]})
    assert dry_run_target["result"]["baseline_run"]["run_id"] == ids["target"]
    into = (await _ok(client, h, job["id"], baseline={"mode": "run", "run_id": ids["target"]}))["baseline_run"]
    assert into["run_id"] == ids["target"] and into["mode"] == "run" and into["run_created"] is False
    assert into["created"] == base["created"] and await _assignments(ids["target"]) == base["created"]
    async with get_session_factory()() as s:
        t = await s.get(ScheduleRun, ids["target"])
        assert t is not None and t.label == "Plan A" and t.params.get("source") != SOURCE  # stays a solver run
        assert [x["file"] for x in t.params["sources"]] == [GUZ_GRID.name]
    assert await _baseline_runs() == []

    # auto (the default): the term's baseline run is made once; the next dry run names it and changes nothing
    first = (await _ok(client, h, job["id"]))["baseline_run"]
    assert first["run_created"] is True and first["mode"] == "auto"
    again = (await _ok(client, h, job["id"], dry_run=True))["result"]["baseline_run"]
    assert again["run_id"] == first["run_id"] and again["run_created"] is False
    assert again["created"] == 0 and again["unchanged"] == first["created"]
    assert [r.id for r in await _baseline_runs()] == [first["run_id"]]
