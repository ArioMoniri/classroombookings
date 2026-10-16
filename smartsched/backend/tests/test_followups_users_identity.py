"""Backend follow-ups 2026-10-16 item 5: a server-side identity filter on the user lists (identity frontend ask), so
Admin › Kullanıcılar pages on the server instead of filtering one 500-row page in the browser.

``identity`` = ``invited`` (an open or expired Microsoft invite, the "Davet bekliyor" chip), ``self_signup`` (the
account was created by a first Microsoft sign-in; ``self_signup_days`` narrows it to the "Kendi kaydı" chip's last
N days), ``sso`` (signs in with Microsoft, or is invited to), ``binding`` (local account bound on its next Microsoft
sign-in), ``local`` (password only) and ``ldap``; several values are OR-ed (``identity=invited,binding``). The
method values follow the Users screen's ``methodView`` (components/admin/users-admin-identity-model.ts).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.db import get_session_factory
from app.models import User
from app.models.base import utcnow
from app.models.sso import SsoInvite, UserIdentity
from httpx import AsyncClient

from tests.api_fixtures import login
from tests.crbs_support import make_user

API = "/api/v1"


async def _people(client: AsyncClient, h: dict[str, str]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for key in ("local", "invited", "expired", "self", "old_self", "bound", "ldap", "binding"):
        ids[key], _ = await make_user(client, h, f"{key}@uni.edu.tr", role="TEACHER")
    now = utcnow()
    async with get_session_factory()() as s:

        def invite(uid: int, kind: str, expires: Any) -> SsoInvite:
            return SsoInvite(
                provider="entra",
                user_id=uid,
                email=f"u{uid}@uni.edu.tr",
                kind=kind,
                token_hash=f"{uid:064d}",
                token_enc="x",
                expires_at=expires,
            )

        def ident(uid: int, origin: str, created: Any) -> UserIdentity:
            return UserIdentity(
                user_id=uid,
                provider="entra",
                issuer="https://login.microsoftonline.com/t/v2.0",
                tenant_id="00000000-0000-0000-0000-000000000001",
                subject=f"sub-{uid}",
                origin=origin,
                created_at=created,
            )

        s.add_all(
            [
                invite(ids["invited"], "invite", now + timedelta(days=20)),
                invite(ids["expired"], "invite", now - timedelta(days=1)),
                invite(ids["binding"], "bind", now + timedelta(days=5)),
                ident(ids["self"], "provision", now - timedelta(days=2)),
                ident(ids["old_self"], "provision", now - timedelta(days=40)),
                ident(ids["bound"], "bind", now - timedelta(days=3)),
            ]
        )
        u = await s.get(User, ids["ldap"])
        assert u is not None
        u.auth_source, u.password_hash = "ldap", None
        await s.commit()
    return ids


async def _search(client: AsyncClient, h: dict[str, str], **q: Any) -> dict[str, Any]:
    r = await client.get(f"{API}/users/search", params=q, headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_identity_filter_pages_on_the_server(client: AsyncClient) -> None:
    h = await login(client)
    ids = await _people(client, h)
    admin_id = next(
        u["id"] for u in (await client.get(f"{API}/users", headers=h)).json() if u["email"] == "admin@example.com"
    )

    def got(page: dict[str, Any]) -> set[int]:
        return {int(u["id"]) for u in page["items"]}

    inv = await _search(client, h, identity="invited")
    assert got(inv) == {ids["invited"], ids["expired"]} and inv["total"] == 2
    assert got(await _search(client, h, identity="self_signup")) == {ids["self"], ids["old_self"]}
    assert got(await _search(client, h, identity="self_signup", self_signup_days=7)) == {ids["self"]}
    sso = await _search(client, h, identity="sso")
    assert got(sso) == {ids["invited"], ids["expired"], ids["self"], ids["old_self"], ids["bound"]}
    assert got(await _search(client, h, identity="binding")) == {ids["binding"]}
    assert got(await _search(client, h, identity="ldap")) == {ids["ldap"]}
    assert got(await _search(client, h, identity="local")) == {ids["local"], admin_id}
    assert got(await _search(client, h, identity="invited,binding")) == {ids["invited"], ids["expired"], ids["binding"]}
    # paging and the other filters stay on the server: total counts the filtered set, the page slices it
    p1 = await _search(client, h, identity="sso", limit=2, offset=0, sort="username")
    p2 = await _search(client, h, identity="sso", limit=2, offset=2, sort="username")
    p3 = await _search(client, h, identity="sso", limit=2, offset=4, sort="username")
    assert p1["total"] == p2["total"] == p3["total"] == 5
    assert len(p1["items"]) == len(p2["items"]) == 2 and len(p3["items"]) == 1
    assert got(p1) | got(p2) | got(p3) == got(sso) and not got(p1) & got(p2)
    assert got(await _search(client, h, identity="sso", q="self")) == {ids["self"], ids["old_self"]}
    # the plain list takes the same filter (the list stays a list)
    r = await client.get(f"{API}/users", params={"identity": "invited"}, headers=h)
    assert r.status_code == 200 and {u["id"] for u in r.json()} == {ids["invited"], ids["expired"]}
    # unknown values are refused in both languages
    r = await client.get(f"{API}/users/search", params={"identity": "facebook"}, headers=h)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "unknown_identity" and detail["message_tr"] and "facebook" in detail["message"]
    # a teacher cannot list users at all
    _tid, teacher = await make_user(client, h, "ogretmen@uni.edu.tr", role="TEACHER")
    assert (await client.get(f"{API}/users/search", params={"identity": "sso"}, headers=teacher)).status_code == 403
