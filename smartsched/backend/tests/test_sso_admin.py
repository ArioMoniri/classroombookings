"""Entra ID administration (owner decisions 2026-10-15): the provider configuration (pinned tenant, encrypted secret
never returned, redirect URI from PUBLIC_URL), the break-glass rule, "OIDC only for non-admins", the optional
app-role / group mapping (off by default; no escalation for whoever edits it; never ADMIN unless explicitly
allowed; a demotion revokes sessions), invites and "bind on next SSO login" by the verified UPN (one time, audited,
expiring), linking an existing local account with a password confirmation, and the audit trail."""

from __future__ import annotations

from datetime import timedelta

from app.core import db as dbmod
from app.core.security import decrypt_secret
from app.models import AuditEvent, Role, Setting, User
from app.models.base import utcnow
from app.models.sso import SsoInvite, SsoProvider, UserIdentity
from app.services import sso as sso_service
from sqlalchemy import select, update

from tests.crbs_support import make_user
from tests.test_sso_fake_idp import (  # noqa: F401
    CLIENT_ID,
    FAKE_SECRET,
    PANEL,
    TENANT,
    error_of,
    sso,
)

ADMIN_URL = "/api/v1/auth/sso/admin/entra"


async def _one(model, *where):  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return (await s.execute(select(model).where(*where))).scalars().one()


async def _all(model, *where):  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(model).where(*where))).scalars())


async def _role_id(code: str) -> int:
    return (await _one(Role, Role.code == code)).id


async def _me(sso, h):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await sso.client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------------------


async def test_config_pins_tenant_and_never_returns_the_secret(sso):  # noqa: F811
    r = await sso.client.get(ADMIN_URL, headers=sso.admin)
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["tenant_id"] == TENANT and cfg["client_id"] == CLIENT_ID and cfg["enabled"] is True
    assert cfg["client_secret_set"] is True and FAKE_SECRET not in r.text and "client_secret" not in cfg
    assert cfg["redirect_uri"] == f"{PANEL}/api/v1/auth/sso/entra/callback"
    assert cfg["authority"] == f"https://login.microsoftonline.com/{TENANT}/v2.0"
    assert cfg["configured"] is True and cfg["auto_provision"] is True and cfg["oidc_only_non_admins"] is False
    assert cfg["role_mapping_enabled"] is False and cfg["allow_admin_mapping"] is False
    assert cfg["invite_days"] == 30 and cfg["default_role"]["code"] == "TEACHER"
    assert cfg["break_glass_admins"] == 1
    row = await _one(SsoProvider, SsoProvider.name == "entra")
    assert row.client_secret_enc and FAKE_SECRET not in row.client_secret_enc
    assert decrypt_secret(row.client_secret_enc) == FAKE_SECRET
    for bad in ("common", "organizations", "consumers", "9188040d-6c67-4c5b-b112-36a304b66dad", "uni.edu.tr", ""):
        r = await sso.configure(tenant_id=bad)
        assert r.status_code == 422, (bad, r.text)
    r = await sso.configure(tenant_id=f" {TENANT.upper()}\u00a0")  # pasted with NBSP and in capitals
    assert r.status_code == 200 and r.json()["tenant_id"] == TENANT
    # an empty secret in a PUT keeps the stored one; the audit log never sees it
    assert (await sso.configure(client_secret="")).json()["client_secret_set"] is True
    events = await _all(AuditEvent, AuditEvent.action == "sso.config_update")
    assert events and all(FAKE_SECRET not in repr((e.before, e.after)) for e in events)
    assert all(FAKE_SECRET not in repr((s.key, s.value)) for s in await _all(Setting))


async def test_config_needs_planning_admin(sso):  # noqa: F811
    _, teacher = await make_user(sso.client, sso.admin, "ogretmen@uni.edu.tr")
    assert (await sso.client.get(ADMIN_URL, headers=teacher)).status_code == 403
    assert (await sso.client.put(ADMIN_URL, json={"enabled": False}, headers=teacher)).status_code == 403


async def test_enabling_needs_tenant_client_secret_and_public_url(client, monkeypatch):
    from app.core.config import get_settings

    from tests.api_fixtures import login

    monkeypatch.setattr(get_settings(), "public_url", None)
    admin = await login(client)
    r = await client.put(ADMIN_URL, json={"enabled": True}, headers=admin)
    assert r.status_code == 422 and "tenant" in r.text
    r = await client.put(
        ADMIN_URL, json={"enabled": True, "tenant_id": TENANT, "client_id": CLIENT_ID, "client_secret": FAKE_SECRET},
        headers=admin,
    )
    assert r.status_code == 422 and "public" in r.text.lower()


