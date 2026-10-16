"""Backend asks, batch 2 (2026-10-16), on the real 2026 Bahar list (the shared published week-3 database of
``tests/test_p19_moderation.py``; every test works on a private copy):

* the runs list carries the run ``label`` (pickers parse ``GET /runs`` through one schema);
* ``POST /moderation/me/preferences?dry_run=1`` answers the server's own ``effective`` and ``items[].text`` and
  stores nothing (no constraint row, no audit event);
* ``GET /moderation/me/rooms``: the rooms a linked academician may wish for (bookable only; code, name, capacity,
  building, tags; never notes, owners or custom fields).

Real row: R601 PTL 102 §1 (52 students; the department asked for C 601), its primary instructor signs in as an
academician (TEACHER) linked to the instructor record and prefers C 301 (typed ``c\\xa0301``: NBSP, lower case).
"""

from __future__ import annotations

from typing import Any

from app.core import db as dbmod
from app.models import AuditEvent, ConstraintRow, Room, ScheduleRun
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401  (booking fixture on the real Bahar import)
from tests.crbs_support import make_user
from tests.test_p19_moderation import real, workdir  # noqa: F401  (shared real-data fixture)
from tests.test_p19_t2_teacher_preferences import ROW, _room, _row, _teacher

API = "/api/v1"


# ------------------------------------------------------------------------------------------- 5. run label


async def test_runs_list_and_detail_carry_the_label(real: dict[str, Any]) -> None:  # noqa: F811
    c, h = real["client"], real["admin"]
    async with dbmod.get_session_factory()() as s:
        run = await s.get(ScheduleRun, real["run_id"])
        assert run is not None
        run.label = "Bahar 3. hafta — İlk taslak"  # Turkish capitals survive the round trip
        await s.commit()
    listed = (await c.get(f"{API}/runs", headers=h)).json()
    one = next(r for r in listed if r["id"] == real["run_id"])
    assert one["label"] == "Bahar 3. hafta — İlk taslak" and one["term_code"]
    assert all("label" in r for r in listed)
    assert (await c.get(f"{API}/runs/{real['run_id']}", headers=h)).json()["label"] == "Bahar 3. hafta — İlk taslak"


# ------------------------------------------------------------------------------------------- 6. dry run


async def _counts() -> tuple[int, int]:
    async with dbmod.get_session_factory()() as s:
        rows = (await s.execute(select(func.count()).select_from(ConstraintRow))).scalar_one()
        events = (
            await s.execute(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("preference.%")))
        ).scalar_one()
    return int(rows), int(events)


