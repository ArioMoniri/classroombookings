"""Peak-hour model (adaptive scheduling AS-06; docs/research/2026-10-17-adaptive-scheduling.md §3.2).

Cells are (weekday, period, group): group = building, room type, capacity band or the whole campus. The measure of
a cell is its **frequency**: the share of the group's usable room-periods that are busy (a placement of a published
run, a booked booking, or a block such as the prep school), per week; holidays and HOLIDAY weeks are left out of
both sides (``seasons.closed_days``). Where sizes are known (published runs with enrolments) the cell also carries
the **seat fill** (seats used / seats of the busy rooms).

Estimate per cell over the weeks of one period kind (lecture weeks by default):

* ``p̂ = (n·x̄ + k·p_parent) / (n + k)``: the cell's weekly mean shrunk toward its parent (group -> campus) with
  ``k = 4`` weeks, so a group seen for one week does not swing to 0 % or 100 %;
* the 80 % range is the 10th-90th percentile of the weekly values (at least ±2 points wide);
* a cell is a **peak** when ``p̂ >= threshold`` (the season profile's ``peak_threshold_pct``, default 85).

Confidence: ``high`` with >= 8 weeks, ``medium`` 3-7, ``low`` 1-2 ("düşük güven"), ``none`` without a published
term ("Yayımlanmış bir dönem gerekli"). The model is closed-form numpy, deterministic and cheap.

The pure core (:class:`Cube`, :func:`estimate`, :func:`period_profile`) is shared by the API (from the database) and
the backtests (``app.services.backtest``, from the parsed fixture workbooks).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

PERIODS = 18
DAYS = 7
WEEKDAYS = (1, 2, 3, 4, 5)
SHRINK_K = 4.0
MIN_HALF_WIDTH = 2.0
GROUP_BY = ("campus", "building", "room_type", "capacity_band")
_DAY_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
_DAY_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


@dataclass(frozen=True)
class RoomInfo:
    id: int
    code: str
    building: str
    room_type: str
    capacity_band: str
    capacity: int


@dataclass
class Cube:
    """Busy room-periods of some weeks: ``busy[w, d-1, p-1, r]`` (bool), ``closed[w, d-1]`` (holiday)."""

    weeks: list[int]
    rooms: list[RoomInfo]
    busy: np.ndarray
    closed: np.ndarray
    #: seats used per busy room-period where known (0 = unknown)
    seats: np.ndarray | None = None

    @classmethod
    def empty(cls, weeks: Sequence[int], rooms: Sequence[RoomInfo]) -> Cube:
        w, r = len(weeks), len(rooms)
        return cls(
            list(weeks),
            list(rooms),
            np.zeros((w, DAYS, PERIODS, r), dtype=bool),
            np.zeros((w, DAYS), dtype=bool),
            np.zeros((w, DAYS, PERIODS, r), dtype=np.int32),
        )

    def mark(self, week: int, day: int, start: int, end: int, room_id: int, seats: int = 0) -> None:
        wi = self._wi.get(week)
        ri = self._ri.get(room_id)
        if wi is None or ri is None or not 1 <= day <= DAYS:
            return
        s, e = max(1, start), min(PERIODS, end)
        if e < s:
            return
        self.busy[wi, day - 1, s - 1 : e, ri] = True
        if seats and self.seats is not None:
            self.seats[wi, day - 1, s - 1 : e, ri] = np.maximum(self.seats[wi, day - 1, s - 1 : e, ri], seats)

    def close(self, week: int, day: int) -> None:
        wi = self._wi.get(week)
        if wi is not None and 1 <= day <= DAYS:
            self.closed[wi, day - 1] = True

    @property
    def _wi(self) -> dict[int, int]:
        return {w: i for i, w in enumerate(self.weeks)}

    @property
    def _ri(self) -> dict[int, int]:
        return {r.id: i for i, r in enumerate(self.rooms)}


def group_of(room: RoomInfo, group_by: str) -> str:
    if group_by == "building":
        return room.building
    if group_by == "room_type":
        return room.room_type
    if group_by == "capacity_band":
        return room.capacity_band
    return "*"


def weekly_frequency(cube: Cube, room_mask: np.ndarray) -> np.ndarray:
    """(W, 7, 18) busy share of the masked rooms per week, NaN where the day is closed or no room is in the group."""
    n = int(room_mask.sum())
    if n == 0 or not cube.weeks:
        return np.full((len(cube.weeks), DAYS, PERIODS), np.nan)
    share = cube.busy[..., room_mask].sum(axis=-1) / n
    share = share.astype(float)
    share[cube.closed] = np.nan
    return share


def weekly_seat_fill(cube: Cube, room_mask: np.ndarray) -> np.ndarray | None:
    if cube.seats is None or not cube.seats[..., room_mask].any():
        return None
    caps = np.array([r.capacity for r in cube.rooms], dtype=float)[room_mask]
    seats = cube.seats[..., room_mask].astype(float)
    known = (seats > 0) & (caps > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        fill = np.where(known, np.minimum(seats / np.where(caps > 0, caps, 1), 1.5), np.nan)
        out = np.nanmean(np.where(known, fill, np.nan), axis=-1)
    return out


@dataclass
class CellEstimate:
    day: int
    period: int
    group: str
    value: float  # shrunk p̂, percent
    lo80: float
    hi80: float
    mean: float  # the cell's own weekly mean, percent
    n_weeks: int
    rooms: int
    seat_fill: float | None = None
    peak: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "period": self.period,
            "group": self.group,
            "value": round(self.value, 1),
            "lo80": round(self.lo80, 1),
            "hi80": round(self.hi80, 1),
            "mean": round(self.mean, 1),
            "n_weeks": self.n_weeks,
            "rooms": self.rooms,
            "seat_fill": None if self.seat_fill is None else round(self.seat_fill, 1),
            "peak": self.peak,
            "label": _t(f"{_DAY_TR[self.day]} {self.period}. ders", f"{_DAY_EN[self.day]} period {self.period}"),
        }


def _range(values: np.ndarray, centre: float) -> tuple[float, float]:
    v = values[~np.isnan(values)]
    if v.size == 0:
        return centre - MIN_HALF_WIDTH, centre + MIN_HALF_WIDTH
    lo, hi = (float(np.percentile(v, 10)), float(np.percentile(v, 90))) if v.size > 1 else (float(v[0]), float(v[0]))
    lo, hi = min(lo, centre - MIN_HALF_WIDTH), max(hi, centre + MIN_HALF_WIDTH)
    return max(0.0, lo), min(100.0, hi)


def estimate(
    cube: Cube,
    group_by: str = "building",
    *,
    threshold: float = 85.0,
    days: Iterable[int] = WEEKDAYS,
    k: float = SHRINK_K,
) -> list[CellEstimate]:
    """Shrunk cell estimates (percent) for every (day, period, group); see the module docstring."""
    days = list(days)
    campus_mask = np.ones(len(cube.rooms), dtype=bool)
    campus = weekly_frequency(cube, campus_mask) * 100.0
    with np.errstate(invalid="ignore"):
        campus_mean = np.nanmean(campus, axis=0) if cube.weeks else np.full((DAYS, PERIODS), np.nan)
    groups: dict[str, np.ndarray] = {}
    for i, r in enumerate(cube.rooms):
        g = group_of(r, group_by)
        groups.setdefault(g, np.zeros(len(cube.rooms), dtype=bool))[i] = True
    out: list[CellEstimate] = []
    for g in sorted(groups):
        mask = groups[g]
        freq = weekly_frequency(cube, mask) * 100.0
        fill = weekly_seat_fill(cube, mask)
        for d in days:
            for p in range(1, PERIODS + 1):
                vals = freq[:, d - 1, p - 1]
                ok = vals[~np.isnan(vals)]
                n = int(ok.size)
                parent = float(campus_mean[d - 1, p - 1]) if not np.isnan(campus_mean[d - 1, p - 1]) else 0.0
                mean = float(ok.mean()) if n else 0.0
                kk = 0.0 if group_by == "campus" else k
                value = (n * mean + kk * parent) / (n + kk) if (n + kk) > 0 else 0.0
                lo, hi = _range(vals, value)
                sf = None
                if fill is not None:
                    fv = fill[:, d - 1, p - 1]
                    fv = fv[~np.isnan(fv)]
                    sf = float(fv.mean() * 100.0) if fv.size else None
                out.append(CellEstimate(d, p, g, value, lo, hi, mean, n, int(mask.sum()), sf, value >= threshold))
    return out


def period_profile(cube: Cube, days: Iterable[int] = WEEKDAYS) -> np.ndarray:
    """Busy share (percent) of the whole campus per period (18), over the given weekdays and every open week."""
    days = [d - 1 for d in days]
    freq = weekly_frequency(cube, np.ones(len(cube.rooms), dtype=bool))[:, days, :] * 100.0
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(np.nanmean(freq.reshape(-1, PERIODS), axis=0))


def day_profile(cube: Cube) -> np.ndarray:
    """Busy room-periods per weekday (7), summed over the weeks and periods."""
    busy = cube.busy.copy()
    busy[cube.closed] = False
    return busy.sum(axis=(0, 2, 3)).astype(float)


def confidence_of(n_weeks: int) -> str:
    if n_weeks <= 0:
        return "none"
    if n_weeks < 3:
        return "low"
    return "medium" if n_weeks < 8 else "high"


CONFIDENCE_LABEL = {
    "high": _t("yüksek güven", "high confidence"),
    "medium": _t("orta güven", "medium confidence"),
    "low": _t("düşük güven", "low confidence"),
    "none": _t("veri yok", "no data"),
}


# ------------------------------------------------------------------------------------------------ database


@dataclass
class TermCube:
    cube: Cube
    term_id: int
    period_kind: str
    weeks: list[int]
    sources: list[dict[str, Any]] = field(default_factory=list)
    counted: dict[str, int] = field(default_factory=dict)


def room_infos(rooms: Iterable[Any]) -> list[RoomInfo]:
    from app.services.utilisation import capacity_band_of, room_type_of

    return [
        RoomInfo(int(r.id), r.code, (r.code or "?")[:1], room_type_of(r), capacity_band_of(r), int(r.capacity or 0))
        for r in sorted(rooms, key=lambda x: x.code)
        if r.is_bookable
    ]


async def term_cube(session: Any, term_id: int, period_kind: str = "LECTURE") -> TermCube | None:
    """The live board of a term (published runs + blocks + booked bookings) over its weeks of ``period_kind``;
    ``None`` when the term has no published run (nothing to learn a peak from)."""
    from sqlalchemy import select

    from app.models import Assignment, ExamRequest, MeetingRequest, Section, Term
    from app.services import seasons
    from app.services.utilisation import build_scope, published_runs

    term = await session.get(Term, term_id)
    if term is None:
        return None
    runs = await published_runs(session, term_id)
    if not runs:
        return None
    weeks_rows, holidays, segs = await seasons.load_calendar(session, term)
    kinds = seasons.week_kinds(weeks_rows)
    seg_kinds = seasons.segment_kind_by_week(segs)
    sc = await build_scope(session, term_id=term_id, scope="term")
    weeks = [w for w in sc.weeks if (seg_kinds.get(w) or kinds.get(w, "LECTURE")) == period_kind]
    if period_kind == "EXAM":
        weeks = weeks or sc.weeks
    rinfo = room_infos(sc.rooms.values())
    cube = Cube.empty(weeks, rinfo)
    for (rid, w, d, p), src in sc.occ.cells.items():
        if src & {"run", "booking", "block"}:
            cube.mark(w, d, p, p, rid)
    for w, d in sc.occ.closed:
        cube.close(w, d)
    # seat fill from the published runs' request sizes
    sizes: dict[tuple[str, int | None], int] = {}
    for r in sc.runs:
        q = select(Assignment).where(Assignment.run_id == r.id, Assignment.archived.is_(False))
        rows = list((await session.execute(q)).scalars())
        mids = {a.meeting_request_id for a in rows if a.meeting_request_id}
        eids = {a.exam_request_id for a in rows if a.exam_request_id}
        if mids:
            for mid, enr in (
                await session.execute(
                    select(MeetingRequest.id, Section.enrolment)
                    .join(Section, Section.id == MeetingRequest.section_id)
                    .where(MeetingRequest.id.in_(mids))
                )
            ).all():
                sizes[("m", mid)] = int(enr or 0)
        if eids:
            for eid, enr in (
                await session.execute(select(ExamRequest.id, ExamRequest.enrolment).where(ExamRequest.id.in_(eids)))
            ).all():
                sizes[("e", eid)] = int(enr or 0)
        from app.services.grid import assignment_weeks

        for a in rows:
            size = (
                sizes.get(("m", a.meeting_request_id)) if a.meeting_request_id else sizes.get(("e", a.exam_request_id))
            )
            if not size or not a.room_ids:
                continue
            per_room = max(1, int(size) // max(1, len(a.room_ids)))
            for w in assignment_weeks(a) or set(weeks):
                for rid in a.room_ids:
                    if cube.seats is not None and cube._ri.get(int(rid)) is not None:
                        cube.mark(int(w), a.day, a.start_period, a.end_period, int(rid), per_room)
    return TermCube(
        cube,
        term_id,
        period_kind,
        weeks,
        [{"run_id": r.id, "kind": r.kind, "label": r.label} for r in sc.runs],
        dict(sc.counted),
    )


async def peaks(
    session: Any,
    *,
    term_id: int | None = None,
    group_by: str = "building",
    period_kind: str = "LECTURE",
    threshold: float | None = None,
) -> dict[str, Any]:
    """``GET /analytics/peaks``: peak cells of a term (default: the active term, else the latest published one)."""
    from sqlalchemy import select

    from app.models import ScheduleRun, Term
    from app.services import seasons

    if group_by not in GROUP_BY:
        raise ValueError(group_by)
    term = await session.get(Term, term_id) if term_id is not None else None
    if term is None and term_id is None:
        term = (await session.execute(select(Term).where(Term.is_active.is_(True)).limit(1))).scalar_one_or_none()
        if (
            term is None
            or not (
                await session.execute(
                    select(ScheduleRun.id)
                    .where(ScheduleRun.term_id == term.id, ScheduleRun.is_active.is_(True))
                    .limit(1)
                )
            ).first()
        ):
            term = (
                await session.execute(
                    select(Term)
                    .join(ScheduleRun, ScheduleRun.term_id == Term.id)
                    .where(ScheduleRun.is_active.is_(True))
                    .order_by(Term.start_date.desc().nullslast(), Term.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none() or term
    if term is None:
        return _none(None, group_by, period_kind, _t("Henüz dönem yok", "No term yet"))
    if threshold is None:
        prof = await seasons.resolve_profile(session, seasons.season_of(term), period_kind)
        threshold = float(prof.peak_threshold_pct if prof else seasons.DEFAULT_PEAK_THRESHOLD)
    tc = await term_cube(session, term.id, period_kind)
    if tc is None or not tc.weeks:
        return _none(
            term.id,
            group_by,
            period_kind,
            _t(
                "Yayımlanmış bir dönem gerekli: yoğun saatler yayımlanmış programdan ve rezervasyonlardan hesaplanır",
                "A published term is needed: peak hours come from the published timetable and the bookings",
            ),
            term_code=term.code,
        )
    cells = estimate(tc.cube, group_by, threshold=threshold)
    conf = confidence_of(len(tc.weeks))
    prof_arr = period_profile(tc.cube)
    peak_cells = sorted((c for c in cells if c.peak), key=lambda c: (-c.value, c.day, c.period, c.group))
    return {
        "term_id": term.id,
        "term_code": term.code,
        "period_kind": period_kind,
        "group_by": group_by,
        "threshold_pct": threshold,
        "weeks": tc.weeks,
        "rooms": len(tc.cube.rooms),
        "sources": tc.sources,
        "cells": [c.as_dict() for c in cells],
        "peaks": [c.as_dict() for c in peak_cells],
        "period_profile": [{"period": p + 1, "value": round(float(v), 1)} for p, v in enumerate(prof_arr.tolist())],
        "method": "shrunk_weekly_mean",
        "basis": _t(
            f"{len(tc.weeks)} haftanın yayımlanmış programı, blokları ve rezervasyonları; tatiller hariç",
            f"the published timetable, blocks and bookings of {len(tc.weeks)} week(s); holidays left out",
        ),
        "confidence": conf,
        "confidence_label": CONFIDENCE_LABEL[conf],
        "needs": None
        if conf in ("medium", "high")
        else _t(
            "En az 3 haftalık yayımlanmış program güveni artırır",
            "At least 3 weeks of a published timetable raise the confidence",
        ),
        "definitions": {
            "value": _t(
                "Yoğunluk %: grubun kullanılabilir oda-periyotlarından dolu (ders, rezervasyon ya da blok) olanların "
                "payı; haftalık ortalama, kampüs değerine doğru büzülmüş (k = 4 hafta)",
                "Load %: the share of the group's usable room-periods that are busy (class, booking or block); weekly "
                "mean shrunk toward the campus value (k = 4 weeks)",
            ),
            "range": _t("%80 aralık: haftalık değerlerin 10.–90. yüzdelikleri", "80 % range: 10th-90th percentile"),
            "seat_fill": _t("Koltuk doluluğu: dolu odalarda öğrenci / kapasite", "Seat fill: students / capacity"),
        },
    }


def _none(
    term_id: int | None, group_by: str, period_kind: str, needs: Mapping[str, str], term_code: str | None = None
) -> dict[str, Any]:
    return {
        "term_id": term_id,
        "term_code": term_code,
        "period_kind": period_kind,
        "group_by": group_by,
        "threshold_pct": None,
        "weeks": [],
        "rooms": 0,
        "sources": [],
        "cells": [],
        "peaks": [],
        "period_profile": [],
        "method": "shrunk_weekly_mean",
        "basis": None,
        "confidence": "none",
        "confidence_label": CONFIDENCE_LABEL["none"],
        "needs": dict(needs),
        "definitions": {},
    }


__all__ = [
    "Cube",
    "CellEstimate",
    "RoomInfo",
    "confidence_of",
    "day_profile",
    "estimate",
    "peaks",
    "period_profile",
    "room_infos",
    "term_cube",
]
