"""AS-07: demand forecast.

* **B3**: Güz weeks 1-2 course room-periods per building from the Bahar shape x the Güz request level: WAPE <= 15 %
  (measured 5.3 %); the 80 % coverage is reported;
* ``requests``: a term with its planning list (real Bahar rows) gives computed demand cells with method, basis,
  confidence and needs (TR/EN); ``seasonal_naive``: a new term of a season that was published; an empty install
  gives ``none``; the output is deterministic.
"""

from __future__ import annotations

import json

from app.core.db import get_session_factory
from app.models import Term
from app.services import backtest as bt
from app.services import forecast as fc

from tests.api_fixtures import login
from tests.as_support import add_meeting, add_rooms, add_term, row_of
from tests.crbs_env import env  # noqa: F401


def test_as_07_b3_building_demand(parsed_bahar_grid, parsed_guz_grid, parsed_guz_list):
    r = bt.b3_building_demand(parsed_bahar_grid, parsed_guz_grid, parsed_guz_list)
    assert r.passed, r.metrics
    assert r.metrics["wape_pct"] <= 15.0
    # AS-21: the 80 % ranges are calibrated out of sample (split conformal on the Güz -> Bahar fold) and cover
    # 70-90 % of the Güz cells; the old within-term week quantiles covered 25 %
    assert 70.0 <= r.metrics["coverage80_pct"] <= 90.0, r.metrics["coverage80_pct"]
    assert r.metrics["coverage80_uncalibrated_pct"] == 25.0
    cal = r.metrics["calibration"]
    assert cal["fold"] == "guz->bahar" and cal["n"] == 60 and cal["shape_q80"] == fc.SHAPE_Q80
    assert cal["level_rel_sd"] == fc.LEVEL_REL_SD_PRIOR
    assert {c["building"] for c in r.metrics["cells"]} >= {"A", "B", "C"}
    again = bt.b3_building_demand(parsed_bahar_grid, parsed_guz_grid, parsed_guz_list)
    assert json.dumps(again.as_dict(), sort_keys=True) == json.dumps(r.as_dict(), sort_keys=True)


def test_as_07_damped_level_needs_three_points():
    assert fc.damped_level([100.0, 110.0]) == 110.0
    v = fc.damped_level([100.0, 110.0, 120.0])
    assert 120.0 < v < 135.0


