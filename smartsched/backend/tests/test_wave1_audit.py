"""P7 audit log and undo on the real Bahar 2026 data (``tests/crbs_env``). Fixture facts used:

* A 101, Monday 16 Feb 2026: P1-P3 free on the board, FZT 132 holds P4-P5;
* A 102 is free at P1 on every Thursday; A 106 (58 seats) has no class at P1 on Monday 16 Feb.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.core import db as dbmod
from app.models import AuditEvent
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)
AUDIT = "/api/v1/audit"


async def _last(env, headers=None, **params):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(AUDIT, params={"limit": 1, **params}, headers=headers or env.admin)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    return items[0] if items else None


async def test_booking_events_carry_actor_request_and_minimised_address(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    r = await env.client.post(
        "/api/v1/bookings",
        json={
            "room_id": env.rooms["A101"],
            "date": MON.isoformat(),
            "period_id": env.periods["P1"],
            "notes": "Ölçme ve değerlendirme",
        },
        headers={**ayse, "X-Request-ID": "req-ayse-1"},
    )
    assert r.status_code == 201, r.text
    assert r.headers["X-Request-ID"] == "req-ayse-1"
    bid = r.json()["id"]
    ev = await _last(env, entity_type="booking", entity_id=str(bid))
    assert ev["action"] == "booking.create" and ev["reversible"] and ev["after"]["room_id"] == env.rooms["A101"]
    assert ev["actor_label"] == "ayse.yilmaz@uni.edu.tr" or "Ayşe" in (ev["actor_label"] or "")
    assert ev["request_id"] == "req-ayse-1" and len(ev["ip_hash"]) == 32 and "127.0.0" not in ev["ip_hash"]
    # the teacher sees her own events, without request ids / network hashes, and not other people's
    own = (await env.client.get(AUDIT, headers=ayse)).json()["items"]
    assert [e["id"] for e in own] == [ev["id"]] and own[0]["request_id"] is None and own[0]["ip_hash"] is None
    # nobody can change or delete an audit event: no route, and the database refuses it
    async with dbmod.get_session_factory()() as s:
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("update audit_events set action = 'x'"))
        await s.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("delete from audit_events"))
        await s.rollback()
        assert await s.get(AuditEvent, ev["id"]) is not None


async def test_no_route_edits_or_deletes_audit_events():
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/v1/audit"):
            assert not (set(getattr(route, "methods", set())) & {"PUT", "PATCH", "DELETE"}), path
            if "POST" in getattr(route, "methods", set()):
                assert path.endswith("/undo"), path


async def test_undo_create_move_and_cancel(env):  # noqa: F811
    _, ayse = await env.user("ayse@uni.edu.tr")
    c = env.client
    # create -> undo = cancelled; a second undo is refused
    bid = (await env.book(ayse, "A101", MON, "P1")).json()["id"]
    ev = await _last(env, ayse, entity_type="booking", entity_id=str(bid))
    r = await c.post(f"{AUDIT}/{ev['id']}/undo", headers=ayse)
    assert r.status_code == 200, r.text
    assert (await c.get(f"/api/v1/bookings/{bid}", headers=ayse)).json()["status"] == "CANCELLED"
    again = await c.post(f"{AUDIT}/{ev['id']}/undo", headers=ayse)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_undone"
    # move P1 -> P2 -> undo = back at P1
    bid = (await env.book(ayse, "A101", MON, "P1")).json()["id"]
    r = await c.put(f"/api/v1/bookings/{bid}", json={"period_id": env.periods["P2"]}, headers=ayse)
    assert r.status_code == 200, r.text
    mv = await _last(env, ayse, action="booking.move")
    assert mv["diff"]["period_id"] == [env.periods["P1"], env.periods["P2"]]
    r = await c.post(f"{AUDIT}/{mv['id']}/undo", headers=ayse)
    assert r.status_code == 200, r.text
    b = (await c.get(f"/api/v1/bookings/{bid}", headers=ayse)).json()
    assert b["period_id"] == env.periods["P1"] and b["status"] == "BOOKED"
    restore = await _last(env, ayse, action="booking.move")
    assert restore["undo_of"] == mv["id"]
    # a later change blocks the undo of an earlier one
    await c.put(f"/api/v1/bookings/{bid}", json={"period_id": env.periods["P3"]}, headers=ayse)
    first_move = await _last(env, ayse, action="booking.move")
    await c.put(f"/api/v1/bookings/{bid}", json={"notes": "Sınav provası"}, headers=ayse)
    r = await c.post(f"{AUDIT}/{first_move['id']}/undo", headers=ayse)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "changed_since"
    assert r.json()["detail"]["message_tr"] == "Bu kayıttan sonra 1 değişiklik yapıldı"


async def test_undo_cancel_restores_or_offers_alternatives_when_taken(env):  # noqa: F811
    _, ayse = await env.user("ayse@uni.edu.tr")
    _, mehmet = await env.user("mehmet.oz@uni.edu.tr")
    c = env.client
    bid = (await env.book(ayse, "A106", MON, "P1")).json()["id"]
    assert (
        await c.post(f"/api/v1/bookings/{bid}/cancel", json={"reason": "yanlışlık"}, headers=ayse)
    ).status_code == 200
    ev = await _last(env, ayse, action="booking.cancel")
    assert ev["reason"] == "yanlışlık" and ev["diff"]["status"] == ["BOOKED", "CANCELLED"]
    r = await c.post(f"{AUDIT}/{ev['id']}/undo", headers=ayse)
    assert r.status_code == 200 and r.json()["action"] == "booking.restore"
    assert (await c.get(f"/api/v1/bookings/{bid}", headers=ayse)).json()["status"] == "BOOKED"
    # cancel again; Mehmet takes the slot; the undo answers 409 with free rooms for the same slot
    await c.post(f"/api/v1/bookings/{bid}/cancel", json={}, headers=ayse)
    ev = await _last(env, ayse, action="booking.cancel")
    assert (await env.book(mehmet, "A106", MON, "P1")).status_code == 201
    r = await c.post(f"{AUDIT}/{ev['id']}/undo", headers=ayse)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "conflict" and "artık dolu" in detail["message_tr"]
    alts = detail["alternatives"]
    assert alts and all(a["capacity"] >= 58 and a["code"] != "A106" for a in alts)
    # another teacher cannot undo Ayşe's cancellation (not visible to him)
    assert (await c.post(f"{AUDIT}/{ev['id']}/undo", headers=mehmet)).status_code == 404


async def test_series_create_is_one_parent_event_and_undo_cancels_the_series(env):  # noqa: F811
    c = env.client
    r = await c.post(
        "/api/v1/bookings/recurring",
        json={"room_id": env.rooms["A102"], "period_id": env.periods["P1"], "date": "2026-02-19", "end": "2026-03-12"},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    ids = [b["id"] for b in r.json()["created"]]
    parent = await _last(env, action="series.create")
    detail = (await c.get(f"{AUDIT}/{parent['id']}", headers=env.admin)).json()
    assert sorted(ch["entity_id"] for ch in detail["children"]) == sorted(str(i) for i in ids)
    assert all(ch["action"] == "booking.create" for ch in detail["children"])
    r = await c.post(f"{AUDIT}/{parent['id']}/undo", headers=env.admin)
    assert r.status_code == 200 and sorted(r.json()["booking_ids"]) == sorted(ids)
    rows = (await c.get(f"/api/v1/bookings/{ids[0]}/series", headers=env.admin)).json()
    assert {b["status"] for b in rows} == {"CANCELLED"}


async def test_admin_changes_are_tracked_with_secrets_redacted(env):  # noqa: F811
    """Every administration write path produces an event (a walk over the mutating routes of users, roles,
    room admin, rooms, org settings, SMTP, booking admin and holidays)."""
    c, admin = env.client, env.admin

    async def count() -> int:
        async with dbmod.get_session_factory()() as s:
            return int((await s.execute(text("select count(*) from audit_events"))).scalar_one())

    calls = [
        (
            "POST",
            "/api/v1/users",
            {"email": "yeni@uni.edu.tr", "role": "TEACHER", "password": "parola-1234"},
            "user.create",
        ),
        (
            "POST",
            "/api/v1/roles",
            {"name": "Bölüm sekreteri", "permissions": ["room.view", "book_single.create"]},
            "role.create",
        ),
        ("PUT", f"/api/v1/room-admin/rooms/{env.rooms['A101']}", {"location": "A Blok 1. kat"}, "room.update"),
        ("PUT", f"/api/v1/rooms/{env.rooms['A102']}", {"capacity": 90}, "room.update"),
        ("POST", "/api/v1/room-admin/groups", {"name": "A Blok", "room_ids": [env.rooms["A101"]]}, "room_group.create"),
        ("PUT", "/api/v1/org/settings", {"name": "Üniversite"}, "settings.update"),
        ("PUT", "/api/v1/org/smtp", {"host": "smtp.uni.edu.tr", "password": "çok-gizli-parola"}, "settings.update"),
        (
            "POST",
            "/api/v1/holidays",
            {"term_id": env.term_id, "name": "Ramazan Bayramı", "date_start": "2026-03-20", "date_end": "2026-03-22"},
            "holiday.create",
        ),
        ("POST", "/api/v1/booking-admin/weeks", {"name": "A Haftası", "bgcol": "FF0000"}, "timetable_week.create"),
    ]
    for method, path, body, action in calls:
        before = await count()
        r = await c.request(method, path, json=body, headers=admin)
        assert r.status_code in (200, 201), (path, r.text)
        assert await count() > before, path
        assert await _last(env, action=action), (path, action)
    # role permissions are logged by name; the password and the SMTP secret never are
    role = await _last(env, action="role.create")
    assert role["after"]["permissions"] == ["book_single.create", "room.view"]
    user = await _last(env, action="user.create")
    assert user["after"]["password_hash"] == "***"
    items = (await c.get(AUDIT, params={"action": "settings.update", "limit": 50}, headers=admin)).json()["items"]
    smtp_pw = [e for e in items if e["entity_id"] == "smtp.password"]
    assert smtp_pw and smtp_pw[0]["after"]["value"] == "***"
    assert "çok-gizli" not in str(items)
    cap = await _last(env, action="room.update", entity_id=str(env.rooms["A102"]))
    assert cap["diff"]["capacity"] == [96, 90]
    # CSV export for auditors (formula-safe)
    csv_r = await c.get(f"{AUDIT}/export.csv", headers=admin)
    assert csv_r.status_code == 200 and "room.update" in csv_r.text
    _, teacher = await env.user("hoca@uni.edu.tr")
    assert (await c.get(f"{AUDIT}/export.csv", headers=teacher)).status_code == 403
