"""AU-10 / AU-11: administrator actions for accounts added by e-mail (docs/research/2026-10-18-auth-backend.md §6, §7).

* ``POST /admin/users/{id}/mfa/reset``: a reason and the identity check are required, audited, refused for SSO-only
  accounts and for the administrator's own account, signs the person out, e-mails them; secrets never appear.
* ``POST /admin/users/{id}/password-reset-link``: local accounts only (``sso_account``, ``directory_account``), the
  existing one-time reset token e-mailed as a link, never in the answer and never stored in the outbox; audited.
"""

from __future__ import annotations

import re

import pytest
from app.services import bookings_notify

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import (
    API,
    PASSWORD,
    audit_rows,
    code_now,
    enrol_totp,
    make_user,
    outbox,
    password_step,
    set_user,
)
from tests.test_crbs_users import FakeSMTP
from tests.webauthn_soft import SoftAuthenticator

EMAIL = "hatice.ozturk@uni.edu.tr"
REASON = "Telefonunu kaybetti; kimliğini bölüm sekreterliğinde yüz yüze doğruladım."
SECRET_WORDS = ("secret", '"recovery_codes"', "public_key", "code_hash", "token_hash", "otpauth", "credential_id")


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    uid, headers = await make_user(client, admin, EMAIL, firstname="Hatice", lastname="Öztürk")
    return client, admin, uid, headers


