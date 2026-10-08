"""Bounded reading of small uploaded tables (.xlsx / .csv) into text cells.

Used by the studio's no-AI column mapping; it runs inside the parse child process
(:func:`app.core.safe_files.run_isolated`), so it imports nothing heavy and raises only
:class:`~app.core.safe_files.UnsafeFileError` (picklable).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time
from pathlib import PurePath
from typing import Any

from app.core.safe_files import UnsafeFileError, open_workbook
from app.importers.normalize import clean_text


def table_cell(v: Any) -> str:
    """Cell value -> trimmed text (dates ISO, times HH:MM, integral floats without ``.0``; NBSP folded)."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute) == (0, 0) else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return clean_text(v) or ""


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_table(
    data: bytes, filename: str, sheet: str | None, *, max_rows: int, max_cols: int
) -> tuple[list[str], str | None, list[tuple[int, list[str]]]]:
    """(sheet names, chosen sheet, [(1-based row number, cells)]) of at most ``max_rows`` x ``max_cols``."""
    suffix = PurePath(filename).suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        wb = open_workbook(data, read_only=True, data_only=True, max_rows=max_rows, max_cols=max_cols)
        try:
            names = [ws.title for ws in wb.worksheets]
            ws = wb[sheet] if sheet and sheet in names else wb.worksheets[0]
            it = ws.iter_rows(max_row=max_rows, max_col=max_cols, values_only=True)
            return names, ws.title, [(i, [table_cell(v) for v in row]) for i, row in enumerate(it, start=1)]
        finally:
            wb.close()
    if suffix == ".csv":
        text = decode_text(data)
        try:
            dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows: list[tuple[int, list[str]]] = []
        for i, r in enumerate(csv.reader(io.StringIO(text), dialect), start=1):
            if i > max_rows:
                break
            rows.append((i, [table_cell(c) for c in r[:max_cols]]))
        return [], None, rows
    raise UnsafeFileError(400, "the column-mapping fallback reads .xlsx and .csv files only")
