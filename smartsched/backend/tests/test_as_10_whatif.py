"""AS-10: capacity shortfall and what-if.

* **B5** on the Bahar requests and the room master: +10 % enrolment gives more classes without a fitting room than
  0 % (deterministic), with the per-cell shortfall;
* the API: a 0 % what-if equals today's room fit; ``solve: true`` queues a draft run with ``params.scenario`` that
  is never active, and the bridge scales the sizes.

Real rows: Bahar list rows 2 (MAT 112, 180 students, Monday P7-P9) and 296 (NUT 254, 60, Thursday P9-P10)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import ScheduleRun
from app.services import backtest as bt
from app.services.solver_bridge import build_solver_input
from app.workers.queue import get_queue

from tests.api_fixtures import login
from tests.as_support import add_meeting, add_rooms, add_term, row_of


def test_as_10_b5_bahar_plus_ten_percent(parsed_bahar_list):
    r = bt.b5_what_if(parsed_bahar_list)
    assert r.passed, r.metrics
    m = r.metrics
    assert m["no_fit_+10pct"] > m["no_fit_0pct"] and m["deterministic"] is True
    assert m["shortfall_total_+10pct"] >= m["shortfall_total_0pct"]
    assert all(c["shortfall"] > 0 and c["competing"] for c in m["top_shortfall_cells"])


async def _seed(parsed_bahar_list) -> tuple[int, dict[str, int], dict[str, int]]:
    async with get_session_factory()() as s:
        term = await add_term(s, "2026-BAHAR", week_kinds=["LECTURE"] * 14)
        rooms = await add_rooms(s, "A101", "A204", "C501")
        ids = {
            "mat": await add_meeting(s, term, row_of(parsed_bahar_list, 2), rooms),
            "nut": await add_meeting(s, term, row_of(parsed_bahar_list, 296), rooms),
        }
        await s.commit()
        return term.id, rooms, ids


async def test_as_10_what_if_api_and_draft_run(client, stub_solver, parsed_bahar_list):
    h = await login(client)
    tid, rooms, ids = await _seed(parsed_bahar_list)
    r = await client.post("/api/v1/analytics/forecast/what-if", json={"term_id": tid}, headers=h)
    assert r.status_code == 200, r.text
    zero = r.json()
    assert zero["today"] == zero["what_if"] and zero["delta"] == {"no_fit": 0, "shortfall_total": 0}
    # today MAT 112 (180) is larger than every room (A 204 seats 156: the planner splits it)
    assert zero["today"]["no_fit"] == 1 and zero["today"]["no_fit_classes"][0]["label"].startswith("MAT112")
    # +10 % with C 501 and A 204 closed: NUT 254 (66) no longer fits A 101 (58)
    r = await client.post(
        "/api/v1/analytics/forecast/what-if",
        json={"term_id": tid, "enrolment_pct": 10, "rooms_closed": [rooms["C501"], rooms["A204"]], "solve": True},
        headers=h,
    )
    out = r.json()
    assert out["what_if"]["no_fit"] > out["today"]["no_fit"]
    assert {c["label"][:6] for c in out["what_if"]["no_fit_classes"]} == {"MAT112", "NUT254"}
    assert out["scenario"]["label"]["tr"].startswith("Senaryo: +10 % kontenjan")
    run_id = out["run_id"]
    assert run_id
    await get_queue().wait_idle(timeout=120)
    run = (await client.get(f"/api/v1/runs/{run_id}", headers=h)).json()
    assert run["is_active"] is False and run["params"]["scenario"]["enrolment_pct"] == 10
    assert run["label"].startswith("Senaryo:")
    async with get_session_factory()() as s:
        row = await s.get(ScheduleRun, run_id)
        assert row is not None
        inp, _m = await build_solver_input(s, row)
    sizes = {e.id: e.size for e in inp.events}
    assert sizes[ids["nut"]] == 66 and sizes[ids["mat"]] == 198  # 60 and 180 x 1.1
    assert not {rooms["C501"], rooms["A204"]} & {r_.id for r_ in inp.rooms}
    # a scope needs its value
    r = await client.post("/api/v1/analytics/forecast/what-if", json={"term_id": tid, "scope": "faculty"}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["message_tr"]


async def test_as_10_shortfall_endpoint(client, parsed_bahar_list):
    h = await login(client)
    tid, _rooms, _ids = await _seed(parsed_bahar_list)
    out = (await client.get("/api/v1/analytics/forecast/shortfall", params={"term_id": tid}, headers=h)).json()
    assert out["method"] == "requests" and out["no_fit"] == 1
    assert out["definitions"]["shortfall"]["tr"]
