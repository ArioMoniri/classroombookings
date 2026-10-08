"""Review M6 (heartbeat + boot-id recovery, wall-clock limit), M7 (no DB transaction held during a solve,
SQLite WAL), M13 (real cancel with CP-SAT StopSearch, per-user run limit)."""

from __future__ import annotations

import asyncio
import random
import socket
import time
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.db import get_engine, get_session_factory
from app.models import Assignment, ImportJob, ScheduleRun
from app.services import solver_bridge
from app.solver import model as sm
from app.workers.queue import BOOT_ID, get_queue, recover_interrupted
from sqlalchemy import func, select, text

from tests.api_fixtures import login


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hard_cpsat_solver(seen: dict):
    """A fake bridge solver that runs a real, slow CP-SAT search (weighted set cover, 120 s limit)."""

    def solve(inp, progress, choice="auto", **_kw):
        from ortools.sat.python import cp_model

        rnd = random.Random(7)
        m = cp_model.CpModel()
        sets = [rnd.sample(range(400), 9) for _ in range(700)]
        xs = [m.new_bool_var(f"s{i}") for i in range(len(sets))]
        for e in range(400):
            m.add_bool_or([xs[i] for i, st in enumerate(sets) if e in st] or [xs[0]])
        m.minimize(sum(rnd.randint(1, 100) * x for x in xs))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 120
        solver.parameters.num_workers = 2
        progress("solving", 10)
        seen["started"] = time.monotonic()
        status = solver.solve(m)
        seen["returned"] = time.monotonic()
        seen["status"] = solver.status_name(status)
        return sm.SolverResult("FEASIBLE", [], 100, 100, {}, [], {})

    return solve


def sleeping_solver(seconds: float, seen: dict | None = None):
    def solve(inp, progress, choice="auto", **_kw):
        progress("solving", 10)
        if seen is not None:
            seen["started"] = time.monotonic()
        time.sleep(seconds)
        return sm.SolverResult("OPTIMAL", [], 100, 100, {}, [], {})

    return solve


async def _term(client, h) -> int:
    return int((await client.post("/api/v1/terms", json={"code": "2026-BAHAR"}, headers=h)).json()["id"])


async def _wait(cond, timeout: float = 20.0) -> None:
    t0 = time.monotonic()
    while not await cond():
        assert time.monotonic() - t0 < timeout, "condition not reached"
        await asyncio.sleep(0.1)


async def _status(client, h, run_id: int) -> dict:
    return (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()


async def test_m13_cancel_stops_a_running_cpsat_search(client, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(solver_bridge, "_call_solver", hard_cpsat_solver(seen))
    h = await login(client)
    tid = await _term(client, h)
    run_id = (await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)).json()["run_id"]

    async def solving() -> bool:
        return "started" in seen

    await _wait(solving)
    await asyncio.sleep(1.0)  # inside CpSolver.solve
    r = await client.post(f"/api/v1/runs/{run_id}/cancel", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED", r.text
    t_cancel = time.monotonic()
    await get_queue().wait_idle(timeout=30)
    assert seen["returned"] - t_cancel < 5, "the CP-SAT search was not stopped"  # 120 s limit otherwise
    run = await _status(client, h, run_id)
    assert run["status"] == "CANCELLED" and "cancelled by" in run["error"]
    async with get_session_factory()() as s:
        n = (await s.execute(select(func.count(Assignment.id)).where(Assignment.run_id == run_id))).scalar_one()
    assert n == 0  # the partial result is discarded
    assert (await client.post(f"/api/v1/runs/{run_id}/cancel", headers=h)).status_code == 409


async def test_m13_cancel_queued_run_and_per_user_limit(client, monkeypatch):
    monkeypatch.setattr(solver_bridge, "_call_solver", sleeping_solver(2.0))
    monkeypatch.setattr(get_settings(), "max_active_runs_per_user", 2)
    h = await login(client)
    tid = await _term(client, h)
    a = (await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)).json()["run_id"]
    b = (await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)).json()["run_id"]
    r = await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)
    assert r.status_code == 429, r.text
    assert (await client.post(f"/api/v1/runs/{b}/cancel", headers=h)).json()["status"] == "CANCELLED"
    r = await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)  # a slot is free again
    assert r.status_code == 202
    await get_queue().wait_idle(timeout=60)
    assert (await _status(client, h, a))["status"] == "OPTIMAL"
    assert (await _status(client, h, b))["status"] == "CANCELLED"


