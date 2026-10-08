"""Council test fixtures: the six real workbooks, the real room master, and the files built from them
(``tests/fixtures/universal/build_*.py``); a scripted SDK stand-in at the client boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.ai.conftest import FakeSDK

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
UNIVERSAL = FIXTURES / "universal"

BAHAR_LIST = FIXTURES / "bahar_derslik_planlama_listesi_v5.xlsx"
GUZ_LIST = FIXTURES / "guz_derslik_planlama_2026_2027_v2.xlsx"
EXAM_LIST = FIXTURES / "final_planlama_listesi_2026_v2.xlsx"
BAHAR_GRID = FIXTURES / "bahar_derslikler_takvimi_2026.xlsx"
GUZ_GRID = FIXTURES / "guz_derslikler_takvimi_2026_2027.xlsx"
FINAL_GRID = FIXTURES / "final_derslikler_takvimi_2026_v2.xlsx"
ROOM_MASTER = FIXTURES / "room_master.csv"

EN_CSV = UNIVERSAL / "bahar_requests_en.csv"
EXAM_PDF = UNIVERSAL / "final_exams_sheet.pdf"
MEMO_DOCX = UNIVERSAL / "rules_memo.docx"
TRANSPOSED = UNIVERSAL / "bahar_week1_transposed.xlsx"
SCAN_PNG = UNIVERSAL / "final_exams_page1.png"

REAL_WORKBOOKS = [BAHAR_LIST, GUZ_LIST, EXAM_LIST, BAHAR_GRID, GUZ_GRID, FINAL_GRID]


@pytest.fixture
def fake_sdk(monkeypatch):
    import anthropic

    FakeSDK.instances, FakeSDK.script, FakeSDK.calls = [], [], []
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeSDK)
    return FakeSDK


def gen(path: Path, year: int = 2026) -> tuple[Any, list[Any], list[dict[str, Any]]]:
    """General council path on one file (no fast path, no model): rendered, analyses, records."""
    from app.council.extract import extract
    from app.council.render import render_file
    from app.council.structure import analyze

    rendered = render_file(path.read_bytes(), path.name)
    analyses = analyze(rendered)
    return rendered, analyses, extract(rendered, analyses, year_hint=year)
