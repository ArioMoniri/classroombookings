"""Command line: ``python -m app.cli import planning-list <file> --term 2026-BAHAR`` etc."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

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
        elif args.what == "room-master":
            from app.importers.room_master import import_room_master

            rep = await import_room_master(session, args.file)
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
            # same shape as POST /runs normalises to: the UI reads horizon_params.weeks
            horizon_params={"week": args.week, "weeks": [args.week]} if args.week else {},
            params={"time_limit_s": args.time_limit, "solver": args.solver},
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


async def _crbs_upgrade(args: argparse.Namespace) -> int:
    """P18-LEGACY: dry run (default) or ``--commit --fingerprint <dry run's>``; prints the JSON report."""
    from app.services import crbs_upgrade as up

    if bool(args.files) == bool(args.dsn):
        print("give SQL dump files or --dsn (one of them)", file=sys.stderr)
        return 2
    if args.commit and not args.fingerprint:
        print("--commit needs --fingerprint from the dry run", file=sys.stderr)
        return 2
    configure_engine(args.database_url or get_settings().database_url)
    await create_all()
    source = args.dsn or [str(Path(f)) for f in args.files]
    label = args.dsn.rsplit("@", 1)[-1] if args.dsn else ", ".join(Path(f).name for f in args.files)
    try:
        if args.commit:
            rep = await up.commit(source, expect=args.fingerprint, filename=label)
        else:
            rep = await up.dry_run(source, filename=label)
    except up.SourceChanged as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False, default=str))
    return 0


async def _learning_refresh(args: argparse.Namespace) -> int:
    """P19-L2/L3: extract learning evidence (idempotent) and recompute priors for every term (or ``--term``)."""
    from sqlalchemy import select

    from app.models import Term
    from app.services import learning

    configure_engine(args.database_url or get_settings().database_url)
    await create_all()
    async with get_session_factory()() as session:
        q = select(Term.id, Term.code).order_by(Term.id)
        if args.term:
            q = q.where(Term.code == args.term)
        terms = (await session.execute(q)).all()
        if args.term and not terms:
            print(f"unknown term {args.term}", file=sys.stderr)
            return 2
        extract = (await learning.refresh(session))["extract"]
        priors = {code: (await learning.refresh(session, term_id)).get("priors") for term_id, code in terms}
        await session.commit()
    print(json.dumps({"extract": extract, "terms": priors}, indent=2, ensure_ascii=False, default=str))
    return 0


class SettingError(Exception):
    """A ``set-setting`` key or value that ``PUT /org/settings`` would refuse (the message never holds the value)."""


#: groups whose keys ``set-setting`` accepts with their prefix (``bookings.approval_mode``, ``org.name``)
_SETTING_GROUPS = ("org", "bookings")


def _setting_field(key: str) -> tuple[str, str]:
    """``(field of OrgSettingsIn, stored key)`` for a ``set-setting`` key; :class:`SettingError` when the key is not
    one ``PUT /org/settings`` writes (the whitelist: its body fields that map to one stored setting)."""
    from app.importers import normalize as n
    from app.schemas.crbs import OrgSettingsIn
    from app.services.bookings_settings import BOOKINGS_SPECS, ORG_SPECS

    # ASCII keys: NBSP / spaces from a pasted runbook go, the case is folded (no Turkish letters in keys)
    text = (n.clean_text(key) or "").replace(" ", "").lower()
    group, _, name = text.rpartition(".")
    stored = {
        **{k: f"org.{k}" for k in ORG_SPECS},
        **{k: f"bookings.{k}" for k in BOOKINGS_SPECS},
        "timezone": "timezone",
    }
    ok = name in OrgSettingsIn.model_fields and name in stored and (not group or stored[name].startswith(f"{group}."))
    if not ok or (group and group not in _SETTING_GROUPS):
        allowed = sorted(stored[f] for f in OrgSettingsIn.model_fields if f in stored)
        raise SettingError(f"unknown setting {text or key!r}; set-setting accepts: {', '.join(allowed)}")
    return name, stored[name]


async def apply_setting(session: Any, key: str, value: str) -> dict[str, Any]:
    """Write one organisation / bookings setting exactly as ``PUT /org/settings`` does (its body model and handler:
    the same whitelist, coercion, Turkish text clean-up and cross-field checks) and commit. Returns
    ``{"key", "value", "changed"}``; :class:`SettingError` for an unknown key or a refused value."""
    from fastapi import HTTPException
    from pydantic import ValidationError

    from app.api.v1.org import _settings_out, put_org_settings
    from app.importers import normalize as n
    from app.schemas.crbs import OrgSettingsIn

    field, stored = _setting_field(key)
    raw = n.clean_text(value) or ""
    body = None
    errors: list[str] = []
    candidates: list[Any] = [raw]
    try:
        candidates.append(json.loads(raw))  # true / 12 / ["tr", "en"] for non-text fields
    except ValueError:
        pass
    for cand in candidates:
        try:
            body = OrgSettingsIn.model_validate({field: cand})
            break
        except ValidationError as exc:
            errors.extend(str(e.get("msg")) for e in exc.errors(include_input=False))
    if body is None or getattr(body, field) is None:
        why = errors[0] if errors else "a value is required"
        raise SettingError(f"{stored}: {why}")
    before = (await _settings_out(session)).get(field)
    try:
        out = await put_org_settings(body, session, None)  # type: ignore[arg-type]  # CLI: no request user
    except HTTPException as exc:
        await session.rollback()
        raise SettingError(f"{stored}: {exc.detail}") from exc
    after = out.get(field)
    return {"key": stored, "value": after, "changed": after != before}


