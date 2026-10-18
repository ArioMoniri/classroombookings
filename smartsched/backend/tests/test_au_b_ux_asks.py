"""AU-13…AU-16: the auth UX spec's asks to the backend (docs/design/v3/auth.md §17): the 10-minute re-auth window,
"Bu cihazı hatırla" off / 7 / 30 days, remembered devices ending with a password change, passkey flags in
``/org/public``, a session after a reset link (through the same 2FA gate), the sign-in history and the extra security
e-mails (passkey_removed, recovery_codes_regenerated, mfa_required)."""

from __future__ import annotations

import pytest
from app.core import db as dbmod
from app.core.security import create_access_token
from app.models import User

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import (
    API,
    PASSWORD,
    bearer,
    enrol_totp,
    make_user,
    next_code,
    outbox,
    password_step,
    set_policy,
    totp_clock,  # noqa: F401  (autouse fixture)
)

EMAIL = "selin.kaya@uni.edu.tr"


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    uid, headers = await make_user(client, admin, EMAIL)
    return client, admin, uid, headers


async def _old_token(uid: int) -> dict[str, str]:
    """A valid session issued 11 minutes ago (outside the re-auth window)."""
    async with dbmod.get_session_factory()() as s:
        u = await s.get(User, uid)
        assert u is not None
        tok = create_access_token(u.email or "", {"uid": u.id, "role": u.role, "tv": int(u.token_version or 0)})
    import jwt
    from app.core.config import get_settings

    claims = jwt.decode(tok, get_settings().signing_key, algorithms=[get_settings().jwt_algorithm])
    claims["iat"] -= 11 * 60
    return bearer(jwt.encode(claims, get_settings().signing_key, algorithm=get_settings().jwt_algorithm))


async def test_fresh_session_needs_no_password_old_one_does(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    r = await c.post(f"{API}/auth/mfa/totp/start", json={}, headers=headers)
    assert r.status_code == 200, r.text  # signed in a moment ago
    old = await _old_token(uid)
    r = await c.post(f"{API}/auth/mfa/recovery-codes", json={}, headers=old)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_failed"
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": "yanlis"}, headers=headers)
    assert r.status_code in (403, 409)  # a password that is sent must be right


async def test_remember_device_can_be_switched_off(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    await set_policy(c, admin, trusted_device_days=0)
    step = await password_step(c, EMAIL)
    r = await c.post(
        f"{API}/auth/mfa/verify",
        json={"challenge_token": step["challenge_token"], "code": next_code(secret), "trust_device": True},
    )
    assert r.status_code == 200 and r.json()["trusted_device_token"] is None and r.json()["trusted_device_days"] == 0
    r = await c.put(f"{API}/admin/auth/mfa-policy", json={"trusted_device_days": 14}, headers=admin)
    assert r.status_code == 422
    body = await set_policy(c, admin, trusted_device_days=7)
    assert body["trusted_device_days"] == 7
    step = await password_step(c, EMAIL)
    r = await c.post(
        f"{API}/auth/mfa/verify",
        json={"challenge_token": step["challenge_token"], "code": next_code(secret), "trust_device": True},
    )
    assert r.json()["trusted_device_days"] == 7
    device = (await c.get(f"{API}/auth/trusted-devices", headers=headers)).json()[0]
    assert (device["expires_at"][:10]) > (device["created_at"][:10])


async def test_password_change_ends_remembered_devices(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    step = await password_step(c, EMAIL)
    r = await c.post(
        f"{API}/auth/mfa/verify",
        json={"challenge_token": step["challenge_token"], "code": next_code(secret), "trust_device": True},
    )
    device = r.json()["trusted_device_token"]
    session = bearer(r.json()["access_token"])
    r = await c.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "yeni-parola-2026"},
        headers=session,
    )
    assert r.status_code == 200, r.text
    again = await password_step(c, EMAIL, "yeni-parola-2026", **{"X-Trusted-Device": device})
    assert again["mfa_required"] is True


async def test_org_public_carries_the_passkey_flags(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, _headers = setup
    flags = (await c.get(f"{API}/org/public")).json()["passkeys"]
    assert flags == {"enabled": False, "sign_in": False, "trusted_device_days": 30}  # no public https URL yet
    await c.put(f"{API}/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=admin)
    await set_policy(c, admin, passkey_first_factor=True)
    flags = (await c.get(f"{API}/org/public")).json()["passkeys"]
    assert flags["enabled"] is True and flags["sign_in"] is True


async def test_reset_link_answer_signs_in_through_the_gate(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    r = await c.post(f"{API}/users/{uid}/reset-token", headers=admin)  # no SMTP: the admin passes the code on
    token = r.json()["token"]
    r = await c.post(f"{API}/auth/password-reset/confirm", json={"token": token, "password": "yeni-parola-2026"})
    assert r.status_code == 200 and r.json()["session"]["access_token"]
    await enrol_totp(c, bearer(r.json()["session"]["access_token"]))
    token = (await c.post(f"{API}/users/{uid}/reset-token", headers=admin)).json()["token"]
    r = await c.post(f"{API}/auth/password-reset/confirm", json={"token": token, "password": "baska-parola-2026"})
    session = r.json()["session"]
    assert session["access_token"] is None and session["mfa_required"] is True and session["challenge_token"]


async def test_sign_in_history_lists_my_security_events(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    step = await password_step(c, EMAIL)
    await c.post(f"{API}/auth/mfa/verify", json={"challenge_token": step["challenge_token"], "code": next_code(secret)})
    r = await c.get(f"{API}/auth/sign-ins", headers=headers)
    assert r.status_code == 200, r.text
    actions = [e["action"] for e in r.json()["events"]]
    assert actions[0] == "auth.mfa_verified" and "auth.mfa_enabled" in actions
    assert all("ip" not in e for e in r.json()["events"])


async def test_recovery_regeneration_and_passkey_removal_are_mailed(setup) -> None:  # type: ignore[no-untyped-def]
    from tests.webauthn_soft import SoftAuthenticator

    c, admin, uid, headers = setup
    await enrol_totp(c, headers)
    await c.post(f"{API}/auth/mfa/recovery-codes", json={"password": PASSWORD}, headers=headers)
    assert len(await outbox("recovery_codes_regenerated", uid)) == 1
    await c.put(f"{API}/calendar/admin/settings", json={"public_url": "https://plan.uni.edu.tr"}, headers=admin)
    opts = (await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)).json()
    auth = SoftAuthenticator("plan.uni.edu.tr", "https://plan.uni.edu.tr")
    r = await c.post(
        f"{API}/auth/passkeys/register/verify",
        json={"challenge_token": opts["challenge_token"], "credential": auth.register(opts["options"]), "name": "Mac"},
        headers=headers,
    )
    pid = r.json()["passkey"]["id"]
    await c.post(f"{API}/auth/passkeys/{pid}/remove", json={"password": PASSWORD}, headers=headers)
    assert len(await outbox("passkey_removed", uid)) == 1


async def test_required_policy_announces_itself_to_people_without_a_factor(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    bid, bheaders = await make_user(c, admin, "mert.aydin@uni.edu.tr")
    await enrol_totp(c, bheaders)  # already has a second factor: no e-mail
    await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"])
    assert len(await outbox("mfa_required", uid)) == 1
    assert await outbox("mfa_required", bid) == []
    await set_policy(c, admin, mfa_grace_days=30)  # no new role: nobody is told twice
    assert len(await outbox("mfa_required", uid)) == 1
