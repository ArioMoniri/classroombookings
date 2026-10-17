"""U2 follow-up (pod CI e2e 2026-10-17): the request that LOSES the first-visit draft race keeps its loaded rows.

`_create_draft` used to roll the whole session back on the unique (term, user, kind) violation, which expired the
request's `User`; PUT /terms/{id}/studio then touched `user` in update_draft -> MissingGreenlet -> 500, logged as
`IntegrityError: UNIQUE constraint failed: studio_drafts.term_id, studio_drafts.user_id, studio_drafts.kind`, and
the studio's Generate never reached /runs/<id> (real-backend.spec.ts:39)."""

from __future__ import annotations

import asyncio

from app.core.db import get_session_factory
from app.models import StudioDraft, User
from app.services import studio as st
from sqlalchemy import func, inspect, select

from tests import studio_support
from tests.studio_support import PLANNER

bahar = studio_support.bahar


async def test_losing_create_keeps_the_request_rows_loaded(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    assert (await c.get(url, params={"kind": "EXAM"}, headers=h)).status_code == 200  # the winner's draft exists
    async with get_session_factory()() as s:
        user = (await s.execute(select(User).where(User.email == PLANNER[0]))).scalar_one()
        draft = await st._create_draft(s, bahar.term_id, user.id, "EXAM")  # INSERT loses on the unique key
        assert draft.kind == "EXAM" and draft.user_id == user.id
        assert not inspect(user).expired_attributes  # a full rollback expired it (lazy load -> MissingGreenlet)
        assert user.email == PLANNER[0]


async def test_first_get_and_put_race_to_one_draft_without_500(bahar):
    c, h, url = bahar.client, bahar.planner, f"/api/v1/terms/{bahar.term_id}/studio"
    put = {"kind": "EXAM", "version": 1, "horizon": "TERM"}
    res = await asyncio.gather(
        *(c.get(url, params={"kind": "EXAM"}, headers=h) for _ in range(3)),
        *(c.put(url, json=put, headers=h) for _ in range(3)),
    )
    assert all(r.status_code in (200, 409) for r in res), [r.text for r in res if r.status_code not in (200, 409)]
    async with get_session_factory()() as s:
        n = (
            await s.execute(
                select(func.count(StudioDraft.id)).where(
                    StudioDraft.term_id == bahar.term_id, StudioDraft.kind == "EXAM"
                )
            )
        ).scalar_one()
    assert n == 1