async def test_default_role_must_be_unprivileged(sso):  # noqa: F811
    r = await sso.configure(default_role_id=await _role_id("ADMIN"))
    assert r.status_code == 422
    r = await sso.configure(default_role_id=await _role_id("VIEWER"))
    assert r.status_code == 200 and r.json()["default_role"]["code"] == "VIEWER"
    me = await _me(sso, await sso.headers(oid="10000000-0000-4000-8000-000000000001"))
    assert me["role"] == "VIEWER"


# --------------------------------------------------------------------------------------------------
# break-glass and "OIDC only for non-admins"
# --------------------------------------------------------------------------------------------------


async def test_break_glass_refuses_oidc_only_without_a_local_admin(sso):  # noqa: F811
    # the only administrator loses the local password (e.g. it became an SSO-only account)
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(User).where(User.email == "admin@example.com").values(password_hash=None))
        await s.commit()
    r = await sso.configure(oidc_only_non_admins=True)
    assert r.status_code == 409, r.text
    assert "break-glass" in r.json()["detail"]["en"] and r.json()["detail"]["tr"]
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(User).where(User.email == "admin@example.com").values(password_hash="argon2-x"))
        await s.commit()
    r = await sso.configure(oidc_only_non_admins=True)
    assert r.status_code == 200 and r.json()["oidc_only_non_admins"] is True


async def test_oidc_only_keeps_password_login_for_admins_only(sso):  # noqa: F811
    tid, _ = await make_user(sso.client, sso.admin, "hoca@uni.edu.tr")
    assert (await sso.configure(oidc_only_non_admins=True)).status_code == 200
    async with dbmod.get_session_factory()() as s:
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        teacher = await s.get(User, tid)
        assert await sso_service.password_login_allowed(s, admin) is True
        assert await sso_service.password_login_allowed(s, teacher) is False
    assert (await sso.configure(oidc_only_non_admins=False)).status_code == 200
    async with dbmod.get_session_factory()() as s:
        assert await sso_service.password_login_allowed(s, await s.get(User, tid)) is True


async def test_mapping_never_demotes_the_last_break_glass_admin(sso):  # noqa: F811
    # the administrator binds the seeded admin account to their Entra account, then mapping is switched on
    admin_id = (await _one(User, User.email == "admin@example.com")).id
    r = await sso.client.post(f"/api/v1/auth/sso/admin/users/{admin_id}/bind", json={}, headers=sso.admin)
    assert r.status_code == 201, r.text
    assert (await sso.configure(role_mapping_enabled=True)).status_code == 200
    r = await sso.client.post(
        f"{ADMIN_URL}/mappings",
        json={"claim": "role", "value": "SmartSched.Teacher", "role_id": await _role_id("TEACHER")},
        headers=sso.admin,
    )
    assert r.status_code == 201, r.text
    h = await sso.headers(oid="20000000-0000-4000-8000-000000000002", preferred_username="admin@example.com",
                          roles=["SmartSched.Teacher"])
    assert (await _me(sso, h))["role"] == "ADMIN"  # kept: the last local admin
    assert await _all(AuditEvent, AuditEvent.action == "sso.demotion_blocked")


# --------------------------------------------------------------------------------------------------
# role mapping
# --------------------------------------------------------------------------------------------------


async def test_role_mapping_promotes_and_demotion_revokes_sessions(sso):  # noqa: F811
    planner_id = await _role_id("PLANNER")
    group = "8f3c2a1b-4d5e-4f60-9a7b-1c2d3e4f5a6b"
    assert (await sso.configure(role_mapping_enabled=True)).status_code == 200
    r = await sso.client.post(
        f"{ADMIN_URL}/mappings", json={"claim": "group", "value": group.upper(), "role_id": planner_id},
        headers=sso.admin,
    )
    assert r.status_code == 201, r.text
    assert r.json()["value"] == group  # group object ids are compared lower-case
    oid = "30000000-0000-4000-8000-000000000003"
    h_old = await sso.headers(oid=oid, groups=[group])
    assert (await _me(sso, h_old))["role"] == "PLANNER"
    h_same = await sso.headers(oid=oid, groups=[group])
    assert (await sso.client.get("/api/v1/auth/me", headers=h_old)).status_code == 200  # no change, no revocation
    # removed from the group at the IdP: the next login demotes and every older session dies
    h_new = await sso.headers(oid=oid, groups=[])
    assert (await _me(sso, h_new))["role"] == "TEACHER"
    for h in (h_old, h_same):
        r = await sso.client.get("/api/v1/auth/me", headers=h)
        assert r.status_code == 401 and r.json()["detail"] == "token revoked"
    assert [e.after["to"] for e in await _all(AuditEvent, AuditEvent.action == "sso.role_change")] == [
        "PLANNER",
        "TEACHER",
    ]


