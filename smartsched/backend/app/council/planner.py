"""Planner: propose the term setup the files imply (term groups, weeks, period grid, days).

* **Term groups.** Each file gets a key from season words (spring/bahar, fall/güz, summer/yaz,
  final/büt) and years found in its name, sheet names and dates. Files with the same key form one
  group, which is committed into one term. A file with no hint joins the only group, or stays
  unassigned for the reviewer when there are several groups.
* **Weeks.** Grid sheets give week indexes and start dates (one sheet per week). Request lists give
  the highest week number they mention. Exam dates give the ISO weeks they span.
* **Period grid.** The time axis of a timetable grid when there is one. Otherwise the default
  18-period grid when at least 90 % of request start times fall on it. Otherwise a grid inferred
  from the start times (a common step between 15 and 60 minutes).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, time, timedelta
from typing import Any

from app.council import text as tx
from app.importers import normalize as n

Record = dict[str, Any]

SEASONS: dict[str, tuple[str, str]] = {
    # folded word -> (season, language)
    "bahar": ("SPRING", "tr"),
    "spring": ("SPRING", "en"),
    "fruhling": ("SPRING", "de"),
    "sommersemester": ("SPRING", "de"),
    "printemps": ("SPRING", "fr"),
    "primavera": ("SPRING", "es"),
    "guz": ("FALL", "tr"),
    "fall": ("FALL", "en"),
    "autumn": ("FALL", "en"),
    "herbst": ("FALL", "de"),
    "wintersemester": ("FALL", "de"),
    "automne": ("FALL", "fr"),
    "otono": ("FALL", "es"),
    "autunno": ("FALL", "it"),
    "yaz": ("SUMMER", "tr"),
    "summer": ("SUMMER", "en"),
    "sommer": ("SUMMER", "de"),
    "verano": ("SUMMER", "es"),
    "final": ("FINAL", "en"),
    "finals": ("FINAL", "en"),
    "butunleme": ("BUT", "tr"),
    "resit": ("BUT", "en"),
    "makeup": ("BUT", "en"),
}
CODE_WORDS = {
    ("SPRING", "tr"): "BAHAR",
    ("FALL", "tr"): "GUZ",
    ("SUMMER", "tr"): "YAZ",
    ("FINAL", "tr"): "FINAL",
    ("BUT", "tr"): "BUT",
}
KIND_OF = {"SPRING": "REGULAR", "FALL": "REGULAR", "SUMMER": "SUMMER", "FINAL": "FINAL", "BUT": "BUT"}
_WORD = re.compile(r"[a-z]+")


def season_of(texts: list[str]) -> tuple[str | None, str]:
    """(season, language of the word) from file/sheet names; exam words win over seasons."""
    found: list[tuple[str, str]] = []
    for t in texts:
        for w in _WORD.findall(tx.fold(t)):
            if w in SEASONS:
                found.append(SEASONS[w])
    for s, lang in found:
        if s in ("FINAL", "BUT"):
            return s, lang
    return found[0] if found else (None, "en")


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_start_from_text(text: str, year: int | None) -> date | None:
    """First 'day month' (or 'd - d month') in a sheet name / day label -> that date's Monday."""
    if not year:
        return None
    f = tx.fold(text)
    m = re.search(r"(\d{1,2})\s*(?:-\s*\d{1,2}\s*)?([a-z]+)", f)
    if not m:
        return None
    month = tx.MONTH_WORDS.get(m.group(2))
    if month is None:
        rest = tx.month_in(f[m.end() :])
        month = rest
    if month is None:
        return None
    try:
        return _monday(date(year, month, int(m.group(1))))
    except ValueError:
        return None


def _grid_from_starts(starts: list[time], ends: list[time]) -> list[dict[str, Any]]:
    mins = sorted({tx.minutes(t) for t in starts})
    if not mins:
        return []
    step = 0
    for a in mins:
        step = math.gcd(step, a - mins[0])
    durations = [tx.minutes(e) - tx.minutes(s) for s, e in zip(starts, ends, strict=False) if e and s and e > s]
    for d in durations:
        step = math.gcd(step, d)
    step = step if 15 <= step <= 60 else (30 if step < 15 else 60)
    last = max([tx.minutes(e) for e in ends if e] + [mins[-1] + step])
    out: list[dict[str, Any]] = []
    t = mins[0]
    while t < last and len(out) < 48:
        out.append(
            {
                "index": len(out) + 1,
                "start": f"{t // 60:02d}:{t % 60:02d}",
                "end": f"{(t + step) // 60:02d}:{(t + step) % 60:02d}",
            }
        )
        t += step
    return out


