"""CRBS roles and permissions: seeded sets (data.sql), the per-route permission matrix, custom roles,
per-user constraints and the lock-out guards."""

from __future__ import annotations

import pytest
from app.core import db as dbmod
from app.core.security import hash_password
from app.models import User

from tests.api_fixtures import login
from tests.crbs_support import make_user, role_id

TEACHER_DATA_SQL = {
    "room.view",
    "book_single.create",
    "book_single.view_other_notes",
    "book_recur.view_other_notes",
}


async def test_seeded_roles_are_the_crbs_defaults_plus_smartsched_roles(client):
    admin = await login(client)
    roles = {r["code"]: r for r in (await client.get("/api/v1/roles", headers=admin)).json()}
    assert set(roles) == {"ADMIN", "PLANNER", "VIEWER", "TEACHER"}
    assert roles["ADMIN"]["name"] == "Administrator" and roles["TEACHER"]["name"] == "Teacher"
    perms = (await client.get("/api/v1/permissions", headers=admin)).json()
    names = {p["name"] for groups in perms.values() for items in groups.values() for p in items}
    assert len(names) == 31 and {"planning.view", "planning.edit", "planning.admin"} <= names
    assert set(roles["ADMIN"]["permissions"]) == names
    assert set(roles["TEACHER"]["permissions"]) == TEACHER_DATA_SQL
    assert all(roles[c]["max_active_bookings"] is None for c in roles)
    # the admin seeded from ADMIN_EMAIL holds the Administrator role
    me = (await client.get("/api/v1/auth/me", headers=admin)).json()
    assert me["role"] == "ADMIN" and me["role_id"] == roles["ADMIN"]["id"]
    assert set(me["permissions"]) == names


MATRIX = [
    # (method, path, body, expected status per role ADMIN, PLANNER, VIEWER, TEACHER)
    ("GET", "/api/v1/roles", None, (200, 403, 403, 403)),
    ("GET", "/api/v1/users", None, (200, 403, 403, 403)),
    ("GET", "/api/v1/runs", None, (200, 200, 200, 403)),
    ("GET", "/api/v1/rooms", None, (200, 200, 200, 403)),
    ("GET", "/api/v1/bookings/context", None, (200, 200, 200, 200)),
    ("GET", "/api/v1/bookings/export.csv", None, (200, 200, 403, 403)),
    ("GET", "/api/v1/org/settings", None, (200, 403, 403, 403)),
    ("GET", "/api/v1/booking-admin/schedules", None, (200, 403, 403, 403)),
    ("GET", "/api/v1/room-admin/groups", None, (200, 403, 403, 403)),
    ("GET", "/api/v1/departments", None, (200, 200, 200, 200)),
    ("POST", "/api/v1/departments", {"name": "Psikoloji"}, (201, 403, 403, 403)),
    ("GET", "/api/v1/settings", None, (200, 403, 403, 403)),
]


async def test_permission_matrix_per_role(client):
    admin = await login(client)
    headers = {"ADMIN": admin}
    for code in ("PLANNER", "VIEWER", "TEACHER"):
        _, headers[code] = await make_user(client, admin, f"{code.lower()}@uni.edu.tr", role=code)
    for method, path, body, expected in MATRIX:
        for code, want in zip(("ADMIN", "PLANNER", "VIEWER", "TEACHER"), expected, strict=True):
            r = await client.request(method, path, json=body, headers=headers[code])
            if want == 201 and r.status_code == 409:  # created once already by an earlier role
                continue
            assert r.status_code == want, f"{code} {method} {path}: {r.status_code} {r.text[:200]}"


