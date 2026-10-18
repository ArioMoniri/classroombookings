"""AS-08 backtest B8 on the real Bahar workbooks (imported through the production importers into SQLite): peak
smoothing on the flexible-day subset of week 3 (Monday and Tuesday, the peak days; the classes the planner did not
lock may take either day).  With the rule on, the hard score and the placed classes are unchanged, no fixed class
moves and the load above the threshold is at most the off run's."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.services import backtest_solver as bs


async def test_b8_bahar_flexible_subset_no_class_lost_no_hard_rule_broken(engine):  # type: ignore[no-untyped-def]
    async with get_session_factory()() as s:
        inp = await bs.b8_input(s)
    res = bs.b8_peak_smoothing(inp)
    m = res.metrics
    assert m["flexible_events"] > 20 and m["events"] > 200
    assert m["hard_score_on"] == m["hard_score_off"] == 100
    assert m["placed_on"] == m["placed_off"]
    assert m["lost_classes"] == 0  # every class the off run placed is placed with the rule on
    assert m["hard_violations_on"] == m["hard_violations_off"]
    assert m["fixed_moved"] == 0
    assert m["peak_units_on"] <= m["peak_units_off"]
    assert m["peak_units_off"] > 0  # the subset has load above the threshold to smooth
    assert m["weight_zero_identical"] is True
    assert res.passed is True
