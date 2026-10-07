"""Scale: a Bahar-like instance.  The medium case runs by default; the full 1 300-event case is
marked ``slow`` (``SMARTSCHED_SLOW=1``)."""

from __future__ import annotations

import os
import time
from dataclasses import replace

import pytest
from app.solver.cpsat import solve
from app.solver.generators import from_fixture_like
from app.solver.repair import validate

WORKERS = max(2, min(8, os.cpu_count() or 2))


def test_medium_300_events_feasible_within_20s() -> None:
    inp, planted = from_fixture_like(n_events=300, weeks=14, seed=3)
    assert len(inp.events) == 300 and len(inp.rooms) == 60
    assert not [v for v in validate(inp, planted) if v.hard]
    inp = replace(inp, time_limit_s=15.0, workers=WORKERS)
    t0 = time.perf_counter()
    res = solve(inp)
    wall = time.perf_counter() - t0
    assert res.status in ("OPTIMAL", "FEASIBLE"), (res.status, res.diagnoses[:2], res.stats)
    assert res.hard_score == 100
    assert wall < 20.0, wall
    assert len(res.assignments) == 300
    assert not [v for v in validate(inp, res.assignments) if v.hard]


@pytest.mark.slow
def test_full_1300_events_60_rooms_14_weeks_7_days_within_120s() -> None:
    inp, planted = from_fixture_like(n_events=1300, weeks=14, seed=5, days=(1, 2, 3, 4, 5, 6, 7))
    assert len(inp.events) == 1300
    assert not [v for v in validate(inp, planted) if v.hard]
    inp = replace(inp, time_limit_s=100.0, workers=WORKERS)
    t0 = time.perf_counter()
    res = solve(inp)
    wall = time.perf_counter() - t0
    assert res.status in ("OPTIMAL", "FEASIBLE"), (res.status, res.diagnoses[:2], res.stats)
    assert res.hard_score == 100
    assert wall < 120.0, wall
    assert not [v for v in validate(inp, res.assignments) if v.hard]


@pytest.mark.slow
def test_exam_instance_with_splits() -> None:
    inp, planted = from_fixture_like(n_events=400, weeks=2, seed=8, exam=True)
    inp = replace(inp, time_limit_s=60.0, workers=WORKERS)
    res = solve(inp)
    assert res.status in ("OPTIMAL", "FEASIBLE"), (res.status, res.diagnoses[:2])
    assert res.hard_score == 100
    assert any(len(a.room_ids) > 1 for a in res.assignments)
