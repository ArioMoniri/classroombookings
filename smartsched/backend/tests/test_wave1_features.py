"""P10 typed room features on the real Bahar 2026 import (``tests/crbs_env``). Fixture facts used:

* the weekly grid tags A 103, A 104, A 105, B 207 and C 202 ``PC`` (B BİLGİ LAB bucket) and A 201-A 203 ``TIP``;
* A 101 has 58 seats and no tag; B 201 has 30 seats;
* the planning list asks for computer labs ("Bilg. Lab. Zorunlu") on real meeting requests (``requested_tags``).
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import Room, ScheduleRun
from app.services.solver_bridge import build_solver_input
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.crbs_support import role_id

FEAT = "/api/v1/room-admin/features"


async def _room_tags(code: str) -> list[str]:
    async with dbmod.get_session_factory()() as s:
        room = (await s.execute(select(Room).where(Room.code == code))).scalar_one()
        return list(room.tags or [])


async def test_adopt_tags_turns_the_imported_tags_into_typed_features(env):  # noqa: F811
    c = env.client
    assert (await c.get(FEAT, headers=env.admin)).json() == []  # no seed data
    r = await c.post(f"{FEAT}/adopt-tags", headers=env.admin)
    assert r.status_code == 200, r.text
    made = {f["solver_tag"]: f for f in r.json()}
    assert set(made) == {"PC", "TIP"}
    assert made["PC"]["name"] == "Bilgisayar laboratuvarı" and made["PC"]["kind"] == "BOOLEAN"
    assert made["TIP"]["name"] == "Tıp Fakültesi dersliği"
    # idempotent: nothing new the second time
    assert (await c.post(f"{FEAT}/adopt-tags", headers=env.admin)).json() == []
    a103 = (await c.get(f"/api/v1/room-admin/rooms/{env.rooms['A103']}/features", headers=env.admin)).json()
    a101 = (await c.get(f"/api/v1/room-admin/rooms/{env.rooms['A101']}/features", headers=env.admin)).json()
    assert a103["values"][str(made["PC"]["id"])] is True and a103["display"]["Bilgisayar laboratuvarı"] is True
    assert a101["values"][str(made["PC"]["id"])] is False
    # the room info popup shows the typed value
    info = (await c.get(f"/api/v1/bookings/rooms/{env.rooms['A201']}", headers=env.admin)).json()
    assert {"name": "Tıp Fakültesi dersliği", "value": True} in [
        {"name": f["name"], "value": f["value"]} for f in info["fields"]
    ]
    # the template is offered, never seeded; only on request
    r = await c.post(f"{FEAT}/template", headers=env.admin)
    assert [f["name"] for f in r.json()][:3] == ["Projeksiyon", "Akıllı tahta", "PC sayısı"]


async def test_tag_mirror_adds_and_removes_only_its_tag_and_the_solver_sees_it(env):  # noqa: F811
    c = env.client
    pc = next(f for f in (await c.post(f"{FEAT}/adopt-tags", headers=env.admin)).json() if f["solver_tag"] == "PC")
    # a manual tag on A 101 (set through the room master API) must survive the feature writes
    r = await c.put(f"/api/v1/rooms/{env.rooms['A101']}", json={"tags": ["LAB"]}, headers=env.planner)
    assert r.status_code == 200, r.text
    url = f"/api/v1/room-admin/rooms/{env.rooms['A101']}/features"
    r = await c.put(url, json={str(pc["id"]): "evet"}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["LAB", "PC"]
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, env.run_id)
        inp, _ = await build_solver_input(s, run)
    a101 = next(room for room in inp.rooms if room.code == "A101")
    assert a101.tags == frozenset({"LAB", "PC"})  # frozen solver contract: Room.tags
    r = await c.put(url, json={"Bilgisayar laboratuvarı": "Hayır"}, headers=env.admin)  # by name, Turkish yes/no
    assert r.json()["tags"] == ["LAB"]
    # A 201 keeps TIP when PC is switched on and off
    url201 = f"/api/v1/room-admin/rooms/{env.rooms['A201']}/features"
    await c.put(url201, json={str(pc["id"]): True}, headers=env.admin)
    assert await _room_tags("A201") == ["TIP", "PC"]
    await c.put(url201, json={str(pc["id"]): False}, headers=env.admin)
    assert await _room_tags("A201") == ["TIP"]


async def test_number_and_select_values_with_turkish_input(env):  # noqa: F811
    c = env.client
    r = await c.post(
        FEAT, json={"name": "PC sayısı", "type": "NUMBER", "unit": "adet", "category": "lab"}, headers=env.admin
    )
    assert r.status_code == 201, r.text
    n_id = r.json()["id"]
    r = await c.post(
        FEAT,
        json={"name": "Oturma düzeni", "type": "SELECT", "options": ["Amfi", "Sınıf düzeni", "U düzeni"]},
        headers=env.admin,
    )
    sel = r.json()
    url = f"/api/v1/room-admin/rooms/{env.rooms['A103']}/features"
    r = await c.put(url, json={str(n_id): "47\xa0", "Oturma düzeni": "SINIF DÜZENİ"}, headers=env.admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["values"][str(n_id)] == 47.0 and body["display"]["Oturma düzeni"] == "Sınıf düzeni"
    bad = await c.put(url, json={str(n_id): "-3"}, headers=env.admin)
    assert bad.status_code == 422 and "negative" in bad.json()["detail"]["message"]
    bad = await c.put(url, json={str(sel["id"]): "Çember"}, headers=env.admin)
    assert bad.status_code == 422
    # a duplicate name (Turkish case-insensitive) is refused
    dup = await c.post(FEAT, json={"name": "OTURMA DÜZENİ", "type": "TEXT"}, headers=env.admin)
    assert dup.status_code == 409
    # the custom-fields mirror for the AI layer / room UI
    async with dbmod.get_session_factory()() as s:
        room = await s.get(Room, env.rooms["A103"])
        assert room.custom_fields["PC sayısı"] == 47.0 and room.custom_fields["Oturma düzeni"] == "Sınıf düzeni"
    # a teacher may not manage features
    _, teacher = await env.user("ogretmen@uni.edu.tr")
    assert (await c.post(FEAT, json={"name": "Mikrofon", "type": "BOOLEAN"}, headers=teacher)).status_code == 403


async def test_facet_counts_follow_room_acl_visibility(env):  # noqa: F811
    c = env.client
    await c.post(f"{FEAT}/adopt-tags", headers=env.admin)
    admin_facets = {f["solver_tag"]: f for f in (await c.get("/api/v1/rooms/facets", headers=env.admin)).json()}
    assert admin_facets["PC"]["counts"]["true"] == 3  # A 103, A 104, A 105 (B 207 and C 202 are not bookable)
    # a custom role without room.view sees only the room its ACL entry opens
    r = await c.post("/api/v1/roles", json={"name": "Lab görevlisi", "permissions": []}, headers=env.admin)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    r = await c.post(
        "/api/v1/room-admin/acl",
        json={
            "entity_type": "room",
            "entity_id": env.rooms["A104"],
            "context_type": "role",
            "context_id": rid,
            "permissions": ["room.view"],
        },
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    _, lab = await env.user("lab@uni.edu.tr", role_id=rid)
    facets = {f["solver_tag"]: f for f in (await c.get("/api/v1/rooms/facets", headers=lab)).json()}
    assert facets["PC"]["counts"] == {"true": 1}
    assert facets["TIP"]["counts"] == {"false": 1}
    assert await role_id(c, env.admin, "TEACHER")  # roles are intact


async def test_bulk_csv_cp1254_semicolon_with_bad_cells(env):  # noqa: F811
    c = env.client
    await c.post(FEAT, json={"name": "Projeksiyon", "type": "BOOLEAN"}, headers=env.admin)
    await c.post(FEAT, json={"name": "PC sayısı", "type": "NUMBER", "unit": "adet"}, headers=env.admin)
    text = "Derslik;Projeksiyon;PC sayısı;Renk\nA 101;Evet;0;mavi\nA 103;var;47;\nA 999;evet;;\nB 201;belki;-3;\n"
    files = {"file": ("ozellikler.csv", text.encode("cp1254"), "text/csv")}
    r = await c.post(f"{FEAT}/bulk-values", files=files, headers=env.admin)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["dry_run"] and rep["errors"] == 3 and rep["unknown_columns"] == ["Renk"]
    msgs = [x.get("message", "") for x in rep["report"] if x["status"] == "error"]
    assert any("room not found" in m for m in msgs) and any("yes/no" in m for m in msgs)
    assert any("negative" in m for m in msgs)
    r = await c.post(f"{FEAT}/bulk-values?dry_run=false", files=files, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bulk_errors"
    r = await c.post(f"{FEAT}/bulk-values?dry_run=false&skip_errors=true", files=files, headers=env.admin)
    assert r.status_code == 200 and r.json()["applied"] == 4
    a103 = (await c.get(f"/api/v1/room-admin/rooms/{env.rooms['A103']}/features", headers=env.admin)).json()
    assert a103["display"]["Projeksiyon"] is True and a103["display"]["PC sayısı"] == 47.0


async def test_removing_a_solver_tag_feature_shows_its_impact_first(env):  # noqa: F811
    c = env.client
    pc = next(f for f in (await c.post(f"{FEAT}/adopt-tags", headers=env.admin)).json() if f["solver_tag"] == "PC")
    imp = (await c.get(f"{FEAT}/{pc['id']}/impact", headers=env.admin)).json()
    assert imp["room_count"] == 5 and imp["requests_needing"] > 0
    assert "A 103" in imp["rooms"] and "kaldırılır" in imp["message_tr"]
    r = await c.delete(f"{FEAT}/{pc['id']}", headers=env.admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "solver_tag_impact"
    assert await _room_tags("A103") == ["PC"]
    r = await c.delete(f"{FEAT}/{pc['id']}?confirm=true", headers=env.admin)
    assert r.status_code == 200 and r.json()["impact"]["room_count"] == 5
    assert await _room_tags("A103") == []
