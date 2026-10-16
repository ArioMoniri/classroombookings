"""P8 booking policies and exam-period mode on the real Bahar 2026 import (``tests/crbs_env``: the imported weekly
board is the published timetable, the clock is Monday 16 Feb 2026 08:00).

Facts from the Bahar board: weeks 17-18 are the Final weeks (1-14 June 2026, sheets "Final 1 - 7 Haziran" and
"Final 8 - 14 Haziran"), the imported exam board is the term's second run (kind EXAM, not published); 23 Nisan 2026
(Thursday) is a national holiday the test adds through the API."""

from __future__ import annotations

from datetime import date, datetime

from app.core import db as dbmod
from app.models import AuditEvent, Booking
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.wave2_support import free_rooms

POL = "/api/v1/booking-policies"


async def _policy(env, **body):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.post(POL, json={"name": "Kural", **body}, headers=env.admin)
    assert r.status_code == 201, r.text
    return r.json()


async def test_three_working_days_across_a_weekend_and_a_holiday(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    pol = await _policy(env, name="3 iş günü önceden", min_notice_workdays=3, role_codes=["teacher"])
    assert pol["role_codes"] == ["TEACHER"] and "3 iş günü" in pol["summary"]["tr"][0]
    env.set_now(datetime(2026, 2, 19, 9, 0))  # Thursday
    mon, tue = date(2026, 2, 23), date(2026, 2, 24)
    room = (await free_rooms(mon, 13, 13))[0]
    r = await env.book(ayse, room, mon, "P13")  # Friday + Monday = 2 working days ahead
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "policy_min_notice"
    assert "3 iş günü" in d["message_tr"] and "24.02.2026" in d["message_tr"] and "hafta sonu" in d["message_tr"]
    assert "working day" in d["message_en"] and d["policy"]["id"] == pol["id"]
    room2 = (await free_rooms(tue, 13, 13))[0]
    assert (await env.book(ayse, room2, tue, "P13")).status_code == 201
    # the administrator (planning.admin) is not bound by policies
    assert (await env.book(env.admin, room, mon, "P13")).status_code == 201
    # holidays are not working days: Tuesday 21 Apr -> Wed 22, (Thu 23 Nisan), Fri 24, Mon 27
    r = await env.client.post(
        "/api/v1/holidays",
        json={
            "term_id": env.term_id,
            "name": "Ulusal Egemenlik ve Çocuk Bayramı",
            "date_start": "2026-04-23",
            "date_end": "2026-04-23",
        },
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    env.set_now(datetime(2026, 4, 21, 9, 0))
    fri = date(2026, 4, 24)
    room3 = (await free_rooms(fri, 13, 13))[0]
    r = await env.book(ayse, room3, fri, "P13")
    assert r.status_code == 409 and "27.04.2026" in r.json()["detail"]["message_tr"]
    # the "Neden?" link: the rules and the verdict for that slot
    r = await env.client.get(
        f"{POL}/effective",
        params={"room_id": env.rooms[room3], "date": fri.isoformat(), "period_id": env.periods["P13"]},
        headers=ayse,
    )
    assert r.status_code == 200, r.text
    eff = r.json()
    assert eff["verdict"] == "refuse" and eff["violations"][0]["rule"] == "min_notice"
    assert [p["id"] for p in eff["policies"]] == [pol["id"]]
    # audited
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "booking_policy.create"))).scalar_one()
        assert ev.entity_id == str(pol["id"]) and ev.after["min_notice_workdays"] == 3


