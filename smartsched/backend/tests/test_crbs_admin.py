"""Setup screens: room groups / order / custom fields / owner / photo, schedules and periods on the grid,
per-group term schedules, timetable weeks, departments (= programmes), organisation settings,
translations, changelog, events, and the first-run setup wizard."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.core import db as dbmod
from app.models import Base
from app.workers import queue as qmod
from httpx import ASGITransport, AsyncClient

from tests.api_fixtures import login
from tests.crbs_env import env  # noqa: F401


async def test_room_groups_order_fields_owner_and_photo(env):  # noqa: F811
    c, admin = env.client, env.admin
    g = await c.post(
        "/api/v1/room-admin/groups",
        json={"name": "Bilgisayar labları", "description": "PC", "room_ids": [env.rooms["A103"], env.rooms["A105"]]},
        headers=admin,
    )
    assert g.status_code == 201, g.text
    lab = g.json()
    assert lab["room_ids"] == [env.rooms["A103"], env.rooms["A105"]] or sorted(lab["room_ids"]) == sorted(
        [env.rooms["A103"], env.rooms["A105"]]
    )
    amfi = (
        await c.post(
            "/api/v1/room-admin/groups", json={"name": "Amfiler", "room_ids": [env.rooms["A204"]]}, headers=admin
        )
    ).json()
    order = (
        await c.put("/api/v1/room-admin/groups/order", json={"ids": [amfi["id"], lab["id"]]}, headers=admin)
    ).json()
    assert [x["name"] for x in order] == ["Amfiler", "Bilgisayar labları"]
    rooms = (
        await c.put(
            "/api/v1/room-admin/rooms/order", json={"ids": [env.rooms["A105"], env.rooms["A103"]]}, headers=admin
        )
    ).json()
    assert [r["code"] for r in rooms] == ["A105", "A103"] and rooms[0]["pos"] == 0

    f_text = (
        await c.post("/api/v1/room-admin/fields", json={"name": "Projeksiyon", "type": "CHECKBOX"}, headers=admin)
    ).json()
    f_sel = (
        await c.post(
            "/api/v1/room-admin/fields",
            json={"name": "Kat zemini", "type": "SELECT", "options": ["Halı", "Parke", " "]},
            headers=admin,
        )
    ).json()
    assert [o["value"] for o in f_sel["options"]] == ["Halı", "Parke"]
    bad = await c.post("/api/v1/room-admin/fields", json={"name": "Boş seçim", "type": "SELECT"}, headers=admin)
    assert bad.status_code == 422
    parke = f_sel["options"][1]["id"]
    r = await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['A103']}/fields",
        json={str(f_text["id"]): True, str(f_sel["id"]): parke},
        headers=admin,
    )
    assert r.status_code == 200 and r.json() == {str(f_text["id"]): True, str(f_sel["id"]): parke}
    wrong = await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['A103']}/fields", json={str(f_sel["id"]): 999999}, headers=admin
    )
    assert wrong.status_code == 422
    info = (await c.get(f"/api/v1/bookings/rooms/{env.rooms['A103']}", headers=env.planner)).json()
    fields = {x["name"]: x["value"] for x in info["fields"]}
    assert fields == {"Projeksiyon": True, "Kat zemini": "Parke"} and info["group"] == "Bilgisayar labları"
    room = (await c.get(f"/api/v1/rooms/{env.rooms['A103']}", headers=env.planner)).json()
    assert room["custom_fields"]["Kat zemini"] == "Parke"  # mirrored for the planning side
    # renaming another option keeps the chosen value
    await c.put(
        f"/api/v1/room-admin/fields/{f_sel['id']}",
        json={"name": "Zemin", "type": "SELECT", "options": ["Halı kaplama", "Parke"]},
        headers=admin,
    )
    assert (await c.get(f"/api/v1/room-admin/rooms/{env.rooms['A103']}/fields", headers=admin)).json()[
        str(f_sel["id"])
    ] == parke
    await c.delete(f"/api/v1/room-admin/fields/{f_sel['id']}", headers=admin)
    room = (await c.get(f"/api/v1/rooms/{env.rooms['A103']}", headers=env.planner)).json()
    assert "Kat zemini" not in room["custom_fields"] and "Zemin" not in room["custom_fields"]
    assert room["custom_fields"]["Projeksiyon"] is True and "sources" in room["custom_fields"]  # importer keys kept

    uid, _ = await env.user("sorumlu@uni.edu.tr")
    upd = await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['A103']}",
        json={"owner_user_id": uid, "location": "A Blok zemin kat", "icon": "monitor", "notes": "Anahtar güvenlikte"},
        headers=admin,
    )
    assert upd.status_code == 200
    assert upd.json()["location"] == "A Blok zemin kat" and upd.json()["owner_user_id"] == uid  # NBSP cleaned
    acl = (
        await c.get(
            "/api/v1/room-admin/acl", params={"entity_type": "room", "entity_id": env.rooms["A103"]}, headers=admin
        )
    ).json()
    assert [a["permissions"] for a in acl] == [["book_single.cancel_other_booking"]]
    await c.put(f"/api/v1/room-admin/rooms/{env.rooms['A103']}", json={"owner_user_id": None}, headers=admin)
    assert (
        await c.get(
            "/api/v1/room-admin/acl", params={"entity_type": "room", "entity_id": env.rooms["A103"]}, headers=admin
        )
    ).json() == []

    photo = await c.post(
        f"/api/v1/room-admin/rooms/{env.rooms['A103']}/photo",
        files={"file": ("lab.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
        headers=admin,
    )
    assert photo.status_code == 200 and photo.json()["photo_url"] == f"/uploads/rooms/{env.rooms['A103']}.png"
    gone = await c.delete(f"/api/v1/room-admin/rooms/{env.rooms['A103']}/photo", headers=admin)
    assert gone.json()["photo_url"] is None
    assert (await c.delete(f"/api/v1/room-admin/groups/{lab['id']}", headers=admin)).status_code == 204
    assert (await c.get(f"/api/v1/bookings/rooms/{env.rooms['A103']}", headers=env.planner)).json()["group"] is None


async def test_schedules_periods_and_group_schedules(env):  # noqa: F811
    c, admin = env.client, env.admin
    s = (await c.post("/api/v1/booking-admin/schedules", json={"name": "İkinci öğretim"}, headers=admin)).json()
    # dotted times as the planning office writes them
    p = await c.post(
        f"/api/v1/booking-admin/schedules/{s['id']}/periods",
        json={"name": "İÖ 1-2", "time_start": "18.00", "time_end": "19.30", "days": [1, 2, 3, 4, 5]},
        headers=admin,
    )
    assert p.status_code == 201, p.text
    assert (p.json()["start_period"], p.json()["end_period"]) == (13, 14)
    assert p.json()["time_start"] == "18:00"
    outside = await c.post(
        f"/api/v1/booking-admin/schedules/{s['id']}/periods",
        json={"name": "Gece", "time_start": "23:00", "time_end": "23:40"},
        headers=admin,
    )
    assert outside.status_code == 422 and "outside" in outside.json()["detail"]
    backwards = await c.post(
        f"/api/v1/booking-admin/schedules/{s['id']}/periods",
        json={"name": "Ters", "time_start": "10:00", "time_end": "09:00"},
        headers=admin,
    )
    assert backwards.status_code == 422
    dup = await c.post(f"/api/v1/booking-admin/schedules/{env.schedule_id}/periods/from-grid", headers=admin)
    assert dup.status_code == 409

    # evening rooms get the evening schedule through their group
    grp = (
        await c.post(
            "/api/v1/room-admin/groups", json={"name": "C Blok", "room_ids": [env.rooms["C201"]]}, headers=admin
        )
    ).json()
    r = await c.put(
        f"/api/v1/booking-admin/sessions/{env.term_id}/schedules",
        json=[{"room_group_id": grp["id"], "schedule_id": s["id"]}],
        headers=admin,
    )
    assert r.status_code == 200 and {x["room_group_id"]: x["schedule_id"] for x in r.json()}[grp["id"]] == s["id"]
    _, teacher = await env.user("aksam@uni.edu.tr")
    wrong = await env.book(teacher, "C201", __import__("datetime").date(2026, 2, 16), "P1")
    assert wrong.status_code == 409 and "not in the schedule" in wrong.json()["detail"]["message"]
    ok = await env.client.post(
        "/api/v1/bookings",
        json={"room_id": env.rooms["C201"], "date": "2026-02-16", "period_id": p.json()["id"]},
        headers=teacher,
    )
    assert ok.status_code == 201, ok.text
    assert (await c.delete(f"/api/v1/booking-admin/periods/{p.json()['id']}", headers=admin)).status_code == 409
    span = await c.put(f"/api/v1/booking-admin/periods/{p.json()['id']}", json={"time_end": "20:20"}, headers=admin)
    assert span.status_code == 409  # its grid span would change under an active booking
    assert (await c.delete(f"/api/v1/booking-admin/schedules/{s['id']}", headers=admin)).status_code == 409
    sessions = (await c.get("/api/v1/booking-admin/sessions", headers=admin)).json()
    bahar = next(x for x in sessions if x["term_id"] == env.term_id)
    assert bahar["is_selectable"] and bahar["default_schedule_id"] == env.schedule_id
    assert bahar["date_start"] == "2026-02-02" and bahar["date_end"] == "2026-06-28"


async def test_departments_are_programmes(env):  # noqa: F811
    c, admin = env.client, env.admin
    before = (await c.get("/api/v1/departments", headers=env.planner)).json()
    assert len(before) > 50  # the Bahar planning list's real programmes
    r = await c.post(
        "/api/v1/departments",
        json={"name": "Sağlık Kültür ve Spor Daire Başkanlığı", "description": "SKS"},
        headers=admin,
    )
    assert r.status_code == 201 and r.json()["name"] == "Sağlık Kültür ve Spor Daire Başkanlığı"
    dup = await c.post("/api/v1/departments", json={"name": "SAĞLIK KÜLTÜR VE SPOR DAİRE BAŞKANLIĞI"}, headers=admin)
    assert dup.status_code == 409  # Turkish-casefold duplicate
    used = next(d for d in before if d["name"].casefold().startswith("psikoloji"))
    assert (await c.delete(f"/api/v1/departments/{used['id']}", headers=admin)).status_code == 409
    uid, _ = await env.user("sks@uni.edu.tr", department_id=r.json()["id"])
    assert (await c.delete(f"/api/v1/departments/{r.json()['id']}", headers=admin)).status_code == 204
    assert (await c.get(f"/api/v1/users/{uid}", headers=admin)).json()["department_id"] is None


async def test_org_settings_translations_changelog_and_events(env):  # noqa: F811
    c, admin = env.client, env.admin
    r = await c.put(
        "/api/v1/org/settings",
        json={
            "name": "Acıbadem Üniversitesi",
            "timezone": "Europe/Istanbul",
            "login_message_enabled": True,
            "login_message_text": "Derslik rezervasyonları için giriş yapın",
            "displaytype": "room",
            "d_columns": "days",
            "max_active_bookings": 5,
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Acıbadem Üniversitesi" and r.json()["max_active_bookings"] == 5
    assert (await c.put("/api/v1/org/settings", json={"d_columns": "rooms"}, headers=admin)).status_code == 422
    assert (await c.put("/api/v1/org/settings", json={"timezone": "Mars/Olympus"}, headers=admin)).status_code == 422
    pub = (await c.get("/api/v1/org/public")).json()
    assert pub["name"] == "Acıbadem Üniversitesi" and pub["login_message"].startswith("Derslik")
    _, teacher = await env.user("ayar@uni.edu.tr")
    ctx = (await c.get("/api/v1/bookings/context", headers=teacher)).json()
    assert ctx["display"]["type"] == "room" and ctx["limits"]["max_active_bookings"] == 5

    t = await c.put(
        "/api/v1/org/translations",
        json=[{"language": "tr", "set": "booking", "key": "booking.book", "text": "Ayırt "}],
        headers=admin,
    )
    assert t.status_code == 200 and t.json()[0]["text"] == "Ayırt "
    again = await c.put(
        "/api/v1/org/translations",
        json=[{"language": "tr", "set": "booking", "key": "booking.book", "text": "Rezerve et"}],
        headers=admin,
    )
    assert again.json()[0]["id"] == t.json()[0]["id"]
    assert [
        x["text"] for x in (await c.get("/api/v1/org/translations", params={"language": "tr"}, headers=teacher)).json()
    ] == ["Rezerve et"]
    assert (await c.put("/api/v1/org/translations", json=[], headers=teacher)).status_code == 403

    log = (await c.get("/api/v1/org/changelog", headers=teacher)).json()
    assert log["entries"] and log["entries"][0]["sections"] and log["unread"] is True
    await c.post("/api/v1/org/changelog/seen", headers=teacher)
    assert (await c.get("/api/v1/org/changelog", headers=teacher)).json()["unread"] is False
    ev = (await c.get("/api/v1/org/events", headers=admin)).json()
    assert "booking.created" in ev["events"] and ev["listeners"]["booking.created"]
    status = (await c.get("/api/v1/org/setup-status")).json()
    assert status["setup_required"] is False and status["checks"]["schedules"] == 1


@pytest.fixture
async def empty_client(tmp_path, monkeypatch) -> AsyncIterator[AsyncClient]:
    """A fresh install: tables exist, nobody has signed up yet (ADMIN_EMAIL not seeded)."""
    eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{tmp_path}/fresh.db")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


async def test_first_run_setup_wizard(empty_client):
    c = empty_client
    assert (await c.get("/api/v1/org/public")).json()["setup_required"] is True
    r = await c.post(
        "/api/v1/org/setup",
        json={
            "org_name": "Acıbadem Üniversitesi",
            "admin_email": "Yonetici@Uni.edu.tr",
            "admin_username": "Yönetici",
            "admin_password": "kurulum-parolası",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "yonetici@uni.edu.tr" and r.json()["username"] == "yönetici"
    again = await c.post(
        "/api/v1/org/setup",
        json={"org_name": "X", "admin_email": "x@y.z", "admin_password": "12345678"},
    )
    assert again.status_code == 409
    h = await login(c, "yonetici@uni.edu.tr", "kurulum-parolası")
    me = (await c.get("/api/v1/auth/me", headers=h)).json()
    assert me["role"] == "ADMIN" and "setup.users" in me["permissions"]
    assert (
        await c.post("/api/v1/auth/login", json={"username": "YÖNETİCİ", "password": "kurulum-parolası"})
    ).status_code == 200
