"""Invigilation backend asks, batch 2 (2026-10-16), on the real 2026 Final exam run
(``tests/planning_analytics_support.py``: Bahar list + room master + Final board + Final exam list, Bahar week 13
published, the Final exam run solved like ``POST /runs``, one invigilation plan with the default rules: 846 posts,
218 people).

* candidates of a post in well under the old ~58 s (only the target post's rules per person, per-person indexes),
  without blocking the event loop;
* ``POST /invigilation/plans/{id}/duties`` fills an under-staffed post by hand (every hard rule, 409 with problems,
  MANUAL + locked, audited, plan re-scored);
* a running plan stores the queue's phase + percentage (``progress {phase, pct}`` in the brief);
* a startup sweep marks plans left QUEUED / RUNNING by a dead process FAILED.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from app.core import db as dbmod
from app.core.config import get_settings
from app.models import AuditEvent, InvigilationDuty, InvigilationPlan, ScheduleRun
from app.services import invigilation as svc
from app.services.seed import seed_admin
from app.solver import invigilation as inv
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login
from tests.planning_analytics_support import build_final_plan, copy_db

P = "/api/v1/invigilation"


@pytest.fixture(scope="session")
def invig2_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("invigilation2")


@pytest.fixture
async def real(invig2_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    base, ids = await build_final_plan(invig2_dir)
    path = copy_db(base, tmp_path)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    dbmod.configure_engine(f"sqlite+aiosqlite:///{path}")
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.headers.update(await login(c))
        yield {"client": c, **ids}
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


async def _detail(c: AsyncClient, plan_id: int) -> dict[str, Any]:
    r = await c.get(f"{P}/plans/{plan_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _issue_of(pid: str, issue: str) -> bool:
    """A ``inv.validate`` line names this person exactly (``INS:1`` must not match ``INS:12``)."""
    return issue.startswith(f"{pid} at ") or issue.startswith(f"{pid}: ")


# ------------------------------------------------------------------------------------------- 1. candidates


async def test_candidates_on_the_real_final_plan_is_fast_and_matches_full_validation(real):
    c = real["client"]
    d = await _detail(c, real["plan"])
    assert d["counts"]["posts"] > 800 and d["counts"]["people"] > 200
    # the busiest exam slot: the post with the most overlapping posts on its date (most duty clashes to find)
    posts = d["posts"]

    def crowd(p: dict[str, Any]) -> int:
        return sum(
            1
            for q in posts
            if q["date"] == p["date"]
            and q["start_period"] <= p["end_period"]
            and p["start_period"] <= q["end_period"]
        )

    post = max((p for p in posts if p["assigned"]), key=lambda p: (crowd(p), p["key"]))
    t0 = time.perf_counter()
    r = await c.get(f"{P}/plans/{real['plan']}/candidates", params={"post_key": post["key"]})
    took = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    assert took < 5.0, f"candidates took {took:.2f} s (was ~58 s before batch 2)"
    cand = r.json()
    on_post = {x["person_key"] for x in post["assigned"]}
    free = {x["person_key"] for x in cand["free"]}
    out = {x["person_key"]: x["reason"] for x in cand["unavailable"]}
    assert free and out and not (free & on_post) and not (set(out) & on_post)
    assert len(free) + len(out) + len(on_post) == d["counts"]["people"]
    # every duty-side reason actually occurs on the busiest slot of the real plan
    assert "on_duty" in out.values(), sorted(set(out.values()))
    for x in cand["unavailable"]:
        assert x["reason_text"]["tr"] and x["reason_text"]["en"]
    # oracle: the solver's own whole-plan validate, for a sample of people of every outcome
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, real["exam_run"])
        assert run is not None
        built = await svc.build_input(s, run, d["params"])
        duties = (
            (await s.execute(select(InvigilationDuty).where(InvigilationDuty.plan_id == real["plan"]))).scalars().all()
        )
    kidx = {p.key: k for k, p in enumerate(built.inp.posts)}
    pidx = {p.id: i for i, p in enumerate(built.inp.people)}
    current: dict[int, list[int]] = {}
    for x in duties:
        current.setdefault(kidx[x.post_key], []).append(pidx[x.person_key])
    assert inv.validate(built.inp, current) == []  # the stored plan is valid
    by_reason: dict[str, list[str]] = {}
    for pid, why in sorted(out.items()):
        by_reason.setdefault(why, []).append(pid)
    sample = sorted(free)[:3] + [v for vs in by_reason.values() for v in vs[:2]]
    k = kidx[post["key"]]
    for pid in sample:
        trial = {q: list(v) for q, v in current.items()}
        trial[k] = [*trial.get(k, []), pidx[pid]]
        broken = [x for x in inv.validate(built.inp, trial) if _issue_of(pid, x)]
        assert bool(broken) == (pid in out), (pid, out.get(pid), broken)


async def test_candidates_does_not_block_the_event_loop(real):
    """While candidates runs, the event loop keeps ticking and a cheap request is answered before it finishes."""
    c = real["client"]
    d = await _detail(c, real["plan"])
    post = next(p for p in d["posts"] if p["assigned"])
    gaps: list[float] = []
    done = asyncio.Event()

    async def ticker() -> None:
        last = time.perf_counter()
        while not done.is_set():
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    async def heavy() -> float:
        r = await c.get(f"{P}/plans/{real['plan']}/candidates", params={"post_key": post["key"]})
        assert r.status_code == 200, r.text
        done.set()
        return time.perf_counter()

    async def cheap() -> float:
        await asyncio.sleep(0.02)
        r = await c.get(f"{P}/pool")
        assert r.status_code == 200
        return time.perf_counter()

    tick = asyncio.create_task(ticker())
    t_heavy, t_cheap = await asyncio.gather(heavy(), cheap())
    await tick
    assert t_cheap < t_heavy, "the cheap request waited for candidates"
    assert gaps and max(gaps) < 0.5, f"the event loop stalled for {max(gaps):.2f} s"
