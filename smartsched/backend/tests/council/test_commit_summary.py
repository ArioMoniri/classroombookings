"""The commit's own summary (T-R1-24): the constraints the commit wrote (the planning list importer's preference
rules and the accepted rule proposals) are counted in ``constraints_total``, equal to the term's constraint delta,
and the commit is stated irreversible (``reversible: false``) in the answer and its audit event. Real Bahar list."""

from __future__ import annotations

from app.core.db import get_session_factory
from app.models import AuditEvent, ConstraintRow
from sqlalchemy import func, select

from tests.api_fixtures import login
from tests.council.conftest import BAHAR_LIST
from tests.council.test_formats_api import upload


async def _constraints() -> int:
    async with get_session_factory()() as s:
        return int((await s.execute(select(func.count()).select_from(ConstraintRow))).scalar_one())


async def test_commit_counts_every_constraint_it_writes(client):
    h = await login(client)
    job = await upload(client, h, (BAHAR_LIST.name, BAHAR_LIST.read_bytes()))
    body = {"group": 0, "term": {"code": "2026-BAHAR", "week_count": 14}, "allow_pending": True}
    dry = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json={**body, "dry_run": True})
    assert dry.status_code == 200, dry.text
    planned = dry.json()["counts"].get("constraints", {}).get("create", 0)
    before = await _constraints()
    r = await client.post(f"/api/v1/council/jobs/{job['id']}/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    delta = await _constraints() - before
    assert delta > 0 and out["constraints_total"] == delta == planned
    assert out["reversible"] is False
    async with get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "council.commit"))).scalar_one()
    assert ev.after["constraints_total"] == delta and ev.reversible is False
