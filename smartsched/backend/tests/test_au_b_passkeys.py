"""AU-07…AU-09: passkeys (WebAuthn, py_webauthn 3.0.1) with a software authenticator (tests/webauthn_soft.py): the
registration ceremony (attestation none, excludeCredentials, origin and RP ID checks), passkeys as the second factor
after the password, passkey-only sign-in when the institution allows it (user verification required), the signature
counter, several passkeys per person (rename, remove with re-authentication), single-use challenges and the RP ID for
real domains and sslip.io (docs/research/2026-10-18-auth-backend.md §3)."""

from __future__ import annotations

from typing import Any

import pytest
from app.services import passkeys

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import API, PASSWORD, audit_rows, bearer, make_user, outbox, password_step, set_policy
from tests.webauthn_soft import SoftAuthenticator

EMAIL = "gozde.ayrancigil@uni.edu.tr"
HOST = "plan.uni.edu.tr"
ORIGIN = f"https://{HOST}"


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    r = await client.put(f"{API}/calendar/admin/settings", json={"public_url": ORIGIN}, headers=admin)
    assert r.status_code == 200, r.text
    uid, headers = await make_user(client, admin, EMAIL, firstname="Gözde", lastname="Ayrancıgil")
    return client, admin, uid, headers


async def _register(c, headers, auth: SoftAuthenticator, name: str = "iPhone", **kw: Any):  # type: ignore[no-untyped-def]
    r = await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 200, r.text
    opts = r.json()
    cred = auth.register(opts["options"], **kw)
    return await c.post(
        f"{API}/auth/passkeys/register/verify",
        json={"challenge_token": opts["challenge_token"], "credential": cred, "name": name},
        headers=headers,
    ), opts


# --------------------------------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------------------------------