async def _smtp(c, admin, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(bookings_notify.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent, FakeSMTP.fail = [], False
    r = await c.put(
        f"{API}/mail/settings",
        json={"host": "smtp.uni.edu.tr", "username": "bildirim", "password": "smtp-gizli", "from_address": "bildirim@uni.edu.tr"},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    r = await c.put(f"{API}/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=admin)
    assert r.status_code == 200, r.text


def _reset_body(**extra):  # type: ignore[no-untyped-def]
    return {"reason": REASON, "identity_check": "in_person", **extra}


# --------------------------------------------------------------------------------------------------
# MFA reset
# --------------------------------------------------------------------------------------------------


async def test_admin_sees_the_state_but_never_a_secret(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await c.put(f"{API}/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=admin)
    await enrol_totp(c, headers)
    r = await c.get(f"{API}/admin/users/{uid}/mfa", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totp_enabled"] is True and body["recovery_codes_remaining"] == 10
    assert body["account_type"] == "local" and body["can_reset_mfa"] is True and body["can_send_reset_link"] is True
    text = r.text.lower()
    assert not any(w in text for w in SECRET_WORDS), text


async def test_reset_needs_reason_and_identity_check(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await enrol_totp(c, headers)
    for body in ({}, {"reason": "kısa", "identity_check": "in_person"}, {"reason": REASON}, _reset_body(identity_check="sezgi")):
        r = await c.post(f"{API}/admin/users/{uid}/mfa/reset", json=body, headers=admin)
        assert r.status_code == 422, (body, r.text)
    # a teacher cannot reset anyone
    r = await c.post(f"{API}/admin/users/{uid}/mfa/reset", json=_reset_body(), headers=headers)
    assert r.status_code == 403


async def test_reset_removes_factors_signs_out_audits_and_mails(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await c.put(f"{API}/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=admin)
    secret, _codes = await enrol_totp(c, headers)
    auth = SoftAuthenticator("plan.uni.edu.tr", "https://plan.uni.edu.tr")
    r = await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)
    opts = r.json()
    r = await c.post(
        f"{API}/auth/passkeys/register/verify",
        json={"challenge_token": opts["challenge_token"], "credential": auth.register(opts["options"]), "name": "Telefon"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    step = await password_step(c, EMAIL)
    r = await c.post(
        f"{API}/auth/mfa/verify",
        json={"challenge_token": step["challenge_token"], "method": "totp", "code": code_now(secret), "trust_device": True},
    )
    device = r.json()["trusted_device_token"]

    r = await c.post(f"{API}/admin/users/{uid}/mfa/reset", json=_reset_body(), headers=admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["removed"] == {"totp": True, "recovery_code_count": 10, "passkeys": 1, "trusted_devices": 1}
    assert not any(w in r.text.lower() for w in SECRET_WORDS)
    # signed out everywhere; the next sign-in needs only the password; the trusted device is gone
    assert (await c.get(f"{API}/auth/me", headers=headers)).status_code == 401
    assert "access_token" in await password_step(c, EMAIL, **{"X-Trusted-Device": device})
    events = await audit_rows("auth.mfa_reset_by_admin")
    assert len(events) == 1
    ev = events[0]
    assert ev.entity_id == str(uid) and ev.reason == REASON
    assert (ev.after or {})["identity_check"] == "in_person"
    assert not any(w in str(ev.after).lower() for w in ("secret", "code_hash", "public_key"))
    mails = await outbox("mfa_reset_by_admin", uid)
    assert len(mails) == 1 and mails[0].to_email == EMAIL


async def test_reset_can_keep_passkeys(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await c.put(f"{API}/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=admin)
    await enrol_totp(c, headers)
    auth = SoftAuthenticator("plan.uni.edu.tr", "https://plan.uni.edu.tr")
    opts = (await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)).json()
    await c.post(
        f"{API}/auth/passkeys/register/verify",
        json={"challenge_token": opts["challenge_token"], "credential": auth.register(opts["options"]), "name": "Anahtar"},
        headers=headers,
    )
    r = await c.post(f"{API}/admin/users/{uid}/mfa/reset", json=_reset_body(keep_passkeys=True), headers=admin)
    assert r.status_code == 200 and r.json()["removed"]["passkeys"] == 0
    step = await password_step(c, EMAIL)
    assert step["mfa_methods"] == ["passkey"]


async def test_reset_refused_for_sso_only_and_own_account(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, _headers = setup
    await set_user(uid, auth_source="oidc", password_hash=None)
    r = await c.post(f"{API}/admin/users/{uid}/mfa/reset", json=_reset_body(), headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sso_account"
    assert "kimlik sağlayıcı" in r.json()["detail"]["message_tr"].lower()
    me = (await c.get(f"{API}/auth/me", headers=admin)).json()["id"]
    r = await c.post(f"{API}/admin/users/{me}/mfa/reset", json=_reset_body(), headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "own_account"
    r = await c.post(f"{API}/admin/users/999999/mfa/reset", json=_reset_body(), headers=admin)
    assert r.status_code == 404
    assert await audit_rows("auth.mfa_reset_by_admin") == []


# --------------------------------------------------------------------------------------------------
# password-reset link
# --------------------------------------------------------------------------------------------------


async def test_reset_link_is_mailed_never_shown_and_works(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, _headers = setup
    await _smtp(c, admin, monkeypatch)
    r = await c.post(f"{API}/admin/users/{uid}/password-reset-link", json={}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["emailed"] is True and body["expires_at"] and "token" not in body
    sent = [m for m in FakeSMTP.sent if m["To"] == EMAIL]
    assert len(sent) == 1
    plain = sent[0].get_body(preferencelist=("plain",)).get_content()
    m = re.search(r"https://plan\.uni\.edu\.tr/reset-password\?token=([A-Za-z0-9_\-]+)", plain)
    assert m, plain
    token = m.group(1)
    assert token not in r.text
    rows = await outbox("password_reset_link_by_admin", uid)
    assert len(rows) == 1 and token not in rows[0].body and token not in (rows[0].link or "")
    r = await c.post(f"{API}/auth/password-reset/confirm", json={"token": token, "password": "yeni-parola-2026"})
    assert r.status_code == 200, r.text
    assert "access_token" in await password_step(c, EMAIL, "yeni-parola-2026")
    events = await audit_rows("auth.reset_link_by_admin")
    assert len(events) == 1 and token not in str(events[0].after)


async def test_reset_link_does_not_bypass_2fa(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await _smtp(c, admin, monkeypatch)
    await enrol_totp(c, headers)
    await c.post(f"{API}/admin/users/{uid}/password-reset-link", json={}, headers=admin)
    plain = [m for m in FakeSMTP.sent if m["To"] == EMAIL][-1].get_body(preferencelist=("plain",)).get_content()
    token = re.search(r"token=([A-Za-z0-9_\-]+)", plain).group(1)  # type: ignore[union-attr]
    assert (await c.post(f"{API}/auth/password-reset/confirm", json={"token": token, "password": "yeni-parola-2026"})).status_code == 200
    assert (await password_step(c, EMAIL, "yeni-parola-2026"))["mfa_required"] is True


async def test_reset_link_refused_for_sso_ldap_no_mail_no_smtp(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, _headers = setup
    r = await c.post(f"{API}/admin/users/{uid}/password-reset-link", json={}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "mail_not_configured"
    await _smtp(c, admin, monkeypatch)
    await set_user(uid, auth_source="oidc", password_hash=None)
    r = await c.post(f"{API}/admin/users/{uid}/password-reset-link", json={}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sso_account"
    await set_user(uid, auth_source="ldap")
    r = await c.post(f"{API}/admin/users/{uid}/password-reset-link", json={}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "directory_account"
    bid, _ = await make_user(c, admin, "eposta.yok@uni.edu.tr")
    await set_user(bid, email=None, username="epostasiz")
    r = await c.post(f"{API}/admin/users/{bid}/password-reset-link", json={}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_email"
    assert FakeSMTP.sent == []
    assert await audit_rows("auth.reset_link_by_admin") == []


async def test_break_glass_admin_with_identity_and_password_is_local(setup) -> None:  # type: ignore[no-untyped-def]
    """A linked identity plus a local password (the break-glass administrator) still has local 2FA."""
    from app.core import db as dbmod
    from app.models.sso import UserIdentity

    c, admin, uid, _headers = setup
    async with dbmod.get_session_factory()() as s:
        s.add(UserIdentity(user_id=uid, provider="entra", issuer="https://login.microsoftonline.com/t/v2.0", tenant_id="t", subject="o-1"))
        await s.commit()
    body = (await c.get(f"{API}/admin/users/{uid}/mfa", headers=admin)).json()
    assert body["account_type"] == "mixed" and body["can_reset_mfa"] is True
    await set_user(uid, password_hash=None)
    body = (await c.get(f"{API}/admin/users/{uid}/mfa", headers=admin)).json()
    assert body["account_type"] == "sso" and body["can_reset_mfa"] is False and body["can_send_reset_link"] is False
