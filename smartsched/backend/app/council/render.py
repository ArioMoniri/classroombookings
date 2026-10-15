"""Intake agent, deterministic part: detect the format and render a file into grids and text units.

Every uploaded file becomes a :class:`Rendered`:

* ``grids``: rectangular cell matrices (strings) for workbook sheets, CSV/TSV/JSON tables, DOCX tables
  and tables recovered from a PDF's text layer. Merged ranges are forward-filled and kept as metadata,
  and trailing empty rows and columns are trimmed.
* ``units``: numbered text units (DOCX paragraphs, PDF/TXT lines that are not table rows), each with a
  source reference.
* ``needs_vision``: the file has no machine-readable text (an image or a scanned PDF). Only the
  model can read it (:func:`app.council.llm.transcribe`).

Workbooks are read with openpyxl in read-only mode (fast, bounded memory, even when Excel reports
16k used columns). Merged ranges come from the sheet XML directly, because read-only mode does not
expose them.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from app.council import text as tx

MAX_ROWS = 20000
MAX_COLS = 400
SCAN_ROWS = 80

FORMATS: dict[str, str] = {
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".csv": "csv",
    ".tsv": "csv",
    ".txt": "txt",
    ".md": "txt",
    ".docx": "docx",
    ".pdf": "pdf",
    ".json": "json",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
}
UNSUPPORTED_HINTS = {
    ".xls": "legacy .xls workbooks are not read; save the file as .xlsx",
    ".ods": "OpenDocument spreadsheets are not read; save the file as .xlsx",
    ".doc": "legacy .doc files are not read; save the file as .docx",
    ".pptx": "presentations are not read; export the slides as PDF",
}
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


class RenderError(ValueError):
    """Unsupported or unreadable file (reported on the file, never fatal for the job)."""


@dataclass
class Grid:
    name: str
    kind: str  # sheet | csv | table | page | json | vision
    cells: list[list[str]]
    merged: list[tuple[int, int, int, int]] = field(default_factory=list)  # r1, c1, r2, c2 (0-based, inclusive)
    origin: dict[str, Any] = field(default_factory=dict)  # {"sheet": ...} / {"page": 2} / {"table": 1}
    #: cells[r][c] is the source's row ``row_numbers[r]`` (1-based) and column ``c + 1``
    row_numbers: list[int] = field(default_factory=list)
    #: per-row reference overrides (PDF tables continued over pages: ``{"page": 3, "line": 12}``)
    row_meta: list[dict[str, Any]] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.cells)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.cells), default=0)

    def cell(self, r: int, c: int) -> str:
        if 0 <= r < len(self.cells) and 0 <= c < len(self.cells[r]):
            return self.cells[r][c]
        return ""

    def row_number(self, r: int) -> int:
        return self.row_numbers[r] if r < len(self.row_numbers) else r + 1

    def ref(self, r: int, c: int | None = None) -> dict[str, Any]:
        if r < len(self.row_meta):
            out: dict[str, Any] = {**self.row_meta[r]}
        else:
            out = {**self.origin, "row": self.row_number(r)}
        if c is not None:
            out["col"] = c + 1
            if self.kind in ("sheet",):
                out["cell"] = f"{col_letter(c)}{self.row_number(r)}"
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "rows": self.n_rows,
            "cols": self.n_cols,
            "merged": len(self.merged),
        }


@dataclass
class Unit:
    ref: dict[str, Any]
    text: str


@dataclass
class Rendered:
    filename: str
    format: str
    sha256: str
    size: int
    grids: list[Grid] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    needs_vision: bool = False
    media_type: str | None = None
    language: str = "und"
    language_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "format": self.format,
            "sha256": self.sha256,
            "size": self.size,
            "language": self.language,
            "language_confidence": self.language_confidence,
            "needs_vision": self.needs_vision,
            "grids": [g.summary() for g in self.grids],
            "units": len(self.units),
            "warnings": self.warnings,
        }


def col_letter(c: int) -> str:
    s = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        s = chr(65 + rem) + s
    return s


def _ref_to_rc(ref: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref)
    if not m:
        raise ValueError(ref)
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return int(m.group(2)) - 1, col - 1


def detect_format(filename: str, data: bytes) -> str:
    ext = PurePath(filename or "upload").suffix.lower()
    if ext in UNSUPPORTED_HINTS:
        raise RenderError(UNSUPPORTED_HINTS[ext])
    fmt = FORMATS.get(ext)
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
        return "image"
    if data[:2] == b"PK" and fmt not in ("xlsx", "docx"):
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            names = []
        if any(nm.startswith("xl/") for nm in names):
            return "xlsx"
        if any(nm.startswith("word/") for nm in names):
            return "docx"
    if fmt is None:
        raise RenderError(f"unsupported file type '{ext or '?'}'")
    return fmt


def _trim(rows: list[list[str]], numbers: list[int]) -> tuple[list[list[str]], list[int]]:
    width = 0
    for r in rows:
        for c in range(len(r) - 1, -1, -1):
            if r[c]:
                width = max(width, c + 1)
                break
    out = [r[:width] + [""] * (width - len(r[:width])) for r in rows]
    while out and not any(out[-1]):
        out.pop()
        numbers = numbers[: len(out)]
    return out, numbers[: len(out)]


# ---------------------------------------------------------------------------
# xlsx
# ---------------------------------------------------------------------------


def _sheet_merges(data: bytes) -> dict[str, list[tuple[int, int, int, int]]]:
    """Sheet title -> merged ranges, read from the workbook XML (read-only openpyxl hides them)."""
    out: dict[str, list[tuple[int, int, int, int]]] = {}
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        wb_xml = zf.read("xl/workbook.xml").decode("utf-8", "replace")
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile):
        return out
    targets = dict(re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    targets.update({k: v for v, k in re.findall(r'<Relationship[^>]*Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
    for name, rid in re.findall(r'<sheet\b[^>]*name="([^"]*)"[^>]*r:id="([^"]+)"', wb_xml):
        target = targets.get(rid)
        if not target:
            continue
        path = target.lstrip("/")
        path = path if path.startswith("xl/") else f"xl/{path}"
        try:
            xml = zf.read(path).decode("utf-8", "replace")
        except KeyError:
            continue
        ranges: list[tuple[int, int, int, int]] = []
        for ref in re.findall(r'<mergeCell\s+ref="([A-Z]+\d+:[A-Z]+\d+)"', xml):
            a, b = ref.split(":")
            r1, c1 = _ref_to_rc(a)
            r2, c2 = _ref_to_rc(b)
            ranges.append((r1, c1, r2, c2))
        title = (
            name.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&apos;", "'")
        )
        out[title] = ranges
    return out


def _xlsx(data: bytes, out: Rendered) -> None:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - reported on the file
        raise RenderError(f"cannot read workbook: {type(exc).__name__}") from exc
    merges = _sheet_merges(data)
    try:
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                out.warnings.append(f"sheet '{ws.title}' is hidden in the workbook; it was read anyway")
            # bound the width by what the first rows actually use (formatting inflates max_column)
            width = 0
            for row in ws.iter_rows(min_row=1, max_row=SCAN_ROWS, max_col=MAX_COLS, values_only=True):
                for c in range(len(row) - 1, -1, -1):
                    if row[c] is not None and tx.cell_text(row[c]):
                        width = max(width, c + 1)
                        break
            sheet_merges = [m for m in merges.get(ws.title, []) if m[0] < MAX_ROWS and m[1] < MAX_COLS]
            width = max([width] + [m[3] + 1 for m in sheet_merges if m[3] < MAX_COLS])
            if width == 0:
                continue
            rows: list[list[str]] = []
            for row in ws.iter_rows(min_row=1, max_col=width, values_only=True):
                rows.append([tx.cell_text(v) for v in row] + [""] * (width - len(row)))
                if len(rows) >= MAX_ROWS:
                    out.warnings.append(f"sheet '{ws.title}': only the first {MAX_ROWS} rows were read")
                    break
            numbers = list(range(1, len(rows) + 1))
            for r1, c1, r2, c2 in sheet_merges:  # forward-fill merged ranges
                if r1 >= len(rows):
                    continue
                v = rows[r1][c1] if c1 < len(rows[r1]) else ""
                for r in range(r1, min(r2, len(rows) - 1) + 1):
                    for c in range(c1, min(c2, width - 1) + 1):
                        rows[r][c] = v
            rows, numbers = _trim(rows, numbers)
            if rows:
                out.grids.append(Grid(ws.title, "sheet", rows, sheet_merges, {"sheet": ws.title}, numbers))
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# csv / tsv / json / txt
# ---------------------------------------------------------------------------


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    for enc in ("cp1254", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _delimited(text: str, name: str, out: Rendered) -> bool:
    # leading "# ..." comment lines (room master style) are kept as units, not table rows
    lines = text.splitlines()
    skip = 0
    while skip < len(lines) and lines[skip].lstrip().startswith("#"):
        skip += 1
    body = "\n".join(lines[skip:])
    try:
        dialect: Any = csv.Sniffer().sniff(body[:8192], delimiters=",;\t|")
    except csv.Error:
        return False
    rows = [[tx.cell_text(c) for c in r] for r in csv.reader(io.StringIO(body), dialect)]
    if len(rows) < 2 or max((len(r) for r in rows[:20]), default=0) < 2:
        return False
    for i in range(skip):
        t = tx.cell_text(lines[i].lstrip("# "))
        if t:
            out.units.append(Unit({"line": i + 1}, t))
    numbers = list(range(skip + 1, skip + len(rows) + 1))
    rows, numbers = _trim(rows[:MAX_ROWS], numbers[:MAX_ROWS])
    out.grids.append(Grid(name, "csv", rows, [], {}, numbers))
    return True


def _json(data: bytes, out: Rendered) -> None:
    try:
        obj = json.loads(decode(data))
    except json.JSONDecodeError as exc:
        raise RenderError(f"invalid JSON: {exc.msg}") from exc
    tables: list[tuple[str, list[Any]]] = []
    if isinstance(obj, list):
        tables.append(("records", obj))
    elif isinstance(obj, dict):
        tables.extend((k, v) for k, v in obj.items() if isinstance(v, list))
    for name, items in tables:
        dicts = [i for i in items if isinstance(i, dict)]
        if not dicts:
            continue
        keys = list(dict.fromkeys(k for d in dicts for k in d))
        rows = [keys] + [[tx.cell_text(d.get(k)) for k in keys] for d in dicts[:MAX_ROWS]]
        out.grids.append(Grid(name, "json", rows, [], {"table": name}, list(range(1, len(rows) + 1))))


def _txt(data: bytes, out: Rendered, filename: str) -> None:
    text = decode(data)
    if _delimited(text, filename, out):
        return
    for i, line in enumerate(text.splitlines(), start=1):
        line = tx.cell_text(line.lstrip("#*->• \t"))
        if line:
            out.units.append(Unit({"line": i}, line))


# ---------------------------------------------------------------------------
# docx
# ---------------------------------------------------------------------------


def _docx(data: bytes, out: Rendered) -> None:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - backend dependency
        raise RenderError("python-docx is not installed on the server") from exc
    try:
        doc = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"cannot read document: {type(exc).__name__}") from exc
    n = 0
    for p in doc.paragraphs:
        t = tx.cell_text(p.text)
        if t:
            n += 1
            out.units.append(Unit({"paragraph": n}, t))
    for t_index, table in enumerate(doc.tables, start=1):
        rows = [[tx.cell_text(c.text) for c in row.cells] for row in table.rows]
        numbers = list(range(1, len(rows) + 1))
        rows, numbers = _trim(rows, numbers)
        if rows:
            out.grids.append(Grid(f"table {t_index}", "table", rows, [], {"table": t_index}, numbers))


# ---------------------------------------------------------------------------
# pdf (text layer; scans are flagged for the vision path)
# ---------------------------------------------------------------------------

_COL_SPLIT = re.compile(r"\S(?:.*?\S)?(?=\s{2,}|$)")


def _line_cells(line: str) -> list[tuple[int, str]]:
    """(start column, text) of the space-separated cells of a layout line (2+ spaces separate cells)."""
    return [(m.start(), m.group(0).strip()) for m in _COL_SPLIT.finditer(line) if m.group(0).strip()]


def _pdf_tables(lines: list[str], page: int) -> tuple[list[Grid], list[Unit]]:
    """Runs of >= 3 consecutive lines with >= 3 cells become one table; columns are aligned on the
    header line's start positions (cells snap to the nearest header column)."""
    grids: list[Grid] = []
    units: list[Unit] = []
    i = 0
    t_index = 0
    while i < len(lines):
        cells = _line_cells(lines[i])
        if len(cells) >= 3:
            j = i
            block: list[tuple[int, list[tuple[int, str]]]] = []
            while j < len(lines) and len(_line_cells(lines[j])) >= 2:
                block.append((j, _line_cells(lines[j])))
                j += 1
            if len(block) >= 3:
                t_index += 1
                starts = [s for s, _ in max(block[:3], key=lambda b: len(b[1]))[1]]
                rows: list[list[str]] = []
                numbers: list[int] = []
                meta: list[dict[str, Any]] = []
                for line_no, cs in block:
                    row = [""] * len(starts)
                    for s, t in cs:
                        k = min(range(len(starts)), key=lambda q: abs(starts[q] - s))
                        row[k] = (row[k] + " " + t).strip()
                    rows.append(row)
                    numbers.append(line_no + 1)
                    meta.append({"page": page, "line": line_no + 1})
                grids.append(Grid(f"page {page} table {t_index}", "page", rows, [], {"page": page}, numbers, meta))
                i = j
                continue
        text = tx.cell_text(lines[i])
        if len(text) >= 3:
            units.append(Unit({"page": page, "line": i + 1}, re.sub(r"\s{2,}", " ", text)))
        i += 1
    return grids, units


