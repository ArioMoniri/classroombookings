"""AU-15 server-side sessions and AU-16 MFA asserted by the identity provider (coordinator decision 2026-10-18).

* every token carries a ``jti``; its first request records a session row; ``GET /auth/sessions`` lists the caller's
  open sessions with the current one marked; ``DELETE /auth/sessions/{id}``, ``POST /auth/sessions/revoke-others`` and
  ``POST /admin/users/{id}/sessions/revoke`` end sessions, and a revoked token answers 401 on its very next request;
* the provider's ``amr`` / ``acr``: with the policy requiring 2FA for the role, a sign-in without asserted MFA is
  refused when "IdP MFA'yı zorunlu tut" is on, else signs in with a one-time step-up notice.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.core import db as dbmod
from app.models import User
from app.models.mfa import UserSession
from app.services import mfa, sessions
from sqlalchemy import func, select

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import API, PASSWORD, audit_rows, bearer, make_user, password_step, set_policy

EMAIL = "deniz.arslan@uni.edu.tr"
SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.6 Mobile/15E148 Safari/604.1"
)


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    sessions.forget()
    admin = await login(client)
    uid, headers = await make_user(client, admin, EMAIL)
    return client, admin, uid, headers


async def _sign_in(c, ua: str | None = None) -> dict[str, str]:  # type: ignore[no-untyped-def]
    step = await password_step(c, EMAIL, **({"User-Agent": ua} if ua else {}))
    return bearer(step["access_token"])


async def test_sessions_are_listed_with_the_current_one_marked(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    phone = await _sign_in(c, SAFARI)
    assert (await c.get(f"{API}/auth/me", headers={**phone, "User-Agent": SAFARI})).status_code == 200
    r = await c.get(f"{API}/auth/sessions", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 2 and sum(1 for x in rows if x["current"]) == 1
    other = next(x for x in rows if not x["current"])
    assert other["device"] == "Safari, iPhone" and "jti" not in str(rows)
    assert all("ip" not in x for x in rows)


async def test_a_revoked_session_fails_on_its_next_request(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    phone = await _sign_in(c, SAFARI)
    assert (await c.get(f"{API}/auth/me", headers=phone)).status_code == 200  # recorded and cached
    rows = (await c.get(f"{API}/auth/sessions", headers=headers)).json()
    other = next(x for x in rows if not x["current"])
    assert (await c.delete(f"{API}/auth/sessions/{other['id']}", headers=headers)).status_code == 204
    r = await c.get(f"{API}/auth/me", headers=phone)
    assert r.status_code == 401 and r.json()["detail"] == "session revoked"
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 200  # this one still works
    assert len(await audit_rows("auth.session_revoked")) == 1


async def test_a_revocation_holds_after_the_cache_is_gone(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    phone = await _sign_in(c)
    await c.get(f"{API}/auth/me", headers=phone)
    other = next(x for x in (await c.get(f"{API}/auth/sessions", headers=headers)).json() if not x["current"])
    await c.delete(f"{API}/auth/sessions/{other['id']}", headers=headers)
    sessions.forget()  # another worker: no cache at all
    assert (await c.get(f"{API}/auth/me", headers=phone)).status_code == 401


async def test_a_revocation_on_another_worker_is_seen_at_once(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Two uvicorn workers (docker-entrypoint default): the worker that answers the phone's next request still holds
    a fresh "not revoked" cache entry. The person's session epoch (on the user row, read anyway) tells it the entry
    is stale, so the revoked token fails on its very next request, not after the cache TTL."""
    c, _admin, _uid, headers = setup
    phone = await _sign_in(c, SAFARI)
    assert (await c.get(f"{API}/auth/me", headers=phone)).status_code == 200  # cached "open" in this process
    other = next(x for x in (await c.get(f"{API}/auth/sessions", headers=headers)).json() if not x["current"])
    monkeypatch.setattr(sessions, "forget", lambda h=None: None)  # the revoking request ran on the other worker
    assert (await c.delete(f"{API}/auth/sessions/{other['id']}", headers=headers)).status_code == 204
    r = await c.get(f"{API}/auth/me", headers=phone)
    assert r.status_code == 401 and r.json()["detail"] == "session revoked"
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 200


