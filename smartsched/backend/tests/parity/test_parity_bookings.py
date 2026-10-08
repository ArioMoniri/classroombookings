"""CRBS parity — bookings: recurring series that follow the timetable week (A/B rotation), "session" as the
series start/end, the recurring slot state, notes, department, multi-booking selections, who may open a
booking, my-bookings filters and the export's room group filter.

Real data (``tests/crbs_env``, Bahar 2026 published weekly grid, term 2026-02-02 .. 2026-06-28, clock Monday
16 Feb 2026 08:00): A 101 Monday 16 Feb P1-P3 free (FZT 132 holds P4-P5); A 102 Thursdays P1 free all term."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import pytest

from tests.api_fixtures import login
from tests.crbs_support import role_id

MON = date(2026, 2, 16)
THU = date(2026, 2, 19)
TERM_START = date(2026, 2, 2)
TERM_END = date(2026, 6, 28)


def _thursdays(start: date, end: date) -> list[date]:
    d = start + timedelta(days=(3 - start.weekday()) % 7)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


async def _closed_dates(env) -> set[str]:  # type: ignore[no-untyped-def]
    """Dates the term calendar itself closes (whole HOLIDAY weeks of the imported calendar)."""
    r = await env.client.get(
        "/api/v1/bookings/dates",
        params={"from": TERM_START.isoformat(), "to": TERM_END.isoformat()},
        headers=env.planner,
    )
    assert r.status_code == 200, r.text
    return {d["date"] for d in r.json()["dates"] if d["holiday"]}


@pytest.mark.parity("B-BOOK-12", "B-SESS-11")
async def test_recurring_series_follow_the_timetable_week(env):
    """``get_recurring_dates``: a series repeats on the same weekday **in the same timetable week** (CRBS
    A/B week rotation), skipping holidays; the other week's Thursdays stay free."""
    c = env.client
    a = (
        await c.post("/api/v1/booking-admin/weeks", json={"name": "A Haftası", "bgcol": "#C6E0B4"}, headers=env.admin)
    ).json()
    b = (
        await c.post("/api/v1/booking-admin/weeks", json={"name": "B Haftası", "bgcol": "#F8CBAD"}, headers=env.admin)
    ).json()
    mapping = {}
    d = TERM_START
    while d <= TERM_END:
        mapping[d.isoformat()] = a["id"] if ((d - TERM_START).days // 7) % 2 == 0 else b["id"]
        d += timedelta(days=1)
    r = await c.put(f"/api/v1/booking-admin/sessions/{env.term_id}/dates", json={"dates": mapping}, headers=env.admin)
    assert r.status_code == 200, r.text
    await c.post(
        "/api/v1/holidays",
        json={
            "term_id": env.term_id,
            "name": "Ulusal Egemenlik ve Çocuk Bayramı",
            "date_start": "2026-04-23",
            "date_end": "2026-04-23",
        },
        headers=env.admin,
    )
    closed = await _closed_dates(env)
    assert mapping[THU.isoformat()] == a["id"]  # 19 Feb is in an A week
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": THU.isoformat(),
        "end": "2026-05-31",
        "notes": "PSİ 216 – A haftası laboratuvarı",
    }
    prev = await c.post("/api/v1/bookings/recurring/preview", json=body, headers=env.planner)
    assert prev.status_code == 200, prev.text
    plan = prev.json()
    assert plan["timetable_week_id"] == a["id"]
    expected = [
        x.isoformat()
        for x in _thursdays(THU, date(2026, 5, 31))
        if mapping[x.isoformat()] == a["id"] and x.isoformat() not in closed
    ]
    assert [i["date"] for i in plan["instances"]] == expected
    assert "2026-02-26" not in expected and "2026-03-05" in expected  # B, then A again
    out = (await c.post("/api/v1/bookings/recurring", json=body, headers=env.planner)).json()
    assert [x["date"] for x in out["created"]] == expected
    # the B-week Thursday is still free for a single booking
    _, teacher = await env.user("b.haftasi@uni.edu.tr")
    assert (await env.book(teacher, "A102", date(2026, 2, 26), "P1")).status_code == 201
    # the grid shows the series as a recurring booking with the A week colour on the date
    grid = (
        await c.get(
            "/api/v1/bookings/grid",
            params={"display": "room", "date": THU.isoformat(), "room_id": env.rooms["A102"]},
            headers=teacher,
        )
    ).json()
    slot = next(s for s in grid["slots"] if s["date"] == THU.isoformat() and s["period_id"] == env.periods["P1"])
    assert slot["status"] == "booked" and slot["reason"] == "recurring"
    assert slot["booking"]["notes"] == "PSİ 216 – A haftası laboratuvarı"  # Teacher: view_other_notes
    day = next(x for x in grid["dates"] if x["date"] == THU.isoformat())
    assert day["timetable_week_id"] == a["id"]


