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
