"""Helper file router (HB-23b): "drop any file, it says what it is and gives you the next step".

docs/design/v3/helper-file-router.md §4 (classifier), §5 (states), §6 (API, stage, token), §7 (card contract).

**No new detector.** :func:`read_signals` runs the detectors that already exist, in the rlimit child
(:func:`app.core.safe_files.run_isolated`), on the header area only (first 3 sheets, 200 rows):

* the importers' header check :func:`app.importers.detect.detect_kind` (rows 1..3 of sheet 1, tabular formats);
* the council's shape detection :func:`app.council.fastpath.detect_shape` (stricter: the time axis, ≥ 5 rooms);
* the council's structure analyst :func:`app.council.structure.analyze` (kind + confidence per sheet / text units);
* the users CSV header words of :mod:`app.services.bookings_users`;
* two small sniffs: CRBS SQL dumps (``CREATE TABLE`` / ``INSERT INTO`` naming the CRBS tables) and ICS events;
* the term the file names, :func:`app.services.import_term_check.file_term` on the bytes.

:func:`candidates` scores them with the agreement rules of §4.3 (deterministic, unit-tested). The **columns decide
the kind** and the file name only feeds the term guess, so ``final_planlama_listesi`` is an exam list, and a
transposed board that ``detect_kind`` reads as a weekly grid goes to the setup wizard (the weekly-grid importer
cannot read it). No model is called anywhere here: the optional tie-breaker of §4.6 is off in v1.

**Evidence is name-free:** canonical column labels (:data:`app.importers.detect.COLUMN_LABELS`, :data:`FIELD_LABELS`,
:data:`USER_LABELS`, the room master's own column names), counts, ICS first / last day and CRBS table names; never a
cell value or the workbook's raw header text (one fixture header names a person). Sheet titles pass
:func:`~app.ai.helper.schema.scrub`, are cut to 40 characters and are dropped when the KVKK name list or the
``ai_personal`` redactor finds a name in them.

**Stage (§6.3):** when a route carries the file, the bytes are encrypted with AES-256-GCM under a random per-stage key
that exists only inside the signed ``upload_token`` (crypto-shredding: the server keeps no key). The token is bound to
the person and their sign-in session, lives 10 minutes and is consumed once (:func:`consume` renames the stage to
``.claimed`` atomically and leaves a ``.used`` tombstone, so a second use answers 410 ``stage_used``). One stage set per
person; :func:`sweep` deletes anything older than 10 minutes. ``HELPER_FILE_STAGE=off`` stages nothing (the browser
sends the File again). Classify writes no database row, no job, no audit row and no plain file.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.helper import cards
from app.ai.helper import schema as s
from app.core.config import get_settings
from app.services.bookings_perms import Access

log = logging.getLogger("smartsched.helper.files")

STAGE_TTL_S = 600
RATE_PER_MINUTE = 20
RATE_PER_DAY = 200
HEAD_ROWS = 200
HEAD_SHEETS = 3
USERS_MAX_BYTES = 5 * 1024 * 1024  # POST /users/import's own cap
_LABEL = b"smartsched/helper/file/v1"
_MAGIC = b"SSHF1"
_EVIDENCE_LABELS = 6
#: formats the importers read through ``workbook_for`` (``detect_kind`` runs on these only)
_IMPORTER_TABULAR = frozenset({"xlsx", "xls", "ods", "csv"})
#: formats a text document comes in (rules memos): a rules text outranks the tables inside it
_DOCUMENTS = frozenset({"docx", "txt", "eml", "pdf"})
#: the import screen reads Excel only (``glass.import.onlyXlsx``); the room master also reads CSV / text
_EXCEL = frozenset({"xlsx"})
_ROOM_MASTER_FORMATS = frozenset({"xlsx", "csv", "txt"})


def now() -> float:
    """Epoch seconds (one place, so the tests can move the clock)."""
    return time.time()


# ================================================================================================ kinds


@dataclass(frozen=True)
class KindInfo:
    label: tuple[str, str]
    #: in a sentence: "Bu bir {tr}" / "This is {en}"
    phrase: tuple[str, str]
    explain: tuple[str, str]
    hint: tuple[str, str]


KINDS: dict[str, KindInfo] = {
    "planning_list": KindInfo(
        ("Planlama listesi", "Planning list"),
        ("planlama listesi", "a planning list"),
        (
            "Planlama listesi, bölümlerin her dersi için gün, saat, şube, öğretim elemanı ve derslik talebini yazdığı "
            "tablodur. İçe aktarınca önce bir önizleme görürsünüz; hiçbir şey 'Uygula' demeden değişmez.",
            "A planning list is the table where departments write each course's day, time, section, instructor and "
            "room request. Importing shows a preview first; nothing changes until you press Apply.",
        ),
        (
            "Derslerin gün, saat ve derslik talepleri dönemin planına eklenir",
            "Adds each course's day, time and room request to the term's plan",
        ),
    ),
    "exam_list": KindInfo(
        ("Sınav listesi", "Exam list"),
        ("sınav listesi", "an exam list"),
        (
            "Sınav listesi, her dersin sınav tarihini, saatini ve salon talebini gösteren tablodur. İçe aktarınca önce "
            "bir önizleme görürsünüz; hiçbir şey 'Uygula' demeden değişmez.",
            "An exam list is the table with each course's exam date, time and room request. Importing shows a preview "
            "first; nothing changes until you press Apply.",
        ),
        (
            "Sınav tarihleri ve salon talepleri sınav dönemine eklenir",
            "Adds exam dates and room requests to the exam period",
        ),
    ),
    "weekly_grid": KindInfo(
        ("Haftalık derslik takvimi", "Weekly room timetable"),
        ("haftalık derslik takvimi", "a weekly room timetable"),
        (
            "Haftalık derslik takvimi, her hafta için bir sayfada dersliklerin gün ve ders saatine göre doluluğunu "
            "gösterir. İçe aktarınca önce bir önizleme görürsünüz; hiçbir şey 'Uygula' demeden değişmez.",
            "A weekly room timetable shows, one sheet per week, which rooms are taken on which day and period. "
            "Importing shows a preview first; nothing changes until you press Apply.",
        ),
        ("Haftalık derslik doluluğu (pano) yüklenir", "Loads the weekly room occupancy board"),
    ),
    "room_master": KindInfo(
        ("Derslik ana listesi", "Room master"),
        ("derslik ana listesi", "the room master"),
        (
            "Derslik ana listesi, her dersliğin kodunu, kapasitesini, sınav kapasitesini ve özelliklerini tutar. "
            "İçe aktarınca önce bir önizleme görürsünüz.",
            "The room master holds each room's code, capacity, exam capacity and features. Importing shows a preview "
            "first.",
        ),
        ("Derslik kapasiteleri ve özellikleri güncellenir", "Updates room capacities and features"),
    ),
    "users_csv": KindInfo(
        ("Kullanıcı listesi", "User list"),
        ("kullanıcı listesi", "a user list"),
        (
            "Kullanıcı listesi, hesap açılacak kişilerin kullanıcı adını ya da e-postasını ve rolünü taşır. İçe "
            "aktarırken rolü, bölümü ve parolayı siz seçersiniz.",
            "A user list carries the username or e-mail and the role of the people to create accounts for. You choose "
            "the role, department and password when importing.",
        ),
        ("Hesaplar oluşturulur; rol ve parolayı siz seçersiniz", "Creates the accounts; you choose role and password"),
    ),
    "crbs_dump": KindInfo(
        ("classroombookings yedeği", "classroombookings backup"),
        ("classroombookings yedeği", "a classroombookings backup"),
        (
            "Bu, classroombookings veritabanının bir dökümüdür. İçe aktarınca salonlar, ders saatleri, haftalar ve "
            "rezervasyonlar SmartSched'e taşınır.",
            "This is a dump of a classroombookings database. Importing moves its rooms, periods, weeks and bookings "
            "into SmartSched.",
        ),
        ("classroombookings verisi taşınır", "Moves the classroombookings data over"),
    ),
    "intake_json": KindInfo(
        ("SmartSched içe aktarma dosyası", "SmartSched import file"),
        ("SmartSched içe aktarma dosyası", "a SmartSched import file"),
        (
            "Bu dosya SmartSched'in kendi içe aktarma biçimindedir. Kurulum sihirbazı içindeki derslikleri, talepleri "
            "ve çizelgeyi okur ve onayınızı ister.",
            "This file is in SmartSched's own import format. The setup wizard reads its rooms, requests and timetable "
            "and asks for your approval.",
        ),
        ("Sihirbaz dosyayı okur ve ne bulduğunu size sorar", "The wizard reads the file and asks you about it"),
    ),
    "calendar_ics": KindInfo(
        ("Takvim dosyası", "Calendar file"),
        ("takvim dosyası", "a calendar file"),
        (
            "Takvim dosyası (.ics), etkinlikleri tarih ve saatleriyle taşır. Kurulum sihirbazı her etkinliği bir "
            "derslik rezervasyonu önerisine çevirir.",
            "A calendar file (.ics) carries events with their dates and times. The setup wizard turns each event into "
            "a proposed room booking.",
        ),
        ("Etkinlikler rezervasyon önerisine çevrilir", "Turns the events into proposed bookings"),
    ),
    "request_list": KindInfo(
        ("Ders talep listesi", "Course request list"),
        ("ders talep listesi", "a course request list"),
        (
            "Bu, derslerin gün, saat ve derslik taleplerini taşıyan bir listedir, ama içe aktarma ekranının beklediği "
            "düzende değil. Kurulum sihirbazı sütunları eşleştirir ve size sorar.",
            "This is a list of course day, time and room requests, but not in the layout the import screen expects. "
            "The setup wizard maps the columns and asks you.",
        ),
        ("Sihirbaz sütunları eşleştirir ve size sorar", "The wizard maps the columns and asks you"),
    ),
    "timetable_other": KindInfo(
        ("Çizelge (farklı düzen)", "Timetable (other layout)"),
        ("farklı düzende bir çizelge", "a timetable in another layout"),
        (
            "Bu bir derslik çizelgesi, ama içe aktarma ekranının okuduğu haftalık takvim düzeninde değil. Kurulum "
            "sihirbazı bu düzeni de okur ve size sorar.",
            "This is a room timetable, but not in the weekly-board layout the import screen reads. The setup wizard "
            "reads this layout too and asks you.",
        ),
        ("Sihirbaz bu düzeni de okur", "The wizard reads this layout too"),
    ),
    "room_list": KindInfo(
        ("Derslik listesi", "Room list"),
        ("derslik listesi", "a room list"),
        (
            "Bu, derslikleri ve kapasitelerini listeleyen bir tablodur, ama derslik ana listesi düzeninde değil. "
            "Kurulum sihirbazı sütunları eşleştirir.",
            "This is a table of rooms and capacities, but not in the room master layout. The setup wizard maps the "
            "columns.",
        ),
        ("Sihirbaz derslikleri okur ve size sorar", "The wizard reads the rooms and asks you"),
    ),
    "holidays": KindInfo(
        ("Tatil ve akademik takvim", "Holidays and calendar"),
        ("tatil ve akademik takvim listesi", "a holiday and academic calendar list"),
        (
            "Bu liste tatil günlerini ve akademik takvim tarihlerini taşır. Kurulum sihirbazı onları okur; tatilleri "
            "elle de girebilirsiniz.",
            "This list carries holidays and academic calendar dates. The setup wizard reads them; you can also enter "
            "the holidays by hand.",
        ),
        ("Tatiller ve dönem tarihleri okunur", "Reads the holidays and term dates"),
    ),
    "staff_list": KindInfo(
        ("Personel listesi", "Staff list"),
        ("personel listesi", "a staff list"),
        (
            "Bu, öğretim elemanlarını ya da personeli listeleyen bir tablodur. Kurulum sihirbazı kişileri derslerle "
            "eşleştirir.",
            "This is a table of instructors or staff. The setup wizard matches the people to the courses.",
        ),
        ("Kişiler derslerle eşleştirilir", "Matches the people to the courses"),
    ),
    "rules_doc": KindInfo(
        ("Kurallar ve tercihler", "Rules and preferences"),
        ("kurallar ve tercihler belgesi", "a rules and preferences document"),
        (
            "Bu belge planlama kurallarını ve tercihlerini yazıyla anlatır. Kurulum sihirbazı cümleleri kurallara "
            "çevirir ve her birini onayınıza sunar.",
            "This document describes planning rules and preferences in words. The setup wizard turns the sentences "
            "into rules and asks you to approve each one.",
        ),
        ("Cümleler kurallara çevrilir", "Turns the sentences into rules"),
    ),
    "scan": KindInfo(
        ("Tarama ya da görüntü", "Scan or image"),
        ("taranmış sayfa ya da görüntü", "a scan or an image"),
        (
            "Bu bir görüntü ya da taranmış sayfadır; içinde okunabilir metin yoktur. Kurulum sihirbazı onu yalnızca "
            "yapay zekâ açıkken okuyabilir.",
            "This is an image or a scanned page with no readable text. The setup wizard can read it only when AI is "
            "turned on.",
        ),
        ("Sihirbaz görüntüyü yapay zekâ ile okur", "The wizard reads the image with AI"),
    ),
}
#: the kinds a person may pick in the chooser besides the detected ones
CHOOSER_ONBOARDING = "onboarding"
#: kinds whose import writes into a term (term line + term warnings)
TERM_KINDS = frozenset({"planning_list", "exam_list", "weekly_grid", "timetable_other", "request_list"})
#: kinds with a downloadable header-only template (app/ai/helper/file_examples.py)
EXAMPLE_KINDS = ("planning_list", "exam_list", "room_master", "users_csv")

IMPORTER_KIND = {
    "planning-list": "planning_list",
    "exam-list": "exam_list",
    "weekly-grid": "weekly_grid",
    "room-master": "room_master",
}
COUNCIL_KIND = {
    "request_list": "request_list",
    "exam_list": "exam_list",
    "timetable_grid": "timetable_other",
    "room_list": "room_list",
    "calendar": "holidays",
    "staff_list": "staff_list",
    "rules": "rules_doc",
}
#: a council kind already covered by the importer kind of the same family (the importer shape wins)
_SAME_FAMILY = {
    "request_list": "planning_list",
    "timetable_other": "weekly_grid",
    "room_list": "room_master",
    "staff_list": "users_csv",
}
#: council lexicon fields -> the canonical label the card shows (Turkish first)
FIELD_LABELS: dict[str, tuple[str, str]] = {
    "course_code": ("Ders Kodu", "course code"),
    "course_name": ("Ders Adı", "course name"),
    "section": ("Şube", "section"),
    "program": ("Bölüm/Program", "department / programme"),
    "faculty": ("Fakülte", "faculty"),
    "class_year": ("Sınıf", "year of study"),
    "semester": ("Yarıyıl", "semester"),
    "enrolment": ("Öğrenci Sayısı", "enrolment"),
    "day": ("Gün", "day"),
    "start_time": ("Başlangıç Saati", "start time"),
    "end_time": ("Bitiş Saati", "end time"),
    "time_range": ("Saat Aralığı", "time range"),
    "room_request": ("Derslik Talebi", "room request"),
    "room": ("Derslik", "room"),
    "instructor": ("Öğretim Elemanı", "instructor"),
    "instructor2": ("2. Öğretim Elemanı", "2nd instructor"),
    "mode": ("Öğretim Şekli", "teaching mode"),
    "weeks": ("Haftalar", "weeks"),
    "notes": ("Açıklama", "notes"),
    "date": ("Tarih", "date"),
    "duration": ("Süre", "duration"),
    "capacity": ("Kapasite", "capacity"),
    "exam_capacity": ("Sınav Kapasitesi", "exam capacity"),
    "building": ("Bina", "building"),
    "floor": ("Kat", "floor"),
    "room_type": ("Derslik Türü", "room type"),
    "person_name": ("Ad Soyad", "name"),
    "email": ("E-posta", "e-mail"),
    "title": ("Unvan", "title"),
    "label": ("Etiket", "label"),
    "start_date": ("Başlangıç Tarihi", "start date"),
    "end_date": ("Bitiş Tarihi", "end date"),
}
#: the users CSV columns (``bookings_users.HEADER_ALIASES`` keys)
USER_LABELS: dict[str, tuple[str, str]] = {
    "username": ("Kullanıcı adı", "username"),
    "email": ("E-posta", "e-mail"),
    "firstname": ("Ad", "first name"),
    "lastname": ("Soyad", "last name"),
    "full_name": ("Ad Soyad", "full name"),
    "password": ("Parola", "password"),
    "role": ("Rol", "role"),
    "department": ("Bölüm", "department"),
    "force_password_reset": ("Parola sıfırlama", "password reset"),
}
#: the importers' preferred order of the evidence labels (the rest follow in the HEADER_SPEC order)
_PLAN_ORDER = ("code", "label", "day", "start", "end", "ins1")
_EXAM_ORDER = ("code", "date", "start", "end", "venue", "definitive")
CRBS_TABLES = frozenset(
    {"bookings", "rooms", "periods", "weeks", "sessions", "users", "schedules", "holidays", "departments"}
)
_SQL_TABLE = re.compile(r"(?:CREATE\s+TABLE|INSERT\s+INTO)\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)", re.IGNORECASE)
FORMAT_NAMES: dict[str, tuple[str, str]] = {
    "xlsx": ("Excel", "Excel"),
    "xls": ("Excel (eski biçim)", "Excel (old format)"),
    "ods": ("OpenDocument tablo", "OpenDocument spreadsheet"),
    "csv": ("CSV", "CSV"),
    "json": ("JSON", "JSON"),
    "xml": ("XML", "XML"),
    "ics": ("takvim (ICS)", "calendar (ICS)"),
    "docx": ("Word", "Word"),
    "pdf": ("PDF", "PDF"),
    "image": ("görüntü", "image"),
    "eml": ("e-posta", "e-mail"),
    "txt": ("metin", "text"),
    "sql": ("SQL", "SQL"),
}
SEASONS: dict[str, tuple[str, str]] = {
    "SPRING": ("Bahar", "Spring"),
    "FALL": ("Güz", "Fall"),
    "SUMMER": ("Yaz", "Summer"),
    "FINAL": ("Final", "Final"),
    "BUT": ("Bütünleme", "Make-up"),
}


def all_labels_tr() -> list[str]:
    """Every canonical label the evidence may show (the name-free test compares against it)."""
    from app.importers.detect import COLUMN_LABELS
    from app.importers.room_master import COLUMNS as ROOM_COLUMNS

    out = [v[0] for v in COLUMN_LABELS.values()] + [v[0] for v in FIELD_LABELS.values()]
    return out + [v[0] for v in USER_LABELS.values()] + list(ROOM_COLUMNS)


# ================================================================================================ signals


@dataclass
class CouncilHit:
    grid: int  # -1 = the file's text units
    name: str
    kind: str
    confidence: float
    fields: list[str]
    language: str
    orientation: str = ""  # timetable grids: vertical | horizontal


@dataclass
class Signals:
    """What the detectors saw (picklable; also kept, encrypted, in the stage so a chooser pick re-routes without
    a second upload). No cell value: field names, counts, dates, CRBS table names and the raw sheet titles (these
    are filtered before they reach a card)."""

    format: str
    ext: str
    size: int
    sha256: str = ""
    header_kind: str | None = None
    shape: str | None = None
    plan_keys: list[str] = field(default_factory=list)
    exam_keys: list[str] = field(default_factory=list)
    room_master_cols: list[str] = field(default_factory=list)
    council: list[CouncilHit] = field(default_factory=list)
    users_fields: list[str] = field(default_factory=list)
    crbs_tables: list[str] = field(default_factory=list)
    ics_events: int = 0
    ics_first: str | None = None
    ics_last: str | None = None
    intake: bool = False
    needs_vision: bool = False
    sheet_titles: list[str] = field(default_factory=list)
    n_sheets: int = 0
    grid_rooms: int = 0
    units: int = 0
    term_season: str | None = None
    term_year: int | None = None
    term_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Signals:
        d = dict(d)
        d["council"] = [CouncilHit(**c) for c in d.get("council") or []]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def card_format(self) -> str:
        return "sql" if self.crbs_tables and self.format in ("csv", "txt") else self.format


def precheck(name: str, data: bytes) -> str:
    """The council's upload-time refusal (magic bytes, per-format caps); runs in the rlimit child."""
    from app.council import formats

    return formats.precheck(name, data)


