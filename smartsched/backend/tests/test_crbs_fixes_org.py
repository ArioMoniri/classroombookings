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
    served = await c.get(url)
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
    served = await c.get(photo)
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
        assert (await c.post("/api/v1/auth/password-reset/request", json={"email": "sifre.unuttum@uni.edu.tr"})).status_code == 202
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
