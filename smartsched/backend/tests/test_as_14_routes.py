"""AS-14 route merged by AS-B: ``POST /learning/weights/propose {term_id}`` (planning.admin) learns from the term's
manual edits and writes at most one **draft** season profile (origin learned); nothing is activated."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import Term
from app.models.seasons import SeasonProfile
from sqlalchemy import select

from tests.api_fixtures import login


async def test_propose_without_edits_writes_no_draft(client):  # type: ignore[no-untyped-def]
    h = await login(client)
    async with get_session_factory()() as s:
        t = Term(code="2026-BAHAR", name="2026 Bahar", week_count=14)
        s.add(t)
        await s.commit()
        tid = t.id
    r = await client.post("/api/v1/learning/weights/propose", json={"term_id": tid}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["term_id"] == tid and out["term_code"] == "2026-BAHAR" and out["proposal"] is None
    assert out["edits"] == 0 and out["confidence"] == "none"
    assert out["needs"]["tr"] == "En az 5 elle düzenleme gerekli (şu an 0)" and out["needs"]["en"]
    async with get_session_factory()() as s:
        assert list((await s.execute(select(SeasonProfile))).scalars()) == []
    r = await client.post("/api/v1/learning/weights/propose", json={"term_id": 999_999}, headers=h)
    assert r.status_code == 404 and r.json()["detail"]["message_tr"] == "dönem bulunamadı"
    r = await client.post("/api/v1/learning/weights/propose", json={}, headers=h)
    assert r.status_code == 422
    assert (await client.post("/api/v1/learning/weights/propose", json={"term_id": tid})).status_code == 401
