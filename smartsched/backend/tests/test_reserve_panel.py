"""Reservation panel additions on the real Bahar 2026 data (the published weekly grid is the timetable):

* ``GET /bookings/rooms/{id}`` carries exam capacity, building and floor for the room details panel;
* ``GET /bookings/departments/{id}/rooms`` lists the rooms a department uses most: its bookings in the
  session plus its classes in the published timetable (PSİKOLOJİ teaches PSI 216 / PSI 330 in A 102).
"""

from __future__ import annotations

from datetime import date

from tests.crbs_env import env  # noqa: F401

MON = date(2026, 2, 16)


async def _psychology(env):  # type: ignore[no-untyped-def]  # noqa: F811
    deps = (await env.client.get("/api/v1/departments", params={"q": "PSİKOLOJİ"}, headers=env.admin)).json()
    return next(d for d in deps if d["name"].casefold().startswith("psikoloji"))


async def test_room_details_carry_exam_capacity_building_and_floor(env):  # noqa: F811
    _, teacher = await env.user("oda.bilgi@uni.edu.tr")
    r = await env.client.get(f"/api/v1/bookings/rooms/{env.rooms['A101']}", headers=teacher)
    assert r.status_code == 200, r.text
    room = r.json()
    assert room["name"] == "A 101"
    assert {"exam_capacity", "building", "building_code", "floor"} <= room.keys()
    assert isinstance(room["exam_capacity"], int)
    assert room["building"], "A 101 belongs to a building in the room master"
    listed = (await env.client.get("/api/v1/bookings/rooms", headers=teacher)).json()
    assert all("exam_capacity" in x and "building" in x for x in listed)