def _render_xlsx_head(name: str, data: bytes) -> tuple[Any, list[str]]:
    """The header area of a workbook (first :data:`HEAD_SHEETS` sheets, :data:`HEAD_ROWS` rows), read-only, with
    merged ranges forward-filled like the council's renderer; and every sheet title."""
    from app.core import safe_files
    from app.council import render as rd
    from app.council import text as tx

    out = rd.Rendered(PurePath(name).name, "xlsx", hashlib.sha256(data).hexdigest(), len(data))
    wb = safe_files.open_workbook(data, read_only=True, data_only=True, max_rows=HEAD_ROWS, max_cols=rd.MAX_COLS)
    try:
        titles = [str(t) for t in wb.sheetnames]
        merges = rd._sheet_merges(data)  # noqa: SLF001 - the renderer's own merge reader (same package family)
        for ws in wb.worksheets:
            if len(out.grids) >= HEAD_SHEETS:
                break
            width = 0
            for row in ws.iter_rows(min_row=1, max_row=min(rd.SCAN_ROWS, HEAD_ROWS), max_col=rd.MAX_COLS, values_only=True):
                for c in range(len(row) - 1, -1, -1):
                    if row[c] is not None and tx.cell_text(row[c]):
                        width = max(width, c + 1)
                        break
            sheet_merges = [m for m in merges.get(ws.title, []) if m[0] < HEAD_ROWS and m[1] < rd.MAX_COLS]
            width = max([width] + [m[3] + 1 for m in sheet_merges if m[3] < rd.MAX_COLS])
            if width == 0:
                continue
            rows = [
                [tx.cell_text(v) for v in row] + [""] * (width - len(row))
                for row in ws.iter_rows(min_row=1, max_row=HEAD_ROWS, max_col=width, values_only=True)
            ]
            numbers = list(range(1, len(rows) + 1))
            for r1, c1, r2, c2 in sheet_merges:
                if r1 >= len(rows):
                    continue
                v = rows[r1][c1] if c1 < len(rows[r1]) else ""
                for r in range(r1, min(r2, len(rows) - 1) + 1):
                    for c in range(c1, min(c2, width - 1) + 1):
                        rows[r][c] = v
            rows, numbers = rd._trim(rows, numbers)  # noqa: SLF001
            if rows:
                out.grids.append(rd.Grid(ws.title, "sheet", rows, sheet_merges, {"sheet": ws.title}, numbers))
    finally:
        wb.close()
    return out, titles