DEFAULT_GRID: list[dict[str, Any]] = [
    {"index": p.index, "start": p.start.strftime("%H:%M"), "end": p.end.strftime("%H:%M")} for p in n.PERIODS
]


def period_grid(axis_slots: list[list[list[str]]], meetings: list[Record]) -> dict[str, Any]:
    starts = [s for s in (tx.from_hhmm(m.get("start")) for m in meetings) if s]
    ends = [e for e in (tx.from_hhmm(m.get("end")) for m in meetings) if e]
    if axis_slots:
        slots = Counter(tuple(tuple(s) for s in ax) for ax in axis_slots).most_common(1)[0][0]
        periods = [{"index": i + 1, "start": a, "end": b} for i, (a, b) in enumerate(slots)]
        source = "timetable-grid"
    else:
        default_starts = {p.start for p in n.PERIODS}
        on_default = sum(1 for s in starts if s in default_starts)
        if starts and on_default / len(starts) >= 0.9:
            periods, source = DEFAULT_GRID, "default-18"
        elif starts:
            periods, source = _grid_from_starts(starts, ends), "inferred"
        else:
            periods, source = DEFAULT_GRID, "default-18"
    grid_starts = {p["start"] for p in periods}
    coverage = round(sum(1 for s in starts if tx.hhmm(s) in grid_starts) / len(starts), 3) if starts else None
    if source == "timetable-grid" and periods == DEFAULT_GRID:
        source = "timetable-grid (= default 18-period grid)"
    return {"source": source, "periods": periods, "coverage": coverage}


