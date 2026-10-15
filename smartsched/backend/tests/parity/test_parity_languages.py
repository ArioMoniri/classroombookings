"""CRBS parity — languages (ROADMAP Phase 18 part 2, inventory row P18-LANG: a deliberate difference).

CRBS ships ``application/language/<language>/*.php`` for Czech, Danish, Dutch, English, Finnish, French, German,
Italian, Portuguese, Portuguese-Brazilian, Spanish, Swedish and Welsh. SmartSched still imports them with
``tools/crbs_lang_import.py`` (a PHP tokenizer, PHP is never executed), but since the product-owner decision of
2026-10-15 it **offers only Turkish and English**, the two fully translated languages (the 12 others had about 36
of 2,743 strings). New writes accept only ``tr`` / ``en``; a stored legacy code (``de``) is kept and shown in
English, and a CRBS legacy import keeps known codes and maps unknown ones to ``en``.

Real data: the Bahar 2026 booking environment (``tests/crbs_env``: A 101, the 18 university periods, clock
Monday 16 Feb 2026 08:00); Turkish user names."""

from __future__ import annotations

import csv
import io
from datetime import date, time

import pytest
from app.services import bookings_i18n as i18n
from app.services.bookings_export import CSV_COLUMNS
from tools import crbs_lang_import as imp

#: every known code: Turkish, English (offered) and the 12 other CRBS languages (legacy, read and kept)
ALL = ["tr", "en", "cs", "cy", "da", "de", "es", "fi", "fr", "it", "nl", "pt", "pt-br", "sv"]
CRBS_FOLDERS = {
    "cs": "czech",
    "cy": "welsh",
    "da": "danish",
    "de": "german",
    "es": "spanish",
    "fi": "finnish",
    "fr": "french",
    "it": "italian",
    "nl": "dutch",
    "pt": "portuguese",
    "pt-br": "portuguese-brazilian",
    "sv": "swedish",
}


@pytest.mark.parity("P18-LANG")
def test_crbs_language_files_are_parsed_without_executing_php():
    """The tokenizer reads both CRBS file styles and never evaluates code."""
    php = r"""<?php
    defined('BASEPATH') OR exit('No direct script access allowed');
    // $lang['commented'] = 'no';
    /* $lang['block'] = 'no'; */
    # $lang['hash'] = 'no';
    $lang['cal_monday'] = 'Montag';
    $lang["cal_friday"]	= "Freitag";
    $lang['quote'] = 'it\'s a \\ test';
    $lang['dq'] = "Zeile\teins \"zwei\"";
    $lang['concat'] = 'Seite ' . "1";
    $lang['var'] = "Hallo $name";
    $lang['call'] = system('rm -rf /');
    $lang['cal_monday'] = 'Montag (2)';
    $lang = [
        'permission.x' => 'Rechte', // trailing comment
        'permission.y' => "Rollen",
    ];
    """
    got = imp.parse_php_lang(php)
    assert got["cal_friday"] == "Freitag"
    assert got["cal_monday"] == "Montag (2)"  # the later assignment wins, as in PHP
    assert got["quote"] == "it's a \\ test"
    assert got["dq"] == 'Zeile\teins "zwei"'
    assert got["concat"] == "Seite 1"
    assert got["permission.x"] == "Rechte" and got["permission.y"] == "Rollen"
    for key in ("commented", "block", "hash", "var", "call"):
        assert key not in got


