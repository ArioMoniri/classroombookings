"""AUX-F ask to RF-B (2026-10-18): ``GET /users/search?mfa_state=`` filters by the 2FA state on the server, so the
admin's 2FA filter covers every page (``total`` counts the filtered set). Accounts that sign in only through an
identity provider have no 2FA state here (their MFA is managed at the provider) and are left out of every value.
"""

from __future__ import annotations

from app.importers.normalize import tr_casefold

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import API, enrol_totp, make_user, set_policy, totp_clock  # noqa: F401  (autouse)
from tests.test_au_b_aux_asks import _sso_only_user


async def _search(c, admin, **params):  # type: ignore[no-untyped-def]
    r = await c.get(f"{API}/users/search", params={"limit": 1, **params}, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


async def test_mfa_state_filter_pages_over_every_user_and_skips_idp_only(client) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    admin = await login(client)
    on_uid, on_headers = await make_user(client, admin, "ayse.ozturk@uni.edu.tr")
    off_uid, _ = await make_user(client, admin, "ilgin.isik@uni.edu.tr")
    sso_uid = await _sso_only_user("sso.kisi@uni.edu.tr")
    await enrol_totp(client, on_headers)

    on = await _search(client, admin, mfa_state="on")
    assert on["total"] == 1 and on["items"][0]["id"] == on_uid

    off = await _search(client, admin, mfa_state="off", limit=50)
    ids = {u["id"] for u in off["items"]}
    assert off_uid in ids and on_uid not in ids and sso_uid not in ids
    assert off["total"] == len(ids)  # the admin (no 2FA) is also "off"

    # limit 1: total still counts every match, the second page holds the next one
    page2 = await _search(client, admin, mfa_state="off", limit=1, offset=1)
    assert page2["total"] == off["total"] and len(page2["items"]) == 1

    await set_policy(client, admin, mfa_policy="required_for_roles", mfa_roles=["TEACHER"])
    pending = await _search(client, admin, mfa_state="pending", limit=50)
    assert {u["id"] for u in pending["items"]} == {off_uid}  # the IdP-only teacher is never pending here

    both = await _search(client, admin, mfa_state="ON,\u00a0Pending", limit=50)  # comma list, case / spaces folded
    assert {u["id"] for u in both["items"]} == {on_uid, off_uid}

    for state in ("on", "off", "pending"):
        got = await _search(client, admin, mfa_state=state, limit=50)
        assert sso_uid not in {u["id"] for u in got["items"]}

    r = await client.get(f"{API}/users/search", params={"mfa_state": "maybe"}, headers=admin)
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["code"] == "mfa_state_invalid" and "iki aşamalı" in tr_casefold(body["message_tr"])
