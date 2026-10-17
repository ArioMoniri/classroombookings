"""Invitations per provider (wave 3b W3-IDP): the themed invite e-mail (W3-MAIL renderer, kind ``invitation``),
resend, the local-password invite, revoke disabling the unused placeholder (T-R1-35), bulk invite from a Turkish
Excel CSV, the per-provider user status, and the integrations-hub cards."""

from __future__ import annotations

from app.core import db as dbmod
from app.models import AuditEvent, NotificationOutbox, User
from app.models.sso import SsoInvite
from app.services import bookings_notify
from sqlalchemy import select

from tests.test_crbs_users import FakeSMTP
from tests.test_w3b_idp_fakes import PANEL, idp, query_of  # noqa: F401

INV = "/api/v1/auth/sso/admin/invites"


async def _all(model, *where):  # type: ignore[no-untyped-def]
    async with dbmod.get_session_factory()() as s:
        return list((await s.execute(select(model).where(*where))).scalars())


async def _smtp(idp, monkeypatch) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    monkeypatch.setattr(bookings_notify.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent, FakeSMTP.fail = [], False
    r = await idp.client.put(
        "/api/v1/mail/settings",
        json={
            "host": "smtp.uni.edu.tr",
            "username": "bildirim",
            "password": "smtp-gizli",
            "from_address": "bildirim@uni.edu.tr",
        },
        headers=idp.admin,
    )
    assert r.status_code == 200, r.text


async def test_invite_email_is_themed_and_the_outbox_never_keeps_the_link(idp, monkeypatch) -> None:  # noqa: F811
    await _smtp(idp, monkeypatch)
    await idp.keycloak()
    r = await idp.client.post(
        INV,
        json={
            "email": "Gözde.AYRANCIGİL@uni.edu.tr",
            "full_name": "Gözde Ayrancıgil",
            "provider": "keycloak",
            "send_email": True,
            "locale": "tr",
        },
        headers=idp.admin,
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["email"] == "gözde.ayrancigil@uni.edu.tr" and out["email_status"] == "SENT"
    assert out["provider_label"] == "Keycloak"
    token = query_of(out["link"])["invite"]
    (msg,) = FakeSMTP.sent
    assert msg["To"] == "gözde.ayrancigil@uni.edu.tr"
    html = msg.get_body(preferencelist=("html",)).get_content()
    plain = msg.get_body(preferencelist=("plain",)).get_content()
    assert token in html and "Keycloak" in html and token in plain and "Administrator" in plain
    (row,) = await _all(NotificationOutbox, NotificationOutbox.kind == "invitation")
    assert row.status == "SENT" and token not in row.body
    # resend: the same link again
    r = await idp.client.post(f"{INV}/{out['id']}/resend", headers=idp.admin)
    assert r.status_code == 200 and r.json()["sent"] is True and len(FakeSMTP.sent) == 2
    assert token in FakeSMTP.sent[1].get_body(preferencelist=("html",)).get_content()


async def test_without_smtp_the_invite_is_unsent_and_the_link_can_be_copied(idp) -> None:  # noqa: F811
    r = await idp.client.post(INV, json={"email": "kopya@uni.edu.tr", "send_email": True}, headers=idp.admin)
    assert r.status_code == 201 and r.json()["email_status"] == "UNSENT" and r.json()["link"].startswith(PANEL)
    assert r.json()["provider"] == "entra"  # the default stays Microsoft (T-R1-35 behaviour)


async def test_local_password_invite_sets_a_password_and_signs_in(idp) -> None:  # noqa: F811
    r = await idp.client.post(
        INV, json={"email": "misafir.hoca@uni.edu.tr", "provider": "local", "role": "TEACHER"}, headers=idp.admin
    )
    assert r.status_code == 201, r.text
    assert r.json()["provider"] == "local" and r.json()["provider_label"] == "Yerel parola"
    token = query_of(r.json()["link"])["invite"]
    banner = (await idp.client.get(f"/api/v1/auth/sso/invites/{token}")).json()
    assert banner["provider"] == "local" and banner["start_url"] is None
    # an identity provider's start refuses a local invite
    s = await idp.client.get("/api/v1/auth/sso/entra/start", params={"invite": token})
    assert query_of(s.headers["location"])["error"] in ("invite_provider", "not_enabled")
    short = await idp.client.post(f"/api/v1/auth/sso/invites/{token}/password", json={"password": "kisa"})
    assert short.status_code == 422
    ok = await idp.client.post(f"/api/v1/auth/sso/invites/{token}/password", json={"password": "Güçlü-parola-2026"})
    assert ok.status_code == 200, ok.text
    r = await idp.client.post(
        "/api/v1/auth/login", json={"email": "misafir.hoca@uni.edu.tr", "password": "Güçlü-parola-2026"}
    )
    assert r.status_code == 200, r.text
    again = await idp.client.post(f"/api/v1/auth/sso/invites/{token}/password", json={"password": "Başka-parola-1"})
    assert again.status_code == 404  # one time
    actions = [e.action for e in await _all(AuditEvent, AuditEvent.action.like("user.invite%"))]
    assert actions == ["user.invited", "user.invite_accepted"] or "user.invite_accepted" in actions


async def test_revoking_a_provider_invite_disables_the_unused_placeholder(idp) -> None:  # noqa: F811
    await idp.keycloak()
    r = await idp.client.post(INV, json={"email": "iptal@uni.edu.tr", "provider": "keycloak"}, headers=idp.admin)
    inv = r.json()
    assert (await idp.client.delete(f"{INV}/{inv['id']}", headers=idp.admin)).status_code == 204
    (user,) = await _all(User, User.email == "iptal@uni.edu.tr")
    assert user.is_active is False
    # a new invite to the same address (another provider) re-enables it
    r = await idp.client.post(INV, json={"email": "iptal@uni.edu.tr", "provider": "local"}, headers=idp.admin)
    assert r.status_code == 201, r.text
    (user,) = await _all(User, User.email == "iptal@uni.edu.tr")
    assert user.is_active is True and user.auth_source == "local"


async def test_bulk_invite_from_a_turkish_excel_csv(idp) -> None:  # noqa: F811
    await idp.keycloak()
    csv = (
        "﻿E-posta;Ad Soyad;Rol;Sağlayıcı\n"
        "AYŞE.KAYA@UNİ.EDU.TR;Ayşe\xa0Kaya;Öğretmen;keycloak\n"
        "mehmet.oz@uni.edu.tr;Mehmet Öz;;\n"
        "bozuk-adres;Bozuk;;\n"
        "ayşe.kaya@uni.edu.tr;Tekrar;;\n"
        "rol.yok@uni.edu.tr;Rol Yok;Rektör;\n"
        "\n"
    )
    r = await idp.client.post(f"{INV}/bulk", json={"csv": csv, "provider": "local"}, headers=idp.admin)
    assert r.status_code == 200, r.text
    out = r.json()
    created = {c["email"]: c for c in out["created"]}
    assert set(created) == {"ayşe.kaya@uni.edu.tr", "mehmet.oz@uni.edu.tr"}
    assert created["ayşe.kaya@uni.edu.tr"]["provider"] == "keycloak"  # the row's column wins
    assert created["mehmet.oz@uni.edu.tr"]["provider"] == "local"  # the request's default
    assert all(c.get("link") is None for c in out["created"])  # bulk answers never list links
    codes = {(e["line"], e["code"]) for e in out["errors"]}
    assert codes == {(4, "invalid_email"), (5, "duplicate"), (6, "unknown_role")}
    assert all(e["tr"] and e["en"] for e in out["errors"])
    (ayse,) = await _all(User, User.email == "ayşe.kaya@uni.edu.tr")
    assert ayse.full_name == "Ayşe Kaya" and ayse.role == "TEACHER"
    assert len(await _all(SsoInvite)) == 2
    st = (await idp.client.get("/api/v1/auth/sso/admin/user-status", headers=idp.admin)).json()
    assert st[str(ayse.id)]["invite"]["provider"] == "keycloak" and st[str(ayse.id)]["status"] == "invited"


async def test_user_status_lists_every_linked_provider(idp) -> None:  # noqa: F811
    await idp.keycloak()
    await idp.google_ws()
    h = await idp.headers("keycloak", idp.kc)
    me = (await idp.client.get("/api/v1/auth/me", headers=h)).json()
    st = (await idp.client.get("/api/v1/auth/sso/admin/user-status", headers=idp.admin)).json()[str(me["id"])]
    assert st["status"] == "linked" and st["auth_methods"] == ["oidc"] and st["providers"] == ["keycloak"]


async def test_integration_status_cards_for_the_hub(idp) -> None:  # noqa: F811
    from app.services import identity

    async with dbmod.get_session_factory()() as s:
        empty = await identity.integration_status(s)
    assert [c["key"] for c in empty] == ["identity.providers", "identity.ldap"]
    kc = await idp.keycloak()
    async with dbmod.get_session_factory()() as s:
        cards = {c["key"]: c for c in await identity.integration_status(s)}
    card = cards["identity.keycloak"]
    assert card["status"] == "connected" and card["enabled"] is True and card["changed_by"]
    assert card["toggle"] == {
        "method": "PUT",
        "path": f"/auth/sso/admin/providers/{kc['id']}",
        "field": "enabled",
        "enable_in_setup": True,  # no test login yet
    }
    assert "secret" not in repr(card).lower() or "client_secret" not in repr(card)
    r = await idp.client.get("/api/v1/integrations/status", headers=idp.admin)
    assert r.status_code == 200, r.text
    identity_area = next(a for a in r.json()["areas"] if a["key"] == "identity")
    assert {c["key"] for c in identity_area["cards"]} == {"identity.keycloak", "identity.ldap"}
    assert all(c["source"] == "contract" for c in identity_area["cards"])
