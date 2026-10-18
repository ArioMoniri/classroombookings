"""Safe intake of uploaded workbooks and documents (review B1).

Every upload path (studio column mapping, AI preference ingest, planning / exam list, weekly grid, CRBS
dump, room master) goes through this module:

1. :func:`read_upload` / :func:`save_upload` stream the request body with a hard byte cap (HTTP 413) and
   never leave a partial file on disk;
2. :func:`inspect_zip` pre-inspects an OOXML container (``.xlsx`` / ``.docx``) *before* any parser sees it:
   member count, total and per-member uncompressed size (``sharedStrings.xml`` included), compression
   ratio, and for worksheets the real extent (highest row / column, number of cells, merged-cell area) so
   a 2 KB file declaring ``<dimension ref="A1:XFD1048576"/>`` or one ``<mergeCell>`` covering the whole
   sheet is refused or clamped instead of expanding to billions of cells;
3. :func:`open_workbook` loads the workbook after the inspection and clamps every read-only sheet's
   dimension to the real (capped) extent, so ``iter_rows()`` without bounds stays bounded;
4. :func:`run_isolated` runs the CPU/memory heavy parse **off the event loop** in a short-lived child
   process (``forkserver``) with an ``RLIMIT_AS`` memory cap and a wall-clock timeout; ``thread`` mode
   (``PARSE_ISOLATION=thread``) falls back to ``asyncio.to_thread`` with the same caps.

Errors are :class:`UnsafeFileError` with an HTTP status (400 malformed / unsupported, 413 too large);
routers map them 1:1. The messages never contain server paths.
"""

from __future__ import annotations

import asyncio
import functools
import io
import logging
import multiprocessing
import re
import zipfile
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from app.core.config import get_settings

log = logging.getLogger(__name__)
MiB = 1024 * 1024
#: OOXML members that are rendered into Python objects (shared strings, sheets, document bodies)
_TEXT_PARTS = re.compile(r"^(xl/(sharedStrings|worksheets/[^/]+|styles)|word/document)\.xml$", re.I)
_SHEET_PART = re.compile(r"^xl/worksheets/[^/]+\.xml$", re.I)
#: the opening tag of a ``<row>`` or ``<c>`` element (``/`` in group 3 when it is self-closing, i.e. empty)
_TAG_RX = re.compile(rb"<(?:\w+:)?(row|c)\b([^>]*?)(/?)>")
_CELL_END_RX = re.compile(rb"</(?:\w+:)?c\s*>")
_R_ATTR = re.compile(rb'\sr="(\d+)"')
_CELL_REF = re.compile(rb'\sr="([A-Z]{1,3})(\d*)"')
#: a cell that holds something: a non-empty value / inline-string text (CDATA too) or a formula
_VALUE_RX = re.compile(rb"<(?:\w+:)?(?:v|t)\b[^>/]*>(?:[^<]|<!\[CDATA\[)|<(?:\w+:)?f\b")
_MERGE_RX = re.compile(rb'<(?:\w+:)?mergeCell\b[^>]*\sref="([A-Z]{1,3})(\d+)(?::([A-Z]{1,3})(\d+))?"')


