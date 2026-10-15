"""Deterministic fast path: files that match a known shape go through the existing importers.

The four shapes are the user's university formats (``docs/DATA_ANALYSIS.md``):

* ``planning-list``: the course request list (``app.importers.planning_list``);
* ``exam-list``: the exam request list (``app.importers.exam_list``);
* ``weekly-grid``: the room x time-slot board with one sheet per week (``app.importers.weekly_grid``);
* ``room-master``: the planner's room CSV (``app.importers.room_master``).

During analysis, the importers' *pure parsers* run (no database) and their output is converted to
council records, so review, critic, reconciler and planner treat every file the same way. On commit,
the importers' own ``import_*`` functions write the file with every rule the university path has
(see :mod:`app.council.commit`). Forcing ``mode=general`` skips this module.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any

from app.council import text as tx
from app.council.render import Rendered
from app.importers import normalize as n
from app.importers.xlsx import map_headers

SHAPES = ("planning-list", "exam-list", "weekly-grid", "room-master")
#: commit order: rooms first, then the board (weeks, blocks), then requests
COMMIT_ORDER = {"room-master": 0, "weekly-grid": 1, "planning-list": 2, "exam-list": 3}

Record = dict[str, Any]


def detect_shape(rendered: Rendered) -> str | None:
    """The known shape of a file, or ``None`` (then the general council path runs)."""
    if rendered.format == "xlsx" and rendered.grids:
        from app.importers.exam_list import HEADER_SPEC as EXAM_SPEC
        from app.importers.planning_list import HEADER_SPEC as PLAN_SPEC

        g0 = rendered.grids[0]
        header: list[str | None] = [h or None for h in (g0.cells[0] if g0.cells else [])]
        plan = map_headers(header, PLAN_SPEC)
        if all(k in plan for k in ("code", "day", "start", "end", "definitive")):
            return "planning-list"
        exam = map_headers(header, EXAM_SPEC)
        if all(k in exam for k in ("code", "date", "start", "definitive")):
            return "exam-list"
        if g0.n_rows > 3 and tx.parse_days(g0.cell(0, 1), allow_abbrev=False):
            heads = [n.parse_room_header(v) for v in g0.cells[1][1:40] if v]
            slots = [n.parse_time_slot(g0.cell(r, 0)) for r in range(2, min(g0.n_rows, 8))]
            if sum(h is not None for h in heads) >= 5 and all(slots):
                return "weekly-grid"
    if rendered.format == "csv" and rendered.grids:
        header = [tx.fold(h) for h in rendered.grids[0].cells[0]]
        if "code" in header and ("capacity" in header or "exam_capacity" in header):
            return "room-master"
    return None


def _hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def _period_times(start: int | None, end: int | None) -> tuple[str | None, str | None]:
    if not start or not end:
        return None, None
    return _hhmm(n.PERIODS[start - 1].start), _hhmm(n.PERIODS[end - 1].end)


def planning_records(path: Path, filename: str) -> tuple[list[Record], list[str]]:
    from app.importers.planning_list import parse_planning_list

    parsed = parse_planning_list(path)
    out: list[Record] = []
    for r in parsed.rows:
        out.append(
            {
                "type": "meeting",
                "course_code": r.course_code,
                "course_name": r.course_name,
                "section": r.label,
                "program": r.program,
                "faculty": r.faculty,
                "class_years": r.class_years,
                "enrolment": r.enrolment,
                "days": r.day.days,
                "flexible_day": r.day.flexible or len(r.day.days) > 1,
                "start": _hhmm(r.start_time),
                "end": _hhmm(r.end_time),
                "room_request": r.venue.raw,
                "rooms": r.definitive.room_codes,
                "room_text": r.definitive.raw,
                "instructors": r.instructors + r.secondary_instructors,
                "mode": r.mode.mode,
                "needs_room": r.needs_room,
                "weeks": r.weeks.weeks,
                "weeks_text": None,
                "notes": r.notes,
                "warnings": r.warnings,
                "confidence": 1.0,
                "source": {"file": filename, "sheet": "Sayfa1", "row": r.row},
            }
        )
    for e in parsed.capacities:
        out.append(
            {
                "type": "room",
                "code": e.code,
                "label": e.raw,
                "capacity": e.capacity,
                "exam_capacity": None,
                "building": e.code[:1] if e.code[:1].isalpha() else None,
                "floor": None,
                "tags": ["PC"] if e.pc_lab else [],
                "bookable": None,
                "notes": None,
                "warnings": [],
                "confidence": 1.0,
                "source": {"file": filename, "sheet": "Sayfa2"},
            }
        )
    warnings = [f"row {row}: skipped ({reason})" for row, reason, _ in parsed.skipped[:50]]
    return out, warnings


def exam_records(path: Path, filename: str) -> tuple[list[Record], list[str]]:
    from app.importers.exam_list import parse_exam_list

    parsed = parse_exam_list(path)
    out: list[Record] = []
    for r in parsed.rows:
        out.append(
            {
                "type": "exam",
                "course_code": r.course_code,
                "course_name": r.course_name,
                "program": r.program,
                "faculty": r.faculty,
                "class_years": r.class_years,
                "enrolment": r.enrolment,
                "instructor": r.instructor,
                "date": r.date.isoformat() if r.date else None,
                "start": _hhmm(r.start_time),
                "end": _hhmm(r.end_time),
                "venue_text": r.venue.raw,
                "rooms": r.definitive.room_codes,
                "room_text": r.definitive.raw,
                "needs_room": r.needs_room,
                "notes": None,
                "warnings": r.warnings,
                "confidence": 1.0,
                "source": {"file": filename, "sheet": "Sayfa1", "row": r.row},
            }
        )
    warnings = [f"row {row}: skipped ({reason})" for row, reason, _ in parsed.skipped[:50]]
    return out, warnings


def grid_records(path: Path, filename: str, year: int) -> tuple[list[Record], list[str]]:
    from app.importers.weekly_grid import parse_weekly_grid

    parsed = parse_weekly_grid(path, year)
    out: list[Record] = []
    for s in parsed.sheets:
        for e in s.entries:
            start, end = _period_times(e.start_period, e.end_period)
            h = s.rooms.get(e.room_code) or parsed.rooms.get(e.room_code)
            out.append(
                {
                    "type": "booking",
                    "sheet": s.name,
                    "week_index": s.week_index,
                    "sheet_kind": s.kind,
                    "day": e.day,
                    "day_text": None,
                    "date": e.date.isoformat() if e.date else None,
                    "room_code": e.room_code,
                    "room_label": h.display_name if h else n.display_room_code(e.room_code),
                    "room_capacity": h.capacity if h else None,
                    "room_tags": h.tags if h else [],
                    "start": start,
                    "end": end,
                    "slot_start": e.start_period,
                    "slot_end": e.end_period,
                    "text": e.cell.raw,
                    "course_codes": e.cell.codes,
                    "warnings": [],
                    "confidence": 1.0,
                    "source": {"file": filename, "sheet": s.name, "cell": e.coord},
                }
            )
    return out, parsed.warnings[:50]


def room_master_records(path: Path, filename: str) -> tuple[list[Record], list[str]]:
    from app.importers.room_master import parse_room_master

    rows, errors = parse_room_master(path.read_text(encoding="utf-8-sig"))
    out: list[Record] = []
    for r in rows:
        out.append(
            {
                "type": "room",
                "code": r["code"],
                "label": n.display_room_code(r["code"]),
                "capacity": r["capacity"],
                "exam_capacity": r["exam_capacity"],
                "building": r["building"],
                "floor": r["floor"],
                "tags": r["tags"] or [],
                "bookable": r["bookable"],
                "notes": r["notes"],
                "warnings": [],
                "confidence": 1.0,
                "source": {"file": filename, "row": r["line"]},
            }
        )
    return out, errors


def records_for(shape: str, path: Path, filename: str, year: int) -> tuple[list[Record], list[str]]:
    if shape == "planning-list":
        return planning_records(path, filename)
    if shape == "exam-list":
        return exam_records(path, filename)
    if shape == "weekly-grid":
        return grid_records(path, filename, year)
    if shape == "room-master":
        return room_master_records(path, filename)
    raise ValueError(f"unknown shape {shape}")


__all__ = ["COMMIT_ORDER", "SHAPES", "detect_shape", "records_for"]
