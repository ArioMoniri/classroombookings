"""Flow loop round 1, lane F (docs/ROADMAP.md "Flow loop tickets — round 1", ``rounds/round-1-tickets.json``):
the dashboard and the learning memory, on the real 2026 Bahar / Güz fixtures.

* T-R1-39: with the imported Güz board published (weeks 1-2 of the weekly grid), the dashboard's room use is the
  heatmap's "Genel doluluk" of the same week, never 0 % because today's week lies outside the board.
"""

from __future__ import annotations

from datetime import date

from app.core.db import get_session_factory
from app.models import ScheduleRun, Term
from app.services.dashboard import build_dashboard
from sqlalchemy import select

from tests.api_fixtures import login
from tests.test_api_runs import _import_guz, publish_directly

TODAY = date(2026, 10, 16)  # Güz 2026-27 week 4: the imported board covers weeks 1 and 2 only


async def _publish_board(term_id: int) -> int:
    async with get_session_factory()() as s:
        board = (
            await s.execute(select(ScheduleRun).where(ScheduleRun.term_id == term_id, ScheduleRun.kind == "COURSE"))
        ).scalar_one()
    await publish_directly(board.id)
    return board.id


# --------------------------------------------------------------------------------------------------
# T-R1-39: the dashboard reads the published board like the heatmap does
# --------------------------------------------------------------------------------------------------


async def test_t_r1_39_dashboard_room_use_equals_the_heatmap_on_a_published_board(client):
    h = await login(client)
    term_id = await _import_guz()
    board = await _publish_board(term_id)

    # default week: today is week 4, the board covers 1-2 -> the closest week the board occupies, not 0 %
    async with get_session_factory()() as s:
        term = await s.get(Term, term_id)
        assert term is not None
        d = await build_dashboard(s, term, today=TODAY)
    assert d["current_week"] == 4 and d["utilisation_week"] == 2
    assert d["active_run_id"] == board and d["utilisation_run_id"] == board
    assert d["utilisation"] > 0.15

    for week in (1, 2):
        dash = (await client.get("/api/v1/dashboard", params={"term_id": term_id, "week": week}, headers=h)).json()
        heat = (
            await client.get("/api/v1/analytics/heatmap/rooms", params={"term_id": term_id, "week": week}, headers=h)
        ).json()
        assert heat["source"] == "board" and [r["run_id"] for r in heat["runs"]] == [board]
        overall = heat["overall"]["total"]["pct"]  # "Genel doluluk %24,1"
        assert overall > 15
        assert abs(100 * dash["utilisation"] - overall) <= 0.5, (week, dash["utilisation"], overall)
        # the building bars use the same definition: every building row is the heatmap's row
        rows = {r["key"]: r["total"]["pct"] for r in heat["rows"]}
        for b in dash["utilisation_by_building"]:
            assert abs(100 * b["utilisation"] - rows[b["building"]]) <= 0.5, (b, rows)
        assert dash["blocks_week"] == heat["counted"]["blocks"] > 0

    # a week the board does not cover reads 0 % honestly (the user picked it), still with the board's id
    d4 = (await client.get("/api/v1/dashboard", params={"term_id": term_id, "week": 4}, headers=h)).json()
    assert d4["utilisation_week"] == 4 and d4["utilisation"] == 0 and d4["active_run_id"] == board
