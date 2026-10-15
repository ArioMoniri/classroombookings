"""Workbook formats of the registry beyond .xlsx: legacy .xls, OpenDocument .ods, and XML.

* ``.xls`` (OLE2 with a ``Workbook`` / ``Book`` stream): :mod:`xlrd` (pinned, BIFF only). Date cells become
  ``YYYY-MM-DD`` / ``HH:MM`` exactly like openpyxl values through :func:`app.council.text.cell_text`, merged
  ranges are forward-filled, the sheet caps apply (more cells than ``max_cells`` -> 413).
* ``.ods``: our own streaming ``content.xml`` reader on :mod:`defusedxml` (no DTDs, no entities). The zip
  container is inspected first (:func:`app.core.safe_files.inspect_zip`). ``number-columns-repeated`` /
  ``number-rows-repeated`` are expanded only for cells and rows that hold a value (trailing filler runs are
  dropped, as LibreOffice writes them), and an expansion past the sheet caps is refused with 413, so a
  4 KB file repeating one cell 16 384 times per row never becomes a 16 384-column grid.
* XML: :mod:`defusedxml` with DTDs, entities and external references forbidden (a billion-laughs file is a
  400 before any expansion), at most ``max_elements`` elements (413). SpreadsheetML 2003
  (``urn:schemas-microsoft-com:office:spreadsheet``, Excel's "XML Spreadsheet") becomes one grid per
  worksheet with ``ss:Index`` gaps and ``MergeAcross`` / ``MergeDown`` honoured; any other document becomes
  one table per run of repeated sibling elements (attributes and child elements are the columns).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime, time, timedelta
from typing import Any

from app.core import safe_files
from app.council import text as tx
from app.council.formats import ODS_MIME, FormatLimits, FormatSpec, MiB, Probe, register
from app.council.render import Grid, Rendered, RenderError, _trim


def _too_big(msg: str) -> safe_files.UnsafeFileError:
    return safe_files.UnsafeFileError(413, msg)


def _fill_merges(rows: list[list[str]], merges: list[tuple[int, int, int, int]], width: int) -> None:
    for r1, c1, r2, c2 in merges:
        if r1 >= len(rows):
            continue
        v = rows[r1][c1] if c1 < len(rows[r1]) else ""
        for r in range(r1, min(r2, len(rows) - 1) + 1):
            row = rows[r]
            if len(row) < width:
                row.extend([""] * (width - len(row)))
            for c in range(c1, min(c2, width - 1) + 1):
                row[c] = v


def _finish_grid(
    out: Rendered, name: str, rows: list[list[str]], merges: list[tuple[int, int, int, int]], origin: dict[str, Any]
) -> None:
    width = max((len(r) for r in rows), default=0)
    _fill_merges(rows, merges, width)
    rows = [r + [""] * (width - len(r)) for r in rows]
    numbers = list(range(1, len(rows) + 1))
    rows, numbers = _trim(rows, numbers)
    if rows:
        out.grids.append(Grid(name, "sheet", rows, merges, origin, numbers))


# --------------------------------------------------------------------------- xls


def _xls_value(cell: Any, datemode: int) -> str:
    import xlrd

    ctype, value = cell.ctype, cell.value
    if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return ""
    if ctype == xlrd.XL_CELL_DATE:
        try:
            y, mo, d, h, mi, s = xlrd.xldate_as_tuple(value, datemode)
        except (xlrd.xldate.XLDateError, ValueError, OverflowError):
            return tx.cell_text(value)
        if y == 0:  # a pure time of day
            return tx.cell_text(time(h, mi, s))
        return tx.cell_text(datetime(y, mo, d, h, mi, s))
    if ctype == xlrd.XL_CELL_BOOLEAN:
        return "TRUE" if value else "FALSE"
    return tx.cell_text(value)


def _open_xls(data: bytes) -> Any:
    try:
        import xlrd
    except ImportError as exc:  # pragma: no cover - pinned main dependency (P19-Q3)
        raise RenderError("xlrd is not installed on the server; save the file as .xlsx") from exc
    try:
        return xlrd.open_workbook(file_contents=data, formatting_info=True, on_demand=True, logfile=io.StringIO())
    except NotImplementedError:
        pass
    except Exception as exc:  # noqa: BLE001 - damaged or encrypted workbook
        raise RenderError(f"cannot read .xls workbook: {type(exc).__name__}") from exc
    try:
        return xlrd.open_workbook(file_contents=data, on_demand=True, logfile=io.StringIO())
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"cannot read .xls workbook: {type(exc).__name__}") from exc


def _render_xls(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    book = _open_xls(data)
    try:
        cells = 0
        for idx in range(book.nsheets):
            sh = book.sheet_by_index(idx)
            if getattr(sh, "visibility", 0):
                out.warnings.append(f"sheet '{sh.name}' is hidden in the workbook; it was read anyway")
            nrows, ncols = sh.nrows, sh.ncols
            if nrows > lim.max_rows:
                raise _too_big(f".xls sheet {sh.name} has {nrows} rows (limit {lim.max_rows})")
            width = 0
            for r in range(min(nrows, 80)):  # formatting inflates ncols: bound it by what the first rows use
                row = sh.row(r)
                for c in range(min(len(row), lim.max_cols) - 1, -1, -1):
                    if _xls_value(row[c], book.datemode):
                        width = max(width, c + 1)
                        break
            merges = [
                (r1, c1, r2 - 1, c2 - 1)
                for r1, r2, c1, c2 in getattr(sh, "merged_cells", []) or []
                if r1 < lim.max_rows and c1 < lim.max_cols
            ]
            width = max([width] + [m[3] + 1 for m in merges if m[3] < lim.max_cols])
            width = min(width or min(ncols, lim.max_cols), lim.max_cols)
            cells += nrows * width
            if cells > lim.max_cells:
                raise _too_big(f"the .xls workbook has more than {lim.max_cells} cells")
            rows = [
                [_xls_value(c, book.datemode) for c in sh.row_slice(r, 0, min(width, sh.row_len(r)))]
                for r in range(nrows)
            ]
            _finish_grid(out, sh.name, rows, merges, {"sheet": sh.name})
            book.unload_sheet(idx)
    finally:
        book.release_resources()


def _precheck_xls(data: bytes, lim: FormatLimits) -> None:
    book = _open_xls(data)
    try:
        total = 0
        for idx in range(book.nsheets):
            sh = book.sheet_by_index(idx)
            if sh.nrows > lim.max_rows:
                raise _too_big(f".xls sheet {sh.name} has {sh.nrows} rows (limit {lim.max_rows})")
            total += sh.nrows * min(sh.ncols, lim.max_cols)
            book.unload_sheet(idx)
        if total > lim.max_cells:
            raise _too_big(f"the .xls workbook has more than {lim.max_cells} cells")
    finally:
        book.release_resources()


def _sniff_xls(p: Probe) -> float:
    if p.family != "ole2":
        return 0.0
    if p.ole_streams & {"Workbook", "Book"}:
        return 1.0
    return 0.4 if p.ext == ".xls" and not p.ole_streams else 0.0


# --------------------------------------------------------------------------- ods

NS_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
NS_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
NS_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
T_TABLE = f"{{{NS_TABLE}}}table"
T_ROW = f"{{{NS_TABLE}}}table-row"
T_CELL = f"{{{NS_TABLE}}}table-cell"
T_COVERED = f"{{{NS_TABLE}}}covered-table-cell"
A_NAME = f"{{{NS_TABLE}}}name"
A_COLS_REP = f"{{{NS_TABLE}}}number-columns-repeated"
A_ROWS_REP = f"{{{NS_TABLE}}}number-rows-repeated"
A_COLS_SPAN = f"{{{NS_TABLE}}}number-columns-spanned"
A_ROWS_SPAN = f"{{{NS_TABLE}}}number-rows-spanned"
A_VTYPE = f"{{{NS_OFFICE}}}value-type"
A_VALUE = f"{{{NS_OFFICE}}}value"
A_DATE = f"{{{NS_OFFICE}}}date-value"
A_TIME = f"{{{NS_OFFICE}}}time-value"
A_BOOL = f"{{{NS_OFFICE}}}boolean-value"
TX_P = f"{{{NS_TEXT}}}p"
TX_H = f"{{{NS_TEXT}}}h"
TX_S = f"{{{NS_TEXT}}}s"
TX_TAB = f"{{{NS_TEXT}}}tab"
TX_BR = f"{{{NS_TEXT}}}line-break"
TX_C = f"{{{NS_TEXT}}}c"
_DURATION = re.compile(r"^-?P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")


def _int_attr(el: Any, name: str, default: int = 1) -> int:
    raw = el.get(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _para_text(el: Any) -> str:
    parts: list[str] = [el.text or ""]
    for ch in el:
        if ch.tag == TX_S:
            parts.append(" " * min(_int_attr(ch, TX_C), 1000))
        elif ch.tag == TX_TAB:
            parts.append("\t")
        elif ch.tag == TX_BR:
            parts.append("\n")
        else:
            parts.append(_para_text(ch))
        parts.append(ch.tail or "")
    return "".join(parts)


def _ods_value(cell: Any) -> str:
    vtype = cell.get(A_VTYPE)
    if vtype in ("float", "percentage", "currency") and cell.get(A_VALUE) is not None:
        try:
            return tx.cell_text(float(cell.get(A_VALUE)))
        except ValueError:
            pass
    if vtype == "date" and cell.get(A_DATE):
        raw = cell.get(A_DATE)
        try:
            dt = datetime.fromisoformat(raw)
            return tx.cell_text(dt if "T" in raw else dt.date())
        except ValueError:
            pass
    if vtype == "time" and cell.get(A_TIME):
        m = _DURATION.match(cell.get(A_TIME))
        if m:
            days, h, mi, s = (float(g) if g else 0.0 for g in m.groups())
            # LibreOffice writes 10:10 as PT10H09M59.999999S: round to the second like Excel's display
            delta = timedelta(seconds=round(days * 86400 + h * 3600 + mi * 60 + s))
            if delta >= timedelta(days=1):  # a date-time shown with a time format: Excel serial semantics
                epoch = datetime(1899, 12, 31) if delta < timedelta(days=61) else datetime(1899, 12, 30)
                return tx.cell_text(epoch + delta)
            return tx.cell_text(delta)
    if vtype == "boolean" and cell.get(A_BOOL) is not None:
        return "TRUE" if cell.get(A_BOOL) == "true" else "FALSE"
    paras = [_para_text(p) for p in cell if p.tag in (TX_P, TX_H)]
    return tx.cell_text("\n".join(paras))


def _ods_sheets(data: bytes, lim: FormatLimits, out: Rendered | None) -> None:
    """Stream ``content.xml``; with ``out=None`` only the caps are checked (upload precheck)."""
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    sl = safe_files.Limits.from_settings()
    safe_files.inspect_zip(data, limits=sl, kind="workbook")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        info = zf.getinfo("content.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise RenderError("the .ods file has no content.xml") from exc
    total_cells = 0
    name = ""
    rows: list[list[str]] = []
    merges: list[tuple[int, int, int, int]] = []
    pending_rows = 0
    sheet_no = 0
    try:
        with zf.open(info) as fh:
            for event, el in DET.iterparse(fh, events=("start", "end"), forbid_dtd=True):
                if event == "start":
                    if el.tag == T_TABLE:
                        sheet_no += 1
                        name = el.get(A_NAME) or f"Sheet{sheet_no}"
                        rows, merges, pending_rows = [], [], 0
                    continue
                if el.tag == T_ROW:
                    row: list[str] = []
                    pending_cols = 0
                    r_index = len(rows) + pending_rows
                    for cell in el:
                        if cell.tag not in (T_CELL, T_COVERED):
                            continue
                        rep = _int_attr(cell, A_COLS_REP)
                        value = _ods_value(cell) if cell.tag == T_CELL else ""
                        span_c, span_r = _int_attr(cell, A_COLS_SPAN), _int_attr(cell, A_ROWS_SPAN)
                        if not value and span_c == 1 and span_r == 1:
                            pending_cols += rep  # empty filler: only expanded when a value follows it
                            continue
                        col = len(row) + pending_cols
                        if col + rep > lim.max_cols:
                            if rep > 1 or span_c > 1:
                                raise _too_big(
                                    f".ods sheet {name} row {r_index + 1} expands to {col + rep} columns "
                                    f"(number-columns-repeated; limit {lim.max_cols})"
                                )
                            if out is not None:
                                out.warnings.append(f"sheet '{name}': columns after {lim.max_cols} were not read")
                            pending_cols += rep
                            continue
                        if span_c > 1 or span_r > 1:
                            if col + span_c > lim.max_cols or r_index + span_r > lim.max_rows:
                                raise _too_big(f".ods sheet {name}: a merged cell reaches past the sheet caps")
                            merges.append((r_index, col, r_index + span_r - 1, col + span_c - 1))
                        row.extend([""] * pending_cols)
                        pending_cols = 0
                        row.extend([value] * rep)
                    rrep = _int_attr(el, A_ROWS_REP)
                    if not any(row):
                        pending_rows += rrep
                    else:
                        if len(rows) + pending_rows + rrep > lim.max_rows:
                            raise _too_big(
                                f".ods sheet {name} expands to {len(rows) + pending_rows + rrep} rows "
                                f"(number-rows-repeated; limit {lim.max_rows})"
                            )
                        total_cells += len(row) * rrep
                        if total_cells > lim.max_cells:
                            raise _too_big(f"the .ods workbook expands to more than {lim.max_cells} cells")
                        rows.extend([] for _ in range(pending_rows))
                        pending_rows = 0
                        rows.extend(list(row) for _ in range(rrep))
                    el.clear()
                elif el.tag == T_TABLE:
                    if out is not None:
                        _finish_grid(out, name, rows, merges, {"sheet": name})
                    rows, merges = [], []
                    el.clear()
    except safe_files.UnsafeFileError:
        raise
    except DefusedXmlException as exc:
        raise safe_files.UnsafeFileError(
            400, f"the .ods content uses a DTD or entities ({type(exc).__name__})"
        ) from exc
    except DET.ParseError as exc:
        raise safe_files.UnsafeFileError(400, f"the .ods content is not valid XML: {exc}") from exc


def _render_ods(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    _ods_sheets(data, lim, out)


def _precheck_ods(data: bytes, lim: FormatLimits) -> None:
    _ods_sheets(data, lim, None)


def _sniff_ods(p: Probe) -> float:
    if p.family != "odf":
        return 0.0
    if p.odf_mime.startswith(ODS_MIME):
        return 1.0
    return 0.6 if not p.odf_mime and p.ext == ".ods" else 0.0


# --------------------------------------------------------------------------- xml

NS_SS = "urn:schemas-microsoft-com:office:spreadsheet"
SS = f"{{{NS_SS}}}"


def _local(tag: Any) -> str:
    t = str(tag)
    return t.rsplit("}", 1)[-1] if "}" in t else t


def parse_xml(data: bytes, lim: FormatLimits) -> Any:
    """The document root, parsed with DTDs, entities and external references forbidden (400) and at most
    ``lim.max_elements`` elements (413)."""
    import defusedxml.ElementTree as DET
    from defusedxml import DefusedXmlException

    if len(data) > lim.max_bytes:
        raise _too_big(f"XML files may be at most {lim.max_bytes // MiB} MiB")
    root = None
    count = 0
    try:
        for _event, el in DET.iterparse(
            io.BytesIO(data), events=("start",), forbid_dtd=True, forbid_entities=True, forbid_external=True
        ):
            count += 1
            if root is None:
                root = el
            if count > lim.max_elements:
                raise _too_big(f"the XML has more than {lim.max_elements} elements")
    except safe_files.UnsafeFileError:
        raise
    except DefusedXmlException as exc:
        raise safe_files.UnsafeFileError(
            400, f"XML with a DTD, entity declarations or external references is not read ({type(exc).__name__})"
        ) from exc
    except DET.ParseError as exc:
        raise safe_files.UnsafeFileError(400, f"the XML is not well-formed: {exc}") from exc
    if root is None:
        raise RenderError("the XML document is empty")
    return root


def _ss_value(cell: Any) -> str:
    data = cell.find(f"{SS}Data")
    if data is None:
        return ""
    kind = data.get(f"{SS}Type", "String")
    raw = "".join(data.itertext())
    if kind == "Number":
        try:
            return tx.cell_text(float(raw))
        except ValueError:
            return tx.cell_text(raw)
    if kind == "DateTime":
        try:
            dt = datetime.fromisoformat(raw.rstrip("Z"))
        except ValueError:
            return tx.cell_text(raw)
        if dt.date() in (date(1899, 12, 31), date(1899, 12, 30)):  # Excel's "time only" epoch
            return tx.cell_text(dt.time())
        return tx.cell_text(dt if (dt.hour, dt.minute) != (0, 0) else dt.date())
    if kind == "Boolean":
        return "TRUE" if raw.strip() in ("1", "true") else "FALSE"
    return tx.cell_text(raw)


def _spreadsheetml(root: Any, out: Rendered, lim: FormatLimits) -> None:
    total = 0
    for ws in root.iter(f"{SS}Worksheet"):
        name = ws.get(f"{SS}Name") or f"Sheet{len(out.grids) + 1}"
        table = ws.find(f"{SS}Table")
        if table is None:
            continue
        rows: list[list[str]] = []
        merges: list[tuple[int, int, int, int]] = []
        r = 0
        for row_el in table.findall(f"{SS}Row"):
            r = _int_attr(row_el, f"{SS}Index", r + 1) if row_el.get(f"{SS}Index") else r + 1
            if r > lim.max_rows:
                raise _too_big(f"XML worksheet {name} has a row {r} past the limit of {lim.max_rows}")
            while len(rows) < r:
                rows.append([])
            row = rows[r - 1]
            c = 0
            for cell in row_el.findall(f"{SS}Cell"):
                c = _int_attr(cell, f"{SS}Index", c + 1) if cell.get(f"{SS}Index") else c + 1
                across = int(cell.get(f"{SS}MergeAcross") or 0)
                down = int(cell.get(f"{SS}MergeDown") or 0)
                if c + across > lim.max_cols or r + down > lim.max_rows or across < 0 or down < 0:
                    raise _too_big(f"XML worksheet {name}: a cell or merge reaches past the sheet caps")
                while len(row) < c:
                    row.append("")
                row[c - 1] = _ss_value(cell)
                total += 1
                if across or down:
                    merges.append((r - 1, c - 1, r - 1 + down, c - 1 + across))
                c += across
            if total > lim.max_cells:
                raise _too_big(f"the XML workbook has more than {lim.max_cells} cells")
        _finish_grid(out, name, rows, merges, {"sheet": name})


def _record_text(el: Any) -> str:
    return tx.cell_text(" ".join(t.strip() for t in el.itertext() if t.strip()))


def _generic_xml(root: Any, out: Rendered, lim: FormatLimits) -> None:
    """Runs of repeated sibling elements become tables (one per container, largest first)."""
    from collections import Counter

    parents: dict[int, Any] = {}
    candidates: list[tuple[int, Any, str]] = []
    for el in root.iter():
        kids = list(el)
        for k in kids:
            parents[id(k)] = el
        counts = Counter(k.tag for k in kids)
        for tag, n in counts.items():
            if n >= 2:
                sample = next(k for k in kids if k.tag == tag)
                if len(sample) or sample.attrib:
                    candidates.append((n, el, tag))
    if not candidates:
        raise RenderError("the XML has no repeated records to read as rows")
    candidates.sort(key=lambda t: -t[0])
    chosen_rows: set[int] = set()
    tables = 0
    for _, container, tag in candidates:
        node, inside = container, False
        while node is not None:  # skip containers that sit inside a row already taken
            if id(node) in chosen_rows:
                inside = True
                break
            node = parents.get(id(node))
        if inside:
            continue
        records = [k for k in container if k.tag == tag][: lim.max_rows]
        cols: list[str] = []
        values: list[dict[str, str]] = []
        for rec in records:
            chosen_rows.add(id(rec))
            row: dict[str, str] = {}
            for a, v in rec.attrib.items():
                row[f"@{_local(a)}"] = tx.cell_text(v)
            for ch in rec:
                key = _local(ch.tag)
                text = _record_text(ch) if len(ch) else tx.cell_text(ch.text)
                row[key] = f"{row[key]}, {text}" if key in row and text else (text or row.get(key, ""))
            if not len(rec) and rec.text and rec.text.strip():
                row[_local(rec.tag)] = tx.cell_text(rec.text)
            for k in row:
                if k not in cols and len(cols) < lim.max_cols:
                    cols.append(k)
            values.append(row)
        grid_rows = [cols] + [[r.get(k, "") for k in cols] for r in values]
        name = f"{_local(container.tag)}/{_local(tag)}"
        out.grids.append(Grid(name, "table", grid_rows, [], {"xpath": name}, list(range(1, len(grid_rows) + 1))))
        tables += 1
        if tables >= 10:
            break


def _render_xml(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    root = parse_xml(data, lim)
    if root.tag == f"{SS}Workbook" or root.find(f".//{SS}Worksheet") is not None:
        out.warnings.append("SpreadsheetML 2003 (Excel XML Spreadsheet)")
        _spreadsheetml(root, out, lim)
    else:
        _generic_xml(root, out, lim)


def _precheck_xml(data: bytes, lim: FormatLimits) -> None:
    parse_xml(data, lim)


def _sniff_xml(p: Probe) -> float:
    if p.family != "text":
        return 0.0
    s = p.text.lstrip("﻿ \t\r\n")
    if s.startswith("<?xml") or re.match(r"<[A-Za-z_][\w.:-]*[\s>/]", s) or s.startswith("<!DOCTYPE"):
        if NS_SS in p.text[:4096] or 'progid="Excel.Sheet"' in p.text[:512]:
            return 1.0
        return 0.9
    return 0.0


register(
    FormatSpec(
        "xls",
        "Excel 97-2003 workbook",
        "ole2",
        (".xls",),
        "structured",
        _sniff_xls,
        _render_xls,
        FormatLimits(max_bytes=20 * MiB),
        _precheck_xls,
    )
)
register(
    FormatSpec(
        "ods",
        "OpenDocument spreadsheet",
        "odf",
        (".ods",),
        "structured",
        _sniff_ods,
        _render_ods,
        FormatLimits(max_bytes=20 * MiB),
        _precheck_ods,
    )
)
register(
    FormatSpec(
        "xml",
        "XML",
        "text",
        (".xml",),
        "structured",
        _sniff_xml,
        _render_xml,
        FormatLimits(max_bytes=10 * MiB),
        _precheck_xml,
    )
)

__all__ = ["NS_SS", "parse_xml"]
