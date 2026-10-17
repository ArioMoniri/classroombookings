"""AS-01: server-side effective weights. The bridge merges ``DEFAULT_WEIGHTS`` < the admin's ``solver_weights``
setting < the active season profile < ``run.params.weights`` and records ``stats.weights_effective`` and
``stats.weights_source`` on every run, so runs created by the API (and moderation re-solves) honour the admin's
weights, not only the Studio page.

Real row: Bahar planning list row 120, PTL 204 §1 (36 students, Tuesday P13-P14), requested C 403, and the planning
office's definitive room C 501: the planner's own choice breaks the room wish, so its evaluated soft penalty is
``room_preference`` × 1."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import ScheduleRun
from app.services import settings_service as ss
from app.services.seasons import effective_weights
from app.services.solver_bridge import build_solver_input
from app.solver import model as sm
from app.solver.scoring import evaluate
from app.solver.weights import DEFAULT_WEIGHTS
from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.as_support import add_meeting, add_rooms, add_term, row_of


async def _seed(parsed_bahar_list) -> tuple[int, int, dict[str, int]]:
    row = row_of(parsed_bahar_list, 120)
    assert row.course_code == "PTL204" and row.venue.room_codes == ["C403"] and row.definitive.room_codes == ["C501"]
    async with get_session_factory()() as s:
        term = await add_term(s, "2026-BAHAR", week_kinds=["LECTURE"] * 14)
        rooms = await add_rooms(s, "C403", "C501")
        mr = await add_meeting(s, term, row, rooms)
        await s.commit()
        return term.id, mr, rooms


def _room_pref_penalty(inp: sm.SolverInput, event_id: int, room_id: int) -> int:
    e = next(x for x in inp.events if x.id == event_id)
    a = sm.Assignment(
        event_id=e.id,
        day=e.fixed_day or 1,
        start=e.fixed_start or 1,
        end=(e.fixed_start or 1) + e.duration - 1,
        room_ids=(room_id,),
        weeks=e.weeks,
    )
    return evaluate(inp, [a]).penalties.get("room_preference", 0)


async def test_as_01_settings_weights_reach_an_api_run_without_weights(client, stub_solver, parsed_bahar_list):
    h = await login(client)
    tid, mr, rooms = await _seed(parsed_bahar_list)
    r = await client.put("/api/v1/settings", json={"solver_weights": {"room_preference": 3}}, headers=h)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/runs", json={"term_id": tid, "kind": "COURSE", "horizon": "TERM"}, headers=h)
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    eff, src = run["stats"]["weights_effective"], run["stats"]["weights_source"]
    assert eff["room_preference"] == 3 and src["room_preference"] == "settings"
    assert eff["building_preference"] == DEFAULT_WEIGHTS["building_preference"]
    assert src["building_preference"] == "default"
    assert set(DEFAULT_WEIGHTS) <= set(eff)
    # the evaluated soft score follows: the planner's C 501 costs 3 instead of the default 10 per unit
    async with get_session_factory()() as s:
        row = await s.get(ScheduleRun, run_id)
        assert row is not None
        inp, _m = await build_solver_input(s, row)
    assert dict(inp.weights) == {"room_preference": 3}
    with_setting = _room_pref_penalty(inp, mr, rooms["C501"])
    default_inp = sm.SolverInput(rooms=inp.rooms, events=inp.events, constraints=inp.constraints, weeks=inp.weeks)
    default_pen = _room_pref_penalty(default_inp, mr, rooms["C501"])
    assert default_pen > 0 and with_setting * DEFAULT_WEIGHTS["room_preference"] == default_pen * 3
    assert _room_pref_penalty(inp, mr, rooms["C403"]) == 0


async def test_as_01_run_params_win_over_settings(client, stub_solver, parsed_bahar_list):
    h = await login(client)
    tid, _mr, _rooms = await _seed(parsed_bahar_list)
    await client.put("/api/v1/settings", json={"solver_weights": {"room_preference": 3, "stability": 4}}, headers=h)
    r = await client.post(
        "/api/v1/runs",
        json={"term_id": tid, "kind": "COURSE", "horizon": "TERM", "params": {"weights": {"room_preference": 7}}},
        headers=h,
    )
    run_id = r.json()["run_id"]
    await get_queue().wait_idle()
    stats = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()["stats"]
    assert stats["weights_effective"]["room_preference"] == 7 and stats["weights_source"]["room_preference"] == "run"
    assert stats["weights_effective"]["stability"] == 4 and stats["weights_source"]["stability"] == "settings"
    assert stats["profile"] is None or stats["profile"]["builtin"] is True


async def test_as_01_layers_merge_in_order_and_bad_setting_values_are_skipped(engine, parsed_bahar_list):
    tid, _mr, _rooms = await _seed(parsed_bahar_list)
    async with get_session_factory()() as s:
        await ss.set_value(s, "solver_weights", '{"room_preference": 2, "capacity": "x", "stability": -1}')
        run = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={"weights": {"stability": 9}})
        s.add(run)
        await s.flush()
        ew = await effective_weights(s, run)
    assert ew.weights["room_preference"] == 2 and ew.source["room_preference"] == "settings"
    assert ew.weights["capacity"] == DEFAULT_WEIGHTS["capacity"] and ew.source["capacity"] == "default"
    assert ew.weights["stability"] == 9 and ew.source["stability"] == "run"
    assert ew.overrides == {"room_preference": 2, "stability": 9}
    assert {w["key"] for w in ew.warnings} == {"capacity", "stability"}
    assert ew.period_kind == "LECTURE" and ew.season == "BAHAR"


async def test_as_01_empty_settings_give_todays_input(engine, parsed_bahar_list):
    """No setting, no profile, no run weights: the solver input carries no weights (byte-identical to before)."""
    tid, _mr, _rooms = await _seed(parsed_bahar_list)
    async with get_session_factory()() as s:
        run = ScheduleRun(term_id=tid, kind="COURSE", horizon="TERM", params={})
        s.add(run)
        await s.flush()
        inp, _m = await build_solver_input(s, run)
        assert dict(inp.weights) == {}
        assert set(run.stats["weights_source"].values()) == {"default"}
