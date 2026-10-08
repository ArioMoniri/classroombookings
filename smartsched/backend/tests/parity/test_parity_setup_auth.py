"""CRBS parity — setup menu, organisation logo on the login page, events, sign-in rules.

Real data: the Bahar 2026 import (``tests/crbs_env``: published weekly grid, the 18 university periods,
term 2026-BAHAR, clock Monday 16 Feb 2026 08:00); Turkish names and usernames."""

from __future__ import annotations

import io
from typing import Any

import pytest
from PIL import Image

from tests.crbs_support import role_id

#: CRBS data.sql: the ten setup.* permissions that build the setup menu (Menu_model::setup_menu)
CRBS_SETUP = {
    "setup.authentication",
    "setup.departments",
    "setup.roles",
    "setup.rooms",
    "setup.rooms_acl",
    "setup.schedules",
    "setup.sessions",
    "setup.settings",
    "setup.timetable_weeks",
    "setup.users",
}


def _names(groups: dict[str, Any]) -> set[str]:
    return {p["name"] for scope in groups.values() for items in scope.values() for p in items}


@pytest.mark.parity("B-SETUP-05")
async def test_setup_menu_follows_the_setup_permissions(env):
    """``Menu_model::setup_menu``: an entry per ``setup.*`` permission the user holds; staff see none."""
    c = env.client
    admin = (await c.get("/api/v1/auth/permissions", headers=env.admin)).json()
    assert admin["role"] == "Administrator" and admin["role_code"] == "ADMIN"
    assert CRBS_SETUP <= set(admin["permissions"]) and CRBS_SETUP <= _names(admin["groups"])
    _, teacher = await env.user("menu.ogretmen@uni.edu.tr", displayname="Gökçe Işık")
    mine = (await c.get("/api/v1/auth/permissions", headers=teacher)).json()
    assert mine["role"] == "Teacher" and not any(p.startswith("setup.") for p in mine["permissions"])
    assert set(mine["permissions"]) == _names(mine["groups"])
    # a custom role with one setup permission gets exactly that menu entry, and the screen behind it
    rid = (
        await c.post(
            "/api/v1/roles", json={"name": "Bölüm sekreteri", "permissions": ["setup.departments"]}, headers=env.admin
        )
    ).json()["id"]
    _, sekreter = await env.user("menu.sekreter@uni.edu.tr", role=None, role_id=rid)
    got = (await c.get("/api/v1/auth/permissions", headers=sekreter)).json()
    assert [p for p in got["permissions"] if p.startswith("setup.")] == ["setup.departments"]
    assert (await c.post("/api/v1/departments", json={"name": "Kütüphane"}, headers=sekreter)).status_code == 201
    assert (await c.get("/api/v1/room-admin/groups", headers=sekreter)).status_code == 403
    # the setup checklist counts the real import (rooms of the Bahar grid, its term)
    status = (await c.get("/api/v1/org/setup-status")).json()
    assert status["checks"]["rooms"] > 50 and status["checks"]["terms"] >= 1 and status["checks"]["admin"]


def _png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (320, 80), "navy").save(b, "PNG")
    return b.getvalue()


@pytest.mark.parity("B-SETUP-07", "S-02")
async def test_logo_is_shown_on_the_login_page_and_can_be_removed(env):
    """``settings/Organisation``: the uploaded logo is what the login page shows; "remove logo" clears it."""
    c = env.client
    assert (await c.get("/api/v1/org/public")).json()["logo_url"] in (None, "")
    up = await c.post("/api/v1/org/logo", files={"file": ("Acıbadem logo.png", _png(), "image/png")}, headers=env.admin)
    assert up.status_code == 200, up.text
    pub = (await c.get("/api/v1/org/public")).json()
    assert pub["logo_url"] == up.json()["logo_url"] and pub["logo_url"].endswith(".png")
    _, teacher = await env.user("logo.yok@uni.edu.tr")
    assert (await c.delete("/api/v1/org/logo", headers=teacher)).status_code == 403
    assert (await c.delete("/api/v1/org/logo", headers=env.admin)).status_code in (200, 204)
    assert (await c.get("/api/v1/org/public")).json()["logo_url"] in (None, "")


