"""M-34 (F-01 S10): a request withdrawn by its requester leaves the approver's open box and shows in their
"decided" box (and in ``status=all``) as WITHDRAWN, so the approver who was asked sees what became of it. Other
approvers who were never asked do not see it; the requester's own list is unchanged.

Real Bahar 2026 data (``tests/crbs_env``; clock Monday 16 Feb 2026 08:00): A 102 is free at P1 every Thursday.
"""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401

THU = date(2026, 2, 19)
APPR = "/api/v1/approvals"


async def test_withdrawn_request_moves_to_the_approvers_decided_box(env):  # noqa: F811
    c = env.client
    r = await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)
    assert r.status_code == 200, r.text
    _gid, gozde = await env.user(
        "gozde.ayrancigil@uni.edu.tr",
        role="ADMIN",
        firstname="Gözde",
        lastname="Ayrancıgil",
        approves_for=[{"type": "all"}],
    )
    _aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    r = await env.book(ayse, "A102", THU, "P1", notes="FZT 132 telafi dersi")
    assert r.status_code == 202, r.text
    (req,) = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    rid = req["id"]

    opened = (await c.get(f"{APPR}/inbox", params={"status": "open"}, headers=gozde)).json()
    assert [x["id"] for x in opened] == [rid]
    assert (await c.post(f"{APPR}/{rid}/withdraw", headers=ayse)).status_code == 200

    assert (await c.get(f"{APPR}/inbox", params={"status": "open"}, headers=gozde)).json() == []
    decided = (await c.get(f"{APPR}/inbox", params={"status": "decided"}, headers=gozde)).json()
    assert [(x["id"], x["status"]) for x in decided] == [(rid, "WITHDRAWN")]
    every = (await c.get(f"{APPR}/inbox", params={"status": "all"}, headers=gozde)).json()
    assert [x["id"] for x in every] == [rid]
    grouped = (await c.get(f"{APPR}/inbox", params={"status": "decided", "grouped": True}, headers=gozde)).json()
    assert [e["status"] for e in grouped] == ["WITHDRAWN"]


async def test_withdrawn_request_is_not_shown_to_an_approver_who_was_not_asked(env):  # noqa: F811
    c = env.client
    await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=env.admin)
    await env.user("gozde.ayrancigil@uni.edu.tr", role="ADMIN", approves_for=[{"type": "all"}])
    # an approver whose scope does not cover A 102 (a room type the room does not have)
    _oid, other = await env.user("onur.kaya@uni.edu.tr", role="ADMIN", approves_for=[{"type": "tag", "tag": "AMPHI"}])
    _aid, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    r = await env.book(ayse, "A102", THU, "P1")
    assert r.status_code == 202, r.text
    (req,) = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    assert (await c.post(f"{APPR}/{req['id']}/withdraw", headers=ayse)).status_code == 200
    assert (await c.get(f"{APPR}/inbox", params={"status": "decided"}, headers=other)).json() == []
    mine = (await c.get(f"{APPR}/mine", headers=ayse)).json()
    assert [(x["id"], x["status"]) for x in mine] == [(req["id"], "WITHDRAWN")]