async def test_custom_role_permissions_are_enforced(client):
    admin = await login(client)
    r = await client.post(
        "/api/v1/roles",
        json={"name": "Bölüm Sekreteri", "description": "İşçi", "permissions": ["setup.users", "room.view"]},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    custom = r.json()
    assert custom["code"] is None and custom["name"] == "Bölüm Sekreteri"
    uid, h = await make_user(client, admin, "sekreter@uni.edu.tr", role_id=custom["id"], role=None)
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    assert me["role"] == "CUSTOM" and set(me["permissions"]) == {"setup.users", "room.view"}
    assert (await client.get("/api/v1/users", headers=h)).status_code == 200
    # read-only role list for user managers (their pickers grey out roles they may not grant); no writes
    assert (await client.get("/api/v1/roles", headers=h)).status_code == 200
    assert (await client.post("/api/v1/roles", json={"name": "y", "permissions": []}, headers=h)).status_code == 403
    assert (await client.get("/api/v1/runs", headers=h)).status_code == 403
    # deleting the role leaves the user without permissions (CRBS: users.role_id = NULL)
    assert (await client.delete(f"/api/v1/roles/{custom['id']}", headers=admin)).status_code == 204
    # ... and ends the member's sessions (B-AUTH-11, as a role change does); after signing in again: no role
    assert (await client.get("/api/v1/auth/me", headers=h)).status_code == 401
    h = await login(client, "sekreter@uni.edu.tr", "parola-1234")
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    assert me["role_id"] is None and me["permissions"] == []
    assert (await client.get("/api/v1/users", headers=h)).status_code == 403


async def test_users_created_before_roles_resolve_by_role_code(client):
    """Rows written by importers / older code carry only ``role``; they keep their old rights."""
    admin = await login(client)
    async with dbmod.get_session_factory()() as s:
        s.add(User(email="eski@uni.edu.tr", password_hash=hash_password("eski-parola"), role="PLANNER"))
        await s.commit()
    h = await login(client, "eski@uni.edu.tr", "eski-parola")
    assert (await client.get("/api/v1/runs", headers=h)).status_code == 200
    assert (await client.get("/api/v1/roles", headers=h)).status_code == 403
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    assert me["role_id"] == await role_id(client, admin, "PLANNER")


async def test_admin_role_lockout_guards(client):
    admin = await login(client)
    admin_role = await role_id(client, admin, "ADMIN")
    assert (await client.delete(f"/api/v1/roles/{admin_role}", headers=admin)).status_code == 409
    r = await client.put(f"/api/v1/roles/{admin_role}", json={"permissions": ["room.view"]}, headers=admin)
    assert r.status_code == 409
    # limits on the admin role are allowed
    r = await client.put(f"/api/v1/roles/{admin_role}", json={"description": "Yönetici"}, headers=admin)
    assert r.status_code == 200 and r.json()["description"] == "Yönetici"


async def test_role_limits_and_user_constraints(client):
    admin = await login(client)
    teacher_role = await role_id(client, admin, "TEACHER")
    r = await client.put(
        f"/api/v1/roles/{teacher_role}",
        json={"max_active_bookings": 3, "range_min": 0, "range_max": 14, "recur_max_instances": 10},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    uid, h = await make_user(client, admin, "hoca@uni.edu.tr")
    ctx = (await client.get("/api/v1/bookings/context", headers=h)).json()
    assert ctx["limits"] == {"max_active_bookings": 3, "range_min": 0, "range_max": 14, "recur_max_instances": 10}
    r = await client.put(
        f"/api/v1/users/{uid}/constraints",
        json={
            "max_active_bookings": {"type": "U", "value": 5},
            "range_max": {"type": "X"},
            "recur_max_instances": {"type": "R"},
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    got = (await client.get(f"/api/v1/users/{uid}/constraints", headers=admin)).json()
    assert got["max_active_bookings"] == {"type": "U", "value": 5}
    assert got["range_max"] == {"type": "X", "value": None}
    ctx = (await client.get("/api/v1/bookings/context", headers=h)).json()
    assert ctx["limits"] == {"max_active_bookings": 5, "range_min": 0, "range_max": None, "recur_max_instances": 10}
    bad = await client.put(f"/api/v1/users/{uid}/constraints", json={"range_min": {"type": "U"}}, headers=admin)
    assert bad.status_code == 422  # U needs a value


@pytest.mark.parametrize("payload", [{"name": ""}, {"name": "x", "permissions": ["not.a.permission"]}])
async def test_role_validation(client, payload):
    admin = await login(client)
    assert (await client.post("/api/v1/roles", json=payload, headers=admin)).status_code == 422