@pytest.mark.parity("B-SETUP-18", "B-AUTH-03")
async def test_login_triggers_the_logged_in_event_and_stamps_last_login(env):
    """CRBS ``Userauth::log_in``: ``lastlogin`` is stamped and ``EventType::USER_LOGGED_IN`` fires."""
    from app.services import bookings_events as events

    seen: list[dict[str, Any]] = []

    async def hook(_session, payload):  # type: ignore[no-untyped-def]
        seen.append(payload)

    uid, _ = await env.user("son.giris@uni.edu.tr", username="şule.kılınç")
    before = (await env.client.get(f"/api/v1/users/{uid}", headers=env.admin)).json()
    events.on("user.logged_in", hook)
    try:
        r = await env.client.post("/api/v1/auth/login", json={"username": "ŞULE.KILINÇ", "password": "parola-1234"})
    finally:
        events.off("user.logged_in", hook)
    assert r.status_code == 200, r.text
    assert seen == [{"user_id": uid, "auth_method": "local"}]
    after = (await env.client.get(f"/api/v1/users/{uid}", headers=env.admin)).json()
    assert after["last_login_at"] and after["last_login_at"] >= (before["last_login_at"] or "")
    # Users::index sorts by last login (most recent first)
    newest = (
        await env.client.get("/api/v1/users/search", params={"sort": "-lastlogin", "limit": 1}, headers=env.admin)
    ).json()
    assert newest["items"][0]["id"] == uid


@pytest.mark.parity("B-AUTH-02")
async def test_disabled_local_accounts_are_refused(env):
    """``Userauth::log_in``: a disabled user cannot sign in even with the right password."""
    uid, h = await env.user("pasif.hesap@uni.edu.tr", username="pasif.hesap")
    assert (await env.client.get("/api/v1/bookings/context", headers=h)).status_code == 200
    r = await env.client.put(f"/api/v1/users/{uid}", json={"is_active": False}, headers=env.admin)
    assert r.status_code == 200 and r.json()["is_active"] is False
    for body in (
        {"username": "PASİF.HESAP", "password": "parola-1234"},
        {"email": "pasif.hesap@uni.edu.tr", "password": "parola-1234"},
    ):
        assert (await env.client.post("/api/v1/auth/login", json=body)).status_code == 403
    # a token issued before the account was disabled stops working too
    assert (await env.client.get("/api/v1/bookings/context", headers=h)).status_code in (401, 403)
    await env.client.put(f"/api/v1/users/{uid}", json={"is_active": True}, headers=env.admin)
    assert (
        await env.client.post("/api/v1/auth/login", json={"username": "pasif.hesap", "password": "parola-1234"})
    ).status_code == 200