async def test_registration_options_use_the_public_host_and_attestation_none(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    r = await c.post(f"{API}/auth/passkeys/register/options", json={"password": "yanlis"}, headers=headers)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_failed"
    r = await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 200, r.text
    pk = r.json()["options"]["publicKey"]
    assert pk["rp"]["id"] == HOST and pk["attestation"] == "none"
    assert pk["authenticatorSelection"]["residentKey"] == "preferred"
    assert pk["authenticatorSelection"]["userVerification"] == "preferred"
    assert {p["alg"] for p in pk["pubKeyCredParams"]} >= {-7, -257}
    assert pk["user"]["name"] == EMAIL and pk["user"]["id"] and pk["excludeCredentials"] == []
    assert len(pk["challenge"]) >= 43  # 256-bit nonce


async def test_register_a_passkey_and_it_is_announced(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    auth = SoftAuthenticator(HOST, ORIGIN, synced=True)
    r, _ = await _register(c, headers, auth, name="iPhone (Ayşe)")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["passkey"]["name"] == "iPhone (Ayşe)" and body["passkey"]["backed_up"] is True
    assert "public_key" not in body["passkey"] and "credential_id" not in body["passkey"]
    assert len(body["recovery_codes"]) == 10  # the first second factor brings recovery codes
    listing = (await c.get(f"{API}/auth/passkeys", headers=headers)).json()
    assert [p["name"] for p in listing] == ["iPhone (Ayşe)"]
    assert set(listing[0]["transports"]) == {"internal", "hybrid"}
    assert len(await outbox("passkey_added", uid)) == 1
    assert len(await audit_rows("auth.passkey_added")) == 1
    # the same authenticator is excluded next time
    r = await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)
    excluded = r.json()["options"]["publicKey"]["excludeCredentials"]
    assert len(excluded) == 1 and excluded[0]["type"] == "public-key"


async def test_registration_from_another_origin_or_rp_is_refused(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    r, _ = await _register(c, headers, SoftAuthenticator(HOST, ORIGIN), origin="https://evil.example")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "passkey_invalid"
    r, _ = await _register(c, headers, SoftAuthenticator(HOST, ORIGIN), rp_id="evil.example")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "passkey_invalid"
    assert (await c.get(f"{API}/auth/passkeys", headers=headers)).json() == []


async def test_registration_challenge_is_single_use(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    auth = SoftAuthenticator(HOST, ORIGIN)
    r, opts = await _register(c, headers, auth)
    assert r.status_code == 201
    other = SoftAuthenticator(HOST, ORIGIN)
    r = await c.post(
        f"{API}/auth/passkeys/register/verify",
        json={"challenge_token": opts["challenge_token"], "credential": other.register(opts["options"]), "name": "x"},
        headers=headers,
    )
    assert r.status_code == 401 and r.json()["detail"]["code"] == "challenge_expired"


async def test_passkeys_switched_off_by_the_institution(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    await set_policy(c, admin, passkeys_enabled=False)
    r = await c.post(f"{API}/auth/passkeys/register/options", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "passkeys_off"


# --------------------------------------------------------------------------------------------------
# second factor
# --------------------------------------------------------------------------------------------------


async def test_passkey_as_second_factor_after_the_password(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, uid, headers = setup
    auth = SoftAuthenticator(HOST, ORIGIN, user_verification=False)  # a security key without a PIN is enough here
    assert (await _register(c, headers, auth, name="YubiKey"))[0].status_code == 201
    step = await password_step(c, EMAIL)
    assert step["mfa_required"] is True and "passkey" in step["mfa_methods"]
    r = await c.post(f"{API}/auth/mfa/passkey/options", json={"challenge_token": step["challenge_token"]})
    assert r.status_code == 200, r.text
    pk = r.json()["options"]["publicKey"]
    assert pk["rpId"] == HOST and len(pk["allowCredentials"]) == 1
    r = await c.post(
        f"{API}/auth/mfa/passkey/verify",
        json={"challenge_token": step["challenge_token"], "credential": auth.assert_(r.json()["options"])},
    )
    assert r.status_code == 200, r.text
    me = await c.get(f"{API}/auth/me", headers=bearer(r.json()["access_token"]))
    assert me.json()["id"] == uid
    listing = (await c.get(f"{API}/auth/passkeys", headers=headers)).json()
    assert listing[0]["last_used_at"]


async def test_assertion_cannot_be_replayed(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    auth = SoftAuthenticator(HOST, ORIGIN, synced=True)
    await _register(c, headers, auth)
    step = await password_step(c, EMAIL)
    opts = (await c.post(f"{API}/auth/mfa/passkey/options", json={"challenge_token": step["challenge_token"]})).json()
    assertion = auth.assert_(opts["options"])
    body = {"challenge_token": step["challenge_token"], "credential": assertion}
    assert (await c.post(f"{API}/auth/mfa/passkey/verify", json=body)).status_code == 200
    r = await c.post(f"{API}/auth/mfa/passkey/verify", json=body)
    assert r.status_code == 401


async def test_signature_counter_must_grow_for_hardware_keys(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    auth = SoftAuthenticator(HOST, ORIGIN, counter=5)
    await _register(c, headers, auth)

    async def attempt(counter: int) -> int:
        step = await password_step(c, EMAIL)
        opts = (
            await c.post(f"{API}/auth/mfa/passkey/options", json={"challenge_token": step["challenge_token"]})
        ).json()
        r = await c.post(
            f"{API}/auth/mfa/passkey/verify",
            json={"challenge_token": step["challenge_token"], "credential": auth.assert_(opts["options"], counter=counter)},
        )
        return r.status_code

    assert await attempt(6) == 200
    assert await attempt(6) == 401  # a cloned key replaying the counter
    assert len(await audit_rows("auth.passkey_counter_error")) == 1
    assert await attempt(9) == 200


async def test_synced_passkeys_with_a_zero_counter_keep_working(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    auth = SoftAuthenticator(HOST, ORIGIN, synced=True, counter=0)
    await _register(c, headers, auth)
    for _ in range(2):
        step = await password_step(c, EMAIL)
        opts = (
            await c.post(f"{API}/auth/mfa/passkey/options", json={"challenge_token": step["challenge_token"]})
        ).json()
        r = await c.post(
            f"{API}/auth/mfa/passkey/verify",
            json={"challenge_token": step["challenge_token"], "credential": auth.assert_(opts["options"], counter=0)},
        )
        assert r.status_code == 200, r.text


async def test_another_persons_passkey_does_not_answer_my_challenge(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    mine = SoftAuthenticator(HOST, ORIGIN)
    await _register(c, headers, mine)
    _bid, bheaders = await make_user(c, admin, "fatih.demir@uni.edu.tr")
    theirs = SoftAuthenticator(HOST, ORIGIN)
    await _register(c, bheaders, theirs)
    step = await password_step(c, EMAIL)
    opts = (await c.post(f"{API}/auth/mfa/passkey/options", json={"challenge_token": step["challenge_token"]})).json()
    r = await c.post(
        f"{API}/auth/mfa/passkey/verify",
        json={"challenge_token": step["challenge_token"], "credential": theirs.assert_(opts["options"])},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------------------------------
# passkey-only sign-in (first factor)
# --------------------------------------------------------------------------------------------------


async def test_passkey_first_factor_is_off_until_the_institution_allows_it(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, _headers = setup
    r = await c.post(f"{API}/auth/passkey/options", json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "passkey_sign_in_off"


async def test_passkey_only_sign_in_with_user_verification(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, uid, headers = setup
    await set_policy(c, admin, passkey_first_factor=True)
    auth = SoftAuthenticator(HOST, ORIGIN, synced=True)
    await _register(c, headers, auth)
    r = await c.post(f"{API}/auth/passkey/options", json={})
    assert r.status_code == 200, r.text
    opts = r.json()
    pk = opts["options"]["publicKey"]
    assert pk["allowCredentials"] == [] and pk["userVerification"] == "required"  # discoverable, names no account
    r = await c.post(
        f"{API}/auth/passkey/verify", json={"challenge_token": opts["challenge_token"], "credential": auth.assert_(opts["options"])}
    )
    assert r.status_code == 200, r.text
    me = await c.get(f"{API}/auth/me", headers=bearer(r.json()["access_token"]))
    assert me.json()["id"] == uid
    assert any((e.after or {}).get("auth_method") == "passkey" for e in await audit_rows("auth.login"))


async def test_passkey_only_sign_in_refuses_without_user_verification(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    await set_policy(c, admin, passkey_first_factor=True)
    auth = SoftAuthenticator(HOST, ORIGIN, user_verification=False)
    await _register(c, headers, auth)
    opts = (await c.post(f"{API}/auth/passkey/options", json={})).json()
    r = await c.post(
        f"{API}/auth/passkey/verify", json={"challenge_token": opts["challenge_token"], "credential": auth.assert_(opts["options"])}
    )
    assert r.status_code == 401


async def test_passkey_only_sign_in_refuses_a_disabled_account(setup) -> None:  # type: ignore[no-untyped-def]
    from tests.au_b_support import set_user

    c, admin, uid, headers = setup
    await set_policy(c, admin, passkey_first_factor=True)
    auth = SoftAuthenticator(HOST, ORIGIN)
    await _register(c, headers, auth)
    await set_user(uid, is_active=False)
    opts = (await c.post(f"{API}/auth/passkey/options", json={})).json()
    r = await c.post(
        f"{API}/auth/passkey/verify", json={"challenge_token": opts["challenge_token"], "credential": auth.assert_(opts["options"])}
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------------------------------
# several passkeys
# --------------------------------------------------------------------------------------------------


async def test_several_passkeys_rename_and_remove_with_password(setup) -> None:  # type: ignore[no-untyped-def]
    c, _admin, _uid, headers = setup
    a, b = SoftAuthenticator(HOST, ORIGIN), SoftAuthenticator(HOST, ORIGIN)
    assert (await _register(c, headers, a, name="iPhone"))[0].status_code == 201
    r, _ = await _register(c, headers, b, name="YubiKey")
    assert r.status_code == 201 and not r.json().get("recovery_codes")
    listing = (await c.get(f"{API}/auth/passkeys", headers=headers)).json()
    assert [p["name"] for p in listing] == ["iPhone", "YubiKey"]
    pid = listing[1]["id"]
    r = await c.patch(f"{API}/auth/passkeys/{pid}", json={"name": "Anahtarlık"}, headers=headers)
    assert r.status_code == 200 and r.json()["name"] == "Anahtarlık"
    r = await c.post(f"{API}/auth/passkeys/{pid}/remove", json={"password": "yanlis"}, headers=headers)
    assert r.status_code == 403
    r = await c.post(f"{API}/auth/passkeys/{pid}/remove", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 204
    assert [p["name"] for p in (await c.get(f"{API}/auth/passkeys", headers=headers)).json()] == ["iPhone"]
    assert len(await audit_rows("auth.passkey_removed")) == 1


async def test_someone_elses_passkey_id_is_not_found(setup) -> None:  # type: ignore[no-untyped-def]
    c, admin, _uid, headers = setup
    await _register(c, headers, SoftAuthenticator(HOST, ORIGIN))
    pid = (await c.get(f"{API}/auth/passkeys", headers=headers)).json()[0]["id"]
    _bid, bheaders = await make_user(c, admin, "fatih.demir@uni.edu.tr")
    r = await c.patch(f"{API}/auth/passkeys/{pid}", json={"name": "x"}, headers=bheaders)
    assert r.status_code == 404


# --------------------------------------------------------------------------------------------------
# relying party
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base", "rp_id", "origin"),
    [
        ("https://plan.uni.edu.tr", "plan.uni.edu.tr", "https://plan.uni.edu.tr"),
        ("https://smartsched.10-0-0-5.sslip.io", "smartsched.10-0-0-5.sslip.io", "https://smartsched.10-0-0-5.sslip.io"),
        ("https://plan.uni.edu.tr:8443/", "plan.uni.edu.tr", "https://plan.uni.edu.tr:8443"),
        ("http://localhost:3000", "localhost", "http://localhost:3000"),
    ],
)
def test_relying_party_from_the_public_url(base: str, rp_id: str, origin: str) -> None:
    rp = passkeys.relying_party_from(base)
    assert rp is not None and rp.rp_id == rp_id and rp.origin == origin


@pytest.mark.parametrize("base", ["", "http://plan.uni.edu.tr", "ftp://x", "https://"])
def test_no_relying_party_without_a_secure_public_url(base: str) -> None:
    assert passkeys.relying_party_from(base) is None
