"""Owner decision 2026-10-17 (R1-S-37, ledger ``decisions-2026-10-17``): an administrator's forced move on the live
(published) plan never edits the live run. The server clones the active run into a new draft (same placements + the
forced edit, the broken rule recorded with the reason on the draft), answers with the draft id, and the live plan
stays as published until the draft is published through the normal guard (``confirm_forced_breaks``).

Real Bahar 2026 import (``tests/crbs_env``): its run is published; the board has parallel Monday classes in different
rooms, so moving one into the other's room in week 3 is a room clash (``room_overlap``).
"""

from __future__ import annotations

from typing import Any

from app.core import db as dbmod
from app.models import Assignment, ScheduleRun
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.test_admin_persona_integrity import _pair

REASON = "Bölüm başkanlığı onayı: ortak sınav provası"


def _row(a: Assignment) -> tuple[Any, ...]:
    return (
        a.meeting_request_id,
        a.exam_request_id,
        a.week,
        tuple(a.weeks or []),
        a.day,
        a.date,
        a.start_period,
        a.end_period,
        tuple(a.room_ids or []),
        a.label,
        tuple(a.course_codes or []),
        a.is_locked,
        a.origin,
        a.archived,
    )


async def _state(run_id: int) -> tuple[ScheduleRun, dict[int, tuple[Any, ...]]]:
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, run_id)
        assert run is not None
        rows = (await s.execute(select(Assignment).where(Assignment.run_id == run_id))).scalars()
        return run, {a.id: _row(a) for a in rows}


async def _n_runs() -> int:
    async with dbmod.get_session_factory()() as s:
        return len(list((await s.execute(select(ScheduleRun.id))).scalars()))


async def test_run_copy_clones_every_placement_into_an_unpublished_draft(env):  # noqa: F811
    from app.services import run_copy

    live, before = await _state(env.run_id)
    async with dbmod.get_session_factory()() as s:
        src = await s.get(ScheduleRun, env.run_id)
        assert src is not None and src.is_active
        draft, id_map = await run_copy.clone_as_draft(s, src, actor=None, reason=REASON)
        await s.commit()
        draft_id = draft.id
    d, rows = await _state(draft_id)
    assert d.is_active is False and d.parent_run_id == env.run_id and d.term_id == live.term_id
    assert d.kind == live.kind and d.status == live.status and d.hard_score == live.hard_score
    assert (d.stats or {}).get("forced_draft", {}).get("live_run_id") == env.run_id
    assert set(id_map) == set(before) and set(id_map.values()) == set(rows)
    assert all(rows[id_map[aid]] == r for aid, r in before.items())  # same placements, field for field
    _, after = await _state(env.run_id)
    assert after == before  # the live rows are untouched


async def test_forced_move_on_the_published_plan_creates_a_draft_and_keeps_the_live_plan(env):  # noqa: F811
    a, b = await _pair(env.run_id)
    live, before = await _state(env.run_id)
    assert live.is_active
    move = {"moves": [{"aid": a.id, "room_ids": list(b.room_ids), "scope": "week", "week": 3}], "force": True}
    base = f"/api/v1/runs/{env.run_id}/assignments"
    # a planner still cannot force; without a reason the admin's force is still a 422 naming the rule
    assert (
        await env.client.post(f"{base}/bulk-move", json={**move, "reason": REASON}, headers=env.planner)
    ).status_code == 403
    r = await env.client.post(f"{base}/bulk-move", json=move, headers=env.admin)
    assert r.status_code == 422 and "room_overlap" in str(r.json()["detail"]), r.text

    r = await env.client.post(f"{base}/bulk-move", json={**move, "reason": REASON}, headers=env.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    draft_id = out["draft_run_id"]
    assert draft_id and draft_id != env.run_id and out["live_run_id"] == env.run_id and out["applied"] is True

    # the live plan is exactly as published: rows, score, no override, still the active run
    after_live, after = await _state(env.run_id)
    assert after == before
    assert after_live.is_active and after_live.hard_score == live.hard_score
    assert not (after_live.stats or {}).get("forced_overrides")

    # the draft holds the forced edit and the broken rule with the reason
    draft = (await env.client.get(f"/api/v1/runs/{draft_id}", headers=env.admin)).json()
    assert draft["is_active"] is False and draft["parent_run_id"] == env.run_id
    assert draft["hard_score"] < 100
    (ov,) = draft["stats"]["forced_overrides"]
    assert ov["reason"] == REASON and "room_overlap" in ov["rules"]
    _, drows = await _state(draft_id)
    moved = [drows[x["id"]] for x in out["assignments"] if x["id"] in drows]  # the answer's rows are the draft's
    assert moved and any(r[8] == tuple(b.room_ids) and r[3] == (3,) for r in moved), moved

    # publishing the draft goes through the normal guard: the forced-break tick is required
    r = await env.client.post(f"/api/v1/runs/{draft_id}/activate", headers=env.admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "forced_breaks", r.text
    r = await env.client.post(
        f"/api/v1/runs/{draft_id}/activate", json={"confirm_forced_breaks": True}, headers=env.admin
    )
    assert r.status_code == 200 and r.json()["is_active"] is True, r.text
    assert (await _state(env.run_id))[0].is_active is False


async def test_an_unforced_move_and_a_dry_run_on_the_published_plan_make_no_draft(env):  # noqa: F811
    a, b = await _pair(env.run_id)
    move = {"moves": [{"aid": a.id, "room_ids": list(b.room_ids), "scope": "week", "week": 3}]}
    n_runs = await _n_runs()
    r = await env.client.post(f"/api/v1/runs/{env.run_id}/assignments/bulk-move", json=move, headers=env.admin)
    assert r.status_code == 200 and r.json()["applied"] is False and r.json().get("draft_run_id") is None, r.text
    r = await env.client.post(
        f"/api/v1/runs/{env.run_id}/assignments/bulk-move",
        json={**move, "force": True, "reason": REASON, "dry_run": True},
        headers=env.admin,
    )
    assert r.status_code == 200 and r.json().get("draft_run_id") is None, r.text
    assert await _n_runs() == n_runs


async def test_single_forced_move_on_the_published_plan_creates_a_draft(env):  # noqa: F811
    a, b = await _pair(env.run_id)
    _, before = await _state(env.run_id)
    r = await env.client.post(
        f"/api/v1/runs/{env.run_id}/assignments/{a.id}/move",
        json={"room_ids": list(b.room_ids), "week": 3, "force": True, "reason": REASON},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["draft_run_id"] and out["draft_run_id"] != env.run_id
    assert out["live_run_id"] == env.run_id
    assert (await _state(env.run_id))[1] == before
    draft = (await env.client.get(f"/api/v1/runs/{out['draft_run_id']}", headers=env.admin)).json()
    assert draft["is_active"] is False and draft["stats"]["forced_overrides"][0]["reason"] == REASON