@pytest.mark.parity("P18-LANG")
def test_only_turkish_and_english_are_offered_and_legacy_codes_read_as_english():
    """Offered = Turkish + English; the 12 CRBS languages stay known (their codes are read and kept, the CRBS day
    and month names stay in the shared data file) but are shown in English and refused for new writes."""
    assert list(i18n.SHIPPED_LANGUAGES) == ["tr", "en"]
    assert list(i18n.KNOWN_LANGUAGES) == ALL and list(i18n.LEGACY_LANGUAGES) == ALL[2:]
    assert {c: i18n.CRBS_LANG_DATA[c]["crbs"] for c in i18n.CRBS_LANGUAGES} == CRBS_FOLDERS
    # every CRBS language keeps 12 + 12 months and 7 + 7 weekdays in the data file (crbs_lang_import --check)
    for code in i18n.CRBS_LANGUAGES:
        for table, n in ((i18n.MONTHS, 12), (i18n.MONTHS_SHORT, 12), (i18n.WEEKDAYS, 7), (i18n.WEEKDAYS_SHORT, 7)):
            assert len(set(table[code])) == n, (code, table[code])
    # reading: codes in any spelling, CRBS folder names too
    assert [i18n.normalize_language(x) for x in ("DE", "pt_BR", "pt-BR", "german", "Portuguese-Brazilian")] == [
        "de",
        "pt-br",
        "pt-br",
        "de",
        "pt-br",
    ]
    assert i18n.normalize_language("xx") is None and i18n.normalize_language("") is None
    # writing: Turkish or English only
    assert [i18n.offered_language(x) for x in ("TR", "english", "en", "de", "german", "xx", None)] == [
        "tr",
        "en",
        "en",
        None,
        None,
        None,
        None,
    ]
    # showing: a legacy (or unknown) stored code is English, nothing stored is the default
    assert [i18n.display_language(x) for x in ("tr", "EN", "de", "pt-br", "xx", "", None)] == [
        "tr",
        "en",
        "en",
        "en",
        "en",
        "tr",
        "tr",
    ]
    assert i18n.effective_languages(["tr", "de", "fr"]) == ["tr", "en"]
    assert i18n.effective_languages(["de"]) == ["en"] and i18n.effective_languages([]) == ["tr", "en"]
    # a CRBS legacy import keeps known codes (nothing is lost) and maps unknown ones to English
    assert [i18n.import_language(x) for x in ("german", "DE", "english", "tr", "klingon", "", None)] == [
        "de",
        "de",
        "en",
        "tr",
        "en",
        None,
        None,
    ]
    # dates of a legacy-language user are English (shown English), the Turkish ones Turkish
    monday = date(2026, 2, 16)
    assert i18n.format_pattern(monday, "EEEE d MMMM yyyy", "de") == "Monday 16 February 2026"
    assert i18n.format_pattern(monday, "EEEE d MMMM yyyy", "tr") == "Pazartesi 16 Şubat 2026"
    assert i18n.format_pattern(time(9, 5), "HH:mm", "fi") == "09:05"


async def _store_legacy(
    *,
    languages: list[str] | None = None,
    default: str | None = None,
    user_email: str | None = None,
    user_lang: str | None = None,
) -> None:
    """Write legacy values straight into the database, as an older SmartSched or a CRBS import left them."""
    from app.core import db as dbmod
    from app.models import User
    from app.services.bookings_settings import set_group
    from sqlalchemy import select

    async with dbmod.get_session_factory()() as s:
        values: dict[str, object] = {}
        if languages is not None:
            values["languages"] = languages
        if default is not None:
            values["default_language"] = default
        if values:
            await set_group(s, "org", values)
        if user_email is not None:
            u = (await s.execute(select(User).where(User.email == user_email))).scalar_one()
            u.language = user_lang
        await s.commit()


@pytest.mark.parity("P18-LANG")
async def test_new_writes_accept_only_tr_and_en_and_stored_legacy_values_are_kept(env):
    """Org settings, the profile and translation overrides refuse ``de``; an org whose stored languages and
    default are legacy codes keeps them in ``/org/settings`` and is served Turkish / English by ``/org/i18n``."""
    c = env.client
    for body in ({"languages": ["tr", "de"]}, {"languages": ["fr"]}, {"default_language": "DE"}):
        bad = await c.put("/api/v1/org/settings", json=body, headers=env.admin)
        assert bad.status_code == 422, (body, bad.text)
    for lang in ("de", "pt-br", "klingon"):
        bad = await c.put("/api/v1/auth/profile", json={"language": lang}, headers=env.admin)
        assert bad.status_code == 422, (lang, bad.text)
    bad = await c.put(
        "/api/v1/org/translations", json=[{"language": "de", "set": "crbs", "key": "a", "text": "b"}], headers=env.admin
    )
    assert bad.status_code == 422
    ok = await c.put(
        "/api/v1/org/settings", json={"languages": ["TR", "English"], "default_language": "en"}, headers=env.admin
    )
    assert ok.status_code == 200, ok.text
    assert (await c.put("/api/v1/auth/profile", json={"language": "EN"}, headers=env.admin)).json()["language"] == "en"

    # a CRBS-era organisation: German enabled and the default
    await _store_legacy(languages=["tr", "de", "fr"], default="de")
    stored = (await c.get("/api/v1/org/settings", headers=env.admin)).json()
    assert stored["languages"] == ["tr", "de", "fr"] and stored["default_language"] == "de"  # kept, nothing lost
    bundle = (await c.get("/api/v1/org/i18n")).json()
    assert bundle["language"] == "en" and bundle["default_language"] == "en"
    assert bundle["languages"] == ["tr", "en"] and set(bundle["language_names"]) == {"tr", "en"}
    assert bundle["date_defaults"] == i18n.DEFAULT_PATTERNS["en"]
    asked = (await c.get("/api/v1/org/i18n", params={"language": "de"})).json()
    assert asked["language"] == "en"  # an older client asking for German gets English
    assert (await c.get("/api/v1/org/i18n", params={"language": "xx"})).status_code == 422
    public = (await c.get("/api/v1/org/public")).json()  # the login page
    assert public["languages"] == ["tr", "en"] and public["default_language"] == "en"
    # saving an unrelated setting keeps the stored languages
    assert (await c.put("/api/v1/org/settings", json={"name": "Üniversite"}, headers=env.admin)).status_code == 200
    assert (await c.get("/api/v1/org/settings", headers=env.admin)).json()["languages"] == ["tr", "de", "fr"]
    # replacing the list is the administrator's explicit choice; the legacy default then reads as English
    r = await c.put("/api/v1/org/settings", json={"languages": ["tr", "en"]}, headers=env.admin)
    assert r.status_code == 200, r.text


