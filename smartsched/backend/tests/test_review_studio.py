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
