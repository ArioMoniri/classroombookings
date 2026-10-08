"""The generated language files (P18-LANG): ``tools/crbs_lang_import.py --check`` and the no-invented-text rule.

Outside tests/parity because they skip where the CRBS sources or the frontend are not checked out (a parity test
must never skip); the parity tests themselves are in ``tests/parity/test_parity_languages.py``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services import bookings_i18n as i18n
from tools import crbs_lang_import as imp


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