async def test_as_07_requests_method_from_the_terms_own_list(client, parsed_bahar_list):
    h = await login(client)
    async with get_session_factory()() as s:
        term = await add_term(s, "2026-BAHAR", week_kinds=["LECTURE"] * 14)
        rooms = await add_rooms(s, "A101", "A204", "C403", "C501", "B207")
        for row in (2, 120, 296, 84):  # MAT 112 (180), PTL 204 (36), NUT 254 (60), BP 112 in a PC lab (49)
            await add_meeting(s, term, row_of(parsed_bahar_list, row), rooms)
        await s.commit()
        tid = term.id
    r = await client.get("/api/v1/analytics/forecast/demand", params={"term_id": tid, "group_by": "tag"}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["method"] == "requests" and out["confidence"] == "high"
    cells = {tuple(c["key"]): c for c in out["cells"]}
    assert cells[("PC",)]["value"] == 4.0  # BP 112: P2-P5 every week
    assert cells[("PC",)]["label"] == {"tr": "bilgisayar laboratuvarı", "en": "computer lab"}
    for c in out["cells"]:
        assert c["method"] == "requests" and c["basis"]["tr"] and c["basis"]["en"] and c["confidence"] == "high"
        assert "needs" in c
    by_band = (
        await client.get(
            "/api/v1/analytics/forecast/demand", params={"term_id": tid, "group_by": "capacity_band"}, headers=h
        )
    ).json()
    assert ("151+",) in {tuple(c["key"]) for c in by_band["cells"]}  # MAT 112, 180 students
    again = (
        await client.get(
            "/api/v1/analytics/forecast/demand", params={"term_id": tid, "group_by": "capacity_band"}, headers=h
        )
    ).json()
    assert again == by_band


async def test_as_07_empty_install_says_none(client):
    h = await login(client)
    out = (await client.get("/api/v1/analytics/forecast/demand", headers=h)).json()
    assert out["confidence"] == "none" and out["cells"] == [] and out["needs"]["tr"] and out["needs"]["en"]


async def test_as_07_seasonal_naive_for_a_new_term_of_a_published_season(env):  # noqa: F811
    async with get_session_factory()() as s:
        t = Term(code="2027-BAHAR", name="2027 Bahar", week_count=14)
        s.add(t)
        await s.commit()
        tid = t.id
    out = (
        await env.client.get(
            "/api/v1/analytics/forecast/demand", params={"term_id": tid, "group_by": "building"}, headers=env.admin
        )
    ).json()
    assert out["method"] == "seasonal_naive" and out["source_term_id"] == env.term_id
    # AS-21: one published term of the season cannot calibrate a cross-term range: "düşük güven" with the
    # backtest-calibrated default width, never the narrow week-to-week quantiles
    assert out["confidence"] == "low"
    a = next(c for c in out["cells"] if c["key"] == ["A"])
    assert a["lo80"] <= a["value"] <= a["hi80"] and a["value"] > 0
    assert a["confidence"] == "low" and a["needs"]["tr"].startswith("Düşük güven") and a["needs"]["en"]
    assert a["hi80"] - a["value"] >= 0.99 * fc.calibrated_half_width(a["value"], fc.SHAPE_Q80, fc.LEVEL_REL_SD_PRIOR)
    assert "kohort oranı 1" in a["basis"]["tr"]
    tagged = (
        await env.client.get(
            "/api/v1/analytics/forecast/demand", params={"term_id": tid, "group_by": "tag"}, headers=env.admin
        )
    ).json()
    assert tagged["confidence"] == "none" and tagged["needs"]["tr"]


def test_as_07_shape_q80_is_the_backtest_calibration(parsed_bahar_grid, parsed_guz_grid):
    # the shipped default is what the Güz -> Bahar fold of the real workbooks gives (shape-only Poisson scores)
    scores = bt.shape_scores(parsed_guz_grid, parsed_bahar_grid)
    assert len(scores) == 60
    assert round(fc.conformal_quantile(scores), 2) == fc.SHAPE_Q80


def test_as_07_conformal_quantile_needs_enough_scores():
    assert fc.conformal_quantile([1.0, 2.0, 3.0]) is None  # ceil(4 x 0.8) = 4 > 3 scores
    assert fc.conformal_quantile([float(i) for i in range(1, 11)]) == 9.0  # ceil(11 x 0.8) = 9th smallest


def test_as_07_seasonal_ranges_calibrate_on_the_installs_own_history(parsed_bahar_grid, parsed_guz_grid):
    # real weekly room-periods per building: the earlier term (Güz) predicts the later one (Bahar)
    def weekly(grid):
        by_week = bt.building_course_room_periods(grid)
        keys = sorted({b for v in by_week.values() for b in v})
        return {(b,): [float(by_week[w].get(b, 0)) for w in sorted(by_week)] for b in keys}

    src = weekly(parsed_bahar_grid)
    alone = fc.seasonal_ranges(src)
    assert alone.confidence == "low" and alone.q80 == fc.SHAPE_Q80 and alone.n_scores == 0
    own = fc.seasonal_ranges(src, prev_weekly=weekly(parsed_guz_grid))
    assert own.confidence == "medium" and own.n_scores == 60 and own.q80 is not None and own.q80 > 0
    for key, (v, lo, hi) in own.cells.items():
        assert lo <= v <= hi, key
    for v, _lo, hi in own.cells.values():
        assert hi - v >= 0.99 * own.q80 * max(v, 1.0) ** 0.5  # the own quantile, no level prior on top
