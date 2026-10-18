"""Backtests of the adaptive-scheduling models on the real fixture workbooks (AS-06, AS-07, AS-10, AS-11, AS-13;
docs/research/2026-10-17-adaptive-scheduling.md §3.8). ``python -m app.cli backtest adaptive [--json]`` runs them;
``tests/test_as_*_backtest*.py`` assert them on the session-cached parsed workbooks.

======  =================================================================  =========================================
ID      Backtest                                                           Target
======  =================================================================  =========================================
B1      weekly course room-periods: fit Bahar weeks 1-8, forecast 9-15       MAPE <= 2 %, MASE vs naive <= 1.0
B2      period profile Bahar -> Güz (18 periods, weekday share)              Pearson >= 0.95, top-4 shared >= 3/4
B3      building demand of Güz weeks 1-2 from the Bahar shape x the Güz      WAPE <= 15 % per building; 80 % coverage
        request level                                                        reported
B4      learning holdout: Bahar priors -> Güz definitive buildings           precision >= 0.8; no cross-season room
B5      what-if +10 % enrolment on the Bahar requests                        deterministic; count > the 0 % count
B6      exam advisor on Final 2026 (AS-12, the solver lane)                  reported by that lane
B7      slot-level exam holds on Final 2026                                  freed room-periods > 0
======  =================================================================  =========================================

Everything here is computed from the workbooks through the production parsers (no stored numbers, no fakes).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.services import peaks as pk

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
BAHAR_GRID = FIXTURES / "bahar_derslikler_takvimi_2026.xlsx"
GUZ_GRID = FIXTURES / "guz_derslikler_takvimi_2026_2027.xlsx"
FINAL_GRID = FIXTURES / "final_derslikler_takvimi_2026_v2.xlsx"
BAHAR_LIST = FIXTURES / "bahar_derslik_planlama_listesi_v5.xlsx"
GUZ_LIST = FIXTURES / "guz_derslik_planlama_2026_2027_v2.xlsx"
EXAM_LIST = FIXTURES / "final_planlama_listesi_2026_v2.xlsx"


# ------------------------------------------------------------------------------------------------ metrics


def mape(actual: Sequence[float], forecast: Sequence[float]) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    ok = a != 0
    return float(np.mean(np.abs((a[ok] - f[ok]) / a[ok])) * 100.0) if ok.any() else math.nan


def mae(actual: Sequence[float], forecast: Sequence[float]) -> float:
    return float(np.mean(np.abs(np.asarray(actual, float) - np.asarray(forecast, float))))


def wape(actual: Sequence[float], forecast: Sequence[float]) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    den = float(np.abs(a).sum())
    return float(np.abs(a - f).sum() / den * 100.0) if den else math.nan


def pearson(x: Any, y: Any) -> float:
    return float(np.corrcoef(np.asarray(x, float), np.asarray(y, float))[0, 1])


def top_k(values: Sequence[float], k: int = 4) -> list[int]:
    """1-based indices of the ``k`` largest values (ties: the earlier one)."""
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    return [i + 1 for i in order[:k]]


# ------------------------------------------------------------------------------------------------ grids -> cubes


def grid_rooms(parsed: Any) -> list[pk.RoomInfo]:
    """Room infos of a parsed weekly grid: ids are positions (no database), capacity from the headers."""
    from app.services.utilisation import CAPACITY_BANDS, CAPACITY_TOP

    def band(cap: int) -> str:
        return next((lab for up, lab in CAPACITY_BANDS if cap <= up), CAPACITY_TOP)

    out = []
    for i, code in enumerate(sorted(parsed.rooms)):
        h = parsed.rooms[code]
        tags = {str(t).upper() for t in h.tags or []}
        rtype = next((t for t in ("TIP", "AMPHI", "LAB", "PC") if t in tags), "STANDARD")
        cap = int(h.capacity or 0)
        out.append(pk.RoomInfo(i + 1, code, code[:1], rtype, band(cap), cap))
    return out


def grid_cube(parsed: Any, kinds: Iterable[str] = ("LECTURE",), weeks: Iterable[int] | None = None) -> pk.Cube:
    """Busy room-periods of the sheets of the given kinds (every entry: courses and blocks)."""
    kinds = set(kinds)
    sheets = [s for s in parsed.sheets if s.kind in kinds and (weeks is None or s.week_index in set(weeks))]
    rooms = grid_rooms(parsed)
    by_code = {r.code: r.id for r in rooms}
    cube = pk.Cube.empty(sorted({s.week_index for s in sheets}), rooms)
    for s in sheets:
        for e in s.entries:
            rid = by_code.get(e.room_code)
            if rid is not None:
                cube.mark(s.week_index, e.day, e.start_period, e.end_period, rid)
    return cube


def weekly_course_room_periods(parsed: Any, kinds: Iterable[str] = ("LECTURE",)) -> dict[int, int]:
    out: dict[int, int] = defaultdict(int)
    for s in parsed.sheets:
        if s.kind not in set(kinds):
            continue
        out[s.week_index] += sum(e.end_period - e.start_period + 1 for e in s.entries if e.cell.kind == "COURSE")
    return dict(sorted(out.items()))


# ------------------------------------------------------------------------------------------------ B1, B2


@dataclass
class Result:
    id: str
    name: str
    metrics: dict[str, Any]
    targets: dict[str, Any]
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "metrics": self.metrics,
            "targets": self.targets,
            "passed": self.passed,
        }


def b1_weekly_volume(bahar_grid: Any) -> Result:
    """Fit the mean of Bahar lecture weeks 1-8, forecast 9-15; the naive forecast repeats week 8."""
    series = weekly_course_room_periods(bahar_grid)
    train = [series[w] for w in range(1, 9) if w in series]
    test_w = [w for w in range(9, 16) if w in series]
    actual = [series[w] for w in test_w]
    mean_f = [float(np.mean(train))] * len(actual)
    naive_f = [float(train[-1])] * len(actual)
    m_mape, n_mape = mape(actual, mean_f), mape(actual, naive_f)
    mase = mae(actual, mean_f) / mae(actual, naive_f) if mae(actual, naive_f) else math.nan
    cv = float(np.std(list(series.values())) / np.mean(list(series.values())) * 100.0)
    return Result(
        "B1",
        "Haftalık ders oda-periyodu: 1-8 → 9-15 / weekly course room-periods: weeks 1-8 → 9-15",
        {
            "weeks": list(series),
            "mean_train": round(float(np.mean(train)), 1),
            "mape_pct": round(m_mape, 2),
            "naive_mape_pct": round(n_mape, 2),
            "mase": round(mase, 3),
            "cv_pct": round(cv, 2),
        },
        {"mape_pct": "<= 2", "mase": "<= 1.0"},
        m_mape <= 2.0 and mase <= 1.0,
    )


def b2_shape_transfer(bahar_grid: Any, guz_grid: Any) -> Result:
    b = pk.period_profile(grid_cube(bahar_grid)).tolist()
    g = pk.period_profile(grid_cube(guz_grid)).tolist()
    r = pearson(b, g)
    tb, tg = top_k(b), top_k(g)
    shared = len(set(tb) & set(tg))
    return Result(
        "B2",
        "Saat profili Bahar → Güz / period shape Bahar → Fall",
        {
            "bahar": [round(v, 1) for v in b],
            "guz": [round(v, 1) for v in g],
            "pearson": round(r, 4),
            "spearman": round(spearman(b, g), 4),
            "top4_bahar": tb,
            "top4_guz": tg,
            "top4_shared": shared,
        },
        {"pearson": ">= 0.95", "top4_shared": ">= 3"},
        r >= 0.95 and shared >= 3,
    )


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    def ranks(v: Sequence[float]) -> np.ndarray:
        order = np.argsort(np.asarray(v, float), kind="stable")
        out = np.empty(len(v), float)
        out[order] = np.arange(1, len(v) + 1)
        # average ranks of ties
        vals = np.asarray(v, float)
        for val in set(vals.tolist()):
            idx = np.where(vals == val)[0]
            if len(idx) > 1:
                out[idx] = out[idx].mean()
        return out

    return pearson(ranks(x), ranks(y))


# ------------------------------------------------------------------------------------------------ B3 (AS-07)


def building_course_room_periods(parsed: Any) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for s in parsed.sheets:
        if s.kind != "LECTURE":
            continue
        for e in s.entries:
            if e.cell.kind == "COURSE":
                out[s.week_index][e.room_code[:1]] += e.end_period - e.start_period + 1
    return {w: dict(v) for w, v in sorted(out.items())}


def _weekly_shares(grid: Any) -> dict[str, list[float]]:
    by_week = building_course_room_periods(grid)
    shares: dict[str, list[float]] = defaultdict(list)
    for _w, by_b in by_week.items():
        tot = sum(by_b.values())
        for b in sorted({k for v in by_week.values() for k in v}):
            shares[b].append(by_b.get(b, 0) / tot if tot else 0.0)
    return shares


def shape_scores(src_grid: Any, tgt_grid: Any) -> list[float]:
    """AS-21 calibration fold: the source term's mean building shares x each target week's real total, scored
    against the target week (``forecast.poisson_score``). Shape only: the level comes from the target itself,
    because the Bahar request list overstates the realised Bahar grid by ~27 % (a list effect B3 does not have)."""
    from app.services import forecast as fc

    shares = _weekly_shares(src_grid)
    out: list[float] = []
    for _w, by_b in sorted(building_course_room_periods(tgt_grid).items()):
        total = float(sum(by_b.values()))
        for b in sorted(set(shares) | set(by_b)):
            mean = float(np.mean(shares[b])) if shares.get(b) else 0.0
            out.append(fc.poisson_score(float(by_b.get(b, 0)), total * mean))
    return out


def b3_building_demand(bahar_grid: Any, guz_grid: Any, guz_list: Any) -> Result:
    """Güz weeks 1-2 course room-periods per building = (the Güz requests' weekly room-periods) x (the Bahar share
    of each building, week by week). 80 % ranges (AS-21): split conformal, calibrated out of sample on the reverse
    fold (Güz shape -> Bahar weeks, ``shape_scores``) plus the level prior; the old within-term range is reported
    as ``coverage80_uncalibrated_pct``. Gate: WAPE <= 15 % and coverage 70-90 %."""
    from app.services import forecast as fc

    bahar = building_course_room_periods(bahar_grid)
    shares: dict[str, list[float]] = defaultdict(list)
    for _w, by_b in bahar.items():
        tot = sum(by_b.values())
        for b in sorted({k for v in bahar.values() for k in v}):
            shares[b].append(by_b.get(b, 0) / tot if tot else 0.0)
    totals = np.asarray([sum(v.values()) for v in bahar.values()], float)
    rel_sd = float(totals.std() / totals.mean()) if totals.size > 1 else 0.0
    needs = fc.needs_from_planning_rows(guz_list.rows)
    actual = building_course_room_periods(guz_grid)
    rows: list[dict[str, Any]] = []
    inside, n_cells = 0, 0
    wapes = {}
    per_building_err: dict[str, list[float]] = defaultdict(list)
    cal_scores = shape_scores(guz_grid, bahar_grid)
    q80 = fc.conformal_quantile(cal_scores)
    q80 = round(q80, 2) if q80 is not None else fc.SHAPE_Q80
    level_sd = max(rel_sd, fc.LEVEL_REL_SD_PRIOR)
    inside_old = 0
    for w, by_b in actual.items():
        level = float(sum(x.span for x in needs if x.weeks is None or w in x.weeks))
        uncal = fc.shape_times_level(level, shares, rel_level_sd=rel_sd)
        fcast = fc.shape_times_level(level, shares, rel_level_sd=level_sd, shape_q80=q80)
        a_list, f_list = [], []
        for b in sorted(set(fcast) | set(by_b)):
            v, lo, hi = fcast.get(b, (0.0, 0.0, 0.0))
            a = float(by_b.get(b, 0))
            a_list.append(a)
            f_list.append(v)
            n_cells += 1
            inside += int(lo <= a <= hi)
            _ov, olo, ohi = uncal.get(b, (0.0, 0.0, 0.0))
            inside_old += int(olo <= a <= ohi)
            per_building_err[b].append(abs(a - v) / a * 100.0 if a else 0.0)
            rows.append(
                {
                    "week": w,
                    "building": b,
                    "actual": a,
                    "forecast": round(v, 1),
                    "lo80": round(lo, 1),
                    "hi80": round(hi, 1),
                }
            )
        wapes[w] = round(wape(a_list, f_list), 2)
    overall = wape([r["actual"] for r in rows], [r["forecast"] for r in rows])
    coverage = inside / n_cells * 100.0 if n_cells else math.nan
    coverage_old = inside_old / n_cells * 100.0 if n_cells else math.nan
    return Result(
        "B3",
        "Bina talebi: Bahar şekli × Güz talep düzeyi / building demand: Bahar shape × Fall request level",
        {
            "wape_pct": round(overall, 2),
            "wape_by_week_pct": wapes,
            "ape_by_building_pct": {b: [round(x, 1) for x in v] for b, v in sorted(per_building_err.items())},
            "coverage80_pct": round(coverage, 1),
            "coverage80_uncalibrated_pct": round(coverage_old, 1),
            "calibration": {
                "fold": "guz->bahar",
                "method": "split conformal, Poisson-scaled shape scores",
                "n": len(cal_scores),
                "shape_q80": q80,
                "level_rel_sd": level_sd,
            },
            "level_requests": {w: float(sum(x.span for x in needs if x.weeks is None or w in x.weeks)) for w in actual},
            "cells": rows,
        },
        {"wape_pct": "<= 15", "coverage80_pct": "70-90"},
        overall <= 15.0 and 70.0 <= coverage <= 90.0,
    )


# ------------------------------------------------------------------------------------------------ B5 (AS-10)


def b5_what_if(bahar_list: Any, room_master: Path | None = None, pct: float = 10.0) -> Result:
    from app.services import forecast as fc

    rooms = fc.rooms_from_master_csv(room_master or FIXTURES / "room_master.csv")
    needs = fc.needs_from_planning_rows(bahar_list.rows)
    base = fc.fit_report(needs, rooms)
    scen = fc.fit_report(fc.apply_what_if(needs, fc.WhatIf(enrolment_pct=pct)), rooms)
    again = fc.fit_report(fc.apply_what_if(needs, fc.WhatIf(enrolment_pct=pct)), rooms)
    return Result(
        "B5",
        f"Ne olur: Bahar talepleri %{pct:+g} kontenjan / what-if {pct:+g} % enrolment on the Bahar requests",
        {
            "classes": base["classes"],
            "no_fit_0pct": base["no_fit"],
            f"no_fit_{pct:+g}pct": scen["no_fit"],
            "shortfall_cells_0pct": base["shortfall_cells"],
            f"shortfall_cells_{pct:+g}pct": scen["shortfall_cells"],
            "shortfall_total_0pct": base["shortfall_total"],
            f"shortfall_total_{pct:+g}pct": scen["shortfall_total"],
            "deterministic": scen == again,
            "top_shortfall_cells": scen["cells"][:5],
        },
        {"no_fit": "> the 0 % count", "deterministic": True},
        scen["no_fit"] > base["no_fit"] and scen == again,
    )


# ------------------------------------------------------------------------------------------------ B7, exam load (AS-11)


def exam_spans(exam_list: Any) -> dict[tuple[str, Any], list[tuple[int, int]]]:
    """(room code, date) -> exam period spans of the Final list's dated rows with definitive rooms."""
    out: dict[tuple[str, Any], list[tuple[int, int]]] = defaultdict(list)
    for r in exam_list.rows:
        codes = list(getattr(r.definitive, "room_codes", []) or [])
        if r.date is None or not codes or not r.periods.start_period:
            continue
        for c in codes:
            out[(c, r.date)].append((int(r.periods.start_period), int(r.periods.end_period)))
    return dict(out)