async def test_department_rooms_count_bookings_and_timetable_classes(env):  # noqa: F811
    psy = await _psychology(env)
    _, teacher = await env.user("bolum.oda@uni.edu.tr", department_id=psy["id"])
    # a booking in A 101 for the teacher's own department (CRBS: the user's department by default)
    made = await env.book(teacher, "A101", MON, "P1")
    assert made.status_code == 201, made.text
    assert made.json()["department_id"] == psy["id"]

    r = await env.client.get(
        f"/api/v1/bookings/departments/{psy['id']}/rooms", params={"term_id": env.term_id, "limit": 50}, headers=teacher
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["department"] == {"id": psy["id"], "name": psy["name"]}
    assert body["term_id"] == env.term_id
    by_code = {x["code"]: x for x in body["rooms"]}
    assert by_code["A101"]["bookings"] == 1
    # PSI 216 and PSI 330 are taught in A 102 on Thursdays in the published grid
    assert by_code["A102"]["classes"] >= 1
    totals = [x["bookings"] + x["classes"] for x in body["rooms"]]
    assert totals == sorted(totals, reverse=True)

    # without a term: the session of today's booking clock; a limit trims the list
    r = await env.client.get(f"/api/v1/bookings/departments/{psy['id']}/rooms", params={"limit": 1}, headers=teacher)
    assert r.status_code == 200 and len(r.json()["rooms"]) == 1

    # cancelled bookings do not count
    await env.client.post(f"/api/v1/bookings/{made.json()['id']}/cancel", json={"scope": "one"}, headers=teacher)
    r = await env.client.get(
        f"/api/v1/bookings/departments/{psy['id']}/rooms", params={"term_id": env.term_id, "limit": 50}, headers=teacher
    )
    assert {x["code"]: x for x in r.json()["rooms"]}.get("A101", {"bookings": 0})["bookings"] == 0


async def test_department_rooms_unknown_department_is_404(env):  # noqa: F811
    _, teacher = await env.user("bolum.yok@uni.edu.tr")
    r = await env.client.get("/api/v1/bookings/departments/999999/rooms", headers=teacher)
    assert r.status_code == 404


# --- CRBS UI gap audit (2026-10-08) items the reservation panel needs from the API ------------------


async def test_grid_slots_say_who_may_cancel_and_rooms_carry_the_owner(env):  # noqa: F811
    _, ayse = await env.user("iptal.ayse@uni.edu.tr")
    _, mehmet = await env.user("iptal.mehmet@uni.edu.tr")
    made = await env.book(ayse, "A101", MON, "P2")
    assert made.status_code == 201, made.text
    params = {"display": "room", "date": MON.isoformat(), "room_id": env.rooms["A101"]}

    async def p2(headers):  # type: ignore[no-untyped-def]
        grid = (await env.client.get("/api/v1/bookings/grid", params=params, headers=headers)).json()
        assert all("owner" in r for r in grid["rooms"])
        return next(s for s in grid["slots"] if s["date"] == MON.isoformat() and s["period_id"] == env.periods["P2"])

    assert (await p2(ayse))["booking"]["can_cancel"] is True  # own booking
    assert (await p2(mehmet))["booking"]["can_cancel"] is False  # someone else's, no cancel permission
    assert (await p2(env.admin))["booking"]["can_cancel"] is True  # administrators cancel any booking


async def test_context_room_groups_count_their_rooms(env):  # noqa: F811
    await env.client.post("/api/v1/room-admin/groups/from-buildings", headers=env.admin)
    _, teacher = await env.user("grup.sayi@uni.edu.tr")
    ctx = (await env.client.get("/api/v1/bookings/context", headers=teacher)).json()
    rooms = (await env.client.get("/api/v1/bookings/rooms", headers=teacher)).json()
    assert ctx["room_groups"], "room groups were made from the buildings"
    for g in ctx["room_groups"]:
        assert g["room_count"] == sum(1 for r in rooms if (r["room_group_id"] or 0) == g["id"])


async def test_booking_users_needs_set_user_not_setup_users(env):  # noqa: F811
    _, teacher = await env.user("kim.teacher@uni.edu.tr", firstname="Kerem", lastname="Ünal")
    assert (await env.client.get("/api/v1/bookings/users", headers=teacher)).status_code == 403
    r = await env.client.get("/api/v1/bookings/users", params={"q": "ünal"}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert [u["name"] for u in r.json()] == ["Kerem Ünal"]
    # a role with set_user but without setup.users may list them too
    role = (
        await env.client.post(
            "/api/v1/roles",
            json={"name": "Bölüm sekreteri", "permissions": ["book_single.create", "book_single.set_user"]},
            headers=env.admin,
        )
    ).json()
    _, secretary = await env.user("sekreter@uni.edu.tr", role=None, role_id=role["id"])
    r = await env.client.get("/api/v1/bookings/users", params={"q": "kerem"}, headers=secretary)
    assert r.status_code == 200 and r.json()[0]["name"] == "Kerem Ünal"


async def test_multi_recurring_honours_per_date_choices(env):  # noqa: F811
    teacher = env.admin  # recurring bookings need book_recur.create (Teacher has only single bookings)
    sel = await env.client.post(
        "/api/v1/bookings/multi",
        json={"slots": [{"date": MON.isoformat(), "period_id": env.periods["P1"], "room_id": env.rooms["A101"]}]},
        headers=teacher,
    )
    assert sel.status_code == 201, sel.text
    mbs = sel.json()["slots"][0]["mbs_id"]
    skip = date(2026, 2, 23).isoformat()
    r = await env.client.post(
        f"/api/v1/bookings/multi/{sel.json()['id']}/create",
        json={
            "type": "recurring",
            "slots": [
                {"mbs_id": mbs, "recurring_end": "2026-03-09", "instances": [{"date": skip, "action": "do_not_book"}]}
            ],
        },
        headers=teacher,
    )
    assert r.status_code in (200, 201), r.text
    created = [b["date"] for s in r.json()["series"] for b in s["created"]]
    assert MON.isoformat() in created and skip not in created
    assert "2026-03-02" in created
