"""Security follow-ups of the CRBS superset gate (2026-10-08): room / room-group ACL rows die with their entity,
holiday names are NBSP-cleaned on edit, Turkish alphabetical order for the department, room-group and room lists.

Real data: the Bahar 2026 import (``tests/crbs_env``: published weekly grid, the 18 university periods, term
2026-BAHAR, clock Monday 16 Feb 2026 08:00)."""

from __future__ import annotations

from app.core import db as dbmod
from app.models import RoomAcl, RoomGroup
from sqlalchemy import select, update

from tests.crbs_env import env  # noqa: F401  (fixture)


async def _guest(env, email: str) -> tuple[int, dict[str, str]]:  # type: ignore[no-untyped-def]
    """A user whose role holds no permission at all: every room they see comes from an ACL entry."""
    r = await env.client.post("/api/v1/roles", json={"name": f"Misafir {email[:6]}", "permissions": []}, headers=env.admin)
    assert r.status_code == 201, r.text
    return await env.user(email, role=None, role_id=r.json()["id"])


async def _new_room(env, code: str, name: str | None = None) -> int:  # type: ignore[no-untyped-def]
    body = {"code": code, "capacity": 40, **({"display_name": name} if name else {})}
    r = await env.client.post("/api/v1/rooms", json=body, headers=env.planner)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def test_room_acl_does_not_survive_its_room(env):
    """CRBS ``Rooms_model::delete`` removes the room's ACL. SQLite hands the highest deleted row id to the next
    room, so a leftover ``room_acl`` row would give the old room's permissions to an unrelated new room."""
    c = env.client
    uid, guest = await _guest(env, "acl.misafir@uni.edu.tr")
    old = await _new_room(env, "D 301", "Eski Çalışma Odası")
    r = await c.post(
        "/api/v1/room-admin/acl",
        json={"entity_type": "room", "entity_id": old, "context_type": "user", "context_id": uid,
              "permissions": ["room.view", "book_single.create"]},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    assert (await c.get(f"/api/v1/bookings/rooms/{old}", headers=guest)).status_code == 200
    assert (await c.delete(f"/api/v1/rooms/{old}", headers=env.planner)).status_code == 204
    left = (await c.get("/api/v1/room-admin/acl", params={"entity_type": "room", "entity_id": old}, headers=env.admin))
    assert left.json() == []
    new = await _new_room(env, "D 302", "Yeni İnceleme Odası")
    assert new == old  # the id is reused: exactly the case the leftover row would leak into
    assert (await c.get(f"/api/v1/bookings/rooms/{new}", headers=guest)).status_code == 404
    assert new not in {room["id"] for room in (await c.get("/api/v1/bookings/rooms", headers=guest)).json()}
    async with dbmod.get_session_factory()() as s:
        assert (await s.execute(select(RoomAcl).where(RoomAcl.entity_type == "room", RoomAcl.entity_id == new))).all() == []


async def test_room_group_acl_does_not_survive_its_group(env):
    """Same for room groups (``entity_type`` ``room_group``): a re-created group with the reused id starts clean."""
    c = env.client
    uid, guest = await _guest(env, "grup.misafir@uni.edu.tr")
    room = await _new_room(env, "D 303", "Şeref Salonu")
    g = (await c.post("/api/v1/room-admin/groups", json={"name": "Geçici Blok", "room_ids": [room]}, headers=env.admin))
    assert g.status_code == 201, g.text
    gid = g.json()["id"]
    r = await c.post(
        "/api/v1/room-admin/acl",
        json={"entity_type": "room_group", "entity_id": gid, "context_type": "user", "context_id": uid,
              "permissions": ["room.view"]},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    assert (await c.get(f"/api/v1/bookings/rooms/{room}", headers=guest)).status_code == 200
    assert (await c.delete(f"/api/v1/room-admin/groups/{gid}", headers=env.admin)).status_code == 204
    again = await c.post("/api/v1/room-admin/groups", json={"name": "Öğrenci Blok", "room_ids": [room]}, headers=env.admin)
    assert again.status_code == 201 and again.json()["id"] == gid
    assert (await c.get(f"/api/v1/bookings/rooms/{room}", headers=guest)).status_code == 404
    acl = await c.get("/api/v1/room-admin/acl", params={"entity_type": "room_group", "entity_id": gid}, headers=env.admin)
    assert acl.json() == []


async def test_holiday_name_is_cleaned_on_edit_like_on_create(env):
    """HolidayUpdate applies the HolidayIn normalisation: NBSP and runs of spaces collapse, blanks are refused."""
    c = env.client
    r = await c.post(
        "/api/v1/holidays",
        json={"term_id": env.term_id, "name": "Ulusal Egemenlik  ", "date_start": "2026-04-23", "date_end": "2026-04-23"},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    hid = r.json()["id"]
    assert r.json()["name"] == "Ulusal Egemenlik"
    r = await c.put(f"/api/v1/holidays/{hid}", json={"name": " 23 Nisan  Çocuk Bayramı\n"}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "23 Nisan Çocuk Bayramı"
    assert (await c.put(f"/api/v1/holidays/{hid}", json={"name": "  "}, headers=env.admin)).status_code == 422
    # dates alone keep the name
    r = await c.put(f"/api/v1/holidays/{hid}", json={"date_end": "2026-04-24"}, headers=env.admin)
    assert r.status_code == 200 and r.json()["name"] == "23 Nisan Çocuk Bayramı"


TR_DEPARTMENTS = ["Zooloji Deneme", "Çevre Deneme", "İngilizce Deneme", "Işık Deneme", "Dil Deneme",
                  "Ölçme Deneme", "Ürün Deneme", "Şehir Deneme", "Jeoloji Deneme", "Ilgaz Deneme"]
TR_DEPARTMENTS_SORTED = ["Çevre Deneme", "Dil Deneme", "Ilgaz Deneme", "Işık Deneme", "İngilizce Deneme",
                         "Jeoloji Deneme", "Ölçme Deneme", "Şehir Deneme", "Ürün Deneme", "Zooloji Deneme"]


async def test_department_list_is_in_turkish_alphabetical_order(env):
    """CRBS ``Departments_model::Get`` sorts by name (MySQL Unicode collation): Ç after C, İ after I/ı, Ö/Ş/Ü
    before the next Latin letter -- not after Z as a code-point sort does."""
    c = env.client
    for name in TR_DEPARTMENTS:
        assert (await c.post("/api/v1/departments", json={"name": name}, headers=env.admin)).status_code == 201
    got = [d["name"] for d in (await c.get("/api/v1/departments", params={"q": "DENEME"}, headers=env.admin)).json()]
    assert got == TR_DEPARTMENTS_SORTED
    # the whole list (the real Bahar programmes included) follows the same order
    from app.services.bookings_collation import tr_sort_key

    every = [d["name"] for d in (await c.get("/api/v1/departments", headers=env.admin)).json()]
    assert len(every) > len(TR_DEPARTMENTS) and every == sorted(every, key=tr_sort_key)


async def test_room_group_and_room_lists_are_in_turkish_alphabetical_order(env):
    """CRBS ``Room_groups_model`` (rg.pos, rg.name) and ``Rooms_model::get_all`` (rg.pos, rooms.pos, rooms.name):
    equal positions fall back to the Turkish alphabetical order of the names."""
    c = env.client
    rooms = {name: await _new_room(env, code, name) for code, name in
             (("D 311", "Zemin Salonu"), ("D 312", "Çatı Salonu"), ("D 313", "İç Avlu"), ("D 314", "Işıklı Oda"))}
    gids = []
    for name in ("Zemin Kat", "Ödev Blok", "Çarşı Blok", "İdari Blok"):
        r = await c.post("/api/v1/room-admin/groups", json={"name": name}, headers=env.admin)
        assert r.status_code == 201, r.text
        gids.append(r.json()["id"])
    r = await c.put(f"/api/v1/room-admin/groups/{gids[0]}", json={"room_ids": list(rooms.values())}, headers=env.admin)
    assert r.status_code == 200, r.text
    # CRBS imports often leave every position at 0 (older CRBS had no ordering)
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(RoomGroup).where(RoomGroup.id.in_(gids)).values(pos=0))
        await s.commit()
    groups = [g["name"] for g in (await c.get("/api/v1/room-admin/groups", headers=env.admin)).json() if g["id"] in gids]
    assert groups == ["Çarşı Blok", "İdari Blok", "Ödev Blok", "Zemin Kat"]
    expected = ["Çatı Salonu", "Işıklı Oda", "İç Avlu", "Zemin Salonu"]
    admin_rooms = (await c.get("/api/v1/room-admin/rooms", params={"room_group_id": gids[0]}, headers=env.admin)).json()
    assert [r["display_name"] for r in admin_rooms] == expected
    booking_rooms = (await c.get("/api/v1/bookings/rooms", params={"room_group_id": gids[0]}, headers=env.admin)).json()
    assert [r["name"] for r in booking_rooms] == expected
    member_ids = (await c.get("/api/v1/room-admin/groups", headers=env.admin)).json()
    assert next(g for g in member_ids if g["id"] == gids[0])["room_ids"] == [rooms[n] for n in expected]
    # the booking context lists its groups in the same order
    ctx = (await c.get("/api/v1/bookings/context", headers=env.admin)).json()
    assert [g["name"] for g in ctx["room_groups"] if g["id"] in gids] == ["Zemin Kat"]  # only groups with rooms
