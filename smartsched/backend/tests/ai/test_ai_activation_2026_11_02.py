"""Owner report 2026-11-02: "AI was not working in the finder (Boş derslik bul) and other parts although I added the
API key". The key the admin saved in the panel was found by the gateway, but the helper (the AI on every page,
Boş derslik bul included) needs an explicit ``helper`` route and stayed in guide mode (``reason: not_routed``).

Now a saved key routes ``helper`` when it has no route (app/ai/activation.py), from the panel, from Settings, at
deploy time and once at start-up; the KVKK consent gate stays, honouring the admin's ``included`` default.
No network: the key is a fake and no model is called.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from app.ai import activation
from app.ai import gateway as gw
from app.ai.helper import status as st
from app.core import db as dbmod
from app.core.security import hash_password
from app.models import AuditEvent, Setting, User
from app.services import kvkk
from app.services import settings_service as ss
from sqlalchemy import select

from tests.api_fixtures import client, login  # noqa: F401 - fixture

KEY = "sk-ant-api03-" + "x" * 40
TEACHER = ("ogretmen@uni.edu.tr", "parola-ogretmen-1234")


async def _teacher(*, consent: bool) -> int:
    async with dbmod.get_session_factory()() as s:
        u = User(email=TEACHER[0], password_hash=hash_password(TEACHER[1]), role="TEACHER", full_name="Ayşe Öğretmen")
        s.add(u)
        await s.commit()
        if consent:
            await kvkk.grant(s, u, "ai_personal")
            await s.commit()
        return u.id


async def _status(client, user=TEACHER) -> dict:  # noqa: F811
    h = await login(client, *user)
    r = await client.get("/api/v1/helper/status", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def _routes() -> dict:
    async with dbmod.get_session_factory()() as s:
        return await gw.get_routes(s)


# ------------------------------------------------------------------ the reported failure, and the fix


async def test_a_key_saved_in_admin_ai_switches_the_helper_on_for_a_teacher(client):  # noqa: F811
    await _teacher(consent=True)
    assert (await _status(client))["reason"] == "not_routed"  # no key yet: guide mode
    admin = await login(client)
    r = await client.put("/api/v1/ai/admin/providers/anthropic", json={"api_key": KEY}, headers=admin)
    assert r.status_code == 200, r.text
    assert KEY not in r.text
    state = await _status(client)
    assert state["mode"] == "ai" and state["reason"] is None, state
    assert (await _routes())["features"]["helper"] == {"provider": "anthropic", "model": "claude-opus-5-5"}
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "ai.routes"))).scalars().all()
        assert len(ev) == 1 and "Admin > AI" in (ev[0].reason or "") and KEY not in json.dumps(ev[0].after)


async def test_a_key_saved_in_settings_ai_switches_the_helper_on(client):  # noqa: F811
    await _teacher(consent=True)
    admin = await login(client)
    r = await client.put("/api/v1/settings", json={"anthropic_api_key": KEY}, headers=admin)
    assert r.status_code == 200, r.text
    assert (await _status(client))["mode"] == "ai"


async def test_an_admins_helper_route_is_kept(client):  # noqa: F811
    async with dbmod.get_session_factory()() as s:
        mine = {"provider": "anthropic", "model": "claude-sonnet-5-5"}
        await gw.put_json(s, gw.ROUTES_KEY, {"features": {"helper": mine}})
        await s.commit()
    admin = await login(client)
    await client.put("/api/v1/ai/admin/providers/anthropic", json={"api_key": KEY}, headers=admin)
    assert (await _routes())["features"]["helper"] == mine


async def test_saving_other_settings_activates_nothing(client):  # noqa: F811
    admin = await login(client)
    r = await client.put("/api/v1/ai/admin/providers/anthropic", json={"enabled": True}, headers=admin)
    assert r.status_code == 200
    assert "helper" not in (await _routes())["features"]


# ------------------------------------------------------------------ activate / activate_once


async def test_without_a_usable_provider_nothing_is_written(session):
    out = await activation.activate(session, actor=None, reason="test")
    assert out == {"helper": "no_provider"}
    assert (
        await session.get(Setting, gw.ROUTES_KEY) is None and await session.get(Setting, activation.MARKER_KEY) is None
    )


async def test_the_default_route_is_followed(session):
    await gw.put_json(session, "ai.provider.openai.config", {"enabled": True})
    await gw.set_provider_secret(session, "openai", "api_key", "sk-proj-" + "y" * 30)
    await gw.put_json(session, gw.ROUTES_KEY, {"default": {"provider": "openai", "model": "gpt-5.5"}})
    await session.commit()
    out = await activation.activate(session, actor=None, reason="test")
    assert out == {"helper": "routed", "provider": "openai", "model": "gpt-5.5"}


async def test_start_up_activates_a_key_saved_before_the_change_once(session):
    await ss.set_value(session, "anthropic_api_key", KEY)  # saved earlier, no helper route
    assert await st.routing_reason(session) == "not_routed"
    assert (await activation.activate_once(session))["helper"] == "routed"
    assert await st.routing_reason(session) is None
    # an admin removes the helper route afterwards: a restart does not put it back
    await gw.put_json(session, gw.ROUTES_KEY, {"features": {}})
    await session.commit()
    assert await activation.activate_once(session) == {"helper": "done"}
    assert await st.routing_reason(session) == "not_routed"


async def test_start_up_without_a_key_tries_again_later(session):
    assert (await activation.activate_once(session))["helper"] == "no_provider"
    await ss.set_value(session, "anthropic_api_key", KEY)
    assert (await activation.activate_once(session))["helper"] == "routed"


# ------------------------------------------------------------------ KVKK consent gate (unchanged default)


async def test_consent_gate_follows_the_admins_ai_personal_default(session):
    await ss.set_value(session, "anthropic_api_key", KEY)
    await activation.activate(session, actor=None, reason="test")
    u = User(email="t@uni.edu.tr", password_hash=hash_password("parola-1234-abcd"), role="TEACHER")
    session.add(u)
    await session.commit()
    # the default stays "excluded": never granted = no AI answers, the chip links to Profil > Gizlilik
    assert (await st.helper_status(session, u.id, turn_available=True))["reason"] == "consent_missing"
    await ss.set_value(session, kvkk.AI_PERSONAL_DEFAULT_KEY, "included")  # the admin's explicit choice
    assert (await st.helper_status(session, u.id, turn_available=True))["mode"] == "ai"
    await kvkk.grant(session, u, "ai_personal")
    await session.commit()
    await kvkk.withdraw(session, u, "ai_personal")
    await session.commit()
    assert (await st.helper_status(session, u.id, turn_available=True))["reason"] == "consent_missing"


# ------------------------------------------------------------------ deploy time (seed/bootstrap_settings.py)


def _bootstrap():
    path = Path(__file__).resolve().parents[3] / "deploy/seed/bootstrap_settings.py"
    if not path.is_file():
        pytest.skip("deploy tool not in this checkout")
    spec = importlib.util.spec_from_file_location("bootstrap_settings_t", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


async def test_deploy_time_key_routes_the_helper_too(session):
    boot = _bootstrap()
    session.add(User(email="admin@uni.edu.tr", password_hash=hash_password("parola-admin-1234"), role="ADMIN"))
    await session.commit()
    out = await boot.run(boot.collect({"AI_API_KEY": KEY}), boot.AppBackend(session), log=lambda _m: None)
    assert out.applied == ["ai"]
    assert await gw.provider_secrets(session, "anthropic") == {"api_key": KEY}
    assert await st.routing_reason(session) is None
