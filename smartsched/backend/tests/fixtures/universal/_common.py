"""Shared helpers for the universal-council fixture builders.

Every builder reads one of the six *real* workbooks in ``tests/fixtures`` (or the real room master CSV)
and writes the same records in another shape or language. Nothing is invented: rows are copied, and
only headers and enumerated words (days, delivery modes) are translated with the fixed tables below.

Run from ``smartsched/backend``::

    python tests/fixtures/universal/build_all.py
"""

from __future__ import annotations

import sys
import warnings
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
BACKEND = FIXTURES.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

BAHAR_LIST = FIXTURES / "bahar_derslik_planlama_listesi_v5.xlsx"
GUZ_LIST = FIXTURES / "guz_derslik_planlama_2026_2027_v2.xlsx"
EXAM_LIST = FIXTURES / "final_planlama_listesi_2026_v2.xlsx"
BAHAR_GRID = FIXTURES / "bahar_derslikler_takvimi_2026.xlsx"
FINAL_GRID = FIXTURES / "final_derslikler_takvimi_2026_v2.xlsx"
ROOM_MASTER = FIXTURES / "room_master.csv"

#: Turkish -> English day names (casefolded keys).
DAYS_EN = {
    "pazartesi": "Monday",
    "salı": "Tuesday",
    "çarşamba": "Wednesday",
    "perşembe": "Thursday",
    "cuma": "Friday",
    "cumartesi": "Saturday",
    "pazar": "Sunday",
}

#: Turkish -> English delivery modes (casefolded keys); other values are kept as written.
MODES_EN = {
    "yüz yüze": "Face to face",
    "online": "Online",
    "çevrimiçi": "Online",
    "hibrit": "Hybrid",
    "hastane": "Hospital",
    "derslik": "Classroom",
    "uzem": "Distance education",
    "asenkron": "Asynchronous",
}


def tr_fold(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").casefold().strip()


def cell_text(v: Any) -> str:
    """Workbook value -> the text a person would type into a CSV / PDF."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        if (v.hour, v.minute) == (0, 0):
            return v.strftime("%Y-%m-%d")
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace("\xa0", " ").strip()


def translate_days(text: str) -> str:
    """Replace every Turkish day name in ``text`` by its English name (longest names first)."""
    out = text
    low = tr_fold(out)
    for tr in sorted(DAYS_EN, key=len, reverse=True):
        idx = low.find(tr)
        while idx >= 0:
            out = out[:idx] + DAYS_EN[tr] + out[idx + len(tr) :]
            low = tr_fold(out)
            idx = low.find(tr, idx + len(DAYS_EN[tr]))
    return out


def translate_mode(text: str) -> str:
    return MODES_EN.get(tr_fold(text), text)