async def test_m6_wall_clock_limit_fails_a_stuck_run(client, monkeypatch):
    monkeypatch.setattr(solver_bridge, "_call_solver", sleeping_solver(4.0))
    monkeypatch.setattr(get_settings(), "run_wall_clock_factor", 0.0)
    monkeypatch.setattr(get_settings(), "run_wall_clock_margin_s", 1.0)
    monkeypatch.setattr(get_settings(), "run_cancel_grace_s", 0.5)
    h = await login(client)
    tid = await _term(client, h)
    run_id = (await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)).json()["run_id"]
    t0 = time.monotonic()
    await get_queue().wait_idle(timeout=30)
    run = await _status(client, h, run_id)
    assert run["status"] == "FAILED" and "wall-clock" in run["error"], run
    assert time.monotonic() - t0 < 4.0  # did not wait for the stuck solver


async def test_m6_heartbeats_and_restart_recovery_by_boot_id(client, monkeypatch):
    monkeypatch.setattr(solver_bridge, "_call_solver", sleeping_solver(1.5))
    monkeypatch.setattr(get_settings(), "run_heartbeat_s", 0.3)
    h = await login(client)
    tid = await _term(client, h)
    run_id = (await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)).json()["run_id"]

    async def beating() -> bool:
        async with get_session_factory()() as s:
            row = await s.get(ScheduleRun, run_id)
            return row is not None and row.heartbeat_at is not None

    await _wait(beating)
    await get_queue().wait_idle(timeout=30)

    host, stale, fresh = socket.gethostname(), _now() - timedelta(minutes=10), _now()
    async with get_session_factory()() as s:
        rows = {
            # Docker restart: same hostname, PID 1 is alive again (the old pid/host check kept it RUNNING)
            "pid_reused": ScheduleRun(term_id=tid, status="RUNNING", heartbeat_at=stale,
                                      stats={"worker": {"host": host, "pid": 1, "boot": "previous-boot"}}),
            # new container hostname: the old check assumed "another node" and never recovered it
            "new_hostname": ScheduleRun(term_id=tid, status="RUNNING", heartbeat_at=stale,
                                        stats={"worker": {"host": "3f2a9c-old-container", "pid": 7, "boot": "b1"}}),
            "never_beat": ScheduleRun(term_id=tid, status="QUEUED", stats={"worker": {"host": "x", "pid": 9, "boot": "b2"}}),
            "this_boot": ScheduleRun(term_id=tid, status="RUNNING", heartbeat_at=fresh,
                                     stats={"worker": {"host": host, "pid": 1, "boot": BOOT_ID}}),
            "other_live_worker": ScheduleRun(term_id=tid, status="RUNNING", heartbeat_at=fresh,
                                             stats={"worker": {"host": "node-2", "pid": 1, "boot": "live-boot"}}),
        }  # fmt: skip
        job_stale = ImportJob(kind="planning-list", status="RUNNING", heartbeat_at=stale, summary={"worker": {"boot": "x"}})
        job_live = ImportJob(kind="planning-list", status="RUNNING", heartbeat_at=fresh, summary={"worker": {"boot": "y"}})
        s.add_all([*rows.values(), job_stale, job_live])
        await s.commit()
        ids = {k: v.id for k, v in rows.items()}
        jobs = (job_stale.id, job_live.id)
    async with get_session_factory()() as s:
        assert await recover_interrupted(s) == {"runs": 4, "imports": 1}
    async with get_session_factory()() as s:
        got = {k: (await s.get(ScheduleRun, i)).status for k, i in ids.items()}
        assert got == {
            "pid_reused": "FAILED",
            "new_hostname": "FAILED",
            "never_beat": "FAILED",
            "this_boot": "FAILED",
            "other_live_worker": "RUNNING",
        }
        assert [(await s.get(ImportJob, j)).status for j in jobs] == ["FAILED", "RUNNING"]


async def test_m7_writes_succeed_quickly_during_a_solve(client, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(solver_bridge, "_call_solver", sleeping_solver(4.0, seen))
    h = await login(client)
    tid = await _term(client, h)
    async with get_engine().connect() as conn:
        assert (await conn.execute(text("PRAGMA journal_mode"))).scalar_one().lower() == "wal"
    run_id = (await client.post("/api/v1/runs", json={"term_id": tid}, headers=h)).json()["run_id"]

    async def solving() -> bool:
        return "started" in seen

    await _wait(solving)
    t0 = time.monotonic()
    r = await client.post("/api/v1/terms", json={"code": "2026-GUZ"}, headers=h)
    w = await client.post(
        "/api/v1/constraints",
        json={"term_id": tid, "kind": "building_preference", "params": {"building": "C"}, "hardness": "soft", "weight": 2},
        headers=h,
    )
    elapsed = time.monotonic() - t0
    assert r.status_code == 201 and w.status_code in (200, 201), (r.text, w.text)
    assert elapsed < 2.0, f"writes waited {elapsed:.1f} s behind the solve"
    assert (await _status(client, h, run_id))["status"] == "RUNNING"
    await get_queue().wait_idle(timeout=30)
    assert (await _status(client, h, run_id))["status"] == "OPTIMAL"
