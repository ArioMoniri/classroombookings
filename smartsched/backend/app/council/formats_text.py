"""Text formats of the registry: CSV / TSV, plain text, JSON (generic tables and ``smartsched.intake.v1``).

Decoding (:func:`decode_text`): a BOM first (UTF-8, UTF-16 LE / BE), then strict UTF-8, then Windows-1254
(Turkish Excel's "CSV (virgülle ayrılmış)": İ / ş / ğ are 0xDD / 0xFE / 0xF0), then Latin-1 as the last resort.

Delimiter (:func:`sniff_delimiter`): an Excel ``sep=;`` first line wins; otherwise :class:`csv.Sniffer` limited
to ``; , \\t |`` on the first 8 KiB, checked against (and on failure replaced by) the delimiter whose records
have the steadiest column count. Turkish exports use ``;`` because ``,`` is the decimal separator.

JSON: at most 10 MiB, nesting depth 32 and 50 000 objects (checked on the raw text before :func:`json.loads`).
A document with ``"schema": "smartsched.intake.v1"`` is the native intake format (rooms, requests, timetable,
see :func:`intake_records`); any other array of objects becomes a table (keys = header row).
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from typing import Any

from app.core import safe_files
from app.council import text as tx
from app.council.formats import FormatLimits, FormatSpec, MiB, Probe, register
from app.council.render import Grid, Rendered, RenderError, Unit, _trim

INTAKE_V1 = "smartsched.intake.v1"
DELIMITERS = ";,\t|"
SNIFF_BYTES = 8192
_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)
_SEP_LINE = re.compile(r'^﻿?"?sep=(.)"?\s*$', re.I)
_DELIM_NAMES = {";": "semicolon", ",": "comma", "\t": "tab", "|": "pipe"}


# --------------------------------------------------------------------------- decoding


def decode_text(data: bytes) -> tuple[str, str]:
    """``(text, encoding)``: BOM, then strict UTF-8, then cp1254, then latin-1 (never fails on 8-bit data)."""
    for bom, enc in _BOMS:
        if data.startswith(bom):
            try:
                return data.decode(enc), enc
            except UnicodeDecodeError as exc:
                if len(data) >= len(bom) + 4 and exc.start >= len(data) - 4:  # a head cut inside a character
                    return data[: exc.start].decode(enc), enc
                raise RenderError(f"the file starts with a {enc} byte-order mark but is not {enc}") from exc
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError as exc:
        if exc.start >= len(data) - 3 and exc.reason == "unexpected end of data":  # a 64 KiB head cut mid-char
            return data[: exc.start].decode("utf-8"), "utf-8"
    try:
        return data.decode("cp1254"), "cp1254"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


# --------------------------------------------------------------------------- delimiter


def _records(sample: str, delimiter: str) -> list[int]:
    """Field counts of the complete records of ``sample`` (the last one may be cut: dropped)."""
    try:
        rows = list(csv.reader(io.StringIO(sample), delimiter=delimiter, strict=False))
    except csv.Error:
        return []
    if len(rows) > 1 and not sample.endswith(("\n", "\r")):
        rows = rows[:-1]
    return [len(r) for r in rows if any(c.strip() for c in r)]


def _steadiness(counts: list[int]) -> tuple[float, int]:
    """(share of records with the modal field count, modal count) - 1.0 is a perfectly rectangular table."""
    if not counts:
        return 0.0, 0
    mode, n = Counter(counts).most_common(1)[0]
    return n / len(counts), mode


def _by_variance(sample: str) -> str | None:
    best: tuple[float, float, int] | None = None
    choice = None
    for d in DELIMITERS:
        counts = _records(sample, d)
        share, mode = _steadiness(counts)
        if mode < 2:
            continue
        mean = sum(counts) / len(counts)
        var = sum((c - mean) ** 2 for c in counts) / len(counts)
        key = (share, -var, mode)
        if best is None or key > best:
            best, choice = key, d
    return choice


def sniff_delimiter(text: str) -> tuple[str | None, int, str]:
    """``(delimiter or None, lines to skip, how)``: ``sep=`` line > csv.Sniffer > steadiest column count."""
    first = text.split("\n", 1)[0].rstrip("\r")
    m = _SEP_LINE.match(first)
    if m and m.group(1) in DELIMITERS:
        return m.group(1), 1, "sep= line"
    sample = text[:SNIFF_BYTES]
    sniffed: str | None = None
    try:
        sniffed = csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        sniffed = None
    steady = _by_variance(sample)
    if sniffed is not None:
        s_share, s_mode = _steadiness(_records(sample, sniffed))
        if s_mode >= 2 and (steady is None or steady == sniffed):
            return sniffed, 0, "sniffer"
        if steady is not None:
            v_share, _ = _steadiness(_records(sample, steady))
            if s_mode >= 2 and s_share >= v_share:
                return sniffed, 0, "sniffer"
            return steady, 0, "column-count variance"
    return steady, 0, "column-count variance" if steady else "none"


# --------------------------------------------------------------------------- csv / tsv / txt


def delimited(text: str, name: str, out: Rendered, lim: FormatLimits, *, encoding: str = "") -> bool:
    """Read ``text`` as one delimited table into ``out``; False when it is not a table (then: plain text)."""
    lines = text.splitlines()
    skip = 0
    delimiter, sep_lines, how = sniff_delimiter(text)
    skip += sep_lines
    # leading "# ..." comment lines (room master style) are kept as units, not table rows
    comment = skip
    while comment < len(lines) and lines[comment].lstrip().startswith("#"):
        comment += 1
    if comment > skip:
        delimiter, _, how = sniff_delimiter("\n".join(lines[comment:]))
    if delimiter is None:
        return False
    body = "\n".join(lines[comment:])
    rows: list[list[str]] = []
    truncated = False
    try:
        reader = csv.reader(io.StringIO(body), delimiter=delimiter, strict=False)
        for raw in reader:
            if len(rows) >= lim.max_rows:
                truncated = True
                break
            rows.append([tx.cell_text(c) for c in raw[: lim.max_cols]])
    except csv.Error as exc:
        raise RenderError(f"cannot read the delimited text: {exc}") from exc
    if len(rows) < 2 or max((len(r) for r in rows[:20]), default=0) < 2:
        return False
    for i in range(sep_lines, comment):
        t = tx.cell_text(lines[i].lstrip("# "))
        if t:
            out.units.append(Unit({"line": i + 1}, t))
    numbers = list(range(comment + 1, comment + len(rows) + 1))
    rows, numbers = _trim(rows, numbers)
    out.grids.append(Grid(name, "csv", rows, [], {}, numbers))
    out.warnings.append(
        f"read as {encoding or 'text'}, {_DELIM_NAMES.get(delimiter, repr(delimiter))}-separated ({how})"
    )
    if truncated:
        out.warnings.append(f"only the first {lim.max_rows} rows were read")
    return True


def _render_csv(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    text, enc = decode_text(data)
    if not delimited(text, out.filename, out, lim, encoding=enc):
        _units(text, out)


def _units(text: str, out: Rendered) -> None:
    for i, line in enumerate(text.splitlines(), start=1):
        line = tx.cell_text(line.lstrip("#*->• \t"))
        if line:
            out.units.append(Unit({"line": i}, line))


def _render_txt(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    text, enc = decode_text(data)
    if delimited(text, out.filename, out, lim, encoding=enc):
        return
    _units(text, out)


def _delimited_confidence(p: Probe) -> float:
    if p.family != "text":
        return 0.0
    delimiter, _, how = sniff_delimiter(p.text)
    if delimiter is None:
        return 0.0
    share, mode = _steadiness(_records(p.text[:SNIFF_BYTES], delimiter))
    if mode < 2:
        return 0.0
    return round(0.5 + 0.3 * share, 3)


def _sniff_csv(p: Probe) -> float:
    c = _delimited_confidence(p)
    return c if c else (0.3 if p.family == "text" and p.ext in (".csv", ".tsv") else 0.0)


def _sniff_txt(p: Probe) -> float:
    if p.family != "text":
        return 0.0
    if p.ext in (".txt", ".md", ".text"):  # a delimited .txt is still read as a table by the txt renderer
        return max(0.3, _delimited_confidence(p))
    return 0.2


# --------------------------------------------------------------------------- json

_STRING = re.compile(r'"(?:[^"\\]|\\.)*"', re.S)
_BRACKET = re.compile(r"[\[\]{}]")


def json_shape(text: str) -> tuple[int, int]:
    """(maximum nesting depth, number of objects) of a JSON text without parsing it."""
    depth = deepest = objects = 0
    for m in _BRACKET.finditer(_STRING.sub('""', text)):
        ch = m.group(0)
        if ch in "[{":
            depth += 1
            deepest = max(deepest, depth)
            objects += ch == "{"
        else:
            depth -= 1
    return deepest, objects


def load_json(data: bytes, lim: FormatLimits) -> Any:
    if len(data) > lim.max_bytes:
        raise safe_files.UnsafeFileError(413, f"JSON files may be at most {lim.max_bytes // MiB} MiB")
    text, _ = decode_text(data)
    depth, objects = json_shape(text)
    if depth > lim.max_depth:
        raise safe_files.UnsafeFileError(413, f"the JSON is nested {depth} levels deep (at most {lim.max_depth})")
    if objects > lim.max_objects:
        raise safe_files.UnsafeFileError(413, f"the JSON holds {objects} objects (at most {lim.max_objects})")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        msg = exc.msg if isinstance(exc, json.JSONDecodeError) else "too deep"
        raise safe_files.UnsafeFileError(400, f"invalid JSON: {msg}") from exc


def _json_cell(v: Any) -> str:
    if isinstance(v, (dict, list)):
        if isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v):
            return ", ".join(tx.cell_text(x) for x in v)
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))[:2000]
    if isinstance(v, bool):
        return "true" if v else "false"
    return tx.cell_text(v)


def _table(name: str, items: list[Any], lim: FormatLimits, origin: dict[str, Any]) -> Grid | None:
    dicts = [i for i in items if isinstance(i, dict)][: lim.max_rows]
    if not dicts:
        return None
    keys = list(dict.fromkeys(k for d in dicts for k in d))[: lim.max_cols]
    rows = [keys] + [[_json_cell(d.get(k)) for k in keys] for d in dicts]
    return Grid(name, "json", rows, [], origin, list(range(1, len(rows) + 1)))


def _render_json(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    obj = load_json(data, lim)
    tables: list[tuple[str, list[Any]]] = []
    native = isinstance(obj, dict) and str(obj.get("schema") or "") == INTAKE_V1
    if isinstance(obj, list):
        tables.append(("records", obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list):
                tables.append((str(k), v))
            elif isinstance(v, dict):  # one level down: {"data": {"items": [...]}}
                tables.extend((f"{k}.{k2}", v2) for k2, v2 in v.items() if isinstance(v2, list))
    for name, items in tables:
        origin: dict[str, Any] = {"table": name}
        if native:
            origin["schema"] = INTAKE_V1
        g = _table(name, items, lim, origin)
        if g is not None:
            out.grids.append(g)
    if native:
        out.warnings.append(f"native {INTAKE_V1} document: rooms, requests and timetable are read as records")
    if not out.grids:
        raise RenderError("the JSON holds no array of objects (nothing to read as rows)")


def _precheck_json(data: bytes, lim: FormatLimits) -> None:
    load_json(data, lim)


def _sniff_json(p: Probe) -> float:
    if p.family != "text":
        return 0.0
    s = p.text.lstrip("﻿ \t\r\n")
    if s[:1] not in ("{", "["):
        return 0.0
    return 0.95 if p.ext == ".json" else 0.9


# --------------------------------------------------------------------------- intake.v1 -> council records


def _list(v: Any) -> list[Any]:
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _days(v: Any) -> list[int]:
    from app.importers import normalize as n

    out: list[int] = []
    for x in _list(v):
        if isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 7:
            out.append(x)
        else:
            out.extend(n.parse_day(str(x)).days)
    return sorted(dict.fromkeys(out))


def _hhmm(v: Any) -> str | None:
    from app.importers import normalize as n

    if v in (None, ""):
        return None
    t = n.parse_time(str(v))  # 08:30, 8.30, 8,30, 08:30:00
    return t.strftime("%H:%M") if t else None


def _weeks(v: Any) -> list[int]:
    from app.importers import normalize as n

    if isinstance(v, list) and all(isinstance(x, int) and not isinstance(x, bool) for x in v):
        return sorted({x for x in v if 1 <= x <= 60})
    if v in (None, ""):
        return []
    return list(n.parse_weeks(str(v), max_week=60).weeks)


def _rooms(v: Any) -> list[str]:
    from app.importers import normalize as n

    out: list[str] = []
    for x in _list(v):
        out.extend(n.parse_room_codes(str(x)))
    return list(dict.fromkeys(out))


def _people(v: Any) -> list[str]:
    from app.importers import normalize as n

    out: list[str] = []
    for x in _list(v):
        out.extend(n.split_person_names(str(x)))
    return out


def _int(v: Any) -> int | None:
    from app.importers import normalize as n

    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return n.parse_int_loose(v) if v not in (None, "") else None


def intake_records(
    data: bytes, filename: str, lim: FormatLimits | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Council records of a ``smartsched.intake.v1`` document (the importers' normalisers on every value)."""
    from app.importers import normalize as n

    obj = load_json(data, lim or FormatLimits(max_bytes=10 * MiB))
    if not isinstance(obj, dict) or obj.get("schema") != INTAKE_V1:
        raise RenderError(f"not a {INTAKE_V1} document")
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for i, r in enumerate(_list(obj.get("rooms")), start=1):
        if not isinstance(r, dict):
            warnings.append(f"rooms[{i - 1}]: not an object, skipped")
            continue
        codes = n.parse_room_codes(str(r.get("code") or ""))
        if not codes:
            warnings.append(f"rooms[{i - 1}]: no room code, skipped")
            continue
        out.append(
            {
                "type": "room",
                "code": codes[0],
                "label": tx.cell_text(r.get("name") or r.get("label")) or n.display_room_code(codes[0]),
                "capacity": _int(r.get("capacity")),
                "exam_capacity": _int(r.get("exam_capacity")),
                "building": tx.cell_text(r.get("building")) or None,
                "floor": tx.cell_text(r.get("floor")) or None,
                "tags": [str(t).upper() for t in _list(r.get("tags"))],
                "bookable": r.get("bookable") if isinstance(r.get("bookable"), bool) else None,
                "notes": tx.cell_text(r.get("notes")) or None,
                "warnings": [],
                "confidence": 1.0,
                "source": {"file": filename, "table": "rooms", "row": i, "pointer": f"/rooms/{i - 1}"},
            }
        )
    for i, r in enumerate(_list(obj.get("requests")), start=1):
        if not isinstance(r, dict):
            warnings.append(f"requests[{i - 1}]: not an object, skipped")
            continue
        code, code_warning = n.canon_course_code_loose(r.get("course_code"), r.get("course_name"))
        if code is None:
            warnings.append(f"requests[{i - 1}]: no course code, skipped")
            continue
        days = _days(r.get("days", r.get("day")))
        mode = n.parse_mode(r.get("mode"))
        rec_warnings = [code_warning] if code_warning else []
        start, end = _hhmm(r.get("start")), _hhmm(r.get("end"))
        if r.get("start") not in (None, "") and start is None:
            rec_warnings.append(f"unparseable start time {r.get('start')!r}")
        years = [y for y in (_int(x) for x in _list(r.get("class_years", r.get("class_year")))) if y]
        out.append(
            {
                "type": "meeting",
                "course_code": code,
                "course_name": tx.cell_text(r.get("course_name")) or None,
                "section": n.parse_section_label(r.get("section")),
                "program": tx.cell_text(r.get("program")) or None,
                "faculty": tx.cell_text(r.get("faculty")) or None,
                "class_years": years,
                "enrolment": _int(r.get("enrolment")),
                "days": days,
                "flexible_day": bool(r.get("flexible_day")) or len(days) > 1,
                "start": start,
                "end": end,
                "room_request": tx.cell_text(r.get("room_request")) or None,
                "rooms": _rooms(r.get("rooms")),
                "room_text": ", ".join(str(x) for x in _list(r.get("rooms"))) or None,
                "instructors": _people(r.get("instructors")),
                "mode": mode.mode,
                "needs_room": bool(r.get("needs_room", mode.needs_room)),
                "weeks": _weeks(r.get("weeks")),
                "weeks_text": None,
                "notes": tx.cell_text(r.get("notes")) or None,
                "warnings": rec_warnings,
                "confidence": 1.0,
                "source": {"file": filename, "table": "requests", "row": i, "pointer": f"/requests/{i - 1}"},
            }
        )
    for i, r in enumerate(_list(obj.get("timetable")), start=1):
        if not isinstance(r, dict):
            warnings.append(f"timetable[{i - 1}]: not an object, skipped")
            continue
        rooms = _rooms(r.get("room") or r.get("rooms"))
        when = tx.parse_date(r.get("date")) if r.get("date") else None
        days = _days(r.get("day")) if r.get("day") not in (None, "") else ([when.isoweekday()] if when else [])
        text = tx.cell_text(r.get("text") or r.get("summary") or " ".join(map(str, _list(r.get("course_codes")))))
        codes = [c for c in (n.course_key(str(x)) for x in _list(r.get("course_codes"))) if c] or tx.course_codes(text)
        if not rooms or not days:
            warnings.append(f"timetable[{i - 1}]: needs a room and a day or date, skipped")
            continue
        for room in rooms:
            out.append(
                {
                    "type": "booking",
                    "sheet": None,
                    "week_index": _int(r.get("week")),
                    "sheet_kind": None,
                    "day": days[0],
                    "day_text": None,
                    "date": when.isoformat() if when else None,
                    "room_code": room,
                    "room_label": n.display_room_code(room),
                    "room_capacity": None,
                    "room_tags": [],
                    "start": _hhmm(r.get("start")),
                    "end": _hhmm(r.get("end")),
                    "slot_start": None,
                    "slot_end": None,
                    "text": text,
                    "course_codes": codes,
                    "section": n.parse_section_label(r.get("section")) if r.get("section") else None,
                    "warnings": [],
                    "confidence": 1.0,
                    "source": {"file": filename, "table": "timetable", "row": i, "pointer": f"/timetable/{i - 1}"},
                }
            )
    return out, warnings


register(
    FormatSpec(
        "csv",
        "CSV / TSV",
        "text",
        (".csv", ".tsv"),
        "structured",
        _sniff_csv,
        _render_csv,
        FormatLimits(max_bytes=15 * MiB),
    )
)
register(
    FormatSpec(
        "json",
        "JSON",
        "text",
        (".json",),
        "structured",
        _sniff_json,
        _render_json,
        FormatLimits(max_bytes=10 * MiB),
        _precheck_json,
    )
)
register(
    FormatSpec(
        "txt",
        "plain text",
        "text",
        (".txt", ".md", ".text"),
        "ai",
        _sniff_txt,
        _render_txt,
        FormatLimits(max_bytes=2 * MiB),
    )
)

__all__ = [
    "INTAKE_V1",
    "decode_text",
    "delimited",
    "intake_records",
    "json_shape",
    "load_json",
    "sniff_delimiter",
]