@pytest.mark.parity("B-BOOK-13", "B-BOOK-03")
async def test_recurring_session_start_and_end(env):
    """``SingleAgent`` recurring start/end "session": from the first to the last repeat date of the term."""
    c = env.client
    body = {
        "room_id": env.rooms["A102"],
        "period_id": env.periods["P1"],
        "date": THU.isoformat(),
        "start": "session",
        "end": "session",
    }
    plan = (await c.post("/api/v1/bookings/recurring/preview", json=body, headers=env.planner)).json()
    closed = await _closed_dates(env)
    expected = [x.isoformat() for x in _thursdays(TERM_START, TERM_END) if x.isoformat() not in closed]
    assert [i["date"] for i in plan["instances"]] == expected
    assert plan["instances"][0]["date"] == "2026-02-05" and plan["instances"][-1]["date"] == expected[-1]
    # a date before today is part of the plan, as in CRBS (no book_recur range limits by default)
    assert plan["bookable_count"] == len(expected)
    grid = (
        await c.get(
            "/api/v1/bookings/grid",
            params={"display": "room", "date": THU.isoformat(), "room_id": env.rooms["A102"]},
            headers=env.planner,
        )
    ).json()
    states = {s["period_id"]: s for s in grid["slots"] if s["date"] == THU.isoformat()}
    assert states[env.periods["P1"]]["status"] == "available"
    assert states[env.periods["P3"]]["status"] == "timetable" and states[env.periods["P3"]]["label"]


@pytest.mark.parity("B-BOOK-07")
async def test_notes_are_cleaned_and_limited_to_255_characters(env):
    """CRBS ``notes`` is ``max_length[255]``; SmartSched also folds NBSP / runs of spaces."""
    _, teacher = await env.user("not.uzun@uni.edu.tr")
    long = "Ölçme ve değerlendirme toplantısı " * 8
    assert len(long) > 255
    r = await env.book(teacher, "A101", MON, "P1", notes=long)
    assert r.status_code == 422, r.text
    ok = await env.book(teacher, "A101", MON, "P1", notes="  İş\xa0güvenliği   semineri ")
    assert ok.status_code == 201 and ok.json()["notes"] == "İş güvenliği semineri"
    r = await env.client.put(f"/api/v1/bookings/{ok.json()['id']}", json={"notes": "x" * 256}, headers=teacher)
    assert r.status_code == 422


@pytest.mark.parity("B-BOOK-10")
async def test_department_of_a_booking(env):
    """``book_single.set_department``: the booking carries the chosen department; without the permission it is
    the user's own (Teacher: refused, test_crbs_bookings)."""
    c = env.client
    deps = (await c.get("/api/v1/departments", params={"q": "HEMŞİRELİK"}, headers=env.admin)).json()
    nursing = next(d for d in deps if "hemşirelik" in d["name"].casefold())
    r = await env.book(env.planner, "A101", MON, "P2", department_id=nursing["id"], notes="HEM 334 telafi")
    assert r.status_code == 201 and r.json()["department_id"] == nursing["id"], r.text
    detail = (await c.get(f"/api/v1/bookings/{r.json()['id']}", headers=env.admin)).json()
    assert detail["department_name"] == nursing["name"]
    # without set_department the booking takes the user's own department (CRBS SingleAgent)
    _, teacher = await env.user("bolumlu@uni.edu.tr", department_id=nursing["id"])
    mine = await env.book(teacher, "A101", MON, "P3")
    assert mine.status_code == 201 and mine.json()["department_id"] == nursing["id"]


@pytest.mark.parity("B-BOOK-17")
async def test_multi_booking_selection_is_private_and_can_be_discarded(env):
    """``multi_bookings``: a selection belongs to its user; "cancel" in the wizard deletes it."""
    c = env.client
    _, ayse = await env.user("secim.ayse@uni.edu.tr")
    _, ali = await env.user("secim.ali@uni.edu.tr")
    slots = [{"date": MON.isoformat(), "period_id": env.periods[p], "room_id": env.rooms["A101"]} for p in ("P1", "P2")]
    mb = (await c.post("/api/v1/bookings/multi", json={"slots": slots}, headers=ayse)).json()
    assert (await c.get(f"/api/v1/bookings/multi/{mb['id']}", headers=ali)).status_code == 404
    assert (await c.delete(f"/api/v1/bookings/multi/{mb['id']}", headers=ali)).status_code == 404
    assert (await c.delete(f"/api/v1/bookings/multi/{mb['id']}", headers=ayse)).status_code == 204
    assert (await c.get(f"/api/v1/bookings/multi/{mb['id']}", headers=ayse)).status_code == 404
    assert (await c.get("/api/v1/bookings/mine", headers=ayse)).json() == []


