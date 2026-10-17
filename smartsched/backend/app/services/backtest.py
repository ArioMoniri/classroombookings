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


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
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
        return {"id": self.id, "name": self.name, "metrics": self.metrics, "targets": self.targets, "passed": self.passed}


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
