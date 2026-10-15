"""P19-01 / review 2026-10-15 D4: the active run of a term + kind *is* the published timetable (it drives the booking
grid). Only a finished run whose hard rules all hold may be activated; at most one run per (term, kind) is active;
the active run cannot be deleted. Activation is audited (D5).

Real Bahar 2026 import (``tests/crbs_env``): the imported weekly-grid run is FEASIBLE with hard 100 and is active.
"""

from __future__ import annotations

import asyncio

import pytest
from app.core import db as dbmod
from app.models import AuditEvent, ScheduleRun
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401


async def _run(term_id: int, **kw) -> int:  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        run = ScheduleRun(term_id=term_id, kind="COURSE", horizon="TERM", **kw)
        s.add(run)
        await s.commit()
        return run.id


async def _active(term_id: int) -> list[int]:
    async with dbmod.get_session_factory()() as s:
        q = select(ScheduleRun.id).where(
            ScheduleRun.term_id == term_id, ScheduleRun.kind == "COURSE", ScheduleRun.is_active.is_(True)
        )
        return list((await s.execute(q)).scalars())


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "FAILED", "error": "solver crashed"},
        {"status": "CANCELLED"},
        {"status": "RUNNING"},
        {"status": "INFEASIBLE", "hard_score": 0},
        {"status": "FEASIBLE", "hard_score": 87},
        {"status": "FEASIBLE", "hard_score": None},
    ],
)
async def test_only_finished_runs_with_every_hard_rule_held_are_published(env, fields):  # noqa: F811
    bad = await _run(env.term_id, **fields)
    r = await env.client.post(f"/api/v1/runs/{bad}/activate", headers=env.planner)
    assert r.status_code == 409, r.text
    assert await _active(env.term_id) == [env.run_id]  # the published grid is untouched


async def test_good_run_replaces_the_published_one_and_is_audited(env):  # noqa: F811
    good = await _run(env.term_id, status="OPTIMAL", hard_score=100, soft_score=91, label="Bahar v2")
    r = await env.client.post(f"/api/v1/runs/{good}/activate", headers=env.planner)
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True
    assert await _active(env.term_id) == [good]
    async with dbmod.get_session_factory()() as s:
        ev = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "run.activate", AuditEvent.entity_id == str(good))
            )
        ).scalar_one()
    assert ev.before == {"active_run_id": env.run_id} and ev.after["active_run_id"] == good
    assert ev.term_id == env.term_id
    # activating it again is a no-op
    r = await env.client.post(f"/api/v1/runs/{good}/activate", headers=env.planner)
    assert r.status_code == 200 and await _active(env.term_id) == [good]


async def test_concurrent_activation_leaves_exactly_one_active(env):  # noqa: F811
    ids = [await _run(env.term_id, status="FEASIBLE", hard_score=100) for _ in range(4)]
    rs = await asyncio.gather(*(env.client.post(f"/api/v1/runs/{i}/activate", headers=env.planner) for i in ids))
    assert all(r.status_code in (200, 409) for r in rs), [r.text for r in rs]
    active = await _active(env.term_id)
    assert len(active) == 1 and active[0] in ids


async def test_the_published_run_cannot_be_deleted(env):  # noqa: F811
    r = await env.client.delete(f"/api/v1/runs/{env.run_id}", headers=env.planner)
    assert r.status_code == 409, r.text
    assert await _active(env.term_id) == [env.run_id]
    other = await _run(env.term_id, status="FAILED")
    r = await env.client.delete(f"/api/v1/runs/{other}", headers=env.planner)
    assert r.status_code == 204, r.text
    async with dbmod.get_session_factory()() as s:
        n = (
            await s.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "run.delete", AuditEvent.entity_id == str(other))
            )
        ).scalar_one()
    assert n == 1