def _pdf(data: bytes, out: Rendered) -> None:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - backend dependency
        raise RenderError("pypdf is not installed on the server") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                pages.append((i, page.extract_text(extraction_mode="layout") or ""))
            except Exception:  # noqa: BLE001 - layout mode fails on some producers; plain mode is enough
                pages.append((i, page.extract_text() or ""))
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"cannot read PDF: {type(exc).__name__}") from exc
    page_grids: list[Grid] = []
    for page_no, text in pages:
        grids, units = _pdf_tables(text.splitlines(), page_no)
        page_grids.extend(grids)
        out.units.extend(units)
    # a table continued over pages repeats its header: merge pages with the same header into one grid
    merged: list[Grid] = []
    for g in page_grids:
        if merged and merged[-1].cells and g.cells and merged[-1].cells[0] == g.cells[0]:
            prev = merged[-1]
            prev.cells.extend(g.cells[1:])
            prev.row_numbers.extend(g.row_numbers[1:])
            prev.row_meta.extend(g.row_meta[1:])
            first = prev.row_meta[0].get("page") if prev.row_meta else prev.origin.get("page")
            prev.name = f"pages {first}-{g.origin.get('page')} table"
            continue
        merged.append(g)
    out.grids.extend(merged)
    if pages and not out.grids and not out.units:
        out.needs_vision = True
        out.media_type = "application/pdf"
        out.warnings.append("the PDF has no text layer (scanned?); it can only be read by the AI model")


