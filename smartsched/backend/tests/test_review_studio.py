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