async def _set_setting(args: argparse.Namespace) -> int:
    """``set-setting <key> <value>``: one whitelisted setting through the ``PUT /org/settings`` validation."""
    configure_engine(args.database_url or get_settings().database_url)
    await create_all()
    async with get_session_factory()() as session:
        try:
            out = await apply_setting(session, args.key, args.value)
        except SettingError as exc:
            print(f"set-setting: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0


def _backtest(args: argparse.Namespace) -> int:
    """``backtest adaptive [--json]``: B1-B7 on the real fixture workbooks; exit 1 when a backtest misses its target."""
    from app.services import backtest

    results = backtest.run_all()
    if not args.skip_db:
        results.insert(3, asyncio.run(backtest.b4_standalone()))
    if args.json:
        print(json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2, default=str))
    else:
        print(backtest.table(results))
    return 0 if all(r.passed for r in results) else 1


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
    rm = imp_sub.add_parser(
        "room-master", help="room master CSV: code,capacity,exam_capacity,tags,building,floor,bookable[,notes]"
    )
    rm.add_argument("file")
    cr = imp_sub.add_parser("crbs")
    cr.add_argument("files", nargs="*", help="SQL dump files (structure.sql data.sql …)")
    cr.add_argument("--dsn", default=None, help="mysql://user:pass@host/db")
    sv = sub.add_parser("solve", help="create and execute a schedule run")
    sv.add_argument("--term", required=True)
    sv.add_argument("--kind", default="COURSE", choices=["COURSE", "EXAM"])
    sv.add_argument("--horizon", default="TERM", choices=["WEEK", "MONTH", "TERM"])
    sv.add_argument("--week", type=int, default=None, help="week number for --horizon WEEK (default: week 1)")
    sv.add_argument("--time-limit", type=float, default=60.0)
    sv.add_argument("--label", default=None)
    sv.add_argument("--solver", default="auto", choices=["auto", "cpsat"])
    sub.add_parser("seed-admin", help="create the admin user from ADMIN_EMAIL/ADMIN_PASSWORD")
    upg = sub.add_parser(
        "crbs-upgrade", help="upgrade a legacy classroombookings database: dry-run diff, then --commit --fingerprint"
    )
    upg.add_argument("files", nargs="*", help="mysqldump / CRBS install SQL files")
    upg.add_argument("--dsn", default=None, help="mysql://user:pass@host/db (opened read-only)")
    upg.add_argument("--commit", action="store_true", help="import for real (needs --fingerprint)")
    upg.add_argument("--fingerprint", default=None, help="the fingerprint printed by the dry run")
    lr = sub.add_parser("learning-refresh", help="extract learning evidence and recompute suggestions (all terms)")
    lr.add_argument("--term", default=None, help="only this term code, e.g. 2026-BAHAR")
    ss = sub.add_parser(
        "set-setting",
        help="write one organisation setting through the PUT /org/settings validation, e.g. bookings.approval_mode all",
    )
    ss.add_argument("key", help="e.g. bookings.approval_mode, org.name, timezone")
    ss.add_argument("value", help="text, true/false, a number or JSON (languages)")
    bt = sub.add_parser("backtest", help="backtests of the adaptive-scheduling models on the fixture workbooks")
    bt.add_argument(
        "suite", choices=["adaptive"], help="adaptive: B1-B7 (docs/research/2026-10-17-adaptive-scheduling.md)"
    )
    bt.add_argument("--json", action="store_true", help="print the results as JSON")
    bt.add_argument("--skip-db", action="store_true", help="leave out B4 (it builds a temporary database, ~2 min)")
    args = p.parse_args(argv)
    if args.cmd == "backtest":
        return _backtest(args)
    if args.cmd == "set-setting":
        return asyncio.run(_set_setting(args))
    if args.cmd == "learning-refresh":
        return asyncio.run(_learning_refresh(args))
    if args.cmd == "import":
        return asyncio.run(_run_import(args))
    if args.cmd == "solve":
        return asyncio.run(_run_solve(args))
    if args.cmd == "seed-admin":
        return asyncio.run(_seed(args))
    if args.cmd == "crbs-upgrade":
        return asyncio.run(_crbs_upgrade(args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
