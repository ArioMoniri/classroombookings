"""Studio class list (filters, Turkish-aware search, draft flags) and bulk edits with imported-snapshot
revert, on the real Bahar 2026 planning list."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import Faculty, MeetingRequest, Program, Room, Section
from sqlalchemy import select

from tests import studio_support
from tests.studio_support import meeting_id

bahar = studio_support.bahar


async def _classes(b, **params):
    r = await b.client.get(f"/api/v1/terms/{b.term_id}/studio/classes", params=params, headers=b.planner)
    assert r.status_code == 200, r.text
    return r.json()


async def test_class_list_filters_on_bahar(bahar):
    page = await _classes(bahar, limit=2000)
    assert page["total"] == 1524 and page["counts"]["total"] == 1524
    assert page["counts"]["left_out"] == 0 and page["counts"]["locked"] == 782
    assert page["counts"]["needs_room"] == 975 and page["counts"]["no_day_time"] > 0
    row = page["items"][0]
    assert row["included"] and row["course_code"] and row["time_label"] in (None, row["time_label"])
    # Turkish-aware, diacritic-insensitive search: "eczacilik" == "ECZACILIK" == "Eczacılık"
    a = await _classes(bahar, q="eczacilik", limit=2000)
    b2 = await _classes(bahar, q="ECZACILIK", limit=2000)
    c = await _classes(bahar, q="Eczacılık", limit=2000)
    assert a["total"] == b2["total"] == c["total"] > 50
    assert all("Eczacılık" in (r["program_name"] or "") or "Eczacılık" in (r["faculty_name"] or "") for r in a["items"])
    # course code search ignores the space and the dotted capital İ
    psi = await _classes(bahar, q="psi116", limit=50)
    assert psi["total"] >= 1 and all(r["course_code"].replace(" ", "") == "PSI116" for r in psi["items"])
    assert (await _classes(bahar, q="PSİ 116"))["total"] == psi["total"]
    async with get_session_factory()() as s:
        fac = (await s.execute(select(Faculty).where(Faculty.name == "Eczacılık Fakültesi"))).scalar_one()
        prog = (await s.execute(select(Program).where(Program.name == "Psikoloji"))).scalar_one()
    f = await _classes(bahar, faculty_id=fac.id, limit=2000)
    assert f["total"] > 0 and all(r["faculty_id"] == fac.id for r in f["items"])
    py = await _classes(bahar, program_id=prog.id, class_year=1, limit=2000)
    assert py["total"] > 0 and all(r["program_id"] == prog.id and 1 in (r["class_years"] or [r["class_year"]]) for r in py["items"])
    mon = await _classes(bahar, day=1, limit=2000)
    assert mon["total"] > 200 and all(r["day"] == 1 or 1 in r["days"] for r in mon["items"])
    cblock = await _classes(bahar, building="c", limit=2000)
    assert cblock["total"] > 0
    assert all(
        r["requested_building"] == "C" or any(code.startswith("C") for code in r["requested_room_codes"] + r["definitive_room_codes"])
        for r in cblock["items"]
    )
    online = await _classes(bahar, mode="ONLINE", limit=2000)
    assert online["total"] > 100 and all(r["mode"] == "ONLINE" for r in online["items"])
    locked = await _classes(bahar, status="LOCKED", limit=5)
    assert locked["total"] == 782 and all(r["locked"] for r in locked["items"]) and len(locked["items"]) == 5
    paged = await _classes(bahar, limit=10, offset=10)
    assert [r["id"] for r in paged["items"]] == [r["id"] for r in page["items"][10:20]]
    # draft state: left out + pinned + rule matches
    phar = await meeting_id("PHAR 240", day=1, start=1)
    url = f"/api/v1/terms/{bahar.term_id}/studio"
    await bahar.client.get(url, headers=bahar.planner)
    r = await bahar.client.put(
        url,
        json={"version": 1, "excluded_event_ids": [phar], "pins": [{"event_id": psi["items"][0]["id"], "room_ids": [10]}]},
        headers=bahar.planner,
    )
    assert r.status_code == 200, r.text
    out = await _classes(bahar, included=False)
    assert [x["id"] for x in out["items"]] == [phar] and out["counts"]["left_out"] == 1
    pinned = await _classes(bahar, pinned=True)
    assert [x["id"] for x in pinned["items"]] == [psi["items"][0]["id"]]
    rule = await bahar.client.post(
        "/api/v1/constraints",
        json={
            "term_id": bahar.term_id,
            "kind": "building_preference",
            "params": {"program": prog.canonical_name, "building": "C"},
            "hardness": "soft",
            "weight": 5,
        },
        headers=bahar.planner,
    )
    assert rule.status_code == 201, rule.text
    rid = rule.json()["id"]
    hits = await _classes(bahar, rule_id=rid, limit=2000)
    assert hits["total"] > 0 and all(rid in x["rule_ids"] for x in hits["items"])
    # the solver's programme selector is a prefix match on cohort keys ("psikoloji" also catches
    # "psikoloji (ingilizce)") and joint lectures merged with Psikoloji rows come along
    progs = {x["program_name"] for x in hits["items"]}
    assert "Psikoloji" in progs and all(
        "Psikoloji" in (x["program_name"] or "") or x["program_id"] != prog.id for x in hits["items"]
    )
    own = await _classes(bahar, program_id=prog.id, needs_room=True, limit=2000)
    assert {x["id"] for x in own["items"] if x["schedulable"]} <= {x["id"] for x in hits["items"]}
    assert all(x["schedulable"] for x in hits["items"])  # the solver only sees schedulable rows
    rules = (await bahar.client.get(f"/api/v1/terms/{bahar.term_id}/studio/rules", headers=bahar.planner)).json()
    card = next(x for x in rules["rules"] if x["id"] == rid)
    assert card["affected_count"] == hits["total"] and card["in_play"] and card["title"]["en"]
    assert {b["kind"] for b in rules["builtins"]} >= {"no_room_overlap", "no_instructor_overlap"}


async def test_bulk_edit_and_revert_to_imported(bahar):
    c, h = bahar.client, bahar.planner
    phar = await meeting_id("PHAR 240", day=1, start=1)  # PHAR 240 §1, 80 students, Mon P1-P3, LOCKED
    r = await c.put("/api/v1/studio/meetings/bulk", json={"ids": [phar], "patch": {"enrolment": 95, "start_period": 2}}, headers=h)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["updated"] == 1 and res["failed"] == 0
    assert set(res["results"][0]["changed"]) == {"enrolment", "start_period", "end_period"}
    row = res["rows"][0]
    assert (row["enrolment"], row["start_period"], row["end_period"], row["time_label"]) == (95, 2, 4, "09:20-11:40")
    changed = {f["field"]: (f["imported"], f["current"]) for f in row["changed_fields"]}
    assert changed == {"enrolment": (80, 95), "start_period": (1, 2), "end_period": (3, 4)}
    # enrolment lives on the section: its other weekly meeting (Thu P2-P5) shows the change too
    ch = (await _classes(bahar, changed=True))["items"]
    sib = await meeting_id("PHAR 240", day=4, start=2)
    assert {x["id"] for x in ch} == {phar, sib}
    assert [f["field"] for f in next(x for x in ch if x["id"] == sib)["changed_fields"]] == ["enrolment"]
    # per-row validation: bad rows are reported and skipped, the good row is written
    no_room = await meeting_id("PHAR 220", day=5, start=8)  # not locked, no definitive room
    other = await meeting_id("PHAR 290", day=3, start=9)
    r = await c.put(
        "/api/v1/studio/meetings/bulk",
        json={
            "items": [
                {"id": no_room, "patch": {"start_period": 10, "end_period": 5}},
                {"id": no_room, "patch": {"locked": True}},
                {"id": other, "patch": {"requested_room_ids": [99999]}},
                {"id": other, "patch": {"requested_building": "c", "requested_tags": ["pc"], "weeks": [1, 2, 3]}},
                {"id": 987654, "patch": {"enrolment": 1}},
            ]
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    res = r.json()
    ok = [x["ok"] for x in res["results"]]
    assert ok == [False, False, False, True, False] and res["updated"] == 1 and res["failed"] == 4
    assert "start <= end" in res["results"][0]["errors"][0] and "definitive_room_ids" in res["results"][1]["errors"][0]
    assert res["rows"][0]["requested_building"] == "C" and res["rows"][0]["requested_tags"] == ["PC"]
    # capacity hint: a room smaller than the class
    async with get_session_factory()() as s:
        small = (await s.execute(select(Room).where(Room.capacity > 0).order_by(Room.capacity))).scalars().first()
    r = await c.put("/api/v1/studio/meetings/bulk", json={"ids": [phar], "patch": {"requested_room_ids": [small.id]}, "dry_run": True}, headers=h)
    warnings = r.json()["results"][0]["warnings"]
    assert f"{small.display_name} has {small.capacity} seats, this class has 95" in warnings
    assert "A 206 has 92 seats, this class has 95" in warnings  # its definitive (locked) room is small too
    assert r.json()["updated"] == 0
    # revert one field, then everything
    r = await c.post(f"/api/v1/studio/meetings/{phar}/revert", json={"fields": ["enrolment"]}, headers=h)
    assert r.status_code == 200 and r.json()["enrolment"] == 80 and r.json()["start_period"] == 2
    r = await c.post(f"/api/v1/studio/meetings/{phar}/revert", json={}, headers=h)
    row = r.json()
    assert (row["enrolment"], row["start_period"], row["end_period"], row["changed_fields"]) == (80, 1, 3, [])
    async with get_session_factory()() as s:
        mr = await s.get(MeetingRequest, phar)
        assert mr.start_time.strftime("%H:%M") == "08:30" and mr.end_time.strftime("%H:%M") == "10:50"
    r = await c.post("/api/v1/studio/meetings/revert", json={"ids": [other]}, headers=h)
    assert r.status_code == 200 and r.json()[0]["requested_building"] is None and r.json()[0]["changed_fields"] == []
    # mode -> ONLINE switches every meeting of the section off rooms; revert puts them back
    r = await c.put("/api/v1/studio/meetings/bulk", json={"ids": [phar], "patch": {"mode": "ONLINE"}}, headers=h)
    assert r.json()["rows"][0]["needs_room"] is False
    async with get_session_factory()() as s:
        sec_id = (await s.get(MeetingRequest, phar)).section_id
        sibs = list((await s.execute(select(MeetingRequest).where(MeetingRequest.section_id == sec_id))).scalars())
        assert len(sibs) >= 1 and all(m.needs_room is False for m in sibs)
    r = await c.post(f"/api/v1/studio/meetings/{phar}/revert", json={"fields": ["mode"]}, headers=h)
    assert r.json()["mode"] == "F2F" and r.json()["needs_room"] is True
    # a re-import with different content makes the snapshot stale: no false "changed" marks
    await c.put("/api/v1/studio/meetings/bulk", json={"ids": [phar], "patch": {"enrolment": 99}}, headers=h)
    assert (await _classes(bahar, changed=True))["total"] == 2
    async with get_session_factory()() as s:
        mr = await s.get(MeetingRequest, phar)
        sec = await s.get(Section, mr.section_id)
        sec.source_row = {**(sec.source_row or {}), "reimported": True}
        await s.commit()
    assert (await _classes(bahar, changed=True))["total"] == 0
