"""Profile › Güvenlik: a signed-in local user links and unlinks a Google Workspace, generic OIDC (Keycloak) or SAML
(YETKİM) identity (W3-IDP open item, idp-2026-10-18). Linking and unlinking need re-authentication (the password,
or a session younger than 10 minutes, as the other security actions); unlinking is audited
(``auth.identity_unbound``). The administrator rules stay: reset links and 2FA resets only for accounts with a local
password, never for IdP-only ones (``sso_account``).

The seeded administrator (admin@example.com, a local password) is the signed-in user; the providers are the
in-process fakes of test_w3b_idp_fakes.py and the SAML fixture of test_w3b_idp_saml.py."""

from __future__ import annotations

import base64
import zlib
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("signxml")
from app.core import db as dbmod
from app.models import AuditEvent, User
from app.models.sso import UserIdentity
from app.services import mfa
from lxml import etree
from sqlalchemy import select

from tests.test_w3b_idp_fakes import PANEL, idp, query_of  # noqa: F401
from tests.test_w3b_idp_saml import METADATA_URL, SamlIdp, federation_metadata, saml_response

SSO = "/api/v1/auth/sso"


@pytest.fixture
def stale_sessions(monkeypatch):  # type: ignore[no-untyped-def]
    """Every bearer token counts as older than the re-authentication window."""
    monkeypatch.setattr(mfa, "REAUTH_WINDOW", timedelta(seconds=-1))


async def _identities(env: Any) -> dict[str, Any]:
    r = await env.client.get(f"{SSO}/me/identities", headers=env.admin)
    assert r.status_code == 200, r.text
    return r.json()


def _by_slug(out: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["slug"]: p for p in out["providers"]}


async def _link(env: Any, slug: str, **body: Any) -> Any:
    return await env.client.post(f"{SSO}/{slug}/link", json={"confirm": True, **body}, headers=env.admin)


async def _saml_provider(env: Any, monkeypatch: Any) -> SamlIdp:
    from app.services import sso as sso_service

    previous = sso_service.transport

    async def route(req: Any) -> Any:
        if str(req.url) == METADATA_URL:
            return sso_service.http.Response(200, content=federation_metadata())
        return await previous.handle_async_request(req)

    monkeypatch.setattr(sso_service, "transport", sso_service.http.MockTransport(route))
    p = await env.create("saml", preset="yetkim")
    from tests.test_w3b_idp_saml import IDP_ENTITY

    r = await env.put(p["id"], metadata_url=METADATA_URL, idp_entity_id=IDP_ENTITY, invite_only=False)
    assert r.status_code == 200, r.text
    assert (await env.put(p["id"], enabled=True)).status_code == 200
    return SamlIdp(env, "yetkim")


