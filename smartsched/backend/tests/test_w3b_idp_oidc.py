"""Several identity providers (wave 3b W3-IDP): the administration API shared by every administrator, discovery
with validation, the guided-setup values, the code flow with PKCE / nonce / state against a generic issuer and
Google Workspace, allowed domains, invite-only, the group mapping with no escalation, the test login and the
ordered /login buttons."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.core import db as dbmod
from app.models import AuditEvent, Role, User
from app.models.sso import SsoAuthState, SsoProvider, UserIdentity
from sqlalchemy import select

from tests.api_fixtures import login
from tests.crbs_support import make_user
from tests.test_w3b_idp_fakes import (  # noqa: F401
    GOOGLE_CLIENT,
    KC_CLIENT,
    KC_ISSUER,
    KC_SECRET,
    PANEL,
    idp,
    query_of,
)

ADMIN = "/api/v1/auth/sso/admin/providers"


async def _all(model, *where):  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(model).where(*where))).scalars())


async def _role_id(code: str) -> int:
    async with dbmod.get_session_factory()() as s:
        return (await s.execute(select(Role.id).where(Role.code == code))).scalar_one()


async def _me(idp, h) -> dict[str, Any]:  # type: ignore[no-untyped-def]  # noqa: F811
    r = await idp.client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------------------------------
# administration: shared rows, write-only secret, audit, "Son değişiklik"
# --------------------------------------------------------------------------------------------------


async def test_gallery_lists_every_kind_and_the_entra_row_is_a_provider(idp) -> None:  # noqa: F811
    r = await idp.client.get("/api/v1/auth/sso/admin/kinds", headers=idp.admin)
    assert r.status_code == 200, r.text
    kinds = {k["kind"]: k for k in r.json()}
    assert list(kinds) == ["entra", "google_workspace", "oidc", "saml", "ldap"]
    assert {p["key"] for p in kinds["oidc"]["presets"]} >= {"okta", "keycloak", "auth0", "authentik", "adfs"}
    assert {p["key"] for p in kinds["saml"]["presets"]} >= {"shibboleth", "yetkim"}
    assert kinds["entra"]["badge"] == "MS" and kinds["google_workspace"]["badge"] == "G"
    listing = (await idp.client.get(ADMIN, headers=idp.admin)).json()
    assert listing["ldap"]["kind"] == "ldap" and listing["ldap"]["enabled"] is False
    # a viewer cannot read the providers
    _uid, teacher = await make_user(idp.client, idp.admin, "ogretmen@uni.edu.tr", role="TEACHER")
    assert (await idp.client.get(ADMIN, headers=teacher)).status_code == 403


async def test_create_keycloak_discovers_and_keeps_the_secret_write_only(idp) -> None:  # noqa: F811
    p = await idp.create("oidc", preset="keycloak")
    assert p["name"] == "keycloak" and p["kind"] == "oidc" and p["enabled"] is False
    assert p["status"] == "not_configured" and p["label"] == "Keycloak"
    setup = (await idp.client.get(f"{ADMIN}/{p['id']}/setup", headers=idp.admin)).json()
    values = {v["key"]: v["value"] for v in setup["console"]}
    assert values["redirect_uri"] == f"{PANEL}/api/v1/auth/sso/keycloak/callback"
    assert values["scopes"] == "openid profile email"
    assert values["post_logout_redirect_uri"] == f"{PANEL}/login?reason=signed_out"
    assert setup["steps"]["tr"] and setup["steps"]["en"] and setup["issuer_hint"].startswith("https://")
    # pasted with NBSP, a capital dotted İ in the host and the discovery suffix: normalised, then discovered
    r = await idp.put(
        p["id"],
        issuer="\xa0https://SSO.UNİ.EDU.TR/realms/uni/.well-known/openid-configuration ",
        client_id=KC_CLIENT,
        client_secret=KC_SECRET,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["issuer"] == KC_ISSUER
    assert out["client_secret_set"] is True and KC_SECRET not in r.text
    assert out["discovery"]["ok"] is True and out["status"] == "disabled"
    assert {c["key"] for c in out["discovery"]["checks"]} >= {"issuer", "pkce", "code_flow", "jwks_uri"}
    assert out["changed_by"] and out["changed_at"]  # "Son değişiklik: <ad>, <zaman>"
    # a second administrator sees the same configuration (organisation-wide rows)
    uid, _ = await make_user(idp.client, idp.admin, "ikinci.yonetici@uni.edu.tr", role="ADMIN")
    other = await login(idp.client, "ikinci.yonetici@uni.edu.tr", "parola-1234")
    seen = (await idp.client.get(f"{ADMIN}/{p['id']}", headers=other)).json()
    assert seen["issuer"] == KC_ISSUER and seen["client_secret_set"] is True and "client_secret" not in seen
    rows = await _all(AuditEvent, AuditEvent.action.like("sso.provider%"))
    assert [e.action for e in rows][:2] == ["sso.provider_create", "sso.provider_update"]
    assert KC_SECRET not in repr([e.after for e in rows])
    assert any((e.after or {}).get("client_secret_changed") for e in rows)


async def test_discovery_mismatch_or_missing_pkce_blocks_enabling(idp) -> None:  # noqa: F811
    p = await idp.create("oidc", preset="generic")
    idp.kc.discovery_over = {"issuer": "https://evil.example/realms/uni"}
    r = await idp.put(p["id"], issuer=KC_ISSUER, client_id=KC_CLIENT, client_secret=KC_SECRET)
    assert r.status_code == 200 and r.json()["discovery"]["ok"] is False
    assert r.json()["status"] == "error" and r.json()["last_check_ok"] is False
    r = await idp.put(p["id"], enabled=True)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "discovery_required"
    idp.kc.discovery_over = {"code_challenge_methods_supported": ["plain"]}
    r = await idp.client.post(f"{ADMIN}/{p['id']}/discover", headers=idp.admin)
    pkce = next(c for c in r.json()["checks"] if c["key"] == "pkce")
    assert r.json()["ok"] is False and pkce["ok"] is False and "PKCE" in pkce["tr"]
    idp.kc.discovery_over = {}
    assert (await idp.client.post(f"{ADMIN}/{p['id']}/discover", headers=idp.admin)).json()["ok"] is True
    assert (await idp.put(p["id"], enabled=True)).status_code == 200
    # http:// is refused for a real host
    r = await idp.put(p["id"], issuer="http://sso.uni.edu.tr/realms/uni")
    assert r.status_code == 422


# --------------------------------------------------------------------------------------------------
# the code flow against a generic issuer
# --------------------------------------------------------------------------------------------------


async def test_code_flow_uses_pkce_state_nonce_and_creates_the_lowest_role(idp) -> None:  # noqa: F811
    await idp.keycloak()
    q = await idp.start("keycloak", next="/bookings")
    assert q["_location"].startswith(f"{KC_ISSUER}/protocol/openid-connect/auth?")
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    assert q["state"] and q["nonce"] and q["client_id"] == KC_CLIENT and "prompt" not in q
    assert q["redirect_uri"] == f"{PANEL}/api/v1/auth/sso/keycloak/callback"
    loc = await idp.callback("keycloak", q, idp.kc)
    assert urlsplit(loc).path == "/login/sso" and query_of(loc)["welcome"] == "self"
    assert idp.kc.token_calls[-1]["auth"] == "basic"  # the discovery listed client_secret_basic only
    r = await idp.client.post("/api/v1/auth/sso/exchange", json={"ticket": query_of(loc)["ticket"]})
    me = await _me(idp, {"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me["email"] == "ayse.yilmaz@uni.edu.tr" and me["role"] == "TEACHER"
    (ident,) = await _all(UserIdentity, UserIdentity.provider == "keycloak")
    assert ident.subject == "f:3c5e:ayse.yilmaz" and len(ident.tenant_id) == 32 and ident.issuer == KC_ISSUER
    # the state is single use: the same callback again is refused
    again = await idp.client.get("/api/v1/auth/sso/keycloak/callback", params={"code": "x", "state": q["state"]})
    assert query_of(again.headers["location"])["error"] == "failed"
    # a second sign-in finds the same identity (no second account)
    await idp.headers("keycloak", idp.kc)
    assert len(await _all(User, User.email == "ayse.yilmaz@uni.edu.tr")) == 1
    # no IdP token is kept anywhere
    states = await _all(SsoAuthState)
    assert "fake-access" not in repr([(s.data, s.code_verifier_enc) for s in states])


async def test_wrong_nonce_wrong_issuer_and_unverified_email_are_refused(idp) -> None:  # noqa: F811
    await idp.keycloak()
    loc = await idp.callback("keycloak", await idp.start("keycloak"), idp.kc, nonce="not-the-nonce")
    assert query_of(loc)["error"] == "failed"
    loc = await idp.callback("keycloak", await idp.start("keycloak"), idp.kc, iss="https://sso.uni.edu.tr/realms/other")
    assert query_of(loc)["error"] == "tenant"
    reasons = [(e.after or {}).get("reason") for e in await _all(AuditEvent, AuditEvent.action == "auth.login_refused")]
    assert reasons[-2:] == ["invalid_token", "tenant"]
    # an unverified e-mail never becomes the account address
    h = await idp.headers("keycloak", idp.kc, sub="u-2", email="baskasi@uni.edu.tr", email_verified=False)
    assert (await _me(idp, h))["email"] is None


async def test_allowed_domains_and_invite_only(idp) -> None:  # noqa: F811
    p = await idp.keycloak(allowed_domains=["UNİ.EDU.TR", "@ogr.uni.edu.tr"])
    assert p["allowed_domains"] == ["uni.edu.tr", "ogr.uni.edu.tr"]
    loc = await idp.callback("keycloak", await idp.start("keycloak"), idp.kc, email="x@gmail.com", sub="g-1")
    assert query_of(loc)["error"] == "domain" and query_of(loc)["provider"] == "keycloak"
    await idp.headers("keycloak", idp.kc, email="ogrenci@ogr.uni.edu.tr", sub="o-1")
    assert (await idp.put(p["id"], invite_only=True)).json()["invite_only"] is True
    loc = await idp.callback("keycloak", await idp.start("keycloak"), idp.kc, email="yeni@uni.edu.tr", sub="n-1")
    assert query_of(loc)["error"] == "signup_closed"
    # an invite for this provider still opens the door
    r = await idp.client.post(
        "/api/v1/auth/sso/admin/invites",
        json={"email": "Yeni@UNİ.edu.tr", "provider": "keycloak", "role": "TEACHER"},
        headers=idp.admin,
    )
    assert r.status_code == 201, r.text
    assert r.json()["provider"] == "keycloak" and r.json()["email"] == "yeni@uni.edu.tr"
    h = await idp.headers("keycloak", idp.kc, email="yeni@uni.edu.tr", sub="n-1")
    assert (await _me(idp, h))["email"] == "yeni@uni.edu.tr"


async def test_invite_for_one_provider_is_refused_through_another(idp) -> None:  # noqa: F811
    await idp.keycloak()
    await idp.google_ws()
    r = await idp.client.post(
        "/api/v1/auth/sso/admin/invites",
        json={"email": "davetli@uni.edu.tr", "provider": "keycloak"},
        headers=idp.admin,
    )
    token = query_of(r.json()["link"])["invite"]
    banner = (await idp.client.get(f"/api/v1/auth/sso/invites/{token}")).json()
    assert banner["provider"] == "keycloak" and banner["start_url"] == "/api/v1/auth/sso/keycloak/start"
    r = await idp.client.get("/api/v1/auth/sso/google/start", params={"invite": token})
    assert query_of(r.headers["location"])["error"] == "invite_provider"
    loc = await idp.callback("google", await idp.start("google"), idp.google, email="davetli@uni.edu.tr")
    assert query_of(loc)["error"] == "invite_provider"


# --------------------------------------------------------------------------------------------------
# Google Workspace: the hosted domain is pinned
# --------------------------------------------------------------------------------------------------


async def test_google_pins_the_hosted_domain_and_needs_a_verified_email(idp) -> None:  # noqa: F811
    p = await idp.google_ws()
    assert p["name"] == "google" and p["hosted_domains"] == ["uni.edu.tr"]
    q = await idp.start("google")
    assert q["hd"] == "uni.edu.tr" and q["prompt"] == "select_account" and q["client_id"] == GOOGLE_CLIENT
    loc = await idp.callback("google", q, idp.google, hd=None, email="kisisel@gmail.com")
    assert query_of(loc)["error"] == "tenant"  # a personal account has no hd
    loc = await idp.callback("google", await idp.start("google"), idp.google, hd="baska.edu.tr")
    assert query_of(loc)["error"] == "tenant"
    h = await idp.headers("google", idp.google)
    assert (await _me(idp, h))["email"] == "ayse.yilmaz@uni.edu.tr"
    assert idp.google.token_calls[-1]["auth"] == "post"
    # the hosted domain is required before enabling
    r = await idp.put(p["id"], hosted_domains=[])
    assert r.status_code == 422


# --------------------------------------------------------------------------------------------------
# group mapping: never beyond what the administrator who set it holds
# --------------------------------------------------------------------------------------------------


async def test_group_mapping_applies_and_never_escalates_beyond_its_creator(idp) -> None:  # noqa: F811
    p = await idp.keycloak(role_mapping_enabled=True, groups_claim="groups")
    url = f"{ADMIN}/{p['id']}/mappings"
    planner = await _role_id("PLANNER")
    body = {"claim": "group", "value": "/personel/planlama\xa0", "role_id": planner}
    r = await idp.client.post(url, json=body, headers=idp.admin)
    assert r.status_code == 201, r.text and r.json()["value"] == "/personel/planlama"
    h = await idp.headers("keycloak", idp.kc, sub="p-1", email="planlamaci@uni.edu.tr", groups=["/personel/planlama"])
    assert (await _me(idp, h))["role"] == "PLANNER"
    # a second administrator adds a mapping, then loses the administrator role: their mapping stops applying
    uid, _ = await make_user(idp.client, idp.admin, "gecici.yonetici@uni.edu.tr", role="ADMIN")
    other = await login(idp.client, "gecici.yonetici@uni.edu.tr", "parola-1234")
    body = {"claim": "group", "value": "/personel/bolum", "role_id": planner}
    assert (await idp.client.post(url, json=body, headers=other)).status_code == 201
    r = await idp.client.put(f"/api/v1/users/{uid}", json={"role_id": await _role_id("TEACHER")}, headers=idp.admin)
    assert r.status_code == 200, r.text
    h = await idp.headers("keycloak", idp.kc, sub="p-2", email="bolum@uni.edu.tr", groups=["/personel/bolum"])
    assert (await _me(idp, h))["role"] == "TEACHER"
    # a planning admin without every permission of a role cannot map to it
    custom = await idp.client.post(
        "/api/v1/roles",
        json={"name": "Planlama Yöneticisi", "permissions": ["planning.view", "planning.edit", "planning.admin"]},
        headers=idp.admin,
    )
    uid2, _ = await make_user(idp.client, idp.admin, "planlama.yon@uni.edu.tr", role="TEACHER")
    await idp.client.put(f"/api/v1/users/{uid2}", json={"role_id": custom.json()["id"]}, headers=idp.admin)
    h2 = await login(idp.client, "planlama.yon@uni.edu.tr", "parola-1234")
    r = await idp.client.post(url, json={"claim": "group", "value": "/x", "role_id": planner}, headers=h2)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_escalation"
    # nor change the provider's default role to one they could not grant
    r = await idp.put(p["id"], headers=h2, default_role_id=await _role_id("ADMIN"))
    assert r.status_code in (403, 422)


async def test_default_role_must_be_eligible(idp) -> None:  # noqa: F811
    p = await idp.create("oidc", preset="okta")
    r = await idp.put(p["id"], default_role_id=await _role_id("PLANNER"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "default_role_privileged"
    viewer = (await _all(Role, Role.code == "VIEWER")) or (await _all(Role, Role.code == "TEACHER"))
    r = await idp.put(p["id"], default_role_id=viewer[0].id)
    assert r.status_code == 200 and r.json()["default_role"]["id"] == viewer[0].id


# --------------------------------------------------------------------------------------------------
# the test login (popup): claims reported, nothing stored, no account
# --------------------------------------------------------------------------------------------------


async def test_test_login_reports_claims_without_creating_anything(idp) -> None:  # noqa: F811
    p = await idp.create("oidc", preset="keycloak")
    await idp.put(p["id"], issuer=KC_ISSUER, client_id=KC_CLIENT, client_secret=KC_SECRET, role_mapping_enabled=True)
    idp.kc.redirect = f"{PANEL}/api/v1/auth/sso/keycloak/callback"
    users_before = len(await _all(User))
    r = await idp.client.post(f"{ADMIN}/{p['id']}/test", headers=idp.admin)
    assert r.status_code == 200, r.text  # works while the provider is still off
    test_id, q = r.json()["test_id"], query_of(r.json()["authorize_url"])
    pending = (await idp.client.get(f"{ADMIN}/{p['id']}/test/{test_id}", headers=idp.admin)).json()
    assert pending["status"] == "pending"
    loc = await idp.callback("keycloak", q, idp.kc, groups=["/personel/planlama"])
    assert loc == f"{PANEL}/api/v1/auth/sso/test-done?ok=1"
    page = await idp.client.get("/api/v1/auth/sso/test-done", params={"ok": "1"})
    assert page.status_code == 200 and "Test" in page.text and "<script" not in page.text
    res = (await idp.client.get(f"{ADMIN}/{p['id']}/test/{test_id}", headers=idp.admin)).json()
    assert res["status"] == "done" and res["ok"] is True
    assert res["claims"]["email"] == "ayse.yilmaz@uni.edu.tr" and res["groups"] == ["/personel/planlama"]
    assert res["verified_email"] == "ayse.yilmaz@uni.edu.tr" and res["domain_ok"] is True
    assert "nonce" not in res["claims"] and "fake-access" not in repr(res) and "id_token" not in repr(res)
    assert len(await _all(User)) == users_before and not await _all(UserIdentity)
    detail = (await idp.client.get(f"{ADMIN}/{p['id']}", headers=idp.admin)).json()
    assert detail["last_check_ok"] is True and detail["last_check_at"]
    # another administrator cannot read this administrator's test
    # (the result belongs to the provider; any planning admin may read it -- shared setup)
    assert [e.action for e in await _all(AuditEvent, AuditEvent.action == "sso.test_login")] == ["sso.test_login"]


async def test_failed_test_login_reports_the_reason(idp) -> None:  # noqa: F811
    p = await idp.create("oidc", preset="keycloak")
    await idp.put(p["id"], issuer=KC_ISSUER, client_id=KC_CLIENT, client_secret=KC_SECRET)
    idp.kc.redirect = f"{PANEL}/api/v1/auth/sso/keycloak/callback"
    r = (await idp.client.post(f"{ADMIN}/{p['id']}/test", headers=idp.admin)).json()
    loc = await idp.callback("keycloak", query_of(r["authorize_url"]), idp.kc, aud="another-client")
    assert loc.endswith("ok=0")
    res = (await idp.client.get(f"{ADMIN}/{p['id']}/test/{r['test_id']}", headers=idp.admin)).json()
    assert res["ok"] is False and res["reason"] == "invalid_token" and res["code"] == "failed"
    assert (await idp.client.get(f"{ADMIN}/{p['id']}", headers=idp.admin)).json()["status"] == "error"


# --------------------------------------------------------------------------------------------------
# /login: one button per enabled provider in the administrators' order
# --------------------------------------------------------------------------------------------------


async def test_login_buttons_follow_the_admin_order(idp) -> None:  # noqa: F811
    kc = await idp.keycloak(display_name="Kurum girişi")
    g = await idp.google_ws()
    r = await idp.client.put(f"{ADMIN}/order", json={"ids": [g["id"], kc["id"]]}, headers=idp.admin)
    assert r.status_code == 200, r.text
    auth = (await idp.client.get("/api/v1/org/public")).json()["auth"]
    assert [(p["name"], p["label"]) for p in auth["providers"]] == [
        ("google", "Google Workspace"),
        ("keycloak", "Kurum girişi"),
    ]
    assert auth["microsoft"]["enabled"] is False and auth["local_enabled"] is True
    out = (await idp.client.get("/api/v1/auth/sso/providers")).json()
    assert [p["name"] for p in out["providers"]][1:] == ["google", "keycloak"]
    assert out["messages"]["domain"]["tr"] and out["messages"]["invite_provider"]["en"]
    # disabling hides the button
    await idp.put(g["id"], enabled=False)
    auth = (await idp.client.get("/api/v1/org/public")).json()["auth"]
    assert [p["name"] for p in auth["providers"]] == ["keycloak"]


async def test_delete_needs_the_provider_off_and_keeps_the_accounts(idp) -> None:  # noqa: F811
    kc = await idp.keycloak()
    await idp.headers("keycloak", idp.kc)
    r = await idp.client.delete(f"{ADMIN}/{kc['id']}", headers=idp.admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "enabled"
    assert (await idp.put(kc["id"], enabled=False)).status_code == 200
    assert (await idp.client.delete(f"{ADMIN}/{kc['id']}", headers=idp.admin)).status_code == 204
    assert not await _all(SsoProvider) and not await _all(UserIdentity)
    assert len(await _all(User, User.email == "ayse.yilmaz@uni.edu.tr")) == 1  # the account stays


async def test_one_microsoft_and_one_google_new_oidc_starts_invite_only(idp) -> None:  # noqa: F811
    await idp.create("google_workspace")
    r = await idp.client.post(ADMIN, json={"kind": "google_workspace"}, headers=idp.admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "exists"
    okta = await idp.create("oidc", preset="okta")
    okta2 = await idp.create("oidc", preset="okta")
    assert (okta["name"], okta2["name"]) == ("okta", "okta-2")
    assert okta["invite_only"] is True and okta["groups_claim"] == "groups" and okta["scopes"] == ["groups"]
    r = await idp.client.post(ADMIN, json={"kind": "oidc", "name": "admin"}, headers=idp.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_slug"


async def test_stale_version_conflicts_and_disabling_the_last_admin_path_is_refused(idp) -> None:  # noqa: F811
    kc = await idp.keycloak()
    r = await idp.put(kc["id"], version="2020-01-01T00:00:00.000000", display_name="Eski")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "conflict" and "Yenileyin" in r.json()["detail"]["tr"]
    assert (await idp.put(kc["id"], version=kc["version"], display_name="Kampüs girişi")).status_code == 200
    # an administrator who signs in only through Keycloak, and no local administrator left
    h = await idp.headers("keycloak", idp.kc, sub="adm-1", email="tek.yonetici@uni.edu.tr")
    me = await _me(idp, h)
    r = await idp.client.put(f"/api/v1/users/{me['id']}", json={"role_id": await _role_id("ADMIN")}, headers=idp.admin)
    assert r.status_code == 200, r.text
    async with dbmod.get_session_factory()() as s:
        seeded = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        seeded.password_hash = None
        await s.commit()
    r = await idp.put(kc["id"], headers=await idp.headers("keycloak", idp.kc, sub="adm-1"), enabled=False)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "last_admin_path"