async def test_preference_dry_run_previews_without_storing(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    rid, iid, dept = await _row(tid, ROW)
    c301 = await _room("C301")
    _uid, teacher = await _teacher(c, h, iid, "ptl.onizleme@uni.edu.tr")
    body = {"kind": "room", "request_ids": [rid], "rooms": ["c\xa0301"], "note": "Projeksiyon\xa0lazım"}
    before = await _counts()
    r = await c.post(f"{API}/moderation/me/preferences", params={"dry_run": 1}, json=body, headers=teacher)
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["dry_run"] is True and prev["status"] == "preview" and prev["submission"] is None
    assert prev["effective"]["tr"] and prev["effective"]["en"]
    assert len(prev["items"]) == 1
    item = prev["items"][0]
    assert item["id"] is None and item["status"] == "pending" and item["enabled"] is False
    assert item["kind"] == "room_preference" and item["wish"]["room_ids"] == [c301]
    assert item["wish"]["rooms"] == ["C 301"] and item["department"]["room_ids"] == dept
    assert "C 301" in item["text"]["tr"] and "room preference C 301" in item["text"]["en"]
    assert item["note"] == "Projeksiyon lazım"  # NBSP folded like the stored note
    assert await _counts() == before  # nothing stored, nothing audited
    me = (await c.get(f"{API}/moderation/me/preferences", headers=teacher)).json()
    assert me["items"] == []
    # the real submit answers the same texts and effective line
    r = await c.post(f"{API}/moderation/me/preferences", json=body, headers=teacher)
    assert r.status_code == 201, r.text
    real_item = r.json()["items"][0]
    assert real_item["text"] == item["text"] and r.json()["effective"] == prev["effective"]
    assert real_item["wish"] == item["wish"] and real_item["id"]
    # a refusal is the same in a dry run (TR + EN), and still stores nothing
    after = await _counts()
    r = await c.post(
        f"{API}/moderation/me/preferences",
        params={"dry_run": "true"},
        json={**body, "rooms": ["Z 999"]},
        headers=teacher,
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_room" and r.json()["detail"]["message_tr"]
    assert await _counts() == after


# ------------------------------------------------------------------------------------------- 7. room list


async def test_linked_academician_reads_the_bookable_rooms(real: dict[str, Any]) -> None:  # noqa: F811
    c, h, tid = real["client"], real["admin"], real["term_id"]
    _rid, iid, _dept = await _row(tid, ROW)
    _uid, teacher = await _teacher(c, h, iid, "ptl.odalar@uni.edu.tr")
    async with dbmod.get_session_factory()() as s:
        rooms = list((await s.execute(select(Room))).scalars())
        c301 = next(r for r in rooms if r.code == "C301")
        c301.notes = "anahtar güvenlikte"  # an internal note never leaves the server
        closed = next(r for r in rooms if r.is_bookable and r.code != "C301")
        closed.is_bookable = False
        await s.commit()
        bookable = sorted(r.code for r in rooms if r.is_bookable)
    r = await c.get(f"{API}/moderation/me/rooms", headers=teacher)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert sorted(x["code"] for x in items) == bookable and closed.code not in {x["code"] for x in items}
    one = next(x for x in items if x["code"] == "C301")
    assert one == {
        "id": c301.id,
        "code": "C301",
        "name": "C 301",
        "capacity": 72,
        "building": "C",
        "building_name": one["building_name"],
        "tags": one["tags"],
        "bookable": True,
    }
    assert "anahtar" not in r.text
    # the list is sorted by building then code, and every room has a building letter
    assert [x["code"] for x in items] == [x["code"] for x in sorted(items, key=lambda x: (x["building"], x["code"]))]
    # nobody else's account: an unlinked user is refused with TR + EN, a planner may read it too
    _u2, stranger = await make_user(c, h, "baska.kullanici@uni.edu.tr", role="TEACHER")
    r = await c.get(f"{API}/moderation/me/rooms", headers=stranger)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_linked" and r.json()["detail"]["message_tr"]
    _p, planner = await make_user(c, h, "koordinator.odalar@uni.edu.tr", role="PLANNER")
    assert (await c.get(f"{API}/moderation/me/rooms", headers=planner)).status_code == 200


# ------------------------------------------------------------------------------------------- 8. approval-first


async def test_approval_first_single_request_is_202_with_policies_on(env) -> None:  # noqa: F811
    """``e2e/approval-first.spec.ts`` ``requestOne`` (tests 3 and 5) on the backend, step for step: a new room in
    A 101's group, an administrator approving for every room, a teacher made through ``POST /users``, P8 policies
    switched on (one the request satisfies, one that would make it a request anyway) and ``approval_mode = all``.
    A teacher's single booking of a free period is a PENDING request (202), never a booking (201); P8 (which only
    refuses or adds a request) cannot turn it into one. With ``approval_mode = rules`` the same call is 201: the
    spec gets 201 exactly when its own test 1 (which switches the mode to ``all`` in the UI) has not run first."""
    c, h = env.client, env.admin
    r = await c.put("/api/v1/org/settings", json={"approval_mode": "all"}, headers=h)
    assert r.status_code == 200 and r.json()["approval_mode"] == "all", r.text
    groups = (await c.get("/api/v1/room-admin/groups", headers=h)).json()
    if not groups:
        groups = (await c.post("/api/v1/room-admin/groups/from-buildings", headers=h)).json()
    rooms = (await c.get("/api/v1/room-admin/rooms", headers=h)).json()
    group_a = next(x for x in rooms if x["code"] == "A101")["room_group_id"]
    assert group_a
    room = (
        await c.post(
            "/api/v1/rooms", json={"code": "AF 512", "display_name": "E2E Onay Dersliği", "capacity": 60}, headers=h
        )
    ).json()
    r = await c.put(
        f"/api/v1/room-admin/rooms/{room['id']}", json={"room_group_id": group_a, "is_bookable": True}, headers=h
    )
    assert r.status_code == 200, r.text
    admin_id, _approver = await env.user("af.yonetici@uni.edu.tr", role="ADMIN")
    r = await c.put(f"/api/v1/approvals/approvers/{admin_id}", json={"scopes": [{"type": "all"}]}, headers=h)
    assert r.status_code in (200, 201), r.text
    _tid, teacher = await env.user("af.hoca@uni.edu.tr", firstname="Pınar", lastname="Tekin")
    for body in (
        {"name": "En fazla 180 gün", "max_advance_days": 180},  # the request satisfies it
        {
            "name": "Öğle arası onaylı",
            "effect": "request",
            "quiet_hours": [{"weekdays": [5], "start": "12.40", "end": "13:20"}],
        },
    ):
        r = await c.post("/api/v1/booking-policies", json=body, headers=h)
        assert r.status_code == 201, r.text
    friday = "2026-02-20"  # the spec's FRIDAY
    payload = {"room_id": room["id"], "date": friday, "period_id": env.periods["P2"], "notes": "Telafi dersi"}
    r = await c.post("/api/v1/bookings", json={**payload, "term_id": env.term_id}, headers=teacher)
    assert r.status_code == 202 and r.json()["status"] == "PENDING", r.text
    mine = (await c.get("/api/v1/approvals/mine", headers=teacher)).json()
    req = next(x for x in mine if x["booking_id"] == r.json()["id"])
    assert req["status"] == "PENDING"
    # the policy that makes a slot request-only (Friday 12:40) is a request too, still 202
    r = await c.post(
        "/api/v1/bookings", json={**payload, "period_id": env.periods["P6"], "term_id": env.term_id}, headers=teacher
    )
    assert r.status_code == 202 and r.json()["status"] == "PENDING", r.text
    # the spec's precondition: without approval_mode = all the teacher books the free period directly
    r = await c.put("/api/v1/org/settings", json={"approval_mode": "rules"}, headers=h)
    assert r.status_code == 200
    r = await c.post(
        "/api/v1/bookings", json={**payload, "period_id": env.periods["P3"], "term_id": env.term_id}, headers=teacher
    )
    assert r.status_code == 201 and r.json()["status"] == "BOOKED", r.text
