"""Persona test 2026-10-15 A-11 (docs/testing/2026-10-15-persona-academician.md): ``GET /rooms/facets`` returned
``[]`` for teacher and admin although PC labs exist (the room tags of an import were never turned into typed
features, P10), and typing "PC" in find-a-room listed the PC labs with "PC özellikli oda; istenmedi, sona alındı".

The solver tags on rooms now show up as yes/no features with Turkish names (created on first use, attributed to the
system), and a text that names a tag ("PC", "bilgisayar lab") counts as asking for it.

Real Bahar 2026 data (``tests/crbs_env``): A 103, A 104, A 105 and B 207 are the computer labs (tag PC).
"""

from __future__ import annotations

from datetime import date

from app.api.v1 import find_room as find_api
from app.core import db as dbmod
from app.models import AuditEvent
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

WED = date(2026, 2, 18)
FIND = "/api/v1/rooms/find"
PC_LABS = {"A103", "A104", "A105", "B207"}


async def _bookable_pc_rooms() -> int:
    from app.models import Room

    async with dbmod.get_session_factory()() as s:
        rooms = (await s.execute(select(Room).where(Room.is_bookable.is_(True)))).scalars()
        n = sum(1 for r in rooms if "PC" in (r.tags or []))
    assert 3 <= n <= len(PC_LABS)
    return n


async def test_room_tags_are_facets_for_everyone(env):  # noqa: F811
    _, teacher = await env.user("akademisyen.fasetler@uni.edu.tr")
    for headers in (teacher, env.admin):
        r = await env.client.get("/api/v1/rooms/facets", headers=headers)
        assert r.status_code == 200, r.text
        pc = next(f for f in r.json() if f["solver_tag"] == "PC")
        assert pc["name"] == "Bilgisayar laboratuvarı" and pc["kind"] == "BOOLEAN" and pc["public"] is True
        assert pc["counts"]["true"] == await _bookable_pc_rooms()
        assert any(f["solver_tag"] == "TIP" for f in r.json())
    async with dbmod.get_session_factory()() as s:
        made = list((await s.execute(select(AuditEvent).where(AuditEvent.action == "room_field.create"))).scalars())
    assert made and all(e.actor_type == "system" for e in made)  # not the teacher who happened to look


async def test_text_pc_and_the_pc_facet_ask_for_computer_labs(env):  # noqa: F811
    find_api.FIND_LIMIT.reset()
    _, teacher = await env.user("akademisyen.pc@uni.edu.tr")
    body = {"date": WED.isoformat(), "start": "16:50", "end": "18:40", "headcount": 42}
    out = (await env.client.post(FIND, json={**body, "text": "PC"}, headers=teacher)).json()
    codes = {x["code"] for x in out["results"]}
    assert codes and codes <= PC_LABS, codes
    for x in out["results"]:
        assert not any("istenmedi" in rsn["tr"] for rsn in x["reasons"]), x
    pc = next(
        f for f in (await env.client.get("/api/v1/rooms/facets", headers=teacher)).json() if f["solver_tag"] == "PC"
    )
    out = (
        await env.client.post(FIND, json={**body, "features": [{"field": pc["id"], "value": True}]}, headers=teacher)
    ).json()
    offered = [x for x in out["results"] if x["status"] in ("free", "partial")]
    assert offered and {x["code"] for x in offered} <= PC_LABS
