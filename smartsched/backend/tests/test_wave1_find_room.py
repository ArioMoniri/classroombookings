"""T1 "find me a room" on the real Bahar 2026 data (``tests/crbs_env``: the weekly grid run is published).

The planner's hand count for "Çarşamba 10:10-12:30, 90+ kişilik boş derslik" (Wednesday 18 Feb 2026, week 3) is
computed independently from the raw weekly-grid workbook (``parsed_bahar_grid``): every room of 90+ seats with
no cell in P3-P5 that day. Other facts: A 102 is free at P1 on every Thursday; 23 Nisan 2026 (Thursday) is a
national holiday; A 201-A 203 carry the TIP tag; A 103-A 105 the PC tag."""

from __future__ import annotations

from datetime import date

from app.api.v1 import find_room as find_api

from tests.crbs_env import env  # noqa: F401

FIND = "/api/v1/rooms/find"
WED = date(2026, 2, 18)
THU = date(2026, 2, 19)
BIG = {"A102": 96, "A201": 96, "A202": 96, "A203": 148, "A204": 156, "A205": 94, "A206": 92, "A207": 120, "C201": 126}


def _planner_free(parsed_grid, d: date, start: int, end: int, rooms: set[str]) -> set[str]:
    busy = {
        e.room_code
        for sh in parsed_grid.sheets
        for e in sh.entries
        if e.date == d and e.room_code in rooms and e.start_period <= end and start <= e.end_period
    }
    return rooms - busy


async def test_wednesday_1010_1230_for_90_matches_the_planners_hand_count(env, parsed_bahar_grid):  # noqa: F811
    find_api.FIND_LIMIT.reset()
    expected = _planner_free(parsed_bahar_grid, WED, 3, 5, set(BIG))
    assert expected == {"A201", "A202", "A203"}  # the board: every other 90+ room has a class that morning
    _, ayse = await env.user("ayse.yilmaz@uni.edu.tr")
    body = {"date": WED.isoformat(), "start": "10.10", "end": "12:30", "headcount": 90}  # dotted time, NBSP-free
    r = await env.client.post(FIND, json=body, headers=ayse)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["slots"] == [{"date": "2026-02-18", "start_period": 3, "end_period": 5}]
    assert out["time"] == {"start": "10:10", "end": "12:30"}
    free = {x["code"] for x in out["results"] if x["status"] == "free"}
    assert free == expected
    # busy rooms carry what holds them (the published course), too-small rooms come after
    by_code = {x["code"]: x for x in out["results"]}
    assert by_code["A204"]["status"] == "busy" and by_code["A204"]["busy_with"] == "PHY 102"
    assert by_code["A101"]["status"] == "too_small"
    statuses = [x["status"] for x in out["results"]]
    assert statuses.index("busy") > max(i for i, s in enumerate(statuses) if s == "free")
    # ranking: the 96-seat TIP rooms before the 148-seat one (less waste); reasons in Turkish and English
    assert [x["code"] for x in out["results"][:3]] == ["A201", "A202", "A203"]
    assert out["results"][0]["fit"]["waste_pct"] == 6 and "boş koltuk" in out["results"][0]["reason"]["tr"]
    # fewer than 3... exactly 3 free: no alternatives needed
    assert out["alternatives"] == []
    # deterministic
    again = (await env.client.post(FIND, json=body, headers=ayse)).json()
    assert [x["room_id"] for x in again["results"]] == [x["room_id"] for x in out["results"]]
    recent = (await env.client.get(f"{FIND}/recent", headers=ayse)).json()
    assert recent[0]["start"] == "10.10" and len(recent) == 1


