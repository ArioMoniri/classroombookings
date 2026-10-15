"""Registry entries for the formats the council read before the registry existed (xlsx, docx, pdf, images)
and the recognised formats it refuses with a "save as" hint. The renderers stay in :mod:`app.council.render`."""

from __future__ import annotations

import io
from pathlib import PurePath

from app.core import safe_files
from app.council import render as rd
from app.council.formats import (
    FormatLimits,
    FormatSpec,
    MiB,
    Probe,
    Unsupported,
    register,
    register_unsupported,
)
from app.council.render import Rendered


def _ooxml(part: str) -> object:
    def sniff(p: Probe) -> float:
        return 1.0 if p.family == "ooxml" and any(m.startswith(part) for m in p.members) else 0.0

    return sniff


def _inspect(kind: str) -> object:
    def check(data: bytes, lim: FormatLimits) -> None:
        sl = safe_files.Limits.from_settings()
        rep = safe_files.inspect_zip(data, limits=sl, kind=kind)
        if kind == "workbook":
            # rows, cells and merges are capped as for a full load (the board importer loads the whole workbook);
            # columns are not: the planning lists declare 16 375 formatted columns and are read read-only, which
            # clamps them, and a full load (open_workbook(read_only=False)) checks its own caps again
            safe_files.check_full_load(rep, safe_files.replace_limits(sl, max_cols=16_384), kind)

    return check


