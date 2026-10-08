"""/users: ADMIN-only CRUD, write-only passwords, last-admin protection."""

from __future__ import annotations

from tests.api_fixtures import login


async def test_users_crud_and_password_reset(client):
    h = await login(client)
    users = (await client.get("/api/v1/users", headers=h)).json()
    assert [u["email"] for u in users] == ["admin@example.com"]
    assert users[0]["has_password"] is True
    assert all(k not in {"password", "password_hash"} for u in users for k in u)  # write-only

    # Turkish name + upper-case e-mail are kept / normalised
    r = await client.post(
        "/api/v1/users",
        json={
            "email": " Fatih.Demir@Uni.EDU.TR ",
            "full_name": "Fatih İşçi",
            "role": "PLANNER",
            "password": "şifre-1234",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    planner = r.json()
    assert planner["email"] == "fatih.demir@uni.edu.tr" and planner["full_name"] == "Fatih İşçi"
    assert planner["role"] == "PLANNER" and "password_hash" not in planner
    dup = await client.post(
        "/api/v1/users", json={"email": "fatih.demir@uni.edu.tr", "password": "another-pass"}, headers=h
    )
    assert dup.status_code == 409
    short = await client.post("/api/v1/users", json={"email": "x@y.z", "password": "123"}, headers=h)
    assert short.status_code == 422
    bad_role = await client.post(
        "/api/v1/users", json={"email": "x@y.z", "password": "12345678", "role": "ROOT"}, headers=h
    )
    assert bad_role.status_code == 422

    # the planner can log in with the Turkish password but cannot manage users
    hp = await login(client, "fatih.demir@uni.edu.tr", "şifre-1234")
    assert (await client.get("/api/v1/users", headers=hp)).status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=hp)).json()["role"] == "PLANNER"

    # admin resets the password -> old one fails, new one works
    r = await client.post(f"/api/v1/users/{planner['id']}/password", json={"password": "yeni-parola-99"}, headers=h)
    assert r.status_code == 200
    bad = await client.post("/api/v1/auth/login", json={"email": "fatih.demir@uni.edu.tr", "password": "şifre-1234"})
    assert bad.status_code == 401
    await login(client, "fatih.demir@uni.edu.tr", "yeni-parola-99")

    # update: role + deactivate; inactive users cannot log in
    r = await client.put(f"/api/v1/users/{planner['id']}", json={"role": "VIEWER", "is_active": False}, headers=h)
    assert r.status_code == 200 and r.json()["role"] == "VIEWER" and r.json()["is_active"] is False
    r = await client.post("/api/v1/auth/login", json={"email": "fatih.demir@uni.edu.tr", "password": "yeni-parola-99"})
    assert r.status_code == 403

    # last-admin protection and no self-delete
    me = users[0]
    assert (await client.put(f"/api/v1/users/{me['id']}", json={"role": "PLANNER"}, headers=h)).status_code == 409
    assert (await client.put(f"/api/v1/users/{me['id']}", json={"is_active": False}, headers=h)).status_code == 409
    assert (await client.delete(f"/api/v1/users/{me['id']}", headers=h)).status_code == 409

    assert (await client.delete(f"/api/v1/users/{planner['id']}", headers=h)).status_code == 204
    assert (await client.get(f"/api/v1/users/{planner['id']}", headers=h)).status_code == 404
    assert (await client.get("/api/v1/users")).status_code == 401
