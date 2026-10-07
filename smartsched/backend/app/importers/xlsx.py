"""openpyxl helpers: read-only row streaming restricted to populated columns, header mapping."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openpyxl

from app.importers.normalize import clean_text, tr_casefold

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


def iter_sheet_rows(
    path: str | Path, sheet: str | int = 0, max_col: int = 40
) -> tuple[list[str | None], Iterator[tuple[int, tuple[Any, ...]]]]:
    """Return (headers, iterator of (excel_row_number, values)) for a long-table sheet.

    The workbook is opened read-only (the planning lists report 16 k columns because of formatting);
    only the first ``max_col`` columns are read and trailing all-empty rows are skipped.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if isinstance(sheet, str) else wb.worksheets[sheet]
    rows = ws.iter_rows(min_row=1, max_col=max_col, values_only=True)
    header_raw = next(rows)
    headers: list[str | None] = [clean_text(h) for h in header_raw]
    last_col = max((i + 1 for i, h in enumerate(headers) if h), default=0)
    # allow one unnamed trailing column (Bahar list has extra remote-education notes)
    width = min(max_col, last_col + 1)
    headers = headers[:width]

    def gen() -> Iterator[tuple[int, tuple[Any, ...]]]:
        try:
            for idx, values in enumerate(rows, start=2):
                vals = values[:width]
                if not any(v is not None and clean_text(v) is not None for v in vals):
                    continue
                yield idx, vals
        finally:
            wb.close()

    return headers, gen()


def map_headers(headers: list[str | None], spec: dict[str, list[str]]) -> dict[str, int]:
    """Map logical field names to column indexes by substring match on casefolded header text.

    ``spec`` maps field -> list of candidate substrings; the first header containing one wins.
    A candidate starting with ``=`` must match the whole header exactly.
    """
    folded = [tr_casefold(h) if h else "" for h in headers]
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for field_name, candidates in spec.items():
        for cand in candidates:
            exact = cand.startswith("=")
            needle = tr_casefold(cand[1:] if exact else cand)
            for i, h in enumerate(folded):
                if i in used or not h:
                    continue
                if (h == needle) if exact else (needle in h):
                    mapping[field_name] = i
                    used.add(i)
                    break
            if field_name in mapping:
                break
    return mapping


def row_dict(headers: list[str | None], values: tuple[Any, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i, v in enumerate(values):
        if v is None:
            continue
        key = headers[i] if i < len(headers) and headers[i] else f"col_{i + 1}"
        out[key] = v if isinstance(v, str | int | float | bool) else str(v)
    return out
