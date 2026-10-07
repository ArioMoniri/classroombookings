"""Command line: ``python -m app.cli import planning-list <file> --term 2026-BAHAR`` etc."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.db import configure_engine, create_all, get_session_factory


async def _run_import(args: argparse.Namespace) -> int:
    configure_engine(args.database_url or get_settings().database_url)
    await create_all()
    async with get_session_factory()() as session:
        if args.what == "planning-list":
            from app.importers.planning_list import import_planning_list

            rep = await import_planning_list(session, args.file, args.term, week_count=args.week_count)
        elif args.what == "exam-list":
            from app.importers.exam_list import import_exam_list

            rep = await import_exam_list(session, args.file, args.term)
        elif args.what == "weekly-grid":
            from app.importers.weekly_grid import import_weekly_grid

            rep = await import_weekly_grid(session, args.file, args.term, year=args.year, term_kind=args.term_kind)
        elif args.what == "crbs":
            from app.importers.crbs_legacy import import_crbs

            source = args.dsn if args.dsn else [Path(f) for f in args.files]
            rep = await import_crbs(session, source)
        else:
            print(f"unknown importer {args.what}", file=sys.stderr)
            return 2
    d = rep.to_dict()
    print(
        json.dumps(
            {k: v for k, v in d.items() if k not in {"warnings", "rows_skipped"}},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    if d["warnings_count"]:
        print(f"\n{d['warnings_count']} warnings; top:")
        for w in d["warning_summary"]:
            print(f"  {w['count']:5d}  {w['text']}")
    if d["rows_skipped_count"]:
        print(f"\n{d['rows_skipped_count']} rows skipped: {d['skip_reasons']}")
    return 0


async def _run_solve(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.models import ScheduleRun, Term
    from app.services.solver_bridge import run_schedule

    configure_engine(args.database_url or get_settings().database_url)
    await create_all()
    factory = get_session_factory()
    async with factory() as session:
        term = (await session.execute(select(Term).where(Term.code == args.term))).scalar_one_or_none()
        if term is None:
            print(f"term {args.term} not found", file=sys.stderr)
            return 2
        run = ScheduleRun(
            term_id=term.id,
            kind=args.kind,
            horizon=args.horizon,
            params={"time_limit_s": args.time_limit},
            label=args.label,
        )
        session.add(run)
        await session.commit()
        run_id = run.id
    result = await run_schedule(factory, run_id, lambda ph, pct: print(f"  {ph:12s} {pct:3d}%", file=sys.stderr))
    print(json.dumps({"run_id": run_id, **result}, indent=2))
    return 0


async def _seed(args: argparse.Namespace) -> int:
    from app.services.seed import seed_admin

    configure_engine(args.database_url or get_settings().database_url)
    await create_all()
    async with get_session_factory()() as session:
        user = await seed_admin(session)
    print("seeded" if user else "users already exist or ADMIN_EMAIL/ADMIN_PASSWORD unset")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="smartsched", description="SmartSched backend CLI")
    p.add_argument("--database-url", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="import a workbook or the CRBS database")
    imp_sub = imp.add_subparsers(dest="what", required=True)
    for name in ("planning-list", "exam-list", "weekly-grid"):
        sp = imp_sub.add_parser(name)
        sp.add_argument("file")
        sp.add_argument("--term", required=True, help="term code, e.g. 2026-BAHAR")
        if name == "planning-list":
            sp.add_argument("--week-count", type=int, default=14)
        if name == "weekly-grid":
            sp.add_argument("--year", type=int, required=True)
            sp.add_argument("--term-kind", default=None, help="REGULAR|FINAL|BUT (default: inferred)")
    cr = imp_sub.add_parser("crbs")
    cr.add_argument("files", nargs="*", help="SQL dump files (structure.sql data.sql …)")
    cr.add_argument("--dsn", default=None, help="mysql://user:pass@host/db")
    sv = sub.add_parser("solve", help="create and execute a schedule run")
    sv.add_argument("--term", required=True)
    sv.add_argument("--kind", default="COURSE", choices=["COURSE", "EXAM"])
    sv.add_argument("--horizon", default="TERM", choices=["WEEK", "MONTH", "TERM"])
    sv.add_argument("--time-limit", type=float, default=60.0)
    sv.add_argument("--label", default=None)
    sv.add_argument("--solver", default="auto", choices=["auto", "cpsat", "stub"])
    sub.add_parser("seed-admin", help="create the admin user from ADMIN_EMAIL/ADMIN_PASSWORD")
    args = p.parse_args(argv)
    if args.cmd == "import":
        return asyncio.run(_run_import(args))
    if args.cmd == "solve":
        return asyncio.run(_run_solve(args))
    if args.cmd == "seed-admin":
        return asyncio.run(_seed(args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
