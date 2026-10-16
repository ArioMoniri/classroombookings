"""Round-1 flow loop, lane E (Turkish/English consistency and admin screens; docs/ROADMAP.md "Flow loop tickets —
round 1", ``docs/testing/flows/rounds/round-1-tickets.json``).

* T-R1-30 (R1-M-16, R1-A-10): built-in role names and permission texts have a Turkish and an English form; the
  stored codes and seeded names stay stable. ``/auth/sso/providers`` names the self sign-up role by code and in
  both languages.
* T-R1-35 (R1-M-25, R1-A-29): revoking an invite disables the unused account it created (a new invite re-enables
  it); the invite list never repeats the link; Microsoft sign-in switched off answers ``not_enabled`` without a
  support code.
"""

from __future__ import annotations

from app.core import db as dbmod
from app.models import AuditEvent, Role, User
from app.services import bookings_perms as perms
from httpx import AsyncClient
from sqlalchemy import select

from tests.api_fixtures import login
from tests.test_sso_fake_idp import error_of, query_of, sso  # noqa: F401

API = "/api/v1"


# --------------------------------------------------------------------------------------------- T-R1-30


def test_role_label_localises_shipped_names_only() -> None:
    teacher = Role(code="TEACHER", name="Teacher")
    assert perms.role_label(teacher) == {"tr": "Öğretim elemanı", "en": "Teacher"}
    # the Turkish shipped name (an admin who typed it) and any casing count as shipped
    assert perms.role_label(Role(code="VIEWER", name="İZLEYİCİ")) == {"tr": "İzleyici", "en": "Viewer"}
    assert perms.role_label(Role(code="ADMIN", name="ADMIN"))["tr"] == "Yönetici"
    # an administrator's own name for a built-in role, and every custom role, are kept
    assert perms.role_label(Role(code="TEACHER", name="Akademisyen")) == {"tr": "Akademisyen", "en": "Akademisyen"}
    assert perms.role_label(Role(code=None, name="Kullanıcı yöneticisi"))["en"] == "Kullanıcı yöneticisi"
    assert perms.role_label(None) is None


def test_every_permission_has_a_turkish_text() -> None:
    assert set(perms.PERMISSION_TR) == set(perms.PERMISSION_NAMES)
    for name in perms.PERMISSION_NAMES:
        text = perms.permission_text(name)
        assert text["tr"] and text["en"] and text["tr"] != text["en"], name
    both = perms.permission_list(["setup.users", "approvals.decide"])
    assert both["tr"] == "Rezervasyon taleplerini onaylama ya da reddetme, Kullanıcılar"
    assert "approvals.decide" not in both["tr"]


async def test_permission_catalogue_and_sso_hint_are_bilingual(client: AsyncClient) -> None:
    admin = await login(client)
    cat = (await client.get(f"{API}/permissions", headers=admin)).json()
    items = [p for scope in cat.values() for group in scope.values() for p in group]
    assert items and all(p["description_tr"] for p in items)
    edit = next(p for p in items if p["name"] == "book_single.edit_other_booking")
    assert edit["description"] == "Edit other users' single bookings"  # the stored text is unchanged
    assert edit["description_tr"] == "Tek seferlik: başkasınınkini düzenleme"

    auth = (await client.get(f"{API}/auth/sso/providers")).json()["auth"]
    assert auth["self_signup_role_name"] == "Teacher"  # stored name, unchanged
    assert auth["self_signup_role_code"] == "TEACHER"
    assert auth["self_signup_role_label"] == {"tr": "Öğretim elemanı", "en": "Teacher"}


# --------------------------------------------------------------------------------------------- T-R1-35

INVITES = f"{API}/auth/sso/admin/invites"


async def _user(email: str) -> User:
    async with dbmod.get_session_factory()() as s:
        return (await s.execute(select(User).where(User.email == email))).scalar_one()


async def test_revoked_invite_disables_its_unused_account_and_a_new_invite_reenables_it(sso) -> None:  # noqa: F811
    r = await sso.client.post(INVITES, json={"email": "davet.test@uni.edu.tr", "full_name": "D. T."}, headers=sso.admin)
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["link"]  # shown once, in the answer that created it
    listed = (await sso.client.get(INVITES, headers=sso.admin)).json()
    assert [i["link"] for i in listed] == [None]  # the list never repeats the token
    assert (await sso.client.get(INVITES, headers=sso.admin)).json()[0]["link"] is None

    assert (await sso.client.delete(f"{INVITES}/{inv['id']}", headers=sso.admin)).status_code == 204
    user = await _user("davet.test@uni.edu.tr")
    assert user.is_active is False  # not left 'Aktif' with no way to sign in
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "user.invite_revoked"))).scalar_one()
    assert ev.after == {"account_disabled": True}

    again = await sso.client.post(INVITES, json={"email": "davet.test@uni.edu.tr"}, headers=sso.admin)
    assert again.status_code == 201, again.text
    assert again.json()["user_id"] == user.id and again.json()["link"]
    assert (await _user("davet.test@uni.edu.tr")).is_active is True


async def test_revoking_a_binding_keeps_the_used_account(sso, client: AsyncClient) -> None:  # noqa: F811
    admin = sso.admin
    r = await client.post(
        f"{API}/users",
        json={"email": "yerel.test@uni.edu.tr", "role": "TEACHER", "password": "parola-1234"},
        headers=admin,
    )
    uid = r.json()["id"]
    r = await client.post(f"{API}/auth/sso/admin/users/{uid}/bind", json={}, headers=admin)
    assert r.status_code in (200, 201), r.text
    assert (await client.delete(f"{INVITES}/{r.json()['id']}", headers=admin)).status_code == 204
    assert (await _user("yerel.test@uni.edu.tr")).is_active is True


async def test_sso_switched_off_is_not_a_failure(sso) -> None:  # noqa: F811
    assert (await sso.configure(enabled=False)).status_code == 200
    r = await sso.client.get(f"{API}/auth/sso/entra/start")
    assert r.status_code == 302
    loc = r.headers["location"]
    assert error_of(loc) == "not_enabled" and "ref" not in query_of(loc)
    messages = (await sso.client.get(f"{API}/auth/sso/providers")).json()["messages"]
    assert messages["not_enabled"]["tr"] == "Microsoft ile giriş bu kurumda henüz açık değil."
    assert messages["not_enabled"]["en"]
