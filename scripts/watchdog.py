#!/usr/bin/env python3
"""Agent-continuity watchdog for SmartSched (see docs/AGENTS.md).

Reads the append-only ledger docs/PROGRESS.md, reports agents whose last entry is older than
--stale-minutes and whose status is not terminal, and optionally runs the quality gates.

Usage:
    python scripts/watchdog.py                # report
    python scripts/watchdog.py --check        # also run `make check` in smartsched/backend and frontend
    python scripts/watchdog.py --json         # machine-readable output (CI)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "PROGRESS.md"
# A row is terminal only when the status *starts* with a terminal word (e.g. "DONE: …"), or mentions a
# hand-off; "importers done" mid-way is a milestone, not completion.
TERMINAL = re.compile(r"^\s*(done|completed|finished)\b|\bhand(ed)?[ -]off\b", re.I)
ROW = re.compile(r"^\|\s*(?P<ts>[^|]+?)\s*\|\s*(?P<agent>[^|]+?)\s*\|\s*(?P<phase>[^|]+?)\s*\|\s*(?P<status>[^|]+?)\s*\|\s*(?P<next>[^|]*?)\s*\|\s*$")


def parse_ledger() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not LEDGER.exists():
        return rows
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m or m.group("ts").lower().startswith(("time", "---")):
            continue
        rows.append(m.groupdict())
    return rows


def parse_ts(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def latest_per_agent(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        latest[row["agent"]] = row  # ledger is append-only, so the last row wins
    return latest


def run_checks() -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for sub in ("smartsched/backend", "smartsched/frontend"):
        path = ROOT / sub
        if not (path / "Makefile").exists() and not (path / "package.json").exists():
            continue
        cmd = ["make", "check"] if (path / "Makefile").exists() else ["npm", "run", "check"]
        proc = subprocess.run(cmd, cwd=path, capture_output=True, text=True)
        results[sub] = {"ok": proc.returncode == 0, "tail": (proc.stdout + proc.stderr)[-2000:]}
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-minutes", type=int, default=45)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    rows = parse_ledger()
    report: dict[str, object] = {"ledger_rows": len(rows), "stale": [], "active": [], "done": []}
    for agent, row in latest_per_agent(rows).items():
        ts = parse_ts(row["ts"])
        age = (now - ts) if ts else None
        entry = {"agent": agent, "phase": row["phase"], "status": row["status"], "next": row["next"],
                 "age_minutes": round(age.total_seconds() / 60) if age else None}
        if TERMINAL.search(row["status"]):
            report["done"].append(entry)  # type: ignore[union-attr]
        elif age is not None and age > timedelta(minutes=args.stale_minutes):
            report["stale"].append(entry)  # type: ignore[union-attr]
        else:
            report["active"].append(entry)  # type: ignore[union-attr]
    if args.check:
        report["checks"] = run_checks()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for key in ("active", "stale", "done"):
            print(f"== {key} ({len(report[key])})")  # type: ignore[arg-type]
            for e in report[key]:  # type: ignore[union-attr]
                print(f"  - {e['agent']:<18} phase {e['phase']:<4} {e['age_minutes']!s:>5} min  {e['status'][:80]}")
                if e["next"]:
                    print(f"      next: {e['next'][:100]}")
        if args.check:
            for sub, res in report["checks"].items():  # type: ignore[union-attr]
                print(f"== check {sub}: {'OK' if res['ok'] else 'FAIL'}")
                if not res["ok"]:
                    print(res["tail"])
    failing = bool(report["stale"]) or (args.check and any(not r["ok"] for r in report.get("checks", {}).values()))  # type: ignore[union-attr]
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
