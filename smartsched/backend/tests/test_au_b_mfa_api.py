"""AU-02…AU-06: authenticator-app 2FA end to end through the API (docs/research/2026-10-18-auth-backend.md §2, §4–§8).

Enrolment (start → otpauth URI + secret → confirm → ten recovery codes once), the sign-in challenge step (password
OK → ``mfa_required`` + a short-lived challenge token → TOTP or a recovery code → session), drift of ±1 step, replay,
recovery-code single use, lockout, trusted devices, disabling with re-authentication, regeneration, the organisation
policy (off / optional / required_for_roles with grace) and the SSO refusal. Every event is audited and the security
e-mails are queued through ``mail.send_kind``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from app.core import totp
from app.core.security_http import LIMITS

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import (
    API,
    PASSWORD,
    audit_rows,
    bearer,
    code_now,
    enrol_totp,
    make_user,
    next_code,
    outbox,
    password_step,
    set_policy,
    set_user,
    totp_clock,  # noqa: F401  (autouse fixture)
)

EMAIL = "ayse.yilmaz@uni.edu.tr"


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    uid, headers = await make_user(client, admin, EMAIL, firstname="Ayşe", lastname="Yılmaz")
    return client, admin, uid, headers


async def _session(c, challenge: str, code: str, method: str = "totp", **extra: Any):  # type: ignore[no-untyped-def]
    return await c.post(
        f"{API}/auth/mfa/verify", json={"challenge_token": challenge, "method": method, "code": code, **extra}
    )


# --------------------------------------------------------------------------------------------------
# enrolment
# --------------------------------------------------------------------------------------------------


async def test_status_of_a_local_account_before_enrolment(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    r = await c.get(f"{API}/auth/mfa", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True and body["reason"] is None
    assert body["totp"]["enabled"] is False
    assert body["recovery_codes"] == {"remaining": 0, "total": 0}
    assert body["passkeys"] == [] and body["trusted_devices"] == []
    assert body["policy"]["mfa_policy"] == "optional" and body["required"] is False


async def test_enrolment_start_needs_the_password_and_returns_uri_and_secret(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": "yanlis-parola"}, headers=headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_failed"
    assert r.json()["detail"]["message_tr"]
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["secret"]) == 32 and body["otpauth_uri"].startswith("otpauth://totp/")
    assert f"secret={body['secret']}" in body["otpauth_uri"] and "ayse.yilmaz%40uni.edu.tr" in body["otpauth_uri"]
    assert body["digits"] == 6 and body["period"] == 30 and body["algorithm"] == "SHA1"
    # not on yet: signing in still needs only the password
    assert "access_token" in await password_step(c, EMAIL)


async def test_confirm_with_a_wrong_code_then_the_right_one(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": PASSWORD}, headers=headers)
    secret = r.json()["secret"]
    wrong = "000000" if code_now(secret) != "000000" else "111111"
    r = await c.post(f"{API}/auth/mfa/totp/confirm", json={"code": wrong}, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_code"
    r = await c.post(f"{API}/auth/mfa/totp/confirm", json={"code": code_now(secret)}, headers=headers)
    assert r.status_code == 200, r.text
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    status = (await c.get(f"{API}/auth/mfa", headers=headers)).json()
    assert status["totp"]["enabled"] is True and status["recovery_codes"] == {"remaining": 10, "total": 10}
    assert "secret" not in status["totp"]
    assert all(code not in str(status) for code in codes)  # never shown again
    assert [e.entity_id for e in await audit_rows("auth.mfa_enabled")] == [str(uid)]
    mails = await outbox("mfa_enabled", uid)
    assert len(mails) == 1 and mails[0].to_email == EMAIL
    assert mails[0].subject == "İki adımlı doğrulama açıldı"


# --------------------------------------------------------------------------------------------------
# the sign-in challenge step
# --------------------------------------------------------------------------------------------------


async def test_password_step_answers_mfa_required_and_the_code_gives_a_session(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    step = await password_step(c, EMAIL)
    assert step["mfa_required"] is True and not step.get("access_token")
    assert set(step["mfa_methods"]) == {"totp", "recovery"}
    assert 0 < step["challenge_expires_in"] <= 300
    # the challenge token is not a session
    assert (await c.get(f"{API}/auth/me", headers=bearer(step["challenge_token"]))).status_code == 401
    r = await _session(c, step["challenge_token"], next_code(secret))
    assert r.status_code == 200, r.text
    me = await c.get(f"{API}/auth/me", headers=bearer(r.json()["access_token"]))
    assert me.status_code == 200 and me.json()["id"] == uid
    # single use: the same challenge cannot start a second session
    r = await _session(c, step["challenge_token"], next_code(secret))
    assert r.status_code == 401 and r.json()["detail"]["code"] == "challenge_expired"
    assert len(await audit_rows("auth.mfa_verified")) == 1


async def test_a_wrong_password_never_reaches_the_second_factor(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    await enrol_totp(c, headers)
    r = await c.post(f"{API}/auth/login", json={"email": EMAIL, "password": "yanlis"})
    assert r.status_code == 401 and r.json()["detail"] == "invalid credentials"


async def test_drift_of_one_step_is_accepted_and_two_steps_are_not(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    base = totp.now() + 600  # later than the enrolment's step
    monkeypatch.setattr(totp, "now", lambda: base)
    for delta, ok in ((-2, False), (2, False), (-1, True)):
        step = await password_step(c, EMAIL)
        r = await _session(c, step["challenge_token"], totp.code_at(secret, int(base) + delta * 30))
        assert (r.status_code == 200) is ok, (delta, r.text)
    monkeypatch.setattr(totp, "now", lambda: base + 60)
    step = await password_step(c, EMAIL)
    r = await _session(c, step["challenge_token"], totp.code_at(secret, int(base + 60) + 30))  # +1 step
    assert r.status_code == 200, r.text


async def test_a_used_code_cannot_be_replayed_in_its_window(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    later = totp.now() + 300
    monkeypatch.setattr(totp, "now", lambda: later)
    code = totp.code_at(secret, int(later))
    assert (await _session(c, (await password_step(c, EMAIL))["challenge_token"], code)).status_code == 200
    r = await _session(c, (await password_step(c, EMAIL))["challenge_token"], code)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_code"


async def test_recovery_codes_are_single_use_and_announced(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    _secret, codes = await enrol_totp(c, headers)
    step = await password_step(c, EMAIL)
    typed = codes[3].lower().replace("-", " ")  # case and separators do not matter
    r = await _session(c, step["challenge_token"], typed, method="recovery")
    assert r.status_code == 200, r.text
    assert r.json()["recovery_codes_remaining"] == 9
    step = await password_step(c, EMAIL)
    r = await _session(c, step["challenge_token"], codes[3], method="recovery")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_code"
    status = (await c.get(f"{API}/auth/mfa", headers=headers)).json()
    assert status["recovery_codes"] == {"remaining": 9, "total": 10}
    assert len(await audit_rows("auth.mfa_recovery_used")) == 1
    assert len(await outbox("mfa_recovery_code_used", uid)) == 1


async def test_lockout_after_five_failures_even_with_the_right_code(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    right = next_code(secret)
    wrong = "123456" if right != "123456" else "654321"
    step = await password_step(c, EMAIL)
    for _ in range(5):
        r = await _session(c, step["challenge_token"], wrong)
        assert r.status_code == 401, r.text
    # the challenge is spent after five tries
    r = await _session(c, step["challenge_token"], right)
    assert r.status_code in (401, 429)
    step = await password_step(c, EMAIL)
    r = await _session(c, step["challenge_token"], right)
    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "mfa_locked" and detail["retry_after"] > 0 and detail["message_tr"]
    assert r.headers["retry-after"]
    assert len(await audit_rows("auth.mfa_failed")) == 5
    assert len(await audit_rows("auth.mfa_locked")) == 1


async def test_lockout_ends_after_its_window(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    for _ in range(5):
        step = await password_step(c, EMAIL)
        await _session(c, step["challenge_token"], "000001" if code_now(secret) != "000001" else "000002")
    from app.services import mfa

    real = mfa.clock
    monkeypatch.setattr(mfa, "clock", lambda: real() + mfa.LOCK_BASE + timedelta(seconds=1))
    later = totp.now() + 3600
    monkeypatch.setattr(totp, "now", lambda: later)
    step = await password_step(c, EMAIL)
    assert (await _session(c, step["challenge_token"], totp.code_at(secret, int(later)))).status_code == 200


# --------------------------------------------------------------------------------------------------
# trusted devices
# --------------------------------------------------------------------------------------------------


async def test_trusted_device_skips_the_second_factor_for_its_account_only(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    step = await password_step(c, EMAIL)
    r = await _session(c, step["challenge_token"], next_code(secret), trust_device=True)
    assert r.status_code == 200, r.text
    device = r.json()["trusted_device_token"]
    assert device and len(device) >= 40 and r.json()["trusted_device_days"] == 30
    direct = await password_step(c, EMAIL, **{"X-Trusted-Device": device})
    assert direct.get("access_token") and not direct.get("mfa_required")
    # the password is still needed
    r = await c.post(f"{API}/auth/login", json={"email": EMAIL, "password": "x"}, headers={"X-Trusted-Device": device})
    assert r.status_code == 401
    # another account with the same device token still gets its own challenge
    _bid, bheaders = await make_user(c, admin, "fatih.demir@uni.edu.tr")
    await enrol_totp(c, bheaders)
    other = await password_step(c, "fatih.demir@uni.edu.tr", **{"X-Trusted-Device": device})
    assert other["mfa_required"] is True
    listing = (await c.get(f"{API}/auth/trusted-devices", headers=headers)).json()
    assert len(listing) == 1 and "token" not in listing[0] and listing[0]["label"]
    r = await c.delete(f"{API}/auth/trusted-devices/{listing[0]['id']}", headers=headers)
    assert r.status_code == 204
    again = await password_step(c, EMAIL, **{"X-Trusted-Device": device})
    assert again["mfa_required"] is True
    assert len(await audit_rows("auth.trusted_device_revoked")) == 1


async def test_revoke_all_trusted_devices(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    secret, _ = await enrol_totp(c, headers)
    tokens = []
    for _ in range(2):
        step = await password_step(c, EMAIL)
        r = await _session(c, step["challenge_token"], next_code(secret), trust_device=True)
        assert r.status_code == 200, r.text
        tokens.append(r.json()["trusted_device_token"])
    r = await c.delete(f"{API}/auth/trusted-devices", headers=headers)
    assert r.status_code == 200 and r.json()["revoked"] == 2
    for t in tokens:
        assert (await password_step(c, EMAIL, **{"X-Trusted-Device": t}))["mfa_required"] is True


# --------------------------------------------------------------------------------------------------
# disable, regenerate
# --------------------------------------------------------------------------------------------------


async def test_disable_needs_password_and_a_current_code(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    secret, codes = await enrol_totp(c, headers)
    r = await c.post(f"{API}/auth/mfa/disable", json={"password": "yanlis", "code": code_now(secret)}, headers=headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_failed"
    r = await c.post(f"{API}/auth/mfa/disable", json={"password": PASSWORD, "code": "000000"}, headers=headers)
    assert r.status_code in (403, 422)
    r = await c.post(f"{API}/auth/mfa/disable", json={"password": PASSWORD, "code": codes[0]}, headers=headers)
    assert r.status_code == 200, r.text
    status = (await c.get(f"{API}/auth/mfa", headers=headers)).json()
    assert status["totp"]["enabled"] is False and status["recovery_codes"]["remaining"] == 0
    assert "access_token" in await password_step(c, EMAIL)
    assert len(await audit_rows("auth.mfa_disabled")) == 1
    assert len(await outbox("mfa_disabled", uid)) == 1


async def test_regenerating_recovery_codes_replaces_all_ten(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    _secret, old = await enrol_totp(c, headers)
    r = await c.post(f"{API}/auth/mfa/recovery-codes", json={"password": "yanlis"}, headers=headers)
    assert r.status_code == 403
    r = await c.post(f"{API}/auth/mfa/recovery-codes", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 200, r.text
    new = r.json()["recovery_codes"]
    assert len(new) == 10 and not set(new) & set(old)
    step = await password_step(c, EMAIL)
    assert (await _session(c, step["challenge_token"], old[0], method="recovery")).status_code == 401
    step = await password_step(c, EMAIL)
    assert (await _session(c, step["challenge_token"], new[0], method="recovery")).status_code == 200
    assert len(await audit_rows("auth.mfa_recovery_regenerated")) == 1


# --------------------------------------------------------------------------------------------------
# organisation policy
# --------------------------------------------------------------------------------------------------


async def test_policy_needs_the_authentication_permission_and_is_audited(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    r = await c.put(f"{API}/admin/auth/mfa-policy", json={"mfa_policy": "off"}, headers=headers)
    assert r.status_code == 403
    r = await c.put(f"{API}/admin/auth/mfa-policy", json={"mfa_policy": "sometimes"}, headers=admin)
    assert r.status_code == 422
    r = await c.put(f"{API}/admin/auth/mfa-policy", json={"mfa_roles": ["NOPE"]}, headers=admin)
    assert r.status_code == 422
    body = await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"], mfa_grace_days=7)
    assert body["mfa_policy"] == "required_for_roles" and body["mfa_roles"] == ["TEACHER"]
    assert body["mfa_grace_days"] == 7 and body["passkeys_enabled"] is True and body["passkey_first_factor"] is False
    assert (await c.get(f"{API}/admin/auth/mfa-policy", headers=admin)).json() == body
    assert len(await audit_rows("auth.mfa_policy")) == 1


async def test_policy_off_skips_the_challenge_and_hides_enrolment(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    await enrol_totp(c, headers)
    await set_policy(c, admin, mfa_policy="off")
    assert "access_token" in await password_step(c, EMAIL)
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "mfa_off"


async def test_required_for_role_with_grace_signs_in_and_says_so(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, _headers = setup
    await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"], mfa_grace_days=14)
    step = await password_step(c, EMAIL)
    assert step["access_token"] and step["mfa_setup_required"] is True and step["mfa_grace_until"]
    # the administrator (ADMIN, not in the list) is not asked
    admin_step = await password_step(c, "admin@example.com", "admin1234")
    assert not admin_step.get("mfa_setup_required")


async def test_required_after_grace_allows_only_enrolment_then_signs_in(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"], mfa_grace_days=0)
    step = await password_step(c, EMAIL)
    assert not step.get("access_token") and step["mfa_setup_required"] is True
    assert set(step["mfa_setup_methods"]) >= {"totp"}
    token = step["challenge_token"]
    assert (await c.get(f"{API}/auth/me", headers=bearer(token))).status_code == 401
    r = await c.post(f"{API}/auth/mfa/setup/totp/start", json={"challenge_token": token})
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    r = await c.post(f"{API}/auth/mfa/setup/totp/confirm", json={"challenge_token": token, "code": code_now(secret)})
    assert r.status_code == 200, r.text
    assert len(r.json()["recovery_codes"]) == 10 and r.json()["access_token"]
    me = await c.get(f"{API}/auth/me", headers=bearer(r.json()["access_token"]))
    assert me.status_code == 200 and me.json()["id"] == uid
    # an MFA challenge token is no enrolment token
    step = await password_step(c, EMAIL)
    assert step["mfa_required"] is True
    r = await c.post(f"{API}/auth/mfa/setup/totp/start", json={"challenge_token": step["challenge_token"]})
    assert r.status_code == 401
    # required by policy: the person cannot turn it off
    r = await c.post(f"{API}/auth/mfa/disable", json={"password": PASSWORD, "code": code_now(secret, 1)}, headers=headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "mfa_required_by_policy"


async def test_disable_refused_while_the_policy_requires_it(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    secret, codes = await enrol_totp(c, headers)
    await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"])
    r = await c.post(f"{API}/auth/mfa/disable", json={"password": PASSWORD, "code": codes[0]}, headers=headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "mfa_required_by_policy"


# --------------------------------------------------------------------------------------------------
# SSO accounts
# --------------------------------------------------------------------------------------------------


async def test_sso_only_account_is_not_offered_local_2fa(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await set_user(uid, auth_source="oidc")
    status = (await c.get(f"{API}/auth/mfa", headers=headers)).json()
    assert status["available"] is False and status["reason"] == "sso_account"
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sso_account"
    r = await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sso_account"


# --------------------------------------------------------------------------------------------------
# rate limits (security_http pattern)
# --------------------------------------------------------------------------------------------------


def test_rate_limit_rules_cover_the_new_unauthenticated_routes() -> None:
    names = {r.name: r for r in LIMITS.rules}
    for name in ("mfa_verify", "passkey_sign_in", "mfa_setup"):
        assert name in names, name
    assert names["mfa_verify"].matches("POST", "/auth/mfa/verify")
    assert names["mfa_verify"].matches("POST", "/auth/mfa/passkey/verify")
    assert names["passkey_sign_in"].matches("POST", "/auth/passkey/options")
    assert names["passkey_sign_in"].matches("POST", "/auth/passkey/verify")
    assert names["mfa_setup"].matches("POST", "/auth/mfa/setup/totp/confirm")


async def test_verify_is_rate_limited_per_address(setup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core import security_http

    c, _admin, _uid, headers = setup
    monkeypatch.setattr(security_http.LIMITS, "enforce_in_tests", True)
    monkeypatch.setattr(security_http, "is_proxy_hop", lambda _a: False)
    security_http.LIMITS.reset()
    try:
        statuses = []
        for _ in range(31):
            r = await c.post(f"{API}/auth/mfa/verify", json={"challenge_token": "x", "method": "totp", "code": "1"})
            statuses.append(r.status_code)
        assert statuses[-1] == 429 and 429 not in statuses[:30]
    finally:
        security_http.LIMITS.reset()
