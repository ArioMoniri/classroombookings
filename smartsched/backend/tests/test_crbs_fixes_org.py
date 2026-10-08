"""CRBS parity audit 2026-10-08 — organisation side: B2 (logo / photo XSS), B8 (settings validation),
B10 (reset throttling), B12 (changelog seen), MISSING 2 (translations + date patterns applied), MISSING 5
(grid_highlight) and the org settings that switch the deliberate differences.

Real fixture data: the Bahar 2026 import (``tests/crbs_env``), A 101 / A 103 and Turkish text."""

from __future__ import annotations

import io
from datetime import date

import pytest
from PIL import Image

from tests.crbs_env import env  # noqa: F401
from tests.test_crbs_admin import empty_client  # noqa: F401

MON = date(2026, 2, 16)

#: every new switch, with the CRBS (behaviour) or safer (security) default
NEW_SETTINGS = {
    "grid_highlight": False,
    "enforce_max_active_on_create": False,
    "recur_max_counts_replacements": False,
    "maintenance_gates_lists": False,
    "manual_current_term": False,
    "export_ungrouped_rooms": False,
    "recurring_department_needs_set_department": False,
    "ignore_unauthorised_user_department": False,
    "cancel_all_includes_past": False,
    "term_date_change": "cancel",
}


async def _serve(url: str):  # type: ignore[no-untyped-def]
    """GET a public upload: mounts are fixed when the app is created, so build one on the test upload dir."""
    from app.main import create_app
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        return await c.get(url)


def _png(w: int = 40, h: int = 20, colour: str = "red") -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(b, "PNG")
    return b.getvalue()


async def test_every_new_setting_has_its_default_and_round_trips(env):  # noqa: F811
    c = env.client
    got = (await c.get("/api/v1/org/settings", headers=env.admin)).json()
    for key, default in NEW_SETTINGS.items():
        assert got[key] == default, key
    flipped = {k: ("confirm" if isinstance(v, str) else not v) for k, v in NEW_SETTINGS.items()}
    r = await c.put("/api/v1/org/settings", json=flipped, headers=env.admin)
    assert r.status_code == 200, r.text
    got = (await c.get("/api/v1/org/settings", headers=env.admin)).json()
    assert {k: got[k] for k in NEW_SETTINGS} == flipped
    bad = await c.put("/api/v1/org/settings", json={"term_date_change": "delete"}, headers=env.admin)
    assert bad.status_code == 422
    # the frontend agent's switch is still there
    assert "show_ungrouped_rooms" in got
    # LDAP certificates are checked unless an admin switches it off (CRBS installer default was 1)
    assert (await c.get("/api/v1/org/auth/ldap", headers=env.admin)).json()["ignore_cert"] is False


async def test_b2_logo_is_reencoded_and_svg_is_refused(env):  # noqa: F811
    c = env.client
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.cookie)</script></svg>'
    r = await c.post("/api/v1/org/logo", files={"file": ("logo.svg", svg, "image/svg+xml")}, headers=env.admin)
    assert r.status_code == 400, r.text
    # an HTML polyglot named .png is not an image
    r = await c.post(
        "/api/v1/org/logo",
        files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n<script>alert(1)</script>", "image/png")},
        headers=env.admin,
    )
    assert r.status_code == 400
    # a real but huge PNG is accepted and scaled to 1600 px; trailing script bytes do not survive
    big = _png(3200, 800) + b"<script>alert(1)</script>"
    r = await c.post("/api/v1/org/logo", files={"file": ("Üniversite logosu.png", big, "image/png")}, headers=env.admin)
    assert r.status_code == 200, r.text
    url = r.json()["logo_url"]
    assert url == "/uploads/rooms/org-logo.png"
    served = await _serve(url)
    assert served.status_code == 200
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["content-security-policy"] == "default-src 'none'"
    assert b"<script>" not in served.content
    assert Image.open(io.BytesIO(served.content)).size == (1600, 400)
    # webp is not a CRBS logo type
    w = io.BytesIO()
    Image.new("RGB", (8, 8)).save(w, "WEBP")
    r = await c.post("/api/v1/org/logo", files={"file": ("logo.webp", w.getvalue(), "image/webp")}, headers=env.admin)
    assert r.status_code == 400