def render_file(data: bytes, filename: str) -> Rendered:
    """Bytes -> :class:`Rendered` (no model call). Raises :class:`RenderError`."""
    name = PurePath(filename or "upload").name
    if not data:
        raise RenderError("the file is empty")
    fmt = detect_format(name, data)
    out = Rendered(name, fmt, hashlib.sha256(data).hexdigest(), len(data))
    if fmt == "xlsx":
        _xlsx(data, out)
    elif fmt == "csv":
        if not _delimited(decode(data), name, out):
            _txt(data, out, name)
    elif fmt == "txt":
        _txt(data, out, name)
    elif fmt == "json":
        _json(data, out)
    elif fmt == "docx":
        _docx(data, out)
    elif fmt == "pdf":
        _pdf(data, out)
    elif fmt == "image":
        out.needs_vision = True
        ext = PurePath(name).suffix.lower().lstrip(".")
        out.media_type = IMAGE_TYPES.get(ext, "image/png" if data[:4] == b"\x89PNG" else "image/jpeg")
    sample: list[str] = []
    for g in out.grids:
        for row in g.cells[:40]:
            sample.extend(row)
    sample.extend(u.text for u in out.units[:200])
    out.language, out.language_confidence = tx.detect_language(sample)
    return out


__all__ = ["Grid", "Rendered", "RenderError", "Unit", "col_letter", "detect_format", "render_file"]
