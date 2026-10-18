"""FIX-A F-AUB-1 (e2e results 2026-10-18): "Diğer cihazlardan çıkış yap" must also end a token that was issued before
the click but has not made a request yet (no session row). Every token carries the user's ``sessions_epoch`` at
issue (claim ``se``); the first request of a token whose ``se`` is behind the user's current epoch is refused."""

from __future__ import annotations

import pytest
from app.models.mfa import UserSession
from app.services import sessions
from sqlalchemy import func, select

from tests.api_fixtures import client, login  # noqa: F401
from tests.au_b_support import API, bearer, make_user, password_step

EMAIL = "deniz.arslan@uni.edu.tr"


@pytest.fixture
async def setup(client):  # type: ignore[no-untyped-def]  # noqa: F811
    sessions.forget()
    admin = await login(client)
    uid, headers = await make_user(client, admin, EMAIL)
    return client, uid, headers


async def _sign_in(c) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return bearer((await password_step(c, EMAIL))["access_token"])


async def test_sign_out_others_ends_a_token_that_never_made_a_request(setup) -> None:  # type: ignore[no-untyped-def]
    c, _uid, _headers = setup
    first = await _sign_in(c)
    second = await _sign_in(c)  # issued, never used
    assert (await c.get(f"{API}/auth/me", headers=first)).status_code == 200
    r = await c.post(f"{API}/auth/sessions/revoke-others", headers=first)
    assert r.status_code == 200, r.text
    r = await c.get(f"{API}/auth/me", headers=second)
    assert r.status_code == 401 and r.json()["detail"] == "session revoked"
    sessions.forget()  # another worker, empty cache: still refused, and no row was recorded for it
    assert (await c.get(f"{API}/auth/me", headers=second)).status_code == 401
    assert (await c.get(f"{API}/auth/me", headers=first)).status_code == 200


async def test_the_refused_fresh_token_leaves_no_open_session(setup) -> None:  # type: ignore[no-untyped-def]
    from app.core import db as dbmod

    c, uid, _headers = setup
    first = await _sign_in(c)
    second = await _sign_in(c)
    await c.get(f"{API}/auth/me", headers=first)
    await c.post(f"{API}/auth/sessions/revoke-others", headers=first)
    await c.get(f"{API}/auth/me", headers=second)
    async with dbmod.get_session_factory()() as s:
        n = await s.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.user_id == uid, UserSession.revoked_at.is_(None))
        )
    assert n == 1  # only the first device
    assert [x["current"] for x in (await c.get(f"{API}/auth/sessions", headers=first)).json()] == [True]


async def test_a_sign_in_after_sign_out_others_works(setup) -> None:  # type: ignore[no-untyped-def]
    c, _uid, _headers = setup
    first = await _sign_in(c)
    await c.get(f"{API}/auth/me", headers=first)
    await c.post(f"{API}/auth/sessions/revoke-others", headers=first)
    later = await _sign_in(c)
    assert (await c.get(f"{API}/auth/me", headers=later)).status_code == 200
    assert (await c.get(f"{API}/auth/me", headers=first)).status_code == 200
