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


# ------------------------------------------------------------------------------------------------ B8 (AS-08)

B8_DAYS = (1, 2)
B8_WEEK = 3
B8_GROUPS = ["*", "building:*", "tag:PC"]
B8_WEIGHT = 10


def flexible_day_subset(inp: Any, days: tuple[int, ...] = B8_DAYS) -> Any:
    """The classes of ``days``; the ones the planner did not lock (no locked room set, a room needed) may take any
    of ``days`` at their own start.  Blocks, days and targeted rules are narrowed to the subset."""
    from dataclasses import replace

    keep = set(days)
    events = []
    for e in inp.events:
        if e.fixed_day is not None and e.fixed_day not in keep:
            continue
        if e.fixed_day is None and not (set(e.allowed_days) & keep):
            continue
        if e.locked is None and e.needs_room:
            e = replace(e, fixed_day=None, allowed_days=frozenset(days))
        events.append(e)
    ids = {e.id for e in events}
    cons = tuple(c for c in inp.constraints if not c.params.get("event_ids") or set(c.params["event_ids"]) & ids)
    return replace(
        inp,
        events=tuple(events),
        days=tuple(days),
        blocks=tuple(b for b in inp.blocks if b.day in keep),
        constraints=cons,
    )


def _peak_units(inp: Any, assignments: Any) -> int:
    """Room-periods above the threshold that flexible classes account for (weight 1, the B8 groups)."""
    from dataclasses import replace

    from app.solver.scoring import evaluate

    probe = replace(
        inp,
        constraints=(*(c for c in inp.constraints if c.kind != "peak_smoothing"), _b8_rule()),
        weights={**inp.weights, "peak_smoothing": 1},
    )
    return int(evaluate(probe, assignments).penalties.get("peak_smoothing", 0))


def _b8_rule() -> Any:
    from app.solver.model import Constraint

    return Constraint("peak_smoothing", {"groups": list(B8_GROUPS)}, hard=False)


def b8_peak_smoothing(
    full: Any, *, days: tuple[int, ...] = B8_DAYS, weight: int = B8_WEIGHT, time_limit_s: float = 20.0
) -> Result:
    """Off vs on (``peak_smoothing`` = ``weight``) on the flexible-day subset, one worker, seed 0 (deterministic)."""
    from dataclasses import replace

    from app.solver.cpsat import solve
    from app.solver.domains import is_input_fixed
    from app.solver.scoring import evaluate

    sub = flexible_day_subset(full, days)
    base = replace(sub, time_limit_s=time_limit_s, workers=1, seed=0)
    rule = _b8_rule()
    off_inp = replace(base, constraints=(*base.constraints, rule), weights={**base.weights, "peak_smoothing": 0})
    on_inp = replace(base, constraints=(*base.constraints, rule), weights={**base.weights, "peak_smoothing": weight})
    plain = solve(base)
    off = solve(off_inp)
    on = solve(on_inp)
    ev_off, ev_on = evaluate(off_inp, off.assignments), evaluate(on_inp, on.assignments)
    flexible = {e.id for e in sub.events if e.needs_room and not is_input_fixed(e, ())}
    placed_off = {a.event_id for a in off.assignments}
    placed_on = {a.event_id for a in on.assignments}
    events = {e.id: e for e in sub.events}
    fixed_moved = 0
    for a in on.assignments:
        e = events[a.event_id]
        if a.event_id in flexible:
            continue
        if e.fixed_day is not None and (a.day, a.start) != (e.fixed_day, e.fixed_start):
            fixed_moved += 1
    off_by = {a.event_id: a for a in off.assignments}
    moved = sum(
        1 for a in on.assignments if a.event_id in flexible and a.event_id in off_by and off_by[a.event_id].day != a.day
    )
    units_off, units_on = _peak_units(sub, off.assignments), _peak_units(sub, on.assignments)
    identical = plain.assignments == off.assignments and plain.objective_breakdown == off.objective_breakdown
    metrics = {
        "week": B8_WEEK,
        "days": list(days),
        "events": len(sub.events),
        "flexible_events": len(flexible),
        "rooms": len(sub.rooms),
        "weight": weight,
        "groups": list(B8_GROUPS),
        "threshold_pct": 85,
        "status_off": off.status,
        "status_on": on.status,
        "hard_score_off": off.hard_score,
        "hard_score_on": on.hard_score,
        "hard_violations_off": len(ev_off.hard_violations()),
        "hard_violations_on": len(ev_on.hard_violations()),
        "placed_off": len(placed_off),
        "placed_on": len(placed_on),
        "lost_classes": len(placed_off - placed_on),
        "fixed_moved": fixed_moved,
        "flexible_moved_day": moved,
        "peak_units_off": units_off,
        "peak_units_on": units_on,
        "objective_on": dict(sorted(on.objective_breakdown.items())),
        "objective_off": dict(sorted(off.objective_breakdown.items())),
        "weight_zero_identical": identical,
    }
    passed = (
        on.hard_score == off.hard_score
        and len(placed_on) == len(placed_off)
        and not (placed_off - placed_on)
        and len(ev_on.hard_violations()) == len(ev_off.hard_violations())
        and fixed_moved == 0
        and units_on <= units_off
        and identical
    )
    return Result(
        "B8",
        "Yoğun saat yumuşatma / peak smoothing (Bahar week 3, Mon-Tue flexible-day subset)",
        metrics,
        {
            "hard_score": "unchanged",
            "placed": "unchanged, no class lost",
            "peak_units_on": "<= peak_units_off",
            "weight_zero_identical": True,
        },
        passed,
    )


async def b8_input(session: Any, week: int = B8_WEEK) -> Any:
    """Bahar imported through the production importers (grid, planning list, room master) -> the week's input."""
    from sqlalchemy import select

    from app.importers.planning_list import import_planning_list
    from app.importers.room_master import import_room_master
    from app.importers.weekly_grid import import_weekly_grid
    from app.models import ScheduleRun, Term
    from app.services.backtest import BAHAR_GRID, BAHAR_LIST
    from app.services.solver_bridge import build_solver_input

    term_id = (await session.execute(select(Term.id).where(Term.code == "2026-BAHAR"))).scalar_one_or_none()
    if term_id is None:
        await import_weekly_grid(session, BAHAR_GRID, "2026-BAHAR", year=2026)
        await import_planning_list(session, BAHAR_LIST, "2026-BAHAR")
        await import_room_master(session, ROOM_MASTER)
        term_id = (await session.execute(select(Term.id).where(Term.code == "2026-BAHAR"))).scalar_one()
    run = ScheduleRun(term_id=term_id, kind="COURSE", horizon="WEEK", horizon_params={"weeks": [week]}, params={})
    inp, _members = await build_solver_input(session, run)
    return inp


async def b8_standalone() -> Result:
    """B8 on its own in-memory SQLite database (the CLI path)."""
    from app.core import db as dbmod
    from app.models import Base

    eng = dbmod.configure_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with dbmod.get_session_factory()() as s:
            inp = await b8_input(s)
        return b8_peak_smoothing(inp)
    finally:
        await dbmod.dispose_engine()


__all__ = [
    "b6_exam_advisor",
    "b6_standalone",
    "b8_input",
    "b8_peak_smoothing",
    "b8_standalone",
    "exam_capacity_of_master",
    "flexible_day_subset",
]
