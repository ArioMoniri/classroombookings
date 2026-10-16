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