async def test_b2_room_photo_is_decoded_and_reencoded(env):  # noqa: F811
    c = env.client
    url = f"/api/v1/room-admin/rooms/{env.rooms['A103']}/photo"
    fake = b"\x89PNG\r\n\x1a\n" + b"0" * 32  # magic bytes only: not a decodable image
    assert (await c.post(url, files={"file": ("lab.png", fake, "image/png")}, headers=env.admin)).status_code == 400
    jpg = io.BytesIO()
    Image.new("RGB", (2400, 1800), "white").save(jpg, "JPEG")
    r = await c.post(url, files={"file": ("bilgisayar lab.jpg", jpg.getvalue(), "image/jpeg")}, headers=env.admin)
    assert r.status_code == 200, r.text
    photo = r.json()["photo_url"]
    assert photo == f"/uploads/rooms/{env.rooms['A103']}.jpg"
    served = await _serve(photo)
    assert served.headers["content-security-policy"] == "default-src 'none'"
    assert Image.open(io.BytesIO(served.content)).size == (1600, 1200)


@pytest.mark.parametrize(
    "payload",
    [
        {"website": "javascript:alert(1)"},
        {"website": "data:text/html,<script>alert(1)</script>"},
        {"languages": ["tr", "de"]},
        {"languages": []},
        {"default_language": "fr"},
        {"languages": ["en"], "default_language": "tr"},
        {"pattern_long": "<b>yyyy</b>"},
        {"pattern_time": "EEEE"},
    ],
)
async def test_b8_org_settings_are_validated(env, payload):  # noqa: F811
    r = await env.client.put("/api/v1/org/settings", json=payload, headers=env.admin)
    assert r.status_code == 422, r.text