class UnsafeFileError(ValueError):
    """An upload that must not be parsed: ``status`` 400 (malformed / unsupported) or 413 (too large)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message

    def __reduce__(self) -> tuple[Any, ...]:  # picklable across the parse subprocess
        return (UnsafeFileError, (self.status, self.message))


@dataclass(frozen=True)
class Limits:
    """Caps applied to one upload (defaults from settings; tests shrink them)."""

    max_upload_bytes: int = 25 * MiB
    max_total_uncompressed: int = 50 * MiB
    max_member_uncompressed: int = 20 * MiB
    max_ratio: float = 100.0
    ratio_floor: int = 2 * MiB  # the ratio is only checked when the expanded size exceeds this
    max_members: int = 2000
    max_rows: int = 20_000
    max_cols: int = 1024
    max_cells: int = 2_000_000  # full (non read-only) loads materialise every cell
    max_merged_cells: int = 2_000_000

    @classmethod
    def from_settings(cls, **overrides: Any) -> Limits:
        s = get_settings()
        base = cls(
            max_upload_bytes=int(s.upload_max_mb * MiB),
            max_total_uncompressed=int(s.zip_max_uncompressed_mb * MiB),
            max_member_uncompressed=int(s.zip_max_member_mb * MiB),
            max_ratio=float(s.zip_max_ratio),
            max_rows=int(s.sheet_max_rows),
            max_cols=int(s.sheet_max_cols),
        )
        return replace_limits(base, **overrides) if overrides else base


def replace_limits(lim: Limits, **kw: Any) -> Limits:
    from dataclasses import replace

    return replace(lim, **kw)


@dataclass
class SheetExtent:
    """The real extent of one worksheet part.

    ``rows`` / ``cols`` are the last row / column holding a value (the used range). A styled-but-empty cell
    (``<c r="XFD7" s="3"/>``, written by Excel for whole formatted rows) and the declared
    ``<dimension ref>`` do not count: the real planning lists declare 16 375 formatted columns but use 26.
    ``cells`` counts every ``<c>`` element, styled-empty ones too, because a full (non read-only) load
    materialises each of them; with the per-part byte cap it bounds the work a styled-cell bomb can cause."""

    rows: int = 0  # last row with a value (explicit ``r`` or implicit position)
    cols: int = 0  # last column with a value (explicit ``r`` or implicit position)
    cells: int = 0  # every <c> element
    merged_cells: int = 0
    styled_cols: int = 0  # last column of any <c> element (informational: what Excel's max_column reports)


@dataclass
class ZipReport:
    members: int = 0
    total_uncompressed: int = 0
    compressed: int = 0
    sheets: dict[str, SheetExtent] = field(default_factory=dict)  # member path -> extent
    clamped: bool = False


def _col_index(letters: bytes) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ch - 64)
    return n


def _mib(n: int) -> str:
    return f"{n / MiB:.1f} MiB"


def _scan_sheet(data: bytes) -> SheetExtent:
    """One linear pass over the (size-capped) worksheet XML; no cell objects are built."""
    ext = SheetExtent()
    row = col = 0
    pos = 0
    while True:
        m = _TAG_RX.search(data, pos)
        if m is None:
            break
        pos = m.end()
        if m.group(1) == b"row":
            r = _R_ATTR.search(m.group(2))
            row = int(r.group(1)) if r else row + 1  # a row without r follows the previous one
            col = 0
            continue
        ext.cells += 1
        ref = _CELL_REF.search(m.group(2))
        col = _col_index(ref.group(1)) if ref else col + 1  # a cell without r follows the previous one
        cell_row = int(ref.group(2)) if ref and ref.group(2) else max(row, 1)
        ext.styled_cols = max(ext.styled_cols, col)
        if m.group(3):  # <c .../>: style only, no value
            continue
        end = _CELL_END_RX.search(data, pos)
        if end is None:  # truncated part: what was seen so far is the extent
            break
        if _VALUE_RX.search(data, pos, end.start()):
            ext.rows = max(ext.rows, cell_row)
            ext.cols = max(ext.cols, col)
        pos = end.end()
    for m in _MERGE_RX.finditer(data):
        c1, r1, c2, r2 = m.groups()
        if c2 is None:
            continue
        w = abs(_col_index(c2) - _col_index(c1)) + 1
        h = abs(int(r2) - int(r1)) + 1
        ext.merged_cells += w * h
    return ext


def inspect_zip(src: bytes | str | Path, *, limits: Limits | None = None, kind: str = "workbook") -> ZipReport:
    """Pre-inspect an OOXML container without expanding it into objects. Raises :class:`UnsafeFileError`."""
    lim = limits or Limits.from_settings()
    fh: IO[bytes] = io.BytesIO(src) if isinstance(src, bytes) else open(src, "rb")  # noqa: SIM115
    try:
        try:
            zf = zipfile.ZipFile(fh)
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            raise UnsafeFileError(400, f"the {kind} is not a valid .xlsx/.docx file (not a zip archive)") from exc
        with zf:
            infos = zf.infolist()
            rep = ZipReport(members=len(infos))
            if len(infos) > lim.max_members:
                raise UnsafeFileError(413, f"the {kind} has too many parts ({len(infos)} > {lim.max_members})")
            for info in infos:
                if info.flag_bits & 0x1:
                    raise UnsafeFileError(400, f"the {kind} is encrypted")
                rep.total_uncompressed += info.file_size
                rep.compressed += info.compress_size
                if info.file_size > lim.max_member_uncompressed:
                    raise UnsafeFileError(
                        413,
                        f"the {kind} part {Path(info.filename).name} expands to {_mib(info.file_size)} "
                        f"(limit {_mib(lim.max_member_uncompressed)})",
                    )
            if rep.total_uncompressed > lim.max_total_uncompressed:
                raise UnsafeFileError(
                    413,
                    f"the {kind} expands to {_mib(rep.total_uncompressed)} (limit {_mib(lim.max_total_uncompressed)})",
                )
            if rep.total_uncompressed > lim.ratio_floor and rep.total_uncompressed > lim.max_ratio * max(
                rep.compressed, 1
            ):
                raise UnsafeFileError(
                    413, f"the {kind} is compressed suspiciously well (>{lim.max_ratio:.0f}:1); refusing to expand it"
                )
            for info in infos:
                if not _SHEET_PART.match(info.filename):
                    continue
                # the declared size was checked above; read at most that much (+1 to detect lies)
                with zf.open(info) as part:
                    data = part.read(lim.max_member_uncompressed + 1)
                if len(data) > lim.max_member_uncompressed:
                    raise UnsafeFileError(413, f"the {kind} part {Path(info.filename).name} is larger than declared")
                rep.sheets[info.filename] = _scan_sheet(data)
            return rep
    finally:
        fh.close()


def check_full_load(rep: ZipReport, lim: Limits, kind: str = "workbook") -> None:
    """A full (non read-only) openpyxl load materialises every cell and every merged cell: refuse sheets
    whose used extent (rows / columns with values) or element counts (cells, merged area) exceed the caps.
    Formatting does not count against the row / column caps (the real planning lists style 16 375 columns);
    styled-empty cells count against ``max_cells``, so a style-only bomb is still bounded."""
    for name, ext in rep.sheets.items():
        sheet = Path(name).stem
        if ext.rows > lim.max_rows:
            raise UnsafeFileError(413, f"{kind} sheet {sheet} has {ext.rows} rows (limit {lim.max_rows})")
        if ext.cols > lim.max_cols:
            raise UnsafeFileError(413, f"{kind} sheet {sheet} has {ext.cols} columns (limit {lim.max_cols})")
        if ext.cells > lim.max_cells:
            raise UnsafeFileError(413, f"{kind} sheet {sheet} has {ext.cells} cells (limit {lim.max_cells})")
        if ext.merged_cells > lim.max_merged_cells:
            raise UnsafeFileError(
                413, f"{kind} sheet {sheet} merges {ext.merged_cells} cells (limit {lim.max_merged_cells})"
            )


def open_workbook(
    src: bytes | str | Path,
    *,
    read_only: bool = True,
    data_only: bool = True,
    limits: Limits | None = None,
    max_rows: int | None = None,
    max_cols: int | None = None,
) -> Any:
    """``openpyxl.load_workbook`` after :func:`inspect_zip`. Read-only sheets get their dimension clamped to
    the used extent (last cell with a value, see :class:`SheetExtent`) capped by ``max_rows`` / ``max_cols``
    (rows beyond the cap are not read); full loads are refused when a sheet exceeds the caps (see
    :func:`check_full_load`) and lose the styled-but-empty cells past the used range (see :func:`_trim_styled`),
    so ``ws.max_column`` / ``ws.max_row`` describe the data, not formatting out to XFD."""
    import openpyxl

    lim = limits or Limits.from_settings()
    rep = inspect_zip(src, limits=lim)
    if not read_only:
        check_full_load(rep, lim)
    try:
        source: Any = io.BytesIO(src) if isinstance(src, bytes) else src
        wb = openpyxl.load_workbook(source, read_only=read_only, data_only=data_only)
    except UnsafeFileError:
        raise
    except Exception as exc:  # noqa: BLE001 - malformed workbook
        raise UnsafeFileError(400, f"cannot read workbook: {type(exc).__name__}") from exc
    if read_only:
        rows_cap = min(max_rows or lim.max_rows, lim.max_rows)
        cols_cap = min(max_cols or lim.max_cols, lim.max_cols)
        extents = list(rep.sheets.values())
        for i, ws in enumerate(wb.worksheets):
            path = getattr(ws, "_worksheet_path", None)
            ext = rep.sheets.get(str(path).lstrip("/")) if path else (extents[i] if i < len(extents) else None)
            real_rows = ext.rows if ext else rows_cap
            real_cols = ext.cols if ext else cols_cap
            ws._max_row = max(1, min(real_rows or 1, rows_cap))
            ws._max_column = max(1, min(real_cols or 1, cols_cap))
            if ext and (ext.rows > rows_cap or ext.cols > cols_cap):
                rep.clamped = True
    else:
        for ws in wb.worksheets:
            _trim_styled(ws)
    wb._safe_report = rep  # noqa: SLF001 - callers may report truncation
    return wb


def _trim_styled(ws: Any) -> None:
    """Drop a fully loaded sheet's empty cells past its used range (the last value or merged cell): Excel writes
    style-only cells out to XFD for formatted rows, which makes ``max_column`` 16 384 and turns an
    ``iter_rows()`` up to it into millions of new cells. The work is bounded by the ``max_cells`` check."""
    cells = getattr(ws, "_cells", None)
    if not cells:
        return
    rows = cols = 0
    for (r, c), cell in cells.items():
        if cell.value is not None:
            rows, cols = max(rows, r), max(cols, c)
    for rng in getattr(ws.merged_cells, "ranges", ()):
        rows, cols = max(rows, rng.max_row), max(cols, rng.max_col)
    for key in [k for k, cell in cells.items() if (k[0] > rows or k[1] > cols) and cell.value is None]:
        del cells[key]


# --------------------------------------------------------------------------- uploads


async def read_upload(file: Any, max_bytes: int | None = None) -> bytes:
    """Read an ``UploadFile`` in chunks; :class:`UnsafeFileError` 413 as soon as ``max_bytes`` is passed."""
    cap = max_bytes if max_bytes is not None else Limits.from_settings().max_upload_bytes
    buf = bytearray()
    while True:
        chunk = await file.read(MiB)
        if not chunk:
            break
        buf += chunk
        if len(buf) > cap:
            raise UnsafeFileError(413, f"file too large (limit {_mib(cap)})")
    return bytes(buf)


async def save_upload(file: Any, target: Path, max_bytes: int | None = None) -> int:
    """Stream an ``UploadFile`` to ``target``; on 413 (or any error) the partial file is removed."""
    cap = max_bytes if max_bytes is not None else Limits.from_settings().max_upload_bytes
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with open(target, "wb") as out:
            while True:
                chunk = await file.read(MiB)
                if not chunk:
                    break
                size += len(chunk)
                if size > cap:
                    raise UnsafeFileError(413, f"file too large (limit {_mib(cap)})")
                out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return size


def is_zip_container(name: str | None) -> bool:
    return (name or "").lower().endswith((".xlsx", ".xlsm", ".docx"))


async def precheck_upload(path_or_bytes: bytes | Path, filename: str | None, *, full_load: bool = False) -> None:
    """Zip pre-inspection of an upload off the event loop (no-op for non-OOXML files)."""
    if not is_zip_container(filename):
        return
    lim = Limits.from_settings()

    def run() -> None:
        rep = inspect_zip(path_or_bytes, limits=lim)
        if full_load:
            check_full_load(rep, lim)

    await asyncio.to_thread(run)


# --------------------------------------------------------------------------- isolation

_PRELOAD = [
    "openpyxl",
    "app.core.safe_files",
    "app.importers.planning_list",
    "app.importers.exam_list",
    "app.importers.weekly_grid",
    "app.importers.tables",
    "app.ai.ingest",
    "app.council.render",
    "app.council.fastpath",
]
_ctx: Any = None


def _context() -> Any:
    global _ctx
    if _ctx is None:
        _ctx = multiprocessing.get_context("forkserver")
        _ctx.set_forkserver_preload(_PRELOAD)
    return _ctx


def _limit_memory(mem_bytes: int) -> None:  # pragma: no cover - runs in the child
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except (ImportError, ValueError, OSError):
        pass


def _kill(pool: ProcessPoolExecutor) -> None:
    for proc in list(getattr(pool, "_processes", {}).values()):
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


async def run_isolated[T](fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run ``fn(*args, **kwargs)`` off the event loop: in a fresh child process with an address-space
    rlimit (``PARSE_ISOLATION=process``, the default) or in a worker thread (``thread``).

    ``fn`` and its arguments / result must be picklable in process mode. ``MemoryError`` or a crashed
    child become :class:`UnsafeFileError` 413; the wall-clock limit (``PARSE_TIMEOUT_S``) a 413 too."""
    s = get_settings()
    call = functools.partial(fn, *args, **kwargs)
    timeout = float(s.parse_timeout_s)
    if s.parse_isolation == "process":
        from app.importers import normalize as n  # the admins' period grid travels with the call (RF-09)

        call = functools.partial(n.call_with_period_grid, n.period_grid_times(), fn, *args, **kwargs)
    if s.parse_isolation != "process":
        try:
            return await asyncio.wait_for(asyncio.to_thread(call), timeout)
        except MemoryError as exc:
            raise UnsafeFileError(413, "the file needs too much memory to read") from exc
        except TimeoutError as exc:
            raise UnsafeFileError(413, f"reading the file took longer than {timeout:.0f} s") from exc
    loop = asyncio.get_running_loop()
    pool = ProcessPoolExecutor(
        max_workers=1, mp_context=_context(), initializer=_limit_memory, initargs=(int(s.parse_memory_mb) * MiB,)
    )
    try:
        return await asyncio.wait_for(loop.run_in_executor(pool, call), timeout)
    except MemoryError as exc:
        raise UnsafeFileError(413, "the file needs too much memory to read") from exc
    except BrokenProcessPool as exc:
        raise UnsafeFileError(413, "the file reader crashed (out of memory?)") from exc
    except TimeoutError as exc:
        _kill(pool)
        raise UnsafeFileError(413, f"reading the file took longer than {timeout:.0f} s") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


__all__ = [
    "Limits",
    "UnsafeFileError",
    "ZipReport",
    "check_full_load",
    "inspect_zip",
    "open_workbook",
    "precheck_upload",
    "read_upload",
    "run_isolated",
    "save_upload",
]
