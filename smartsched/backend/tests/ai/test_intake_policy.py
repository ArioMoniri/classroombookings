"""D7 / P19-A1: AI intake and vision switches (default OFF) with a KVKK sign-off record.

With intake off, an uploaded file is read locally and routed to "needs AI": no client is built and no request
reaches the (fake) SDK. Only an administrator can switch it on, and only with the KVKK acknowledgement; the
sign-off (who, when, legal basis, notice version) is stored and audited. A flag set without a sign-off (e.g.
through the generic settings ``extra``) does not count.
"""

from __future__ import annotations

from app.ai.policy import INTAKE_KEY, ai_allowed, get_policy
from app.core.db import get_session_factory
from app.core.security import hash_password
from app.models import AuditEvent, User
from app.services import settings_service as ss
from sqlalchemy import select

from tests.ai.conftest import empty_params, empty_selector, proposal, seed_small, store_key, tool
from tests.api_fixtures import login

MEMO = "PHAR 240 dersi 23 Şubat'tan itibaren A 206'da olsun.\nİletişim: ayse@uni.edu.tr, 0532 123 45 67\n".encode()


async def _planner(client) -> dict[str, str]:
    async with get_session_factory()() as s:
        s.add(User(email="planner@uni.edu.tr", password_hash=hash_password("planner-123"), role="PLANNER"))
        await s.commit()
    return await login(client, "planner@uni.edu.tr", "planner-123")


async def _upload(client, term_id: int, h: dict[str, str]):
    return await client.post(
        f"/api/v1/terms/{term_id}/preferences/upload",
        files={"file": ("memo.txt", MEMO, "text/plain")},
        data={"lang": "tr"},
        headers=h,
    )


async def test_switches_default_off(session):
    assert not await ai_allowed(session, "intake")
    assert not await ai_allowed(session, "vision")
    pol = await get_policy(session)
    assert pol["intake_enabled"] is False and pol["vision_enabled"] is False and pol["signoff"] is None
    assert pol["notice"]["tr"] and pol["notice"]["en"]


async def test_upload_with_intake_off_sends_nothing(client, fake_sdk):
    h = await login(client)
    async with get_session_factory()() as s:
        sd = await seed_small(s)
        await store_key(s)
    r = await _upload(client, sd.term_id, h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["needs_ai"] is True and out["proposals"] == [] and out["units"] == 2
    assert out["unparsed"] and all("AI" in u["reason"] for u in out["unparsed"])
    assert fake_sdk.calls == [] and fake_sdk.instances == []  # 0 calls, not even a client


async def test_flag_without_signoff_does_not_count(session):
    await ss.set_value(session, INTAKE_KEY, "true")  # e.g. PUT /settings {"extra": {...}}
    assert not await ai_allowed(session, "intake")


async def test_admin_signoff_enables_intake(client, fake_sdk):
    admin = await login(client)
    planner = await _planner(client)
    async with get_session_factory()() as s:
        sd = await seed_small(s)
        await store_key(s)

    assert (await client.get("/api/v1/ai/policy", headers=planner)).status_code == 200
    r = await client.put("/api/v1/ai/policy", json={"intake_enabled": True, "kvkk_ack": True}, headers=planner)
    assert r.status_code == 403
    r = await client.put("/api/v1/ai/policy", json={"intake_enabled": True}, headers=admin)
    assert r.status_code == 422 and "KVKK" in r.text
    r = await client.put("/api/v1/ai/policy", json={"vision_enabled": True, "kvkk_ack": True}, headers=admin)
    assert r.status_code == 422  # vision needs intake

    r = await client.put("/api/v1/ai/policy", json={"intake_enabled": True, "kvkk_ack": True}, headers=admin)
    assert r.status_code == 200, r.text
    pol = r.json()
    assert pol["intake_enabled"] is True and pol["vision_enabled"] is False
    sign = pol["signoff"]
    assert sign["features"] == ["intake"] and sign["by"] and sign["at"] and "KVKK" in sign["legal_basis"]
    assert sign["notice_version"]

    fake_sdk.script = [
        tool(
            "propose_constraints",
            {
                "proposals": [
                    proposal(
                        "room_pin",
                        selector=empty_selector(course_codes=["PHAR 240"]),
                        params=empty_params(room_codes=["A 206"]),
                        source_ref=1,
                    )
                ],
                "section_edits": [],
                "unparsed": [],
            },
        )
    ]
    r = await _upload(client, sd.term_id, planner)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["needs_ai"] is False and len(fake_sdk.calls) == 1
    sent = fake_sdk.calls[0]["messages"][0]["content"]
    # KVKK: contact data is redacted before it leaves the server
    assert "ayse@uni.edu.tr" not in sent and "0532" not in sent and "[e-posta]" in sent and "[telefon]" in sent
    assert out["redactions"] == {"emails": 1, "phones": 1}

    # switching it off again is recorded too, and uploads stop reaching the model
    r = await client.put("/api/v1/ai/policy", json={"intake_enabled": False}, headers=admin)
    assert r.status_code == 200 and r.json()["intake_enabled"] is False
    r = await _upload(client, sd.term_id, planner)
    assert r.json()["needs_ai"] is True and len(fake_sdk.calls) == 1
    async with get_session_factory()() as s:
        acts = (await s.execute(select(AuditEvent.action).where(AuditEvent.action == "ai.policy"))).scalars().all()
    assert len(acts) == 2
