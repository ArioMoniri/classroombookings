"""One AI policy for every path that sends uploaded content (coordinator 2026-10-15, after the universal merge).

``app.ai.policy.ai_allowed(db, kind)`` is the single check: the chat upload and the Ingestion Council call it
(``intake`` for text, ``vision`` for scans/images). The council's ``council_ai_enabled`` settings toggle is the
same switch: writing it goes through ``set_policy`` (sign-off record + audit; the toggle carries the KVKK text,
so switching it on is the administrator's acknowledgement) and reading it reports the effective policy. A value
written behind the policy's back no longer opens the council.
"""

from __future__ import annotations

from app.ai.policy import SIGNOFF_KEY, ai_allowed, get_policy
from app.core.db import get_session_factory
from app.models import AuditEvent, Setting
from app.services import settings_service as ss
from sqlalchemy import select

from tests.api_fixtures import login


async def test_settings_toggle_is_the_policy_switch(client):
    h = await login(client)
    view = (await client.get("/api/v1/settings", headers=h)).json()
    assert view["council_ai_enabled"] is False and view["ai_policy"]["intake_enabled"] is False

    r = await client.put("/api/v1/settings", headers=h, json={"council_ai_enabled": True})
    assert r.status_code == 200 and r.json()["council_ai_enabled"] is True
    async with get_session_factory()() as s:
        assert await ai_allowed(s, "intake") and await ai_allowed(s, "vision")
        sign = (await get_policy(s))["signoff"]
        assert sign["features"] == ["intake", "vision"] and sign["acknowledged"] is True
        assert "council_ai_enabled" in sign["reason"]
        assert (await s.execute(select(AuditEvent).where(AuditEvent.action == "ai.policy"))).scalars().first()

    # PUT /ai/policy and the toggle agree both ways
    r = await client.put("/api/v1/ai/policy", headers=h, json={"intake_enabled": False})
    assert r.status_code == 200
    assert (await client.get("/api/v1/settings", headers=h)).json()["council_ai_enabled"] is False
    r = await client.put("/api/v1/settings", headers=h, json={"council_ai_enabled": False})
    assert r.status_code == 200 and r.json()["council_ai_enabled"] is False


async def test_raw_council_flag_does_not_open_the_council(session):
    await ss.set_value(session, "council_ai_enabled", True)  # behind the policy's back
    assert not await ai_allowed(session, "intake")
    assert await session.get(Setting, SIGNOFF_KEY) is None


async def test_council_context_uses_the_policy(session, monkeypatch):
    from app.ai.policy import set_policy
    from app.council.orchestrator import make_ctx
    from app.models import CouncilJob, User

    from tests.ai.conftest import store_key

    await store_key(session)
    admin = User(email="adm@uni.edu.tr", password_hash="x", role="ADMIN")
    session.add(admin)
    await session.commit()
    job = CouncilJob(mode="general", lang="tr", settings={})
    ctx = await make_ctx(job)
    assert ctx.client is None and "AI is off" in ctx.ai_note and ctx.vision is False

    await set_policy(session, admin, intake_enabled=True, kvkk_ack=True)
    ctx = await make_ctx(job)
    assert ctx.client is not None and ctx.vision is False  # text yes, scans need the vision switch
    await set_policy(session, admin, vision_enabled=True, kvkk_ack=True)
    ctx = await make_ctx(job)
    assert ctx.client is not None and ctx.vision is True
