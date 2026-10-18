"""Backtests of the solver lane of adaptive scheduling (AS-S: B6 AS-12, B8 AS-08, B9 AS-14;
docs/research/2026-10-17-adaptive-scheduling.md §3.8).  They return :class:`app.services.backtest.Result` so that
``python -m app.cli backtest adaptive`` can list them with B1-B7.

======  =================================================================  =========================================
ID      Backtest                                                           Target
======  =================================================================  =========================================
B6      exam advisor on Final 2026: accept the ranked moves                 peak day 126 -> <= 100, no new cohort
                                                                           conflict (cohort day > 2 or clash)
B8      peak smoothing on the flexible-day subset of Bahar week 3           hard score and placed classes unchanged,
        (Mon-Tue, the unlocked classes may take either day)                load above the threshold <= the off run
B9      weight learning on synthetic edits made with known weights         Kendall tau of the recovered weight
                                                                           ratios >= 0.8
======  =================================================================  =========================================
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.services.backtest import EXAM_LIST, FIXTURES, Result

ROOM_MASTER = FIXTURES / "room_master.csv"


def exam_capacity_of_master(path: Path = ROOM_MASTER) -> int:
    """Sum of the exam capacities of the bookable rooms of a room-master CSV."""
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    total = 0
    for row in csv.DictReader(lines):
        if str(row.get("bookable", "1")).strip() in ("0", "false", "False"):
            continue
        total += int(row.get("exam_capacity") or 0)
    return total


# ------------------------------------------------------------------------------------------------ B6 (AS-12)


def _conflict_cells(items: Iterable[Any], max_per_day: int) -> set[tuple[str, str, Any]]:
    """(kind, key, date) of every cohort day above ``max_per_day`` and every clashing pair."""
    from collections import Counter, defaultdict

    per: Counter[tuple[str, Any]] = Counter()
    spans: dict[tuple[str, Any], list[tuple[int, int, int]]] = defaultdict(list)
    for x in items:
        for c in x.cohorts:
            per[(c, x.date)] += 1
        for k in x.keys:
            spans[(k, x.date)].append((x.start, x.end, x.id))
    out: set[tuple[str, str, Any]] = {("cohort_day", c, d) for (c, d), n in per.items() if n > max_per_day}
    for (k, d), v in spans.items():
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                (sa, ea, ia), (sb, eb, ib) = v[i], v[j]
                if sa <= eb and sb <= ea:
                    out.add(("clash", f"{k}|{min(ia, ib)}|{max(ia, ib)}", d))
    return out


def b6_exam_advisor(exam_list: Any, room_master: Path | None = None, target: int = 100) -> Result:
    from app.services import exam_advisor as ea

    items = ea.items_from_exam_list(exam_list)
    cap = exam_capacity_of_master(room_master or ROOM_MASTER)
    cfg = ea.AdvisorConfig()
    out = ea.advise(items, exam_capacity=cap, cfg=cfg)
    again = ea.advise(list(reversed(items)), exam_capacity=cap, cfg=cfg)
    moves = out["suggestions"]
    before = ea.summary(items, exam_capacity=cap, cfg=cfg)
    # the smallest prefix of the ranked moves that brings the peak day to the target (or all of them)
    n_needed = len(moves)
    for n in range(len(moves) + 1):
        if ea.summary(ea.apply_moves(items, moves[:n]), exam_capacity=cap, cfg=cfg)["peak_exams"] <= target:
            n_needed = n
            break
    accepted = moves[:n_needed]
    after_items = ea.apply_moves(items, accepted)
    after = ea.summary(after_items, exam_capacity=cap, cfg=cfg)
    new_conflicts = _conflict_cells(after_items, cfg.max_per_day) - _conflict_cells(items, cfg.max_per_day)
    metrics = {
        "exam_rows": sum(i.rows for i in items),
        "exams": len(items),
        "exam_capacity": cap,
        "peak_day_before": before["peak_day"],
        "peak_exams_before": before["peak_exams"],
        "weekday_mean": before["weekday_mean"],
        "target_per_day": before["target_per_day"],
        "suggestions": len(moves),
        "moves_accepted": len(accepted),
        "rows_moved": sum(m["rows"] for m in accepted),
        "peak_day_after": after["peak_day"],
        "peak_exams_after": after["peak_exams"],
        "cohort_days_over_before": before["cohort_days_over"],
        "cohort_days_over_after": after["cohort_days_over"],
        "clashes_before": before["clashes"],
        "clashes_after": after["clashes"],
        "back_to_back_before": before["back_to_back"],
        "back_to_back_after": after["back_to_back"],
        "front_load_before": before["front_load"],
        "front_load_after": after["front_load"],
        "seat_slots_over_before": before["seat_slots_over"],
        "seat_slots_over_after": after["seat_slots_over"],
        "new_cohort_conflicts": len(new_conflicts),
        "deterministic": out == again,
        "top_moves": [m["text"]["en"] for m in moves[:5]],
    }
    return Result(
        "B6",
        "Sınav tarihi danışmanı / exam date advisor (Final 2026)",
        metrics,
        {"peak_exams_after": f"<= {target} (from 126)", "new_cohort_conflicts": 0, "deterministic": True},
        before["peak_exams"] > after["peak_exams"]
        and after["peak_exams"] <= target
        and not new_conflicts
        and out == again,
    )


def b6_standalone() -> Result:
    from app.importers.exam_list import parse_exam_list

    return b6_exam_advisor(parse_exam_list(EXAM_LIST))


__all__ = ["b6_exam_advisor", "b6_standalone", "exam_capacity_of_master"]
