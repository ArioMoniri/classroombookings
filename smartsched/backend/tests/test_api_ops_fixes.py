"""Fixes found by the deploy run: non-blocking solves, restart recovery, private uploads, term input
validation and client-safe import errors."""

from __future__ import annotations

import asyncio
import io
import os
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import openpyxl
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.models import ImportJob, ScheduleRun
from app.services import solver_bridge
from app.solver import model as sm
from app.workers.queue import get_queue, public_error, recover_interrupted, worker_id
from httpx import ASGITransport, AsyncClient

from tests.api_fixtures import login


async def test_solve_runs_off_the_event_loop_and_reports_progress(client, monkeypatch):
    seen: dict[str, object] = {}

    def slow_solver(inp, progress, choice="auto", **_kw):
        seen["thread"] = threading.get_ident()
        progress("solving", 50)  # called from the worker thread
        time.sleep(1.5)  # stands in for CP-SAT holding the CPU for the time limit
        return sm.SolverResult("OPTIMAL", [], 100, 100, {}, [], {})

    monkeypatch.setattr(solver_bridge, "_call_solver", slow_solver)
    h = await login(client)
    term = (await client.post("/api/v1/terms", json={"code": "2026-BAHAR"}, headers=h)).json()
    run_id = (await client.post("/api/v1/runs", json={"term_id": term["id"]}, headers=h)).json()["run_id"]
    await asyncio.sleep(0.4)
    t0 = time.perf_counter()
    r = await client.get("/api/v1/health")
    assert r.status_code == 200 and time.perf_counter() - t0 < 0.5  # not stuck behind the solve
    st = get_queue().state(f"run:{run_id}")
    assert st is not None and st.status == "RUNNING" and st.phase == "solving" and st.progress >= 50
    running = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert running["status"] == "RUNNING" and running["stats"]["worker"]["pid"] == os.getpid()
    await get_queue().wait_idle()
    assert seen["thread"] != threading.get_ident()
    assert (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()["status"] == "OPTIMAL"


async def test_restart_marks_orphaned_runs_and_imports_failed(client):
    h = await login(client)
    term = (await client.post("/api/v1/terms", json={"code": "2026-GÜZ"}, headers=h)).json()
    host = socket.gethostname()
    dead = {"host": host, "pid": 2**22 + 12345}  # no such process
    async with get_session_factory()() as s:
        rows = [
            ScheduleRun(term_id=term["id"], status="RUNNING", stats={"worker": dead, "progress": 40}),
            ScheduleRun(term_id=term["id"], status="QUEUED", stats={}),  # pre-fix row without owner
            ScheduleRun(  # another live worker: other boot id, fresh heartbeat (review M6)
                term_id=term["id"],
                status="RUNNING",
                heartbeat_at=datetime.now(UTC).replace(tzinfo=None),
                stats={"worker": {"host": "other-node", "pid": 1, "boot": "live"}},
            ),
            ScheduleRun(term_id=term["id"], status="FEASIBLE", stats={}),
        ]
        job = ImportJob(kind="planning-list", status="RUNNING", summary={"worker": dead})
        s.add_all([*rows, job])
        await s.commit()
        ids = [r.id for r in rows]
        job_id = job.id
    from app.main import app, lifespan

    async with lifespan(app):  # the startup hook runs recover_interrupted; checks inside (exit disposes the engine)
        got = {i: (await client.get(f"/api/v1/runs/{i}", headers=h)).json() for i in ids}
        assert got[ids[0]]["status"] == "FAILED" and got[ids[0]]["error"] == "interrupted by restart"
        assert got[ids[0]]["stats"]["error"] == "interrupted by restart"
        assert got[ids[1]]["status"] == "FAILED"
        assert got[ids[2]]["status"] == "RUNNING"  # another node owns it
        assert got[ids[3]]["status"] == "FEASIBLE"
        j = (await client.get(f"/api/v1/imports/{job_id}", headers=h)).json()
        assert j["status"] == "FAILED" and j["error"] == "interrupted by restart"
        async with get_session_factory()() as s:
            assert await recover_interrupted(s) == {"runs": 0, "imports": 0}  # idempotent
    assert worker_id()["pid"] == os.getpid()


async def test_uploaded_workbooks_are_not_public(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "up"))
    from app.main import create_app

    app = create_app()  # mounts are fixed at creation time
    h = await login(client)
    (tmp_path / "up" / "imports").mkdir(parents=True)
    (tmp_path / "up" / "imports" / "7_Bahar_Derslik_Planlama_Listesi_v5.xlsx").write_bytes(b"PK secret")
    (tmp_path / "up" / "rooms" / "3.jpg").write_bytes(b"\xff\xd8 photo")
    async with get_session_factory()() as s:
        s.add(ImportJob(id=7, kind="planning-list", status="DONE", filename="Bahar Derslik Planlama Listesi v5.xlsx"))
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/uploads/imports/7_Bahar_Derslik_Planlama_Listesi_v5.xlsx")).status_code == 404
        assert (await c.get("/uploads/rooms/3.jpg")).status_code == 200
        assert (await c.get("/api/v1/imports/7/file")).status_code == 401
        r = await c.get("/api/v1/imports/7/file", headers=h)
        assert r.status_code == 200 and r.content == b"PK secret"
        assert "Bahar_Derslik_Planlama_Listesi_v5.xlsx" in r.headers["content-disposition"]
        assert (await c.get("/api/v1/imports/8/file", headers=h)).status_code == 404


async def test_create_term_defaults_name_and_rejects_bad_input(client):
    h = await login(client)
    r = await client.post("/api/v1/terms", json={"code": "2026 BAHAR "}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "2026 BAHAR" and r.json()["name"] == "2026 BAHAR"  # NBSP normalised
    r = await client.post("/api/v1/terms", json={"code": "2026-GÜZ", "name": "Güz Dönemi"}, headers=h)
    assert r.status_code == 201 and r.json()["name"] == "Güz Dönemi"
    assert (await client.post("/api/v1/terms", json={"code": "2026-GÜZ"}, headers=h)).status_code == 409
    for bad in (
        {"code": ""},
        {"code": "X", "kind": "WINTER"},
        {"code": "X", "week_count": 0},
        {"code": "X", "start_date": "2026-06-01", "end_date": "2026-02-01"},
        {"name": "no code"},
    ):
        assert (await client.post("/api/v1/terms", json=bad, headers=h)).status_code == 422, bad
    tid = r.json()["id"]
    assert (await client.put(f"/api/v1/terms/{tid}", json={"kind": "WINTER"}, headers=h)).status_code == 422


async def test_import_failure_returns_short_message_without_traceback(client):
    h = await login(client)
    # a real (safe) workbook without the planning-list columns: passes app.core.safe_files, fails parsing
    wb = openpyxl.Workbook()
    wb.active.append(["Ders", "Not"])  # type: ignore[union-attr]
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("Bahar Derslik Planlama Listesi v5.xlsx", buf.getvalue(), "application/octet-stream")}
    r = await client.post("/api/v1/imports/planning-list", data={"term_code": "2026-BAHAR"}, files=files, headers=h)
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    await get_queue().wait_idle()
    job = (await client.get(f"/api/v1/imports/{job_id}", headers=h)).json()
    assert job["status"] == "FAILED"
    err = job["error"]
    assert f"import job {job_id} failed" in err and "Traceback" not in err and len(err) < 500
    assert str(Path(get_settings().upload_dir)) not in err and "/imports/" not in err
    assert public_error(FileNotFoundError("/srv/x/uploads/imports/9_a.xlsx")) == "FileNotFoundError: 9_a.xlsx"