@pytest.mark.parity("B-USERS-01")
async def test_user_list_filters_sort_and_paging(env):
    """``Users::index``: search, role / department / enabled filters, sort and paging."""
    c = env.client
    deps = (await c.get("/api/v1/departments", params={"q": "PSİKOLOJİ"}, headers=env.admin)).json()
    psy = next(d for d in deps if d["name"].casefold().startswith("psikoloji"))
    names = ["Çağla Ünal", "Ömer Şen", "İpek Aydın"]
    ids = []
    for i, name in enumerate(names):
        uid, _ = await env.user(f"liste{i}@uni.edu.tr", displayname=name, department_id=psy["id"])
        ids.append(uid)
    await c.put(f"/api/v1/users/{ids[1]}", json={"is_active": False}, headers=env.admin)
    by_dep = (await c.get("/api/v1/users/search", params={"department_id": psy["id"]}, headers=env.admin)).json()
    assert by_dep["total"] == 3 and {u["id"] for u in by_dep["items"]} == set(ids)
    enabled = (
        await c.get("/api/v1/users/search", params={"department_id": psy["id"], "enabled": "true"}, headers=env.admin)
    ).json()
    assert {u["id"] for u in enabled["items"]} == {ids[0], ids[2]}
    # Turkish alphabetical order of display names: Ç < İ < Ö (tr_casefold), descending reverses it
    srt = (
        await c.get(
            "/api/v1/users/search", params={"department_id": psy["id"], "sort": "displayname"}, headers=env.admin
        )
    ).json()
    assert [u["displayname"] for u in srt["items"]] == ["Çağla Ünal", "İpek Aydın", "Ömer Şen"]
    page2 = (
        await c.get(
            "/api/v1/users/search",
            params={"department_id": psy["id"], "sort": "displayname", "limit": 2, "offset": 2},
            headers=env.admin,
        )
    ).json()
    assert page2["total"] == 3 and [u["displayname"] for u in page2["items"]] == ["Ömer Şen"]
    # CRBS sort_map: department and role sort by their *names*; several keys may be combined ("role,-username")
    viewer = await c.post(
        "/api/v1/users",
        json={"username": "zz.izleyici", "role": "VIEWER", "department_id": psy["id"], "password": "parola-1234"},
        headers=env.admin,
    )
    assert viewer.status_code == 201, viewer.text
    by_role = (
        await c.get(
            "/api/v1/users/search", params={"department_id": psy["id"], "sort": "role,-displayname"}, headers=env.admin
        )
    ).json()
    assert [u["role_name"] for u in by_role["items"]] == ["Teacher", "Teacher", "Teacher", "Viewer"]
    assert [u["displayname"] for u in by_role["items"][:3]] == ["Ömer Şen", "İpek Aydın", "Çağla Ünal"]
    # never signed in (NULL last login) sorts first ascending and last descending, as in MySQL
    asc = (
        await c.get("/api/v1/users/search", params={"department_id": psy["id"], "sort": "lastlogin"}, headers=env.admin)
    ).json()
    assert asc["items"][0]["username"] == "zz.izleyici"
    desc = (
        await c.get(
            "/api/v1/users/search", params={"department_id": psy["id"], "sort": "-lastlogin"}, headers=env.admin
        )
    ).json()
    assert desc["items"][-1]["username"] == "zz.izleyici"
    other = (await c.post("/api/v1/departments", json={"name": "Acil Durum Birimi"}, headers=env.admin)).json()
    await c.put(f"/api/v1/users/{ids[2]}", json={"department_id": other["id"]}, headers=env.admin)
    by_dep_name = (
        await c.get(
            "/api/v1/users/search", params={"q": "uni.edu.tr", "sort": "department", "limit": 500}, headers=env.admin
        )
    ).json()
    named = [u for u in by_dep_name["items"] if u["department_name"]]
    assert named[0]["id"] == ids[2] and named[0]["department_name"] == "Acil Durum Birimi"
    teacher_role = await role_id(c, env.admin, "TEACHER")
    both = (
        await c.get("/api/v1/users/search", params={"role_id": teacher_role, "q": "ÇAĞLA"}, headers=env.admin)
    ).json()
    assert [u["id"] for u in both["items"]] == [ids[0]]


async def _me(env, headers: dict[str, str]) -> int:  # type: ignore[no-untyped-def]
    return (await env.client.get("/api/v1/auth/me", headers=headers)).status_code


