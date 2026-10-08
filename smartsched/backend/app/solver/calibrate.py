"""Weight calibration against the planner's own rooms (``python -m app.solver.calibrate``).

With the planner's definitive rooms used as *soft hints* (bridge run param ``definitive_rooms="prefer"``,
no locks), how often does the solver put an event back into exactly the planner's room set?  This
module grid-searches a few weight sets (``SolverInput.weights`` overrides of ``weights.DEFAULT_WEIGHTS``)
on Bahar week 3, Güz week 3 and the Final exams and records, per (instance, weight set):

* ``placed`` / ``roomed`` — placement (must not drop against the defaults), ``hard`` — hard score;
* ``repro_exact`` — planner-roomed events whose solver room set *equals* the planner's set (courses);
* ``repro_overlap`` — events sharing at least one room with the planner's set (exams: the planner's split /
  shared room patterns differ legitimately, so the overlap rate is the exam target).

The solver itself never imports this module.  Only :func:`build_instances` touches the importers and the
bridge (lazily, on a throw-away SQLite file), so the measurement is exactly what ``POST /runs`` would
solve.  Deterministic per seed; with ``workers > 1`` and a time limit the numbers vary by a few events
between runs, so the CLI reports the mean of ``--repeat`` seeds.

    cd smartsched/backend
    python -m app.solver.calibrate --time-limit 90 --repeat 2 --workers 4 --out /tmp/calibration.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.solver.model import SolverInput, SolverResult

#: candidate weight sets (overrides of weights.DEFAULT_WEIGHTS); "defaults" is the reference
WEIGHT_SETS: dict[str, dict[str, int]] = {
    "defaults": {},
    "pref20": {"room_preference": 20, "building_preference": 5, "min_capacity_waste": 1},
    "pref30-bld2": {"room_preference": 30, "building_preference": 2, "min_capacity_waste": 1},
    "pref30-bld0": {"room_preference": 30, "building_preference": 0, "min_capacity_waste": 1},
    "pref50-bld0": {"room_preference": 50, "building_preference": 0, "min_capacity_waste": 1},
    "pref10-waste0": {"room_preference": 10, "building_preference": 5, "min_capacity_waste": 0},
}


@dataclass
class Instance:
    name: str
    kind: str  # COURSE | EXAM
    inp: SolverInput
    #: solver event id -> the planner's definitive room set (rooms inside the pool, LOCKED rows only)
    planner: dict[int, frozenset[int]]


def metrics(inst: Instance, res: SolverResult) -> dict[str, Any]:
    """Placement and reproduction of one solve (event level; joint lectures / exam cohorts merged)."""
    asg = {a.event_id: a for a in res.assignments}
    roomed = [e for e in inst.inp.events if e.needs_room]
    placed_roomed = sum(1 for e in roomed if e.id in asg)
    exact = sum(1 for e, rs in inst.planner.items() if e in asg and set(asg[e].room_ids) == set(rs))
    overlap = sum(1 for e, rs in inst.planner.items() if e in asg and set(asg[e].room_ids) & set(rs))
    n = max(1, len(inst.planner))
    return {
        "events": len(inst.inp.events),
        "placed": len(asg),
        "roomed": len(roomed),
        "placed_roomed": placed_roomed,
        "planner_events": len(inst.planner),
        "planner_placed": sum(1 for e in inst.planner if e in asg),
        "repro_exact": exact,
        "repro_overlap": overlap,
        "repro_exact_rate": round(exact / n, 4),
        "repro_overlap_rate": round(overlap / n, 4),
        "hard": res.hard_score,
        "soft": res.soft_score,
        "status": res.status,
        "relax_status": res.stats.get("relax_status"),
        "phase2_status": res.stats.get("phase2_status"),
    }


def run_grid(
    instances: Iterable[Instance],
    weight_sets: Mapping[str, Mapping[str, int]],
    *,
    time_limit_s: float = 90.0,
    seeds: Iterable[int] = (0,),
    workers: int = 8,
    log: Any = None,
) -> list[dict[str, Any]]:
    """Solve every instance with every weight set (and seed); one row per (instance, set, seed)."""
    from app.solver.cpsat import solve

    rows: list[dict[str, Any]] = []
    for inst in instances:
        for name, weights in weight_sets.items():
            for seed in seeds:
                inp = replace(inst.inp, weights=dict(weights), time_limit_s=time_limit_s, seed=seed, workers=workers)
                t0 = time.perf_counter()
                res = solve(inp)
                row = {
                    "instance": inst.name,
                    "kind": inst.kind,
                    "weights": name,
                    "overrides": dict(weights),
                    "seed": seed,
                    "wall_s": round(time.perf_counter() - t0, 1),
                }
                row.update(metrics(inst, res))
                rows.append(row)
                if log is not None:
                    print(json.dumps(row, ensure_ascii=False), file=log, flush=True)
    return rows


def summarise(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """weight set -> instance -> mean metrics over seeds."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    keys = (
        "placed",
        "placed_roomed",
        "roomed",
        "planner_events",
        "planner_placed",
        "repro_exact",
        "repro_overlap",
        "repro_exact_rate",
        "repro_overlap_rate",
        "hard",
        "soft",
        "wall_s",
    )
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["weights"], r["instance"]), []).append(r)
    for (w, inst), rs in groups.items():
        out.setdefault(w, {})[inst] = {k: round(statistics.fmean(float(x[k]) for x in rs), 4) for k in keys}
    return out


