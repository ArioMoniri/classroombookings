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
            if q["date"] == p["date"] and q["start_period"] <= p["end_period"] and p["start_period"] <= q["end_period"]
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


# ------------------------------------------------------------------------------------------- 2. fill a post by hand


async def _understaffed(c: AsyncClient, real: dict[str, Any]) -> dict[str, Any]:
    """The real Final staffed by two research assistants at one invigilator per 10 students: INFEASIBLE, most rooms
    short (the duties that fit are made, nothing relaxed)."""
    for name in ("Arş. Gör. Deniz Ak", "Arş. Gör. Elif Kara"):
        r = await c.post(f"{P}/pool", json={"full_name": name, "kind": "ASSISTANT", "term_id": real["final_id"]})
        assert r.status_code == 201, r.text
    r = await c.post(
        f"{P}/plans",
        json={
            "exam_run_id": real["exam_run"],
            "params": {"instructor_pool": "none", "students_per_invigilator": 10, "time_limit_s": 3},
        },
    )
    assert r.status_code == 202, r.text
    await qmod.get_queue().wait_idle(600)
    d = await _detail(c, r.json()["plan_id"])
    assert d["status"] == "INFEASIBLE" and d["counts"]["missing"] > 0
    return d


async def test_fill_an_understaffed_post_by_hand(real):
    c = real["client"]
    d = await _understaffed(c, real)
    plan_id = d["id"]
    # a third assistant joins after the run (İ/ı in the name: canonical keys must hold)
    r = await c.post(
        f"{P}/pool", json={"full_name": "Arş. Gör. İpek Işık", "kind": "ASSISTANT", "term_id": real["final_id"]}
    )
    assert r.status_code == 201, r.text
    new = r.json()["person_key"]
    short = sorted((p for p in d["posts"] if p["missing"]), key=lambda p: (p["date"], p["start_period"], p["key"]))

    def overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
        return (
            a["key"] != b["key"]
            and a["date"] == b["date"]
            and a["start_period"] <= b["end_period"]
            and b["start_period"] <= a["end_period"]
        )

    # the first short post with another short post at the same time (a clash for the same person)
    post, clash = next((a, b) for a in short for b in short if overlaps(a, b))
    before_hard = d["hard_score"]
    r = await c.post(
        f"{P}/plans/{plan_id}/duties",
        json={"post_key": post["key"], "person_key": new, "reason": "elle tamamlandı"},
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["person_key"] == new and out["origin"] == "MANUAL" and out["is_locked"] is True
    assert out["post_key"] == post["key"] and out["date"] == post["date"] and out["room_id"] == post["room_id"]
    assert out["person_name"] == "Arş. Gör. İpek Işık"
    # re-scored: one more seat filled, the post one fewer missing, the load counts the new person
    after = await _detail(c, plan_id)
    assert after["counts"]["filled"] == d["counts"]["filled"] + 1
    assert after["counts"]["missing"] == d["counts"]["missing"] - 1
    assert after["hard_score"] >= before_hard and after["status"] == "INFEASIBLE"
    p2 = next(p for p in after["posts"] if p["key"] == post["key"])
    assert p2["missing"] == post["missing"] - 1 and new in {x["person_key"] for x in p2["assigned"]}
    load = next(x for x in after["people"] if x["person_key"] == new)
    assert load["duties"] == 1 and load["periods"] == post["end_period"] - post["start_period"] + 1
    assert load["days"] == 1
    # the same person at an overlapping post: 409 with the problem, nothing stored
    r = await c.post(f"{P}/plans/{plan_id}/duties", json={"post_key": clash["key"], "person_key": new})
    assert r.status_code == 409, r.text
    det = r.json()["detail"]
    assert det["reason"] == "on_duty" and det["problems"] and "at once" in det["problems"][0]
    assert det["tr"] and det["en"] and det["reason_text"]["tr"]
    # twice on one post, an unknown person, an unknown post
    r = await c.post(f"{P}/plans/{plan_id}/duties", json={"post_key": post["key"], "person_key": new})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "on_post"
    r = await c.post(f"{P}/plans/{plan_id}/duties", json={"post_key": post["key"], "person_key": "STAFF:999999"})
    assert r.status_code == 422
    r = await c.post(f"{P}/plans/{plan_id}/duties", json={"post_key": "2026-01-01|1|1-2", "person_key": new})
    assert r.status_code == 404
    # declared unavailability holds too
    other = next(p for p in short if p["date"] != post["date"])
    pool = {m["person_key"]: m for m in (await c.get(f"{P}/pool")).json()}
    r = await c.put(
        f"{P}/pool/{pool[new]['id']}", json={"unavailable": [{"date": other["date"], "note": "bölüm kurulu"}]}
    )
    assert r.status_code == 200, r.text
    r = await c.post(f"{P}/plans/{plan_id}/duties", json={"post_key": other["key"], "person_key": new})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "unavailable"
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "invigilation.add_duty"))).scalar_one()
        n_duties = len(
            (await s.execute(select(InvigilationDuty).where(InvigilationDuty.plan_id == plan_id))).scalars().all()
        )
    assert ev.reason == "elle tamamlandı" and ev.after["person_key"] == new and ev.before is None
    assert n_duties == after["counts"]["filled"]


