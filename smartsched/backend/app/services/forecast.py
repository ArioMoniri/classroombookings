"""Demand forecasts, capacity shortfall and what-if (adaptive scheduling AS-07, AS-10, AS-18;
docs/research/2026-10-17-adaptive-scheduling.md §3.4).

Every answer carries ``value, lo80, hi80, method, basis, confidence (high | medium | low | none), needs``:

* ``requests``: the target term already has a planning list, so demand is *computed*, not forecast: the room needs
  of its fixed-time requests (one lecture listed once per programme counts once) per building x weekday x period x
  room feature (tag) x capacity band. Works from the first import (owner decision 10).
* ``seasonal_naive``: no requests yet, but a term of the same season was published: its weekly room-periods,
  scaled by the cohort-progression ratio (1 with one year of history, and the basis says so); 80 % range from the
  week-to-week quantiles of that term; fewer than 10 calibration weeks -> ``low`` ("düşük güven") with the
  campus-level relative range. A damped level (:func:`damped_level`) is used only with >= 3 same-season terms.
* ``none``: neither; ``needs`` names what is missing. Nothing is invented.

Shortfall (AS-10) is a Hall-type check per (weekday, period, room group): for every capacity threshold c, the
fixed-time requests that need >= c seats (and the tag) against the bookable rooms with >= c seats (and the tag); the
largest excess is the shortfall, with the requests that compete. What-if recomputes that with scaled enrolments, a
narrower scope, closed rooms or extra sections, and can queue a draft child run (never activated).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from app.services.utilisation import CAPACITY_BANDS, CAPACITY_TOP

_DAY_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
_DAY_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
TAG_TR = {"PC": "bilgisayar laboratuvarı", "LAB": "laboratuvar", "TIP": "tıp dersliği", "AMPHI": "amfi"}
TAG_EN = {"PC": "computer lab", "LAB": "laboratory", "TIP": "medicine room", "AMPHI": "amphitheatre"}
MIN_CALIBRATION = 10
MIN_REL_HALF_WIDTH = 0.02
Z80 = 1.2816
#: AS-21 calibrated ranges (split conformal). A cell's score is the Poisson-scaled error |actual - forecast| /
#: sqrt(forecast). SHAPE_Q80 is the 80 % conformal quantile of the shape-only scores of the Güz -> Bahar fold of
#: the real workbooks (60 cells, ``backtest.shape_scores``; tests/test_as_07 recomputes it). LEVEL_REL_SD_PRIOR is a
#: stated prior for the term-to-term level change (not fitted: two terms cannot calibrate it). Both apply until
#: the install has its own history (MIN_CONFORMAL_SCORES scores from two published terms of the season); until
#: then the forecast says "düşük güven".
SHAPE_Q80 = 1.45
LEVEL_REL_SD_PRIOR = 0.05
MIN_CONFORMAL_SCORES = 20
DEMAND_GROUPS = ("building", "weekday", "period", "tag", "capacity_band", "cell")


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def band_of(size: int) -> str:
    return next((lab for up, lab in CAPACITY_BANDS if size <= up), CAPACITY_TOP)


# ------------------------------------------------------------------------------------------------ pure core


@dataclass(frozen=True)
class Need:
    """One fixed-time request that needs a room (a joint lecture listed per programme is one need)."""

    key: str
    label: str
    day: int
    start: int
    end: int
    size: int
    tags: frozenset[str] = frozenset()
    building: str | None = None
    weeks: frozenset[int] | None = None  # None = every lecture week
    program: str | None = None
    faculty: str | None = None
    request_ids: tuple[int, ...] = ()

    @property
    def span(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class RoomCap:
    id: int
    code: str
    capacity: int
    tags: frozenset[str] = frozenset()
    building: str = ""


def dedupe(needs: Iterable[Need]) -> list[Need]:
    """One need per (course, section, day, periods): the rows of a joint lecture are one lecture; the largest size
    and the union of tags win."""
    out: dict[tuple[Any, ...], Need] = {}
    for x in needs:
        k = (x.key, x.day, x.start, x.end)
        if k in out:
            y = out[k]
            out[k] = replace(
                y,
                size=max(y.size, x.size),
                tags=y.tags | x.tags,
                building=y.building or x.building,
                request_ids=tuple(sorted(set(y.request_ids) | set(x.request_ids))),
            )
        else:
            out[k] = x
    return sorted(out.values(), key=lambda n_: (n_.day, n_.start, n_.key))


def needs_from_planning_rows(rows: Iterable[Any]) -> list[Need]:
    """Needs of a parsed planning list (``importers.planning_list``): rows that need a room and have one day and a
    time (two days such as "Perşembe/Cuma" are a choice, not two meetings: left out of fixed-time demand); the
    requested building (or the requested rooms' building) when the department named one."""
    out: list[Need] = []
    for r in rows:
        if not (r.needs_room and r.has_day_and_time and r.periods.start_period and r.periods.end_period):
            continue
        if len(r.day.days) != 1:
            continue
        b = r.venue.building or (r.venue.room_codes[0][:1] if r.venue.room_codes else None)
        weeks = None if r.weeks.all_weeks else frozenset(int(w) for w in r.weeks.weeks)
        for d in r.day.days:
            out.append(
                Need(
                    key=f"{r.course_code}|{r.label or ''}",
                    label=f"{r.course_code} §{r.label}" if r.label else str(r.course_code),
                    day=int(d),
                    start=int(r.periods.start_period),
                    end=int(r.periods.end_period),
                    size=int(r.enrolment or 0),
                    tags=frozenset(str(t).upper() for t in r.venue.tags or []),
                    building=b,
                    weeks=weeks,
                    program=r.program,
                    faculty=r.faculty,
                )
            )
    return dedupe(out)


def rooms_from_master_csv(path: Any) -> list[RoomCap]:
    """Bookable rooms of a room-master CSV (``tests/fixtures/room_master.csv`` shape)."""
    import csv

    out: list[RoomCap] = []
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    for i, row in enumerate(csv.DictReader(lines)):
        if str(row.get("bookable", "1")).strip() in ("0", "false", "False"):
            continue
        cap = int(row.get("capacity") or 0)
        if cap <= 0:
            continue
        code = (row.get("code") or "").replace(" ", "").upper()
        tags = frozenset(t.strip().upper() for t in (row.get("tags") or "").replace(";", ",").split(",") if t.strip())
        out.append(RoomCap(i + 1, code, cap, tags, (row.get("building") or code[:1]).upper()))
    return out


def scale(needs: Sequence[Need], pct: float, keep: Any = None) -> list[Need]:
    """Enrolment x (1 + pct/100), rounded up, for the needs ``keep`` accepts (all by default)."""
    out = []
    for x in needs:
        if keep is None or keep(x):
            out.append(replace(x, size=int(math.ceil(round(x.size * (1 + pct / 100.0), 6)))))
        else:
            out.append(x)
    return out


def fits(x: Need, room: RoomCap) -> bool:
    return room.capacity >= x.size and x.tags <= room.tags


def no_fit(needs: Sequence[Need], rooms: Sequence[RoomCap]) -> list[Need]:
    """Needs with no bookable room of at least their size and their tags (a split over rooms aside)."""
    return [x for x in needs if x.size > 0 and not any(fits(x, r) for r in rooms)]


def _tag_group(x: Need) -> str:
    return "PC" if "PC" in x.tags else ("TIP" if "TIP" in x.tags else "*")


def shortfall_cells(needs: Sequence[Need], rooms: Sequence[RoomCap], week: int | None = None) -> list[dict[str, Any]]:
    """Per (weekday, period, tag group): demand vs supply at the tightest capacity threshold (Hall's condition on
    nested room sets). ``shortfall`` > 0 means no assignment can seat every fixed-time request there."""
    by_cell: dict[tuple[int, int, str], list[Need]] = defaultdict(list)
    for x in needs:
        if x.size <= 0 or (week is not None and x.weeks is not None and week not in x.weeks):
            continue
        for p in range(x.start, x.end + 1):
            by_cell[(x.day, p, _tag_group(x))].append(x)
            if _tag_group(x) != "*":
                by_cell[(x.day, p, "*")].append(x)
    out: list[dict[str, Any]] = []
    for (d, p, g), xs in sorted(by_cell.items()):
        pool = [r for r in rooms if g == "*" or g in r.tags]
        best = (0, 0, 0, 0)  # (excess, threshold, demand, supply)
        for c in sorted({x.size for x in xs}):
            dem = sum(1 for x in xs if x.size >= c)
            sup = sum(1 for r in pool if r.capacity >= c)
            if dem - sup > best[0]:
                best = (dem - sup, c, dem, sup)
        n_any = len(xs)
        out.append(
            {
                "day": d,
                "period": p,
                "group": g,
                "demand": n_any,
                "supply": len(pool),
                "load_pct": round(100.0 * n_any / len(pool), 1) if pool else None,
                "shortfall": best[0],
                "threshold_seats": best[1] or None,
                "demand_at_threshold": best[2],
                "supply_at_threshold": best[3],
                "p_shortfall": 1.0 if best[0] > 0 else 0.0,
                "competing": sorted({x.label for x in xs if not best[1] or x.size >= best[1]})[:40],
            }
        )
    return out


def demand_cells(needs: Sequence[Need], lecture_weeks: Sequence[int]) -> dict[tuple[str, int, int, str, str], float]:
    """Weekly room-periods per (building, weekday, period, tag group, capacity band), averaged over the lecture
    weeks (a request for some weeks counts in those only)."""
    weeks = list(lecture_weeks) or list(range(1, 15))
    out: dict[tuple[str, int, int, str, str], float] = defaultdict(float)
    for x in needs:
        active = len([w for w in weeks if x.weeks is None or w in x.weeks]) / len(weeks)
        if active <= 0:
            continue
        for p in range(x.start, x.end + 1):
            out[(x.building or "*", x.day, p, _tag_group(x), band_of(x.size) if x.size else "?")] += active
    return out


def poisson_score(actual: float, forecast: float) -> float:
    """The conformal score of one cell: |actual - forecast| / sqrt(forecast) (scale-free across a 40 and a 650
    room-period building)."""
    return abs(float(actual) - float(forecast)) / math.sqrt(max(float(forecast), 1.0))


def conformal_quantile(scores: Sequence[float], coverage: float = 0.8) -> float | None:
    """Split-conformal quantile: the ceil((n + 1) x coverage)-th smallest score; None when there are too few
    scores for that rank (the range would be unbounded)."""
    s = sorted(float(x) for x in scores)
    k = math.ceil((len(s) + 1) * coverage)
    return s[k - 1] if s and k <= len(s) else None


def calibrated_half_width(value: float, q80: float, rel_level_sd: float = 0.0) -> float:
    """80 % half-width: the shape term q80 x sqrt(value) and the level term Z80 x rel_level_sd x value, added in
    quadrature."""
    v = max(float(value), 0.0)
    return math.hypot(q80 * math.sqrt(max(v, 1.0)), Z80 * rel_level_sd * v)


def shape_times_level(
    level: float,
    weekly_shares: Mapping[str, Sequence[float]],
    *,
    rel_level_sd: float = 0.0,
    shape_q80: float | None = None,
) -> dict[str, tuple[float, float, float]]:
    """(value, lo80, hi80) per group: ``level`` x the mean share. Without ``shape_q80`` the range is the old
    within-term one (10th-90th percentile of the weekly shares, widened by the level's spread, at least ±2 %; it
    covered 25 % in B3). With ``shape_q80`` (AS-21) the range is at least the calibrated half-width."""
    out: dict[str, tuple[float, float, float]] = {}
    for g, shares in weekly_shares.items():
        s = np.asarray(shares, float)
        mean = float(s.mean()) if s.size else 0.0
        lo_s, hi_s = (float(np.percentile(s, 10)), float(np.percentile(s, 90))) if s.size > 1 else (mean, mean)
        v = level * mean
        lo = level * lo_s * (1 - Z80 * rel_level_sd)
        hi = level * hi_s * (1 + Z80 * rel_level_sd)
        lo, hi = min(lo, v * (1 - MIN_REL_HALF_WIDTH)), max(hi, v * (1 + MIN_REL_HALF_WIDTH))
        if shape_q80 is not None:
            hw = calibrated_half_width(v, shape_q80, rel_level_sd)
            lo, hi = min(lo, v - hw), max(hi, v + hw)
        out[g] = (v, max(0.0, lo), hi)
    return out


@dataclass(frozen=True)
class SeasonalRanges:
    """``seasonal_ranges``: (value, lo80, hi80) per key, the confidence, the quantile used and its score count."""

    cells: dict[tuple[Any, ...], tuple[float, float, float]]
    confidence: str
    q80: float | None
    n_scores: int


def seasonal_ranges(
    weekly: Mapping[tuple[Any, ...], Sequence[float]],
    prev_weekly: Mapping[tuple[Any, ...], Sequence[float]] | None = None,
) -> SeasonalRanges:
    """Seasonal-naive cells from the source term's weekly counts (value = the weekly mean). The 80 % range:
    * the install's own history (AS-21): the earlier same-season term's weekly means predict each week of the
      source term; with >= MIN_CONFORMAL_SCORES scores their conformal quantile is the half-width
      (``medium``);
    * otherwise the backtest calibration SHAPE_Q80 with the LEVEL_REL_SD_PRIOR level prior (``low``,
      "düşük güven").
    Never narrower than the source term's own 10th-90th week percentiles or ±2 %."""
    q: float | None = None
    scores: list[float] = []
    if prev_weekly:
        for k, weeks in weekly.items():
            prev = prev_weekly.get(k)
            f = float(np.mean(prev)) if prev else 0.0
            scores.extend(poisson_score(a, f) for a in weeks)
        q = conformal_quantile(scores) if len(scores) >= MIN_CONFORMAL_SCORES else None
    own = q is not None
    cells: dict[tuple[Any, ...], tuple[float, float, float]] = {}
    for k, weeks in weekly.items():
        v = np.asarray(weeks, float)
        val = float(v.mean()) if v.size else 0.0
        lo, hi = (float(np.percentile(v, 10)), float(np.percentile(v, 90))) if v.size > 1 else (val, val)
        hw = (
            calibrated_half_width(val, q, 0.0)
            if q is not None
            else calibrated_half_width(val, SHAPE_Q80, LEVEL_REL_SD_PRIOR)
        )
        lo = min(lo, val * (1 - MIN_REL_HALF_WIDTH), val - hw)
        hi = max(hi, val * (1 + MIN_REL_HALF_WIDTH), val + hw)
        cells[k] = (val, max(0.0, lo), hi)
    return SeasonalRanges(cells, "medium" if own else "low", q if own else SHAPE_Q80, len(scores) if own else 0)


def damped_level(values: Sequence[float], alpha: float = 0.5, beta: float = 0.3, phi: float = 0.9) -> float:
    """One-step damped-trend (Holt) forecast; only for >= 3 same-season points (else the last value)."""
    if len(values) < 3:
        return float(values[-1]) if values else math.nan
    level, trend = float(values[0]), float(values[1] - values[0])
    for y in values[1:]:
        prev = level
        level = alpha * y + (1 - alpha) * (level + phi * trend)
        trend = beta * (level - prev) + (1 - beta) * phi * trend
    return level + phi * trend


# ------------------------------------------------------------------------------------------------ database


async def needs_from_db(session: Any, term_id: int) -> tuple[list[Need], int]:
    """(needs, requests without a known size) of a term's fixed-time meeting requests that need a room."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Faculty, MeetingRequest, Program, Room, Section

    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    programs = {p.id: p for p in (await session.execute(select(Program))).scalars()}
    faculties = {f.id: f.name for f in (await session.execute(select(Faculty))).scalars()}
    q = (
        select(MeetingRequest)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(
            Section.term_id == term_id,
            Section.archived.is_(False),
            MeetingRequest.archived.is_(False),
            MeetingRequest.needs_room.is_(True),
        )
        .options(selectinload(MeetingRequest.section).selectinload(Section.course))
    )
    out: list[Need] = []
    unknown = 0
    for mr in (await session.execute(q)).scalars():
        if mr.start_period is None or mr.end_period is None:
            continue
        days = [int(mr.day)] if mr.day else [int(d) for d in (mr.days or [])]
        if len(days) != 1:
            continue  # a choice of days (flexible): not fixed-time demand
        sec = mr.section
        size = int(sec.enrolment or mr.requested_capacity or 0)
        if size <= 0:
            unknown += 1
        rids = [int(x) for x in (mr.requested_room_ids or []) if int(x) in rooms]
        building = mr.requested_building or (rooms[rids[0]].code[:1] if rids else None)
        prog = programs.get(sec.program_id) if sec.program_id else None
        code = sec.course.display_code if sec.course is not None else f"#{mr.id}"
        for d in days:
            out.append(
                Need(
                    key=f"{sec.course_id}|{sec.label or ''}",
                    label=f"{code} §{sec.label}" if sec.label else code,
                    day=d,
                    start=int(mr.start_period),
                    end=int(mr.end_period),
                    size=size,
                    tags=frozenset(str(t).upper() for t in (mr.requested_tags or [])),
                    building=(building or "").upper()[:1] or None,
                    weeks=frozenset(int(w) for w in mr.weeks) if mr.weeks else None,
                    program=prog.name if prog else None,
                    faculty=faculties.get(prog.faculty_id) if prog and prog.faculty_id else None,
                    request_ids=(mr.id,),
                )
            )
    return dedupe(out), unknown


async def rooms_from_db(session: Any, closed: Iterable[int] = ()) -> list[RoomCap]:
    from sqlalchemy import select

    from app.models import Room

    shut = {int(x) for x in closed}
    return [
        RoomCap(r.id, r.code, int(r.capacity or 0), frozenset(str(t).upper() for t in r.tags or []), r.code[:1])
        for r in (await session.execute(select(Room).where(Room.is_bookable.is_(True)).order_by(Room.code))).scalars()
        if (r.capacity or 0) > 0 and r.id not in shut
    ]


async def lecture_weeks(session: Any, term: Any) -> list[int]:
    from app.services import seasons

    weeks_rows, _h, segs = await seasons.load_calendar(session, term)
    kinds = seasons.week_kinds(weeks_rows)
    if not kinds:
        return list(range(1, (term.week_count or 14) + 1))
    kept, _dropped = seasons.course_weeks(sorted(kinds), kinds, term)
    return kept


def _label(group_by: str, key: tuple[Any, ...]) -> dict[str, str]:
    if group_by == "building":
        return (
            _t("Bina belirtilmemiş", "No building given")
            if key[0] == "*"
            else _t(f"{key[0]} blok", f"Building {key[0]}")
        )
    if group_by == "weekday":
        return _t(_DAY_TR[key[0]], _DAY_EN[key[0]])
    if group_by == "period":
        return _t(f"{key[0]}. ders", f"period {key[0]}")
    if group_by == "tag":
        return (
            _t("Özel donanım yok", "No special room")
            if key[0] == "*"
            else _t(TAG_TR.get(key[0], key[0]), TAG_EN.get(key[0], key[0]))
        )
    if group_by == "capacity_band":
        return _t(f"{key[0]} kişi", f"{key[0]} seats")
    b, d, p, tg, cb = key
    room_tr = TAG_TR.get(tg, "derslik") if tg != "*" else "derslik"
    room_en = TAG_EN.get(tg, "classroom") if tg != "*" else "classroom"
    where_tr = "?" if b == "*" else f"{b} blok"
    where_en = "?" if b == "*" else f"Building {b}"
    return _t(
        f"{where_tr} · {_DAY_TR[d]} {p}. ders · {room_tr} · {cb}",
        f"{where_en} · {_DAY_EN[d]} period {p} · {room_en} · {cb}",
    )


def _project(key: tuple[str, int, int, str, str], group_by: str) -> tuple[Any, ...]:
    b, d, p, tg, cb = key
    return {
        "building": (b,),
        "weekday": (d,),
        "period": (p,),
        "tag": (tg,),
        "capacity_band": (cb,),
        "cell": key,
    }[group_by]


NEEDS_NONE = _t(
    "Bu dönemin planlama listesi yok ve aynı dönemden yayımlanmış bir dönem yok: tahmin için önce listeyi içe "
    "aktarın ya da bir dönemi yayımlayın",
    "This term has no planning list and no term of the same season was published: import the list or publish a "
    "term first",
)


async def demand_forecast(session: Any, term_id: int | None, group_by: str = "building") -> dict[str, Any]:
    """``GET /analytics/forecast/demand``: weekly room-periods per group with method, basis, confidence, needs."""
    from sqlalchemy import select

    from app.models import Term

    if group_by not in DEMAND_GROUPS:
        raise ValueError(group_by)
    term = await session.get(Term, term_id) if term_id is not None else None
    if term is None and term_id is None:
        term = (await session.execute(select(Term).where(Term.is_active.is_(True)).limit(1))).scalar_one_or_none()
    if term is None:
        return _empty(None, group_by, "none", _t("Henüz dönem yok", "No term yet"))
    needs, unknown = await needs_from_db(session, term.id)
    weeks = await lecture_weeks(session, term)
    if needs:
        cells = demand_cells(needs, weeks)
        agg: dict[tuple[Any, ...], float] = defaultdict(float)
        for k, v in cells.items():
            agg[_project(k, group_by)] += v
        basis = _t(
            f"Dönemin kendi talepleri: {len(needs)} sabit saatli ders ({len(weeks)} ders haftası)",
            f"The term's own requests: {len(needs)} fixed-time classes ({len(weeks)} lecture weeks)",
        )
        rows = [
            {
                "key": list(k),
                "label": _label(group_by, k),
                "value": round(v, 1),
                "lo80": round(v, 1),
                "hi80": round(v, 1),
                "method": "requests",
                "basis": basis,
                "confidence": "high",
                "needs": None,
            }
            for k, v in sorted(agg.items(), key=lambda kv: tuple(str(x) for x in kv[0]))
        ]
        return {
            "term_id": term.id,
            "term_code": term.code,
            "group_by": group_by,
            "unit": _t("haftalık oda-periyodu", "room-periods per week"),
            "method": "requests",
            "basis": basis,
            "confidence": "high",
            "needs": _t(
                f"{unknown} talebin öğrenci sayısı yok; kapasite bandı '?' olarak sayıldı",
                f"{unknown} request(s) have no enrolment; counted under capacity band '?'",
            )
            if unknown
            else None,
            "cells": rows,
            "total": round(sum(agg.values()), 1),
        }
    return await _seasonal_naive(session, term, group_by)


def _weekly_counts(tc: Any, group_by: str) -> dict[tuple[Any, ...], list[float]]:
    """Weekly room-periods per building / weekday / period of a term cube (``peaks.term_cube``)."""
    busy = tc.cube.busy  # (W, 7, 18, R)
    weekly: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for wi in range(len(tc.weeks)):
        counts: Counter[tuple[Any, ...]] = Counter()
        for ri, room in enumerate(tc.cube.rooms):
            col = busy[wi, :, :, ri]
            for d, p in zip(*np.nonzero(col), strict=False):
                key = {"building": (room.building,), "weekday": (int(d) + 1,), "period": (int(p) + 1,)}[group_by]
                counts[key] += 1
        for k in set(counts) | set(weekly):
            weekly[k].append(float(counts.get(k, 0)))
    return weekly


async def _seasonal_naive(session: Any, term: Any, group_by: str) -> dict[str, Any]:
    """The same season's last published term, ratio 1 (one year of history), per building / weekday / period."""
    from sqlalchemy import select

    from app.models import ScheduleRun, Term
    from app.services import peaks, seasons

    season = seasons.season_of(term)
    cands = [
        t
        for t in (await session.execute(select(Term).where(Term.id != term.id))).scalars()
        if seasons.season_of(t) == season
    ]
    published = []
    for t in cands:
        if (
            await session.execute(
                select(ScheduleRun.id).where(
                    ScheduleRun.term_id == t.id, ScheduleRun.is_active.is_(True), ScheduleRun.kind == "COURSE"
                )
            )
        ).first():
            published.append(t)
    if not published or group_by in ("tag", "capacity_band", "cell"):
        needs = (
            NEEDS_NONE
            if not published
            else _t(
                "Önceki dönemden yalnız bina, gün ve saat tahmini yapılır; donanım ve kapasite için talepler gerekli",
                "From an earlier term only building, weekday and period can be forecast; features and capacity "
                "need the requests",
            )
        )
        return _empty(term.id, group_by, "none", needs, term_code=term.code)
    ordered = sorted(published, key=lambda t: (t.start_date is not None, t.start_date, t.id))
    src = ordered[-1]
    tc = await peaks.term_cube(session, src.id, "LECTURE")
    if tc is None or not tc.weeks:
        return _empty(term.id, group_by, "none", NEEDS_NONE, term_code=term.code)
    weekly = _weekly_counts(tc, group_by)
    prev_weekly = None
    if len(ordered) >= 2:  # AS-21: the install's own cross-term history calibrates the range
        prev_tc = await peaks.term_cube(session, ordered[-2].id, "LECTURE")
        prev_weekly = _weekly_counts(prev_tc, group_by) if prev_tc is not None and prev_tc.weeks else None
    n_cal = len(tc.weeks)
    ranges = seasonal_ranges(weekly, prev_weekly)
    conf = ranges.confidence
    basis = _t(
        f"{src.code} yayımlanmış programı (aynı dönem, {n_cal} hafta) × kohort oranı 1 (bir yıllık geçmiş)",
        f"the published timetable of {src.code} (same season, {n_cal} weeks) × cohort ratio 1 (one year of history)",
    )
    if conf == "medium":
        basis = _t(
            f"{basis['tr']}; aralık {ordered[-2].code} → {src.code} hatalarından kalibre ({ranges.n_scores} hücre)",
            f"{basis['en']}; range calibrated on the {ordered[-2].code} → {src.code} errors ({ranges.n_scores} cells)",
        )
    low_needs = _t(
        "Düşük güven: aralık bu kurumun geçmişiyle henüz kalibre edilmedi (aynı dönemden iki yayımlanmış program "
        "gerekir); geniş aralık örnek verilerdeki geriye dönük testten",
        "Low confidence: the range is not yet calibrated on this institution's history (two published terms of "
        "the season are needed); the wide range comes from the backtest on the sample data",
    )
    rows: list[dict[str, Any]] = []
    for k in sorted(ranges.cells, key=lambda x: tuple(str(v) for v in x)):
        val, lo, hi = ranges.cells[k]
        rows.append(
            {
                "key": list(k),
                "label": _label(group_by, k),
                "value": round(val, 1),
                "lo80": round(max(0.0, lo), 1),
                "hi80": round(hi, 1),
                "method": "seasonal_naive",
                "basis": basis,
                "confidence": conf,
                "needs": low_needs if conf == "low" else None,
            }
        )
    return {
        "term_id": term.id,
        "term_code": term.code,
        "group_by": group_by,
        "unit": _t("haftalık oda-periyodu", "room-periods per week"),
        "method": "seasonal_naive",
        "basis": basis,
        "confidence": conf,
        "needs": _t(
            (low_needs["tr"] + ". " if conf == "low" else "")
            + "Planlama listesi içe aktarıldığında tahmin dönemin kendi taleplerinden hesaplanır",
            (low_needs["en"] + ". " if conf == "low" else "")
            + "Once the planning list is imported, demand is computed from the term's own requests",
        ),
        "source_term_id": src.id,
        "cells": rows,
        "total": round(sum(float(r["value"]) for r in rows), 1),
    }


def _empty(
    term_id: int | None, group_by: str, confidence: str, needs: Mapping[str, str], term_code: str | None = None
) -> dict[str, Any]:
    return {
        "term_id": term_id,
        "term_code": term_code,
        "group_by": group_by,
        "unit": _t("haftalık oda-periyodu", "room-periods per week"),
        "method": "none",
        "basis": None,
        "confidence": confidence,
        "needs": dict(needs),
        "cells": [],
        "total": 0,
    }


# ------------------------------------------------------------------------------------------------ AS-10


@dataclass
class WhatIf:
    enrolment_pct: float = 0.0
    scope: str = "all"  # all | faculty | program
    scope_value: str | None = None
    rooms_closed: list[int] = field(default_factory=list)
    extra_sections: int = 0

    def keep(self) -> Any:
        if self.scope == "all" or not self.scope_value:
            return None
        from app.importers import normalize as n

        want = n.tr_casefold(self.scope_value)
        attr = "faculty" if self.scope == "faculty" else "program"
        return lambda x: n.tr_casefold(getattr(x, attr) or "") == want

    def label(self) -> dict[str, str]:
        parts_tr, parts_en = [], []
        if self.enrolment_pct:
            parts_tr.append(f"{self.enrolment_pct:+g} % kontenjan")
            parts_en.append(f"{self.enrolment_pct:+g} % enrolment")
        if self.scope != "all" and self.scope_value:
            parts_tr.append(f"{self.scope_value}")
            parts_en.append(f"{self.scope_value}")
        if self.rooms_closed:
            parts_tr.append(f"{len(self.rooms_closed)} oda kapalı")
            parts_en.append(f"{len(self.rooms_closed)} room(s) closed")
        if self.extra_sections:
            parts_tr.append(f"+{self.extra_sections} şube")
            parts_en.append(f"+{self.extra_sections} section(s)")
        return _t(
            "Senaryo: " + (", ".join(parts_tr) or "bugünkü durum"), "Scenario: " + (", ".join(parts_en) or "as today")
        )


def apply_what_if(needs: Sequence[Need], w: WhatIf) -> list[Need]:
    """Scaled sizes inside the scope, plus ``extra_sections`` copies of the largest in-scope classes (each a new
    section at the same time: the worst case for rooms)."""
    keep = w.keep()
    out = scale(needs, w.enrolment_pct, keep)
    if w.extra_sections > 0:
        pool = sorted((x for x in out if keep is None or keep(x)), key=lambda x: (-x.size, x.day, x.start, x.key))
        for i, x in enumerate(pool[: w.extra_sections]):
            out.append(replace(x, key=f"{x.key}|extra{i + 1}", label=f"{x.label} (+{i + 1})", request_ids=()))
    return out


def fit_report(needs: Sequence[Need], rooms: Sequence[RoomCap]) -> dict[str, Any]:
    bad = no_fit(needs, rooms)
    cells = shortfall_cells(needs, rooms)
    short = [c for c in cells if c["shortfall"] > 0]
    return {
        "classes": len(needs),
        "no_fit": len(bad),
        "no_fit_classes": [
            {"label": x.label, "size": x.size, "tags": sorted(x.tags), "day": x.day, "start": x.start, "end": x.end}
            for x in sorted(bad, key=lambda x: (-x.size, x.label))[:100]
        ],
        "shortfall_cells": len(short),
        "shortfall_total": sum(c["shortfall"] for c in short),
        "cells": sorted(short, key=lambda c: (-c["shortfall"], c["day"], c["period"], c["group"]))[:200],
    }


async def shortfall(session: Any, term_id: int, *, peaks_only: bool = False) -> dict[str, Any]:
    """``GET /analytics/forecast/shortfall``: demand vs suitable supply per (weekday, period, room group)."""
    from app.models import Term

    term = await session.get(Term, term_id)
    if term is None:
        raise LookupError(term_id)
    needs, unknown = await needs_from_db(session, term_id)
    if not needs:
        return {
            "term_id": term_id,
            "method": "none",
            "confidence": "none",
            "needs": _t(
                "Bu dönemin sabit saatli talebi yok: planlama listesini içe aktarın",
                "This term has no fixed-time requests: import the planning list",
            ),
            "cells": [],
        }
    rooms = await rooms_from_db(session)
    rep = fit_report(needs, rooms)
    all_cells = shortfall_cells(needs, rooms)
    if peaks_only:
        from app.services import peaks

        pk = await peaks.peaks(session, term_id=term_id, group_by="campus")
        hot = {(c["day"], c["period"]) for c in pk["peaks"]}
        all_cells = [c for c in all_cells if (c["day"], c["period"]) in hot]
    return {
        "term_id": term_id,
        "term_code": term.code,
        "method": "requests",
        "confidence": "high",
        "basis": _t(
            f"{len(needs)} sabit saatli talep ve {len(rooms)} kapasitesi bilinen oda",
            f"{len(needs)} fixed-time requests and {len(rooms)} rooms with a known capacity",
        ),
        "needs": _t(f"{unknown} talebin öğrenci sayısı yok", f"{unknown} request(s) have no enrolment")
        if unknown
        else None,
        "no_fit": rep["no_fit"],
        "no_fit_classes": rep["no_fit_classes"],
        "cells": [c for c in all_cells if c["shortfall"] > 0 or c["group"] != "*" or (c["load_pct"] or 0) >= 85],
        "definitions": {
            "shortfall": _t(
                "Açık: en sıkışık kapasite eşiğinde, o eşiği isteyen ders sayısı − o eşikte uygun oda sayısı",
                "Shortfall: at the tightest capacity threshold, classes needing it − rooms offering it",
            ),
            "p_shortfall": _t(
                "Talepler kesin olduğu için olasılık 0 ya da 1'dir (tahmin değil, hesap)",
                "With the requests known the probability is 0 or 1 (computed, not forecast)",
            ),
        },
    }


async def what_if(session: Any, term_id: int, body: Mapping[str, Any], actor: Any) -> dict[str, Any]:
    """``POST /analytics/forecast/what-if``: today's room fit vs the scenario's; ``solve`` queues a draft child run."""
    from app.models import Term

    term = await session.get(Term, term_id)
    if term is None:
        raise LookupError(term_id)
    w = WhatIf(
        enrolment_pct=float(body.get("enrolment_pct") or 0.0),
        scope=str(body.get("scope") or "all"),
        scope_value=body.get("scope_value"),
        rooms_closed=[int(x) for x in body.get("rooms_closed") or []],
        extra_sections=int(body.get("extra_sections") or 0),
    )
    needs, _unknown = await needs_from_db(session, term_id)
    base_rooms = await rooms_from_db(session)
    rooms = await rooms_from_db(session, w.rooms_closed)
    today = fit_report(needs, base_rooms)
    scen = fit_report(apply_what_if(needs, w), rooms)
    out: dict[str, Any] = {
        "term_id": term_id,
        "scenario": {
            "enrolment_pct": w.enrolment_pct,
            "scope": w.scope,
            "scope_value": w.scope_value,
            "rooms_closed": w.rooms_closed,
            "extra_sections": w.extra_sections,
            "label": w.label(),
        },
        "method": "requests" if needs else "none",
        "confidence": "high" if needs else "none",
        "needs": None
        if needs
        else _t("Bu dönemin sabit saatli talebi yok: planlama listesini içe aktarın", "No fixed-time requests"),
        "today": today,
        "what_if": scen,
        "delta": {
            "no_fit": scen["no_fit"] - today["no_fit"],
            "shortfall_total": scen["shortfall_total"] - today["shortfall_total"],
        },
        "run_id": None,
    }
    if body.get("solve") and needs:
        out["run_id"] = await queue_scenario_run(session, term, w, actor)
    return out


async def queue_scenario_run(session: Any, term: Any, w: WhatIf, actor: Any) -> int:
    """A draft COURSE run with ``params.scenario`` (the bridge scales the sizes): never active, labelled
    "Senaryo: ...", comparable in ``/runs/compare``."""
    from app.core.config import get_settings
    from app.models import ScheduleRun

    s = get_settings()
    run = ScheduleRun(
        term_id=term.id,
        kind="COURSE",
        horizon="TERM",
        horizon_params={},
        params={
            "time_limit_s": float(min(60.0, s.solver_max_time_limit)),
            "workers": 1,
            "best_effort": True,
            "scenario": {
                "enrolment_pct": w.enrolment_pct,
                "scope": w.scope,
                "scope_value": w.scope_value,
                "rooms_closed": list(w.rooms_closed),
                "extra_sections": w.extra_sections,
            },
        },
        status="QUEUED",
        label=w.label()["tr"][:255],
        is_active=False,
        stats={"progress": 0, "phase": "queued", "scenario": True},
        created_by=getattr(actor, "id", None),
    )
    session.add(run)
    await session.flush()
    from app.services.events import publish_event

    await publish_event(
        session,
        "forecast.what_if_run",
        "run",
        run.id,
        after={"scenario": run.params["scenario"]},
        actor=actor,
        term_id=term.id,
    )
    await session.commit()
    from app.api.v1.runs import _enqueue

    _enqueue(run.id)
    return int(run.id)


__all__ = [
    "Need",
    "RoomCap",
    "WhatIf",
    "apply_what_if",
    "damped_level",
    "demand_cells",
    "demand_forecast",
    "dedupe",
    "fit_report",
    "needs_from_db",
    "needs_from_planning_rows",
    "no_fit",
    "rooms_from_master_csv",
    "shape_times_level",
    "shortfall",
    "shortfall_cells",
    "what_if",
]


# ------------------------------------------------------------------------------------------------ AS-09 warnings


def pressure_cells(
    needs: Sequence[Need], rooms: Sequence[RoomCap], threshold_pct: float = 85.0
) -> list[dict[str, Any]]:
    """Cells where the fixed-time requests alone need more than ``threshold_pct`` of the suitable rooms (room
    group ``PC`` / ``TIP`` / every room), consecutive periods with the same numbers merged."""
    cells = [
        c for c in shortfall_cells(needs, rooms) if c["supply"] and 100.0 * c["demand"] / c["supply"] > threshold_pct
    ]
    merged: list[dict[str, Any]] = []
    for c in sorted(cells, key=lambda c: (c["group"], c["day"], c["period"])):
        last = merged[-1] if merged else None
        if (
            last is not None
            and (last["group"], last["day"], last["demand"], last["supply"])
            == (c["group"], c["day"], c["demand"], c["supply"])
            and last["end_period"] + 1 == c["period"]
        ):
            last["end_period"] = c["period"]
            last["competing"] = sorted(set(last["competing"]) | set(c["competing"]))
            continue
        merged.append({**c, "start_period": c["period"], "end_period": c["period"]})
    return merged


def pressure_text(c: Mapping[str, Any]) -> dict[str, str]:
    d, s, e, g = c["day"], c["start_period"], c["end_period"], c["group"]
    when_tr = f"{s}. ders" if s == e else f"{s}.–{e}. ders"
    when_en = f"period {s}" if s == e else f"periods {s}–{e}"
    what_tr = f"{TAG_TR.get(g, g)} isteyen" if g != "*" else "derslik isteyen"
    what_en = f"needing a {TAG_EN.get(g, g)}" if g != "*" else "needing a room"
    room_tr = "uygun" if g != "*" else "toplam"
    return _t(
        f"{_DAY_TR[d]} {when_tr}: {what_tr} {c['demand']} ders, {room_tr} {c['supply']} oda",
        f"{_DAY_EN[d]} {when_en}: {c['demand']} classes {what_en}, {c['supply']} suitable room(s)",
    )


async def peak_pressure(session: Any, term_id: int, threshold_pct: float | None = None) -> list[dict[str, Any]]:
    """``peak_pressure`` data issues of a term (no run needed)."""
    from app.models import Term
    from app.services import seasons

    term = await session.get(Term, term_id)
    if term is None:
        return []
    if threshold_pct is None:
        prof = await seasons.resolve_profile(session, seasons.season_of(term), "LECTURE")
        threshold_pct = float(prof.peak_threshold_pct if prof else seasons.DEFAULT_PEAK_THRESHOLD)
    needs, _u = await needs_from_db(session, term_id)
    if not needs:
        return []
    rooms = await rooms_from_db(session)
    by_label: dict[str, set[int]] = defaultdict(set)
    for x in needs:
        by_label[x.label] |= set(x.request_ids)
    out = []
    for c in pressure_cells(needs, rooms, threshold_pct):
        text = pressure_text(c)
        out.append(
            {
                "diagnosis_index": -1,
                "code": "peak_pressure",
                "severity": "warning" if c["demand"] > c["supply"] else "info",
                "message": text["en"],
                "message_tr": text["tr"],
                "detail": "",
                "suggestions": ["move a class with a flexible time out of this cell, or free a suitable room"],
                "event_ids": [],
                "request_ids": sorted({r for lab in c["competing"] for r in by_label.get(lab, set())}),
                "unplaced": False,
                "params": {
                    k: c[k] for k in ("day", "start_period", "end_period", "group", "demand", "supply", "shortfall")
                }
                | {"threshold_pct": threshold_pct, "competing": c["competing"]},
                "classes": [],
            }
        )
    return out
