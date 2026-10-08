"""Bookings on the real Bahar 2026 data: the published grid is the timetable. Real fixture rows used:

* A 101, Monday 16 Feb 2026: FZT 132 holds P4-P5, PDL 212 P7-P9, ACU177 P10-P11; P1-P3 are free.
* A 102, Thursdays: PSI 216 holds P3-P5 and PSI 330 P7-P9 in lecture weeks 2-15; P1 is free all term.
* 23 Nisan 2026 (Thursday) is the national holiday Ulusal Egemenlik ve Çocuk Bayramı.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from app.core import db as dbmod
from app.models import BookingSlot
from sqlalchemy.exc import IntegrityError

from tests.crbs_env import env  # noqa: F401
from tests.crbs_support import role_id

MON = date(2026, 2, 16)
THU = date(2026, 2, 19)


async def test_published_timetable_and_other_bookings_block_a_slot(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr", firstname="Ayşe", lastname="Yılmaz")
    _, mehmet = await env.user("mehmet.oz@uni.edu.tr")
    r = await env.book(ayse, "A101", MON, "P4")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "conflict" and detail["conflict"]["kind"] == "timetable"
    assert "FZT 132" in detail["message"]
    r = await env.book(ayse, "A101", MON, "P1", notes="Ölçme ve değerlendirme – İş güvenliği")
    assert r.status_code == 201, r.text
    mine = r.json()
    assert mine["room_name"] == "A 101" and mine["start_period"] == mine["end_period"] == 1
    assert mine["notes"] == "Ölçme ve değerlendirme – İş güvenliği" and mine["is_owner"]
    clash = await env.book(mehmet, "A101", MON, "P1")
    assert clash.status_code == 409 and clash.json()["detail"]["conflict"]["kind"] == "booking"

    grid = (
        await env.client.get(
            "/api/v1/bookings/grid",
            params={"display": "room", "date": MON.isoformat(), "room_id": env.rooms["A101"]},
            headers=mehmet,
        )
    ).json()
    slots = {(s["date"], s["period_id"]): s for s in grid["slots"]}
    p1 = slots[(MON.isoformat(), env.periods["P1"])]
    assert p1["status"] == "booked" and p1["reason"] == "single"
    # Teacher (data.sql) may read other users' notes but not who booked
    assert p1["booking"]["notes"].startswith("Ölçme") and p1["booking"]["user_id"] is None
    assert p1["booking"]["user_hidden"] is True
    p4 = slots[(MON.isoformat(), env.periods["P4"])]
    assert p4["status"] == "timetable" and p4["label"] == "FZT 132"
    assert slots[(MON.isoformat(), env.periods["P2"])]["status"] == "available"

    # the DB refuses a second active holder of the same room/date/period even without the service
    other = (await env.book(mehmet, "A101", MON, "P2")).json()
    async with dbmod.get_session_factory()() as s:
        s.add(BookingSlot(booking_id=other["id"], period=1, room_id=env.rooms["A101"], date=MON))
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()


async def test_unpublished_runs_do_not_block_but_activation_reports_conflicts(env):  # noqa: F811
    _, ayse = await env.user("ayse@uni.edu.tr")
    from app.models import ScheduleRun

    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, env.run_id)
        run.is_active = False
        await s.commit()
    r = await env.book(ayse, "A101", MON, "P4")
    assert r.status_code == 201, r.text  # FZT 132 is in an unpublished run now
    r = await env.client.post(f"/api/v1/runs/{env.run_id}/activate", headers=env.planner)
    assert r.status_code == 200
    conflicts = (
        await env.client.get("/api/v1/bookings/conflicts", params={"term_id": env.term_id}, headers=env.planner)
    ).json()
    assert len(conflicts) == 1 and conflicts[0]["held"]["label"] == "FZT 132"


async def test_recurring_series_skips_holidays_and_timetable_and_respects_limit(env):  # noqa: F811
    hol = await env.client.post(
        "/api/v1/holidays",
        json={
            "term_id": env.term_id,
            "name": "Ulusal Egemenlik ve Çocuk Bayramı",
            "date_start": "2026-04-23",
            "date_end": "2026-04-23",
        },
        headers=env.admin,
    )
    assert hol.status_code == 201, hol.text
    tid, teacher = await env.user("hoca@uni.edu.tr")
    assert (await env.book(teacher, "A102", date(2026, 3, 5), "P1", notes="Telafi")).status_code == 201
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": "2026-04-30",
        "notes": "PSİ 216 ek ders",
    }
    # Teacher (data.sql) has no book_recur.create
    assert (await env.client.post("/api/v1/bookings/recurring/preview", json=body, headers=teacher)).status_code == 403
    prev = (await env.client.post("/api/v1/bookings/recurring/preview", json=body, headers=env.planner)).json()
    dates = [i["date"] for i in prev["instances"]]
    assert "2026-04-23" not in dates and len(dates) == 10 and dates[0] == "2026-02-19" and dates[-1] == "2026-04-30"
    booked = [i for i in prev["instances"] if i["status"] == "booked"]
    assert [i["date"] for i in booked] == ["2026-03-05"]
    assert booked[0]["actions"] == ["replace", "do_not_book"]  # planner may cancel others' bookings
    assert prev["bookable_count"] == 9 and prev["exceeds_by"] == 0

    timetable = (
        await env.client.post(
            "/api/v1/bookings/recurring/preview", json={**body, "period_id": env.periods["P3"]}, headers=env.planner
        )
    ).json()
    assert {i["status"] for i in timetable["instances"]} == {"timetable"}
    assert all(i["actions"] == ["do_not_book"] for i in timetable["instances"])
    r = await env.client.post(
        "/api/v1/bookings/recurring", json={**body, "period_id": env.periods["P3"]}, headers=env.planner
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "none_created"

    planner_role = await role_id(env.client, env.admin, "PLANNER")
    await env.client.put(f"/api/v1/roles/{planner_role}", json={"recur_max_instances": 4}, headers=env.admin)
    prev = (await env.client.post("/api/v1/bookings/recurring/preview", json=body, headers=env.planner)).json()
    assert prev["max_instances"] == 4 and prev["exceeds_by"] == 5
    res = await env.client.post(
        "/api/v1/bookings/recurring",
        json={**body, "instances": [{"date": "2026-03-05", "action": "replace"}]},
        headers=env.planner,
    )
    assert res.status_code == 201, res.text
    out = res.json()
    assert [b["date"] for b in out["created"]] == ["2026-02-19", "2026-02-26", "2026-03-05", "2026-03-12"]
    assert all(b["type"] == "recurring" and b["series_id"] == out["series_id"] for b in out["created"])
    assert [s["reason"] for s in out["skipped"]].count("recur_max_instances") == 6
    # the teacher's replaced booking is cancelled with a reason, and she was notified (outbox: no SMTP)
    mine = (await env.client.get("/api/v1/bookings/mine", params={"status": "ALL"}, headers=teacher)).json()
    replaced = next(b for b in mine if b["date"] == "2026-03-05")
    assert replaced["status"] == "CANCELLED" and replaced["cancel_reason"] == f"replaced by series #{out['series_id']}"
    outbox = (await env.client.get("/api/v1/booking-admin/outbox", headers=env.admin)).json()
    cancel_mail = next(o for o in outbox if o["kind"] == "booking_cancelled")
    assert cancel_mail["to_email"] == "hoca@uni.edu.tr" and cancel_mail["status"] == "UNSENT"
    assert cancel_mail["error"] == "SMTP is not configured"


async def test_cancel_one_future_all_and_owner_rules(env):  # noqa: F811
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": "2026-03-26",
    }
    out = (await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).json()
    ids = {b["date"]: b["id"] for b in out["created"]}
    assert list(ids) == ["2026-02-19", "2026-02-26", "2026-03-05", "2026-03-12", "2026-03-19", "2026-03-26"]
    c = env.client
    r = await c.post(
        f"/api/v1/bookings/{ids['2026-02-26']}/cancel", json={"scope": "one", "reason": "Sınav"}, headers=env.planner
    )
    assert r.json()["cancelled"] == [ids["2026-02-26"]]
    r = await c.post(f"/api/v1/bookings/{ids['2026-03-12']}/cancel", json={"scope": "future"}, headers=env.planner)
    assert sorted(r.json()["cancelled"]) == sorted([ids["2026-03-12"], ids["2026-03-19"], ids["2026-03-26"]])
    series = (await c.get(f"/api/v1/bookings/{ids['2026-02-19']}/series", headers=env.planner)).json()
    assert [b["status"] for b in series] == ["BOOKED", "CANCELLED", "BOOKED", "CANCELLED", "CANCELLED", "CANCELLED"]
    assert series[1]["cancel_reason"] == "Sınav"
    # a cancelled slot is free again
    _, teacher = await env.user("ogretmen@uni.edu.tr")
    assert (await env.book(teacher, "A102", date(2026, 2, 26), "P1")).status_code == 201
    r = await c.post(f"/api/v1/bookings/{ids['2026-02-19']}/cancel", json={"scope": "all"}, headers=env.planner)
    assert sorted(r.json()["cancelled"]) == sorted([ids["2026-02-19"], ids["2026-03-05"]])
    again = await c.post(f"/api/v1/bookings/{ids['2026-02-19']}/cancel", json={"scope": "one"}, headers=env.planner)
    assert again.status_code == 409

    # owners cancel their own future bookings; not past ones, and not other people's
    _, other = await env.user("diger@uni.edu.tr")
    b = (await env.book(teacher, "A101", MON, "P2")).json()
    assert (await c.post(f"/api/v1/bookings/{b['id']}/cancel", json={}, headers=other)).status_code == 403
    env.set_now(datetime(2026, 2, 17, 9, 0))
    assert (await c.post(f"/api/v1/bookings/{b['id']}/cancel", json={}, headers=teacher)).status_code == 403
    # admins hold the role-level cancel permission: no date restriction
    assert (await c.post(f"/api/v1/bookings/{b['id']}/cancel", json={}, headers=env.admin)).status_code == 200
    # cancel many: only those the user may cancel
    b1 = (await env.book(teacher, "A101", date(2026, 2, 18), "P11")).json()
    b2 = (await env.book(other, "A101", date(2026, 2, 18), "P12")).json()
    res = (
        await c.post("/api/v1/bookings/cancel-multi", json={"booking_ids": [b1["id"], b2["id"]]}, headers=teacher)
    ).json()
    assert res["cancelled"] == [b1["id"]] and res["skipped"] == [{"id": b2["id"], "reason": "not_cancelable"}]


async def test_limits_max_active_window_and_past(env):  # noqa: F811
    teacher_role = await role_id(env.client, env.admin, "TEACHER")
    await env.client.put(
        f"/api/v1/roles/{teacher_role}",
        json={"max_active_bookings": 2, "range_min": 1, "range_max": 10},
        headers=env.admin,
    )
    tid, teacher = await env.user("sinirli@uni.edu.tr")
    same_day = await env.book(teacher, "A101", MON, "P1")
    assert same_day.status_code == 409 and same_day.json()["detail"]["code"] == "range_min"
    far = await env.book(teacher, "A101", date(2026, 3, 2), "P1")
    assert far.status_code == 409 and far.json()["detail"]["code"] == "range_max"
    assert (await env.book(teacher, "A101", date(2026, 2, 17), "P1")).status_code == 201
    assert (await env.book(teacher, "A101", date(2026, 2, 18), "P11")).status_code == 201
    third = await env.book(teacher, "A101", date(2026, 2, 19), "P6")
    assert third.status_code == 409 and third.json()["detail"]["code"] == "max_active_bookings"
    grid = (
        await env.client.get("/api/v1/bookings/grid", params={"display": "day", "date": "2026-02-20"}, headers=teacher)
    ).json()
    assert {s["reason"] for s in grid["slots"] if s["status"] == "unavailable"} >= {"limit"}
    # a booking made for her by the planner does not count against her own limit (CRBS created_by rule)
    r = await env.book(env.planner, "A101", date(2026, 2, 20), "P1", user_id=tid)
    assert r.status_code == 201, r.text
    ctx = (await env.client.get("/api/v1/bookings/context", headers=teacher)).json()
    assert ctx["active_bookings"] == 2 and ctx["remaining_bookings"] == 0
    # user override X (unlimited) lifts the role limit
    await env.client.put(
        f"/api/v1/users/{tid}/constraints", json={"max_active_bookings": {"type": "X"}}, headers=env.admin
    )
    assert (await env.book(teacher, "A101", date(2026, 2, 19), "P6")).status_code == 201
    # past: a single-only user can never book yesterday, even without range limits
    await env.client.put(
        f"/api/v1/roles/{teacher_role}", json={"range_min": None, "range_max": None}, headers=env.admin
    )
    past = await env.book(teacher, "A101", date(2026, 2, 13), "P1")
    assert past.status_code == 409 and past.json()["detail"]["code"] == "range_min"


async def test_room_acl_by_department_and_access_checker(env):  # noqa: F811
    c = env.client
    deps = (await c.get("/api/v1/departments", params={"q": "PSİKOLOJİ"}, headers=env.admin)).json()
    psy = next(d for d in deps if d["name"].casefold().startswith("psikoloji"))
    role = (
        await c.post("/api/v1/roles", json={"name": "Misafir öğretim elemanı", "permissions": []}, headers=env.admin)
    ).json()
    uid, guest = await env.user("misafir@uni.edu.tr", role=None, role_id=role["id"], department_id=psy["id"])
    assert (await c.get("/api/v1/bookings/rooms", headers=guest)).json() == []
    acl = await c.post(
        "/api/v1/room-admin/acl",
        json={
            "entity_type": "room",
            "entity_id": env.rooms["A102"],
            "context_type": "department",
            "context_id": psy["id"],
            "permissions": ["room.view", "book_single.create"],
        },
        headers=env.admin,
    )
    assert acl.status_code == 201, acl.text
    assert acl.json()["context_label"] == psy["name"] and acl.json()["entity_label"] == "A 102"
    rooms = (await c.get("/api/v1/bookings/rooms", headers=guest)).json()
    assert [r["code"] for r in rooms] == ["A102"]
    assert (await env.book(guest, "A102", THU, "P1")).status_code == 201
    assert (await env.book(guest, "A101", MON, "P1")).status_code == 404  # A 101 is invisible to her
    bad = await c.post(
        "/api/v1/room-admin/acl",
        json={
            "entity_type": "room",
            "entity_id": env.rooms["A102"],
            "context_type": "user",
            "context_id": uid,
            "permissions": ["setup.users"],
        },
        headers=env.admin,
    )
    assert bad.status_code == 422
    check = (
        await c.get(
            "/api/v1/booking-admin/access-check",
            params={"user_id": uid, "room_id": env.rooms["A102"]},
            headers=env.admin,
        )
    ).json()
    assert check["from_role"] == [] and check["from_acl"] == ["book_single.create", "room.view"]
    assert check["effective"]["book_single"]["book_single.create"] is True
    assert check["effective"]["book_recur"]["book_recur.create"] is False
    # a group ACL on the A building grants every room of the group
    groups = (await c.post("/api/v1/room-admin/groups/from-buildings", headers=env.admin)).json()
    a_block = next(g for g in groups if env.rooms["A101"] in g["room_ids"])
    await c.post(
        "/api/v1/room-admin/acl",
        json={
            "entity_type": "room_group",
            "entity_id": a_block["id"],
            "context_type": "user",
            "context_id": uid,
            "permissions": ["room.view"],
        },
        headers=env.admin,
    )
    visible = {r["code"] for r in (await c.get("/api/v1/bookings/rooms", headers=guest)).json()}
    assert {"A101", "A102"} <= visible
    assert (await env.book(guest, "A101", MON, "P1")).status_code == 403  # can see, cannot book


async def test_multi_booking_selection_and_atomic_create(env):  # noqa: F811
    _, teacher = await env.user("coklu@uni.edu.tr")
    c = env.client
    slots = [
        {"date": MON.isoformat(), "period_id": env.periods[p], "room_id": env.rooms["A101"]} for p in ("P1", "P2", "P4")
    ]
    sel = await c.post("/api/v1/bookings/multi", json={"slots": slots}, headers=teacher)
    assert sel.status_code == 201, sel.text
    mb = sel.json()
    by_period = {s["period_id"]: s for s in mb["slots"]}
    assert by_period[env.periods["P4"]]["status"] == "timetable" and by_period[env.periods["P1"]]["status"] == "free"
    assert mb["can_book_single"] and not mb["can_book_recur"]
    r = await c.post(f"/api/v1/bookings/multi/{mb['id']}/create", json={"type": "single"}, headers=teacher)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "slots_unavailable"
    assert (await c.get("/api/v1/bookings/mine", headers=teacher)).json() == []  # nothing half-created
    p4 = by_period[env.periods["P4"]]["mbs_id"]
    dry = await c.post(
        f"/api/v1/bookings/multi/{mb['id']}/create",
        json={"type": "single", "dry_run": True, "slots": [{"mbs_id": p4, "create": False}]},
        headers=teacher,
    )
    assert dry.json() == {"dry_run": True, "problems": [], "would_create": 2}
    r = await c.post(
        f"/api/v1/bookings/multi/{mb['id']}/create",
        json={
            "type": "single",
            "slots": [
                {"mbs_id": p4, "create": False},
                {"mbs_id": by_period[env.periods["P1"]]["mbs_id"], "notes": "Kulüp toplantısı"},
            ],
        },
        headers=teacher,
    )
    assert r.status_code == 200, r.text
    created = r.json()["created"]
    assert [b["start_period"] for b in created] == [1, 2] and created[0]["notes"] == "Kulüp toplantısı"
    assert (await c.get(f"/api/v1/bookings/multi/{mb['id']}", headers=teacher)).status_code == 404  # consumed
    # setting the department needs book_single.set_department
    sel2 = (
        await c.post(
            "/api/v1/bookings/multi",
            json={"slots": [{"date": MON.isoformat(), "period_id": env.periods["P3"], "room_id": env.rooms["A101"]}]},
            headers=teacher,
        )
    ).json()
    r = await c.post(
        f"/api/v1/bookings/multi/{sel2['id']}/create",
        json={"type": "single", "slots": [{"mbs_id": sel2["slots"][0]["mbs_id"], "department_id": 1}]},
        headers=teacher,
    )
    assert r.status_code == 403


async def test_edit_scopes_and_field_rights(env):  # noqa: F811
    tid, teacher = await env.user("duzenle@uni.edu.tr")
    c = env.client
    b = (await env.book(teacher, "A101", MON, "P1", notes="ilk")).json()
    r = await c.put(
        f"/api/v1/bookings/{b['id']}", json={"period_id": env.periods["P2"], "notes": "İkinci saat"}, headers=teacher
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["start_period"] == 2 and r.json()[0]["notes"] == "İkinci saat"
    into_lecture = await c.put(f"/api/v1/bookings/{b['id']}", json={"period_id": env.periods["P4"]}, headers=teacher)
    assert into_lecture.status_code == 409 and into_lecture.json()["detail"]["conflict"]["label"] == "FZT 132"
    assert (await env.book(teacher, "A101", MON, "P1")).status_code == 201  # P1 was freed by the move
    admin_id = (await c.get("/api/v1/auth/me", headers=env.admin)).json()["id"]
    assert (await c.put(f"/api/v1/bookings/{b['id']}", json={"user_id": admin_id}, headers=teacher)).status_code == 403

    out = (
        await c.post(
            "/api/v1/bookings/recurring",
            json={
                "room_id": env.rooms["A102"],
                "period_id": env.periods["P1"],
                "date": THU.isoformat(),
                "start": THU.isoformat(),
                "end": "2026-03-12",
                "notes": "seri",
            },
            headers=env.planner,
        )
    ).json()
    ids = [x["id"] for x in out["created"]]
    r = await c.put(
        f"/api/v1/bookings/{ids[2]}", params={"scope": "future"}, json={"notes": "Ders kaydırıldı"}, headers=env.planner
    )
    assert [x["notes"] for x in r.json()] == ["Ders kaydırıldı", "Ders kaydırıldı"]
    series = (await c.get(f"/api/v1/bookings/{ids[0]}/series", headers=env.planner)).json()
    assert [x["notes"] for x in series] == ["seri", "seri", "Ders kaydırıldı", "Ders kaydırıldı"]
    moved = await c.put(
        f"/api/v1/bookings/{ids[0]}", params={"scope": "all"}, json={"room_id": env.rooms["A101"]}, headers=env.planner
    )
    assert moved.status_code == 403  # a whole series cannot be moved in time or space (UpdateAgent)
    detail = (await c.get(f"/api/v1/bookings/{ids[0]}", headers=env.planner)).json()
    assert detail["edit_features"]["all"]["room"] is False and detail["edit_features"]["one"]["room"] is True
    assert detail["room"]["code"] == "A102"


async def test_booking_for_another_user_notifies_and_shows_on_dashboard(env):  # noqa: F811
    tid, teacher = await env.user("adina@uni.edu.tr")
    c = env.client
    _, teacher2 = await env.user("baska@uni.edu.tr")
    assert (await env.book(teacher2, "A101", MON, "P2", user_id=tid)).status_code == 403  # no set_user
    r = await env.book(env.planner, "A101", date(2026, 2, 17), "P1", user_id=tid, notes="Fatih Bey ayırdı")
    assert r.status_code == 201 and r.json()["user_id"] == tid
    dash = (await c.get("/api/v1/bookings/dashboard", headers=teacher)).json()
    assert [b["date"] for b in dash["user_bookings"]] == ["2026-02-17"]
    assert dash["totals"]["active"] == 0 and dash["totals"]["all"] == 1  # created by someone else
    mail = next(
        o
        for o in (await c.get("/api/v1/booking-admin/outbox", headers=env.admin)).json()
        if o["kind"] == "booking_created"
    )
    assert mail["to_email"] == "adina@uni.edu.tr" and mail["status"] == "UNSENT" and "A 101" in mail["body"]
    # room owner dashboard: others' bookings in the room she owns
    await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['A102']}",
        json={"owner_user_id": tid, "location": "A Blok 1. kat"},
        headers=env.admin,
    )
    assert (await env.book(teacher2, "A102", THU, "P1")).status_code == 201
    dash = (await c.get("/api/v1/bookings/dashboard", headers=teacher)).json()
    assert [b["room_name"] for b in dash["room_bookings"]] == ["A 102"]
    owned = (await c.get("/api/v1/bookings/owned-rooms", headers=teacher)).json()
    assert owned[0]["location"] == "A Blok 1. kat" and len(owned[0]["upcoming"]) == 1
    # the owner ACL (CRBS migration) lets her cancel others' single bookings in her room
    other = owned[0]["upcoming"][0]
    assert (await c.post(f"/api/v1/bookings/{other['id']}/cancel", json={}, headers=teacher)).status_code == 200


async def test_show_names_setting_and_maintenance_mode(env):  # noqa: F811
    c = env.client
    _, a = await env.user("goster1@uni.edu.tr", displayname="Zeynep Şahin")
    _, b = await env.user("goster2@uni.edu.tr")
    bk = (await env.book(a, "A101", MON, "P1")).json()
    assert (await c.get(f"/api/v1/bookings/{bk['id']}", headers=b)).json()["user_name"] is None
    r = await c.put("/api/v1/org/settings", json={"bookings_show_name": True}, headers=env.admin)
    assert r.status_code == 200 and r.json()["bookings_show_name"] is True
    assert (await c.get(f"/api/v1/bookings/{bk['id']}", headers=b)).json()["user_name"] == "Zeynep Şahin"
    await c.put(
        "/api/v1/org/settings",
        json={"maintenance_mode": True, "maintenance_mode_message": "Bakımdayız"},
        headers=env.admin,
    )
    blocked = await c.get("/api/v1/bookings/context", headers=b)
    assert blocked.status_code == 503 and blocked.json()["detail"] == "Bakımdayız"
    assert (await c.get("/api/v1/bookings/context", headers=env.admin)).status_code == 200
    public = (await c.get("/api/v1/org/public")).json()
    assert public["maintenance_mode"] is True and public["maintenance_message"] == "Bakımdayız"


async def test_closed_dates_and_wrong_periods(env):  # noqa: F811
    _, teacher = await env.user("kapali@uni.edu.tr")
    c = env.client
    await c.post(
        "/api/v1/holidays",
        json={"term_id": env.term_id, "name": "Ara tatil", "date_start": "2026-02-17", "date_end": "2026-02-17"},
        headers=env.admin,
    )
    r = await env.book(teacher, "A101", date(2026, 2, 17), "P1")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "holiday"
    # timetable weeks: once mapped, unmapped dates are closed (CRBS)
    wk = (
        await c.post("/api/v1/booking-admin/weeks", json={"name": "A Haftası", "bgcol": "#71aae3"}, headers=env.admin)
    ).json()
    assert wk["bgcol"] == "#71AAE3" and wk["fgcol"] == "#ffffff"  # brightness 159.5 <= 160: white text
    await c.put(
        f"/api/v1/booking-admin/sessions/{env.term_id}/dates",
        json={"dates": {"2026-02-18": wk["id"]}},
        headers=env.admin,
    )
    r = await env.book(teacher, "A101", date(2026, 2, 19), "P1")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_week"
    assert (await env.book(teacher, "A101", date(2026, 2, 18), "P11")).status_code == 201
    # a period not available on that weekday
    await c.put(f"/api/v1/booking-admin/periods/{env.periods['P1']}", json={"days": [1, 2, 3, 4, 5]}, headers=env.admin)
    await c.post(
        f"/api/v1/booking-admin/sessions/{env.term_id}/apply-week",
        json={"timetable_week_id": wk["id"]},
        headers=env.admin,
    )
    r = await env.book(teacher, "A101", date(2026, 2, 21), "P1")
    assert r.status_code == 409 and "not available" in r.json()["detail"]["message"]
