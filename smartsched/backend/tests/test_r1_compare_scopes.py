"""Round-1 R1-M-10: comparing a week run with a term run said "B daha iyi" for metrics the week run simply has no
data for (instructor gaps 348 -> 0, highest weekly load 45 -> 0). Runs with different horizons are compared on the
weeks they share; a metric a side has no data for is "not comparable" (``better: null``, ``comparable: false``).

Real Bahar 2026 week-3 runs (``tests/planning_analytics_support``); the term run is run A's timetable stored as a
TERM run (its rows in every teaching week), and a second term run whose rows avoid week 3.
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import Assignment, ScheduleRun
from sqlalchemy import select

from tests.test_planning_analytics import analytics_dir, bahar  # noqa: F401


async def _term_copy(run_id: int, weeks: list[int]) -> int:
    async with dbmod.get_session_factory()() as s:
        src = await s.get(ScheduleRun, run_id)
        assert src is not None
        run = ScheduleRun(
            term_id=src.term_id,
            kind="COURSE",
            horizon="TERM",
            horizon_params={},
            status="FEASIBLE",
            hard_score=100,
            soft_score=src.soft_score,
            params=dict(src.params or {}),
            stats={**(src.stats or {}), "placed": (src.stats or {}).get("placed")},
            label="term copy",
        )
        s.add(run)
        await s.flush()
        for a in (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars():
            s.add(
                Assignment(
                    run_id=run.id,
                    meeting_request_id=a.meeting_request_id,
                    week=None,
                    weeks=weeks,
                    day=a.day,
                    start_period=a.start_period,
                    end_period=a.end_period,
                    room_ids=list(a.room_ids or []),
                    origin="SOLVER",
                )
            )
        await s.commit()
        return run.id


async def test_week_run_against_a_term_run_compares_the_shared_week(bahar):  # noqa: F811
    c = bahar["client"]
    term = await _term_copy(bahar["a"], list(range(1, 15)))
    d = (await c.get("/api/v1/analytics/compare", params={"a": term, "b": bahar["b"]})).json()
    assert d["scope"]["differs"] and d["scope"]["common_weeks"] == [3] and d["scope"]["compared_weeks"] == [3]
    assert "Kapsamlar farklı" in d["headline"]["tr"] and "3. hafta" in d["scope"]["note"]["tr"]
    m = {x["key"]: x for x in d["metrics"]}
    for k in ("gaps_per_week_total", "instructors_with_gaps", "periods_per_week_max", "utilisation_pct"):
        assert m[k]["comparable"] and m[k]["a"] and m[k]["b"], m[k]  # both runs have week-3 data
    for k in ("placed", "unplaced", "objective", "soft_score"):
        assert m[k]["better"] is None and m[k]["comparable"] is False, m[k]
    assert all(r["better"] is None for r in d["rules"])


async def test_no_shared_data_is_never_better(bahar):  # noqa: F811
    c = bahar["client"]
    late = await _term_copy(bahar["a"], [8, 9, 10])  # a term timetable with nothing in week 3
    d = (await c.get("/api/v1/analytics/compare", params={"a": late, "b": bahar["b"]})).json()
    m = {x["key"]: x for x in d["metrics"]}
    for k in ("gaps_per_week_total", "instructors_with_gaps", "periods_per_week_max", "utilisation_pct"):
        assert m[k]["better"] is None and m[k]["comparable"] is False and m[k]["b"] is None, m[k]
    # same-scope runs are still compared normally
    same = (await c.get("/api/v1/analytics/compare", params={"a": bahar["a"], "b": bahar["b"]})).json()
    assert not same["scope"]["differs"] and same["scope"]["note"] is None
    assert all(x["comparable"] for x in same["metrics"] if x["a"] is not None and x["b"] is not None)
