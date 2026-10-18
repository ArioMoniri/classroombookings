"""AS-01 / audit RF-02 (blocker): the admin's default solver weights *and* seed (Ayarlar › Çözücü, saved through
``PUT /settings``: ``solver_weights`` and ``extra.solver_default_seed``) reach every run path, because the bridge
reads them on the server: ``POST /runs`` (API), the Studio's generate, a moderation re-solve, and a run created
without any params by a server job. One regression test per path.

Real row: Bahar planning list row 120, PTL 204 §1 (requested C 403, definitive C 501)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import ScheduleRun
from app.services.solver_bridge import run_schedule
from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.as_support import add_meeting, add_rooms, add_term, row_of


async def _setup(client, parsed_bahar_list) -> tuple[dict[str, str], int, int]:
    h = await login(client)
    async with get_session_factory()() as s:
        term = await add_term(s, "2026-BAHAR", week_kinds=["LECTURE"] * 14)
        rooms = await add_rooms(s, "C403", "C501")
        mr = await add_meeting(s, term, row_of(parsed_bahar_list, 120), rooms)
        await s.commit()
        tid = term.id
    r = await client.put(
        "/api/v1/settings",
        json={"solver_weights": {"room_preference": 3}, "extra": {"solver_default_seed": 7}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    return h, tid, mr


def _check(stats: dict) -> None:
    assert stats["weights_effective"]["room_preference"] == 3, stats.get("weights_source")
    assert stats["weights_source"]["room_preference"] == "settings"
    assert stats["seed"] == {"value": 7, "source": "settings"}


async def _get(client, h, run_id: int) -> dict:
    await get_queue().wait_idle(timeout=120)
    return (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()


async def test_rf02_post_runs(client, stub_solver, parsed_bahar_list):
    h, tid, _mr = await _setup(client, parsed_bahar_list)
    r = await client.post("/api/v1/runs", json={"term_id": tid, "kind": "COURSE", "horizon": "TERM"}, headers=h)
    run = await _get(client, h, r.json()["run_id"])
    _check(run["stats"])
    # an explicit seed in the run wins
    r = await client.post(
        "/api/v1/runs", json={"term_id": tid, "kind": "COURSE", "horizon": "TERM", "params": {"seed": 3}}, headers=h
    )
    run = await _get(client, h, r.json()["run_id"])
    assert run["stats"]["seed"] == {"value": 3, "source": "run"}


async def test_rf02_studio_generate(client, stub_solver, parsed_bahar_list):
    h, tid, _mr = await _setup(client, parsed_bahar_list)
    url = f"/api/v1/terms/{tid}/studio"
    r = await client.get(url, headers=h)
    assert r.status_code == 200, r.text
    r = await client.post(f"{url}/generate", json={"label": "studio"}, headers=h)
    assert r.status_code == 202, r.text
    run = await _get(client, h, r.json()["run_id"])
    assert run["params"].get("studio") is not None
    _check(run["stats"])


async def test_rf02_moderation_resolve(client, stub_solver, parsed_bahar_list):
    h, tid, mr = await _setup(client, parsed_bahar_list)
    r = await client.post("/api/v1/runs", json={"term_id": tid, "kind": "COURSE", "horizon": "TERM"}, headers=h)
    base = await _get(client, h, r.json()["run_id"])
    assert base["status"] in {"FEASIBLE", "OPTIMAL"}, base.get("diagnosis")
    r = await client.post(
        f"/api/v1/terms/{tid}/moderation/resolve",
        json={
            "base_run_id": base["id"],
            "changed_request_ids": [mr],
            "mode": "repair",
            "wait": True,
            "time_limit_s": 10,
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    child = (await client.get(f"/api/v1/runs/{r.json()['run_id']}", headers=h)).json()
    assert child["params"]["moderation"]["base_run_id"] == base["id"]
    _check(child["stats"])
    # the re-solve's own stability weight is a run-layer override, the admin's weights stay underneath
    assert child["stats"]["weights_source"]["stability"] == "run"


async def test_rf02_server_job_run_without_params(engine, stub_solver, parsed_bahar_list):
    """A run a server job creates with no params at all (CLI, council baseline, chat child) gets the same layers."""
    from app.services import settings_service as ss

    async with get_session_factory()() as s:
        term = await add_term(s, "2026-BAHAR", week_kinds=["LECTURE"] * 14)
        rooms = await add_rooms(s, "C403", "C501")
        await add_meeting(s, term, row_of(parsed_bahar_list, 120), rooms)
        await ss.set_value(s, "solver_weights", '{"room_preference": 3}')
        await ss.set_value(s, "solver_default_seed", "7")
        run = ScheduleRun(term_id=term.id, kind="COURSE", horizon="TERM", params={})
        s.add(run)
        await s.commit()
        rid = run.id
    factory = get_session_factory()
    await run_schedule(factory, rid)
    async with factory() as s:
        row = await s.get(ScheduleRun, rid)
        assert row is not None
        _check(row.stats)
