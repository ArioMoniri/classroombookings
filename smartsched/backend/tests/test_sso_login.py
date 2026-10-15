"""Microsoft Entra ID sign-in (owner decision 2026-10-15): authorization code + PKCE + state + nonce against the
local fake Entra (``tests/test_sso_fake_idp``), ID token checks (signature via cached JWKS, pinned issuer, aud, exp,
nonce), identity by ``oid`` + ``tid`` (never the e-mail), auto-provisioning as the lowest role, no automatic linking
to existing accounts, IdP tokens dropped, SmartSched's normal JWT with token-version revocation."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit

from app.core import db as dbmod
from app.models import AuditEvent, User
from app.models.sso import SsoAuthState, UserIdentity
from sqlalchemy import select

from tests.test_sso_fake_idp import (  # noqa: F401
    CLIENT_ID,
    ISSUER,
    LOGIN,
    OTHER_TENANT,
    PANEL,
    REDIRECT,
    TENANT,
    FakeEntra,
    error_of,
    new_key,
    s256,
    sso,
)


async def _rows(model):  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(model))).scalars())


async def _actions(prefix: str = "") -> list[str]:
    return [e.action for e in await _rows(AuditEvent) if e.action.startswith(prefix)]


def _instructor_with_dotted_capital_i(parsed) -> str:  # type: ignore[no-untyped-def]
    """The first instructor of the real Bahar list whose name carries a Turkish dotted capital İ."""
    for row in parsed.rows:
        for name in row.instructors or []:
            if "İ" in name:
                return name
    raise AssertionError("fixture changed: no instructor with İ")


async def test_happy_path_provisions_teacher_with_turkish_name_and_drops_idp_tokens(sso, parsed_bahar_list):  # noqa: F811
    real_name = _instructor_with_dotted_capital_i(parsed_bahar_list)  # e.g. "DR. ÖĞR. ÜYESİ ŞEHRİBAN SERBEST"
    q = await sso.start()
    assert q["response_type"] == "code" and q["client_id"] == CLIENT_ID and q["redirect_uri"] == REDIRECT
    assert set(q["scope"].split()) == {"openid", "profile", "email"}
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    assert len(q["state"]) >= 32 and len(q["nonce"]) >= 32 and q["state"] != q["nonce"]
    loc = await sso.callback(
        q,
        name=f"  {real_name.replace(' ', '\u00a0', 1)}\u200b ",  # NBSP + zero-width as Entra may pass them on
        preferred_username="SEHRIBAN.SERBEST@UNI.EDU.TR",
        email=None,
        oid="11111111-2222-4333-8444-555555555555",
    )
    assert loc.startswith(f"{PANEL}/login/sso?"), loc
    query = {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}
    assert query["next"] == "/bookings" and len(query["ticket"]) >= 32
    r = await sso.client.post("/api/v1/auth/sso/exchange", json={"ticket": query["ticket"]})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = await sso.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["role"] == "TEACHER"  # the lowest role, never more
    assert body["email"] == "sehriban.serbest@uni.edu.tr"  # Turkish-aware folding of the UPN
    assert body["full_name"] == " ".join(real_name.split())  # NBSP / zero-width removed, letters kept as written
    users = [u for u in await _rows(User) if u.email == "sehriban.serbest@uni.edu.tr"]
    assert len(users) == 1 and users[0].auth_source == "oidc" and users[0].password_hash is None
    (ident,) = await _rows(UserIdentity)
    assert (ident.tenant_id, ident.subject, ident.issuer) == (TENANT, "11111111-2222-4333-8444-555555555555", ISSUER)
    assert ident.user_id == users[0].id
    # nothing but oid/tid/e-mail/display name is kept: no IdP token, code or id_token anywhere in the database
    async with dbmod.get_session_factory()() as s:
        dump = repr([(c.name, getattr(ident, c.name)) for c in UserIdentity.__table__.columns])
        audit = repr([(e.action, e.after, e.before) for e in (await s.execute(select(AuditEvent))).scalars()])
    for secret in ("fake.access", "fake-refresh-token", "eyJ", "fake-client-secret"):
        assert secret not in dump and secret not in audit
    assert await _rows(SsoAuthState) == []  # state and ticket were single use
    assert {"auth.sso_provision", "auth.sso_login"} <= set(await _actions("auth.sso"))
    # the ticket cannot be replayed
    again = await sso.client.post("/api/v1/auth/sso/exchange", json={"ticket": query["ticket"]})
    assert again.status_code == 401


async def test_logout_revokes_the_sso_session(sso):  # noqa: F811
    h = await sso.headers()
    assert (await sso.client.get("/api/v1/auth/me", headers=h)).status_code == 200
    assert (await sso.client.post("/api/v1/auth/logout", headers=h)).status_code == 204
    r = await sso.client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401 and r.json()["detail"] == "token revoked"


async def test_wrong_tenant_issuer_is_refused(sso):  # noqa: F811
    for claims in (
        {"iss": f"{LOGIN}/{OTHER_TENANT}/v2.0", "tid": OTHER_TENANT},
        {"iss": f"{LOGIN}/common/v2.0"},
        {"tid": OTHER_TENANT},  # iss right, tid of another tenant
        {"iss": f"{LOGIN}/9188040d-6c67-4c5b-b112-36a304b66dad/v2.0", "tid": "9188040d-6c67-4c5b-b112-36a304b66dad"},
    ):
        loc = await sso.callback(await sso.start(), **claims)
        assert error_of(loc) == "invalid_token", (claims, loc)
    assert [u.email for u in await _rows(User) if u.auth_source == "oidc"] == []
    assert (await _actions("auth.sso_failed")).count("auth.sso_failed") == 4


async def test_wrong_audience_expired_and_bad_nonce_are_refused(sso):  # noqa: F811
    now = int(time.time())
    for claims in (
        {"aud": "00000003-0000-0000-c000-000000000000"},  # a token for Graph, not for SmartSched
        {"exp": now - 3600, "iat": now - 7200, "nbf": now - 7200},
        {"nonce": "not-the-nonce-we-sent"},
        {"nonce": None},
        {"oid": None},
    ):
        loc = await sso.callback(await sso.start(), **claims)
        assert error_of(loc) == "invalid_token", (claims, loc)
    assert await _rows(UserIdentity) == []


async def test_bad_signature_and_unknown_key_are_refused(sso):  # noqa: F811
    loc = await sso.callback(await sso.start(), key=new_key("entra-test-key-1"))  # same kid, other key
    assert error_of(loc) == "invalid_token"
    loc = await sso.callback(await sso.start(), key=new_key("not-published"))
    assert error_of(loc) == "invalid_token"
    assert await _rows(UserIdentity) == []


async def test_replayed_or_unknown_state_is_refused(sso):  # noqa: F811
    q = await sso.start()
    first = await sso.callback(q)
    assert "ticket=" in first
    replay = await sso.callback(q)  # the same state a second time
    assert error_of(replay) == "state"
    forged = await sso.callback({**q, "state": "forged-state-value-forged-state-value"})
    assert error_of(forged) == "state"
    assert (await _actions("auth.sso_failed")).count("auth.sso_failed") == 2


async def test_guest_accounts_of_the_tenant_are_refused(sso):  # noqa: F811
    loc = await sso.callback(await sso.start(), idp=f"{LOGIN}/{OTHER_TENANT}/v2.0")
    assert error_of(loc) == "guest"
    loc = await sso.callback(await sso.start(), idp="live.com")
    assert error_of(loc) == "guest"


async def test_identity_is_oid_not_email(sso):  # noqa: F811
    oid = "22222222-3333-4444-8555-666666666666"
    h1 = await sso.headers(oid=oid, preferred_username="m.ozturk@uni.edu.tr", email="m.ozturk@uni.edu.tr")
    me1 = (await sso.client.get("/api/v1/auth/me", headers=h1)).json()
    # the university renames the account: new UPN and e-mail, same oid -> the same SmartSched user
    h2 = await sso.headers(
        oid=oid, preferred_username="mehmet.ozturk@uni.edu.tr", email="mehmet.ozturk@uni.edu.tr", name="Mehmet Öztürk"
    )
    me2 = (await sso.client.get("/api/v1/auth/me", headers=h2)).json()
    assert me1["id"] == me2["id"]
    (ident,) = await _rows(UserIdentity)
    assert ident.email_at_login == "mehmet.ozturk@uni.edu.tr" and ident.display_name == "Mehmet Öztürk"
    # someone else (another oid) presenting the first user's old e-mail is a different person
    h3 = await sso.headers(oid="33333333-4444-4555-8666-777777777777", preferred_username="x.y@uni.edu.tr",
                           email="m.ozturk@uni.edu.tr")
    me3 = (await sso.client.get("/api/v1/auth/me", headers=h3)).json()
    assert me3["id"] != me1["id"]


async def test_provisioning_off_is_refused_with_tr_en_message_and_audit(sso):  # noqa: F811
    r = await sso.configure(auto_provision=False)
    assert r.status_code == 200, r.text
    loc = await sso.callback(await sso.start(), oid="44444444-5555-4666-8777-888888888888")
    assert error_of(loc) == "provisioning_off"
    assert await _rows(UserIdentity) == []
    msgs = (await sso.client.get("/api/v1/auth/sso/providers")).json()["messages"]
    assert "yönetici" in msgs["provisioning_off"]["tr"] and "administrator" in msgs["provisioning_off"]["en"]
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.sso_failed"))).scalars().one()
    assert ev.after["reason"] == "provisioning_off"


async def test_no_automatic_link_to_an_admin_by_email(sso):  # noqa: F811
    # an attacker controls an account of the tenant whose e-mail claim equals the administrator's address
    loc = await sso.callback(
        await sso.start(),
        oid="55555555-6666-4777-8888-999999999999",
        email="admin@example.com",
        preferred_username="ADMIN@example.com",
    )
    assert error_of(loc) == "account_exists"
    assert await _rows(UserIdentity) == []
    admin = next(u for u in await _rows(User) if u.email == "admin@example.com")
    assert admin.role == "ADMIN"
    assert "auth.sso_failed" in await _actions("auth.sso")


async def test_disabled_account_is_refused(sso):  # noqa: F811
    h = await sso.headers(oid="66666666-7777-4888-8999-000000000000")
    me = (await sso.client.get("/api/v1/auth/me", headers=h)).json()
    r = await sso.client.put(f"/api/v1/users/{me['id']}", json={"is_active": False}, headers=sso.admin)
    assert r.status_code == 200, r.text
    loc = await sso.callback(await sso.start(), oid="66666666-7777-4888-8999-000000000000")
    assert error_of(loc) == "disabled"


async def test_jwks_is_cached_and_refreshed_on_key_rotation(sso):  # noqa: F811
    await sso.headers(oid="77777777-8888-4999-8000-111111111111")
    await sso.headers(oid="77777777-8888-4999-8000-111111111111")
    assert sso.fake.jwks_calls == 1  # second login used the cache
    rotated = new_key("entra-test-key-2")
    sso.fake.published = [sso.fake.key, rotated]
    await sso.headers(oid="77777777-8888-4999-8000-111111111111", key=None)
    assert sso.fake.jwks_calls == 1
    loc = await sso.callback(await sso.start(), key=rotated, oid="77777777-8888-4999-8000-111111111111")
    assert "ticket=" in loc  # unknown kid -> one refetch picks the new key up
    assert sso.fake.jwks_calls == 2


async def test_denied_consent_and_bad_code_answer_panel_errors(sso):  # noqa: F811
    q = await sso.start()
    r = await sso.client.get(
        "/api/v1/auth/sso/entra/callback",
        params={"error": "access_denied", "error_description": "AADSTS65004: User declined", "state": q["state"]},
    )
    assert r.status_code == 302 and error_of(r.headers["location"]) == "denied"
    q = await sso.start()
    r = await sso.client.get("/api/v1/auth/sso/entra/callback", params={"code": "never-issued", "state": q["state"]})
    assert r.status_code == 302 and error_of(r.headers["location"]) == "exchange"


async def test_start_refuses_open_redirects_and_unconfigured_provider(sso):  # noqa: F811
    for bad in ("//evil.example/x", "https://evil.example/", "/\\evil.example"):
        q = await sso.start(return_path=bad)
        loc = await sso.callback(q)
        assert "next=%2F" not in loc or "evil" not in loc
        assert "evil" not in loc
    assert (await sso.configure(enabled=False)).status_code == 200
    r = await sso.client.get("/api/v1/auth/sso/entra/start")
    assert r.status_code == 302 and error_of(r.headers["location"]) == "not_configured"
    providers = (await sso.client.get("/api/v1/auth/sso/providers")).json()["providers"]
    assert providers == [
        {"name": "entra", "label": "Microsoft 365", "enabled": False, "start_url": "/api/v1/auth/sso/entra/start"}
    ]


async def test_existing_identity_whose_user_was_deleted_is_provisioned_again(sso):  # noqa: F811
    h = await sso.headers(oid="88888888-9999-4000-8111-222222222222")
    me = (await sso.client.get("/api/v1/auth/me", headers=h)).json()
    assert (await sso.client.delete(f"/api/v1/users/{me['id']}", headers=sso.admin)).status_code == 204
    assert await _rows(UserIdentity) == []  # the identity went with the user (cascade)
    h2 = await sso.headers(oid="88888888-9999-4000-8111-222222222222")
    me2 = (await sso.client.get("/api/v1/auth/me", headers=h2)).json()
    assert me2["id"] != me["id"] and me2["role"] == "TEACHER"


def test_issuer_constant_matches_the_pinned_tenant() -> None:
    assert ISSUER == f"https://login.microsoftonline.com/{TENANT}/v2.0"
    assert s256("a" * 43) != s256("b" * 43)
    assert isinstance(FakeEntra().key.kid, str)