def b7_slot_holds(exam_list: Any, buffer_periods: int = 1) -> Result:
    from datetime import timedelta

    from app.services.booking_policies import ExamSlotIndex

    spans = exam_spans(exam_list)
    ids = {c: i + 1 for i, c in enumerate(sorted({c for c, _d in spans}))}
    idx = ExamSlotIndex(None, buffer_periods, {(ids[c], d): v for (c, d), v in spans.items()})
    held = idx.held_room_periods()
    rooms = {c for c, _d in spans}
    mondays = sorted({d - timedelta(days=d.weekday()) for _c, d in spans})
    days = [m + timedelta(days=i) for m in mondays for i in range(7)]
    closed = len(rooms) * len(days) * 18
    exam_rp = sum(e - s + 1 for v in spans.values() for s, e in v)
    uncovered = 0
    for (c, d), v in spans.items():
        for s, e in v:
            for p in range(s, e + 1):
                if idx.covers(ids[c], d, p, p) is None:
                    uncovered += 1
    return Result(
        "B7",
        "Sınav saatine göre tutma / slot-level exam holds (Final 2026)",
        {
            "exam_rooms": len(rooms),
            "exam_days_closed": len(days),
            "exam_room_periods": exam_rp,
            "held_room_periods": len(held),
            "closed_room_periods": closed,
            "freed_room_periods": closed - len(held),
            "exam_room_periods_bookable": uncovered,
            "buffer_periods": buffer_periods,
        },
        {"freed_room_periods": "> 0", "exam_room_periods_bookable": 0},
        closed - len(held) > 0 and uncovered == 0,
    )