@pytest.mark.parity("P18-LANG")
async def test_a_user_stored_as_german_keeps_the_code_and_gets_english_emails(env):
    """A user whose stored language is ``de`` (CRBS import) keeps it and receives the English e-mail text with
    English dates; the Turkish teacher keeps Turkish."""
    c = env.client
    await _store_legacy(languages=["tr", "en", "de"])
    r = await c.put(
        "/api/v1/org/settings", json={"pattern_long": "EEEE d MMMM yyyy", "pattern_time": "HH:mm"}, headers=env.admin
    )
    assert r.status_code == 200, r.text
    sent: dict[str, dict[str, str]] = {}
    for lang, email, day in (
        ("de", "dil.almanca@uni.edu.tr", date(2026, 2, 17)),
        ("tr", "dil.turkce@uni.edu.tr", date(2026, 3, 3)),
    ):
        uid, headers = await env.user(email, displayname=f"Öğretmen {lang}")
        if lang == "de":
            await _store_legacy(user_email=email, user_lang="de")
        else:
            assert (await c.put("/api/v1/auth/profile", json={"language": "tr"}, headers=headers)).status_code == 200
        prof = (await c.get("/api/v1/auth/profile", headers=headers)).json()
        assert prof["language"] == lang  # the stored value is kept and returned as is
        booked = await env.book(env.planner, "A101", day, "P1", user_id=uid)
        assert booked.status_code == 201, booked.text
        outbox = (await c.get("/api/v1/booking-admin/outbox", headers=env.admin)).json()
        sent[lang] = next(o for o in outbox if o["kind"] == "booking_created" and o["to_email"] == email)
    assert sent["de"]["subject"] == "A booking was made for you"
    assert "Tuesday 17 February 2026" in sent["de"]["body"] and "A 101" in sent["de"]["body"]
    assert sent["tr"]["subject"] == "Sizin adınıza rezervasyon yapıldı"
    assert "Salı 3 Mart 2026" in sent["tr"]["body"]


@pytest.mark.parity("P18-LANG")
async def test_csv_export_keeps_the_crbs_english_columns_in_every_language(env):
    """CRBS ``export_unbuffered`` writes fixed English column names and MySQL ``DAYNAME()`` weekdays whatever
    the UI language; SmartSched's CSV does the same for a Turkish administrator."""
    c = env.client
    # A 101 has no room group in the import; CRBS leaves such rooms out, the documented switch keeps them
    r = await c.put("/api/v1/org/settings", json={"export_ungrouped_rooms": True}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert (await c.put("/api/v1/auth/profile", json={"language": "tr"}, headers=env.admin)).status_code == 200
    assert (await env.book(env.planner, "A101", date(2026, 2, 17), "P1")).status_code == 201
    r = await c.get("/api/v1/bookings/export.csv", headers=env.admin)
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert any(row[6] == "Tuesday" for row in rows[1:])
