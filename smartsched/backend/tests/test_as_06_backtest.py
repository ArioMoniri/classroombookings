"""AS-06: the peak-hour model and the backtest harness on the real fixture workbooks.

* **B1** Bahar lecture weeks 9-15 forecast from the mean of weeks 1-8: MAPE <= 2 %, MASE vs naive <= 1.0
  (measured 0.70 %, 0.92);
* **B2** Bahar -> Güz period shape: Pearson >= 0.95 and >= 3 of the top-4 peak periods shared (measured 0.996);
* the Bahar peaks include P4 and P8 on Monday to Thursday; an empty database answers ``confidence: none`` + needs;
* ``GET /analytics/peaks`` on the imported Bahar board; ``python -m app.cli backtest adaptive --json``.
"""

from __future__ import annotations

import json

import pytest
from app.services import backtest as bt
from app.services import peaks as pk

from tests.crbs_env import env  # noqa: F401


def test_as_06_b1_weekly_volume(parsed_bahar_grid):
    r = bt.b1_weekly_volume(parsed_bahar_grid)
    assert r.passed, r.metrics
    assert r.metrics["weeks"] == list(range(1, 16))
    assert r.metrics["mape_pct"] <= 2.0 and r.metrics["mase"] <= 1.0
    assert r.metrics["mape_pct"] == pytest.approx(0.70, abs=0.05)


def test_as_06_b2_shape_transfer(parsed_bahar_grid, parsed_guz_grid):
    r = bt.b2_shape_transfer(parsed_bahar_grid, parsed_guz_grid)
    assert r.passed, r.metrics
    assert r.metrics["pearson"] >= 0.95 and r.metrics["top4_shared"] >= 3
    assert {4, 8} <= set(r.metrics["top4_bahar"]) and {4, 8} <= set(r.metrics["top4_guz"])


def test_as_06_bahar_peaks_include_p4_and_p8_monday_to_thursday(parsed_bahar_grid):
    cube = bt.grid_cube(parsed_bahar_grid)
    assert len(cube.weeks) == 15
    cells = pk.estimate(cube, "building", threshold=85)
    for day in (1, 2, 3, 4):
        for period in (4, 8):
            hot = [c for c in cells if (c.day, c.period) == (day, period) and c.peak]
            assert hot, (day, period)
            assert all(c.lo80 <= c.value <= c.hi80 for c in hot)
    # lunch (P6) and the evening are never a campus peak
    campus = pk.estimate(cube, "campus", threshold=85)
    assert not [c for c in campus if c.peak and (c.period == 6 or c.period >= 12)]
    # shrinkage: a two-room building moves toward the campus value
    d = [c for c in cells if c.group == "D" and (c.day, c.period) == (2, 8)][0]
    raw = d.mean
    camp = next(c for c in campus if (c.day, c.period) == (2, 8)).value
    assert min(raw, camp) <= d.value <= max(raw, camp)


async def test_as_06_empty_database_has_no_peaks(engine, session):
    out = await pk.peaks(session)
    assert out["confidence"] == "none" and out["cells"] == [] and out["needs"]["tr"] and out["needs"]["en"]


async def test_as_06_api_peaks_on_the_imported_bahar_board(env):  # noqa: F811
    r = await env.client.get(
        "/api/v1/analytics/peaks", params={"term_id": env.term_id, "group_by": "building"}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["confidence"] == "high" and out["weeks"] == list(range(1, 16)) and out["threshold_pct"] == 85
    peaks = {(c["day"], c["period"]) for c in out["peaks"]}
    assert {(d, p) for d in (1, 2, 3, 4) for p in (4, 8)} <= peaks
    assert out["peaks"][0]["label"]["tr"].endswith(". ders")
    prof = {x["period"]: x["value"] for x in out["period_profile"]}
    assert prof[4] > 75 and prof[8] > 75 and prof[6] < 50
    csv = await env.client.get(
        "/api/v1/analytics/peaks", params={"term_id": env.term_id, "format": "csv"}, headers=env.admin
    )
    assert csv.status_code == 200 and "group_by,group,day,period" in csv.text


def test_as_06_cli_backtest_json(
    monkeypatch, capsys, parsed_bahar_grid, parsed_guz_grid, parsed_bahar_list, parsed_guz_list, parsed_exam_list
):
    from app import cli

    fx = bt.Fixtures(parsed_bahar_grid, parsed_guz_grid, parsed_bahar_list, parsed_guz_list, parsed_exam_list)
    monkeypatch.setattr(bt, "load_fixtures", lambda: fx)
    code = cli.main(["backtest", "adaptive", "--json", "--skip-db"])  # B4: tests/test_as_13_learning.py
    out = json.loads(capsys.readouterr().out)
    ids = [r["id"] for r in out]
    assert {"B1", "B2", "B3", "B5", "B7"} <= set(ids)
    assert code == (0 if all(r["passed"] for r in out) else 1)
    assert all(r["passed"] for r in out), [(r["id"], r["metrics"]) for r in out if not r["passed"]]
