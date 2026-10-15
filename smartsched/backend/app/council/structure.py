"""Structure analyst, deterministic part: what is this sheet, and which column is which field?

For every :class:`~app.council.render.Grid` it produces a :class:`SheetAnalysis`:

* **timetable grids** are recognised by their *axes*: a run of at least 4 time-slot cells down a column
  (vertical) or across a row (horizontal, i.e. a transposed board). The row (or column) just before the
  run holds the entity headers (rooms), and day labels sit in "day rows" above.
* **lists** get a header row (the row with the most lexicon hits among the first 30) and a one-to-one
  column -> field mapping from :func:`app.council.lexicon.guess_column`, each with a confidence.
* the **kind** (room list, request list, exam list, timetable grid, calendar, staff list, rules, other)
  follows from which fields are present.

The model (when configured) is a second voter; see :mod:`app.council.llm`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from typing import Any

from app.council import lexicon
from app.council import text as tx
from app.council.render import Grid, Rendered

KINDS = (
    "room_list",
    "request_list",
    "exam_list",
    "timetable_grid",
    "calendar",
    "staff_list",
    "rules",
    "other",
)
KIND_LABELS = {
    "room_list": "room list",
    "request_list": "course / request list",
    "exam_list": "exam list",
    "timetable_grid": "existing timetable grid",
    "calendar": "calendar / holidays",
    "staff_list": "staff list",
    "rules": "preferences / rules",
    "other": "other",
}
MULTI_FIELDS = {"notes"}
MIN_AXIS = 4
HEADER_SCAN = 30


@dataclass
class ColumnMap:
    index: int
    header: str
    field: str | None
    confidence: float
    alternatives: list[list[Any]] = dc_field(default_factory=list)  # [[field, score], ...]
    samples: list[str] = dc_field(default_factory=list)
    source: str = "heuristic"  # heuristic | llm | consensus | review


@dataclass
class TimeAxis:
    orientation: str  # vertical: slots down column ``line``; horizontal: slots across row ``line``
    line: int
    start: int  # first slot row (vertical) / column (horizontal)
    end: int  # last slot, inclusive
    header: int  # row (vertical) / column (horizontal) holding the entity headers
    slots: list[list[str]] = dc_field(default_factory=list)  # [["08:30", "09:10"], ...]
    stop: int = -1  # last entity column (vertical) / row (horizontal), inclusive


@dataclass
class SheetAnalysis:
    grid: int  # index into Rendered.grids; -1 = the file's free-text units
    name: str
    kind: str
    confidence: float
    header_rows: list[int] = dc_field(default_factory=list)
    columns: list[ColumnMap] = dc_field(default_factory=list)
    axes: list[TimeAxis] = dc_field(default_factory=list)
    language: str = "und"
    notes: list[str] = dc_field(default_factory=list)
    source: str = "heuristic"

    def mapping(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for c in self.columns:
            if c.field:
                out.setdefault(c.field, []).append(c.index)
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SheetAnalysis:
        d = dict(d)
        d["columns"] = [ColumnMap(**c) for c in d.get("columns", [])]
        d["axes"] = [TimeAxis(**a) for a in d.get("axes", [])]
        return cls(**d)


# ---------------------------------------------------------------------------
# Timetable axes
# ---------------------------------------------------------------------------


def _slot(cell: str) -> tuple[str, str | None] | None:
    if not cell:
        return None
    rng = tx.parse_time_range(cell)
    if rng:
        return tx.hhmm(rng[0]) or "", tx.hhmm(rng[1])
    if len(cell) <= 8 and (":" in cell or "." in cell):
        t = tx.parse_clock(cell)
        if t is not None:
            return tx.hhmm(t) or "", None
    return None


def _increasing(slots: list[tuple[str, str | None]]) -> bool:
    starts = [s for s, _ in slots]
    return all(a < b for a, b in zip(starts, starts[1:], strict=False))


def _transpose(cells: list[list[str]]) -> list[list[str]]:
    width = max((len(r) for r in cells), default=0)
    return [[r[c] if c < len(r) else "" for r in cells] for c in range(width)]


def _vertical_axes(cells: list[list[str]]) -> list[TimeAxis]:
    axes: list[TimeAxis] = []
    width = max((len(r) for r in cells), default=0)
    for c in range(width):
        r = 0
        while r < len(cells):
            s = _slot(cells[r][c] if c < len(cells[r]) else "")
            if s is None:
                r += 1
                continue
            start = r
            slots: list[tuple[str, str | None]] = []
            while r < len(cells):
                s2 = _slot(cells[r][c] if c < len(cells[r]) else "")
                if s2 is None:
                    break
                slots.append(s2)
                r += 1
            if len(slots) >= MIN_AXIS and start >= 1 and _increasing(slots):
                filled: list[list[str]] = []
                for i, (a, b) in enumerate(slots):
                    if b is None:
                        b = slots[i + 1][0] if i + 1 < len(slots) else a
                    filled.append([a, b])
                axes.append(TimeAxis("vertical", c, start, r - 1, start - 1, filled))
    # an axis column ends the entity band of the axis to its left
    by_rows: dict[tuple[int, int], list[TimeAxis]] = {}
    for ax in axes:
        by_rows.setdefault((ax.start, ax.end), []).append(ax)
    for group in by_rows.values():
        group.sort(key=lambda t: t.line)
        for i, ax in enumerate(group):
            ax.stop = (group[i + 1].line - 1) if i + 1 < len(group) else width - 1
    return axes


def find_axes(grid: Grid) -> list[TimeAxis]:
    vertical = _vertical_axes(grid.cells)
    horizontal = _vertical_axes(_transpose(grid.cells))
    for a in horizontal:
        a.orientation = "horizontal"
    # keep axes whose header line actually names >= 2 entities
    out: list[TimeAxis] = []
    for a in vertical + horizontal:
        cells = grid.cells if a.orientation == "vertical" else _transpose(grid.cells)
        header = cells[a.header] if a.header < len(cells) else []
        names = [h for h in header[a.line + 1 : a.stop + 1] if h and _slot(h) is None]
        # a list's header row ("Course Code", "Start Time" ...) is not a row of entity headers
        if len(names) >= 2 and _header_hits(list(dict.fromkeys(names))) < 2:
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# Header row and column mapping
# ---------------------------------------------------------------------------


def _header_hits(row: list[str]) -> int:
    fields = set()
    for cell in row:
        if cell and len(cell) <= 160:
            cands = lexicon.header_scores(cell)
            if cands and cands[0][1] >= 0.6:
                fields.add(cands[0][0])
    return len(fields)


def find_header_rows(grid: Grid) -> list[int]:
    best: tuple[int, int] | None = None  # (hits, row)
    for r in range(min(HEADER_SCAN, grid.n_rows)):
        hits = _header_hits(grid.cells[r])
        if hits >= 2 and (best is None or hits > best[0]):
            best = (hits, r)
    if best is None:
        return []
    h = best[1]
    rows = [h]
    # a second header row: below the first, mostly non-data cells and its own lexicon hits
    if h + 1 < grid.n_rows:
        nxt = grid.cells[h + 1]
        data_like = sum(1 for v in nxt if v and (tx.parse_clock(v) or tx.parse_int(v) is not None or tx.course_code(v)))
        if _header_hits(nxt) >= 2 and data_like == 0:
            rows.append(h + 1)
    return rows


def _column_values(grid: Grid, col: int, first_data_row: int, limit: int = 300) -> list[str]:
    out: list[str] = []
    for r in range(first_data_row, grid.n_rows):
        v = grid.cell(r, col)
        if v:
            out.append(v)
            if len(out) >= limit:
                break
    return out


def map_columns(grid: Grid, header_rows: list[int]) -> list[ColumnMap]:
    first_data = (max(header_rows) + 1) if header_rows else 0
    guesses: list[tuple[int, str, lexicon.ColumnGuess, list[str]]] = []
    for c in range(grid.n_cols):
        header = " ".join(dict.fromkeys(grid.cell(r, c) for r in header_rows if grid.cell(r, c))).strip()
        values = _column_values(grid, c, first_data)
        if not header and not values:
            continue
        guesses.append((c, header, lexicon.guess_column(header, values), values))
    # one-to-one assignment, best score first (``notes`` may repeat)
    cands: list[tuple[float, int, str]] = []
    for c, _h, g, _v in guesses:
        if g.field:
            cands.append((g.confidence, c, g.field))
        for f, s in g.alternatives:
            cands.append((float(s), c, f))
    cands.sort(key=lambda t: (-t[0], t[1]))
    headers = {c: tx.fold(h) for c, h, _g, _v in guesses}
    assigned: dict[int, tuple[str, float]] = {}
    used: dict[str, set[str]] = {}  # field -> folded headers already mapped to it
    for score, c, f in cands:
        if c in assigned or score < 0.35:
            continue
        # a field repeats only for "notes" or for a repeated column group with the same header
        # (room / capacity pairs side by side: "DERSLİK | KAPASİTE | DERSLİK | KAPASİTE")
        if f in used and f not in MULTI_FIELDS and headers[c] not in used[f]:
            continue
        assigned[c] = (f, score)
        used.setdefault(f, set()).add(headers[c])
    out: list[ColumnMap] = []
    for c, header, g, values in guesses:
        chosen: tuple[str | None, float] = assigned.get(c, (None, 0.0))
        fld, score = chosen
        alts: list[list[Any]] = [[g.field, g.confidence]] if g.field and g.field != fld else []
        alts += [[af, s] for af, s in g.alternatives if af != fld]
        out.append(ColumnMap(c, header, fld, round(score, 3), alts[:3], list(dict.fromkeys(values))[:5]))
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

_EXAM_WORDS = ("sinav", "exam", "examen", "prufung", "esame", "final", "butunleme", "midterm")
_RULE_WORDS = (
    "must",
    "should",
    "only",
    "never",
    "avoid",
    "prefer",
    "not ",
    "no ",
    "same room",
    "same time",
    "olmali",
    "olmamali",
    "sadece",
    "yalnizca",
    "tercih",
    "haric",
    "yapilmamali",
    "yapilacak",
    "ayni",
    "birlikte",
    "gerekiyor",
    "gerekli",
    "rica",
    "lab",
    "derslik",
    "kullanilabilir",
    "muss",
    "soll",
    "nur",
    "nicht",
    "doit",
    "seulement",
    "debe",
    "solo",
    "deve",
)


def _kind_from_fields(fields: set[str], header_text: str) -> tuple[str, float]:
    has = fields.__contains__
    exam_hint = any(w in tx.fold(header_text) for w in _EXAM_WORDS)
    if has("course_code") and has("date") and (has("start_time") or has("time_range")):
        return "exam_list", 0.9 if exam_hint else 0.75
    if has("course_code") and (has("day") or has("start_time") or has("time_range")):
        return "request_list", 0.9
    if has("course_code") and (has("enrolment") or has("course_name") or has("instructor")):
        return ("exam_list", 0.65) if exam_hint else ("request_list", 0.65)
    if (has("room") or has("room_request")) and (has("capacity") or has("exam_capacity")):
        return "room_list", 0.9
    if has("person_name") and (has("email") or has("title") or has("program")):
        return "staff_list", 0.8
    if has("instructor") and has("email"):
        return "staff_list", 0.75
    if (has("date") or has("start_date")) and (has("label") or has("notes") or has("weeks")):
        return "calendar", 0.75
    if has("room") and len(fields) <= 3:
        return "room_list", 0.55
    return "other", 0.3


def is_rule_text(t: str) -> bool:
    f = " " + tx.fold(t) + " "
    return len(t) >= 15 and any(w in f for w in _RULE_WORDS)


def analyze_grid(grid: Grid, index: int) -> SheetAnalysis:
    axes = find_axes(grid)
    if axes:
        n_slots = sum(a.end - a.start + 1 for a in axes)
        conf = 0.95 if n_slots >= 8 else 0.8
        orient = {a.orientation for a in axes}
        notes = [f"{len(axes)} time axis band(s), {n_slots} slot rows, orientation {'/'.join(sorted(orient))}"]
        return SheetAnalysis(index, grid.name, "timetable_grid", conf, axes=axes, notes=notes)
    header_rows = find_header_rows(grid)
    columns = map_columns(grid, header_rows)
    fields = {c.field for c in columns if c.field}
    header_text = " ".join(c.header for c in columns) + " " + grid.name
    kind, conf = _kind_from_fields(fields, header_text)
    key = [c.confidence for c in columns if c.field in {"course_code", "room", "capacity", "date", "day"}]
    if key and kind != "other":
        conf = round(min(conf, 0.5 + 0.5 * (sum(key) / len(key))), 3)
    if not header_rows:
        conf = min(conf, 0.5)
    lang, _ = tx.detect_language([c.header for c in columns])
    notes = []
    if not header_rows:
        notes.append("no header row recognised; columns mapped from their values only")
    return SheetAnalysis(index, grid.name, kind, conf, header_rows, columns, [], lang, notes)


def analyze_units(rendered: Rendered) -> SheetAnalysis | None:
    if not rendered.units:
        return None
    rules = [u for u in rendered.units if is_rule_text(u.text)]
    share = len(rules) / len(rendered.units)
    if rules and share >= 0.2:
        return SheetAnalysis(-1, "text", "rules", round(min(0.9, 0.5 + share / 2), 3), language=rendered.language)
    return SheetAnalysis(-1, "text", "other", 0.4, language=rendered.language)


def analyze(rendered: Rendered) -> list[SheetAnalysis]:
    out = [analyze_grid(g, i) for i, g in enumerate(rendered.grids)]
    unit_analysis = analyze_units(rendered)
    if unit_analysis is not None:
        out.append(unit_analysis)
    return out


__all__ = [
    "KINDS",
    "KIND_LABELS",
    "ColumnMap",
    "SheetAnalysis",
    "TimeAxis",
    "analyze",
    "analyze_grid",
    "find_axes",
    "find_header_rows",
    "is_rule_text",
    "map_columns",
]