async def test_mapping_off_keeps_roles_managed_in_smartsched(sso):  # noqa: F811
    group = "8f3c2a1b-4d5e-4f60-9a7b-1c2d3e4f5a6b"
    r = await sso.client.post(
        f"{ADMIN_URL}/mappings", json={"claim": "group", "value": group, "role_id": await _role_id("PLANNER")},
        headers=sso.admin,
    )
    assert r.status_code == 201
    oid = "40000000-0000-4000-8000-000000000004"
    me = await _me(sso, await sso.headers(oid=oid, groups=[group]))
    assert me["role"] == "TEACHER"  # mapping is off by default: the IdP's groups do not matter
    # an admin promotes the user in SmartSched; later SSO logins keep it
    r = await sso.client.put(f"/api/v1/users/{me['id']}", json={"role": "PLANNER"}, headers=sso.admin)
    assert r.status_code == 200, r.text
    assert (await _me(sso, await sso.headers(oid=oid, groups=[])))["role"] == "PLANNER"


async def test_mapping_to_admin_needs_explicit_allow_and_editor_needs_the_permissions(sso):  # noqa: F811
    admin_role = await _role_id("ADMIN")
    body = {"claim": "role", "value": "SmartSched.Admin", "role_id": admin_role}
    r = await sso.client.post(f"{ADMIN_URL}/mappings", json=body, headers=sso.admin)
    assert r.status_code == 422 and "allow_admin_mapping" in r.text
    assert (await sso.configure(allow_admin_mapping=True, role_mapping_enabled=True)).status_code == 200
    assert (await sso.client.post(f"{ADMIN_URL}/mappings", json=body, headers=sso.admin)).status_code == 201
    me = await _me(sso, await sso.headers(oid="50000000-0000-4000-8000-000000000005", roles=["SmartSched.Admin"]))
    assert me["role"] == "ADMIN"
    # the switch goes off again: an existing ADMIN mapping no longer grants anything at login
    assert (await sso.configure(allow_admin_mapping=False)).status_code == 200
    me = await _me(sso, await sso.headers(oid="50000000-0000-4000-8000-000000000006", roles=["SmartSched.Admin"],
                                          preferred_username="ikinci@uni.edu.tr"))
    assert me["role"] == "TEACHER"
    # a planning admin without setup.roles cannot map to roles they could not grant (no escalation)
    custom = await sso.client.post(
        "/api/v1/roles",
        json={"name": "Planlama Yöneticisi", "permissions": ["planning.view", "planning.edit", "planning.admin"]},
        headers=sso.admin,
    )
    assert custom.status_code == 201, custom.text
    uid, h = await make_user(sso.client, sso.admin, "planlama@uni.edu.tr", role="TEACHER")
    r = await sso.client.put(f"/api/v1/users/{uid}", json={"role_id": custom.json()["id"]}, headers=sso.admin)
    assert r.status_code == 200, r.text
    from tests.api_fixtures import login

    h = await login(sso.client, "planlama@uni.edu.tr", "parola-1234")
    r = await sso.client.post(
        f"{ADMIN_URL}/mappings", json={"claim": "role", "value": "Planner", "role_id": await _role_id("PLANNER")},
        headers=h,
    )
    assert r.status_code == 403, r.text
    mappings = (await sso.client.get(f"{ADMIN_URL}/mappings", headers=sso.admin)).json()
    r = await sso.client.delete(f"{ADMIN_URL}/mappings/{mappings[0]['id']}", headers=h)
    assert r.status_code == 403  # nor remove a mapping to the Administrator role
    assert (await sso.client.delete(f"{ADMIN_URL}/mappings/{mappings[0]['id']}", headers=sso.admin)).status_code == 204
    actions = [e.action for e in await _all(AuditEvent, AuditEvent.action.like("sso.mapping%"))]
    assert actions == ["sso.mapping_create", "sso.mapping_delete"]