async def test_b8_valid_values_and_pattern_option_list(env):  # noqa: F811
    c = env.client
    r = await c.put(
        "/api/v1/org/settings",
        json={
            "website": " https://www.üniversite.edu.tr/derslik ",
            "languages": ["tr", "en"],
            "default_language": "en",
            "pattern_long": "EEEE, d MMMM yyyy",
            "pattern_weekday": "",
            "pattern_time": "h:mm a",
        },
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["website"] == "https://www.üniversite.edu.tr/derslik"
    _, teacher = await env.user("desen@uni.edu.tr")
    opts = (await c.get("/api/v1/org/date-patterns", params={"language": "tr"}, headers=teacher)).json()
    examples = {o["pattern"]: o["example"] for o in opts["pattern_long"]}
    year = date.today().year
    weekday = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")[date(year, 4, 16).weekday()]
    assert examples["EEEE d MMMM yyyy"] == f"{weekday} 16 Nisan {year}"
    assert examples["d MMM yyyy"] == f"16 Nis {year}"
    assert examples["dd.MM.yyyy"] == f"16.04.{year}"
    assert {o["pattern"] for o in opts["pattern_time"]} == {"", "HH:mm", "hh:mma", "hh:mm a", "h:mma", "h:mm a"}
    en = (await c.get("/api/v1/org/date-patterns", params={"language": "en"}, headers=teacher)).json()
    assert {o["pattern"]: o["example"] for o in en["pattern_time"]}["h:mm a"] == "9:30 AM"


async def test_missing2_i18n_bundle_merges_overrides(env):  # noqa: F811
    c = env.client
    r = await c.put(
        "/api/v1/org/translations",
        json=[
            {"language": "tr", "set": "bookings", "key": "grid.title", "text": "Derslik\xa0Rezervasyonları"},
            {"language": "tr", "set": "email", "key": "booking_created.subject", "text": "İŞLEM: {actor} sizin için"},
            {"language": "en", "set": "bookings", "key": "grid.title", "text": "Room bookings"},
        ],
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    bundle = (await c.get("/api/v1/org/i18n", params={"language": "tr"})).json()  # public: the login page uses it
    assert bundle["language"] == "tr" and bundle["languages"] == ["tr", "en"]
    assert bundle["messages"]["bookings"]["grid.title"] == "Derslik Rezervasyonları"  # NBSP cleaned
    assert bundle["messages"]["email"]["booking_created.subject"] == "İŞLEM: {actor} sizin için"
    assert bundle["messages"]["email"]["booking_cancelled.subject"] == "Rezervasyonunuz iptal edildi"  # shipped
    assert bundle["date_patterns"]["pattern_long"] == "EEEE d MMMM yyyy"
    en = (await c.get("/api/v1/org/i18n", params={"language": "en"})).json()
    assert en["messages"]["bookings"]["grid.title"] == "Room bookings"
    assert en["messages"]["email"]["booking_created.subject"] == "A booking was made for you"
    assert (await c.get("/api/v1/org/i18n", params={"language": "de"})).status_code == 422
    default = (await c.get("/api/v1/org/i18n")).json()
    assert default["language"] == "tr"


async def test_missing2_emails_use_overrides_and_date_patterns(env):  # noqa: F811
    c = env.client
    await c.put(
        "/api/v1/org/settings", json={"pattern_long": "EEEE d MMMM yyyy", "pattern_time": "HH:mm"}, headers=env.admin
    )
    await c.put(
        "/api/v1/org/translations",
        json=[{"language": "tr", "set": "email", "key": "booking_created.subject", "text": "Rezervasyon: {actor}"}],
        headers=env.admin,
    )
    tid, _ = await env.user("bildirim@uni.edu.tr", displayname="Gül Çelik")
    r = await env.book(env.planner, "A101", date(2026, 2, 17), "P1", user_id=tid)
    assert r.status_code == 201, r.text
    mail = next(
        o
        for o in (await c.get("/api/v1/booking-admin/outbox", headers=env.admin)).json()
        if o["kind"] == "booking_created"
    )
    assert mail["subject"].startswith("Rezervasyon: ")
    assert "Salı 17 Şubat 2026" in mail["body"] and "08:30" in mail["body"] and "A 101" in mail["body"]


async def test_missing5_grid_highlight_reaches_the_grid(env):  # noqa: F811
    c = env.client
    _, teacher = await env.user("vurgu@uni.edu.tr")
    ctx = (await c.get("/api/v1/bookings/context", headers=teacher)).json()
    assert ctx["display"]["grid_highlight"] is False
    await c.put("/api/v1/org/settings", json={"grid_highlight": True}, headers=env.admin)
    ctx = (await c.get("/api/v1/bookings/context", headers=teacher)).json()
    assert ctx["display"]["grid_highlight"] is True


async def test_b10_public_reset_is_throttled_and_keeps_the_earlier_code(env, monkeypatch):  # noqa: F811
    from app.models import PasswordResetToken
    from app.services import bookings_users

    c = env.client
    uid, _ = await env.user("sifre.unuttum@uni.edu.tr")
    await c.put(
        "/api/v1/org/smtp", json={"host": "smtp.uni.edu.tr", "from_address": "noreply@uni.edu.tr"}, headers=env.admin
    )
    sent: list[str] = []

    async def fake_deliver(session, row):  # type: ignore[no-untyped-def]
        sent.append(row.body)
        row.status = "SENT"
        return row

    monkeypatch.setattr(bookings_users, "notify", _notify_with(fake_deliver))
    for _ in range(3):
        r = await c.post("/api/v1/auth/password-reset/request", json={"email": "SIFRE.UNUTTUM@uni.edu.tr"})
        assert r.status_code == 202
    from app.core import db as dbmod
    from sqlalchemy import select

    async with dbmod.get_session_factory()() as s:
        rows = list((await s.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == uid))).scalars())
    # every requested code stays valid until it expires or one is used (a stranger cannot revoke it)
    assert len(rows) == 3 and all(t.used_at is None for t in rows)
    # per-account limit: further requests are accepted (202, nothing revealed) but issue nothing
    for _ in range(5):
        assert (
            await c.post("/api/v1/auth/password-reset/request", json={"email": "sifre.unuttum@uni.edu.tr"})
        ).status_code == 202
    async with dbmod.get_session_factory()() as s:
        n = len(list((await s.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == uid))).scalars()))
    assert n == 3
    # per-address limit: many different accounts from one address -> 429
    codes = [
        (await c.post("/api/v1/auth/password-reset/request", json={"email": f"yok{i}@uni.edu.tr"})).status_code
        for i in range(25)
    ]
    assert 429 in codes


def _notify_with(deliver):  # type: ignore[no-untyped-def]
    from app.models import NotificationOutbox

    async def notify(session, *, kind, to_email, subject, body, user_id=None, booking_id=None):  # type: ignore[no-untyped-def]
        row = NotificationOutbox(kind=kind, to_email=to_email, subject=subject, body=body, user_id=user_id)
        session.add(row)
        await session.flush()
        await deliver(session, row)
        return row

    return notify