async def _sign_in(env, ident: str, password: str = "parola-1234") -> dict[str, str]:  # type: ignore[no-untyped-def]
    r = await env.client.post("/api/v1/auth/login", json={"username": ident, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.parity("B-AUTH-11")
async def test_sign_out_revokes_the_token_on_every_device(env):
    """CRBS ``Logout`` destroys the session. SmartSched: POST /auth/logout bumps the user's token version, so the
    bearer token (and the copy another device holds) answers 401 at once instead of living until it expires."""
    c = env.client
    _, laptop = await env.user("oturum.kapat@uni.edu.tr", username="gülşen.ışık", displayname="Gülşen Işık")
    phone = await _sign_in(env, "GÜLŞEN.IŞIK")  # Turkish İ/I folding on the username, second device
    assert await _me(env, laptop) == 200 and await _me(env, phone) == 200
    assert (await c.post("/api/v1/auth/logout", headers=laptop)).status_code == 204
    assert await _me(env, laptop) == 401 and await _me(env, phone) == 401
    assert (await c.get("/api/v1/bookings/context", headers=phone)).status_code == 401
    assert (await c.post("/api/v1/auth/logout", headers=laptop)).status_code == 401  # already revoked
    assert (await c.post("/api/v1/auth/logout")).status_code == 401  # no token
    again = await _sign_in(env, "oturum.kapat@uni.edu.tr")
    assert await _me(env, again) == 200
    # other users keep their sessions
    assert await _me(env, env.admin) == 200


@pytest.mark.parity("B-AUTH-11")
async def test_password_changes_and_resets_revoke_older_tokens(env):
    """Own password change, admin password set and the one-time reset code all end the existing sessions."""
    c = env.client
    uid, h = await env.user("parola.degis@uni.edu.tr", username="ömer.çelik")
    r = await c.post(
        "/api/v1/auth/change-password",
        json={"current_password": "parola-1234", "new_password": "yeni-Parola-1"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert await _me(env, h) == 401
    h = await _sign_in(env, "ömer.çelik", "yeni-Parola-1")
    assert await _me(env, h) == 200
    # the administrator sets a new password (Users -> password)
    r = await c.post(f"/api/v1/users/{uid}/password", json={"password": "admin-verdi-2"}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert await _me(env, h) == 401
    h = await _sign_in(env, "ömer.çelik", "admin-verdi-2")
    # ... or through the user edit form
    r = await c.put(f"/api/v1/users/{uid}", json={"password": "duzenle-parola-3"}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert await _me(env, h) == 401
    h = await _sign_in(env, "ömer.çelik", "duzenle-parola-3")
    # one-time reset code
    code = (await c.post(f"/api/v1/users/{uid}/reset-token", headers=env.admin)).json()["token"]
    assert await _me(env, h) == 200  # issuing a code alone does not sign anyone out
    r = await c.post("/api/v1/auth/password-reset/confirm", json={"token": code, "password": "kod-parola-4"})
    assert r.status_code == 200, r.text
    assert await _me(env, h) == 401
    assert await _me(env, await _sign_in(env, "ömer.çelik", "kod-parola-4")) == 200


@pytest.mark.parity("B-AUTH-11", "B-AUTH-02")
async def test_disabling_and_role_changes_revoke_older_tokens(env):
    """A disabled account's token does not come back when the account is enabled again; a role change ends the
    sessions issued under the old role."""
    c = env.client
    uid, h = await env.user("rol.degis@uni.edu.tr", username="işıl.şahin")
    assert (await c.put(f"/api/v1/users/{uid}", json={"is_active": False}, headers=env.admin)).status_code == 200
    assert (await c.put(f"/api/v1/users/{uid}", json={"is_active": True}, headers=env.admin)).status_code == 200
    assert await _me(env, h) == 401  # re-enabling does not revive the old token
    h = await _sign_in(env, "işıl.şahin")
    # an unrelated edit keeps the session
    r = await c.put(f"/api/v1/users/{uid}", json={"displayname": "Işıl Şahin"}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert await _me(env, h) == 200
    # the same role again is not a change
    assert (await c.put(f"/api/v1/users/{uid}", json={"role": "TEACHER"}, headers=env.admin)).status_code == 200
    assert await _me(env, h) == 200
    r = await c.put(f"/api/v1/users/{uid}", json={"role_id": await role_id(c, env.admin, "VIEWER")}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert await _me(env, h) == 401
    h = await _sign_in(env, "işıl.şahin")
    me = (await c.get("/api/v1/auth/me", headers=h)).json()
    assert me["role"] == "VIEWER"


@pytest.mark.parity("B-AUTH-11")
async def test_forced_password_change_user_may_sign_out(env):
    """A user who must change the password first may still sign out (like /auth/change-password)."""
    _, h = await env.user("zorunlu.degisim@uni.edu.tr", force_password_reset=True)
    assert (await env.client.get("/api/v1/bookings/context", headers=h)).status_code == 403
    assert (await env.client.post("/api/v1/auth/logout", headers=h)).status_code == 204
    assert await _me(env, h) == 401