# --------------------------------------------------------------------------------------------------
# invites and binding
# --------------------------------------------------------------------------------------------------


async def test_invite_binds_on_first_login_by_verified_upn_with_turkish_folding(sso):  # noqa: F811
    r = await sso.client.post(
        "/api/v1/auth/sso/admin/invites",
        json={"email": "SEHRİBAN.SERBEST@UNİ.EDU.TR\u00a0", "full_name": "Şehriban Serbest", "role": "PLANNER"},
        headers=sso.admin,
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["email"] == "sehriban.serbest@uni.edu.tr" and inv["status"] == "invited" and inv["kind"] == "invite"
    status = (await sso.client.get("/api/v1/auth/sso/admin/user-status", headers=sso.admin)).json()
    assert status[str(inv["user_id"])] == "invited"
    oid = "60000000-0000-4000-8000-000000000006"
    me = await _me(sso, await sso.headers(oid=oid, preferred_username="Sehriban.Serbest@uni.edu.tr", email=None))
    assert me["id"] == inv["user_id"] and me["role"] == "PLANNER"  # the admin's role, not the default
    assert await _all(SsoInvite) == []  # one time
    status = (await sso.client.get("/api/v1/auth/sso/admin/user-status", headers=sso.admin)).json()
    assert status[str(inv["user_id"])] == "linked"
    # after binding, identity is by oid only: a new UPN still finds the user, the old UPN on another oid does not
    me2 = await _me(sso, await sso.headers(oid=oid, preferred_username="s.serbest@uni.edu.tr"))
    assert me2["id"] == inv["user_id"]
    loc = await sso.callback(
        await sso.start(), oid="60000000-0000-4000-8000-000000000007", preferred_username="sehriban.serbest@uni.edu.tr"
    )
    assert error_of(loc) == "account_exists"
    assert [e.after["kind"] for e in await _all(AuditEvent, AuditEvent.action == "auth.sso_bind")] == ["invite"]


async def test_invite_is_not_bound_by_an_unverified_email_claim(sso):  # noqa: F811
    r = await sso.client.post("/api/v1/auth/sso/admin/invites", json={"email": "d.kaya@uni.edu.tr"}, headers=sso.admin)
    assert r.status_code == 201
    invited = r.json()["user_id"]
    # the e-mail claim alone (mutable, not domain-verified) is ignored: no binding, a separate account under the UPN
    me = await _me(sso, await sso.headers(oid="70000000-0000-4000-8000-000000000007",
                                          preferred_username="other@uni.edu.tr", email="d.kaya@uni.edu.tr"))
    assert me["id"] != invited and me["email"] == "other@uni.edu.tr"
    assert len(await _all(SsoInvite)) == 1
    # an e-mail with the domain-owner-verified flag (optional claim xms_edov) counts
    me = await _me(sso, await sso.headers(oid="70000000-0000-4000-8000-000000000008",
                                          preferred_username="other2@uni.edu.tr", email="D.Kaya@uni.edu.tr",
                                          xms_edov=True))
    assert me["id"] == invited


async def test_expired_invite_is_refused(sso):  # noqa: F811
    r = await sso.client.post(
        "/api/v1/auth/sso/admin/invites", json={"email": "e.demir@uni.edu.tr", "days": 1}, headers=sso.admin
    )
    assert r.status_code == 201
    async with dbmod.get_session_factory()() as s:
        await s.execute(update(SsoInvite).values(expires_at=utcnow() - timedelta(minutes=1)))
        await s.commit()
    status = (await sso.client.get("/api/v1/auth/sso/admin/user-status", headers=sso.admin)).json()
    assert status[str(r.json()["user_id"])] == "invite_expired"
    loc = await sso.callback(await sso.start(), oid="80000000-0000-4000-8000-000000000008",
                             preferred_username="e.demir@uni.edu.tr")
    assert error_of(loc) == "invite_expired"
    assert await _all(UserIdentity) == []


async def test_invite_creation_follows_no_escalation(sso):  # noqa: F811
    _, users_admin = await make_user(sso.client, sso.admin, "kullanici.yonetici@uni.edu.tr", role="TEACHER")
    custom = await sso.client.post(
        "/api/v1/roles", json={"name": "Kullanıcı Yöneticisi", "permissions": ["setup.users", "room.view"]},
        headers=sso.admin,
    )
    uid = (await _one(User, User.email == "kullanici.yonetici@uni.edu.tr")).id
    await sso.client.put(f"/api/v1/users/{uid}", json={"role_id": custom.json()["id"]}, headers=sso.admin)
    from tests.api_fixtures import login

    h = await login(sso.client, "kullanici.yonetici@uni.edu.tr", "parola-1234")
    r = await sso.client.post("/api/v1/auth/sso/admin/invites", json={"email": "x@uni.edu.tr", "role": "ADMIN"},
                              headers=h)
    assert r.status_code == 403
    admin_id = (await _one(User, User.email == "admin@example.com")).id
    r = await sso.client.post(f"/api/v1/auth/sso/admin/users/{admin_id}/bind", json={}, headers=h)
    assert r.status_code == 403  # nor mark an administrator's account for binding
    r = await sso.client.post("/api/v1/auth/sso/admin/invites", json={"email": "admin@example.com"}, headers=sso.admin)
    assert r.status_code == 409  # existing account: use "bind on next SSO login" instead


async def test_admin_marks_existing_admin_account_bind_on_next_login(sso):  # noqa: F811
    uid, _ = await make_user(sso.client, sso.admin, "ikinci.admin@uni.edu.tr", role="ADMIN")
    r = await sso.client.post(f"/api/v1/auth/sso/admin/users/{uid}/bind", json={"days": 7}, headers=sso.admin)
    assert r.status_code == 201 and r.json()["kind"] == "bind", r.text
    me = await _me(sso, await sso.headers(oid="90000000-0000-4000-8000-000000000009",
                                          preferred_username="IKINCI.ADMIN@UNI.EDU.TR"))
    assert me["id"] == uid and me["role"] == "ADMIN"
    r = await sso.client.post(f"/api/v1/auth/sso/admin/users/{uid}/bind", json={}, headers=sso.admin)
    assert r.status_code == 409  # already linked
    r = await sso.client.delete(f"/api/v1/auth/sso/admin/users/{uid}/identity", headers=sso.admin)
    assert r.status_code == 204
    assert [e.after["kind"] for e in await _all(AuditEvent, AuditEvent.action == "auth.sso_bind")] == ["bind"]
    assert await _all(AuditEvent, AuditEvent.action == "sso.unlink")


async def test_linking_a_local_account_needs_the_password_and_confirmation(sso):  # noqa: F811
    uid, h = await make_user(sso.client, sso.admin, "yerel.hoca@uni.edu.tr")
    url = "/api/v1/auth/sso/entra/link"
    r = await sso.client.post(url, json={"password": "yanlış-parola", "confirm": True}, headers=h)
    assert r.status_code == 403
    r = await sso.client.post(url, json={"password": "parola-1234", "confirm": False}, headers=h)
    assert r.status_code == 422
    r = await sso.client.post(url, json={"password": "parola-1234", "confirm": True}, headers=h)
    assert r.status_code == 200, r.text
    from urllib.parse import parse_qs, urlsplit

    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["authorize_url"]).query).items()}
    loc = await sso.callback(q, oid="a0000000-0000-4000-8000-00000000000a", preferred_username="farkli@uni.edu.tr")
    assert loc == f"{PANEL}/profile?sso=linked", loc
    status = (await sso.client.get("/api/v1/auth/sso/me", headers=h)).json()
    assert status["linked"] is True and status["email_at_login"] == "farkli@uni.edu.tr"
    me = await _me(sso, await sso.headers(oid="a0000000-0000-4000-8000-00000000000a"))
    assert me["id"] == uid
    assert await _all(AuditEvent, AuditEvent.action == "auth.sso_link")
    # the same Entra account cannot be linked to a second SmartSched account
    _, h2 = await make_user(sso.client, sso.admin, "baska.hoca@uni.edu.tr")
    r = await sso.client.post(url, json={"password": "parola-1234", "confirm": True}, headers=h2)
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["authorize_url"]).query).items()}
    loc = await sso.callback(q, oid="a0000000-0000-4000-8000-00000000000a")
    assert error_of(loc) == "already_linked"
    # unlinking the own identity: allowed while a password remains
    assert (await sso.client.delete(url, headers=h)).status_code == 204
    assert (await sso.client.get("/api/v1/auth/sso/me", headers=h)).json()["linked"] is False
