"""Round-1 R1-M-11: an invigilation plan over an exam run that seats no exam in a room had 0 room-sessions and said
"En iyi · 0 salon-oturum, 0 görev: tümü atandı · sert 100 · yumuşak 100", and could be published. An empty plan
says that there is nothing to assign and why, carries no scores, and is never published.

Real 2026 Final data (``tests/planning_analytics_support``): the exam term, its pool and teaching; the empty exam
run is a finished exam run of the same term with no rows (the imported Final list without rooms in round 1).
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import ScheduleRun

from tests.planning_analytics_support import PLAN_PARAMS
from tests.test_invigilation_api import P, _wait, invig_dir, real  # noqa: F401


async def test_empty_plan_is_named_and_never_published(real):  # noqa: F811
    c = real["client"]
    async with dbmod.get_session_factory()() as s:
        src = await s.get(ScheduleRun, real["exam_run"])
        assert src is not None
        empty = ScheduleRun(
            term_id=src.term_id,
            kind="EXAM",
            horizon=src.horizon,
            horizon_params=dict(src.horizon_params or {}),
            status="FEASIBLE",
            hard_score=100,
            params={},
            stats={},
            label="Grid import: exam list without rooms",
        )
        s.add(empty)
        await s.commit()
        run_id = empty.id
    r = await c.post(f"{P}/plans", json={"exam_run_id": run_id, "params": PLAN_PARAMS})
    assert r.status_code in (200, 201, 202), r.text
    d = await _wait(c, r.json()["plan_id"])
    assert d["empty"] is True and d["counts"]["posts"] == 0, d
    assert d["hard_score"] is None and d["soft_score"] is None
    assert d["headline"]["tr"].startswith("Atanacak görev yok") and "tümü atandı" not in d["headline"]["tr"]
    assert f"#{run_id}" in d["empty_reason"]["tr"]
    r = await c.post(f"{P}/plans/{d['id']}/activate")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "empty_plan" and "Boş plan yayımlanamaz" in r.json()["detail"]["tr"]
    # the real plan is unchanged: staffed, scored, publishable
    real_plan = (await c.get(f"{P}/plans/{real['plan']}")).json()
    assert real_plan["empty"] is False and real_plan["hard_score"] == 100
    r = await c.post(f"{P}/plans/{real['plan']}/activate")
    assert r.status_code == 200, r.text
