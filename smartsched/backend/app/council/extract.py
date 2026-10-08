"""Extractor: typed records with provenance from a rendered file and its structure analysis.

Every record is a JSON-ready dict with a ``type`` (``meeting``, ``exam``, ``room``, ``staff``,
``calendar``, ``booking``), the parsed fields, ``warnings``, a ``confidence`` and a ``source``. The
source has the file plus ``sheet``/``row``/``col``/``cell`` or ``page``/``line``, so the review screen can
show where a value came from. Free text that may contain rules becomes ``rule_text`` units for the rule
miner.

The extractor is deterministic: once a column mapping is fixed (by the heuristic voter, the model or a
human reviewer), re-running it gives the same records. That makes review edits cheap to apply.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.council import text as tx
from app.council.render import Grid, Rendered, col_letter
from app.council.structure import SheetAnalysis, TimeAxis, _transpose, is_rule_text
from app.importers import normalize as n

Record = dict[str, Any]


def _src(filename: str, ref: dict[str, Any]) -> dict[str, Any]:
    return {"file": filename, **ref}


def _get(grid: Grid, r: int, cols: list[int] | None) -> str:
    if not cols:
        return ""
    return " ".join(v for v in (grid.cell(r, c) for c in cols) if v).strip()


def _is_header_repeat(grid: Grid, r: int, header_rows: list[int]) -> bool:
    return any(grid.cells[r] == grid.cells[h] for h in header_rows)


def _conf(analysis: SheetAnalysis, keys: Iterable[str]) -> float:
    cols = {c.field: c.confidence for c in analysis.columns if c.field}
    vals = [cols[k] for k in keys if k in cols]
    base = min([analysis.confidence, *vals]) if vals else analysis.confidence
    return round(base, 3)


def _mode_needs_room(mode: str | None, *texts: str) -> bool:
    if mode in tx.ROOMLESS_MODES:
        return False
    for t in texts:
        if t and tx.parse_mode(t) in tx.ROOMLESS_MODES and not tx.parse_days(t, allow_abbrev=False):
            return False
        if t and n.parse_day(t).needs_room is False:
            return False
    return True


# ---------------------------------------------------------------------------
# List-shaped sheets
# ---------------------------------------------------------------------------


def _times(grid: Grid, r: int, m: dict[str, list[int]], day_text: str) -> tuple[str | None, str | None, list[str]]:
    warnings: list[str] = []
    start = tx.parse_clock(_get(grid, r, m.get("start_time"))) if m.get("start_time") else None
    end = tx.parse_clock(_get(grid, r, m.get("end_time"))) if m.get("end_time") else None
    if (start is None or end is None) and (m.get("time_range") or day_text):
        rng = tx.parse_time_range(_get(grid, r, m.get("time_range")) or day_text)
        if rng:
            start, end = rng
    if start is not None and end is not None and tx.minutes(end) <= tx.minutes(start):
        warnings.append(f"end time {tx.hhmm(end)} is not after start time {tx.hhmm(start)}")
    return tx.hhmm(start), tx.hhmm(end), warnings


def _course(grid: Grid, r: int, m: dict[str, list[int]]) -> tuple[str | None, list[str]]:
    raw = _get(grid, r, m.get("course_code"))
    code = tx.course_code(raw)
    if code:
        return code, []
    code, warning = n.canon_course_code_loose(raw, _get(grid, r, m.get("course_name")))
    return code, [warning] if warning else []


def _meetings(rendered: Rendered, grid: Grid, a: SheetAnalysis, max_week: int) -> list[Record]:
    m = a.mapping()
    out: list[Record] = []
    first = (max(a.header_rows) + 1) if a.header_rows else 0
    base_conf = _conf(a, ("course_code", "day", "start_time"))
    for r in range(first, grid.n_rows):
        if not any(grid.cells[r]) or _is_header_repeat(grid, r, a.header_rows):
            continue
        code, warnings = _course(grid, r, m)
        if not code:
            continue
        day_text = _get(grid, r, m.get("day"))
        days = tx.parse_days(day_text)
        start, end, tw = _times(grid, r, m, day_text)
        warnings += tw
        mode_text = _get(grid, r, m.get("mode"))
        mode = tx.parse_mode(mode_text)
        if not days and day_text and tx.parse_mode(day_text) in tx.ROOMLESS_MODES:
            mode = mode if mode not in (None, "OTHER") else tx.parse_mode(day_text)
        needs_room = _mode_needs_room(mode, day_text)
        if needs_room and not days:
            warnings.append(f"no day recognised in {day_text!r}" if day_text else "no day given")
        if needs_room and days and (start is None or end is None):
            warnings.append("no start/end time")
        weeks_text = _get(grid, r, m.get("weeks"))
        weeks = n.parse_weeks(weeks_text, max_week=max_week) if weeks_text else None
        rec: Record = {
            "type": "meeting",
            "course_code": code,
            "course_name": _get(grid, r, m.get("course_name")) or None,
            "section": n.parse_section_label(_get(grid, r, m.get("section"))),
            "program": _get(grid, r, m.get("program")) or None,
            "faculty": _get(grid, r, m.get("faculty")) or None,
            "class_years": n.parse_class_year(_get(grid, r, m.get("class_year"))),
            "enrolment": tx.parse_int(_get(grid, r, m.get("enrolment"))),
            "days": days,
            "flexible_day": len(days) > 1 or (not days and bool(day_text)),
            "start": start,
            "end": end,
            "room_request": _get(grid, r, m.get("room_request")) or None,
            "rooms": tx.room_tokens(_get(grid, r, m.get("room"))),
            "room_text": _get(grid, r, m.get("room")) or None,
            "instructors": n.split_person_names(_get(grid, r, m.get("instructor")))
            + n.split_person_names(_get(grid, r, m.get("instructor2"))),
            "mode": mode,
            "needs_room": needs_room,
            "weeks": weeks.weeks if weeks else [],
            "weeks_text": weeks_text or None,
            "notes": _get(grid, r, m.get("notes")) or None,
            "warnings": warnings,
            "confidence": round(base_conf - (0.15 if warnings else 0.0), 3),
            "source": _src(rendered.filename, grid.ref(r)),
        }
        out.append(rec)
    return out


def _exams(rendered: Rendered, grid: Grid, a: SheetAnalysis, year_hint: int | None) -> list[Record]:
    m = a.mapping()
    out: list[Record] = []
    first = (max(a.header_rows) + 1) if a.header_rows else 0
    base_conf = _conf(a, ("course_code", "date", "start_time"))
    for r in range(first, grid.n_rows):
        if not any(grid.cells[r]) or _is_header_repeat(grid, r, a.header_rows):
            continue
        code, warnings = _course(grid, r, m)
        if not code:
            continue
        date_text = _get(grid, r, m.get("date"))
        d = tx.parse_date(date_text, year_hint)
        if date_text and d is None:
            warnings.append(f"unrecognised date {date_text!r}")
        start, end, tw = _times(grid, r, m, "")
        warnings += tw
        venue = _get(grid, r, m.get("room_request"))
        rooms_text = _get(grid, r, m.get("room"))
        needs_room = _mode_needs_room(None, date_text, venue)
        out.append(
            {
                "type": "exam",
                "course_code": code,
                "course_name": _get(grid, r, m.get("course_name")) or None,
                "program": _get(grid, r, m.get("program")) or None,
                "faculty": _get(grid, r, m.get("faculty")) or None,
                "class_years": n.parse_class_year(_get(grid, r, m.get("class_year"))),
                "enrolment": tx.parse_int(_get(grid, r, m.get("enrolment"))),
                "instructor": _get(grid, r, m.get("instructor")) or None,
                "date": d.isoformat() if d else None,
                "start": start,
                "end": end,
                "venue_text": venue or None,
                "rooms": tx.room_tokens(rooms_text),
                "room_text": rooms_text or None,
                "needs_room": needs_room,
                "notes": _get(grid, r, m.get("notes")) or None,
                "warnings": warnings,
                "confidence": round(base_conf - (0.15 if warnings else 0.0), 3),
                "source": _src(rendered.filename, grid.ref(r)),
            }
        )
    return out


_TAG_SPLIT = re.compile(r"[\s,;/|+]+")


def _rooms(rendered: Rendered, grid: Grid, a: SheetAnalysis) -> list[Record]:
    m = a.mapping()
    room_cols = sorted(m.get("room", []) or m.get("room_request", []))
    cap_cols = sorted(m.get("capacity", []))
    out: list[Record] = []
    first = (max(a.header_rows) + 1) if a.header_rows else 0
    base_conf = _conf(a, ("room", "capacity"))
    for i, rc in enumerate(room_cols):
        nxt = room_cols[i + 1] if i + 1 < len(room_cols) else 10**6
        own_cap = [c for c in cap_cols if rc < c < nxt] or ([cap_cols[0]] if len(room_cols) == 1 and cap_cols else [])
        single = len(room_cols) == 1
        for r in range(first, grid.n_rows):
            label = grid.cell(r, rc)
            if not label or _is_header_repeat(grid, r, a.header_rows):
                continue
            codes = tx.room_tokens(label)
            if len(codes) != 1:
                if not any(ch.isdigit() for ch in label):
                    continue
                codes = [tx.canon_room(label)]
            tags_text = _get(grid, r, m.get("room_type")) if single else ""
            tags = [n.tr_upper(t) for t in _TAG_SPLIT.split(tags_text) if t and t != "-"] if tags_text else []
            bookable = None
            out.append(
                {
                    "type": "room",
                    "code": codes[0],
                    "label": label,
                    "capacity": tx.parse_int(_get(grid, r, own_cap[:1])),
                    "exam_capacity": tx.parse_int(_get(grid, r, m.get("exam_capacity"))) if single else None,
                    "building": (_get(grid, r, m.get("building")) or None) if single else None,
                    "floor": (_get(grid, r, m.get("floor")) or None) if single else None,
                    "tags": list(dict.fromkeys(tags)),
                    "bookable": bookable,
                    "notes": (_get(grid, r, m.get("notes")) or None) if single else None,
                    "warnings": [],
                    "confidence": base_conf,
                    "source": _src(rendered.filename, grid.ref(r, rc)),
                }
            )
    return out


def _staff(rendered: Rendered, grid: Grid, a: SheetAnalysis) -> list[Record]:
    m = a.mapping()
    name_cols = m.get("person_name") or m.get("instructor")
    out: list[Record] = []
    first = (max(a.header_rows) + 1) if a.header_rows else 0
    for r in range(first, grid.n_rows):
        name = _get(grid, r, name_cols)
        if not name or _is_header_repeat(grid, r, a.header_rows):
            continue
        out.append(
            {
                "type": "staff",
                "name": name,
                "key": tx.person_key(name),
                "email": _get(grid, r, m.get("email")) or None,
                "title": _get(grid, r, m.get("title")) or None,
                "department": _get(grid, r, m.get("program")) or None,
                "warnings": [],
                "confidence": _conf(a, ("person_name",)),
                "source": _src(rendered.filename, grid.ref(r)),
            }
        )
    return out


_HOLIDAY = ("tatil", "holiday", "bayram", "ferien", "vacances", "vacaciones", "feriado", "break", "closed", "kapali")
_EXAMW = ("sinav", "exam", "final", "butunleme", "prufung", "examen")


def _calendar(rendered: Rendered, grid: Grid, a: SheetAnalysis, year_hint: int | None) -> list[Record]:
    m = a.mapping()
    out: list[Record] = []
    first = (max(a.header_rows) + 1) if a.header_rows else 0
    for r in range(first, grid.n_rows):
        label = _get(grid, r, m.get("label") or m.get("notes"))
        d1 = tx.parse_date(_get(grid, r, m.get("start_date") or m.get("date")), year_hint)
        d2 = tx.parse_date(_get(grid, r, m.get("end_date")), year_hint) if m.get("end_date") else None
        if d1 is None:
            continue
        f = tx.fold(label)
        kind = "HOLIDAY" if any(w in f for w in _HOLIDAY) else "EXAM" if any(w in f for w in _EXAMW) else "OTHER"
        out.append(
            {
                "type": "calendar",
                "label": label or None,
                "start_date": d1.isoformat(),
                "end_date": (d2 or d1).isoformat(),
                "kind": kind,
                "warnings": [],
                "confidence": _conf(a, ("date", "start_date", "label")),
                "source": _src(rendered.filename, grid.ref(r)),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Timetable grids
# ---------------------------------------------------------------------------

_CAP_RX = re.compile(r"\((\d{1,4})\)|\b(?:cap(?:acity)?|kapasite|seats|plätze|places)\s*[:=]?\s*(\d{1,4})\b", re.I)


def parse_entity_header(text: str) -> dict[str, Any]:
    """Room header cell -> {code, label, capacity, tags} (``A 201\\n(96)\\nTIP``, ``Room 1.12 (cap 40)``)."""
    known = n.parse_room_header(text)
    if known is not None:
        return {"code": known.code, "label": known.display_name, "capacity": known.capacity, "tags": known.tags}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    label = lines[0] if lines else text.strip()
    m = _CAP_RX.search(text)
    cap = int(m.group(1) or m.group(2)) if m else None
    label = _CAP_RX.sub("", label).strip(" -:")
    tags = [n.tr_upper(t) for ln in lines[1:] for t in ln.split() if not _CAP_RX.fullmatch(t) and t.isalpha()]
    codes = tx.room_tokens(label)
    code = codes[0] if len(codes) == 1 else tx.canon_room(label)
    return {"code": code, "label": label, "capacity": cap, "tags": tags}


def _day_rows(cells: list[list[str]], upto: int) -> list[int]:
    rows = []
    for r in range(0, min(upto, len(cells))):
        vals = [v for v in cells[r] if v]
        if not vals:
            continue
        hits = sum(1 for v in vals if tx.parse_days(v, allow_abbrev=False))
        if hits and hits >= len(vals) / 2:
            rows.append(r)
    return rows


def _year_hint_from(grid: Grid, year_hint: int | None) -> int | None:
    years = tx.years_in(grid.name)
    return years[0] if years else year_hint


def _bookings(rendered: Rendered, grid: Grid, a: SheetAnalysis, year_hint: int | None) -> list[Record]:
    out: list[Record] = []
    year = _year_hint_from(grid, year_hint)
    for axis in a.axes:
        cells = grid.cells if axis.orientation == "vertical" else _transpose(grid.cells)

        def ref(r: int, c: int, axis: TimeAxis = axis) -> dict[str, Any]:
            return grid.ref(r, c) if axis.orientation == "vertical" else grid.ref(c, r)

        def coord(r: int, c: int, axis: TimeAxis = axis) -> str:
            rr, cc = (r, c) if axis.orientation == "vertical" else (c, r)
            return f"{col_letter(cc)}{grid.row_number(rr)}"

        day_rows = [d for d in _day_rows(cells, axis.header) if d < axis.header]
        header = cells[axis.header]
        for j in range(axis.line + 1, min(axis.stop, len(header) - 1) + 1):
            head = header[j] if j < len(header) else ""
            if not head:
                continue
            ent = parse_entity_header(head)
            day_text = ""
            for d in reversed(day_rows):
                if j < len(cells[d]) and cells[d][j]:
                    day_text = cells[d][j]
                    break
            days = tx.parse_days(day_text, allow_abbrev=False)
            date = tx.parse_date(day_text, year) if tx.month_in(day_text) else None
            r = axis.start
            while r <= axis.end:
                v = cells[r][j] if j < len(cells[r]) else ""
                if not v or v == head:
                    r += 1
                    continue
                r2 = r
                while r2 + 1 <= axis.end and (cells[r2 + 1][j] if j < len(cells[r2 + 1]) else "") == v:
                    r2 += 1
                slot_a = axis.slots[r - axis.start]
                slot_b = axis.slots[r2 - axis.start]
                src = _src(rendered.filename, ref(r, j))
                src["cell"] = coord(r, j) + (f":{coord(r2, j)}" if r2 > r else "")
                out.append(
                    {
                        "type": "booking",
                        "sheet": grid.name,
                        "day": days[0] if len(days) == 1 else None,
                        "day_text": day_text or None,
                        "date": date.isoformat() if date else None,
                        "room_code": ent["code"],
                        "room_label": ent["label"],
                        "room_capacity": ent["capacity"],
                        "room_tags": ent["tags"],
                        "start": slot_a[0],
                        "end": slot_b[1],
                        "slot_start": r - axis.start + 1,
                        "slot_end": r2 - axis.start + 1,
                        "text": v,
                        "course_codes": tx.course_codes(v),
                        "warnings": [] if days else ["no day label found for this column"],
                        "confidence": round(a.confidence - (0.0 if days else 0.2), 3),
                        "source": src,
                    }
                )
                r = r2 + 1
    return out


def grid_rooms(bookings: list[Record]) -> dict[str, dict[str, Any]]:
    """Rooms named by timetable headers (first header wins; capacities from the headers)."""
    rooms: dict[str, dict[str, Any]] = {}
    for b in bookings:
        rooms.setdefault(
            b["room_code"],
            {"label": b["room_label"], "capacity": b["room_capacity"], "tags": b["room_tags"], "source": b["source"]},
        )
    return rooms


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def extract(
    rendered: Rendered, analyses: list[SheetAnalysis], *, year_hint: int | None = None, max_week: int = 16
) -> list[Record]:
    """Records for every analysed grid (deterministic)."""
    records: list[Record] = []
    for a in analyses:
        if a.grid < 0:
            continue
        grid = rendered.grids[a.grid]
        if a.kind == "request_list":
            records += _meetings(rendered, grid, a, max_week)
        elif a.kind == "exam_list":
            records += _exams(rendered, grid, a, year_hint)
        elif a.kind == "room_list":
            records += _rooms(rendered, grid, a)
        elif a.kind == "staff_list":
            records += _staff(rendered, grid, a)
        elif a.kind == "calendar":
            records += _calendar(rendered, grid, a, year_hint)
        elif a.kind == "timetable_grid":
            records += _bookings(rendered, grid, a, year_hint)
    return records


def rule_texts(rendered: Rendered, analyses: list[SheetAnalysis], records: list[Record]) -> list[Record]:
    """Free text the rule miner should read: notes of meetings/exams (deduplicated, with the course
    codes that carry them) and rule-like paragraphs/lines."""
    out: list[Record] = []
    by_note: dict[str, Record] = {}
    for rec in records:
        note = rec.get("notes")
        if rec["type"] not in ("meeting", "exam") or not note or len(note) < 12:
            continue
        if note in by_note:
            codes = by_note[note]["course_codes"]
            if rec["course_code"] not in codes:
                codes.append(rec["course_code"])
            continue
        by_note[note] = {
            "type": "rule_text",
            "text": note,
            "course_codes": [rec["course_code"]],
            "source": rec["source"],
        }
    out.extend(by_note.values())
    text_kind = next((a.kind for a in analyses if a.grid < 0), None)
    for u in rendered.units:
        if text_kind == "rules" and len(u.text) >= 15 or is_rule_text(u.text):
            out.append(
                {
                    "type": "rule_text",
                    "text": u.text,
                    "course_codes": tx.course_codes(u.text)[:10],
                    "source": _src(rendered.filename, u.ref),
                }
            )
    return out


__all__ = ["Record", "extract", "grid_rooms", "parse_entity_header", "rule_texts"]
