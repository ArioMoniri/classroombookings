"""Round-1 flow loop, lane E (Turkish/English consistency and admin screens; docs/ROADMAP.md "Flow loop tickets —
round 1", ``docs/testing/flows/rounds/round-1-tickets.json``).

* T-R1-30 (R1-M-16, R1-A-10): built-in role names and permission texts have a Turkish and an English form; the
  stored codes and seeded names stay stable. ``/auth/sso/providers`` names the self sign-up role by code and in
  both languages.
"""

from __future__ import annotations

from app.models import Role
from app.services import bookings_perms as perms
from httpx import AsyncClient

from tests.api_fixtures import login

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