def choose(
    summary: Mapping[str, Mapping[str, Mapping[str, float]]],
    reference: str = "defaults",
    tolerance: float = 0.02,
    min_gain: float = 0.01,
) -> str:
    """The weight set with the best reproduction (course exact + exam exact, averaged) among those that
    keep hard 100 and place at least as many room-needing events as ``reference`` minus ``tolerance``
    (2 %: the seed-to-seed spread of a time-limited best-effort Bahar run).  A set replaces
    ``reference`` only if it beats it by more than ``min_gain`` (1 point): smaller gaps are within the
    spread between seeds (Güz week 3, defaults: 89.8 % vs 91.6 %) and are no reason to change the weights
    every run uses."""

    def score(per: Mapping[str, Mapping[str, float]]) -> float:
        rates = [m["repro_exact_rate"] for m in per.values()]
        return statistics.fmean(rates) if rates else 0.0

    ref = summary.get(reference, {})
    best, best_score = reference, (score(ref) + min_gain) if ref else -1.0
    for name, per in summary.items():
        ok = all(m["hard"] >= 100 for m in per.values()) and all(
            m["placed_roomed"] >= ref.get(i, m)["placed_roomed"] * (1 - tolerance) for i, m in per.items()
        )
        if not ok or name == reference:
            continue
        if score(per) > best_score:
            best, best_score = name, score(per)
    return best