async def test_advance_duration_active_quiet_hours_blackout_buffer(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    _, mehmet = await env.user("mehmet.oz@uni.edu.tr")
    await _policy(env, name="En fazla 30 gün", max_advance_days=30)
    far = date(2026, 3, 30)
    room = (await free_rooms(far, 13, 13))[0]
    r = await env.book(ayse, room, far, "P13")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_max_advance"
    assert "18.03.2026" in r.json()["detail"]["message_tr"]

    # back to back in one room: P13 18:00-18:40 + P14 18:50-19:30 = 90 minutes, + P15 -> 140 > 100
    await _policy(env, name="100 dakika", max_duration_minutes=100)
    day = date(2026, 2, 18)
    room = next(c for c in await free_rooms(day, 13, 16, limit=20))
    assert (await env.book(ayse, room, day, "P13")).status_code == 201
    assert (await env.book(ayse, room, day, "P14")).status_code == 201
    r = await env.book(ayse, room, day, "P15")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_max_duration"
    assert "18:00-20:20" in r.json()["detail"]["message_tr"]

    # a setup buffer: Mehmet's booking right after Ayşe's (10-minute grid break) is too close for 20 minutes
    await _policy(env, name="Hazırlık", buffer_minutes=20)
    r = await env.book(mehmet, room, day, "P15")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_buffer"
    assert "20 dakika" in r.json()["detail"]["message_tr"]

    # quiet hours with a dotted time (Turkish style "12.40"): Friday noon prayer
    pol = await _policy(env, name="Cuma", quiet_hours=[{"weekdays": [5], "start": "12.40", "end": "13:30"}])
    assert pol["quiet_hours"] == [{"weekdays": [5], "start": "12:40", "end": "13:30"}]
    fri = date(2026, 2, 20)
    room_f = (await free_rooms(fri, 6, 6))[0]
    r = await env.book(mehmet, room_f, fri, "P6")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_quiet_hours"
    assert "Cuma 12:40-13:30" in r.json()["detail"]["message_tr"]

    # a blackout with a Turkish date
    await _policy(env, name="Bahar şenliği", blackouts=[{"from": "26.02.2026", "label": "Bahar Şenliği"}])
    thu = date(2026, 2, 26)
    room_t = (await free_rooms(thu, 13, 13))[0]
    r = await env.book(mehmet, room_t, thu, "P13")
    assert r.status_code == 409 and "Bahar Şenliği" in r.json()["detail"]["message_tr"]

    # at most 2 active bookings for teachers: Ayşe has 2 already
    await _policy(env, name="İki etkin", max_active_bookings=2, role_codes=["TEACHER"])
    day2 = date(2026, 2, 17)
    room2 = (await free_rooms(day2, 13, 13))[0]
    r = await env.book(ayse, room2, day2, "P13")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_max_active"
    assert "en fazla 2 etkin" in r.json()["detail"]["message_tr"]


async def test_request_effect_makes_an_approval_request(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    await _policy(
        env,
        name="Akşam talep",
        effect="request",
        quiet_hours=[{"weekdays": [1, 2, 3, 4, 5], "start": "18:00", "end": "23:00"}],
    )
    day = date(2026, 2, 18)
    room = (await free_rooms(day, 13, 13))[0]
    r = await env.book(ayse, room, day, "P13")
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "PENDING"
    async with dbmod.get_session_factory()() as s:
        from app.services import approvals

        b = await s.get(Booking, r.json()["id"])
        req = await approvals.request_for_booking(s, b)
        assert req is not None and req.rule_snapshot["source"] == "policy"


async def test_exam_period_mode_turns_exam_halls_into_requests(env, parsed_final_grid):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    # the exam halls are the rooms of the real Final board (2026 final derslikler takvimi); the Bahar board's own
    # Final sheets are empty, so the administrator lists them (from_exam_timetable stays on)
    exam_rooms = {e.room_code for e in parsed_final_grid.entries} & set(env.rooms)
    assert len(exam_rooms) >= 10
    june = date(2026, 6, 2)  # Tuesday of "Final 1 - 7 Haziran" (Bahar week 17, kind EXAM)
    hall = next(c for c in await free_rooms(june, 13, 13, codes=sorted(exam_rooms), limit=40))
    plain_free = [c for c in await free_rooms(june, 13, 13, limit=80) if c not in exam_rooms]
    # off by default: a direct booking
    r = await env.client.get(POL, headers=env.admin)
    assert r.json()["exam_period"]["mode"] == "off"
    ids = sorted(env.rooms[c] for c in exam_rooms)
    r = await env.client.put(f"{POL}/exam-period", json={"mode": "request", "room_ids": ids}, headers=env.admin)
    assert r.status_code == 200 and r.json()["mode"] == "request" and r.json()["room_ids"] == ids
    r = await env.book(ayse, hall, june, "P13")
    assert r.status_code == 202 and r.json()["status"] == "PENDING", r.text
    # the finder offers "Talep et" for exam halls in Final weeks
    r = await env.client.post(
        "/api/v1/rooms/find",
        json={"date": "2026-06-03", "start": "18.00", "end": "18:40", "headcount": 30, "text": hall[:1]},
        headers=ayse,
    )
    assert r.status_code == 200, r.text
    by_code = {x["code"]: x for x in r.json()["results"]}
    halls = [x for c, x in by_code.items() if c in exam_rooms and x["status"] in ("free", "requestable")]
    assert halls and all(x["status"] == "requestable" and x["action"] == "request" for x in halls)
    assert "Sınav döneminde" in halls[0]["reason"]["tr"]
    # a room the exam board does not use books directly; lecture weeks are not affected
    if plain_free:
        assert (await env.book(ayse, plain_free[0], june, "P13")).status_code == 201
    feb = date(2026, 2, 18)
    feb_room = next(c for c in await free_rooms(feb, 13, 13, codes=sorted(exam_rooms), limit=40))
    assert (await env.book(ayse, feb_room, feb, "P13")).status_code == 201
    # the grid marks request-only slots
    r = await env.client.get(
        "/api/v1/bookings/grid",
        params={"display": "room", "date": "2026-06-03", "room_id": env.rooms[hall]},
        headers=ayse,
    )
    assert r.status_code == 200, r.text
    marked = [s for s in r.json()["slots"] if s.get("request_only")]
    assert marked and marked[0]["policy"]["rule"] == "exam_period"
    # closed: refused with the reason
    r = await env.client.put(f"{POL}/exam-period", json={"mode": "closed"}, headers=env.admin)
    assert r.status_code == 200
    june9 = date(2026, 6, 9)
    hall2 = next(c for c in await free_rooms(june9, 13, 13, codes=sorted(exam_rooms), limit=40))
    r = await env.book(ayse, hall2, june9, "P13")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_exam_period"
    assert "kapalıdır" in r.json()["detail"]["message_tr"]
    r = await env.client.put(f"{POL}/exam-period", json={"mode": "sometimes"}, headers=env.admin)
    assert r.status_code == 422 and "message_tr" in r.json()["detail"]


async def test_series_skips_refused_dates_and_moves_keep_policies(env):  # noqa: F811
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    await _policy(env, name="Bahar şenliği", blackouts=[{"from": "2026-03-04", "to": "2026-03-04", "label": "Şenlik"}])
    # the planner (book_recur.create, not planning.admin) books Wednesdays P13 in a room free that evening
    weds = [date(2026, 2, 18), date(2026, 2, 25), date(2026, 3, 4), date(2026, 3, 11)]
    cands = set(await free_rooms(weds[0], 13, 13, limit=80))
    for d in weds[1:]:
        cands &= set(await free_rooms(d, 13, 13, limit=80))
    room = sorted(cands)[0]
    body = {
        "room_id": env.rooms[room],
        "period_id": env.periods["P13"],
        "date": "2026-02-18",
        "start": "2026-02-18",
        "end": "2026-03-11",
    }
    r = await env.client.post("/api/v1/bookings/recurring/preview", json=body, headers=env.planner)
    assert r.status_code == 200, r.text
    inst = {i["date"]: i for i in r.json()["instances"]}
    assert inst["2026-03-04"]["status"] == "policy" and inst["2026-03-04"]["actions"] == ["do_not_book"]
    assert "Şenlik" in inst["2026-03-04"]["policy"]["message_tr"]
    r = await env.client.post("/api/v1/bookings/recurring", json=body, headers=env.planner)
    assert r.status_code == 201, r.text
    assert "2026-03-04" not in {b["date"] for b in r.json()["created"]}
    assert any(x["date"] == "2026-03-04" and x["reason"] == "policy_blackout" for x in r.json()["skipped"])
    # a single booking moved onto the blackout date is refused
    room1 = (await free_rooms(date(2026, 2, 19), 13, 13))[0]
    r = await env.book(ayse, room1, date(2026, 2, 19), "P13")
    assert r.status_code == 201
    target = (await free_rooms(date(2026, 3, 4), 13, 13))[0]
    r = await env.client.put(
        f"/api/v1/bookings/{r.json()['id']}",
        json={"date": "2026-03-04", "room_id": env.rooms[target]},
        headers=ayse,
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "policy_blackout", r.text


async def test_policy_validation_and_crud(env):  # noqa: F811
    r = await env.client.post(POL, json={"name": " Boş "}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "empty"
    r = await env.client.post(
        POL,
        json={"name": "x", "quiet_hours": [{"weekdays": [9], "start": "08:00", "end": "09:00"}]},
        headers=env.admin,
    )
    assert r.status_code == 422 and "Pazartesi" in r.json()["detail"]["message_tr"]
    r = await env.client.post(POL, json={"name": "x", "scope_type": "tag", "max_advance_days": 5}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "tag"
    pol = await _policy(env, name="TIP salonları", scope_type="tag", tag="tıp", max_advance_days=5)
    assert pol["tag"] == "TIP"
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    assert (await env.client.post(POL, json={"name": "x", "max_advance_days": 1}, headers=ayse)).status_code == 403
    r = await env.client.put(f"{POL}/{pol['id']}", json={**pol, "max_advance_days": 7}, headers=env.admin)
    assert r.status_code == 200 and r.json()["max_advance_days"] == 7
    assert (await env.client.delete(f"{POL}/{pol['id']}", headers=env.admin)).status_code == 204
    assert (await env.client.delete(f"{POL}/{pol['id']}", headers=env.admin)).status_code == 404
    async with dbmod.get_session_factory()() as s:
        acts = [
            e.action
            for e in (await s.execute(select(AuditEvent).where(AuditEvent.entity_type == "booking_policy"))).scalars()
        ]
        assert acts == ["booking_policy.create", "booking_policy.update", "booking_policy.delete"]
