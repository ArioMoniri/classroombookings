"""Round-1 R1-M-04 / R1-M-05 / R1-S-01 on a real Bahar 2026 week-3 run (CP-SAT, fixed seed), published.

* R1-M-04: the run's verdict comes from one object (``stats.truth``, the planner-level check of the stored rows);
  the run, its summary and the card read the same placed / total / verdict / headline, and a run with accepted
  exceptions never says "hiçbir kural bozulmadı".
* R1-M-05 / R1-S-01: a move is checked with the run's own hard-rule evaluation. PHAR 240 §1 into a free TIP room
  (the cause of the silent 100 -> 99) is a hard conflict; a planner cannot apply it, an administrator forces it only
  with a written reason; on the published run that edit goes into a new draft (owner decision 2026-10-17, R1-S-37:
  the live run keeps hard 100) which names the broken rule with the reason (stats.integrity.broken, truth, summary
  headline, audit), publishing it needs ``confirm_forced_breaks``; undoing the move brings hard 100 back. Moving the planner's own LOCKED class to a free fitting room is "uygun" and keeps hard 100 (a listed
  manual edit).
"""

from __future__ import annotations

from typing import Any

from app.core import db as dbmod
from app.models import Assignment, AuditEvent, Room
from app.workers.queue import get_queue
from sqlalchemy import select

from tests import studio_support
from tests.studio_support import meeting_id

bahar = studio_support.bahar


async def _week3_run(bahar) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    await c.get(url, headers=h)
    r = await c.put(url, json={"version": 1, "horizon": "WEEK", "horizon_params": {"weeks": [3]}}, headers=h)
    assert r.status_code == 200, r.text
    r = await c.post(
        f"{url}/generate", json={"params": {"solver": "cpsat", "time_limit_s": 20, "workers": 2, "seed": 1}}, headers=h
    )
    assert r.status_code == 202, r.text
    await get_queue().wait_idle(timeout=600)
    run = (await c.get(f"/api/v1/runs/{r.json()['run_id']}", headers=h)).json()
    assert run["status"] == "FEASIBLE_PARTIAL" and run["hard_score"] == 100, (run["status"], run.get("error"))
    return run


async def _phar(run_id: int) -> Assignment:
    mid = await meeting_id("PHAR 240", day=1, start=1)
    async with dbmod.get_session_factory()() as s:
        return (
            await s.execute(select(Assignment).where(Assignment.run_id == run_id, Assignment.meeting_request_id == mid))
        ).scalar_one()


SATURDAY = 6  # the Bahar week has no Saturday classes: every room is free, so only the planner's own rules speak


async def _free(bahar, run_id: int, a: Assignment, tip: bool) -> int:  # type: ignore[no-untyped-def]
    r = await bahar.client.get(
        f"/api/v1/runs/{run_id}/free-rooms",
        params={
            "day": SATURDAY,
            "start_period": a.start_period,
            "end_period": a.end_period,
            "exclude_assignment_id": a.id,
        },
        headers=bahar.planner,
    )
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        tags = {x.id: set(x.tags or []) for x in (await s.execute(select(Room))).scalars()}
    rooms = r.json()["rooms"]
    if tip:
        hit = [x for x in rooms if "TIP" in tags[x["room_id"]] and x["capacity"] >= 80 and x["status"] != "busy"]
        assert hit and all(x["status"] == "tag_mismatch" for x in hit), hit[:3]  # never listed as free
    else:
        hit = [x for x in rooms if x["status"] == "free" and x["room_id"] not in (a.room_ids or [])]
    assert hit, [(x["code"], x["status"], x["capacity"], (x.get("reason") or {}).get("en")) for x in rooms][:40]
    return int(hit[0]["room_id"])


