"""CRBS parity — usernames, deleting users, and what deleting a role / department / room group removes;
ACL entries whose context is a role. Real data: the Bahar 2026 import (``tests/crbs_env``): A 101 Monday
16 Feb P1-P3 free, A 102 Thursdays P1 free all term, the real programmes of the planning list."""

from __future__ import annotations

from datetime import date

import pytest

from tests.api_fixtures import login

MON = date(2026, 2, 16)
THU = date(2026, 2, 19)


async def _acl(env, entity_type: str, entity_id: int) -> list[dict]:  # type: ignore[no-untyped-def]
    r = await env.client.get(
        "/api/v1/room-admin/acl", params={"entity_type": entity_type, "entity_id": entity_id}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _grant(env, entity_type: str, entity_id: int, context_type: str, context_id: int, perms: list[str]) -> dict:  # type: ignore[no-untyped-def]
    r = await env.client.post(
        "/api/v1/room-admin/acl",
        json={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "context_type": context_type,
            "context_id": context_id,
            "permissions": perms,
        },
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parity("B-USERS-02")
async def test_usernames_are_turkish_aware_and_unique(env):
    """``Users::save``: a username is required to be unique and free of spaces. SmartSched also accepts
    Turkish letters (CRBS: ``[A-Za-z0-9-_.@]``, at most 32) and folds İ/I/ı/i so one person is one account."""
    c = env.client
    bad = await c.post(
        "/api/v1/users",
        json={"username": "Ayşe Kılıç", "password": "parola-1234", "role": "TEACHER"},
        headers=env.admin,
    )
    assert bad.status_code == 422
    ok = await c.post(
        "/api/v1/users",
        json={"username": "\xa0AYŞE.KILIÇ ", "password": "parola-1234", "role": "TEACHER", "displayname": "Ayşe Kılıç"},
        headers=env.admin,
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["username"] == "ayşe.kiliç" and ok.json()["email"] is None  # CRBS users may have no e-mail
    dup = await c.post(
        "/api/v1/users",
        json={"username": "ayşe.kılıç", "password": "parola-1234", "role": "TEACHER"},
        headers=env.admin,
    )
    assert dup.status_code == 409
    r = await c.post("/api/v1/auth/login", json={"username": "Ayşe.Kılıç", "password": "parola-1234"})
    assert r.status_code == 200, r.text


@pytest.mark.parity("B-USERS-04")
async def test_deleting_a_user_refuses_yourself_and_removes_acl_constraints_and_ownership(env):
    """``Users::delete`` / ``Users_model::Delete``: never your own account; the user's ACL entries and
    constraints go and rooms they owned lose the owner (their bookings stay as history: test_crbs_users)."""
    c = env.client
    me = (await c.get("/api/v1/auth/me", headers=env.admin)).json()
    assert (await c.delete(f"/api/v1/users/{me['id']}", headers=env.admin)).status_code == 409
    uid, _ = await env.user("silinecek@uni.edu.tr", displayname="Tuğba Erdoğan")
    await _grant(env, "room", env.rooms["A102"], "user", uid, ["room.view", "book_recur.create"])
    r = await c.put(
        f"/api/v1/users/{uid}/constraints", json={"max_active_bookings": {"type": "U", "value": 3}}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    r = await c.put(f"/api/v1/room-admin/rooms/{env.rooms['A101']}", json={"owner_user_id": uid}, headers=env.admin)
    assert r.status_code == 200 and r.json()["owner_user_id"] == uid
    assert len(await _acl(env, "room", env.rooms["A101"])) == 1  # the owner ACL (CRBS migration 2025-04)
    assert (await c.delete(f"/api/v1/users/{uid}", headers=env.admin)).status_code == 204
    assert await _acl(env, "room", env.rooms["A102"]) == []
    assert await _acl(env, "room", env.rooms["A101"]) == []
    rooms = {r["id"]: r for r in (await c.get("/api/v1/room-admin/rooms", headers=env.admin)).json()}
    assert rooms[env.rooms["A101"]]["owner_user_id"] is None
    assert (await c.get(f"/api/v1/users/{uid}", headers=env.admin)).status_code == 404


@pytest.mark.parity("B-ROLES-07", "B-ROOMS-06")
async def test_role_acl_grants_rooms_and_acl_entries_can_be_changed_and_removed(env):
    """``Auth_model::user_room_permissions``: an ACL whose context is the user's *role* grants its
    permissions in that room; editing the entry changes them, deleting it takes them away."""
    c = env.client
    role = (
        await c.post("/api/v1/roles", json={"name": "Misafir araştırmacı", "permissions": []}, headers=env.admin)
    ).json()
    _, guest = await env.user("misafir.arastirmaci@uni.edu.tr", role=None, role_id=role["id"])
    assert (await c.get("/api/v1/bookings/rooms", headers=guest)).json() == []
    acl = await _grant(env, "room", env.rooms["A102"], "role", role["id"], ["room.view", "book_single.create"])
    assert acl["context_label"] == "Misafir araştırmacı" and acl["entity_label"] == "A 102"
    assert [r["code"] for r in (await c.get("/api/v1/bookings/rooms", headers=guest)).json()] == ["A102"]
    first = await env.book(guest, "A102", THU, "P1")
    assert first.status_code == 201, first.text
    r = await c.put(f"/api/v1/room-admin/acl/{acl['id']}", json={"permissions": ["room.view"]}, headers=env.admin)
    assert r.status_code == 200 and r.json()["permissions"] == ["room.view"]
    assert (await env.book(guest, "A102", date(2026, 2, 26), "P1")).status_code == 403  # sees it, cannot book
    assert (await c.delete(f"/api/v1/room-admin/acl/{acl['id']}", headers=env.admin)).status_code == 204
    assert (await c.get("/api/v1/bookings/rooms", headers=guest)).json() == []
    # her own booking stays hers to see (ownership), although the room is no longer visible
    assert (await c.get(f"/api/v1/bookings/{first.json()['id']}", headers=guest)).status_code == 200


@pytest.mark.parity("B-ROLES-04")
async def test_deleting_a_role_removes_its_acl_entries(env):
    """``Roles_model::delete``: users lose the role (role_id NULL: test_crbs_roles) and the role's ACL
    entries are deleted."""
    c = env.client
    role = (
        await c.post("/api/v1/roles", json={"name": "Laboratuvar sorumlusu", "permissions": []}, headers=env.admin)
    ).json()
    uid, h = await env.user("lab.sorumlu@uni.edu.tr", role=None, role_id=role["id"])
    await _grant(env, "room", env.rooms["A103"], "role", role["id"], ["room.view", "book_single.create"])
    assert [r["code"] for r in (await c.get("/api/v1/bookings/rooms", headers=h)).json()] == ["A103"]
    assert (await c.delete(f"/api/v1/roles/{role['id']}", headers=env.admin)).status_code == 204
    assert await _acl(env, "room", env.rooms["A103"]) == []
    assert (await c.get(f"/api/v1/users/{uid}", headers=env.admin)).json()["role_id"] is None
    # losing the role also ends the member's sessions (B-AUTH-11); signed in again they see no room
    assert (await c.get("/api/v1/bookings/rooms", headers=h)).status_code == 401
    h = await login(c, "lab.sorumlu@uni.edu.tr", "parola-1234")
    assert (await c.get("/api/v1/bookings/rooms", headers=h)).json() == []


@pytest.mark.parity("B-ROLES-10")
async def test_deleting_a_department_removes_its_acl_entries(env):
    """``Departments_model::delete``: users lose the department (test_crbs_admin) and the department's ACL
    entries are deleted."""
    c = env.client
    dep = (await c.post("/api/v1/departments", json={"name": "Sürekli Eğitim Merkezi"}, headers=env.admin)).json()
    role = (await c.post("/api/v1/roles", json={"name": "Eğitmen", "permissions": []}, headers=env.admin)).json()
    _, h = await env.user("egitmen@uni.edu.tr", role=None, role_id=role["id"], department_id=dep["id"])
    await _grant(env, "room", env.rooms["A104"], "department", dep["id"], ["room.view"])
    assert [r["code"] for r in (await c.get("/api/v1/bookings/rooms", headers=h)).json()] == ["A104"]
    assert (await c.delete(f"/api/v1/departments/{dep['id']}", headers=env.admin)).status_code == 204
    assert await _acl(env, "room", env.rooms["A104"]) == []
    assert (await c.get("/api/v1/bookings/rooms", headers=h)).json() == []


@pytest.mark.parity("B-ROOMS-14")
async def test_deleting_a_room_group_removes_its_acl_entries_and_frees_its_rooms(env):
    """``Room_groups_model::delete``: member rooms become ungrouped and the group's ACL entries go."""
    c = env.client
    g = (
        await c.post(
            "/api/v1/room-admin/groups",
            json={"name": "Amfiler", "room_ids": [env.rooms["A204"], env.rooms["A203"]]},
            headers=env.admin,
        )
    ).json()
    uid, h = await env.user(
        "amfi@uni.edu.tr",
        role=None,
        role_id=(
            await c.post("/api/v1/roles", json={"name": "Amfi kullanıcısı", "permissions": []}, headers=env.admin)
        ).json()["id"],
    )
    await _grant(env, "room_group", g["id"], "user", uid, ["room.view"])
    assert {r["code"] for r in (await c.get("/api/v1/bookings/rooms", headers=h)).json()} == {"A203", "A204"}
    assert (await c.delete(f"/api/v1/room-admin/groups/{g['id']}", headers=env.admin)).status_code == 204
    assert await _acl(env, "room_group", g["id"]) == []
    rooms = {r["id"]: r for r in (await c.get("/api/v1/room-admin/rooms", headers=env.admin)).json()}
    assert rooms[env.rooms["A204"]]["room_group_id"] is None and rooms[env.rooms["A204"]]["room_group"] is None
    assert (await c.get("/api/v1/bookings/rooms", headers=h)).json() == []
