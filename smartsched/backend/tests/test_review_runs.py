"""Review 2026-10-08 regressions on the real Bahar 2026 import: B2 (chat-apply children keep the studio
draft), B3 (no PLANNER bypass of ADMIN-only built-ins through ``POST /runs`` params), M13 bounds."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import Assignment, ScheduleRun
from app.services import run_params as rp
from app.services import solver_bridge
from app.workers.queue import get_queue
from sqlalchemy import select

from tests import studio_support

bahar = studio_support.bahar


async def _studio_run_keeping(bahar, keep_n: int = 25) -> tuple[int, set[int], list[int]]:
    """A stub studio run (week 3) of ``keep_n`` Eczacılık classes; every other class is left out."""
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    await c.get(url, headers=h)
    page = (await c.get(f"{url}/classes", params={"limit": 2000}, headers=h)).json()["items"]
    keep = {r["id"] for r in page if r["program_name"] == "Eczacılık"}
    keep = set(sorted(keep)[:keep_n])
    excluded = [r["id"] for r in page if r["id"] not in keep]
    r = await c.put(
        url,
        json={"version": 1, "horizon": "WEEK", "horizon_params": {"weeks": [3]}, "excluded_event_ids": excluded},
        headers=h,
    )
    assert r.status_code == 200, r.text
    r = await c.post(f"{url}/generate", json={"params": {"solver": "cpsat", "time_limit_s": 10}}, headers=h)
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    await get_queue().wait_idle(timeout=300)
    run = (await c.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["status"] != "FAILED", run.get("error")
    assert "studio_sig" in run["params"]  # sealed by the server
    return run_id, keep, excluded


async def _placed(run_id: int) -> set[int]:
    async with get_session_factory()() as s:
        rows = (await s.execute(select(Assignment.meeting_request_id).where(Assignment.run_id == run_id))).scalars()
        return {int(x) for x in rows if x is not None}


async def test_b2_chat_apply_child_keeps_the_drafts_left_out_classes(bahar, stub_solver):
    run_id, keep, excluded = await _studio_run_keeping(bahar)
    parent = await _placed(run_id)
    assert parent and parent <= keep
    c, h = bahar.client, bahar.planner
    a = (await c.get(f"/api/v1/runs/{run_id}/assignments", headers=h)).json()[0]
    diff = {"id": "d-b2", "run_id": run_id, "operations": [{"op": "lock", "assignment_id": a["id"]}], "re_solve": True}
    r = await c.post(f"/api/v1/runs/{run_id}/chat/apply", json={"diff": diff}, headers=h)
    assert r.status_code == 200, r.text
    child_id = r.json()["child_run_id"]
    await get_queue().wait_idle(timeout=300)
    async with get_session_factory()() as s:
        child = await s.get(ScheduleRun, child_id)
        assert child is not None and child.status != "FAILED", child.error
    placed = await _placed(child_id)
    assert placed, "the child run placed nothing"
    assert placed <= keep, f"left-out classes came back: {sorted(placed - keep)[:10]}"
    assert not placed & set(excluded)


async def test_b3_planner_cannot_switch_builtins_off_through_post_runs(bahar):
    c, h = bahar.client, bahar.planner
    forged = {
        "draft_id": 1,
        "version": 1,
        "kind": "COURSE",
        "excluded_event_ids": [],
        "pins": [],
        "disabled_rule_ids": [],
        "rule_overrides": {},
        "disabled_builtin_kinds": ["capacity", "no_cohort_overlap", "no_instructor_overlap"],
    }
    base = {"term_id": bahar.term_id, "kind": "COURSE", "horizon": "WEEK", "horizon_params": {"weeks": [3]}}
    for params in ({"studio": forged}, {"studio": forged, "studio_sig": "0" * 64}, {"draft_id": 1}):
        r = await c.post("/api/v1/runs", json={**base, "params": {"solver": "cpsat", **params}}, headers=h)
        assert r.status_code == 422, (params.keys(), r.text)
    # even a snapshot written straight into the DB (no server seal) is ignored by the bridge
    async with get_session_factory()() as s:
        run = ScheduleRun(
            term_id=bahar.term_id, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [3]},
            params={"solver": "cpsat", "studio": forged, "studio_sig": "f" * 64}, status="QUEUED", stats={},
        )  # fmt: skip
        s.add(run)
        await s.commit()
        assert rp.trusted_studio_snapshot(run) is None
        from app.services.studio import build_solver_input_for_run

        inp, _ = await build_solver_input_for_run(s, run)
        assert not any(c_.kind == "capacity" and not c_.hard for c_ in inp.constraints)
        assert all("__studio_disabled__" not in (c_.params.get("keys") or []) for c_ in inp.constraints)
        assert solver_bridge._studio_run(run) is False


async def test_b3_sealed_studio_snapshot_survives_server_side_child_copies(bahar, stub_solver):
    run_id, keep, _ = await _studio_run_keeping(bahar, keep_n=10)
    async with get_session_factory()() as s:
        parent = await s.get(ScheduleRun, run_id)
        assert parent is not None
        child = ScheduleRun(
            term_id=parent.term_id, kind=parent.kind, horizon=parent.horizon,
            horizon_params=dict(parent.horizon_params or {}), params=dict(parent.params or {}),
        )  # fmt: skip
        assert rp.trusted_studio_snapshot(child) == parent.params["studio"]
        tampered = ScheduleRun(
            term_id=parent.term_id, kind=parent.kind,
            params={**parent.params, "studio": {**parent.params["studio"], "disabled_builtin_kinds": ["capacity"]}},
        )  # fmt: skip
        assert rp.trusted_studio_snapshot(tampered) is None


async def test_m13_post_runs_params_are_whitelisted_and_bounded(bahar, stub_solver):
    c, h = bahar.client, bahar.planner
    base = {"term_id": bahar.term_id, "kind": "COURSE", "horizon": "WEEK", "horizon_params": {"weeks": [3]}}
    bad = [
        {"time_limit_s": 10**9},
        {"time_limit_s": 0},
        {"workers": 10_000},
        {"workers": "8"},
        {"seed": -1},
        {"solver": "os.system"},
        {"weights": {"capacity": 10**9}},
        {"rm_rf": True},
        {"best_effort": "yes"},
    ]
    for params in bad:
        r = await c.post("/api/v1/runs", json={**base, "params": params}, headers=h)
        assert r.status_code == 422, (params, r.text)
    r = await c.post("/api/v1/runs", json={**base, "parent_run_id": 999_999, "params": {}}, headers=h)
    assert r.status_code == 422
    r = await c.post(
        "/api/v1/runs",
        json={**base, "params": {"solver": "cpsat", "time_limit_s": 5, "workers": 2, "weights": {"stability": 3}}},
        headers=h,
    )
    assert r.status_code == 202, r.text
    await get_queue().wait_idle(timeout=300)
    run = (await c.get(f"/api/v1/runs/{r.json()['run_id']}", headers=h)).json()
    assert run["params"]["time_limit_s"] == 5 and run["params"]["workers"] == 2
