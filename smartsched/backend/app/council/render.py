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
expose them. Every OOXML container (``.xlsx`` / ``.docx``, by extension or sniffed) is pre-inspected with
:func:`app.core.safe_files.inspect_zip` (member count, expanded sizes, compression ratio, real sheet
extent) before any parser or ``zipfile.read`` touches it, and workbooks open through
:func:`app.core.safe_files.open_workbook` (dimensions clamped). The orchestrator runs :func:`render_file`
in :func:`app.core.safe_files.run_isolated` (child process, ``RLIMIT_AS``, wall-clock kill).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

from app.core import safe_files
from app.council import text as tx

MAX_ROWS = 20000
MAX_COLS = 400
SCAN_ROWS = 80

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
    #: the decimal mark of a delimited text file's numbers: "," for a ';'-separated (Turkish / European Excel)
    #: export, where "0,4" is the number 0.4 (app.council.formats.typed, R3-S-04)
    decimal: str = "."

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
    """Format name of an upload: magic bytes first, the extension only as a tie-break
    (:func:`app.council.formats.detect`). Raises :class:`RenderError` (unsupported, empty, "save as" hint)."""
    from app.council import formats

    return formats.detect_format(filename, data)


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
    try:
        wb = safe_files.open_workbook(data, read_only=True, data_only=True, max_rows=MAX_ROWS, max_cols=MAX_COLS)
    except safe_files.UnsafeFileError as exc:
        raise RenderError(exc.message) from exc
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
    """Bytes -> :class:`Rendered` (no model call) through the format registry (:mod:`app.council.formats`).
    Raises :class:`RenderError` (unsupported / unreadable) or :class:`app.core.safe_files.UnsafeFileError`
    (a cap or a forbidden construct: 400 / 413)."""
    from app.council import formats

    if not data:
        raise RenderError("the file is empty")
    return formats.render(data, filename)


__all__ = ["Grid", "Rendered", "RenderError", "Unit", "col_letter", "detect_format", "render_file"]
