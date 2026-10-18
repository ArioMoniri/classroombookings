"""AUX-F asks to AU-B (2026-10-18): the Users list's 2FA tag and filter, the policy screen's counts, "Uygulamayı
değiştir" (a new authenticator app while one is on) and the app's wording "iki aşamalı doğrulama".

* ``GET /auth/sso/admin/user-status`` carries ``mfa_state`` (``on`` | ``off`` | ``pending``; ``null`` for an account
  that signs in only through an identity provider) and ``mfa_grace_until`` per user;
* ``GET/PUT /admin/auth/mfa-policy`` carry ``required_people`` and ``enrolled_people``;
* ``POST /auth/mfa/totp/start`` with the app on starts a change: the old app keeps working until the new one is
  confirmed; confirming replaces it, keeps the recovery codes, is audited and e-mails the person.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.core import db as dbmod
from app.models import User
from app.models.mfa import UserMfa
from app.models.sso import UserIdentity
from app.services import mfa
from app.services.sso import MESSAGES

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import (
    API,
    PASSWORD,
    audit_rows,
    code_now,
    enrol_totp,
    make_user,
    next_code,
    outbox,
    password_step,
    set_policy,
    totp_clock,  # noqa: F401  (autouse fixture)
)

EMAIL = "elif.yildirim@uni.edu.tr"


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    uid, headers = await make_user(client, admin, EMAIL)
    return client, admin, uid, headers


async def _status_map(c, admin) -> dict:  # type: ignore[no-untyped-def,type-arg]
    r = await c.get(f"{API}/auth/sso/admin/user-status", headers=admin)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def _sso_only_user(email: str) -> int:
    async with dbmod.get_session_factory()() as s:
        u = User(email=email, username=email, role="TEACHER", is_active=True, password_hash=None, auth_source="oidc")
        s.add(u)
        await s.flush()
        s.add(UserIdentity(user_id=u.id, provider="entra", issuer="https://login.example", tenant_id="t", subject="s1"))
        await s.commit()
        return int(u.id)


# --------------------------------------------------------------------------------------------------
# 1. users status map
# --------------------------------------------------------------------------------------------------


async def test_status_map_carries_the_2fa_state_and_grace(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    sso_uid = await _sso_only_user("sso.kisi@uni.edu.tr")
    smap = await _status_map(c, admin)
    assert smap[str(uid)]["mfa_state"] == "off" and smap[str(uid)]["mfa_grace_until"] is None
    assert smap[str(sso_uid)]["mfa_state"] is None  # managed at the identity provider: no tag

    await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"], mfa_grace_days=14)
    smap = await _status_map(c, admin)
    # covered, nothing set up, never signed in since: pending, the grace starts at the next sign-in
    assert smap[str(uid)]["mfa_state"] == "pending" and smap[str(uid)]["mfa_grace_until"] is None
    assert smap[str(sso_uid)]["mfa_state"] is None

    out = await password_step(c, EMAIL)  # starts the grace period
    assert out["mfa_setup_required"] is True
    async with dbmod.get_session_factory()() as s:
        row = await s.get(UserMfa, uid)
        assert row is not None and row.required_since is not None
        expected = row.required_since + timedelta(days=14)
    got = (await _status_map(c, admin))[str(uid)]
    assert got["mfa_state"] == "pending" and got["mfa_grace_until"].startswith(expected.isoformat()[:16])

    await enrol_totp(c, headers)
    got = (await _status_map(c, admin))[str(uid)]
    assert got["mfa_state"] == "on" and got["mfa_grace_until"] is None
    assert "secret" not in str(got).lower()


# --------------------------------------------------------------------------------------------------
# 2. policy counts
# --------------------------------------------------------------------------------------------------


async def test_policy_answer_counts_required_and_enrolled_people(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    await make_user(c, admin, "ikinci.hoca@uni.edu.tr")
    await _sso_only_user("sso.hoca@uni.edu.tr")  # not counted: the identity provider handles it
    r = await c.get(f"{API}/admin/auth/mfa-policy", headers=admin)
    assert r.status_code == 200 and r.json()["required_people"] == 0 and r.json()["enrolled_people"] == 0
    out = await set_policy(c, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"])
    assert out["required_people"] == 2 and out["enrolled_people"] == 0
    await enrol_totp(c, headers)
    got = (await c.get(f"{API}/admin/auth/mfa-policy", headers=admin)).json()
    assert got["required_people"] == 2 and got["enrolled_people"] == 1


# --------------------------------------------------------------------------------------------------
# 3. change the authenticator app
# --------------------------------------------------------------------------------------------------


async def _sign_in_with(c, secret: str) -> int:  # type: ignore[no-untyped-def]
    step = await password_step(c, EMAIL)
    assert step["mfa_required"] is True
    r = await c.post(
        f"{API}/auth/mfa/verify",
        json={"challenge_token": step["challenge_token"], "method": "totp", "code": next_code(secret)},
    )
    return int(r.status_code)


async def test_change_app_keeps_the_old_one_until_the_new_one_is_confirmed(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    old, codes = await enrol_totp(c, headers)
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": "yanlis-parola"}, headers=headers)
    assert r.status_code in (401, 403)  # a password that is given must be right
    r = await c.post(f"{API}/auth/mfa/totp/start", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 200, r.text
    new = r.json()["secret"]
    assert new != old and r.json()["replacing"] is True

    assert await _sign_in_with(c, old) == 200  # not confirmed yet: the old app still signs in
    status = (await c.get(f"{API}/auth/mfa", headers=headers)).json()
    assert status["totp"]["enabled"] is True and status["totp"]["change_pending"] is True

    r = await c.post(f"{API}/auth/mfa/totp/confirm", json={"code": code_now(new)}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"enabled": True, "changed": True, "recovery_codes": []}  # the saved codes stay valid
    assert (await c.get(f"{API}/auth/mfa", headers=headers)).json()["recovery_codes"]["remaining"] == len(codes)

    assert await _sign_in_with(c, old) == 401
    assert await _sign_in_with(c, new) == 200
    assert [e.entity_id for e in await audit_rows("auth.mfa_app_changed")] == [str(uid)]
    mails = await outbox("mfa_app_changed", uid)
    assert len(mails) == 1 and "aşamalı" in mails[0].subject
    assert len(await outbox("mfa_enabled", uid)) == 1  # only the first enrolment


async def test_a_wrong_code_for_the_new_app_leaves_the_old_one(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    old, _codes = await enrol_totp(c, headers)
    await c.post(f"{API}/auth/mfa/totp/start", json={"password": PASSWORD}, headers=headers)
    r = await c.post(f"{API}/auth/mfa/totp/confirm", json={"code": code_now(old)}, headers=headers)
    assert r.status_code == 422  # the old app's code does not confirm the new one
    assert await _sign_in_with(c, old) == 200


# --------------------------------------------------------------------------------------------------
# 4. wording
# --------------------------------------------------------------------------------------------------


def test_turkish_wording_is_iki_asamali() -> None:
    tr = MESSAGES["idp_mfa_required"]["tr"]
    assert "iki aşamalı doğrulama" in tr and "adımlı doğrulama istiyor" not in tr
    for err in (mfa._not_enabled(), mfa._sso()):
        assert "adımlı" not in err.tr
    from app.emails.kinds import KINDS
    from app.emails.strings import TR

    for kind in ("mfa_enabled", "mfa_disabled", "mfa_reset_by_admin", "mfa_required", "mfa_app_changed"):
        assert "adımlı" not in KINDS[kind].label_tr
    assert not [k for k, v in TR.items() if "iki adımlı" in str(v).lower()]