async def test_verdict_and_moves_use_the_runs_own_hard_rules(bahar):
    c, planner, admin = bahar.client, bahar.planner, bahar.admin
    run = await _week3_run(bahar)
    rid = run["id"]
    # ---- R1-M-04: one truth
    truth = run["stats"]["truth"]
    assert truth["source"] == "planner_check" and truth["verdict"] in ("exceptions", "clean")
    assert (truth["placed"], truth["total"]) == (run["stats"]["placed"], run["stats"]["events_total"])
    assert truth["broken"] == [] and truth["hard_score"] == 100
    summary = (await c.get(f"/api/v1/runs/{rid}/summary", headers=planner)).json()
    assert summary["truth"]["verdict"] == truth["verdict"] and summary["headline"]["tr"].startswith(
        truth["headline"]["tr"]
    )
    if truth["verdict"] == "exceptions":
        assert "hiçbir kural bozulmadı" not in summary["headline"]["tr"]
        assert all(x["label"]["tr"] for x in truth["exceptions"])
    r = await c.post(f"/api/v1/runs/{rid}/activate", json={"confirm_scope_reduction": True}, headers=planner)
    assert r.status_code == 200, r.text
    # ---- R1-S-01 / R1-M-05: a TIP room is a hard conflict for a non-medical class (the solver's room-tag rule)
    a = await _phar(rid)
    tip = await _free(bahar, rid, a, tip=True)
    body = {"day": SATURDAY, "room_ids": [tip], "scope": "week", "week": 3}
    pre = (await c.post(f"/api/v1/runs/{rid}/assignments/{a.id}/move-preview", json=body, headers=planner)).json()
    item = pre["items"][0]
    assert not item["ok"] and any(i["code"] == "tip" and i["severity"] == "hard" for i in item["hard"]), item
    # the single-move endpoint agrees
    r = await c.post(
        f"/api/v1/runs/{rid}/assignments/{a.id}/move", json={"day": SATURDAY, "room_ids": [tip]}, headers=planner
    )
    assert r.status_code == 200 and r.json()["ok"] is False, r.json()
    # a planner cannot apply it; an administrator needs a written reason
    move = {"moves": [{"aid": a.id, **body}]}
    r = await c.post(f"/api/v1/runs/{rid}/assignments/bulk-move", json=move, headers=planner)
    assert r.status_code == 200 and r.json()["applied"] is False
    r = await c.post(f"/api/v1/runs/{rid}/assignments/bulk-move", json={**move, "force": True}, headers=planner)
    assert r.status_code == 403
    r = await c.post(f"/api/v1/runs/{rid}/assignments/bulk-move", json={**move, "force": True}, headers=admin)
    assert r.status_code == 422 and "reason" in str(r.json()["detail"])
    reason = "Bölüm başkanı onayı, tek seferlik"
    r = await c.post(
        f"/api/v1/runs/{rid}/assignments/bulk-move", json={**move, "force": True, "reason": reason}, headers=admin
    )
    assert r.status_code == 200 and r.json()["applied"] is True, r.text
    # owner decision 2026-10-17 (R1-S-37): the forced edit went into a new draft; the published run is unchanged
    did = r.json()["draft_run_id"]
    assert did and did != rid and r.json()["live_run_id"] == rid
    undo = r.json()["undo"]
    live = (await c.get(f"/api/v1/runs/{rid}", headers=planner)).json()
    assert live["is_active"] and live["hard_score"] == 100 and not live["stats"].get("forced_overrides")
    # ---- surfaced: the draft names the broken rule, its reason and the score
    after = (await c.get(f"/api/v1/runs/{did}", headers=planner)).json()
    assert not after["is_active"] and after["hard_score"] < 100
    broken = after["stats"]["integrity"]["broken"]
    assert [b["rule"] for b in broken] == ["tags"], broken
    assert broken[0]["explained"] and broken[0]["reason"] == reason and "TIP" in broken[0]["message"]
    t2 = after["stats"]["truth"]
    assert t2["verdict"] == "broken" and t2["broken_count"] == 1 and t2["hard_score"] == after["hard_score"]
    s2 = (await c.get(f"/api/v1/runs/{did}/summary", headers=planner)).json()
    assert "1 kesin kural bozuk" in s2["headline"]["tr"] and "hiçbir kural bozulmadı" not in s2["headline"]["tr"]
    async with dbmod.get_session_factory()() as s:
        ev = (
            (
                await s.execute(
                    select(AuditEvent).where(AuditEvent.action == "run.hard_score", AuditEvent.entity_id == str(did))
                )
            )
            .scalars()
            .first()
        )
    assert ev is not None and ev.after["hard_score"] < 100 and ev.after["broken"][0]["rule"] == "tags"
    # ---- undo: the break is gone, the score comes back (the override no longer counts)
    r = await c.post(f"/api/v1/runs/{did}/assignments/restore", json=undo, headers=admin)
    assert r.status_code == 200, r.text
    back = (await c.get(f"/api/v1/runs/{did}", headers=planner)).json()
    assert back["hard_score"] == 100 and back["stats"]["integrity"]["broken"] == []
    assert back["stats"]["forced_overrides"][0]["undone_at"]
    # ---- a planner moving its own LOCKED class to a free, fitting room re-decides the lock: "uygun", hard 100,
    # listed as a manual edit (never a silent drop to 99)
    other = await _free(bahar, rid, a, tip=False)
    body = {"day": SATURDAY, "room_ids": [other], "scope": "week", "week": 3}
    pre = (await c.post(f"/api/v1/runs/{rid}/assignments/{a.id}/move-preview", json=body, headers=planner)).json()
    assert pre["items"][0]["ok"], pre["items"][0]
    r = await c.post(
        f"/api/v1/runs/{rid}/assignments/bulk-move", json={"moves": [{"aid": a.id, **body}]}, headers=planner
    )
    assert r.status_code == 200 and r.json()["applied"] is True, r.text
    moved = (await c.get(f"/api/v1/runs/{rid}", headers=planner)).json()
    assert moved["hard_score"] == 100 and moved["stats"]["truth"]["broken"] == []
    assert "manual" in {x["cause"] for x in moved["stats"]["truth"]["exceptions"]}