async def test_b12_changelog_seen_is_a_version_and_timestamp(env, monkeypatch, tmp_path):  # noqa: F811
    from app.api.v1 import org as org_api

    log = tmp_path / "CHANGELOG.md"
    log.write_text("# Changelog\n\n## [0.3.0] 2026-10-08\n### Added\n- Derslik rezervasyonu\n", encoding="utf-8")
    monkeypatch.setattr(org_api, "CHANGELOG", log)
    c = env.client
    _, teacher = await env.user("yenilik@uni.edu.tr")
    assert (await c.get("/api/v1/org/changelog", headers=teacher)).json()["unread"] is True
    seen = (await c.post("/api/v1/org/changelog/seen", headers=teacher)).json()
    assert seen["version"] == "0.3.0" and "T" in seen["viewed_at"]
    assert (await c.get("/api/v1/org/changelog", headers=teacher)).json()["unread"] is False
    # a second release on the same day is still "new" (a date-only stamp missed it)
    log.write_text(
        "# Changelog\n\n## [0.3.1] 2026-10-08\n### Fixed\n- İptal\n\n## [0.3.0] 2026-10-08\n### Added\n- x\n",
        encoding="utf-8",
    )
    assert (await c.get("/api/v1/org/changelog", headers=teacher)).json()["unread"] is True


async def test_ldap_rejection_does_not_fall_back_to_the_local_copy(env, monkeypatch):  # noqa: F811
    """Deliberate security difference: CRBS (Userauth::log_in) tries the local password after *any* LDAP
    failure; SmartSched only when the directory cannot be reached, or for accounts that are not LDAP ones."""
    from app.services import bookings_ldap

    from tests.test_crbs_users import FakeDirectory

    monkeypatch.setattr(bookings_ldap.ldap3, "Connection", FakeDirectory)
    monkeypatch.setattr(FakeDirectory, "password", "doğru-parola")
    monkeypatch.setattr(FakeDirectory, "down", False)
    c = env.client
    await env.user("yerel.hesap@uni.edu.tr", username="yerel.hesap", password="yerel-parola-1")
    cfg = {
        "enabled": True,
        "server": "ldap.uni.edu.tr",
        "bind_dn_format": "uid=:user,ou=people,dc=uni,dc=edu,dc=tr",
        "base_dn": "ou=people,dc=uni,dc=edu,dc=tr",
        "search_filter": "(uid=:user)",
        "attr_displayname": ":givenName :sn",
    }
    assert (await c.put("/api/v1/org/auth/ldap", json=cfg, headers=env.admin)).status_code == 200
    ok = await c.post("/api/v1/auth/login", json={"username": "ilker.sahin", "password": "doğru-parola"})
    assert ok.status_code == 200, ok.text
    # the directory password changes: the stale local copy no longer opens the account
    monkeypatch.setattr(FakeDirectory, "password", "yeni-dizin-parolası")
    old = await c.post("/api/v1/auth/login", json={"username": "ilker.sahin", "password": "doğru-parola"})
    assert old.status_code == 401
    # ... except while the directory is unreachable (CRBS fallback)
    monkeypatch.setattr(FakeDirectory, "down", True)
    assert (
        await c.post("/api/v1/auth/login", json={"username": "ilker.sahin", "password": "doğru-parola"})
    ).status_code == 200
    monkeypatch.setattr(FakeDirectory, "down", False)
    # local (non-directory) accounts still sign in with their own password
    r = await c.post("/api/v1/auth/login", json={"username": "YEREL.HESAP", "password": "yerel-parola-1"})
    assert r.status_code == 200, r.text