async def test_features_buildings_and_turkish_text(env):  # noqa: F811
    find_api.FIND_LIMIT.reset()
    c = env.client
    pc = next(f for f in (await c.post("/api/v1/room-admin/features/adopt-tags", headers=env.admin)).json()
              if f["solver_tag"] == "PC")
    body = {"date": WED.isoformat(), "start": 1, "duration_periods": 2, "features": [{"field": "BİLGİSAYAR LABORATUVARI"}]}
    out = (await c.post(FIND, json=body, headers=env.admin)).json()
    pcs = {x["code"] for x in out["results"] if x["status"] not in ("feature_missing",)}
    assert pcs == {"A103", "A104", "A105"}
    # the same through a word for the tag, and through free text
    out2 = (await c.post(FIND, json={**body, "features": [], "tags": ["bilgisayar"]}, headers=env.admin)).json()
    assert {x["code"] for x in out2["results"] if x["status"] != "feature_missing"} == pcs
    out3 = (await c.post(FIND, json={**body, "features": [], "text": "Bilgisayar"}, headers=env.admin)).json()
    assert {x["code"] for x in out3["results"]} == pcs
    assert pc["id"]
    # buildings in Turkish forms
    out4 = (await c.post(FIND, json={**body, "features": [], "buildings": ["c blok"]}, headers=env.admin)).json()
    assert out4["results"] and all(x["building"] == "C" for x in out4["results"])
    # a time outside the teaching day is refused with a Turkish reason
    bad = await c.post(FIND, json={"date": WED.isoformat(), "start": "07:00", "end": "08:00"}, headers=env.admin)
    assert bad.status_code == 422 and "ders gününün dışında" in bad.json()["detail"]["message_tr"]
    # the unrequested PC lab ranks after an ordinary room of the same fit
    out5 = (await c.post(FIND, json={"date": WED.isoformat(), "start": 1, "headcount": 40}, headers=env.admin)).json()
    a103 = next(x for x in out5["results"] if x["code"] == "A103")
    assert any("PC" in r["tr"] for r in a103["reasons"])


async def test_recurring_partial_results_and_holidays(env):  # noqa: F811
    find_api.FIND_LIMIT.reset()
    _, ayse = await env.user("ayse@uni.edu.tr")
    r = await env.book(ayse, "A102", date(2026, 3, 5), "P1")  # one Thursday taken
    assert r.status_code == 201, r.text
    body = {"term_id": env.term_id, "weekday": 4, "start": "08:30", "end": "09:10", "headcount": 90}
    out = (await env.client.post(FIND, json=body, headers=ayse)).json()
    assert {"date": "2026-04-23", "reason": "holiday"} == {
        k: v for k, v in next(x for x in out["closed_dates"] if x["date"] == "2026-04-23").items() if k != "holiday"
    }
    a102 = next(x for x in out["results"] if x["code"] == "A102")
    assert a102["status"] == "partial" and a102["free_dates"] == a102["open_dates"] - 1
    per = {p["date"]: p["status"] for p in a102["per_date"]}
    assert per["2026-03-05"] == "busy" and per["2026-04-23"] == "closed" and per["2026-02-19"] == "free"
    assert f"{a102['free_dates']}/{a102['open_dates']} tarih boş" in a102["reason"]["tr"]
    # the caller sees their own booking as the holder
    assert "Rezervasyon" in a102["busy_with"]
    # performance: ~60 rooms x every Thursday of the term on SQLite
    assert out["timing_ms"] < 3000


async def test_acl_hides_rooms_and_alternatives_when_few_are_free(env):  # noqa: F811
    find_api.FIND_LIMIT.reset()
    c = env.client
    r = await c.post("/api/v1/roles", json={"name": "Misafir", "permissions": []}, headers=env.admin)
    rid = r.json()["id"]
    _, guest = await env.user("misafir@uni.edu.tr", role_id=rid)
    out = (await c.post(FIND, json={"date": WED.isoformat(), "start": 3, "end": 5}, headers=guest)).json()
    assert out["results"] == []  # no room.view anywhere
    # 150+ seats Wednesday P3-P5: A 204 (156) is busy with PHY 102 -> alternatives at other times
    out = (
        await c.post(FIND, json={"date": WED.isoformat(), "start": 3, "end": 5, "headcount": 150, "flex": {"other_days": True}},
                     headers=env.admin)
    ).json()
    assert not [x for x in out["results"] if x["status"] == "free"]
    kinds = {a["kind"] for a in out["alternatives"]}
    assert "time" in kinds or "day" in kinds
    assert all(a["reason"]["tr"] and a["reason"]["en"] for a in out["alternatives"])
    near = [a for a in out["alternatives"] if a["kind"] == "near_miss"]
    assert all(a["code"] != "A204" for a in near)
