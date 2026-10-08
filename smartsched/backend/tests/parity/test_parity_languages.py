"""CRBS parity — the 13 CRBS UI languages plus Turkish (ROADMAP Phase 18 part 2, inventory row P18-LANG).

CRBS ships ``application/language/<language>/*.php`` for Czech, Danish, Dutch, English, Finnish, French, German,
Italian, Portuguese, Portuguese-Brazilian, Spanish, Swedish and Welsh. SmartSched imports them with
``tools/crbs_lang_import.py`` (a PHP tokenizer, PHP is never executed): the frontend message files, the day and
month names and default date patterns the backend shares with the frontend, and the coverage report.

Real data: the Bahar 2026 booking environment (``tests/crbs_env``: A 101, the 18 university periods, clock
Monday 16 Feb 2026 08:00); Turkish user names."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, time
from pathlib import Path

import pytest
from app.services import bookings_i18n as i18n
from app.services.bookings_export import CSV_COLUMNS
from tools import crbs_lang_import as imp

#: the 14 languages: Turkish, English and the 12 other CRBS languages
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
def test_the_14_languages_are_shipped_with_crbs_date_names():
    """Backend list = Turkish + English + the 12 CRBS languages; day and month names are CRBS's own
    (``calendar_lang.php``), the default patterns are CRBS "(Default)" (ICU FULL / MEDIUM / SHORT)."""
    assert list(i18n.SHIPPED_LANGUAGES) == ALL
    assert {c: i18n.CRBS_LANG_DATA[c]["crbs"] for c in i18n.CRBS_LANGUAGES} == CRBS_FOLDERS
    assert i18n.LANGUAGE_NAMES["de"] == "Deutsch" and i18n.LANGUAGE_NAMES["pt-br"] == "Português (Brasil)"
    monday = date(2026, 2, 16)
    assert i18n.format_pattern(monday, "EEEE d MMMM yyyy", "de") == "Montag 16 Februar 2026"
    assert i18n.format_pattern(monday, "EEEE d MMMM yyyy", "fr") == "Lundi 16 Février 2026"
    assert i18n.format_pattern(monday, "EEE d MMM", "cy") == "Llun 16 Chwef"
    assert i18n.format_pattern(monday, i18n.DEFAULT_PATTERNS["de"]["long"], "de") == "Montag, 16. Februar 2026"
    assert i18n.format_pattern(monday, i18n.DEFAULT_PATTERNS["es"]["long"], "es") == "Lunes, 16 de Febrero de 2026"
    assert i18n.format_pattern(time(9, 5), i18n.DEFAULT_PATTERNS["fi"]["time"], "fi") == "9.05"
    # CRBS's Italian file names Saturday "Dom" (Sunday); the import corrects it from its own "Sabato"
    assert i18n.format_pattern(date(2026, 2, 21), "EEE", "it") == "Sab"
    # every CRBS language has 12 + 12 months and 7 + 7 weekdays, all distinct
    for code in i18n.CRBS_LANGUAGES:
        for table, n in ((i18n.MONTHS, 12), (i18n.MONTHS_SHORT, 12), (i18n.WEEKDAYS, 7), (i18n.WEEKDAYS_SHORT, 7)):
            assert len(set(table[code])) == n, (code, table[code])
    # codes in any spelling, CRBS folder names too; anything else is not a language
    assert [i18n.normalize_language(x) for x in ("DE", "pt_BR", "pt-BR", "german", "Portuguese-Brazilian")] == [
        "de",
        "pt-br",
        "pt-br",
        "de",
        "pt-br",
    ]
    assert i18n.normalize_language("xx") is None and i18n.normalize_language("") is None


@pytest.mark.parity("P18-LANG")
async def test_org_enables_every_crbs_language_and_serves_its_bundle(env):
    """CRBS setup/Language: enable any of the languages and pick the default; ``GET /org/i18n`` serves the
    backend strings of each (English per key where CRBS has none) with that language's date defaults."""
    c = env.client
    r = await c.put(
        "/api/v1/org/settings",
        json={"languages": [*ALL[:-2], "pt_BR", "Swedish"], "default_language": "DE"},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    bundle = (await c.get("/api/v1/org/i18n", params={"language": "de"})).json()
    assert bundle["languages"] == ALL and bundle["default_language"] == "de"
    assert bundle["language_names"]["cy"] == "Cymraeg" and bundle["language_names"]["tr"] == "Türkçe"
    assert bundle["date_defaults"] == {"long": "EEEE, d. MMMM yyyy", "weekday": "dd.MM.yyyy", "time": "HH:mm"}
    # CRBS has no German e-mail texts: English per key
    assert bundle["messages"]["email"]["booking_created.subject"] == "A booking was made for you"
    # the API lower-cases the query: pt-BR is pt-br
    br = (await c.get("/api/v1/org/i18n", params={"language": "pt-BR"})).json()
    assert br["language"] == "pt-br" and br["date_defaults"]["long"] == "EEEE, d' de 'MMMM' de 'yyyy"
    for code in ALL:
        assert (await c.get("/api/v1/org/i18n", params={"language": code})).status_code == 200, code
    options = (await c.get("/api/v1/org/date-patterns", params={"language": "fr"}, headers=env.admin)).json()
    assert options["pattern_long"][0]["example"].startswith("Jeudi 16 Avril")  # CRBS "(Default)" in French
    # unknown languages are refused everywhere
    bad = await c.put("/api/v1/org/settings", json={"languages": ["tr", "xx"]}, headers=env.admin)
    assert bad.status_code == 422
    bad = await c.put("/api/v1/org/settings", json={"default_language": "klingon"}, headers=env.admin)
    assert bad.status_code == 422
    bad = await c.put(
        "/api/v1/org/translations", json=[{"language": "xx", "set": "crbs", "key": "a", "text": "b"}], headers=env.admin
    )
    assert bad.status_code == 422


@pytest.mark.parity("P18-LANG")
async def test_emails_follow_the_profile_language_with_crbs_dates_and_english_texts(env):
    """CRBS uses the recipient's profile language: the German teacher gets the English e-mail text (CRBS has no
    German one) with German dates, the French override wins over it, the Turkish teacher keeps Turkish."""
    c = env.client
    await c.put(
        "/api/v1/org/settings",
        json={"languages": ALL, "pattern_long": "EEEE d MMMM yyyy", "pattern_time": "HH:mm"},
        headers=env.admin,
    )
    r = await c.put(
        "/api/v1/org/translations",
        json=[{"language": "FR", "set": "email", "key": "booking_created.subject", "text": "Réservation : {actor}"}],
        headers=env.admin,
    )
    assert r.status_code == 200 and r.json()[0]["language"] == "fr"
    sent: dict[str, dict[str, str]] = {}
    for lang, email, day, period in (
        ("de", "dil.almanca@uni.edu.tr", date(2026, 2, 17), "P1"),
        ("fr", "dil.fransizca@uni.edu.tr", date(2026, 2, 24), "P1"),
        ("tr", "dil.turkce@uni.edu.tr", date(2026, 3, 3), "P1"),
    ):
        uid, headers = await env.user(email, displayname=f"Öğretmen {lang}")
        prof = await c.put("/api/v1/auth/profile", json={"language": lang}, headers=headers)
        assert prof.status_code == 200 and prof.json()["language"] == lang
        booked = await env.book(env.planner, "A101", day, period, user_id=uid)
        assert booked.status_code == 201, booked.text
        outbox = (await c.get("/api/v1/booking-admin/outbox", headers=env.admin)).json()
        sent[lang] = next(o for o in outbox if o["kind"] == "booking_created" and o["to_email"] == email)
    assert sent["de"]["subject"] == "A booking was made for you"
    assert "Dienstag 17 Februar 2026" in sent["de"]["body"] and "A 101" in sent["de"]["body"]
    assert sent["fr"]["subject"].startswith("Réservation : ")
    assert "Mardi 24 Février 2026" in sent["fr"]["body"]
    assert sent["tr"]["subject"] == "Sizin adınıza rezervasyon yapıldı"
    assert "Salı 3 Mart 2026" in sent["tr"]["body"]


@pytest.mark.parity("P18-LANG")
async def test_csv_export_keeps_the_crbs_english_columns_in_every_language(env):
    """CRBS ``export_unbuffered`` writes fixed English column names and MySQL ``DAYNAME()`` weekdays whatever
    the UI language; SmartSched's CSV does the same for a German administrator."""
    c = env.client
    # A 101 has no room group in the import; CRBS leaves such rooms out, the documented switch keeps them
    r = await c.put("/api/v1/org/settings", json={"languages": ALL, "export_ungrouped_rooms": True}, headers=env.admin)
    assert r.status_code == 200, r.text
    assert (await c.put("/api/v1/auth/profile", json={"language": "de"}, headers=env.admin)).status_code == 200
    assert (await env.book(env.planner, "A101", date(2026, 2, 17), "P1")).status_code == 201
    r = await c.get("/api/v1/bookings/export.csv", headers=env.admin)
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert any(row[6] == "Tuesday" for row in rows[1:])


# ------------------------------------------------------------------------------------------- generated files


def test_generated_language_files_are_fresh():
    """``tools/crbs_lang_import.py --check``: the committed catalogues, locale data and report match the CRBS
    files (skipped where the CRBS sources are not checked out)."""
    if not (imp.CRBS / "application" / "language").is_dir() or not imp.MESSAGES.is_dir():
        pytest.skip("crbs-core or the frontend is not checked out")
    res = imp.build()
    for path, text in imp.outputs(res).items():
        assert path.exists(), path
        old = path.read_text(encoding="utf-8")
        if path == imp.REPORT:
            old, text = imp._without_date(old), imp._without_date(text)
        assert old == text, f"{path} is stale: run `python -m tools.crbs_lang_import` in smartsched/backend"


def test_frontend_and_backend_share_one_locale_table():
    if not imp.FRONTEND_DATA.exists():
        pytest.skip("the frontend is not checked out")
    front = json.loads(imp.FRONTEND_DATA.read_text(encoding="utf-8"))
    back = json.loads((Path(i18n.__file__).with_name("crbs_lang_data.json")).read_text(encoding="utf-8"))
    assert front == back


def test_message_files_only_carry_crbs_translations():
    """No invented text: every key of a generated message file is an en.json key whose English text is the
    English text of the CRBS key it came from, and the value is that CRBS translation."""
    if not (imp.CRBS / "application" / "language").is_dir() or not imp.MESSAGES.is_dir():
        pytest.skip("crbs-core or the frontend is not checked out")
    res = imp.build()
    en = imp.flatten(json.loads((imp.MESSAGES / "en.json").read_text(encoding="utf-8")))
    for lang in imp.LANGUAGES:
        shipped = imp.flatten(json.loads((imp.MESSAGES / f"{lang.code}.json").read_text(encoding="utf-8")))
        assert shipped, lang.code
        for key, text in shipped.items():
            crbs_key = res.mapping[key]
            assert imp.norm(res.english[crbs_key]) == imp.norm(en[key]) or key in imp.EXPLICIT
            assert imp.norm(res.sources[lang.code][crbs_key]) == text
        assert shipped["days.1"] == imp.norm(res.sources[lang.code]["cal_monday"])
