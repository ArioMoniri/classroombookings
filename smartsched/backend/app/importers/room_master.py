"""Room master: the planner's authoritative room list (``python -m app.cli import room-master file.csv`` or
``POST /api/v1/imports/room-master``; a CSV, or an ``.xlsx`` whose first sheet has the same columns).

Columns (header row required, order free, ``;`` or ``,`` delimited, UTF-8 with or without BOM):

``code, capacity, exam_capacity, tags, building, floor, bookable[, notes]``

* ``code``: any spelling the importers understand (``A 101``, ``C z01``, ``B Blok Bilg. Lab.``).
* ``capacity`` / ``exam_capacity``: integers; an empty cell leaves the stored value unchanged.
* ``tags``: ``PC``, ``TIP``, … separated by ``|``, ``;``, ``/`` or spaces; the cell *replaces* the tag
  list (``-`` clears it); empty = unchanged.
* ``building``: building code (``A``); ``floor``: free text (``0`` = ground floor).
* ``bookable``: ``1/0``, ``yes/no``, ``true/false``, ``evet/hayır``; empty = derived (bookable when the
  room has a capacity).
* Lines starting with ``#`` are comments.

Values set here are marked in ``custom_fields.master`` and are never overwritten by a later workbook
import (the workbook value is reported as a warning instead).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_files import Limits, UnsafeFileError, is_zip_container, open_workbook, run_isolated
from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.importers.report import ImportReport

COLUMNS = ("code", "capacity", "exam_capacity", "tags", "building", "floor", "bookable", "notes")
_TRUE = {"1", "yes", "y", "true", "evet", "e", "x"}
_FALSE = {"0", "no", "n", "false", "hayır", "hayir", "h"}


def _bool(value: str | None) -> bool | None:
    v = n.tr_casefold(value or "").strip()
    if not v:
        return None
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"not a yes/no value: {value!r}")


def _int(value: str | None) -> int | None:
    v = (value or "").strip()
    if not v:
        return None
    out = n.parse_int_loose(v)
    if out is None or out < 0:
        raise ValueError(f"not a non-negative integer: {value!r}")
    return out


def _tags(value: str | None) -> list[str] | None:
    v = (value or "").strip()
    if not v:
        return None
    if v == "-":
        return []
    parts = [n.tr_upper(t.strip()) for t in v.replace("|", " ").replace(";", " ").replace("/", " ").split()]
    return list(dict.fromkeys(p for p in parts if p))


def parse_room_master(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse the CSV text into row dicts (typed values, ``None`` = unchanged) and error strings."""
    lines = [ln for ln in text.lstrip("﻿").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return [], ["empty room master"]
    dialect = csv.Sniffer().sniff(lines[0], delimiters=",;\t")
    reader = csv.DictReader(io.StringIO("\n".join(lines)), dialect=dialect)
    header = [n.tr_casefold(h or "").strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    if "code" not in header:
        return [], [f"room master needs a 'code' column; got {header}"]
    unknown = [h for h in header if h and h not in COLUMNS]
    errors: list[str] = [f"unknown column(s) ignored: {unknown}"] if unknown else []
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(reader, start=2):
        codes = n.parse_room_codes(raw.get("code"))
        if len(codes) != 1:
            errors.append(f"line {i}: cannot read room code {raw.get('code')!r}")
            continue
        try:
            rows.append(
                {
                    "line": i,
                    "code": codes[0],
                    "capacity": _int(raw.get("capacity")),
                    "exam_capacity": _int(raw.get("exam_capacity")),
                    "tags": _tags(raw.get("tags")),
                    "building": (raw.get("building") or "").strip().upper() or None,
                    "floor": (raw.get("floor") or "").strip() or None,
                    "bookable": _bool(raw.get("bookable")),
                    "notes": (raw.get("notes") or "").strip() or None,
                }
            )
        except ValueError as exc:
            errors.append(f"line {i}: {exc}")
    return rows, errors


def xlsx_to_csv_text(path: str | Path) -> str:
    """The first sheet of a room-master workbook as ``;`` separated text (header row first), read with the
    safe workbook reader (zip pre-inspection, row / column caps)."""
    wb = open_workbook(path, read_only=True, data_only=True, max_rows=5000, max_cols=len(COLUMNS) + 4)
    try:
        ws = wb.worksheets[0]
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";", lineterminator="\n")
        for values in ws.iter_rows(values_only=True):
            cells = [
                "" if v is None else str(int(v)) if isinstance(v, float) and v.is_integer() else str(v) for v in values
            ]
            if any(c.strip() for c in cells):
                writer.writerow(cells)
        return buf.getvalue()
    finally:
        wb.close()


def read_room_master_text(path: str | Path) -> str:
    """CSV text of a room master: UTF-8 (with or without BOM), else Windows-1254 (Turkish Excel's "CSV"
    export); ``.xlsx`` / ``.xlsm`` workbooks are converted from their first sheet."""
    if is_zip_container(Path(path).name):
        return xlsx_to_csv_text(path)
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1254")


async def import_room_master(session: AsyncSession, path: str | Path, *, filename: str | None = None) -> ImportReport:
    """Apply a room master (CSV or xlsx, see the module doc) - the CLI ``import room-master`` and
    ``POST /imports/room-master``."""
    report = ImportReport(kind="room-master", filename=filename or Path(path).name)
    cap = Limits.from_settings().max_upload_bytes
    if Path(path).stat().st_size > cap:
        raise UnsafeFileError(413, f"room master larger than {cap // (1024 * 1024)} MiB")
    if is_zip_container(Path(path).name):
        text = await run_isolated(xlsx_to_csv_text, path)  # off the loop, memory-capped child
    else:
        text = read_room_master_text(path)
    rows, errors = parse_room_master(text)
    for e in errors:
        report.warn(e)
    report.rows_total = len(rows) + sum(1 for e in errors if e.startswith("line "))
    cat = Catalog(session, report)
    seen: set[str] = set()
    for r in rows:
        if r["code"] in seen:
            report.warn(f"line {r['line']}: duplicate room {r['code']}; last one wins")
        seen.add(r["code"])
        room = await cat.room(r["code"])
        assert room is not None
        fields = dict(room.custom_fields or {})
        master = set(fields.get("master") or [])
        changed = False
        for attr in ("capacity", "exam_capacity"):
            if r[attr] is not None:
                master.add(attr)
                if getattr(room, attr) != r[attr]:
                    setattr(room, attr, r[attr])
                    changed = True
        if r["tags"] is not None and list(room.tags or []) != r["tags"]:
            room.tags = r["tags"]
            changed = True
        if r["building"]:
            b = await cat.building(r["building"])
            if room.building_id != b.id:
                room.building_id = b.id
                changed = True
        if r["floor"] is not None and room.floor != r["floor"]:
            room.floor = r["floor"]
            changed = True
        if r["notes"] and room.notes != r["notes"]:
            room.notes = r["notes"]
            changed = True
        bookable = r["bookable"]
        if bookable is None:
            bookable = bool(room.capacity or room.exam_capacity)
        if room.is_bookable != bookable:
            room.is_bookable = bookable
            changed = True
        fields.pop("auto_unbookable", None)
        fields["master"] = sorted(master)
        fields["capacity_source"] = f"room-master:{report.filename}"
        if fields != (room.custom_fields or {}):
            room.custom_fields = fields
            changed = True
        if changed:
            report.updated["rooms"] += 1
        report.rows_imported += 1
    no_cap = sorted(r["code"] for r in rows if r["code"] in cat.touched_rooms and not _has_capacity(cat, r["code"]))
    if no_cap:
        report.warn(f"{len(no_cap)} room(s) in the master still have no capacity: {', '.join(no_cap)}")
    report.extra["rooms"] = len(seen)
    await session.commit()
    return report


def _has_capacity(cat: Catalog, code: str) -> bool:
    room = cat._rooms[code]
    return bool(room.capacity or room.exam_capacity)


__all__ = ["COLUMNS", "import_room_master", "parse_room_master", "read_room_master_text", "xlsx_to_csv_text"]
