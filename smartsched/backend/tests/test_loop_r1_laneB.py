"""Flow loop round 1, lane B (docs/ROADMAP.md "Flow loop tickets — round 1", ``rounds/round-1-tickets.json``):
approval-first wording, bookings, find-room, approvals and Taleplerim, on the real Bahar 2026 import
(``tests/crbs_env``: clock Monday 16 Feb 2026 08:00; A 102 is free at P1 every Thursday).
"""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401

THU = date(2026, 2, 19)
POL = "/api/v1/booking-policies"
APPR = "/api/v1/approvals"


async def _mode(env, mode: str) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.put("/api/v1/org/settings", json={"approval_mode": mode}, headers=env.admin)
    assert r.status_code == 200, r.text


async def _people(env):  # type: ignore[no-untyped-def]  # noqa: F811
    gid, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr",
        role="ADMIN",
        firstname="Gözde",
        lastname="Ayrancıgil",
        approves_for=[{"type": "all"}],
    )
    aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    return gid, gozde, aid, ayse


async def _effective(env, headers, room: str = "A102", day: date = THU, period: str = "P1"):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(
        f"{POL}/effective",
        params={"room_id": env.rooms[room], "date": day.isoformat(), "period_id": env.periods[period]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------------------------------
# T-R1-10: with approval-first on, the "Neden?" verdict says "request", never "book"
# --------------------------------------------------------------------------------------------------


async def test_t_r1_10_effective_says_request_under_approval_first(env):  # noqa: F811
    _, gozde, _, ayse = await _people(env)
    # rules mode (default), no policy: a teacher books directly
    eff = await _effective(env, ayse)
    assert eff["verdict"] == "book" and eff["violations"] == []
    assert eff["approval"] == {
        "mode": "rules",
        "first": False,
        "action": "book",
        "source": None,
        "message_tr": "",
        "message_en": "",
    }
    await _mode(env, "all")
    eff = await _effective(env, ayse)
    assert eff["verdict"] == "request"
    assert eff["approval"]["first"] is True and eff["approval"]["source"] == "approval_mode"
    (v,) = eff["violations"]
    assert v["rule"] == "approval_mode" and v["effect"] == "request"
    assert "Onaylayıcılara gider" in v["message_tr"] and "Her talep önce onaya" in v["message_tr"]
    assert "approvers" in v["message_en"] and "Onay" not in v["message_en"]
    # the room-level call (no date/period: the grid asks once) carries the same fact
    r = await env.client.get(
        f"{POL}/effective", params={"room_id": env.rooms["A102"], "term_id": env.term_id}, headers=ayse
    )
    assert r.status_code == 200 and r.json()["approval"]["first"] is True and "verdict" not in r.json()
    # the sheet's own check agrees (one decision, two endpoints)
    check = (await env.client.get(f"{APPR}/rooms/{env.rooms['A102']}/check", headers=ayse)).json()
    assert check["action"] == "request"
    # approvers and planning administrators still book directly: their verdict stays "book"
    for who in (gozde, env.admin):
        eff = await _effective(env, who)
        assert eff["verdict"] == "book" and eff["approval"]["first"] is False, eff


async def test_t_r1_10_approval_rule_room_says_request_in_rules_mode(env):  # noqa: F811
    _, _, _, ayse = await _people(env)
    r = await env.client.post(
        "/api/v1/approval-rules", json={"entity_type": "room", "entity_id": env.rooms["A102"]}, headers=env.admin
    )
    assert r.status_code == 201, r.text
    eff = await _effective(env, ayse)
    assert eff["verdict"] == "request" and eff["approval"]["source"] == "approval_rule"
    assert eff["approval"]["first"] is False
    assert eff["violations"][-1]["rule"] == "approval_rule" and "A 102" in eff["violations"][-1]["message_tr"]


# --------------------------------------------------------------------------------------------------
# T-R1-13: a two-period submission is one conflict row whose options keep the periods together
# --------------------------------------------------------------------------------------------------


async def _two_period_class(run_id: int) -> tuple[int, date, int]:
    """(room id, date, first period) of a board class over at least two periods in one room (Bahar weeks 3-6)."""
    from app.core import db as dbmod
    from app.models import Assignment
    from sqlalchemy import select

    async with dbmod.get_session_factory()() as s:
        rows = (
            await s.execute(
                select(Assignment)
                .where(Assignment.run_id == run_id, Assignment.date.between(date(2026, 2, 17), date(2026, 3, 13)))
                .order_by(Assignment.date, Assignment.start_period, Assignment.id)
            )
        ).scalars()
        for a in rows:
            if len(a.room_ids or []) == 1 and a.end_period > a.start_period and 2 <= a.start_period <= 15:
                return int(a.room_ids[0]), a.date, a.start_period
    raise AssertionError("no two-period class on the board")


async def test_t_r1_13_a_two_period_submission_is_one_conflict_with_options_that_keep_it_together(env):  # noqa: F811
    from app.core import db as dbmod
    from app.models import Booking, ScheduleRun
    from sqlalchemy import select, update

    c = env.client
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    async with dbmod.get_session_factory()() as s:  # the board is not published yet when she books
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
    assert r.status_code in (200, 201, 202), r.text
    r = await c.post(f"/api/v1/runs/{env.run_id}/activate", headers=env.planner)
    assert r.status_code == 200, r.text
    plan = (await c.get(f"/api/v1/bookings/conflicts/{env.run_id}/plan", headers=env.planner)).json()
    mine = [g for g in plan["groups"] if g["room_id"] == rid and g["conflicts"][0]["date"] == day.isoformat()]
    (g,) = mine  # one row for the submission, not one per period
    assert g["kind"] == "submission" and g["key"].startswith("multi:")
    assert sorted(x["start_period"] for x in g["conflicts"]) == [p, p + 1]
    moves = [o for o in g["options"] if o["kind"].startswith("move_")]
    assert moves, g["options"]
    for o in moves:  # every move keeps both periods: the option spans P..P+1 (or that span shifted)
        assert o["end_period"] - o["start_period"] == 1, o
    # the bookings carry no headcount: no sentence invents one
    assert not any("kişi için" in o["reason"]["tr"] for o in g["options"] if o.get("reason"))
    # applying the group's option to its conflicts moves both periods together
    o = next(x for x in moves if x["kind"] in ("move_room", "move_period"))
    items = [
        {"conflict_id": x["conflict_id"], "action": o["kind"], "option_id": o["id"], "scope": "one"}
        for x in g["conflicts"]
    ]
    r = await c.post(f"/api/v1/bookings/conflicts/{env.run_id}/apply", json={"items": items}, headers=env.planner)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        rows = list((await s.execute(select(Booking).where(Booking.multi_booking_id == mb["id"]))).scalars())
    assert {b.room_id for b in rows} == {o["room_id"]}
    spans = sorted((b.start_period, b.end_period) for b in rows)
    assert spans[0][0] == o["start_period"] and spans[-1][1] == o["end_period"] and len(spans) == 2


# --------------------------------------------------------------------------------------------------
# T-R1-14: find-room marks the caller's own open request; alternatives say the shift in words
# --------------------------------------------------------------------------------------------------


async def test_t_r1_14_own_pending_request_reads_talebiniz_bekliyor_and_shifts_are_words(env):  # noqa: F811
    c = env.client
    _, _, _, ayse = await _people(env)
    await _mode(env, "all")
    r = await env.book(ayse, "A102", THU, "P1", notes="FZT 132 telafi")
    assert r.status_code == 202, r.text
    body = {"date": THU.isoformat(), "start": 1, "end": 1, "text": "A 102"}
    res = (await c.post("/api/v1/rooms/find", json=body, headers=ayse)).json()
    (row,) = [x for x in res["results"] if x["code"] == "A102"]
    assert row["status"] == "mine_pending" and row["action"] == "none"
    assert row["reason"]["tr"].startswith("Talebiniz bekliyor")
    # her own request is not offered back to her as a free alternative at the same time
    assert not any(a["room_id"] == env.rooms["A102"] and a["start_period"] == 1 for a in res["alternatives"])
    # somebody else sees the slot as held (the request holds it only for its requester and the approvers)
    _, mehmet = await env.user("mehmet.oz@uni.edu.tr")
    other = (await c.post("/api/v1/rooms/find", json=body, headers=mehmet)).json()
    assert all(x["status"] != "mine_pending" for x in other["results"])
    # a time alternative says how it differs, in words
    time_alts = [a for a in res["alternatives"] if a["kind"] == "time"]
    assert time_alts, res["alternatives"]
    assert all(
        ("ders saati geç başlar" in a["reason"]["tr"] or "ders saati erken başlar" in a["reason"]["tr"])
        for a in time_alts
    )
    assert all(
        "period" in a["reason"]["en"] and ("later" in a["reason"]["en"] or "earlier" in a["reason"]["en"])
        for a in time_alts
    )
