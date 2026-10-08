"""Enriched assignments / grid cells / RunOut, locking manual moves and the dashboard, on the real Güz
fixtures (weekly grid = room master + HAZIRLIK blocks, planning list = requests)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import ScheduleRun
from app.services.solver_bridge import build_solver_input
from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.test_api_runs import _import_guz

PSI155_NAME = "Felsefede Temel Kavramlar ve Sorunlar"  # Güz list row 2: PSI 155, Psikoloji, 120 students, A 204


async def _stub_run(client, h, term_id: int, week: int = 3) -> int:
    r = await client.post(
        "/api/v1/runs",
        json={
            "term_id": term_id,
            "kind": "COURSE",
            "horizon": "WEEK",
            "horizon_params": {"week": week},
            "params": {"solver": "stub"},
        },
        headers=h,
    )
    assert r.status_code == 202, r.text
    await get_queue().wait_idle()
    return int(r.json()["run_id"])


async def test_enriched_assignments_grid_move_lock_and_dashboard(client):
    h = await login(client)
    term_id = await _import_guz()

    # ---- dashboard before solving: counts come from the imported rows; utilisation from the planner's
    # published board (the weekly-grid import stores it as a FEASIBLE run with IMPORT assignments)
    stats = (await client.get("/api/v1/requests/stats", params={"term_id": term_id}, headers=h)).json()
    d0 = (await client.get("/api/v1/dashboard", params={"term_id": term_id}, headers=h)).json()
    assert d0["term"]["code"] == "2026-GUZ"
    assert d0["meetings_total"] == sum(stats["meetings"].values()) > 900
    assert d0["requests_needs_review"] == stats["meetings"].get("NEEDS_REVIEW", 0) + stats["exams"].get(
        "NEEDS_REVIEW", 0
    )
    assert d0["requests_pending"] == d0["requests_total"] - d0["requests_locked"]
    assert d0["requests_locked"] == stats["meetings"]["LOCKED"]
    assert d0["sections_total"] > 500 and d0["rooms_bookable"] >= 50
    board = next(r for r in d0["last_runs"] if r["id"] == d0["utilisation_run_id"])
    assert board["params"]["source"] == "GRID_IMPORT" and board["kind"] == "COURSE"
    assert d0["active_run_id"] is None and 0 < d0["utilisation"] <= 1 and d0["blocks_week"] > 0

    run_id = await _stub_run(client, h, term_id)

    # ---- RunOut: term code, top-level progress and objective breakdown, structured diagnoses
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["term_code"] == "2026-GUZ" and run["progress"] == 100
    assert isinstance(run["objective_breakdown"], dict)
    for i, dg in enumerate(run["diagnosis"]):
        assert dg["id"] == str(i) and len(dg["event_labels"]) == len(dg["event_ids"])
        assert all({"index", "text", "action", "applicable"} <= set(s) for s in dg["suggestions"])
    listed = (await client.get("/api/v1/runs", params={"term_id": term_id}, headers=h)).json()
    assert listed[0]["term_code"] == "2026-GUZ"

    # ---- enriched assignment of the real PSI 155 row
    rows = (await client.get(f"/api/v1/runs/{run_id}/assignments", params={"week": 3, "day": 1}, headers=h)).json()
    psi = next(a for a in rows if a["course_code"] == "PSI 155")
    assert psi["course_name"] == PSI155_NAME and psi["program_name"] == "Psikoloji"
    assert psi["size"] == 120 and psi["enrolment"] == 120 and psi["class_year"] == 1
    assert psi["room_codes"] == ["A 204"] and psi["capacity"] >= 120
    assert any("Yuna" in name for name in psi["instructors"]) and psi["instructor"]
    assert 3 in psi["week_set"] and psi["is_conflict"] is False and psi["conflict_reasons"] == []

    # ---- grid cells carry the same enrichment
    grid = (await client.get(f"/api/v1/runs/{run_id}/grid", params={"week": 3}, headers=h)).json()
    a204 = next(rm for rm in grid["days"][0]["rooms"] if rm["code"] == "A204")
    cell = a204["cells"][3]
    assert cell["course_name"] == PSI155_NAME and cell["size"] == 120 and cell["program_name"] == "Psikoloji"
    assert cell["is_conflict"] is False and 3 in cell["weeks"] and cell["instructors"]
    visible = {c["id"] for d in grid["days"] for rm in d["rooms"] for c in rm["cells"] if c and c.get("is_conflict")}
    assert grid["week_start"] and grid["conflicts"] >= len(visible) > 0  # overlapping cells hide each other

    # ---- move into the occupied A 204 slot: rejected with a readable reason
    other = next(a for a in rows if a["id"] != psi["id"] and a["start_period"] <= 5 and a["end_period"] >= 4)
    r = await client.post(
        f"/api/v1/runs/{run_id}/assignments/{other['id']}/move",
        json={
            "room_ids": [a204["room_id"]],
            "day": 1,
            "start_period": 4,
            "end_period": 4 + other["end_period"] - other["start_period"],
        },
        headers=h,
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] is False
    assert any("A 204" in c["message"] and "PSI 155" in c["message"] for c in body["conflicts"]), body["conflicts"]
    assert body["assignment"]["is_locked"] is False  # unchanged

    # ---- move to a free slot: MANUAL + locked
    free_room = next(
        rm
        for rm in grid["days"][5]["rooms"]  # Saturday
        if all(c is None for c in rm["cells"][:3]) and rm["capacity"] >= other["size"]
    )
    dur = other["end_period"] - other["start_period"]
    r = await client.post(
        f"/api/v1/runs/{run_id}/assignments/{other['id']}/move",
        json={"room_ids": [free_room["room_id"]], "day": 6, "start_period": 1, "end_period": 1 + dur},
        headers=h,
    )
    moved = r.json()
    assert moved["ok"] is True, moved
    assert moved["assignment"]["origin"] == "MANUAL" and moved["assignment"]["is_locked"] is True
    assert moved["assignment"]["day"] == 6 and moved["assignment"]["room_ids"] == [free_room["room_id"]]
    assert (
        await client.post(f"/api/v1/runs/{run_id}/assignments/{other['id']}/move", json={"day": 9}, headers=h)
    ).status_code == 422

    # ---- a child run carries the planner's lock: Event.locked overrides the request's fixed day/time
    async with get_session_factory()() as s:
        parent = await s.get(ScheduleRun, run_id)
        assert parent is not None
        child = ScheduleRun(
            term_id=term_id, kind="COURSE", horizon="WEEK", horizon_params={"week": 3}, params={}, parent_run_id=run_id
        )
        inp, _members = await build_solver_input(s, child)
    ev = next(e for e in inp.events if e.id == other["meeting_request_id"])
    assert ev.locked is not None and (ev.locked.day, ev.locked.start) == (6, 1)
    assert ev.locked.room_ids == (free_room["room_id"],) and ev.duration == dur + 1

    # ---- forced overlap is flagged as a conflict on both sides
    r = await client.post(
        f"/api/v1/runs/{run_id}/assignments/{other['id']}/move",
        json={"room_ids": [a204["room_id"]], "day": 1, "start_period": 4, "end_period": 4 + dur, "force": True},
        headers=h,
    )
    assert r.json()["ok"] is True and r.json()["assignment"]["is_conflict"] is True
    assert any(x.startswith("room overlap: A 204") for x in r.json()["assignment"]["conflict_reasons"])
    rows = (await client.get(f"/api/v1/runs/{run_id}/assignments", params={"week": 3, "day": 1}, headers=h)).json()
    assert next(a for a in rows if a["id"] == psi["id"])["is_conflict"] is True

    # ---- dashboard with the run: real utilisation matrices + last runs
    await client.post(f"/api/v1/runs/{run_id}/activate", headers=h)
    d = (await client.get("/api/v1/dashboard", params={"term_id": term_id}, headers=h)).json()
    assert d["active_run_id"] == run_id and d["utilisation_run_id"] == run_id and d["utilisation_week"] == 3
    assert d["last_runs"][0]["id"] == run_id and d["last_runs"][0]["hard_score"] is not None
    assert d["last_runs"][0]["term_code"] == "2026-GUZ"
    buildings = {b["building"] for b in d["utilisation_by_building"]}
    assert {"A", "B", "C"} <= buildings
    assert len(d["utilisation_building_day"]) == 7 * len(buildings)
    assert len(d["utilisation_building_period"]) == 18 * len(buildings)
    assert len(d["peak_hours"]) == 7 * 18
    a_mon = next(c for c in d["utilisation_building_day"] if c["building"] == "A" and c["day"] == 1)
    a_p4 = next(c for c in d["utilisation_building_period"] if c["building"] == "A" and c["period"] == 4)
    assert 0 < a_mon["utilisation"] <= 1 and 0 < a_p4["utilisation"] <= 1
    assert 0 < d["utilisation"] <= 1 and d["conflicts"] >= 2
    assert (await client.get("/api/v1/dashboard", params={"term_id": 9999}, headers=h)).status_code == 404
    # default term = the newest one when none is active
    assert (await client.get("/api/v1/dashboard", headers=h)).json()["term"]["id"] == term_id