async def test_sign_out_others_on_another_worker_is_seen_at_once(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    phone = await _sign_in(c, SAFARI)
    assert (await c.get(f"{API}/auth/me", headers=phone)).status_code == 200
    monkeypatch.setattr(sessions, "forget", lambda h=None: None)
    assert (await c.post(f"{API}/auth/sessions/revoke-others", headers=headers)).json()["revoked"] == 1
    assert (await c.get(f"{API}/auth/me", headers=phone)).status_code == 401
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 200


async def test_sign_out_other_devices(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    others = [await _sign_in(c) for _ in range(2)]
    for h in others:
        await c.get(f"{API}/auth/me", headers=h)
    await c.get(f"{API}/auth/me", headers=headers)
    r = await c.post(f"{API}/auth/sessions/revoke-others", headers=headers)
    assert r.status_code == 200 and r.json()["revoked"] == 2
    for h in others:
        assert (await c.get(f"{API}/auth/me", headers=h)).status_code == 401
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 200
    assert [x["current"] for x in (await c.get(f"{API}/auth/sessions", headers=headers)).json()] == [True]


async def test_someone_elses_session_is_not_found(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    mine = (await c.get(f"{API}/auth/sessions", headers=headers)).json()[0]["id"]
    _bid, bheaders = await make_user(c, admin, "baska.kisi@uni.edu.tr")
    assert (await c.delete(f"{API}/auth/sessions/{mine}", headers=bheaders)).status_code == 404
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 200


async def test_admin_signs_a_person_out_everywhere(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await c.get(f"{API}/auth/me", headers=headers)
    r = await c.post(f"{API}/admin/users/{uid}/sessions/revoke", headers=headers)
    assert r.status_code == 403
    r = await c.post(f"{API}/admin/users/{uid}/sessions/revoke", headers=admin)
    assert r.status_code == 200 and r.json()["revoked"] >= 1
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 401
    assert len(await audit_rows("auth.sessions_revoked_by_admin")) == 1
    fresh = await _sign_in(c)
    assert (await c.get(f"{API}/auth/me", headers=fresh)).status_code == 200


async def test_the_cache_keeps_the_database_out_of_repeat_requests(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    await c.get(f"{API}/auth/me", headers=headers)
    calls = {"n": 0}
    real = dbmod.get_session_factory

    def counting():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real()

    monkeypatch.setattr(dbmod, "get_session_factory", counting)
    for _ in range(5):
        assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 200
    # the session check opens no database session of its own while its cache entry is fresh
    assert calls["n"] == 0
    sessions.forget()
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 200
    assert calls["n"] == 1  # a cache miss: one short read
    async with real()() as s:
        assert (await s.execute(select(func.count(UserSession.id)))).scalar_one() >= 1


async def test_tokens_without_jti_still_work(setup) -> None:  # type: ignore[no-untyped-def]
    from app.core.security import create_access_token

    c, _admin, uid, _headers = setup
    async with dbmod.get_session_factory()() as s:
        u = await s.get(User, uid)
        assert u is not None
        old = create_access_token(u.email or "", {"uid": u.id, "role": u.role, "tv": int(u.token_version or 0)})
    assert (await c.get(f"{API}/auth/me", headers=bearer(old))).status_code == 200


def test_network_is_cut_to_24_or_48_bits() -> None:
    assert sessions.network_of("212.156.4.9") == "212.156.4.0/24"
    assert sessions.network_of("2a02:4e0:2d00:12::5") == "2a02:4e0:2d00::/48"
    assert sessions.network_of("testclient") == ""


# --------------------------------------------------------------------------------------------------
# AU-16
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claims", "ok"),
    [
        ({"amr": ["pwd", "mfa"]}, True),
        ({"amr": ["pwd", "otp"]}, True),
        ({"amr": ["ngcmfa"]}, True),
        ({"amr": ["pwd"]}, False),
        ({}, False),
        ({"acr": "http://schemas.openid.net/pape/policies/2007/06/multi-factor"}, True),
        ({"acr": "urn:mace:incommon:iap:aal2"}, True),
        ({"acr": "1"}, False),
        ({"amr": "mfa"}, False),  # not a list: not trusted
    ],
)
def test_idp_asserted_mfa(claims: dict, ok: bool) -> None:  # type: ignore[type-arg]
    assert mfa.idp_asserted_mfa(claims) is ok


async def test_idp_gate_refuses_or_notices_by_the_provider_switch(setup) -> None:  # type: ignore[no-untyped-def]
    from app.services.sso import PUBLIC_CODES, SsoError, providers_out

    c, admin, uid, _headers = setup
    await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"])
    entra = SimpleNamespace(name="entra", display_name="Microsoft", kind="entra", options={"require_idp_mfa": True})
    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, uid)
        assert user is not None
        await mfa.idp_mfa_gate(s, entra, user, {"amr": ["pwd", "mfa"]})  # asserted: passes
        with pytest.raises(SsoError) as err:
            await mfa.idp_mfa_gate(s, entra, user, {"amr": ["pwd"]})
        assert PUBLIC_CODES[err.value.code] == "idp_mfa_required"
        entra.options = {}
        await mfa.idp_mfa_gate(s, entra, user, {"amr": ["pwd"]})  # off: signs in, notice once
        saml = SimpleNamespace(name="kampus", display_name="Kampüs", kind="saml", options={"require_idp_mfa": True})
        await mfa.idp_mfa_gate(s, saml, user, {})  # SAML is not checked
        notice = await mfa.pop_idp_notice(s, user)
        assert notice["idp_mfa_missing"] is True and "Microsoft" in notice["idp_mfa_message_tr"]
        assert await mfa.pop_idp_notice(s, user) == {}
        await s.commit()
        msgs = (await providers_out(s))["messages"]
    assert "idp_mfa_required" in msgs and msgs["idp_mfa_required"]["tr"]
    assert [e.after["enforced"] for e in await audit_rows("auth.idp_mfa_missing")] == [True, False]


async def test_idp_gate_ignores_roles_the_policy_does_not_cover(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, _headers = setup
    await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["ADMIN"])
    entra = SimpleNamespace(name="entra", display_name="Microsoft", kind="entra", options={"require_idp_mfa": True})
    async with dbmod.get_session_factory()() as s:
        user = await s.get(User, uid)
        assert user is not None
        await mfa.idp_mfa_gate(s, entra, user, {"amr": ["pwd"]})
    assert await audit_rows("auth.idp_mfa_missing") == []


async def test_admin_switches_require_idp_mfa_per_provider(setup) -> None:  # type: ignore[no-untyped-def]
    from app.models.sso import SsoProvider

    c, admin, _uid, headers = setup
    async with dbmod.get_session_factory()() as s:
        s.add(SsoProvider(name="google", kind="google", display_name="Google", enabled=True))
        await s.commit()
        pid = (await s.execute(select(SsoProvider.id).where(SsoProvider.name == "google"))).scalar_one()
    r = await c.put(f"{API}/admin/auth/providers/{pid}/idp-mfa", json={"require": True}, headers=headers)
    assert r.status_code == 403
    r = await c.put(f"{API}/admin/auth/providers/{pid}/idp-mfa", json={"require": True}, headers=admin)
    assert r.status_code == 200 and r.json()["require_idp_mfa"] is True
    listing = (await c.get(f"{API}/admin/auth/providers/idp-mfa", headers=admin)).json()
    assert {"name": "google", "require_idp_mfa": True, "supported": True}.items() <= next(
        p for p in listing if p["name"] == "google"
    ).items()
    assert len(await audit_rows("auth.idp_mfa_setting")) == 1
    assert (
        await c.put(f"{API}/admin/auth/providers/99999/idp-mfa", json={"require": True}, headers=admin)
    ).status_code == 404


async def test_password_kept_working_through_all_of_this(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, _headers = setup
    assert (await password_step(c, EMAIL, PASSWORD))["access_token"]