async def test_setup_users_cannot_grant_or_take_over_administrator_without_setup_roles(env):  # noqa: F811
    """Deliberate security difference: CRBS (Users::save) lets anyone holding setup.users give any role,
    Administrator included. SmartSched asks for setup.roles as well before a user management action grants
    -- or takes over the account of -- a role that holds setup.roles (Administrator does)."""
    c = env.client
    roles = {r["code"]: r for r in (await c.get("/api/v1/roles", headers=env.admin)).json()}
    r = await c.post(
        "/api/v1/roles",
        json={"name": "Bölüm Sekreteri", "description": "İİBF", "permissions": ["setup.users", "room.view"]},
        headers=env.admin,
    )
    assert r.status_code == 201, r.text
    _, sekreter = await env.user("sekreter@uni.edu.tr", role=None, role_id=r.json()["id"])
    yetkili = (
        await c.post(
            "/api/v1/roles",
            json={"name": "Rol Yöneticisi", "permissions": ["setup.roles", "room.view"]},
            headers=env.admin,
        )
    ).json()
    admin_id = (await c.get("/api/v1/auth/me", headers=env.admin)).json()["id"]

    # user managers may read roles and permissions (to grey out what they cannot grant) but not change them
    assert (await c.get("/api/v1/roles", headers=sekreter)).status_code == 200
    assert (await c.get("/api/v1/permissions", headers=sekreter)).status_code == 200
    assert (await c.post("/api/v1/roles", json={"name": "x", "permissions": []}, headers=sekreter)).status_code == 403
    # no escalation (user decision 2026-10-08): a role is granted only when the actor holds all its permissions
    izleyici = (
        await c.post(
            "/api/v1/roles", json={"name": "Derslik İzleyici", "permissions": ["room.view"]}, headers=env.admin
        )
    ).json()
    ok = await c.post(
        "/api/v1/users",
        json={"email": "ilker.sahin@uni.edu.tr", "role_id": izleyici["id"], "password": "parola-1234"},
        headers=sekreter,
    )
    assert ok.status_code == 201, ok.text
    teacher_id = ok.json()["id"]
    # Teacher holds booking permissions the secretary lacks (CRBS would allow this grant)
    r = await c.post(
        "/api/v1/users",
        json={"email": "ozan.demir@uni.edu.tr", "role": "TEACHER", "password": "parola-1234"},
        headers=sekreter,
    )
    assert r.status_code == 403, r.text
    assert "booking" in r.json()["detail"] or "book" in r.json()["detail"]
    # ... but not Administrator, nor a role holding setup.roles, on create or on update
    for body in ({"role": "ADMIN"}, {"role_id": roles["ADMIN"]["id"]}, {"role_id": yetkili["id"]}):
        r = await c.post(
            "/api/v1/users",
            json={"email": "ışık.öztürk@uni.edu.tr", "password": "parola-1234", "role": None, **body},
            headers=sekreter,
        )
        assert r.status_code == 403, r.text
        r = await c.put(f"/api/v1/users/{teacher_id}", json=body, headers=sekreter)
        assert r.status_code == 403, r.text
    assert (await c.get(f"/api/v1/users/{teacher_id}", headers=env.admin)).json()["role_id"] == izleyici["id"]
    # nor take the Administrator's account over (password, reset code, e-mail, disable, delete)
    assert (
        await c.post(f"/api/v1/users/{admin_id}/password", json={"password": "ele-gecirme-1"}, headers=sekreter)
    ).status_code == 403
    assert (await c.post(f"/api/v1/users/{admin_id}/reset-token", headers=sekreter)).status_code == 403
    assert (
        await c.put(f"/api/v1/users/{admin_id}", json={"email": "saldirgan@uni.edu.tr"}, headers=sekreter)
    ).status_code == 403
    assert (await c.delete(f"/api/v1/users/{admin_id}", headers=sekreter)).status_code == 403
    # the CSV import refuses those rows (and an Administrator default) but imports the others
    csv = "kullanıcı adı,ad,soyad,e-posta,parola,rol,bölüm\nayşe.yılmaz,Ayşe,Yılmaz,,parola-1234,Derslik İzleyici,\n"
    csv += "İLKNUR.ÇELİK,İlknur,Çelik,,parola-1234,Administrator,\n"
    r = await c.post(
        "/api/v1/users/import", files={"file": ("users.csv", csv.encode("utf-8"), "text/csv")}, headers=sekreter
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["created"] == 1
    assert [x["status"] for x in res["results"]] == ["success", "forbidden"]
    assert "setup.roles" in res["results"][1]["error"]
    # a Teacher row is refused too: it needs booking permissions the secretary does not hold
    r = await c.post(
        "/api/v1/users/import",
        files={"file": ("users.csv", b"zeynep.arslan,Zeynep,Arslan,,parola-1234,Teacher,\n", "text/csv")},
        headers=sekreter,
    )
    assert [x["status"] for x in r.json()["results"]] == ["forbidden"]
    r = await c.post(
        "/api/v1/users/import",
        files={"file": ("users.csv", b"murat.kaya,Murat,Kaya,,parola-1234,,\n", "text/csv")},
        data={"role_id": str(roles["ADMIN"]["id"])},
        headers=sekreter,
    )
    assert r.status_code == 403, r.text
    # an actor holding setup.roles (the Administrator) still may
    r = await c.put(f"/api/v1/users/{teacher_id}", json={"role": "ADMIN"}, headers=env.admin)
    assert r.status_code == 200 and r.json()["role"] == "ADMIN"


async def test_missing6_installer_requirements_step(empty_client, tmp_path, monkeypatch):  # noqa: F811
    """CRBS ``Install::check_requirements``: runtime version, image library (GD), LDAP module (warning only),
    a writable uploads folder and the database -- shown before the first administrator is created, and the
    install refuses to continue while one of them is an error."""
    from app.core.config import get_settings

    from tests.api_fixtures import login

    c = empty_client
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "yüklemeler"))
    r = await c.get("/api/v1/org/setup/requirements")
    assert r.status_code == 200, r.text
    out = r.json()
    req = out["requirements"]
    assert out["setup_required"] is True and out["ok"] is True
    for key in ("python_version", "image_library", "folder_uploads", "database"):
        assert req[key]["status"] == "ok", (key, req[key])
    assert req["ldap_module"]["status"] in ("ok", "warn")
    assert req["database_schema"]["status"] in ("ok", "warn")  # tests build the schema without alembic
    assert all(set(v) == {"status", "message"} for v in req.values())

    # an uploads folder that cannot be created (a file is in the way) blocks the install like CRBS
    blocker = tmp_path / "dosya"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "upload_dir", str(blocker / "uploads"))
    out = (await c.get("/api/v1/org/setup/requirements")).json()
    assert out["ok"] is False and out["requirements"]["folder_uploads"]["status"] == "err"
    body = {"org_name": "Acıbadem Üniversitesi", "admin_email": "kurulum@uni.edu.tr", "admin_password": "kurulum-1234"}
    r = await c.post("/api/v1/org/setup", json=body)
    assert r.status_code == 409 and "folder_uploads" in r.text
    assert (await c.get("/api/v1/org/public")).json()["setup_required"] is True

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "yüklemeler"))
    assert (await c.post("/api/v1/org/setup", json=body)).status_code == 201
    # once installed the report (versions, paths) is for administrators only
    assert (await c.get("/api/v1/org/setup/requirements")).status_code == 401
    admin = await login(c, "kurulum@uni.edu.tr", "kurulum-1234")
    r = await c.get("/api/v1/org/setup/requirements", headers=admin)
    assert r.status_code == 200 and r.json()["setup_required"] is False