@pytest.mark.parity("B-BOOK-19", "DIFF-e")
async def test_booking_details_need_room_view_or_ownership(env):
    """Deliberate security difference (e): a booking is opened only by its owner or by someone who may see
    its room (CRBS shows any booking id to any signed-in user)."""
    c = env.client
    owner_id, owner = await env.user("detay.sahibi@uni.edu.tr", displayname="Nihal Güneş")
    b = (await env.book(owner, "A101", MON, "P1", notes="Bölüm toplantısı")).json()
    nobody = (await c.post("/api/v1/roles", json={"name": "Yetkisiz", "permissions": []}, headers=env.admin)).json()
    _, stranger = await env.user("detay.yabanci@uni.edu.tr", role=None, role_id=nobody["id"])
    for path in (f"/api/v1/bookings/{b['id']}", f"/api/v1/bookings/{b['id']}/series"):
        assert (await c.get(path, headers=stranger)).status_code == 404
    assert (await c.post(f"/api/v1/bookings/{b['id']}/cancel", json={}, headers=stranger)).status_code == 404
    _, colleague = await env.user("detay.meslektas@uni.edu.tr")
    seen = (await c.get(f"/api/v1/bookings/{b['id']}", headers=colleague)).json()
    assert seen["notes"] == "Bölüm toplantısı" and seen["user_name"] is None  # Teacher rules (data.sql)
    # the owner keeps access to her booking after losing room.view
    await c.put(f"/api/v1/users/{owner_id}", json={"role_id": nobody["id"]}, headers=env.admin)
    assert (await c.get(f"/api/v1/bookings/{b['id']}", headers=owner)).status_code == 401  # role change (B-AUTH-11)
    owner = await login(c, "detay.sahibi@uni.edu.tr", "parola-1234")
    mine = (await c.get(f"/api/v1/bookings/{b['id']}", headers=owner)).json()
    assert mine["is_owner"] and mine["user_name"] == "Nihal Güneş"


@pytest.mark.parity("B-BOOK-30")
async def test_my_bookings_filters(env):
    """``Bookings_model::ByUser`` lists: date range and status filters, own bookings only."""
    c = env.client
    _, teacher = await env.user("benim@uni.edu.tr")
    _, other = await env.user("baskasinin@uni.edu.tr")
    b1 = (await env.book(teacher, "A101", MON, "P1")).json()
    b2 = (await env.book(teacher, "A102", THU, "P1")).json()
    gone = (await env.book(teacher, "A101", MON, "P2")).json()
    await c.post(f"/api/v1/bookings/{gone['id']}/cancel", json={"reason": "Vazgeçildi"}, headers=teacher)
    await env.book(other, "A101", MON, "P3")
    assert [x["id"] for x in (await c.get("/api/v1/bookings/mine", headers=teacher)).json()] == [b1["id"], b2["id"]]
    ranged = (await c.get("/api/v1/bookings/mine", params={"from": "2026-02-17"}, headers=teacher)).json()
    assert [x["id"] for x in ranged] == [b2["id"]]
    upto = (await c.get("/api/v1/bookings/mine", params={"to": "2026-02-16"}, headers=teacher)).json()
    assert [x["id"] for x in upto] == [b1["id"]]
    cancelled = (await c.get("/api/v1/bookings/mine", params={"status": "CANCELLED"}, headers=teacher)).json()
    assert [(x["id"], x["cancel_reason"]) for x in cancelled] == [(gone["id"], "Vazgeçildi")]
    assert len((await c.get("/api/v1/bookings/mine", params={"status": "ALL"}, headers=teacher)).json()) == 3


@pytest.mark.parity("B-BOOK-31")
async def test_export_filters_by_room_group(env):
    """``Export``: the room group filter keeps only that group's rooms."""
    c = env.client
    a = (
        await c.post(
            "/api/v1/room-admin/groups", json={"name": "A Blok", "room_ids": [env.rooms["A101"]]}, headers=env.admin
        )
    ).json()
    await c.post(
        "/api/v1/room-admin/groups", json={"name": "A Blok 1. kat", "room_ids": [env.rooms["A102"]]}, headers=env.admin
    )
    _, teacher = await env.user("disari.grup@uni.edu.tr")
    await env.book(teacher, "A101", MON, "P1", notes="İlk grup")
    await env.book(teacher, "A102", THU, "P1", notes="İkinci grup")

    async def rows(**params: object) -> list[dict[str, str]]:
        r = await c.get("/api/v1/bookings/export.csv", params={"term_id": env.term_id, **params}, headers=env.admin)
        assert r.status_code == 200, r.text
        return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))

    assert sorted(x["Room"] for x in await rows()) == ["A 101", "A 102"]
    only_a = await rows(room_group_id=a["id"])
    assert [(x["Room"], x["Room Group"], x["Notes"]) for x in only_a] == [("A 101", "A Blok", "İlk grup")]


@pytest.mark.parity("B-ROLES-03")
async def test_permissions_are_grouped_like_crbs(env):
    """``Permissions_model::get_scoped``: system / setup permissions and room / booking permissions are listed
    in their CRBS groups; a role keeps exactly the permissions it was saved with."""
    c = env.client
    perms = (await c.get("/api/v1/permissions", headers=env.admin)).json()
    groups = {g for scope in perms.values() for g in scope}
    assert {"system", "setup", "room", "book_single", "book_recur"} <= groups
    assert len([p for scope in perms.values() for items in scope.values() for p in items]) == 31
    teacher = await role_id(c, env.admin, "TEACHER")
    role = (await c.get(f"/api/v1/roles/{teacher}", headers=env.admin)).json()
    assert set(role["permissions"]) == {
        "room.view",
        "book_single.create",
        "book_single.view_other_notes",
        "book_recur.view_other_notes",
    }