def _render_xlsx(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    try:
        safe_files.inspect_zip(data, kind="workbook")
    except safe_files.UnsafeFileError as exc:
        raise rd.RenderError(exc.message) from exc
    rd._xlsx(data, out)


def _render_docx(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    try:
        safe_files.inspect_zip(data, kind="document")
    except safe_files.UnsafeFileError as exc:
        raise rd.RenderError(exc.message) from exc
    rd._docx(data, out)


MAX_PDF_PAGES = 200


def _pdf_page_count(data: bytes) -> int:
    from pypdf import PdfReader

    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception as exc:  # noqa: BLE001
        raise rd.RenderError(f"cannot read PDF: {type(exc).__name__}") from exc


def _precheck_pdf(data: bytes, lim: FormatLimits) -> None:
    n = _pdf_page_count(data)
    if n > MAX_PDF_PAGES:
        raise safe_files.UnsafeFileError(413, f"the PDF has {n} pages (at most {MAX_PDF_PAGES})")


def _plumber_tables(data: bytes) -> list[rd.Grid]:
    """Ruled tables found by pdfplumber (lines strategy); a table continued on the next page with the same
    header row becomes one grid. Empty when the PDF draws no table lines."""
    import pdfplumber

    from app.council import text as tx

    grids: list[rd.Grid] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages[:MAX_PDF_PAGES], start=1):
            for t_no, table in enumerate(page.extract_tables(), start=1):
                rows = [[tx.cell_text(c) for c in row] for row in table if row and any(c for c in row)]
                if len(rows) < 2 or max(len(r) for r in rows) < 2:
                    continue
                meta = [{"page": page_no, "table": t_no, "row": i + 1} for i in range(len(rows))]
                prev = grids[-1] if grids else None
                if prev is not None and prev.cells and prev.cells[0] == rows[0]:
                    prev.cells.extend(rows[1:])
                    prev.row_meta.extend(meta[1:])
                    prev.row_numbers.extend(range(len(prev.row_numbers) + 1, len(prev.row_numbers) + len(rows)))
                    prev.name = f"pages {prev.row_meta[0]['page']}-{page_no} table"
                    continue
                grids.append(
                    rd.Grid(
                        f"page {page_no} table {t_no}",
                        "page",
                        rows,
                        [],
                        {"page": page_no, "table": t_no, "reader": "pdfplumber"},
                        list(range(1, len(rows) + 1)),
                        meta,
                    )
                )
    return grids


def _render_pdf(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    _precheck_pdf(data, lim)
    rd._pdf(data, out)  # text layer + layout tables (or "needs vision" for a scan)
    try:
        ruled = _plumber_tables(data)
    except Exception as exc:  # noqa: BLE001 - pdfplumber is an improvement, never a reason to fail the file
        out.warnings.append(f"ruled-table reader skipped: {type(exc).__name__}")
        ruled = []
    if ruled:  # drawn table lines are more reliable than column positions
        out.grids = ruled
        out.needs_vision = False
        out.warnings.append(f"{len(ruled)} ruled table(s) read with pdfplumber")


def _precheck_image(data: bytes, lim: FormatLimits) -> None:
    from app.council.formats_media import check_image

    check_image(data)  # Pillow verify + pixel cap (decompression bombs are 413)


def _render_image(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    out.needs_vision = True
    ext = PurePath(out.filename).suffix.lower().lstrip(".")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        out.media_type = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        out.media_type = "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        out.media_type = "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        out.media_type = "image/webp"
    else:
        out.media_type = rd.IMAGE_TYPES.get(ext, "image/png")


register(
    FormatSpec(
        "xlsx",
        "Excel workbook",
        "ooxml",
        (".xlsx", ".xlsm"),
        "structured",
        _ooxml("xl/"),  # type: ignore[arg-type]
        _render_xlsx,
        FormatLimits(max_bytes=25 * MiB),
        _inspect("workbook"),  # type: ignore[arg-type]
    )
)
register(
    FormatSpec(
        "docx",
        "Word document",
        "ooxml",
        (".docx",),
        "ai",
        _ooxml("word/"),  # type: ignore[arg-type]
        _render_docx,
        FormatLimits(max_bytes=15 * MiB),
        _inspect("document"),  # type: ignore[arg-type]
    )
)
register(
    FormatSpec(
        "pdf",
        "PDF",
        "pdf",
        (".pdf",),
        "ai",
        lambda p: 1.0 if p.family == "pdf" else 0.0,
        _render_pdf,
        FormatLimits(max_bytes=15 * MiB),
        _precheck_pdf,
    )
)
register(
    FormatSpec(
        "image",
        "image",
        "image",
        (".png", ".jpg", ".jpeg", ".webp", ".gif"),
        "ai",
        lambda p: 1.0 if p.family == "image" else 0.0,
        _render_image,
        FormatLimits(max_bytes=10 * MiB),
        _precheck_image,
    )
)

register_unsupported(
    Unsupported(
        "doc",
        lambda p: 1.0 if p.family == "ole2" and "WordDocument" in p.ole_streams else 0.0,
        "legacy .doc files are not read; save the file as .docx",
    )
)
register_unsupported(
    Unsupported(
        "ppt",
        lambda p: 1.0 if p.family == "ole2" and "PowerPoint Document" in p.ole_streams else 0.0,
        "legacy .ppt presentations are not read; export the slides as PDF",
    )
)
register_unsupported(
    Unsupported(
        "pptx",
        lambda p: 1.0 if p.family == "ooxml" and any(m.startswith("ppt/") for m in p.members) else 0.0,
        "presentations are not read; export the slides as PDF",
    )
)
register_unsupported(
    Unsupported(
        "odf-other",
        lambda p: (
            1.0
            if p.family == "odf"
            and p.odf_mime
            and not p.odf_mime.startswith("application/vnd.oasis.opendocument.spreadsheet")
            else 0.0
        ),
        "OpenDocument text and presentations are not read; save the file as .docx or PDF",
    )
)
register_unsupported(
    Unsupported(
        "zip",
        lambda p: 0.5 if p.family == "zip" else 0.0,
        "zip archives are not unpacked; upload the files inside it",
    )
)
register_unsupported(
    Unsupported(
        "ole2-other",
        lambda p: 0.5 if p.family == "ole2" else 0.0,
        "this Office file is not a workbook the council can read; save it as .xlsx",
    )
)