async def test_lists_the_enabled_providers_and_links_keycloak_and_google(idp) -> None:  # noqa: F811
    await idp.keycloak()
    await idp.google_ws()
    out = await _identities(idp)
    assert out["has_password"] is True
    rows = _by_slug(out)
    assert set(rows) == {"keycloak", "google"}  # Entra keeps its own section; it is not configured here anyway
    assert (
        rows["keycloak"]["linked"] is False
        and rows["keycloak"]["label"]
        and rows["google"]["kind"] == "google_workspace"
    )

    # Keycloak: a fresh session needs no password again; the browser goes to the issuer and comes back
    r = await _link(idp, "keycloak")
    assert r.status_code == 200, r.text
    q = query_of(r.json()["authorize_url"])
    loc = await idp.callback("keycloak", q, idp.kc)
    assert urlsplit(loc).path == "/profile" and query_of(loc) == {"sso": "linked", "provider": "keycloak"}
    # Google: the hd-pinned identity (another subject)
    q = query_of((await _link(idp, "google")).json()["authorize_url"])
    loc = await idp.callback("google", q, idp.google, email="admin@uni.edu.tr", sub="1101694844")
    assert query_of(loc)["sso"] == "linked"

    rows = _by_slug(await _identities(idp))
    assert rows["keycloak"]["linked"] is True and rows["keycloak"]["email_at_login"] == "ayse.yilmaz@uni.edu.tr"
    assert rows["google"]["linked"] is True and rows["google"]["linked_at"]
    # a second link to the same provider is refused
    r = await _link(idp, "keycloak")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_linked"
    async with dbmod.get_session_factory()() as s:
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        idents = {i.provider for i in (await s.execute(select(UserIdentity))).scalars()}
        bound = list((await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.identity_bound"))).scalars())
        kind = await mfa.account_type(s, admin)
    assert idents == {"keycloak", "google"} and len(bound) == 2
    assert {(e.after or {}).get("provider") for e in bound} == {"keycloak", "google"}
    # a linked local account keeps its password: still "mixed", so administrators may still reset it
    assert kind == "mixed"


async def test_linking_an_identity_of_another_account_is_refused(idp) -> None:  # noqa: F811
    await idp.keycloak()
    # Ayşe signs up through Keycloak (self sign-up: an IdP-only account)
    assert (await idp.sign_in("keycloak", idp.kc)).status_code == 200
    q = query_of((await _link(idp, "keycloak")).json()["authorize_url"])
    loc = await idp.callback("keycloak", q, idp.kc)
    assert urlsplit(loc).path == "/profile"
    assert query_of(loc)["error"] == "already_linked" and query_of(loc)["provider"] == "keycloak"


async def test_saml_link_and_unlink_need_reauthentication_and_are_audited(idp, monkeypatch, stale_sessions) -> None:  # noqa: F811
    sp = await _saml_provider(idp, monkeypatch)
    assert _by_slug(await _identities(idp))["yetkim"]["linked"] is False
    # an old session: the password is needed, and it must be right
    r = await _link(idp, "yetkim")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_failed"
    assert "Parola" in r.json()["detail"]["tr"]
    r = await _link(idp, "yetkim", password="yanlış-parola")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_failed"
    r = await _link(idp, "yetkim", password="admin1234")
    assert r.status_code == 200, r.text
    url = r.json()["authorize_url"]
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    rid = etree.fromstring(zlib.decompress(base64.b64decode(q["SAMLRequest"]), -15)).get("ID")
    loc = await sp.post(q["RelayState"], saml_response(rid, acs=sp.acs, audience=sp.entity, mail="admin@uni.edu.tr"))
    assert urlsplit(loc).path == "/profile" and query_of(loc) == {"sso": "linked", "provider": "yetkim"}
    row = _by_slug(await _identities(idp))["yetkim"]
    assert row["linked"] is True and row["email_at_login"] == "admin@uni.edu.tr"

    # the linked identity now signs this account in
    rid, relay = await sp.start()
    loc = await sp.post(relay, saml_response(rid, acs=sp.acs, audience=sp.entity, mail="admin@uni.edu.tr"))
    tok = (await idp.client.post(f"{SSO}/exchange", json={"ticket": query_of(loc)["ticket"]})).json()["access_token"]
    me = (await idp.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})).json()
    assert me["email"] == "admin@example.com"

    # unlink: re-authentication first
    r = await idp.client.post(f"{SSO}/yetkim/unlink", json={}, headers=idp.admin)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_failed"
    r = await idp.client.post(f"{SSO}/yetkim/unlink", json={"password": "admin1234"}, headers=idp.admin)
    assert r.status_code == 204, r.text
    r = await idp.client.post(f"{SSO}/yetkim/unlink", json={"password": "admin1234"}, headers=idp.admin)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_linked"
    assert _by_slug(await _identities(idp))["yetkim"]["linked"] is False
    async with dbmod.get_session_factory()() as s:
        assert not list((await s.execute(select(UserIdentity))).scalars())
        (ev,) = (await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.identity_unbound"))).scalars()
    assert ev.before["provider"] == "yetkim" and ev.before["kind"] == "saml" and ev.actor_id is not None


async def test_idp_only_accounts_cannot_link_and_admins_cannot_reset_them(idp, monkeypatch) -> None:  # noqa: F811
    sp = await _saml_provider(idp, monkeypatch)
    rid, relay = await sp.start()
    loc = await sp.post(relay, saml_response(rid, acs=sp.acs, audience=sp.entity))
    tok = (await idp.client.post(f"{SSO}/exchange", json={"ticket": query_of(loc)["ticket"]})).json()["access_token"]
    ayse = {"Authorization": f"Bearer {tok}"}
    await idp.keycloak()
    r = await idp.client.post(f"{SSO}/keycloak/link", json={"confirm": True}, headers=ayse)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_password"
    assert "parola" in r.json()["detail"]["tr"].lower()
    async with dbmod.get_session_factory()() as s:
        user = (await s.execute(select(User).where(User.email == "ayse.yilmaz@uni.edu.tr"))).scalar_one()
        assert await mfa.account_type(s, user) == "sso"
    # the administrator rules are unchanged: no reset link and no 2FA reset for an IdP-only account
    r = await idp.client.post(
        f"/api/v1/admin/users/{user.id}/password-reset-link",
        json={"reason": "Telefonunu kaybetti, kimliği yüz yüze doğrulandı"},
        headers=idp.admin,
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sso_account", r.text
    r = await idp.client.post(
        f"/api/v1/admin/users/{user.id}/mfa/reset",
        json={"reason": "Telefonunu kaybetti, kimliği yüz yüze doğrulandı", "identity_check": "in_person"},
        headers=idp.admin,
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sso_account", r.text


async def test_link_needs_an_enabled_provider_and_a_confirmation(idp) -> None:  # noqa: F811
    p = await idp.create("oidc", preset="keycloak")
    r = await _link(idp, p["name"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_configured"
    assert "etkin değil" in r.json()["detail"]["tr"]
    r = await _link(idp, "yok-boyle-bir-saglayici")
    assert r.status_code == 404
    await idp.keycloak()
    r = await idp.client.post(f"{SSO}/keycloak/link", json={"confirm": False}, headers=idp.admin)
    assert r.status_code == 422