def plan(
    files: list[dict[str, Any]], records: dict[int, list[Record]], axis_slots: list[list[list[str]]]
) -> dict[str, Any]:
    """``files`` = [{index, filename, sheets: [names], route}], ``records`` by file index."""
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    unassigned: list[int] = []
    file_keys: dict[int, tuple[Any, ...] | None] = {}
    global_files: list[int] = []
    sheet_names = {f["index"]: list(f.get("sheets", [])) for f in files}
    for f in files:
        idx = f["index"]
        recs = records.get(idx, [])
        if recs and all(r["type"] in ("room", "staff") for r in recs):
            global_files.append(idx)  # rooms and staff are not term-scoped: committed with every group
            continue
        names = [f["filename"], *f.get("sheets", [])]
        # the file name says what the file is; sheet names only help when it is silent
        # (a term board has "Final" week sheets, but it is still the spring board)
        season, lang = season_of([f["filename"]])
        if season is None:
            season, lang = season_of(f.get("sheets", []))
        years = sorted(set(y for t in [f["filename"]] for y in tx.years_in(t))) or sorted(
            set(y for t in names for y in tx.years_in(t))
        )
        dates = [d for d in (tx.parse_date(r.get("date")) for r in recs if r.get("date")) if d]
        if not years and dates:
            years = [Counter(d.year for d in dates).most_common(1)[0][0]]
        exam_share = sum(1 for r in recs if r["type"] == "exam") / max(
            1, sum(1 for r in recs if r["type"] in ("exam", "meeting"))
        )
        if season is None and exam_share > 0.5:
            season = "FINAL"
        if season is None and not years:
            file_keys[idx] = None
            unassigned.append(idx)
            continue
        key = (season, tuple(years[:2]))
        file_keys[idx] = key
        g = groups.setdefault(
            key, {"season": season, "lang": lang, "years": list(years[:2]), "files": [], "evidence": []}
        )
        g["files"].append(idx)
        g["evidence"].append(f"{f['filename']}: " + ", ".join(filter(None, [season or "", "/".join(map(str, years))])))
    # a season group without a year joins the group of the same season that has one
    for key in [k for k in groups if not k[1]]:
        same = [k for k in groups if k[0] == key[0] and k[1]]
        if len(same) == 1:
            target = groups[same[0]]
            target["files"].extend(groups[key]["files"])
            target["evidence"].extend(groups[key]["evidence"])
            del groups[key]
    if len(groups) == 1 and unassigned:
        only = next(iter(groups.values()))
        only["files"].extend(unassigned)
        only["evidence"].extend(f"file #{i}: no season or year found; joined the only group" for i in unassigned)
        unassigned = []
    if not groups and unassigned:
        groups[(None, ())] = {
            "season": None,
            "lang": "en",
            "years": [],
            "files": unassigned,
            "evidence": ["no season or year found in any file"],
        }
        unassigned = []

    out_groups = []
    for g in groups.values():
        recs = [r for i in g["files"] for r in records.get(i, [])]
        season = g["season"]
        years = g["years"]
        year = years[0] if years else None
        kind = KIND_OF.get(season or "", "REGULAR")
        if season == "SPRING" and len(years) == 2:
            year = years[1]
        word = CODE_WORDS.get((season or "", g["lang"])) or (season or "TERM")
        code = f"{'-'.join(map(str, years)) or 'TERM'}-{word}" if years else word
        # weeks: grid sheets (fast path gives week_index; general bookings give sheet order)
        sheets: dict[str, dict[str, Any]] = {}
        for fi in g["files"]:  # every sheet of a board is a week, even one without entries
            if any(r["type"] == "booking" for r in records.get(fi, [])):
                for name in sheet_names.get(fi, []):
                    sheets.setdefault(name, {"label": name, "index": None, "dates": [], "kind": None})
        for r in recs:
            if r["type"] != "booking":
                continue
            s = sheets.setdefault(r["sheet"], {"label": r["sheet"], "index": None, "dates": [], "kind": None})
            s["index"] = s["index"] or r.get("week_index")
            s["kind"] = s["kind"] or r.get("sheet_kind")
            if r.get("date"):
                s["dates"].append(r["date"])
        weeks: list[dict[str, Any]] = []
        for i, (name, s) in enumerate(sheets.items(), start=1):
            start = _monday(date.fromisoformat(min(s["dates"]))) if s["dates"] else _week_start_from_text(name, year)
            wk = s["kind"] or ("EXAM" if kind in ("FINAL", "BUT") else "LECTURE")
            weeks.append(
                {
                    "index": s["index"] or i,
                    "start_date": start.isoformat() if start else None,
                    "kind": wk,
                    "label": name,
                }
            )
        meeting_weeks = [w for r in recs if r["type"] == "meeting" for w in (r.get("weeks") or [])]
        exam_dates = sorted({d for d in (tx.parse_date(r.get("date")) for r in recs if r["type"] == "exam") if d})
        if kind in ("FINAL", "BUT") and exam_dates and not weeks:
            mondays = sorted({_monday(d) for d in exam_dates})
            weeks = [
                {"index": i + 1, "start_date": m.isoformat(), "kind": "EXAM", "label": None}
                for i, m in enumerate(mondays)
            ]
        lecture = [w for w in weeks if w["kind"] == "LECTURE"]
        week_count = max([len(weeks), max(meeting_weeks, default=0), max((w["index"] for w in lecture), default=0)])
        if week_count == 0:
            week_count = 14 if kind in ("REGULAR", "SUMMER") else max(1, len(weeks))
        starts = [w["start_date"] for w in weeks if w["start_date"]]
        exam_monday = [_monday(exam_dates[0]).isoformat()] if exam_dates else []
        start_date = min(starts + exam_monday) if (starts or exam_monday) else None
        end_date = exam_dates[-1].isoformat() if exam_dates else None
        if not end_date and start_date:
            end_date = (date.fromisoformat(start_date) + timedelta(weeks=week_count) - timedelta(days=1)).isoformat()
        meetings = [r for r in recs if r["type"] in ("meeting", "exam")]
        days = sorted(
            {d for r in meetings for d in (r.get("days") or [])}
            | {r["day"] for r in recs if r["type"] == "booking" and r.get("day")}
        )
        confidence = 0.9 if (season and years) else 0.6 if (season or years) else 0.3
        out_groups.append(
            {
                "key": f"{season or 'UNKNOWN'}:{'-'.join(map(str, years)) or '?'}",
                "code": code,
                "name": " ".join(filter(None, [str(year) if year else "", (season or "Term").title()])),
                "kind": kind,
                "year": year,
                "files": sorted(g["files"]),
                "week_count": week_count,
                "start_date": start_date,
                "end_date": end_date,
                "weeks": sorted(weeks, key=lambda w: w["index"]),
                "days": days,
                "evidence": g["evidence"][:10],
                "confidence": confidence,
            }
        )
    out_groups.sort(key=lambda g: g["files"][0] if g["files"] else 99)
    all_meetings = [r for rs in records.values() for r in rs if r["type"] in ("meeting",)]
    return {
        "groups": out_groups,
        "unassigned_files": unassigned,
        "global_files": global_files,
        "period_grid": period_grid(axis_slots, all_meetings),
        "horizons": ["WEEK", "MONTH", "TERM"],
    }


__all__ = ["DEFAULT_GRID", "period_grid", "plan", "season_of"]
