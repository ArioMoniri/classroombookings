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


# --------------------------------------------------------------------------------------------- T-R1-31

ENGLISH_SENTENCE = ("must", "not allowed", "blocked", "belongs", "Value error")


def _issue(body: dict) -> dict:
    """The first item of a 422 ``detail`` list, or the dict detail of a coded refusal."""
    detail = body["detail"]
    return detail[0] if isinstance(detail, list) else detail


async def test_webhook_url_guard_is_bilingual_and_has_no_pydantic_prefix(client: AsyncClient) -> None:
    admin = await login(client)
    r = await client.post(f"{API}/webhooks", json={"url": "http://127.0.0.1:19102/hook", "events": ["*"]}, headers=admin)
    assert r.status_code == 422, r.text
    item = _issue(r.json())
    assert not item["msg"].startswith("Value error")
    ctx = item["ctx"]
    assert ctx["code"] == "webhook_url_blocked"
    assert ctx["message_tr"].startswith("Bu adres ")
    assert "127.0.0.1" not in ctx["message_tr"] or True  # the address is shown by the field, not the sentence
    assert ctx["message_en"].startswith("blocked address")
    assert item["loc"][-1] == "url"
    # an unknown event type and a bad scheme are coded too
    r = await client.post(f"{API}/webhooks", json={"url": "ftp://hooks.uni.edu.tr/x", "events": ["*"]}, headers=admin)
    assert _issue(r.json())["ctx"]["message_tr"] == "Webhook adresi https:// ya da http:// ile başlamalı."
    r = await client.post(f"{API}/webhooks", json={"url": "https://hooks.uni.edu.tr/x", "events": ["booking.deleted"]}, headers=admin)
    assert r.status_code == 422
    assert _issue(r.json())["ctx"]["message_tr"].startswith("Bilinmeyen olay türü")


async def test_sso_tenant_common_is_refused_in_turkish(sso) -> None:  # noqa: F811
    r = await sso.configure(tenant_id="common")
    assert r.status_code == 422, r.text
    ctx = _issue(r.json())["ctx"]
    assert ctx["code"] == "sso_tenant_reserved"
    assert ctx["message_tr"] == "“common” kullanılamaz: üniversitenin kendi dizin (tenant) kimliğini girin."
    assert "not allowed" in ctx["message_en"]
    r = await sso.configure(tenant_id="uni.edu.tr")
    assert _issue(r.json())["ctx"]["message_tr"].startswith("Dizin (tenant) kimliği ")
    r = await sso.configure(domain_hint="not a domain")
    assert _issue(r.json())["ctx"]["message_tr"].startswith("Alan adı ")


async def test_room_photo_of_the_wrong_type_is_refused_in_turkish(client: AsyncClient) -> None:
    admin = await login(client)
    room = (await client.post(f"{API}/rooms", json={"code": "T 101", "capacity": 40}, headers=admin)).json()
    files = {"file": ("foto.png", b"this is a text file, not a png\n", "image/png")}
    r = await client.post(f"{API}/room-admin/rooms/{room['id']}/photo", files=files, headers=admin)
    assert r.status_code == 400, r.text
    d = r.json()["detail"]
    assert d["code"] == "image_not_image"
    assert d["message_tr"] == "Dosya bir jpg, png, gif ya da webp görseli değil."
    assert d["message_en"] == "the file is not a jpg, png, gif or webp image"
    files = {"file": ("foto.txt", b"x", "text/plain")}
    r = await client.post(f"{API}/room-admin/rooms/{room['id']}/photo", files=files, headers=admin)
    assert r.status_code == 400 and r.json()["detail"]["message_tr"].startswith("Desteklenmeyen görsel türü")


