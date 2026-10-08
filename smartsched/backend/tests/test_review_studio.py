"""Review 2026-10-08 regressions in the Generator Studio on the real Bahar 2026 import: M1 (atomic draft
versioning), U2 (first-visit draft race), M3 (coupled-field revert), M5 (pre-check fixes)."""

from __future__ import annotations

import asyncio

import pytest
from app.core.db import get_session_factory
from app.models import StudioDraft, User
from app.services import studio as st
from sqlalchemy import func, select

from tests import studio_support
from tests.studio_support import PLANNER, meeting_id

bahar = studio_support.bahar


async def _planner() -> User:
    async with get_session_factory()() as s:
        return (await s.execute(select(User).where(User.email == PLANNER[0]))).scalar_one()


async def test_m1_conditional_update_loses_the_race_with_409(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    d = (await c.get(url, headers=h)).json()
    a, b = await meeting_id("PHAR 240", day=1, start=1), await meeting_id("PHAR 290", day=3, start=9)
    user = await _planner()
    from app.schemas.studio import DraftIn

    factory = get_session_factory()
    async with factory() as s1, factory() as s2:  # both load version 1 before either writes
        d1 = await s1.get(StudioDraft, d["draft_id"])
        d2 = await s2.get(StudioDraft, d["draft_id"])
        assert d1 is not None and d2 is not None and d1.version == d2.version == d["version"]
        await st.update_draft(s1, d1, DraftIn(excluded_event_ids=[a]), user, expected_version=d1.version)
        with pytest.raises(st.StudioError) as exc:
            await st.update_draft(s2, d2, DraftIn(excluded_event_ids=[b]), user, expected_version=d2.version)
        assert exc.value.status == 409
    final = (await c.get(url, headers=h)).json()
    assert final["excluded_event_ids"] == [a] and final["version"] == d["version"] + 1  # no lost update


async def test_m1_concurrent_puts_one_wins(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    d = (await c.get(url, headers=h)).json()
    ids = [await meeting_id("PHAR 240", day=1, start=1), await meeting_id("PHAR 290", day=3, start=9)]
    bodies = [{"version": d["version"], "excluded_event_ids": [i]} for i in ids] + [
        {"version": d["version"], "pins": [{"event_id": ids[0], "day": 2}]}
    ]
    res = await asyncio.gather(*(c.put(url, json=b, headers=h) for b in bodies))
    codes = sorted(r.status_code for r in res)
    assert codes == [200, 409, 409], [r.text for r in res]
    final = (await c.get(url, headers=h)).json()
    assert final["version"] == d["version"] + 1
    winner = next(b for b, r in zip(bodies, res, strict=True) if r.status_code == 200)
    if "pins" in winner:
        assert final["excluded_event_ids"] == [] and final["pins"]
    else:
        assert final["excluded_event_ids"] == winner["excluded_event_ids"] and final["pins"] == []


async def test_u2_first_visits_race_to_one_draft(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    res = await asyncio.gather(*(c.get(url, params={"kind": "EXAM"}, headers=h) for _ in range(6)))
    assert [r.status_code for r in res] == [200] * 6, [r.text for r in res if r.status_code != 200]
    assert len({r.json()["draft_id"] for r in res}) == 1
    async with get_session_factory()() as s:
        n = (
            await s.execute(
                select(func.count(StudioDraft.id)).where(StudioDraft.term_id == bahar.term_id, StudioDraft.kind == "EXAM")
            )
        ).scalar_one()
    assert n == 1


async def test_m3_revert_restores_coupled_groups(bahar):
    c, h = bahar.client, bahar.planner
    phar = await meeting_id("PHAR 240", day=1, start=1)  # PHAR 240 §1, Mon P1-P3, LOCKED in A 206
    r = await c.put(
        "/api/v1/studio/meetings/bulk", json={"ids": [phar], "patch": {"day": 2, "start_period": 4}}, headers=h
    )
    assert r.status_code == 200 and r.json()["updated"] == 1, r.text
    row = r.json()["rows"][0]
    assert (row["day"], row["start_period"], row["end_period"]) == (2, 4, 6)
    # old code: start reverted alone -> P1-P6 (start without its end); now the whole time group
    r = await c.post(f"/api/v1/studio/meetings/{phar}/revert", json={"fields": ["start_period"]}, headers=h)
    assert r.status_code == 200, r.text
    row = r.json()
    assert (row["start_period"], row["end_period"], row["time_label"]) == (1, 3, "08:30-10:50")
    assert row["day"] == 2  # the day group was not asked for
    # old code: days reverted alone -> days [1] but day 2
    r = await c.post(f"/api/v1/studio/meetings/{phar}/revert", json={"fields": ["days"]}, headers=h)
    row = r.json()
    assert (row["day"], row["days"]) == (1, [1]) and row["changed_fields"] == []


async def test_m3_edit_cannot_leave_a_locked_class_without_its_room(bahar):
    c, h = bahar.client, bahar.planner
    phar = await meeting_id("PHAR 240", day=1, start=1)
    r = await c.put(
        "/api/v1/studio/meetings/bulk", json={"ids": [phar], "patch": {"definitive_room_ids": []}}, headers=h
    )
    res = r.json()["results"][0]
    assert not res["ok"] and "locked class needs its room" in res["errors"][0]
    r = await c.put(  # unlocking in the same patch is fine
        "/api/v1/studio/meetings/bulk",
        json={"ids": [phar], "patch": {"definitive_room_ids": [], "locked": False}},
        headers=h,
    )
    assert r.json()["results"][0]["ok"], r.text


async def _locked_small_item(bahar) -> tuple[int, dict, int]:
    from tests.studio_support import room

    phar = await meeting_id("PHAR 240", day=1, start=1)  # locked in A 206
    a206 = await room("A206")
    r = await bahar.client.put(
        "/api/v1/studio/meetings/bulk", json={"ids": [phar], "patch": {"enrolment": a206.capacity + 20}}, headers=bahar.planner
    )
    assert r.status_code == 200
    pre = (await bahar.client.post(f"/api/v1/terms/{bahar.term_id}/studio/precheck", headers=bahar.planner)).json()
    item = next(it for it in pre["items"] if phar in it["event_ids"] and it["group"] == "locked_small")
    return phar, item, pre["version"]


async def test_m5_fix_stays_in_the_draft_and_write_through_needs_confirm(bahar):
    c, h = bahar.client, bahar.planner
    url = f"/api/v1/terms/{bahar.term_id}/studio/precheck/fix"
    phar, item, version = await _locked_small_item(bahar)
    # stale If-Match -> 409; write-through without confirm -> 428
    r = await c.post(url, json={"item_id": item["id"], "option": "rooms"}, headers={**h, "If-Match": f'"{version + 7}"'})
    assert r.status_code == 409, r.text
    r = await c.post(url, json={"item_id": item["id"], "option": "rooms", "write_through": True}, headers=h)
    assert r.status_code == 428
    # another planner's draft is not affected by a draft-only fix
    r = await c.post(url, json={"item_id": item["id"], "option": "rooms", "version": version}, headers=h)
    assert r.status_code == 200, r.text
    admin_draft = (await c.get(f"/api/v1/terms/{bahar.term_id}/studio", headers=bahar.admin)).json()
    assert admin_draft["pins"] == []
    row = (await c.get(f"/api/v1/terms/{bahar.term_id}/studio/classes", params={"ids": str(phar)}, headers=h)).json()["items"][0]
    assert row["locked"]


async def test_m5_confirmed_write_through_never_unlocks(bahar):
    c, h = bahar.client, bahar.planner
    url = f"/api/v1/terms/{bahar.term_id}/studio/precheck/fix"
    phar, item, _ = await _locked_small_item(bahar)
    rooms = next(f for f in item["fixes"] if f["option"] == "rooms")["action"]["payload"]["patch"]["requested_room_ids"]
    r = await c.post(url, json={"item_id": item["id"], "option": "rooms", "write_through": True, "confirm": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["applied"]["scope"] == "term"
    row = (await c.get(f"/api/v1/terms/{bahar.term_id}/studio/classes", params={"ids": str(phar)}, headers=h)).json()["items"][0]
    assert row["requested_room_ids"] == rooms  # written term-wide (with snapshot)
    assert row["status"] == "LOCKED" and row["locked"]  # ...but the LOCK is only lifted in the draft
    assert r.json()["draft"]["pins"] == [{"event_id": phar, "unlock": True}]


async def test_m5_exam_write_through_takes_a_snapshot(bahar):
    from app.models import ExamRequest, ImportedSnapshot
    from app.services import precheck as pc

    async with get_session_factory()() as s:
        ex = ExamRequest(term_id=bahar.term_id, course_code="PHAR240", enrolment=80, requested_room_count=1, status="LOCKED", source_key="EX:t#0")
        s.add(ex)
        await s.commit()
        draft = await st.get_draft(s, bahar.term_id, (await _planner()).id, "EXAM")
        await pc._write_through(s, draft, "exam_update", [ex.id], {"requested_room_count": 3}, await _planner())
        await s.commit()
        snap = (
            await s.execute(select(ImportedSnapshot).where(ImportedSnapshot.entity == "exam", ImportedSnapshot.entity_id == ex.id))
        ).scalar_one()
        await s.refresh(ex)
        assert snap.values == {"requested_room_count": 1, "status": "LOCKED"}
        assert ex.requested_room_count == 3 and ex.status == "LOCKED"


async def test_m10_constraint_crud_is_validated_and_builtins_protected(bahar):
    c, h, adm = bahar.client, bahar.planner, bahar.admin
    url = "/api/v1/constraints"
    base = {"term_id": bahar.term_id, "hardness": "soft", "weight": 3}
    bad = [
        {**base, "kind": "capacity", "params": {}, "source": "BUILTIN"},  # spoofed source
        {**base, "kind": "capacity", "params": {}, "source": "AI"},
        {**base, "kind": "make_everyone_happy", "params": {}},  # unknown kind
        {**base, "kind": "building_preference", "params": {"building": 42}},  # bad params
        {**base, "kind": "building_preference", "params": {"building": "C"}, "weight": 10**6},
        {**base, "kind": "x" * 200, "params": {}},  # MINOR 4: would be a Postgres-only 500
        {**base, "kind": "building_preference", "params": {"building": "C"}, "nl_text": "y" * 5000},
    ]
    for body in bad:
        r = await c.post(url, json=body, headers=h)
        assert r.status_code == 422, (body, r.text)
    ok = await c.post(url, json={**base, "kind": "building_preference", "params": {"building": "C"}}, headers=h)
    assert ok.status_code == 201, ok.text
    assert (await c.put(f"{url}/{ok.json()['id']}", json={"params": {"building": 7}}, headers=h)).status_code == 422
    # an ADMIN switches a built-in off in their draft; the planner can neither see nor undo it
    d = (await c.get(f"/api/v1/terms/{bahar.term_id}/studio", headers=adm)).json()
    r = await c.put(
        f"/api/v1/terms/{bahar.term_id}/studio",
        json={"version": d["version"], "disabled_builtin_kinds": ["capacity"]},
        headers=adm,
    )
    assert r.status_code == 200, r.text
    from app.models import ConstraintRow

    async with get_session_factory()() as s:
        builtin = (await s.execute(select(ConstraintRow).where(ConstraintRow.source == "BUILTIN"))).scalar_one()
    listed = (await c.get(url, params={"term_id": bahar.term_id}, headers=h)).json()
    assert builtin.id not in {x["id"] for x in listed}
    assert (await c.put(f"{url}/{builtin.id}", json={"enabled": True}, headers=h)).status_code == 403
    assert (await c.delete(f"{url}/{builtin.id}", headers=h)).status_code == 403
    assert (await c.delete(f"{url}/{builtin.id}", headers=adm)).status_code == 403
