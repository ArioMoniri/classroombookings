"""Registry entries for the formats the council read before the registry existed (xlsx, docx, pdf, images)
and the recognised formats it refuses with a "save as" hint. The renderers stay in :mod:`app.council.render`."""

from __future__ import annotations

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


def _render_pdf(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    rd._pdf(data, out)


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