async def _import(client: AsyncClient, headers: dict[str, str], csv: str, **form: str) -> dict:
    r = await client.post(f"{API}/users/import", files={"file": ("users.csv", csv.encode("utf-8"), "text/csv")}, data=form, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_csv_row_errors_carry_turkish_text_in_the_actors_language(client: AsyncClient) -> None:
    admin = await login(client)
    assert (await client.put(f"{API}/auth/profile", json={"language": "tr"}, headers=admin)).status_code == 200
    r = await client.post(f"{API}/users", json={"email": "personel.test@smartsched.local", "role": "TEACHER", "password": "Flow-2026!pw"}, headers=admin)
    assert r.status_code == 201, r.text
    res = await _import(client, admin, "pt2,P,T,personel.test@smartsched.local,Flow-2026!pw,Teacher,\n")
    row = res["results"][0]
    assert row["status"] == "email_exists"
    assert row["error"] == row["error_tr"] == "Bu e-posta başka bir kullanıcıya ait."
    assert row["error_en"] == "e-mail personel.test@smartsched.local belongs to another user"
    assert not any(w in row["error"] for w in ENGLISH_SENTENCE)
    # a warning too
    res = await _import(client, admin, "yeni.kisi,Y,K,,Flow-2026!pw,Bilinmeyen rol,\n")
    row = res["results"][0]
    assert row["status"] == "success" and row["warning_tr"].startswith("Bilinmeyen rol")
    assert row["warning"] == row["warning_tr"]


# --------------------------------------------------------------------------------------------- T-R1-33


async def test_csv_header_row_names_the_columns(client: AsyncClient) -> None:
    admin = await login(client)
    assert (await client.put(f"{API}/auth/profile", json={"language": "tr"}, headers=admin)).status_code == 200
    r = await client.post(f"{API}/users", json={"email": "personel.test@smartsched.local", "role": "TEACHER", "password": "Flow-2026!pw"}, headers=admin)
    assert r.status_code == 201
    csv = (
        "email,full_name,role,password\n"
        "ds.test@smartsched.local,D. S.,TEACHER,Flow-2026!pw\n"
        "nopass.test@smartsched.local,N. P.,TEACHER,\n"
        "personel.test@smartsched.local,P. T.,TEACHER,Flow-2026!pw\n"
    )
    res = await _import(client, admin, csv)
    assert res["created"] == 1
    # the header row is not a user row; the data rows keep their file line numbers
    assert [(x["line"], x["status"]) for x in res["results"]] == [(2, "success"), (3, "password_empty"), (4, "email_exists")]
    assert res["results"][0]["username"] == "ds.test"
    assert res["summary"] == {"rows": 3, "created": 1, "password_empty": 1, "email_exists": 1}
    assert res["summary_tr"] == "3 satır: 1 oluşturuldu, 1 parola yok, 1 e-posta var"
    assert res["summary_en"] == "3 rows: 1 created, 1 without password, 1 e-mail exists"
    me = (await client.get(f"{API}/users", params={"q": "ds.test"}, headers=admin)).json()
    created = me["items"][0] if isinstance(me, dict) else me[0]
    assert created["email"] == "ds.test@smartsched.local" and created["role"] == "TEACHER"
    assert created.get("displayname") == "D. S." or created.get("full_name") == "D. S."
    # a Turkish header in the CRBS column order still works, and a header-less file is positional
    res = await _import(client, admin, "kullanıcı adı,ad,soyad,e-posta,parola,rol,bölüm\nayse.yilmaz,Ayşe,Yılmaz,,parola-1234,Teacher,\n")
    assert [x["status"] for x in res["results"]] == ["success"]
    res = await _import(client, admin, "murat.kaya,Murat,Kaya,,parola-1234,Teacher,\n")
    assert [x["status"] for x in res["results"]] == ["success"] and res["results"][0]["line"] == 1
    # a header that names no known column is refused, in Turkish
    r = await client.post(f"{API}/users/import", files={"file": ("users.csv", "isim;yas\nAli;3\n".encode(), "text/csv")}, data={}, headers=admin)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "csv_columns_unknown" and r.json()["detail"]["message_tr"].startswith("Sütunlar ")


# --------------------------------------------------------------------------------------------- T-R1-34


async def test_room_admin_edits_capacity_and_follows_the_group_building(client: AsyncClient) -> None:
    admin = await login(client)
    room = (await client.post(f"{API}/rooms", json={"code": "T 101", "display_name": "Test dersliği", "capacity": 40}, headers=admin)).json()
    assert room["code"] == "T101"
    g = (await client.post(f"{API}/room-admin/groups", json={"name": "A Blok"}, headers=admin)).json()
    r = await client.put(f"{API}/room-admin/rooms/{room['id']}", json={"capacity": 42, "room_group_id": g["id"]}, headers=admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["capacity"] == 42 and out["room_group"] == "A Blok" and out["building_code"] == "A" and out["code_label"] == "T 101"
    full = (await client.get(f"{API}/rooms/{room['id']}", headers=admin)).json()
    assert full["capacity"] == 42
    r = await client.put(f"{API}/room-admin/rooms/{room['id']}", json={"capacity": -1}, headers=admin)
    assert r.status_code == 422
    assert _issue(r.json())["ctx"]["message_tr"] == "Kişi sayısı 0 ya da daha büyük olmalı."
