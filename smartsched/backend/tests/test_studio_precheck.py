"""Studio pre-check on the real Bahar term: static checker items in plain TR/EN, structured fixes that
apply into the draft (leave out, other rooms + unlock, built-in switch for ADMIN)."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import MeetingRequest, StudioDraft, User
from app.services.studio import build_draft_input
from sqlalchemy import select

from tests import studio_support
from tests.studio_support import bahar_counts, largest_room, meeting_id, room

bahar = studio_support.bahar


async def _precheck(b, headers=None):
    r = await b.client.post(f"/api/v1/terms/{b.term_id}/studio/precheck", headers=headers or b.planner)
    assert r.status_code == 200, r.text
    return r.json()


def _items_for(pre, event_id):
    return [it for it in pre["items"] if event_id in it["event_ids"]]


async def _fix(b, item_id, option, headers=None):
    return await b.client.post(
        f"/api/v1/terms/{b.term_id}/studio/precheck/fix",
        json={"item_id": item_id, "option": option},
        headers=headers or b.planner,
    )


async def test_precheck_finds_too_big_class_and_leave_out_fix(bahar):
    pre = await _precheck(bahar)
    assert pre["readiness"] == "blocked" and pre["counts"]["events"] > 600 and pre["duration_s"] < 10
    assert pre["estimate_s"]["low"] < pre["estimate_s"]["high"] and pre["estimate_s"]["words"]["en"]
    assert all(it["message"]["tr"] and it["message"]["en"] and it["title"]["en"] for it in pre["items"])
    assert sum(g["count"] for g in pre["groups"]) == len(pre["items"]) and pre["groups"][0]["severity"] == "error"
    # pick a plain single-request class that the real term does not already flag
    flagged = {e for it in pre["items"] for e in it["event_ids"]}
    async with get_session_factory()() as s:
        uid = (await s.execute(select(User.id).where(User.email == "planner@example.com"))).scalar_one()
        draft = (await s.execute(select(StudioDraft).where(StudioDraft.user_id == uid))).scalar_one()
        din = await build_draft_input(s, draft)
    ev = next(
        e
        for e in din.inp.events
        if e.locked is None
        and e.needs_room
        and din.members[e.id] == [e.id]
        and e.id not in flagged
        and e.fixed_start
        and not e.required_tags
    )
    r = await bahar.client.put(
        "/api/v1/studio/meetings/bulk", json={"ids": [ev.id], "patch": {"enrolment": 400}}, headers=bahar.planner
    )
    assert r.status_code == 200 and r.json()["updated"] == 1
    pre = await _precheck(bahar)
    mine = _items_for(pre, ev.id)
    assert len(mine) == 1, mine
    item = mine[0]
    assert item["group"] == "capacity" and item["severity"] == "error" and item["category"] == "impossible"
    assert "400 students" in item["message"]["en"] and "400 öğrenci" in item["message"]["tr"]
    big = await largest_room()
    assert f"{big.display_name} ({big.capacity} seats)" in item["message"]["en"]  # display name, not the code
    assert item["classes"][0]["request_ids"] == [ev.id]
    options = {f["option"]: f for f in item["fixes"]}
    assert options["cap_enrolment"]["action"] == {
        "type": "meeting_update",
        "payload": {"request_ids": [ev.id], "patch": {"enrolment": big.capacity}},
    }
    assert options["exclude"]["action"]["type"] == "exclude"
    r = await _fix(bahar, item["id"], "exclude")
    assert r.status_code == 200, r.text
    out = r.json()
    assert ev.id in out["draft"]["excluded_event_ids"] and out["draft"]["version"] == 2
    assert not _items_for(out["precheck"], ev.id)
    assert out["applied"]["type"] == "exclude"
    # the request itself is untouched (left out per draft, not archived)
    async with get_session_factory()() as s:
        mr = await s.get(MeetingRequest, ev.id)
        assert mr.archived is False and mr.needs_room is True
    # stale / unknown items and options
    assert (await _fix(bahar, "pc-doesnotexist", "exclude")).status_code == 404


async def test_precheck_fix_moves_locked_class_to_rooms_that_fit(bahar):
    phar = await meeting_id("PHAR 240", day=1, start=1)  # locked in A 206 (92 seats)
    a206 = await room("A206")
    r = await bahar.client.put(
        "/api/v1/studio/meetings/bulk",
        json={"ids": [phar], "patch": {"enrolment": a206.capacity + 20}},
        headers=bahar.planner,
    )
    assert r.status_code == 200
    pre = await _precheck(bahar)
    mine = _items_for(pre, phar)
    # trust_locked_rooms (run default): the planner's smaller room is kept and reported as a warning
    assert {it["group"] for it in mine} == {"locked_small"}, mine
    item = next(it for it in mine if it["group"] == "locked_small")
    assert item["severity"] == "warning"
    assert a206.display_name in item["message"]["en"] and str(a206.capacity) in item["message"]["en"]
    rooms = next(f for f in item["fixes"] if f["option"] == "rooms")
    patch = rooms["action"]["payload"]["patch"]
    assert patch["locked"] is False and len(patch["requested_room_ids"]) == 3
    r = await _fix(bahar, item["id"], "rooms")
    assert r.status_code == 200, r.text
    assert not _items_for(r.json()["precheck"], phar)
    rows = (
        await bahar.client.get(
            f"/api/v1/terms/{bahar.term_id}/studio/classes", params={"ids": str(phar)}, headers=bahar.planner
        )
    ).json()["items"]
    row = rows[0]
    # review M5: the fix lives in the draft (pin: one of the fitting rooms, lock ignored for this draft);
    # the term's request keeps the planner's LOCK in A 206
    assert row["status"] == "LOCKED" and row["locked"] and row["definitive_room_ids"] == [a206.id]
    assert {f["field"] for f in row["changed_fields"]} == {"enrolment"}
    pins = r.json()["draft"]["pins"]
    assert pins == [{"event_id": phar, "room_ids": patch["requested_room_ids"], "unlock": True}]
    assert r.json()["applied"]["scope"] == "draft"


async def test_builtin_fix_is_admin_only(bahar):
    pre = await _precheck(bahar)
    clash = next(it for it in pre["items"] if it["group"] == "instructor_clash")
    opt = "builtin_off:no_instructor_overlap"
    assert next(f for f in clash["fixes"] if f["option"] == opt)["admin_only"] is True
    assert (await _fix(bahar, clash["id"], opt)).status_code == 403
    pre_a = await _precheck(bahar, bahar.admin)
    clash_a = next(it for it in pre_a["items"] if it["group"] == "instructor_clash")
    r = await _fix(bahar, clash_a["id"], opt, bahar.admin)
    assert r.status_code == 200, r.text
    assert r.json()["draft"]["disabled_builtin_kinds"] == ["no_instructor_overlap"]
    assert not [it for it in r.json()["precheck"]["items"] if it["group"] == "instructor_clash"]
    # the summary reflects the draft
    s = (await bahar.client.get(f"/api/v1/terms/{bahar.term_id}/studio/summary", headers=bahar.admin)).json()
    assert s["readiness"] == r.json()["precheck"]["readiness"] and s["counts"]["builtins_off"] == 1
    n = await bahar_counts(bahar.term_id)
    assert (s["counts"]["rooms"], s["counts"]["weeks"], s["counts"]["classes_total"]) == (
        n["rooms"],
        n["weeks"],
        n["meetings"],
    )
    assert "classes" in s["sentence"]["en"] and "ders" in s["sentence"]["tr"]