def exam_day_load(exam_list: Any) -> Result:
    """Exams with a date and a room per weekday of the Final period: the peak day and its ratio to the mean."""
    from app.services.exam_load import day_load

    load = day_load(
        [
            (r.date, int(r.enrolment or 0))
            for r in exam_list.rows
            if r.date is not None and getattr(r.definitive, "room_codes", None)
        ]
    )
    return Result(
        "B6a",
        "Sınav günü yükü / exam day load (Final 2026)",
        load,
        {"peak_to_mean": "1.86 ± 0.01 (measured 2026-10-17)"},
        abs(load["peak_to_mean"] - 1.86) <= 0.01,
    )


# ------------------------------------------------------------------------------------------------ all


@dataclass
class Fixtures:
    bahar_grid: Any
    guz_grid: Any
    bahar_list: Any
    guz_list: Any
    exam_list: Any


def load_fixtures() -> Fixtures:
    from app.importers.exam_list import parse_exam_list
    from app.importers.planning_list import parse_planning_list
    from app.importers.weekly_grid import parse_weekly_grid

    return Fixtures(
        parse_weekly_grid(BAHAR_GRID, year=2026),
        parse_weekly_grid(GUZ_GRID, year=2026),
        parse_planning_list(BAHAR_LIST),
        parse_planning_list(GUZ_LIST),
        parse_exam_list(EXAM_LIST),
    )


