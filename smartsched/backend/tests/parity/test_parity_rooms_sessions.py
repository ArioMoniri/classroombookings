"""CRBS parity — room custom TEXT fields, rooms that are not bookable, selectable sessions, periods that are
not bookable, editing / deleting timetable weeks and holidays. Real data: the Bahar 2026 import
(``tests/crbs_env``): A 101 Monday 16 Feb P1-P3 free, A 102 Thursdays P1 free all term."""

from __future__ import annotations

from datetime import date

import pytest

MON = date(2026, 2, 16)
TUE = date(2026, 2, 17)
WED = date(2026, 2, 18)
THU = date(2026, 2, 19)


@pytest.mark.parity("B-ROOMS-05")
async def test_text_custom_field_holds_turkish_text(env):
    """``setup/rooms/Fields`` TEXT type: free text per room, shown on the room card."""
    c = env.client
    f = await c.post("/api/v1/room-admin/fields", json={"name": "Anahtar", "type": "TEXT"}, headers=env.admin)
    assert f.status_code == 201, f.text
    fid = str(f.json()["id"])
    r = await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['A105']}/fields",
        json={fid: "Güvenlik\xa0masası – İç kapı"},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    info = (await c.get(f"/api/v1/bookings/rooms/{env.rooms['A105']}", headers=env.planner)).json()
    assert {x["name"]: x["value"] for x in info["fields"]}["Anahtar"] == "Güvenlik masası – İç kapı"
    assert (await c.get(f"/api/v1/rooms/{env.rooms['A105']}", headers=env.planner)).json()["custom_fields"][
        "Anahtar"
    ] == "Güvenlik masası – İç kapı"


@pytest.mark.parity("B-ROOMS-09")
async def test_rooms_that_are_not_bookable_leave_the_grid(env):
    """``Rooms_model::get_bookable_rooms``: only rooms marked bookable are offered, to everyone."""
    c = env.client
    _, teacher = await env.user("oda.kapali@uni.edu.tr")
    codes = {r["code"] for r in (await c.get("/api/v1/bookings/rooms", headers=teacher)).json()}
    assert "A101" in codes
    r = await c.put(f"/api/v1/room-admin/rooms/{env.rooms['A101']}", json={"is_bookable": False}, headers=env.admin)
    assert r.status_code == 200 and r.json()["is_bookable"] is False
    for who in (teacher, env.admin):
        codes = {r["code"] for r in (await c.get("/api/v1/bookings/rooms", headers=who)).json()}
        assert "A101" not in codes
        grid = (await c.get("/api/v1/bookings/grid", params={"date": MON.isoformat()}, headers=who)).json()
        assert "A 101" not in [x["name"] for x in grid["rooms"]]
    refused = await env.book(teacher, "A101", MON, "P1")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "room_not_bookable"
    await c.put(f"/api/v1/room-admin/rooms/{env.rooms['A101']}", json={"is_bookable": True}, headers=env.admin)
    assert (await env.book(teacher, "A101", MON, "P1")).status_code == 201


@pytest.mark.parity("B-SESS-05")
async def test_only_selectable_sessions_unless_view_all_sessions(env):
    """``Bookings::change_session`` / ``Sessions_model::get_available_session``: staff pick among selectable
    sessions; ``system.view_all_sessions`` (Planner, Administrator) reaches the others too."""
    c = env.client
    yaz = await c.post(
        "/api/v1/terms",
        json={"code": "2026-YAZ", "name": "2026 Yaz Okulu", "start_date": "2026-07-06", "end_date": "2026-08-21"},
        headers=env.planner,
    )
    assert yaz.status_code == 201, yaz.text
    yid = yaz.json()["id"]
    r = await c.put(
        f"/api/v1/booking-admin/sessions/{yid}",
        json={"is_selectable": False, "default_schedule_id": env.schedule_id},
        headers=env.admin,
    )
    assert r.status_code == 200 and r.json()["is_selectable"] is False
    _, teacher = await env.user("yaz.okulu@uni.edu.tr")
    staff = {s["id"] for s in (await c.get("/api/v1/bookings/context", headers=teacher)).json()["sessions"]}
    assert env.term_id in staff and yid not in staff
    planner = {s["id"] for s in (await c.get("/api/v1/bookings/context", headers=env.planner)).json()["sessions"]}
    assert {env.term_id, yid} <= planner
    july = date(2026, 7, 6)
    refused = await env.book(teacher, "A101", july, "P1", term_id=yid)
    assert refused.status_code == 409, refused.text
    assert (await c.get("/api/v1/bookings/grid", params={"term_id": yid, "date": july.isoformat()}, headers=teacher)).status_code == 409
    ok = await env.book(env.planner, "A101", july, "P1", term_id=yid)
    assert ok.status_code == 201 and ok.json()["term_id"] == yid, ok.text
    # opening the session lets staff in
    await c.put(f"/api/v1/booking-admin/sessions/{yid}", json={"is_selectable": True}, headers=env.admin)
    assert (await env.book(teacher, "A101", july, "P2", term_id=yid)).status_code == 201


