"""UI gap audit 2026-10-08 (docs/review/2026-10-08-crbs-ui-gap-audit.md) backend support for the admin screens.

#4: a room administrator (``setup.rooms`` without planning rights) creates and deletes rooms from Admin -> Rooms
(CRBS ``setup/rooms/Rooms::add`` / ``delete``); a teacher cannot.
#3: Admin -> Sessions asks ``GET /terms/{id}/usage`` before deleting a term, because the delete takes the term's
bookings with it (CRBS ``session.delete.warning``).

Real fixture rows (Bahar 2026 weekly grid): A 101 Monday 16 Feb, P1 is free."""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)


async def _role(e, name: str, perms: list[str]) -> int:  # type: ignore[no-untyped-def]
    r = await e.client.post("/api/v1/roles", json={"name": name, "permissions": perms}, headers=e.admin)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def test_setup_rooms_may_create_and_delete_rooms(env):  # noqa: F811
    rid = await _role(env, "Derslik yöneticisi", ["setup.rooms"])
    _, clerk = await env.user("derslik.yonetici@uni.edu.tr", role=None, role_id=rid)
    c = env.client
    r = await c.post("/api/v1/rooms", json={"code": "Z 901", "display_name": "Z 901 Seminer", "capacity": 24}, headers=clerk)
    assert r.status_code == 201, r.text
    room = r.json()
    assert room["code"] == "Z901" and room["capacity"] == 24
    # the room administrator sees it in the room admin list and can give it a group like any other room
    listed = (await c.get("/api/v1/room-admin/rooms", headers=clerk)).json()
    assert any(x["id"] == room["id"] for x in listed)
    assert (await c.delete(f"/api/v1/rooms/{room['id']}", headers=clerk)).status_code == 204
    assert (await c.get(f"/api/v1/rooms/{room['id']}", headers=env.admin)).status_code == 404

    # a room with bookings is refused (history is kept, audit B16), the reason is machine readable
    _, teacher = await env.user("ogretmen.derslik@uni.edu.tr")
    assert (await env.book(teacher, "A101", MON, "P1")).status_code == 201
    r = await c.delete(f"/api/v1/rooms/{env.rooms['A101']}", headers=clerk)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "room_has_bookings"

    # a teacher may do neither
    assert (await c.post("/api/v1/rooms", json={"code": "Z 902"}, headers=teacher)).status_code == 403
    assert (await c.delete(f"/api/v1/rooms/{env.rooms['A101']}", headers=teacher)).status_code == 403


async def test_term_usage_counts_what_a_delete_erases(env):  # noqa: F811
    _, teacher = await env.user("donem.sayim@uni.edu.tr")
    assert (await env.book(teacher, "A101", MON, "P1")).status_code == 201
    c = env.client
    usage = (await c.get(f"/api/v1/terms/{env.term_id}/usage", headers=env.admin)).json()
    assert usage["term_id"] == env.term_id
    assert usage["active_bookings"] >= 1 and usage["bookings"] >= usage["active_bookings"]
    assert usage["runs"] >= 1

    # setup.sessions alone may read it (the sessions admin), a teacher may not
    rid = await _role(env, "Dönem sorumlusu", ["setup.sessions"])
    _, clerk = await env.user("donem.sorumlu@uni.edu.tr", role=None, role_id=rid)
    assert (await c.get(f"/api/v1/terms/{env.term_id}/usage", headers=clerk)).status_code == 200
    assert (await c.get(f"/api/v1/terms/{env.term_id}/usage", headers=teacher)).status_code == 403

    # CRBS behaviour: deleting the session deletes its bookings
    assert (await c.delete(f"/api/v1/terms/{env.term_id}", headers=clerk)).status_code == 204
    assert (await c.get(f"/api/v1/terms/{env.term_id}/usage", headers=env.admin)).status_code == 404
    mine = (await c.get("/api/v1/bookings/mine", params={"status": "ALL"}, headers=teacher)).json()
    assert mine == [] or all(b["term_id"] != env.term_id for b in mine)