def build_instances(
    fixtures: Path,
    *,
    names: Iterable[str] = ("bahar_w3", "guz_w3", "final"),
    definitive_rooms: str = "prefer",
) -> list[Instance]:
    """Import the real fixtures into a throw-away SQLite DB (grid, planning / exam list, room master)
    and build the bridge's input with ``definitive_rooms="prefer"`` (the planner's rooms as hints;
    ``"lock"`` builds the locked reference, ``"ignore"`` the no-hint baseline)."""
    import asyncio
    import os
    import tempfile

    os.environ.setdefault("APP_SECRET", "calibration-secret-calibration-secret-0000")
    os.environ.setdefault("PARSE_ISOLATION", "thread")

    async def _build() -> list[Instance]:
        from sqlalchemy import select

        from app.core import db as dbmod
        from app.importers.exam_list import import_exam_list
        from app.importers.planning_list import import_planning_list
        from app.importers.room_master import import_room_master
        from app.importers.weekly_grid import import_weekly_grid
        from app.models import Base, ExamRequest, MeetingRequest, ScheduleRun, Term
        from app.services.solver_bridge import build_solver_input

        specs = {
            "bahar_w3": ("2026-BAHAR", "COURSE", "WEEK", {"weeks": [3]}),
            "guz_w3": ("2026-GUZ", "COURSE", "WEEK", {"weeks": [3]}),
            "final": ("2026-FINAL", "EXAM", "TERM", {}),
        }
        files = {
            "2026-BAHAR": ("bahar_derslikler_takvimi_2026.xlsx", "bahar_derslik_planlama_listesi_v5.xlsx"),
            "2026-GUZ": ("guz_derslikler_takvimi_2026_2027.xlsx", "guz_derslik_planlama_2026_2027_v2.xlsx"),
            "2026-FINAL": ("final_derslikler_takvimi_2026_v2.xlsx", "final_planlama_listesi_2026_v2.xlsx"),
        }
        out: list[Instance] = []
        with tempfile.TemporaryDirectory() as tmp:
            for name in names:
                term_code, kind, horizon, hp = specs[name]
                eng = dbmod.configure_engine(f"sqlite+aiosqlite:///{tmp}/{name}.db")
                async with eng.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                grid, plan = files[term_code]
                async with dbmod.get_session_factory()() as s:
                    await import_weekly_grid(s, fixtures / grid, term_code, year=2026)
                    if kind == "EXAM":
                        await import_exam_list(s, fixtures / plan, term_code)
                    else:
                        await import_planning_list(s, fixtures / plan, term_code)
                    await import_room_master(s, fixtures / "room_master.csv")
                    await s.commit()
                    tid = (await s.execute(select(Term.id).where(Term.code == term_code))).scalar_one()
                    run = ScheduleRun(
                        term_id=tid,
                        kind=kind,
                        horizon=horizon,
                        horizon_params=hp,
                        params={"definitive_rooms": definitive_rooms},
                    )
                    inp, members = await build_solver_input(s, run)
                    model = ExamRequest if kind == "EXAM" else MeetingRequest
                    rows = {r.id: r for r in (await s.execute(select(model))).scalars()}
                    pool = {r.id for r in inp.rooms}
                    planner: dict[int, frozenset[int]] = {}
                    for e in inp.events:
                        ms = [rows[m] for m in members.get(e.id, [e.id]) if m in rows]
                        rs = frozenset(
                            int(x)
                            for r in ms
                            if r.status == "LOCKED"
                            for x in (r.definitive_room_ids or [])
                            if int(x) in pool
                        )
                        if rs and e.needs_room:
                            planner[e.id] = rs
                    out.append(Instance(name, kind, inp, planner))
                await dbmod.dispose_engine()
        return out

    return asyncio.run(_build())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fixtures", type=Path, default=Path(__file__).resolve().parents[2] / "tests" / "fixtures")
    ap.add_argument("--time-limit", type=float, default=90.0)
    ap.add_argument("--repeat", type=int, default=1, help="seeds 0..repeat-1 per (instance, weight set)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--sets", nargs="*", default=list(WEIGHT_SETS), help=f"weight sets ({', '.join(WEIGHT_SETS)})")
    ap.add_argument("--instances", nargs="*", default=["bahar_w3", "guz_w3", "final"])
    ap.add_argument("--definitive-rooms", default="prefer", choices=("prefer", "lock", "ignore"))
    ap.add_argument("--cache", type=Path, help="pickle of the built instances (reused when present)")
    ap.add_argument("--out", type=Path, help="write rows + summary + choice as JSON")
    args = ap.parse_args(argv)
    # build through the importable module so a cached pickle names app.solver.calibrate.Instance, not
    # __main__.Instance (loadable from tests and scripts too)
    from app.solver import calibrate as module

    if args.cache and args.cache.exists():
        import pickle

        instances = pickle.loads(args.cache.read_bytes())
    else:
        instances = module.build_instances(args.fixtures, names=args.instances, definitive_rooms=args.definitive_rooms)
        if args.cache:
            import pickle

            args.cache.write_bytes(pickle.dumps(instances))
    instances = [i for i in instances if i.name in args.instances]
    sets = {k: WEIGHT_SETS[k] for k in args.sets}
    rows = run_grid(
        instances, sets, time_limit_s=args.time_limit, seeds=range(args.repeat), workers=args.workers, log=sys.stderr
    )
    summary = summarise(rows)
    choice = choose(summary)
    print(f"{'weights':<16} " + " ".join(f"{i.name:>28}" for i in instances))
    for w, per in summary.items():
        cells = []
        for i in instances:
            m = per.get(i.name, {})
            rate = m.get("repro_overlap_rate" if i.kind == "EXAM" else "repro_exact_rate", 0.0)
            cells.append(f"{rate:6.1%} repro {m.get('placed_roomed', 0):5.0f} placed h{m.get('hard', 0):3.0f}")
        print(f"{w:<16} " + " ".join(f"{c:>28}" for c in cells))
    print(f"chosen: {choice}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "time_limit_s": args.time_limit,
                    "repeat": args.repeat,
                    "workers": args.workers,
                    "definitive_rooms": args.definitive_rooms,
                    "rows": rows,
                    "summary": summary,
                    "choice": choice,
                },
                indent=1,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