async def test_move_check_falls_back_on_the_scoring_rules(bahar, monkeypatch):
    """Even if the cell check missed a rule (here: it says nothing at all), the planner-level evaluation the score
    uses refuses the TIP room: the two can never disagree again."""
    from app.services import calendar_views as cv

    c, planner = bahar.client, bahar.planner
    run = await _week3_run(bahar)
    rid = run["id"]
    a = await _phar(rid)
    tip = await _free(bahar, rid, a, tip=True)
    monkeypatch.setattr(cv, "check_candidate", lambda ctx, cand, others=None: ([], []))
    body = {"day": SATURDAY, "room_ids": [tip], "scope": "week", "week": 3}
    pre = (await c.post(f"/api/v1/runs/{rid}/assignments/{a.id}/move-preview", json=body, headers=planner)).json()
    item = pre["items"][0]
    assert not item["ok"] and [i["code"] for i in item["hard"]] == ["planner:tags"], item
    assert "TIP" in item["hard"][0]["text"]["en"] and "Kesin kural bozulur" in item["hard"][0]["text"]["tr"]


async def test_publishing_a_run_with_a_forced_break_needs_the_confirm(bahar):
    c, planner, admin = bahar.client, bahar.planner, bahar.admin
    run = await _week3_run(bahar)
    rid = run["id"]
    a = await _phar(rid)
    tip = await _free(bahar, rid, a, tip=True)
    move = {"moves": [{"aid": a.id, "day": SATURDAY, "room_ids": [tip], "scope": "week", "week": 3}], "force": True}
    r = await c.post(
        f"/api/v1/runs/{rid}/assignments/bulk-move", json={**move, "reason": "Sınav provası"}, headers=admin
    )
    assert r.status_code == 200 and r.json()["applied"], r.text
    r = await c.post(f"/api/v1/runs/{rid}/activate", json={"confirm_scope_reduction": True}, headers=planner)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "forced_breaks" and [b["rule"] for b in d["breaks"]] == ["tags"]
    assert d["breaks"][0]["reason"] == "Sınav provası" and "onaylayın" in d["message_tr"]
    r = await c.post(
        f"/api/v1/runs/{rid}/activate",
        json={"confirm_scope_reduction": True, "confirm_forced_breaks": True},
        headers=planner,
    )
    assert r.status_code == 200, r.text


async def test_assignment_flags_match_the_planner_level_check(bahar):
    """R1-S-17 / R1-M-04: the assignments API says which rows are the planner's own locks, never calls two requests
    of one joint lecture a room clash, never calls a room without a known capacity "over capacity", and marks the
    conflict reasons that are accepted exceptions (so the grid and the verdict count the same things)."""
    from app.models import MeetingRequest

    c, planner = bahar.client, bahar.planner
    run = await _week3_run(bahar)
    rid = run["id"]
    rows = (await c.get(f"/api/v1/runs/{rid}/assignments", headers=planner)).json()
    assert rows
    head_of = {int(m): int(h) for h, ms in (run["stats"].get("event_members") or {}).items() for m in ms}
    by_id = {a["id"]: a for a in rows}
    async with dbmod.get_session_factory()() as s:
        mrs = {
            m.id: m
            for m in (
                await s.execute(
                    select(MeetingRequest).where(MeetingRequest.id.in_([a["meeting_request_id"] for a in rows]))
                )
            ).scalars()
        }
    locked_rows = 0
    for a in rows:
        mr = mrs.get(a["meeting_request_id"])
        own = bool(mr and mr.status == "LOCKED" and mr.definitive_room_ids) and sorted(a["room_ids"]) == sorted(
            mr.definitive_room_ids or []
        )
        assert a["planner_lock"] == own, (a["display_label"], a["room_codes"])
        locked_rows += own
        assert not any(r.endswith("> 0") for r in a["conflict_reasons"]), a["conflict_reasons"]
        assert set(a["exception_reasons"]) <= set(a["conflict_reasons"])
        for r in a["conflict_reasons"]:
            if r.startswith("room overlap") and "#" in r:
                other = by_id.get(int(r.rsplit("#", 1)[1]))
                if other is not None:
                    ha = head_of.get(a["meeting_request_id"], a["meeting_request_id"])
                    hb = head_of.get(other["meeting_request_id"], other["meeting_request_id"])
                    assert ha != hb, ("one joint lecture flagged as a clash", a["display_label"])
    assert locked_rows > 100  # the Bahar list locks most of its rows to their definitive rooms