def _crbs_tables(data: bytes) -> list[str]:
    """CRBS SQL dump sniff: the CRBS tables a ``CREATE TABLE`` / ``INSERT INTO`` names (a prefix is allowed)."""
    text = data[: 4 * 1024 * 1024].decode("utf-8", "replace")
    found: list[str] = []
    for m in _SQL_TABLE.finditer(text):
        name = m.group(1).lower()
        base = name if name in CRBS_TABLES else name.split("_", 1)[-1]
        if base in CRBS_TABLES and base not in found:
            found.append(base)
    return found


def read_signals(name: str, data: bytes) -> Signals:
    """Every detector on the header area of one (prechecked) file. Runs in the rlimit child."""
    from app.council import fastpath, formats, structure
    from app.importers import exam_list, planning_list
    from app.importers import normalize as n
    from app.importers.detect import detect_kind
    from app.importers.room_master import COLUMNS as ROOM_COLUMNS
    from app.importers.xlsx import map_headers
    from app.services import bookings_users
    from app.services.import_term_check import file_term

    det = formats.detect(name, data)
    fmt = det.spec.name
    sig = Signals(
        format=fmt, ext=PurePath(name).suffix.lower().lstrip(".")[:8], size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    if fmt == "xlsx":
        rendered, titles = _render_xlsx_head(name, data)
    else:
        rendered = formats.render(data, name)
        titles = [g.name for g in rendered.grids] if fmt in ("xls", "ods") else []
    if fmt == "csv" and not rendered.grids and len(rendered.units) == 1:
        # a header-only CSV (a downloaded template): the council reads one line as text; it is the header row
        line = rendered.units[0].text
        sep = max(";,\t|", key=line.count)
        cells = [c.strip().strip('"') for c in line.split(sep)]
        if line.count(sep) >= 1 and all(cells):
            from app.council.render import Grid

            rendered.grids.append(Grid("csv", "csv", [cells], [], {"table": "csv"}, [1]))
            rendered.units.clear()
    for g in rendered.grids:
        del g.cells[HEAD_ROWS:]
        del g.row_numbers[HEAD_ROWS:]
    del rendered.grids[HEAD_SHEETS:]
    sig.sheet_titles, sig.n_sheets = titles[:60], len(titles)
    sig.units = len(rendered.units)
    sig.needs_vision = bool(rendered.needs_vision) or fmt == "image"
    g0 = rendered.grids[0] if rendered.grids else None
    header_row = 0
    if g0 is not None and fmt in _IMPORTER_TABULAR:
        for i in range(min(3, g0.n_rows)):
            got = detect_kind(list(g0.cells[i]))
            if got:
                sig.header_kind, header_row = got, i
                break
    if g0 is not None and g0.cells:
        header: list[str | None] = [h or None for h in g0.cells[header_row]]
        sig.plan_keys = list(map_headers(header, planning_list.HEADER_SPEC))
        sig.exam_keys = list(map_headers(header, exam_list.HEADER_SPEC))
    sig.shape = fastpath.detect_shape(rendered)
    sig.intake = sig.shape == "intake-v1"
    if g0 is not None and sig.shape == "room-master":
        folded = [str(h).strip().casefold() for h in g0.cells[0]]
        sig.room_master_cols = [c for c in ROOM_COLUMNS if c in folded]
    if g0 is not None and sig.shape == "weekly-grid" and g0.n_rows > 1:
        sig.grid_rooms = sum(1 for v in g0.cells[1][1:] if v and n.parse_room_header(v) is not None)
    for a in structure.analyze(rendered):
        fields = list(dict.fromkeys(c.field for c in a.columns if c.field))
        orient = "/".join(sorted({ax.orientation for ax in a.axes}))
        sig.council.append(CouncilHit(a.grid, a.name, a.kind, float(a.confidence), fields, a.language, orient))
    if g0 is not None and fmt in ("csv", "txt") and g0.cells:
        row = [str(c) for c in g0.cells[0]]
        try:
            ok = bookings_users.header_columns(row) is not None
        except Exception:  # noqa: BLE001 - a Refusal: no usable users header, so no signal
            ok = False
        if ok:
            words = [bookings_users._header_word(c) for c in row]  # noqa: SLF001 - the importer's own alias reader
            sig.users_fields = list(dict.fromkeys(w for w in words if w))
    if det.probe.family == "text":
        sig.crbs_tables = _crbs_tables(data)
    if fmt == "ics" and g0 is not None:
        events = g0.cells[1:]
        sig.ics_events = len(events)
        if events:
            sig.ics_first, sig.ics_last = events[0][0] or None, events[-1][0] or None
    sig.term_season, sig.term_year, sig.term_source = file_term(name, data)
    return sig


# ================================================================================================ scoring


def _first_hit(sig: Signals) -> CouncilHit | None:
    hits = [h for h in sig.council if h.kind != "other"]
    if sig.format in _DOCUMENTS:
        rules = [h for h in hits if h.grid == -1 and h.kind == "rules"]
        if rules:
            return rules[0]
    return hits[0] if hits else None


def candidates(sig: Signals) -> list[tuple[str, float]]:
    """§4.3: (kind, score) sorted by score. The extension never decides alone; the file name never decides the
    kind (it only feeds the term)."""
    scores: dict[str, float] = {}

    def put(kind: str, score: float) -> None:
        scores[kind] = max(scores.get(kind, 0.0), round(score, 3))

    if sig.intake:
        put("intake_json", 0.98)
    if sig.format == "ics":
        put("calendar_ics", 0.98)
    hk = sig.header_kind if sig.header_kind in IMPORTER_KIND else None
    sh = sig.shape if sig.shape in IMPORTER_KIND else None
    first = _first_hit(sig)
    if sh and hk == sh:
        put(IMPORTER_KIND[sh], 0.95)
    elif sh and hk:
        put(IMPORTER_KIND[sh], 0.70)  # they disagree on two importer shapes: both kept, the chooser asks
        put(IMPORTER_KIND[hk], 0.65)
    elif sh:
        put(IMPORTER_KIND[sh], 0.90)
    elif hk == "weekly-grid":
        if first is not None and first.kind == "timetable_grid":
            put("timetable_other", 0.80)  # day names on top but no importer time axis: the importer would fail
        else:
            put("weekly_grid", 0.55)
    elif hk:
        put(IMPORTER_KIND[hk], 0.70)
    users = set(sig.users_fields)
    if users & {"username", "email"} and len(users) >= 2:
        put("users_csv", 0.90)
    if len(sig.crbs_tables) >= 5:
        put("crbs_dump", 0.95)
    elif len(sig.crbs_tables) >= 3:
        put("crbs_dump", 0.75)
    if first is not None:
        kind = COUNCIL_KIND.get(first.kind)
        if kind and (kind in scores or _SAME_FAMILY.get(kind) not in scores):
            put(kind, first.confidence * 0.85)
    if sig.needs_vision:
        put("scan", 0.80)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def band(score: float) -> str:
    return "sure" if score >= 0.85 else ("likely" if score >= 0.60 else "unsure")


def decide(cands: list[tuple[str, float]]) -> str:
    """``detected`` | ``ambiguous`` | ``unknown`` (§4.3)."""
    if not cands or cands[0][1] < 0.40:
        return "unknown"
    if len(cands) >= 2 and cands[1][1] >= 0.50 and cands[0][1] - cands[1][1] <= 0.15:
        return "ambiguous"
    if cands[0][1] < 0.60:
        return "ambiguous"
    return "detected"


# ================================================================================================ routes


@dataclass(frozen=True)
class RouteSpec:
    feature_id: str
    params: dict[str, Any]
    label: tuple[str, str]
    carries_file: bool
    #: any-of; empty = the feature index entry decides (alternatives)
    perms: tuple[str, ...] = ()
    label_short: tuple[str, str] | None = None


_IMPORT_KIND = {"planning_list": "planning-list", "exam_list": "exam-list", "weekly_grid": "weekly-grid"}
_IMPORT_OBJECT = {
    "planning_list": ("planlama listesi", "planning list"),
    "exam_list": ("sınav listesi", "exam list"),
    "weekly_grid": ("haftalık derslik takvimi", "weekly room timetable"),
}
ONBOARDING = RouteSpec(
    "onboarding", {}, ("Kurulum sihirbazında aç", "Open in the setup wizard"), True, ("planning.edit",)
)


@dataclass
class TermGuess:
    term_id: int | None
    name: tuple[str, str]
    source: str
    matches_active: bool
    code: str | None = None
    year: int | None = None


def _import_route(kind: str, term: TermGuess | None, year: int | None) -> RouteSpec:
    params: dict[str, Any] = {"kind": _IMPORT_KIND[kind]}
    if term is not None and term.term_id is not None:
        params["term_id"] = term.term_id
    if kind == "weekly_grid" and year is not None:
        params["year"] = year
    obj_tr, obj_en = _IMPORT_OBJECT[kind]
    if term is not None and not term.matches_active:
        label = (f"{term.name[0]} dönemine {obj_tr} olarak aktar", f"Import into {term.name[1]} as {obj_en}")
        short_tr = f"{term.name[0]} dönemine aktar"
        short = (short_tr, f"Import into {term.name[1]}") if len(short_tr) <= 28 else None
    else:
        label, short = (f"{obj_tr[0].upper()}{obj_tr[1:]} olarak içe aktar", f"Import as {obj_en}"), None
    return RouteSpec("import", params, label, True, ("planning.edit",), short)


def file_routes(kind: str, sig: Signals, term: TermGuess | None, year: int | None) -> list[RouteSpec]:
    """The routes that carry the file, best first (the planner side of §4.2)."""
    fmt = sig.card_format
    if kind in _IMPORT_KIND:
        return [_import_route(kind, term, year), ONBOARDING] if fmt in _EXCEL else [ONBOARDING]
    if kind == "room_master":
        if fmt in _ROOM_MASTER_FORMATS:
            rm = RouteSpec(
                "import",
                {"kind": "room-master"},
                ("Derslik ana listesi olarak içe aktar", "Import as room master"),
                True,
                ("planning.edit", "setup.rooms"),
            )
            return [rm, ONBOARDING]
        return [ONBOARDING]
    if kind in ("users_csv", "staff_list") and set(sig.users_fields) & {"username", "email"}:
        if sig.size > USERS_MAX_BYTES:
            return []
        return [RouteSpec("admin.users", {"import": 1}, ("Kullanıcıları içe aktar", "Import users"), True, ("setup.users",))]
    if kind == "users_csv":
        return []
    if kind == "crbs_dump":
        return [
            RouteSpec(
                "import",
                {"kind": "crbs"},
                ("classroombookings verisini aktar", "Import classroombookings data"),
                True,
                ("planning.edit",),
            )
        ]
    return [ONBOARDING]


def _alt(feature_id: str, tr: str, en: str, params: dict[str, Any] | None = None) -> RouteSpec:
    return RouteSpec(feature_id, params or {}, (tr, en), False)


_MY_CLASSES = _alt("my_classes", "Derslerim'i aç", "Open My classes")
_FIND_ROOM = _alt("find_room", "Derslik bul'u aç", "Open Find a room")
_RESERVE = _alt("reserve", "Hızlı rezervasyonu aç", "Open Quick reserve")
_MY_REQUESTS = _alt("my_requests", "Taleplerim'i aç", "Open My requests")
_CALENDAR = _alt("profile.calendar", "Takvimime ekle", "Add to my calendar", {"calendar": 1})


def alternatives(kind: str, sig: Signals) -> list[RouteSpec]:
    """The person's own pages when the file is the planning team's job (no file is carried)."""
    if kind in ("planning_list", "exam_list"):
        return [_MY_CLASSES]
    if kind in ("weekly_grid", "room_master", "room_list", "timetable_other"):
        return [_FIND_ROOM]
    if kind == "calendar_ics":
        return [_CALENDAR, _RESERVE]
    if kind == "request_list":
        hit = _first_hit(sig)
        f = set(hit.fields if hit else [])
        if "room" in f or "room_request" in f:
            return [_RESERVE, _MY_REQUESTS]
    return []


def _secondary_extra(kind: str) -> list[RouteSpec]:
    if kind == "holidays":
        return [RouteSpec("admin.holidays", {}, ("Tatilleri elle ekle", "Add holidays by hand"), False)]
    return []


def _visible(access: Access, r: RouteSpec) -> bool:
    if r.perms:
        return any(p in access.perms for p in r.perms)
    from app.ai.helper.index import get_index, visible

    entry = next((e for e in get_index().entries if e.id == r.feature_id), None)
    return entry is not None and visible(entry, access.perms)


@dataclass
class Plan:
    """The routes one person gets for one kind."""

    primary: RouteSpec | None
    secondary: list[RouteSpec]
    needs_planner: bool

    @property
    def carries_file(self) -> bool:
        return any(r.carries_file for r in ([self.primary] if self.primary else []) + self.secondary)

    def all(self) -> list[RouteSpec]:
        return ([self.primary] if self.primary else []) + self.secondary


def plan_for(
    access: Access, kind: str, sig: Signals, term: TermGuess | None, year: int | None, context: str | None = None
) -> Plan:
    held = [r for r in file_routes(kind, sig, term, year) if _visible(access, r)]
    if held:
        primary, rest = held[0], held[1:]
        secondary = [r for r in rest + [r for r in _secondary_extra(kind) if _visible(access, r)] if r != primary]
        if context:
            secondary.sort(key=lambda r: r.feature_id != context)
        return Plan(primary, secondary[:2], False)
    alts = [r for r in alternatives(kind, sig) if _visible(access, r)]
    return Plan(alts[0] if alts else None, alts[1:2], True)


def routable_kinds(access: Access, sig: Signals, cands: list[tuple[str, float]]) -> list[str]:
    """The candidate kinds this person may hand the file over for (the token's ``kinds``)."""
    out = []
    for kind, _ in cands:
        if any(_visible(access, r) for r in file_routes(kind, sig, None, None)):
            out.append(kind)
    return out


# ================================================================================================ term guess


def _season_name(season: str, year: int | None) -> tuple[str, str]:
    tr, en = SEASONS.get(season, (season.title(), season.title()))
    return (f"{tr} {year}", f"{en} {year}") if year else (tr, en)


async def guess_term(session: AsyncSession, sig: Signals, active_term_id: int | None) -> tuple[TermGuess | None, Any]:
    """(the file's term, the person's active term). The client's active term (the page's term select) when it
    sends one, else the server's current term (``app/services/terms.py``)."""
    from app.council.term_match import calendar_year, term_season
    from app.models import Term
    from app.services.terms import current_term

    terms = list((await session.execute(select(Term))).scalars())
    active = next((t for t in terms if active_term_id is not None and t.id == active_term_id), None)
    active = active or current_term(terms)
    season, year = sig.term_season, sig.term_year
    if not season:
        return None, active
    ordered = sorted(terms, key=lambda t: (t.start_date is not None, t.start_date, t.id), reverse=True)
    same = [t for t in ordered if term_season(t.code, t.name) == season]
    exact = [t for t in same if year is None or calendar_year(season, t.code, t.name) == year]
    pick = (exact or same or [None])[0]
    if pick is not None:
        name = (cards.clean(pick.name, 60), cards.clean(pick.name, 60))
        matches = active is not None and pick.id == active.id
        y = calendar_year(season, pick.code, pick.name) or year
        guess = TermGuess(pick.id, name, sig.term_source or "file_name", matches, pick.code, y)
    else:
        a_season = term_season(active.code, active.name) if active is not None else None
        a_year = calendar_year(a_season, active.code, active.name) if active is not None else None
        matches = a_season == season and (year is None or a_year is None or a_year == year)
        guess = TermGuess(None, _season_name(season, year), sig.term_source or "file_name", matches, None, year)
    return guess, active


def _active_year(active: Any) -> int | None:
    if active is None:
        return None
    from app.council.term_match import calendar_year, term_season

    y = calendar_year(term_season(active.code, active.name), active.code, active.name)
    return y or (active.start_date.year if active.start_date else None)


# ================================================================================================ evidence


def _labels_line(labels: list[tuple[str, str]], kind_label: tuple[str, str]) -> tuple[str, str]:
    shown = labels[:_EVIDENCE_LABELS]
    more = len(labels) - len(shown)
    tr = ", ".join(lab[0] for lab in shown) + (f", +{more}" if more else "")
    en = ", ".join(lab[1] for lab in shown) + (f", +{more}" if more else "")
    return f"Sütunlar: {tr} → {kind_label[0]}", f"Columns: {en} → {kind_label[1]}"


def _keys_labels(keys: list[str], order: tuple[str, ...]) -> list[tuple[str, str]]:
    from app.importers.detect import COLUMN_LABELS

    ordered = [k for k in order if k in keys] + [k for k in keys if k not in order]
    return [COLUMN_LABELS[k] for k in ordered if k in COLUMN_LABELS]


def _date_tr(iso: str | None) -> str:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else ""


class _Titles:
    """Sheet titles made safe for a card: scrubbed, ≤ 40 characters, dropped when a name is found in them."""

    def __init__(self, redactor: Any) -> None:
        self.redactor = redactor

    def __call__(self, title: str | None) -> str | None:
        from app.core import kvkk_guard

        if not title:
            return None
        t = cards.clean(title, 40)
        if not t or kvkk_guard.unmasked_hits(title.encode("utf-8"), "title.txt"):
            return None
        if self.redactor and self.redactor.text(title) != title:
            return None
        return t


def evidence(kind: str, sig: Signals, safe_title: _Titles) -> list[tuple[str, str]]:
    info = KINDS[kind]
    lines: list[tuple[str, str]] = []
    first = _first_hit(sig)
    if kind == "weekly_grid":
        t = safe_title(sig.sheet_titles[0] if sig.sheet_titles else None)
        where_tr = f' ("{t}")' if t else ""
        lines.append(
            (
                f"{sig.n_sheets} sayfa, her biri bir hafta{where_tr}; üstte gün adları, solda ders saatleri, "
                f"{sig.grid_rooms} derslik sütunu",
                f"{sig.n_sheets} sheets, one per week{where_tr}; day names on top, periods on the left, "
                f"{sig.grid_rooms} room columns",
            )
        )
    elif kind == "planning_list" and sig.plan_keys:
        lines.append(_labels_line(_keys_labels(sig.plan_keys, _PLAN_ORDER), info.label))
    elif kind == "exam_list" and sig.exam_keys and sig.format in _IMPORTER_TABULAR:
        lines.append(_labels_line(_keys_labels(sig.exam_keys, _EXAM_ORDER), info.label))
    elif kind == "room_master" and sig.room_master_cols:
        lines.append(_labels_line([(c, c) for c in sig.room_master_cols], info.label))
    elif kind in ("users_csv", "staff_list") and sig.users_fields:
        tr, en = _labels_line(
            [USER_LABELS[f] for f in sig.users_fields if f in USER_LABELS], ("kullanıcı listesi", "user list")
        )
        lines.append((f"{tr}. Satırlar gösterilmez.", f"{en}. Rows are not shown."))
    elif kind == "crbs_dump":
        names = sig.crbs_tables[:_EVIDENCE_LABELS]
        more = len(sig.crbs_tables) - len(names)
        joined = ", ".join(names) + (f", +{more}" if more else "")
        lines.append(
            (f"Veritabanı dökümü; tablolar: {joined} → classroombookings", f"Database dump; tables: {joined} → classroombookings")
        )
    elif kind == "calendar_ics":
        first_d, last_d = sig.ics_first or "", sig.ics_last or ""
        span_tr = f", {_date_tr(first_d)} – {_date_tr(last_d)}" if first_d else ""
        span_en = f", {first_d} – {last_d}" if first_d else ""
        lines.append((f"Takvim dosyası: {sig.ics_events} etkinlik{span_tr}", f"Calendar file: {sig.ics_events} events{span_en}"))
    elif kind == "intake_json":
        lines.append(("SmartSched içe aktarma biçimi (smartsched.intake.v1)", "SmartSched import format (smartsched.intake.v1)"))
    elif kind == "timetable_other":
        if first is not None and "horizontal" in first.orientation:
            lines.append(
                (
                    "Saatler üstte, derslikler solda: yan çevrilmiş bir çizelge",
                    "Times across the top, rooms down the side: a transposed timetable",
                )
            )
        else:
            lines.append(
                ("Ders saatleri ve derslikler var, ama haftalık takvim düzeninde değil", "Periods and rooms, but not in the weekly-board layout")
            )
    elif kind == "scan":
        lines.append(("Görüntü ya da taranmış sayfa; okunabilir metin yok", "An image or a scanned page; no readable text"))
    elif kind == "rules_doc":
        lines.append(
            (f"Belge: {sig.units} paragraf; kural ve tercih cümleleri var", f"Document: {sig.units} paragraphs with rules and preferences")
        )
    elif first is not None and first.fields:
        labs = [FIELD_LABELS[f] for f in first.fields if f in FIELD_LABELS]
        if labs:
            lines.append(_labels_line(labs, info.label))
    if kind == "request_list" and first is not None and first.language == "en":
        lines.append(("Sütun adları İngilizce; Kurulum sihirbazı onları eşleştirir", "The column names are English; the setup wizard maps them"))
    # several sheets with different kinds: the first sheet decided, the others add one line
    others = [h for h in sig.council if h.grid >= 0 and h is not first and h.kind not in ("other", first.kind if first else "")]
    if others:
        h = others[0]
        t = safe_title(h.name)
        label = KINDS.get(COUNCIL_KIND.get(h.kind, ""), None)
        if t and label is not None:
            lines.append((f"{t}: {label.phrase[0]}", f"{t}: {label.label[1].lower()}"))
    return lines[:4]


# ================================================================================================ cards


@dataclass
class Built:
    card: s.CardBase
    #: the kinds the token may be routed to (empty: nothing carries the file)
    kinds: list[str]
    kind: str | None = None
    score: float | None = None
    state: str = ""


def _route(r: RouteSpec) -> s.FileRoute:
    return s.FileRoute(
        feature_id=r.feature_id,
        params=dict(r.params),
        label=cards.txt(*r.label),
        label_short=cards.txt(*r.label_short) if r.label_short else None,
        carries_file=r.carries_file,
    )


def _warn(code: str, status: str, tr: str, en: str) -> s.FileWarning:
    return s.FileWarning(code=code, status=status, message=cards.txt(tr, en))  # type: ignore[arg-type]


async def _ai_vision(session: AsyncSession) -> bool:
    from app.ai.policy import ai_allowed

    try:
        return await ai_allowed(session, "vision")
    except Exception:  # noqa: BLE001 - no sign-off row yet: off
        return False


async def _term_locked(term: TermGuess | None) -> bool:
    if term is None or term.code is None:
        return False
    from app.services import term_lock

    try:
        await term_lock.assert_unlocked(term_lock.term_key(term.code))
    except term_lock.TermLocked:
        return True
    except Exception:  # noqa: BLE001 - a lock table problem must not break classify
        return False
    return False


async def kind_card(
    session: AsyncSession,
    access: Access,
    sig: Signals,
    kind: str,
    score: float | None,
    *,
    active_term_id: int | None,
    context: str | None,
    safe_title: _Titles,
) -> Built:
    """The ``file`` card for one kind (detected or needs_planner) and its routable kinds."""
    info = KINDS[kind]
    term, active = await guess_term(session, sig, active_term_id) if kind in TERM_KINDS else (None, None)
    year = (term.year if term else None) or _active_year(active) if kind == "weekly_grid" else None
    plan = plan_for(access, kind, sig, term, year, context)
    certainty = band(score) if score is not None else "sure"
    warnings: list[s.FileWarning] = []
    if plan.needs_planner:
        if kind == "calendar_ics" and plan.primary is not None:
            title = cards.txt("Bu bir takvim dosyası", "This is a calendar file")
            warnings.append(
                _warn(
                    "ics_academic",
                    "info",
                    "SmartSched dışarıdan takvim okumaz. Derslerinizi ve rezervasyonlarınızı takviminize buradan "
                    "eklersiniz.",
                    "SmartSched doesn't read outside calendars. You add your classes and bookings to your calendar "
                    "from here.",
                )
            )
        else:
            team = ("yönetici", "an administrator") if kind == "users_csv" else ("planlama ekibi", "the planning team")
            send = ("yöneticinize", "your administrator") if kind == "users_csv" else ("bölüm planlamacınıza", "your department's planner")
            if plan.primary is not None:
                title = cards.txt(
                    f"Bu dosya bir {info.phrase[0]}. Bunu {team[0]} içe aktarır. Sizin için:",
                    f"This file is {info.phrase[1]}. {team[1][0].upper()}{team[1][1:]} imports it. For you:",
                )
            else:
                title = cards.txt(
                    f"Bu dosya bir {info.phrase[0]}. Bunu {team[0]} içe aktarır; dosyayı {send[0]} gönderebilirsiniz.",
                    f"This file is {info.phrase[1]}. {team[1][0].upper()}{team[1][1:]} imports it; you can send it to "
                    f"{send[1]}.",
                )
            if plan.primary is not None and plan.primary.feature_id == "my_classes":
                warnings.append(
                    _warn(
                        "my_classes_known",
                        "info",
                        "Derslerinizi SmartSched zaten biliyor; dosyayı yüklemenize gerek yok.",
                        "SmartSched already knows your classes; you don't need to upload the file.",
                    )
                )
    else:
        if certainty == "sure":
            title = cards.txt(f"Bu bir {info.phrase[0]}", f"This is {info.phrase[1]}")
        else:
            title = cards.txt(f"Bu büyük olasılıkla bir {info.phrase[0]}", f"This is most likely {info.phrase[1]}")
        # the term warnings speak about the button, so only when the button imports into a term
        imports = plan.primary is not None and plan.primary.feature_id == "import" and kind in _IMPORT_KIND
        if imports and term is not None and not term.matches_active and active is not None:
            warnings.append(
                _warn(
                    "term_mismatch",
                    "warn",
                    f"Dosya {term.name[0]} diyor; şu an {cards.clean(active.name, 60)} seçili. Düğme dosyanın "
                    "dönemine aktarır.",
                    f"The file says {term.name[1]}; {cards.clean(active.name, 60)} is selected now. The button imports "
                    "into the file's term.",
                )
            )
        if imports and term is None:
            warnings.append(
                _warn(
                    "term_unknown",
                    "info",
                    "Dosya hangi döneme ait olduğunu söylemiyor. İçe aktarırken dönemi siz seçeceksiniz.",
                    "The file doesn't say which term it is for. You'll choose the term when importing.",
                )
            )
        if imports and await _term_locked(term if term is not None and term.term_id else None):
            assert term is not None
            warnings.append(
                _warn(
                    "term_locked",
                    "warn",
                    f"{term.name[0]} dönemine şu anda başka bir içe aktarma yazıyor. Önizleme açılır; uygulama işlem "
                    "bitince yapılır.",
                    f"Another import is writing {term.name[1]} right now. The preview opens; applying waits until it "
                    "finishes.",
                )
            )
        if kind in _IMPORT_KIND and sig.card_format not in _EXCEL:
            warnings.append(
                _warn(
                    "needs_excel",
                    "info",
                    "İçe aktarma ekranı yalnızca Excel (.xlsx) okur. Bu dosya Kurulum sihirbazında aynı kurallarla "
                    "okunur.",
                    "The import screen reads Excel (.xlsx) only. The setup wizard reads this file with the same rules.",
                )
            )
    if (kind == "scan" or (sig.format == "pdf" and sig.needs_vision)) and not await _ai_vision(session):
        warnings.append(
            _warn(
                "scan_ai_off",
                "warn",
                "Taranmış sayfalar yapay zekâ olmadan okunamaz; yalnızca tablolar okunur. Yönetici Ayarlar › "
                "Yapay zekâ'dan açabilir.",
                "Scanned pages can't be read without AI; only tables are read. An admin can turn it on in Settings › "
                "AI.",
            )
        )
    if kind == "users_csv" and sig.size > USERS_MAX_BYTES:
        mb = f"{sig.size / (1024 * 1024):.1f}".replace(".", ",")
        warnings.append(
            _warn(
                "too_large_for_target",
                "bad",
                f"Kullanıcı listesi en çok 5 MB olabilir; dosya {mb} MB. Listeyi bölün.",
                f"A user list can be at most 5 MB; this file is {mb.replace(',', '.')} MB. Split the list.",
            )
        )
    distinct = {h.kind for h in sig.council if h.grid >= 0 and h.kind != "other"}
    if sig.n_sheets > 1 and len(distinct) > 1:
        t = safe_title(sig.sheet_titles[0] if sig.sheet_titles else None)
        if t:
            warnings.append(
                _warn(
                    "many_sheets",
                    "info",
                    f'Dosyada {sig.n_sheets} sayfa var; ilk sayfa "{t}" okundu.',
                    f'The file has {sig.n_sheets} sheets; the first sheet "{t}" was read.',
                )
            )
    lines = evidence(kind, sig, safe_title)
    file_term = None
    if term is not None and not plan.needs_planner:
        file_term = s.FileTerm(
            term_id=term.term_id,
            name=cards.txt(*term.name),
            source="sheet_title" if term.source == "sheet_title" else "file_name",
            matches_active=term.matches_active,
        )
    card = s.FileCard(
        id=cards.new_id(),
        title=title,
        state="needs_planner" if plan.needs_planner else "detected",
        kind=kind,
        kind_label=cards.txt(*info.label),
        certainty=certainty,  # type: ignore[arg-type]
        format=sig.card_format,
        evidence=s.Texts(tr=[cards.clean(t) for t, _ in lines], en=[cards.clean(e) for _, e in lines]),
        term=file_term,
        warnings=warnings[:4],
        primary=_route(plan.primary) if plan.primary else None,
        secondary=[_route(r) for r in plan.secondary],
        explain=s.Texts(tr=[info.explain[0]], en=[info.explain[1]]),
    )
    return Built(card, [kind] if plan.carries_file else [], kind, score, card.state)


def _accepted_explain() -> s.Texts:
    return s.Texts(
        tr=[
            "Tanıdığım dosyalar: planlama listesi, sınav listesi, haftalık derslik takvimi, derslik ana listesi, "
            "kullanıcı listesi, classroombookings yedeği, takvim (.ics)."
        ],
        en=[
            "Files I recognise: planning list, exam list, weekly room timetable, room master, user list, "
            "classroombookings backup, calendar (.ics)."
        ],
    )


def _example_kinds(access: Access) -> list[str]:
    from app.ai.helper.file_examples import EXAMPLES

    out = []
    for kind in EXAMPLE_KINDS:
        ex = EXAMPLES[kind]
        if any(p in access.perms for p in ex.perms):
            out.append(kind)
    return out


def unknown_card(access: Access, sig: Signals) -> Built:
    fmt_tr, fmt_en = FORMAT_NAMES.get(sig.card_format, (sig.card_format, sig.card_format))
    onboarding = _visible(access, ONBOARDING)
    card = s.FileCard(
        id=cards.new_id(),
        title=cards.txt("Bu dosyayı tanıyamadım.", "I couldn't recognise this file."),
        state="unknown",
        format=sig.card_format,
        evidence=s.Texts(
            tr=[f"Bu dosyayı tanıyamadım. {fmt_tr} biçiminde, ama tanıdığım sütunlar yok."],
            en=[f"I couldn't recognise this file. It is {fmt_en}, but I found no columns I know."],
        ),
        secondary=[_route(ONBOARDING)] if onboarding else [],
        explain=_accepted_explain(),
        examples=_example_kinds(access),
    )
    return Built(card, [CHOOSER_ONBOARDING] if onboarding else [], None, None, "unknown")


def onboarding_card(sig: Signals) -> Built:
    """The chooser's "Kurulum sihirbazında aç" row: one hand-over to the wizard."""
    card = s.FileCard(
        id=cards.new_id(),
        title=cards.txt("Kurulum sihirbazı dosyayı okur ve size sorar", "The setup wizard reads the file and asks you"),
        state="detected",
        format=sig.card_format,
        primary=_route(ONBOARDING),
        explain=s.Texts(tr=[KINDS["intake_json"].hint[0]], en=[KINDS["intake_json"].hint[1]]),
    )
    return Built(card, [CHOOSER_ONBOARDING], None, None, "detected")


async def build(
    session: AsyncSession,
    access: Access,
    sig: Signals,
    *,
    active_term_id: int | None = None,
    context: str | None = None,
    forced_kind: str | None = None,
) -> Built:
    """The card for one read file: detected / needs_planner (``file``), ambiguous (``choice``) or unknown."""
    from app.ai.personal import load_redactor

    redactor = await load_redactor(session) if sig.sheet_titles or len(sig.council) > 1 else None
    titles = _Titles(redactor)
    cands = candidates(sig)
    kinds = routable_kinds(access, sig, cands)
    planner = _visible(access, ONBOARDING)
    if forced_kind is not None:
        if forced_kind == CHOOSER_ONBOARDING and planner:
            return onboarding_card(sig)
        score = dict(cands).get(forced_kind)
        if forced_kind not in kinds or score is None:
            raise KindNotAllowed(forced_kind)
        return await kind_card(
            session, access, sig, forced_kind, score, active_term_id=active_term_id, context=context, safe_title=titles
        )
    state = decide(cands)
    if state == "unknown":
        return unknown_card(access, sig)
    if state == "ambiguous":
        options = [k for k, _ in cands if k in kinds][:3]
        if planner and options:
            options.append(CHOOSER_ONBOARDING)
        if len(options) >= 2:
            opts = []
            for k in options:
                if k == CHOOSER_ONBOARDING:
                    opts.append(
                        s.Option(
                            value=k,
                            label=cards.txt("Kurulum sihirbazında aç", "Open in the setup wizard"),
                            hint=cards.txt(*KINDS["intake_json"].hint),
                        )
                    )
                else:
                    opts.append(s.Option(value=k, label=cards.txt(*KINDS[k].label), hint=cards.txt(*KINDS[k].hint)))
            card = s.ChoiceCard(
                id=cards.new_id(),
                action="classify_file",
                arg="kind",
                question=cards.txt("Bu dosya hangisi?", "Which one is this file?"),
                options=opts,
            )
            return Built(card, options, None, cands[0][1], "ambiguous")
    kind, score = cands[0]
    return await kind_card(
        session, access, sig, kind, score, active_term_id=active_term_id, context=context, safe_title=titles
    )


def token_kinds(access: Access, sig: Signals) -> list[str]:
    """The kinds a staged file may be routed / handed over to by this person: the routable candidates, plus the
    setup wizard for planners (§6.3 ``kinds``)."""
    kinds = routable_kinds(access, sig, candidates(sig))
    return kinds + ([CHOOSER_ONBOARDING] if _visible(access, ONBOARDING) else [])


class KindNotAllowed(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


# ================================================================================================ refusals


@dataclass
class Refusal:
    code: str
    tr: str
    en: str
    status: int = 200


async def read_file(name: str, data: bytes) -> tuple[Signals | None, Refusal | None]:
    """Precheck (rlimit child) → KVKK guard (test stacks) → signals (rlimit child). A refusal never stages."""
    from app.core import kvkk_guard, safe_files
    from app.council import i18n
    from app.council.render import RenderError

    ext = re.sub(r"[^a-z0-9]", "", PurePath(name).suffix.lower())[:8]
    shown = f".{ext}" if ext else "?"
    if not data:
        return None, Refusal("file_empty", "Dosya boş.", "The file is empty.")
    try:
        await safe_files.run_isolated(precheck, name, data)
    except RenderError as exc:
        msg = str(exc)
        if "empty" in msg:
            return None, Refusal("file_empty", "Dosya boş.", "The file is empty.")
        if msg.startswith("unsupported file type"):
            return None, Refusal(
                "file_type_unsupported",
                f"Bu tür dosyayı okuyamıyorum ({shown}).",
                f"I can't read this type of file ({shown}).",
            )
        return None, Refusal("file_type_unsupported", i18n.localize(msg, "tr") or msg, msg)
    except safe_files.UnsafeFileError as exc:
        return None, Refusal(
            "file_unsafe",
            "Bu dosya güvenle okunamıyor: çok büyük ya da bozuk bir içerik var.",
            f"This file can't be read safely: {exc.message}.",
        )
    try:
        await asyncio.to_thread(kvkk_guard.check, data, name)
    except kvkk_guard.KvkkRefused as exc:
        return None, Refusal(exc.code, exc.message_tr, exc.message_en)
    try:
        sig = await safe_files.run_isolated(read_signals, name, data)
    except (RenderError, safe_files.UnsafeFileError, ValueError, OSError) as exc:
        log.info("helper file read failed: %s", type(exc).__name__)
        return None, Refusal(
            "file_read_failed",
            "Dosya okunamadı. Tekrar deneyin ya da başka bir dosya seçin.",
            "The file couldn't be read. Try again or choose another file.",
            status=-1,
        )
    return sig, None


def refusal_card(access: Access, r: Refusal) -> s.CardBase:
    from app.ai.helper.index import get_index, visible

    if r.status == -1:
        return cards.status("error", r.code, r.tr, r.en, action="classify_file")
    nav = []
    for fid in ("import", "onboarding"):
        entry = next((e for e in get_index().entries if e.id == fid), None)
        if entry is not None and visible(entry, access.perms):
            nav.append(cards.nav(entry))
    return cards.status("refusal", r.code, r.tr, r.en, nav[:2], action="classify_file")


# ================================================================================================ rate limit

_rate: dict[int, deque[float]] = {}
_rate_lock = threading.Lock()


def rate_ok(user_id: int) -> bool:
    """20 per minute and 200 per day per person (in-process; the helper's other limits are per feature)."""
    t = now()
    with _rate_lock:
        q = _rate.setdefault(user_id, deque())
        while q and t - q[0] > 86_400:
            q.popleft()
        if len(q) >= RATE_PER_DAY or sum(1 for x in q if t - x <= 60) >= RATE_PER_MINUTE:
            return False
        q.append(t)
        return True


def reset_rate_limit() -> None:
    with _rate_lock:
        _rate.clear()


# ================================================================================================ stage


class StageError(Exception):
    def __init__(self, status: int, code: str, tr: str, en: str) -> None:
        super().__init__(code)
        self.status, self.code, self.tr, self.en = status, code, tr, en


_MESSAGES = {
    "stage_bad_token": (
        403,
        "Bu dosya aktarımı geçerli değil. Dosyayı yeniden seçin.",
        "This file hand-over is not valid. Choose the file again.",
    ),
    "stage_other_user": (
        403,
        "Bu dosya başka bir oturuma ait. Dosyayı yeniden seçin.",
        "This file belongs to another session. Choose the file again.",
    ),
    "stage_expired": (
        410,
        "Dosyanın süresi doldu (10 dakika). Yeniden seçin.",
        "The file expired (10 minutes). Choose it again.",
    ),
    "stage_used": (410, "Bu dosya zaten kullanıldı. Yeniden seçin.", "This file was already used. Choose it again."),
}


def _err(code: str) -> StageError:
    status, tr, en = _MESSAGES[code]
    return StageError(status, code, tr, en)


def _secret() -> bytes:
    return hmac.new(get_settings().app_secret.encode("utf-8"), _LABEL, hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{_b64(body)}.{_b64(hmac.new(_secret(), body, hashlib.sha256).digest())}"


def _verify(token: str) -> dict[str, Any]:
    try:
        body_b64, sig_b64 = str(token).split(".", 1)
        body = _unb64(body_b64)
        good = hmac.compare_digest(_unb64(sig_b64), hmac.new(_secret(), body, hashlib.sha256).digest())
        payload = json.loads(body) if good else None
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict) or payload.get("k") != "file" or not re.fullmatch(r"[a-f0-9]{32}", str(payload.get("s"))):
        raise _err("stage_bad_token")
    return payload


def stage_id(token: str) -> str:
    """The stage id of a token (``DELETE /helper/files/{sid}``)."""
    return str(_verify(token)["s"])


def _dir() -> Path:
    d = Path(get_settings().upload_dir) / "helper-stage"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _tag(user_id: int) -> str:
    return hmac.new(_secret(), f"owner:{user_id}".encode(), hashlib.sha256).hexdigest()[:12]


def session_tag(request: Any, user: Any) -> str:
    """The sign-in session a token is bound to: the AU-15 session row and the token version."""
    from app.services import sessions

    return f"{sessions.current_id(request) or 0}:{int(getattr(user, 'token_version', 0) or 0)}"


@dataclass
class Staged:
    token: str
    sid: str
    expires_at: datetime
    size: int
    format: str


def _write_private(path: Path, blob: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(blob)


def clear(user_id: int) -> int:
    """Delete every stage of one person (a new classify, sign-out)."""
    n = 0
    for p in _dir().glob(f"{_tag(user_id)}-*"):
        if p.suffix in (".bin", ".claimed"):
            p.unlink(missing_ok=True)
            n += 1
    return n


def stage(
    data: bytes, sig: Signals, kinds: list[str], user_id: int, sess: str, *, replace: bool = True
) -> Staged:
    """Encrypt ``data`` under a fresh key that only the returned token carries; mode 0600; 10 minutes."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if replace:
        clear(user_id)
    sid = secrets.token_hex(16)
    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)
    meta = json.dumps(
        {"sig": sig.to_dict(), "kinds": kinds, "fmt": sig.card_format, "ext": sig.ext, "size": len(data),
         "sha": sig.sha256, "uid": user_id},
        separators=(",", ":"),
    ).encode("utf-8")
    n1, n2 = secrets.token_bytes(12), secrets.token_bytes(12)
    meta_ct = aes.encrypt(n1, meta, sid.encode())
    data_ct = aes.encrypt(n2, data, sid.encode())
    blob = _MAGIC + len(meta_ct).to_bytes(4, "big") + n1 + meta_ct + n2 + data_ct
    _write_private(_dir() / f"{_tag(user_id)}-{sid}.bin", blob)
    exp = int(now()) + STAGE_TTL_S
    token = _sign({"k": "file", "s": sid, "u": user_id, "ss": sess, "key": _b64(key), "e": exp})
    return Staged(token, sid, datetime.fromtimestamp(exp, UTC).replace(tzinfo=None), len(data), sig.card_format)


def _check(token: str, user_id: int, sess: str) -> dict[str, Any]:
    p = _verify(token)
    if p.get("u") != user_id or p.get("ss") != sess:
        raise _err("stage_other_user")
    if int(p.get("e") or 0) <= now():
        raise _err("stage_expired")
    return p


def _paths(p: dict[str, Any]) -> tuple[Path, Path, Path]:
    base = _dir() / f"{_tag(int(p['u']))}-{p['s']}"
    return base.with_suffix(".bin"), base.with_suffix(".claimed"), base.with_suffix(".used")


def _decrypt(blob: bytes, p: dict[str, Any], *, with_data: bool) -> tuple[dict[str, Any], bytes]:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(_MAGIC):
        raise _err("stage_bad_token")
    aes = AESGCM(_unb64(str(p["key"])))
    i = len(_MAGIC)
    ln = int.from_bytes(blob[i : i + 4], "big")
    n1, meta_ct = blob[i + 4 : i + 16], blob[i + 16 : i + 16 + ln]
    rest = blob[i + 16 + ln :]
    try:
        meta = json.loads(aes.decrypt(n1, meta_ct, str(p["s"]).encode()))
        data = aes.decrypt(rest[:12], rest[12:], str(p["s"]).encode()) if with_data else b""
    except (InvalidTag, ValueError) as exc:
        raise _err("stage_bad_token") from exc
    return meta, data


def _gone(used: Path) -> StageError:
    return _err("stage_used") if used.exists() else _err("stage_expired")


def peek(token: str, user_id: int, sess: str, *, with_data: bool = False) -> tuple[dict[str, Any], bytes]:
    """The stage's metadata (and bytes) without consuming it (chooser pick, hand-over)."""
    p = _check(token, user_id, sess)
    path, _claimed, used = _paths(p)
    try:
        blob = path.read_bytes()
    except FileNotFoundError as exc:
        raise _gone(used) from exc
    return _decrypt(blob, p, with_data=with_data)


def consume(token: str, user_id: int, sess: str) -> tuple[dict[str, Any], bytes]:
    """Claim the stage once (atomic rename), decrypt, delete. 403 another person or session, 410 used / expired."""
    p = _check(token, user_id, sess)
    path, claimed, used = _paths(p)
    try:
        os.rename(path, claimed)
    except FileNotFoundError as exc:
        raise _gone(used) from exc
    try:
        meta, data = _decrypt(claimed.read_bytes(), p, with_data=True)
    finally:
        claimed.unlink(missing_ok=True)
        if not used.exists():
            _write_private(used, b"")  # the tombstone: a second use says "used", not "expired"
    return meta, data


def delete(sid: str, user_id: int) -> bool:
    if not re.fullmatch(r"[a-f0-9]{32}", sid):
        return False
    gone = False
    for suffix in (".bin", ".claimed"):
        p = _dir() / f"{_tag(user_id)}-{sid}{suffix}"
        if p.exists():
            p.unlink(missing_ok=True)
            gone = True
    return gone


def sweep() -> int:
    """Delete every stage (and tombstone) older than 10 minutes; returns how many files went."""
    d = Path(get_settings().upload_dir) / "helper-stage"
    if not d.is_dir():
        return 0
    n = 0
    t = now()
    for p in d.iterdir():
        try:
            if p.is_file() and t - p.stat().st_mtime > STAGE_TTL_S:
                p.unlink(missing_ok=True)
                n += 1
        except OSError:
            continue
    return n


_sweeper: asyncio.Task[None] | None = None


async def _sweep_loop(interval: float) -> None:
    while True:
        try:
            await asyncio.to_thread(sweep)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failing sweep must never stop the app
            log.exception("helper stage sweep failed")
        await asyncio.sleep(interval)


def start_sweeper(interval: float = 60.0) -> None:
    """Every minute (and once now, at start-up)."""
    global _sweeper
    if _sweeper is None or _sweeper.done():
        _sweeper = asyncio.create_task(_sweep_loop(interval), name="helper-file-stage-sweeper")


async def stop_sweeper() -> None:
    global _sweeper
    if _sweeper is not None:
        _sweeper.cancel()
        try:
            await _sweeper
        except asyncio.CancelledError:
            pass
        _sweeper = None


def telemetry(kind: str | None, score: float | None, fmt: str, ms: float, state: str) -> None:
    """``helper.files.classified`` without content (a log line; classify writes no database row)."""
    log.info(
        "helper.files.classified kind=%s band=%s format=%s ms=%d state=%s",
        kind or "-",
        band(score) if score is not None else "-",
        fmt,
        int(ms),
        state,
    )


__all__ = [
    "CouncilHit",
    "KINDS",
    "RATE_PER_MINUTE",
    "STAGE_TTL_S",
    "Signals",
    "StageError",
    "all_labels_tr",
    "band",
    "build",
    "candidates",
    "consume",
    "decide",
    "delete",
    "now",
    "peek",
    "read_file",
    "read_signals",
    "reset_rate_limit",
    "stage",
    "stage_id",
    "sweep",
]
