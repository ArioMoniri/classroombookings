"""Flow loop round 2, lane B (docs/ROADMAP.md "Flow loop tickets — round 2", ``rounds/round-2-tickets.json``):
bookings, find-room, approvals and My bookings on the real Bahar 2026 import (``tests/crbs_env``).
"""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401
from tests.test_loop_r1_laneB import _mode, _people, _two_period_class

THU = date(2026, 2, 19)


# --------------------------------------------------------------------------------------------------
# T-R2-13: a two-period request is one conflict row too; the My bookings totals count on one basis
# --------------------------------------------------------------------------------------------------


async def test_t_r2_13_a_two_period_request_is_one_conflict_row(env):  # noqa: F811
    from app.core import db as dbmod
    from app.models import ScheduleRun
    from sqlalchemy import update

    c = env.client
    _, _, _, ayse = await _people(env)
    await _mode(env, "all")
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(ScheduleRun).where(ScheduleRun.id == env.run_id).values(is_active=False))
        await s.commit()
    rid, day, p = await _two_period_class(env.run_id)
    slots = [{"date": day.isoformat(), "period_id": env.periods[f"P{q}"], "room_id": rid} for q in (p, p + 1)]
    mb = (await c.post("/api/v1/bookings/multi", json={"slots": slots}, headers=ayse)).json()
    r = await c.post(
        f"/api/v1/bookings/multi/{mb['id']}/create",
        json={"type": "single", "slots": [{"mbs_id": x["mbs_id"]} for x in mb["slots"]], "confirm_unpublished": True},
        headers=ayse,
    )
    assert r.status_code == 202, r.text  # T-R2-17 (c): a request answers 202 like POST /bookings
    assert all(b["status"] == "PENDING" for b in r.json()["created"])
    r = await c.post(f"/api/v1/runs/{env.run_id}/activate", headers=env.planner)
    assert r.status_code == 200, r.text
    plan = (await c.get(f"/api/v1/bookings/conflicts/{env.run_id}/plan", headers=env.planner)).json()
    mine = [g for g in plan["groups"] if g["room_id"] == rid and g["conflicts"][0]["date"] == day.isoformat()]
    (g,) = mine  # one row for the request, not one per period
    assert g["kind"] == "submission" and g["requested"] is True and g["key"].startswith("multi:")
    assert sorted(x["start_period"] for x in g["conflicts"]) == [p, p + 1]


async def test_t_r2_13_two_requests_sent_one_by_one_for_adjacent_periods_are_one_conflict_row(env):  # noqa: F811
    from app.core import db as dbmod
    from app.models import ScheduleRun
    from sqlalchemy import update

    c = env.client
    _, _, _, ayse = await _people(env)
    await _mode(env, "all")
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(ScheduleRun).where(ScheduleRun.id == env.run_id).values(is_active=False))
        await s.commit()
    rid, day, p = await _two_period_class(env.run_id)
    for q in (p, p + 1):  # the admin's round-2 run: two POST /bookings, no multi-booking
        r = await c.post(
            "/api/v1/bookings",
            json={"room_id": rid, "date": day.isoformat(), "period_id": env.periods[f"P{q}"], "confirm_unpublished": True},
            headers=ayse,
        )
        assert r.status_code == 202, r.text
    r = await c.post(f"/api/v1/runs/{env.run_id}/activate", headers=env.planner)
    assert r.status_code == 200, r.text
    plan = (await c.get(f"/api/v1/bookings/conflicts/{env.run_id}/plan", headers=env.planner)).json()
    mine = [g for g in plan["groups"] if g["room_id"] == rid and g["conflicts"][0]["date"] == day.isoformat()]
    (g,) = mine
    assert g["kind"] == "submission" and g["requested"] is True and g["key"].startswith("adjacent:")
    assert sorted(x["start_period"] for x in g["conflicts"]) == [p, p + 1]
    moves = [o for o in g["options"] if o["kind"].startswith("move_")]
    assert moves and all(o["end_period"] - o["start_period"] == 1 for o in moves), g["options"]


async def test_t_r2_13_totals_count_sessions_and_leave_the_cancelled_out(env):  # noqa: F811
    c = env.client
    _, _, _, ayse = await _people(env)
    a102 = env.rooms["A102"]
    # four free single-bookable periods of A 102 on a Thursday after the published weeks (the grid knows)
    day = date(2026, 5, 7)
    grid = (await c.get("/api/v1/bookings/grid", params={"display": "day", "date": day.isoformat()}, headers=ayse)).json()
    order = {p["id"]: p["start_period"] for p in grid["periods"]}
    free = sorted(
        (s for s in grid["slots"] if s["room_id"] == a102 and s["status"] == "available" and s.get("allow_single")),
        key=lambda s: order[s["period_id"]],
    )
    assert len(free) >= 4, free
    pids = [s["period_id"] for s in free[:4]]
    # one two-period submission (one session), one single booking, one cancelled booking
    slots = [{"date": day.isoformat(), "period_id": pid, "room_id": a102} for pid in pids[:2]]
    mb = (await c.post("/api/v1/bookings/multi", json={"slots": slots}, headers=ayse)).json()
    r = await c.post(
        f"/api/v1/bookings/multi/{mb['id']}/create",
        json={"type": "single", "slots": [{"mbs_id": x["mbs_id"]} for x in mb["slots"]]},
        headers=ayse,
    )
    assert r.status_code in (200, 201), r.text
    single = await c.post(
        "/api/v1/bookings", json={"room_id": a102, "date": day.isoformat(), "period_id": pids[2]}, headers=ayse
    )
    assert single.status_code == 201, single.text
    gone = await c.post(
        "/api/v1/bookings", json={"room_id": a102, "date": day.isoformat(), "period_id": pids[3]}, headers=ayse
    )
    assert gone.status_code == 201, gone.text
    r = await c.post(f"/api/v1/bookings/{gone.json()['id']}/cancel", json={}, headers=ayse)
    assert r.status_code in (200, 204), r.text
    dash = (await c.get("/api/v1/bookings/dashboard", headers=ayse)).json()
    totals = dash["totals"]
    # sessions: the P1-P2 submission + P3 = 2; the cancelled P4 is out of every number
    assert totals["active"] == 2 and totals["active_periods"] == 3, totals
    assert totals["session"] == 2 and totals["all"] == 2, totals
    assert totals["session_periods"] == 3 and totals["all_periods"] == 3, totals
    assert totals["cancelled"] == 1, totals
    mine = (await c.get("/api/v1/bookings/mine", headers=ayse)).json()
    assert len({(b["group_id"], b["date"], b["room_id"]) if b.get("group_id") else b["id"] for b in mine}) == 2