async def test_a_full_post_takes_no_extra_invigilator(real):
    c = real["client"]
    d = await _detail(c, real["plan"])
    post = next(p for p in d["posts"] if p["assigned"] and not p["missing"])
    cand = (await c.get(f"{P}/plans/{real['plan']}/candidates", params={"post_key": post["key"]})).json()
    r = await c.post(
        f"{P}/plans/{real['plan']}/duties", json={"post_key": post["key"], "person_key": cand["free"][0]["person_key"]}
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["reason"] == "post_full" and r.json()["detail"]["problems"]


async def test_reassign_rescores_the_plan(real):
    """A swap keeps the counts and moves the load (days included) from the old to the new person."""
    c = real["client"]
    d = await _detail(c, real["plan"])
    post = next(p for p in d["posts"] if p["assigned"])
    duty = post["assigned"][0]
    cand = (await c.get(f"{P}/plans/{real['plan']}/candidates", params={"post_key": post["key"]})).json()
    loads = {x["person_key"]: x for x in d["people"]}
    good = min(cand["free"], key=lambda x: (x["person_key"] in loads, x["person_key"]))  # nobody's load, if any
    was = loads.get(good["person_key"], {"duties": 0, "days": 0})
    r = await c.put(f"{P}/plans/{real['plan']}/duties/{duty['id']}", json={"person_key": good["person_key"]})
    assert r.status_code == 200, r.text
    after = await _detail(c, real["plan"])
    assert after["counts"] == d["counts"] and after["hard_score"] == 100
    new_load = {x["person_key"]: x for x in after["people"]}[good["person_key"]]
    assert new_load["duties"] == was["duties"] + 1 and new_load["days"] >= max(1, was["days"])
    old = {x["person_key"]: x for x in after["people"]}.get(duty["person_key"])
    assert (old["duties"] if old else 0) == loads[duty["person_key"]]["duties"] - 1


# ------------------------------------------------------------------------------------------- 3. progress


async def test_a_running_plan_stores_the_queue_phase_and_percentage(real):
    c = real["client"]
    r = await c.post(f"{P}/plans", json={"exam_run_id": real["exam_run"], "params": {"time_limit_s": 3}})
    assert r.status_code == 202, r.text
    plan_id = r.json()["plan_id"]
    brief = (await c.get(f"{P}/plans")).json()
    assert next(p for p in brief if p["id"] == plan_id)["progress"]["phase"] in ("queued", "loading", "solving")
    seen: list[tuple[str, int]] = []
    for _ in range(2000):
        b = next(
            p
            for p in (await c.get(f"{P}/plans", params={"exam_run_id": real["exam_run"]})).json()
            if p["id"] == plan_id
        )
        pr = b["progress"]
        if not seen or seen[-1] != (pr["phase"], pr["pct"]):
            seen.append((pr["phase"], pr["pct"]))
        if b["status"] not in ("QUEUED", "RUNNING"):
            break
        await asyncio.sleep(0.02)
    await qmod.get_queue().wait_idle(600)
    d = await _detail(c, plan_id)
    assert d["status"] in ("OPTIMAL", "FEASIBLE") and d["progress"] == {"phase": "done", "pct": 100}
    # the phases the job reported, in order, from the database (not the in-memory queue): the solve is seen running
    phases = [ph for ph, _ in seen]
    assert "solving" in phases, seen
    assert [x for x in phases if x in ("queued", "loading", "solving", "persisting", "done")] == phases, seen
    pcts = [pct for _, pct in seen]
    assert pcts == sorted(pcts), seen
    async with dbmod.get_session_factory()() as s:
        row = await s.get(InvigilationPlan, plan_id)
        assert row is not None and row.heartbeat_at is not None  # the queue beat for the plan while it ran


# ------------------------------------------------------------------------------------------- 4. startup sweep


async def test_startup_sweep_fails_plans_of_a_dead_process(real):
    import datetime as dt

    from app.main import lifespan

    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    async with dbmod.get_session_factory()() as s:
        dead = InvigilationPlan(
            term_id=real["final_id"],
            exam_run_id=real["exam_run"],
            status="RUNNING",
            stats={"worker": {"host": "old", "pid": 1, "boot": "a-dead-boot"}},
            progress_phase="solving",
            progress_pct=30,
            heartbeat_at=now - dt.timedelta(minutes=5),
        )
        queued = InvigilationPlan(
            term_id=real["final_id"], exam_run_id=real["exam_run"], status="QUEUED", stats={"worker": {"boot": "x"}}
        )
        live = InvigilationPlan(  # another replica, still beating: left alone
            term_id=real["final_id"],
            exam_run_id=real["exam_run"],
            status="RUNNING",
            stats={"worker": {"host": "node-2", "pid": 7, "boot": "another-live-boot"}},
            heartbeat_at=now,
        )
        s.add_all([dead, queued, live])
        await s.commit()
        ids = (dead.id, queued.id, live.id)
    from app.main import app

    async with lifespan(app):
        async with dbmod.get_session_factory()() as s:
            rows = {p.id: p for p in (await s.execute(select(InvigilationPlan))).scalars()}
    for pid in ids[:2]:
        assert rows[pid].status == "FAILED" and "interrupted" in (rows[pid].error or "")
        assert rows[pid].finished_at is not None and rows[pid].progress_phase == "failed"
    assert rows[ids[2]].status == "RUNNING"
    async with dbmod.get_session_factory()() as s:
        assert await svc.recover_interrupted_plans(s) == 0  # idempotent
