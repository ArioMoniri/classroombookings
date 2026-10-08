"""Preference-file ingestion: .xlsx / .csv / .docx / .pdf / .txt / .md -> proposals + section edits.

The file is read locally (openpyxl, csv, python-docx, pypdf), split into numbered *units* (a sheet
row, a paragraph or table row, a PDF/text line), compacted, chunked and sent to the same strict
``propose_constraints`` round as the free-text prompt (:func:`app.ai.elicit.propose`). Every unit
carries a :class:`~app.schemas.ai.SourceRef` (filename, sheet, row / paragraph / page / line number,
excerpt) so the review UI can show "from file X row 12". Nothing is applied here.

Limits are explicit, never silent: files above :data:`MAX_FILE_BYTES` are refused; at most
:data:`MAX_UNITS` units and :data:`MAX_CHUNKS` model calls per file - anything beyond is reported in
``warnings`` and ``truncated=True``.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import PurePath
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.ai.elicit import propose
from app.ai.resolve import load_term_context
from app.core.safe_files import inspect_zip, open_workbook, run_isolated
from app.importers.normalize import tr_casefold
from app.schemas.ai import IngestOut, ProposedConstraint, ProposedSectionEdit, SourceRef, UsageOut

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNITS = 1500
MAX_TABLE_COLS = 100
MAX_PDF_PAGES = 200
MAX_UNIT_CHARS = 600
CHUNK_CHARS = 12000
MAX_CHUNKS = 8
SUPPORTED = {
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".csv": "csv",
    ".docx": "docx",
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "txt",
}

#: Header keywords per column role (Turkish + English, casefolded). Order = priority.
COLUMN_ROLES: dict[str, tuple[str, ...]] = {
    "course": ("ders kodu", "dersin kodu", "course code", "kod", "code", "ders", "course"),
    "section": ("şube", "sube", "section", "grup"),
    "program": ("program", "bölüm", "bolum", "department", "fakülte", "faculty"),
    "year": ("sınıf", "sinif", "class year", "year", "yıl"),
    "enrolment": ("öğrenci sayısı", "ogrenci sayisi", "kontenjan", "mevcut", "enrolment", "enrollment", "students"),
    "day": ("gün", "gun", "day"),
    "time": ("saat", "time", "period", "zaman"),
    "room": ("derslik", "salon", "room", "mekan", "yer", "venue"),
    "mode": ("eğitim şekli", "öğretim şekli", "mode", "uzem", "online"),
    "note": ("not", "açıklama", "aciklama", "talep", "istek", "tercih", "preference", "note", "comment", "remarks"),
}


class IngestError(ValueError):
    """Unsupported, empty, oversized or unreadable file (HTTP 400/413 at the API)."""


@dataclass
class Unit:
    ref: SourceRef
    text: str


@dataclass
class Extracted:
    file_kind: str
    units: list[Unit] = field(default_factory=list)
    columns: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False


def _cell(v: Any) -> str:
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
    return re.sub(r"\s+", " ", str(v)).strip()[:MAX_UNIT_CHARS]


def detect_columns(header: list[str]) -> dict[int, str]:
    """Column index -> role from header texts (each role at most once, best keyword first)."""
    roles: dict[int, str] = {}
    used: set[str] = set()
    keys = [tr_casefold(h or "") for h in header]
    for role, words in COLUMN_ROLES.items():
        best: tuple[int, int] | None = None  # (keyword rank, column)
        for col, key in enumerate(keys):
            if not key or col in roles:
                continue
            for rank, w in enumerate(words):
                if key == w or re.search(rf"(^|\W){re.escape(w)}(\W|$)", key):
                    if best is None or rank < best[0]:
                        best = (rank, col)
                    break
        if best is not None and role not in used:
            roles[best[1]] = role
            used.add(role)
    return roles


def _find_header(rows: list[list[str]]) -> int | None:
    """Index of the most header-like row among the first 15 (>= 2 recognised roles)."""
    best: tuple[int, int] | None = None
    for i, row in enumerate(rows[:15]):
        n = len(detect_columns(row))
        if n >= 2 and (best is None or n > best[0]):
            best = (n, i)
    return best[1] if best else None


def _table_units(rows: list[tuple[int, list[str]]], filename: str, sheet: str | None, out: Extracted) -> None:
    """Rows (1-based row number, cells) -> units ``role=value | ...`` using the detected header."""
    plain = [cells for _, cells in rows]
    h = _find_header(plain)
    roles: dict[int, str] = {}
    headers: list[str] = []
    if h is not None:
        headers = plain[h]
        roles = detect_columns(headers)
        for col, role in roles.items():
            out.columns.setdefault(role, headers[col])
    for i, (rownum, cells) in enumerate(rows):
        if h is not None and i <= h:
            continue
        if not any(cells):
            continue
        parts: list[str] = []
        for col, val in enumerate(cells):
            if not val:
                continue
            if col in roles:
                parts.append(f"{roles[col]}={val}")
            elif headers and col < len(headers) and headers[col]:
                parts.append(f"{headers[col][:30]}={val}")
            else:
                parts.append(val)
        text = " | ".join(parts)[:MAX_UNIT_CHARS]
        out.units.append(
            Unit(SourceRef(filename=filename, kind="row", ref=rownum, sheet=sheet, excerpt=text[:200]), text)
        )


def _xlsx(data: bytes, filename: str) -> Extracted:
    out = Extracted("xlsx")
    # zip pre-inspection + clamped sheet dimensions (app/core/safe_files.py, review B1)
    wb = open_workbook(data, read_only=True, data_only=True, max_rows=MAX_UNITS + 16, max_cols=MAX_TABLE_COLS)
    try:
        for ws in wb.worksheets:
            rows: list[tuple[int, list[str]]] = []
            it = ws.iter_rows(max_row=MAX_UNITS + 16, max_col=MAX_TABLE_COLS, values_only=True)
            for rownum, row in enumerate(it, start=1):
                rows.append((rownum, [_cell(v) for v in row]))
                if len(rows) > MAX_UNITS + 15:
                    break
            _table_units(rows, filename, ws.title if len(wb.worksheets) > 1 else None, out)
    finally:
        wb.close()
    return out


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _csv(data: bytes, filename: str) -> Extracted:
    out = Extracted("csv")
    text = _decode(data)
    try:
        dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [(i, [_cell(c) for c in r]) for i, r in enumerate(csv.reader(io.StringIO(text), dialect), start=1)]
    _table_units(rows[: MAX_UNITS + 15], filename, None, out)
    return out


def _docx(data: bytes, filename: str) -> Extracted:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - listed as a backend dependency
        raise IngestError("python-docx is not installed on the server") from exc
    out = Extracted("docx")
    inspect_zip(data, kind="document")  # a .docx is a zip too: refuse bombs before python-docx expands it
    try:
        doc = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"cannot read document: {type(exc).__name__}") from exc
    n = 0
    for p in doc.paragraphs:
        text = _cell(p.text)
        if not text:
            continue
        n += 1
        out.units.append(Unit(SourceRef(filename=filename, kind="paragraph", ref=n, excerpt=text[:200]), text))
    for t_index, table in enumerate(doc.tables, start=1):
        rows = [(r_index, [_cell(c.text) for c in row.cells]) for r_index, row in enumerate(table.rows, start=1)]
        _table_units(rows, filename, f"table {t_index}", out)
    return out


def _pdf(data: bytes, filename: str) -> Extracted:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - listed as a backend dependency
        raise IngestError("pypdf is not installed on the server") from exc
    out = Extracted("pdf")
    try:
        reader = PdfReader(io.BytesIO(data))
        n_pages = len(reader.pages)
        pages = []
        for i in range(min(n_pages, MAX_PDF_PAGES)):  # never read 20 000 pages for a 1 500-unit cap
            pages.append((i + 1, reader.pages[i].extract_text() or ""))
            if sum(len(t) for _, t in pages) > MAX_UNITS * MAX_UNIT_CHARS:
                break
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"cannot read PDF: {type(exc).__name__}") from exc
    if n_pages > len(pages):
        out.warnings.append(f"only the first {len(pages)} of {n_pages} pages were read")
        out.truncated = True
    for page_no, text in pages:
        for line in text.splitlines():
            line = _cell(line)
            if len(line) >= 3:
                out.units.append(Unit(SourceRef(filename=filename, kind="page", ref=page_no, excerpt=line[:200]), line))
    if not out.units and pages:
        out.warnings.append("the PDF has no extractable text (scanned?); OCR is not supported")
    return out


def _txt(data: bytes, filename: str) -> Extracted:
    out = Extracted("txt")
    for i, line in enumerate(_decode(data).splitlines(), start=1):
        line = _cell(line.lstrip("#*->• \t"))
        if line:
            out.units.append(Unit(SourceRef(filename=filename, kind="line", ref=i, excerpt=line[:200]), line))
    return out


def extract_units(file_bytes: bytes, filename: str) -> Extracted:
    """Read the file into numbered units (no model call). Raises :class:`IngestError`."""
    name = PurePath(filename or "upload").name
    ext = PurePath(name).suffix.lower()
    kind = SUPPORTED.get(ext)
    if kind is None:
        raise IngestError(f"unsupported file type '{ext or '?'}'; use .xlsx, .csv, .docx, .pdf, .txt or .md")
    if not file_bytes:
        raise IngestError("the file is empty")
    if len(file_bytes) > MAX_FILE_BYTES:
        raise IngestError(f"file too large ({len(file_bytes) // 1024} KiB > {MAX_FILE_BYTES // 1024} KiB)")
    reader = {"xlsx": _xlsx, "csv": _csv, "docx": _docx, "pdf": _pdf, "txt": _txt}[kind]
    out = reader(file_bytes, name)
    out.file_kind = kind
    if len(out.units) > MAX_UNITS:
        out.warnings.append(f"only the first {MAX_UNITS} of {len(out.units)} rows/paragraphs were read")
        out.units = out.units[:MAX_UNITS]
        out.truncated = True
    return out


def chunk_units(units: list[Unit], budget: int = CHUNK_CHARS) -> list[list[tuple[int, Unit]]]:
    """Consecutive units numbered 1..n, grouped into chunks of at most ``budget`` characters."""
    chunks: list[list[tuple[int, Unit]]] = []
    cur: list[tuple[int, Unit]] = []
    size = 0
    for n, u in enumerate(units, start=1):
        line = len(u.text) + 8
        if cur and size + line > budget:
            chunks.append(cur)
            cur, size = [], 0
        cur.append((n, u))
        size += line
    if cur:
        chunks.append(cur)
    return chunks


def _chunk_prompt(
    filename: str, ex: Extracted, chunk: list[tuple[int, Unit]], index: int, total: int, lang: str
) -> str:
    cols = ", ".join(f"{role}='{hdr}'" for role, hdr in ex.columns.items()) or "none detected"
    lines = "\n".join(f"[{n}] {u.text}" for n, u in chunk)
    return (
        f"The planner uploaded a preference file '{filename}' ({ex.file_kind}); part {index} of {total}. "
        f"Detected columns: {cols}. Each line is tagged [n]; set source_ref=n on everything you derive from it. "
        "Rows that only restate a normal timetable entry (course, day, time) without a wish, a room preference, "
        "a change or a restriction produce nothing. "
        f"Write titles and rationales in {'Turkish' if lang == 'tr' else 'English'}.\n\n"
        f"<document>\n{lines}\n</document>\n\n"
        "Call propose_constraints once with every rule and section edit you can map."
    )


async def extract_preferences(
    session: AsyncSession,
    term_id: int,
    file_bytes: bytes,
    filename: str,
    lang: str = "tr",
    *,
    client: AIClient,
) -> IngestOut:
    """Uploaded file -> reviewed-later proposals with source references (nothing is applied)."""
    # the local read runs off the event loop in a memory-capped child process (review B1)
    ex = await run_isolated(extract_units, file_bytes, filename)
    name = PurePath(filename or "upload").name
    if not ex.units:
        return IngestOut(
            proposals=[],
            filename=name,
            file_kind=ex.file_kind,  # type: ignore[arg-type]
            warnings=ex.warnings or ["no text found in the file"],
            assistant_message="Dosyada metin bulunamadı." if lang == "tr" else "No text found in the file.",
        )
    ctx = await load_term_context(session, term_id)
    chunks = chunk_units(ex.units)
    if len(chunks) > MAX_CHUNKS:
        skipped = sum(len(c) for c in chunks[MAX_CHUNKS:])
        ex.warnings.append(f"{skipped} rows/paragraphs after part {MAX_CHUNKS} were not analysed (file too long)")
        ex.truncated = True
        chunks = chunks[:MAX_CHUNKS]
    proposals: list[ProposedConstraint] = []
    edits: list[ProposedSectionEdit] = []
    unparsed: list[dict[str, Any]] = []
    notes: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        by_n = {n: u for n, u in chunk}

        def lookup(ref: int, _by_n: dict[int, Unit] = by_n) -> SourceRef | None:
            u = _by_n.get(ref)
            return u.ref if u is not None else SourceRef(filename=name, kind=ex.units[0].ref.kind)

        p, e, u, note = await propose(
            client, ctx, _chunk_prompt(name, ex, chunk, i, len(chunks), lang), lang, lookup=lookup
        )
        proposals += p
        edits += e
        unparsed += u
        if note:
            notes.append(note)
    log.info(
        "ingest term=%s file_kind=%s units=%d chunks=%d proposals=%d edits=%d",
        term_id,
        ex.file_kind,
        len(ex.units),
        len(chunks),
        len(proposals),
        len(edits),
    )
    return IngestOut(
        proposals=proposals,
        section_edits=edits,
        unparsed=unparsed,
        assistant_message="\n\n".join(notes)[:4000],
        usage=UsageOut(**client.usage.to_out()),
        filename=name,
        file_kind=ex.file_kind,  # type: ignore[arg-type]
        units=len(ex.units),
        chunks=len(chunks),
        truncated=ex.truncated,
        detected_columns=ex.columns,
        warnings=ex.warnings,
    )


__all__ = ["IngestError", "chunk_units", "detect_columns", "extract_preferences", "extract_units"]
