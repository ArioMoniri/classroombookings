"""Generate from a studio draft: the run gets the draft snapshot, left-out classes are not solved, and
the run reaches a terminal status (greedy stub and CP-SAT)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import Assignment, ScheduleRun
from app.workers.queue import get_queue
from sqlalchemy import select

from tests import studio_support
from tests.studio_support import meeting_id, room

bahar = studio_support.bahar

TERMINAL = {"FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL", "INFEASIBLE", "TIMEOUT", "FAILED", "ERROR"}


async def test_generate_from_draft_with_stub_and_cpsat(bahar, stub_solver):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    await c.get(url, headers=h)
    phar = await meeting_id("PHAR 240", day=1, start=1)
    pin_target = await meeting_id("PHAR 290", day=3, start=9)
    a204 = (await room("A204")).id
    r = await c.put(
        url,
        json={
            "version": 1,
            "horizon": "WEEK",
            "horizon_params": {"weeks": [3]},
            "excluded_event_ids": [phar],
            "pins": [{"event_id": pin_target, "room_ids": [a204]}],
            "params": {"time_limit_s": 10, "seed": 1},
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    r = await c.post(f"{url}/generate", json={"label": "studio week 3", "params": {"solver": "cpsat"}}, headers=h)
    assert r.status_code == 202, r.text
    g = r.json()
    assert g["status"] == "QUEUED" and g["excluded"] == 1 and g["events"] > 400 and g["draft_version"] == 2
    assert "1 left out" in g["prompt_text"] and "weeks 3" in g["prompt_text"]
    await get_queue().wait_idle(timeout=300)
    run = (await c.get(f"/api/v1/runs/{g['run_id']}", headers=h)).json()
    assert run["status"] in TERMINAL and run["status"] != "FAILED", run.get("error")
    assert run["stats"]["solver"] == "app.solver.stub" and run["label"] == "studio week 3"
    assert run["params"]["studio"]["excluded_event_ids"] == [phar] and run["params"]["time_limit_s"] == 10
    async with get_session_factory()() as s:
        rows = list((await s.execute(select(Assignment).where(Assignment.run_id == g["run_id"]))).scalars())
        assert rows and phar not in {a.meeting_request_id for a in rows}
        pinned = [a for a in rows if a.meeting_request_id == pin_target]
        assert pinned and all(a.room_ids == [a204] for a in pinned)  # draft pin honoured
        db_run = await s.get(ScheduleRun, g["run_id"])
        assert db_run.stats["studio_draft_id"] == g["draft_id"]
    # CP-SAT on the same draft: the real Bahar data is statically infeasible -> terminal with diagnoses
    stub_solver.undo()
    r = await c.post(f"{url}/generate", json={"params": {"solver": "cpsat", "time_limit_s": 5}}, headers=h)
    run_id = r.json()["run_id"]
    await get_queue().wait_idle(timeout=300)
    run = (await c.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["status"] in TERMINAL and run["status"] not in {"FAILED", "ERROR"}, run.get("error")
    assert run["stats"]["solver"] == "app.solver.cpsat"
    # the real Bahar week 3 is over-subscribed: a best-effort partial timetable, never a silent full one
    assert run["status"] == "FEASIBLE_PARTIAL", run["status"]
    assert 0 < run["stats"]["placed"] < run["stats"]["events_total"] and run["hard_score"] == 100
    assert run["diagnosis"] and all(phar not in d["event_ids"] for d in run["diagnosis"])  # left out stays out
    # parent run must belong to the same term + kind
    r = await c.post(f"{url}/generate", json={"parent_run_id": 999999}, headers=h)
    assert r.status_code == 422


async def test_generate_small_feasible_draft_with_cpsat(bahar):
    """Only Eczacılık on one week (preset-style include filter written into the draft) solves with CP-SAT."""
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    await c.get(url, headers=h)
    page = (await c.get(f"{url}/classes", params={"limit": 2000}, headers=h)).json()["items"]
    keep = {r["id"] for r in page if r["program_name"] == "Eczacılık" and not r["locked"]}
    pre_ids = [r["id"] for r in page if r["id"] not in keep]
    r = await c.put(
        url,
        json={"version": 1, "horizon": "WEEK", "horizon_params": {"weeks": [3]}, "excluded_event_ids": pre_ids},
        headers=h,
    )
    assert r.status_code == 200
    pre = (await c.post(f"{url}/precheck", headers=h)).json()
    assert pre["readiness"] == "ready", [it["message"]["en"] for it in pre["items"] if it["severity"] == "error"][:3]
    r = await c.post(
        f"{url}/generate", json={"params": {"solver": "cpsat", "time_limit_s": 20, "workers": 2}}, headers=h
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    await get_queue().wait_idle(timeout=300)
    run = (await c.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["status"] in {"FEASIBLE", "OPTIMAL"}, (run["status"], run["diagnosis"][:2])
    assert run["hard_score"] == 100