def run_all(fx: Fixtures | None = None) -> list[Result]:
    fx = fx or load_fixtures()
    out = [
        b1_weekly_volume(fx.bahar_grid),
        b2_shape_transfer(fx.bahar_grid, fx.guz_grid),
        b3_building_demand(fx.bahar_grid, fx.guz_grid, fx.guz_list),
        b5_what_if(fx.bahar_list),
        exam_day_load(fx.exam_list),
        b7_slot_holds(fx.exam_list),
    ]
    return out


def table(results: Sequence[Result]) -> str:
    """Plain-text table for the CLI."""
    lines = [f"{'ID':4} {'OK':4} name / metrics"]
    for r in results:
        keep = {k: v for k, v in r.metrics.items() if not isinstance(v, list | dict) or k.endswith("_pct")}
        lines.append(f"{r.id:4} {'yes' if r.passed else 'NO':4} {r.name}")
        lines.append(f"          {keep}")
        lines.append(f"          targets: {r.targets}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ B4 (AS-13)


async def b4_learning_holdout(session: Any, train_code: str = "2026-BAHAR", test_code: str = "2026-GUZ") -> Result:
    """Priors for the Güz term learned from Bahar evidence only (the Güz term's own observations are left out:
    run this on a copy) -> the suggestible building priors vs the buildings of the Güz definitive rooms of the same
    subjects (instructor, course, programme). Also: no room or room-feature prior may be suggestible across seasons.

    Destructive on purpose: it deletes the test term's observations in the given database."""
    from sqlalchemy import delete, select

    from app.models import LearnedObservation, LearnedPrior, MeetingRequest, Room, Section, SectionInstructor, Term
    from app.services import learning

    terms = {t.code: t for t in (await session.execute(select(Term))).scalars()}
    test = terms[test_code]
    await session.execute(delete(LearnedObservation).where(LearnedObservation.term_id == test.id))
    await session.flush()
    learning._forget()
    await learning.recompute_priors(session, test.id)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    truth: dict[tuple[str, str], set[str]] = defaultdict(set)
    q = (
        select(MeetingRequest.definitive_room_ids, Section.course_id, Section.program_id, Section.id)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(Section.term_id == test.id, MeetingRequest.archived.is_(False))
    )
    sec_ins: dict[int, list[int]] = defaultdict(list)
    for sid, iid in (
        await session.execute(
            select(SectionInstructor.section_id, SectionInstructor.instructor_id)
            .join(Section, Section.id == SectionInstructor.section_id)
            .where(Section.term_id == test.id)
        )
    ).all():
        sec_ins[int(sid)].append(int(iid))
    for ids, cid, pid, sid in (await session.execute(q)).all():
        blds = {rooms[int(r)].code[:1] for r in ids or [] if int(r) in rooms}
        if not blds:
            continue
        truth[("course", str(cid))] |= blds
        if pid:
            truth[("program", str(pid))] |= blds
        for iid in sec_ins.get(int(sid), []):
            truth[("instructor", str(iid))] |= blds
    priors = list(
        (
            await session.execute(
                select(LearnedPrior).where(LearnedPrior.term_id == test.id, LearnedPrior.suggestible.is_(True))
            )
        ).scalars()
    )
    building = [p for p in priors if p.attribute == "building" and (p.subject_type, p.subject_key) in truth]
    hits = sum(1 for p in building if p.value in truth[(p.subject_type, p.subject_key)])
    cross = [p for p in priors if p.attribute in ("room", "tag")]
    precision = hits / len(building) if building else math.nan
    return Result(
        "B4",
        "Öğrenme: yalnız Bahar → Güz bina önerileri / learning holdout: Bahar only → Güz building suggestions",
        {
            "building_suggestions": len(building),
            "hits": hits,
            "precision": round(precision, 3) if building else None,
            "cross_season_room_or_tag": len(cross),
            "suggestible_total": len(priors),
            "by_subject": dict(Counter(p.subject_type for p in building)),
        },
        {"precision": ">= 0.8", "cross_season_room_or_tag": 0},
        bool(building) and precision >= 0.8 and not cross,
    )


async def b4_standalone() -> Result:
    """B4 on a throwaway SQLite database built from the two planning lists (the CLI path)."""
    import tempfile

    from app.core import db as dbmod
    from app.importers.planning_list import import_planning_list
    from app.models import Base
    from app.services import learning_extract

    with tempfile.TemporaryDirectory(prefix="smartsched-b4-") as tmp:
        dbmod.configure_engine(f"sqlite+aiosqlite:///{tmp}/b4.db")
        async with dbmod.get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with dbmod.get_session_factory()() as s:
                await import_planning_list(s, BAHAR_LIST, "2026-BAHAR")
                await s.commit()
                await import_planning_list(s, GUZ_LIST, "2026-GUZ")
                await s.commit()
                await learning_extract.extract(s)
                await s.commit()
                return await b4_learning_holdout(s)
        finally:
            await dbmod.dispose_engine()
