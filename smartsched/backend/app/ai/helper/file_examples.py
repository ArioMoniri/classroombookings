"""Header-only template files for the helper file router's "Örnek dosyaları gör" (HB-23b, router spec §6.6).

Each template is generated from the importer's own column definitions, so it can never drift from what the importer
reads: the planning and exam lists from their ``HEADER_SPEC`` through the canonical labels of
:data:`app.importers.detect.COLUMN_LABELS` (each label reads back as its own key), the room master from
``room_master.COLUMNS`` and the users CSV from the Turkish header words of ``bookings_users.HEADER_ALIASES``.
Owner decision (2026-10-18): header rows only, no example rows, so there is no name to mask. Static: no database
read.
"""

from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    kind: str
    format: str  # xlsx | csv
    file_name: str
    #: who may import this kind (any-of); the unknown card lists only these
    perms: tuple[str, ...]
    description: tuple[str, str]


EXAMPLES: dict[str, Example] = {
    "planning_list": Example(
        "planning_list",
        "xlsx",
        "ornek_planlama_listesi.xlsx",
        ("planning.edit",),
        ("Planlama listesi: her ders için bir satır", "Planning list: one row per course"),
    ),
    "exam_list": Example(
        "exam_list",
        "xlsx",
        "ornek_sinav_listesi.xlsx",
        ("planning.edit",),
        ("Sınav listesi: her sınav için bir satır", "Exam list: one row per exam"),
    ),
    "room_master": Example(
        "room_master",
        "csv",
        "ornek_derslik_ana_listesi.csv",
        ("planning.edit", "setup.rooms"),
        ("Derslik ana listesi: her derslik için bir satır", "Room master: one row per room"),
    ),
    "users_csv": Example(
        "users_csv",
        "csv",
        "ornek_kullanici_listesi.csv",
        ("setup.users",),
        ("Kullanıcı listesi: her kişi için bir satır", "User list: one row per person"),
    ),
}
#: the users CSV header, Turkish first; each word is a ``bookings_users.HEADER_ALIASES`` entry
USERS_HEADER = ("Kullanıcı adı", "E-posta", "Ad", "Soyad", "Rol", "Bölüm")


def _xlsx(header: list[str]) -> bytes:
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sayfa1"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def header(kind: str) -> list[str]:
    from app.importers import exam_list, planning_list
    from app.importers.detect import COLUMN_LABELS
    from app.importers.room_master import COLUMNS

    if kind == "planning_list":
        return [COLUMN_LABELS[k][0] for k in planning_list.HEADER_SPEC]
    if kind == "exam_list":
        return [COLUMN_LABELS[k][0] for k in exam_list.HEADER_SPEC]
    if kind == "room_master":
        return list(COLUMNS)
    if kind == "users_csv":
        return list(USERS_HEADER)
    raise KeyError(kind)


def render(kind: str) -> bytes:
    """The template bytes (``KeyError`` for a kind without one)."""
    ex = EXAMPLES[kind]
    cols = header(kind)
    if ex.format == "xlsx":
        return _xlsx(cols)
    sep = ";" if kind == "users_csv" else ","  # Turkish Excel opens ';' files in columns; the room master reads both
    return ("﻿" + sep.join(cols) + "\r\n").encode("utf-8")


def listing() -> list[dict[str, object]]:
    from app.ai.helper.files import KINDS

    return [
        {
            "kind": ex.kind,
            "format": ex.format,
            "file_name": ex.file_name,
            "label": {"tr": KINDS[ex.kind].label[0], "en": KINDS[ex.kind].label[1]},
            "description": {"tr": ex.description[0], "en": ex.description[1]},
            "permission": list(ex.perms),
        }
        for ex in EXAMPLES.values()
    ]


__all__ = ["EXAMPLES", "Example", "header", "listing", "render"]
