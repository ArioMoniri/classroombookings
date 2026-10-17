"""Wave-3 integration: the error-group triage (``POST /ops/errors/{id}/status``) is an admin decision shared by
every admin, so each change writes an ``ops.error.status`` audit event with the actor and the before / after status
(test_audit_coverage classifies it as ``event``)."""

from __future__ import annotations

import pytest
from app.core import observability as obs
from app.core.db import get_session_factory
from app.models import AuditEvent
from sqlalchemy import select

from tests.api_fixtures import login


@pytest.fixture(autouse=True)
def _fresh():
    obs.report_limiter.reset()
    yield
    obs.report_limiter.reset()


async def test_error_status_change_is_audited(client):
    admin = await login(client)
    r = await client.post("/api/v1/ops/errors", json={"message": "boom", "kind": "TypeError", "stack": "x"})
    assert r.status_code == 202, r.text
    eid = (await client.get("/api/v1/ops/errors", headers=admin)).json()["items"][0]["id"]
    for st in ("acknowledged", "resolved"):
        r = await client.post(f"/api/v1/ops/errors/{eid}/status", json={"status": st}, headers=admin)
        assert r.status_code == 200, r.text
    async with get_session_factory()() as s:
        rows = (
            (await s.execute(select(AuditEvent).where(AuditEvent.action == "ops.error.status").order_by(AuditEvent.id)))
            .scalars()
            .all()
        )
    assert [(e.before, e.after) for e in rows] == [
        ({"status": "open"}, {"status": "acknowledged"}),
        ({"status": "acknowledged"}, {"status": "resolved"}),
    ]
    assert all(e.entity_type == "error_event" and e.entity_id == str(eid) and e.actor_id for e in rows)