async def test_no_escalation_role_editors_cannot_grant_permissions_they_lack(env):  # noqa: F811
    """User decision 2026-10-08 (stricter than CRBS): a role editor (setup.roles) may only put permissions
    they hold into a role, may only edit or delete roles whose permissions they hold, and cannot raise
    their own role."""
    c = env.client
    yonetici = (
        await c.post(
            "/api/v1/roles",
            json={"name": "Rol Yöneticisi (sınırlı)", "permissions": ["setup.roles", "room.view"]},
            headers=env.admin,
        )
    ).json()
    _, rol_yon = await env.user("rol.yonetici@uni.edu.tr", role=None, role_id=yonetici["id"])
    roles = {r["code"]: r for r in (await c.get("/api/v1/roles", headers=rol_yon)).json()}

    # creating a role: only permissions the editor holds
    ok = await c.post("/api/v1/roles", json={"name": "Görüntüleyici", "permissions": ["room.view"]}, headers=rol_yon)
    assert ok.status_code == 201, ok.text
    r = await c.post("/api/v1/roles", json={"name": "Süper", "permissions": ["setup.settings"]}, headers=rol_yon)
    assert r.status_code == 403 and "setup.settings" in r.json()["detail"]
    # raising their own role, or any role, is refused
    r = await c.put(
        f"/api/v1/roles/{yonetici['id']}",
        json={"permissions": ["setup.roles", "room.view", "setup.users"]},
        headers=rol_yon,
    )
    assert r.status_code == 403, r.text
    r = await c.put(f"/api/v1/roles/{ok.json()['id']}", json={"permissions": ["setup.users"]}, headers=rol_yon)
    assert r.status_code == 403, r.text
    # editing or deleting a role whose permissions exceed theirs (Teacher can book) is refused
    assert (
        await c.put(f"/api/v1/roles/{roles['TEACHER']['id']}", json={"name": "Öğretmen"}, headers=rol_yon)
    ).status_code == 403
    assert (await c.delete(f"/api/v1/roles/{roles['TEACHER']['id']}", headers=rol_yon)).status_code == 403
    # within their own permissions everything still works
    r = await c.put(f"/api/v1/roles/{ok.json()['id']}", json={"name": "Derslik Görüntüleyici"}, headers=rol_yon)
    assert r.status_code == 200, r.text
    assert (await c.delete(f"/api/v1/roles/{ok.json()['id']}", headers=rol_yon)).status_code == 204
    # the Administrator holds every permission and is unaffected
    r = await c.put(
        f"/api/v1/roles/{yonetici['id']}",
        json={"permissions": ["setup.roles", "room.view", "setup.users"]},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