@pytest.mark.parity("B-SESS-08")
async def test_periods_that_are_not_bookable_are_not_offered(env):
    """``Periods`` ``bookable`` flag: CRBS's grid loads only bookable periods (Context::init_periods)."""
    c = env.client
    _, teacher = await env.user("ogle.arasi@uni.edu.tr")
    r = await c.put(f"/api/v1/booking-admin/periods/{env.periods['P6']}", json={"bookable": False}, headers=env.admin)
    assert r.status_code == 200 and r.json()["bookable"] is False
    grid = (await c.get("/api/v1/bookings/grid", params={"date": MON.isoformat()}, headers=teacher)).json()
    names = [p["name"] for p in grid["periods"]]
    assert "P6" not in names and "P5" in names and "P7" in names
    refused = await env.book(teacher, "A101", MON, "P6")
    assert refused.status_code == 409 and "not bookable" in refused.json()["detail"]["message"]


@pytest.mark.parity("B-SESS-10")
async def test_timetable_weeks_can_be_recoloured_and_deleted(env):
    """``Weeks`` edit / delete: the text colour follows the background (``colour_brightness``) and deleting a
    week clears it from the session calendar (``Weeks_model::delete`` -> ``dates_model->clear``)."""
    c = env.client
    _, teacher = await env.user("hafta.renk@uni.edu.tr")
    wk = (
        await c.post("/api/v1/booking-admin/weeks", json={"name": "A Haftası", "bgcol": "FFF2CC"}, headers=env.admin)
    ).json()
    assert wk["fgcol"] == "#000000"
    up = await c.put(
        f"/api/v1/booking-admin/weeks/{wk['id']}", json={"name": "Tek hafta", "bgcol": "#1F3864"}, headers=env.admin
    )
    assert up.status_code == 200 and up.json()["fgcol"] == "#ffffff" and up.json()["name"] == "Tek hafta"
    await c.put(
        f"/api/v1/booking-admin/sessions/{env.term_id}/dates", json={"dates": {WED.isoformat(): wk["id"]}}, headers=env.admin
    )
    closed = await env.book(teacher, "A101", THU, "P1")
    assert closed.status_code == 409 and closed.json()["detail"]["code"] == "no_week"
    assert (await c.delete(f"/api/v1/booking-admin/weeks/{wk['id']}", headers=env.admin)).status_code == 204
    days = (await c.get(f"/api/v1/booking-admin/sessions/{env.term_id}/dates", headers=env.admin)).json()
    assert all(d.get("timetable_week_id") is None for d in days["dates"]), days["dates"][:3]
    # no week mapped any more: every date is open again (a term without weeks recurs weekly)
    assert (await env.book(teacher, "A101", THU, "P1")).status_code == 201


@pytest.mark.parity("B-SESS-12")
async def test_holidays_can_be_moved_and_deleted(env):
    """``Holidays`` edit / delete (``Dates_model::refresh_holidays``): the closed dates follow the holiday."""
    c = env.client
    _, teacher = await env.user("tatil.tasi@uni.edu.tr")
    h = await c.post(
        "/api/v1/holidays",
        json={"term_id": env.term_id, "name": "Kurum\xa0içi eğitim günü", "date_start": TUE.isoformat(), "date_end": TUE.isoformat()},
        headers=env.admin,
    )
    assert h.status_code == 201 and h.json()["name"] == "Kurum içi eğitim günü", h.text
    hid = h.json()["id"]
    assert (await env.book(teacher, "A101", TUE, "P1")).json()["detail"]["code"] == "holiday"
    moved = await c.put(
        f"/api/v1/holidays/{hid}", json={"date_start": WED.isoformat(), "date_end": WED.isoformat()}, headers=env.admin
    )
    assert moved.status_code == 200 and moved.json()["date_start"] == WED.isoformat(), moved.text
    assert (await env.book(teacher, "A101", TUE, "P1")).status_code == 201
    assert (await env.book(teacher, "A101", WED, "P11")).json()["detail"]["code"] == "holiday"
    listed = (await c.get("/api/v1/holidays", params={"term_id": env.term_id}, headers=teacher)).json()
    assert [x["name"] for x in listed] == ["Kurum içi eğitim günü"]
    _, other = await env.user("tatil.yetkisiz@uni.edu.tr")
    assert (await c.delete(f"/api/v1/holidays/{hid}", headers=other)).status_code == 403
    assert (await c.delete(f"/api/v1/holidays/{hid}", headers=env.admin)).status_code == 204
    assert (await env.book(teacher, "A101", WED, "P11")).status_code == 201
