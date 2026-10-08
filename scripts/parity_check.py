#!/usr/bin/env python3
"""CRBS superset gate (docs/ROADMAP.md Phase 18): is every classroombookings behaviour and screen proven?

Reads the parity inventory (smartsched/backend/tests/parity/inventory.py), runs every API acceptance test it
names -- the tests under tests/parity (``@pytest.mark.parity("<row>")``) and the existing tests it references --
on the real Bahar 2026 fixtures, maps the UI rows to Playwright test titles in
smartsched/frontend/e2e/{bookings,calendar,admin-gaps}.spec.ts, prints one line per row and writes
docs/testing/crbs-parity-report.md.

Row result: PASS (API tests passed, UI titles present / passed), FAIL (a test failed or was skipped), MISSING
(no test and no declared gap, a stale test reference or a UI title that no longer exists) or GAP (declared in the
inventory with a reason and a proposed fix). Exit status 1 on any FAIL or MISSING (``--strict``: GAP too).

    python3 scripts/parity_check.py                  # run, print, write the report
    python3 scripts/parity_check.py --dry-run        # mapping only (no tests run, no report)
    python3 scripts/parity_check.py --playwright-json results.json   # UI column from a Playwright JSON report

UI titles are checked statically unless ``--playwright-json`` (``npx playwright test --reporter=json``) is given;
pod CI runs the specs themselves in the e2e-real gate.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "smartsched" / "backend"
E2E_DIR = ROOT / "smartsched" / "frontend" / "e2e"
UI_SPECS = ("bookings.spec.ts", "calendar.spec.ts", "admin-gaps.spec.ts")
DEFAULT_REPORT = ROOT / "docs" / "testing" / "crbs-parity-report.md"

PASS, FAIL, MISSING, GAP, NA, SPEC, NOTRUN = "PASS", "FAIL", "MISSING", "GAP", "-", "SPEC", "NOT RUN"


# --------------------------------------------------------------------------------------------------
# inventory and static discovery
# --------------------------------------------------------------------------------------------------


def load_inventory() -> tuple[Any, ...]:
    sys.path.insert(0, str(BACKEND))
    try:
        from tests.parity.inventory import ROWS  # only dataclasses: imports nothing from the app
    finally:
        sys.path.remove(str(BACKEND))
    return ROWS


def _test_functions(path: Path) -> dict[str, ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        n.name: n
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test")
    }


def _marker_rows(fn: ast.AST) -> list[str]:
    rows: list[str] = []
    for dec in getattr(fn, "decorator_list", []):
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "parity"
            and isinstance(dec.func.value, ast.Attribute)
            and dec.func.value.attr == "mark"
        ):
            rows += [a.value for a in dec.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return rows


def marked_tests() -> dict[str, list[str]]:
    """nodeid -> parity rows, from the decorators of tests/parity/test_*.py (static, so --dry-run works)."""
    out: dict[str, list[str]] = {}
    for path in sorted((BACKEND / "tests" / "parity").glob("test_*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        for name, fn in _test_functions(path).items():
            rows = _marker_rows(fn)
            if rows:
                out[f"{rel}::{name}"] = rows
    return out


def existing_nodeids(nodeids: set[str]) -> set[str]:
    ok: set[str] = set()
    cache: dict[str, set[str]] = {}
    for nid in nodeids:
        file, _, name = nid.partition("::")
        if file not in cache:
            p = BACKEND / file
            cache[file] = set(_test_functions(p)) if p.is_file() else set()
        if name in cache[file]:
            ok.add(nid)
    return ok


_TITLE_RX = re.compile(r"""\btest\(\s*(?P<q>["'`])(?P<t>(?:\\.|(?!(?P=q)).)*)(?P=q)\s*,""", re.DOTALL)


def ui_titles() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for spec in UI_SPECS:
        path = E2E_DIR / spec
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        out[spec] = {re.sub(r"\\(.)", r"\1", m.group("t")) for m in _TITLE_RX.finditer(text)}
    return out


def playwright_results(path: Path) -> dict[str, str]:
    """``<spec>::<title>`` -> passed / failed / skipped from a Playwright JSON report."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}

    def walk(suite: dict[str, Any], file: str) -> None:
        file = Path(suite.get("file") or file).name
        for spec in suite.get("specs", []):
            statuses = [r.get("status") for t in spec.get("tests", []) for r in t.get("results", [])]
            final = statuses[-1] if statuses else "skipped"
            out[f"{file}::{spec['title']}"] = "passed" if final in ("passed", "flaky") else final or "skipped"
        for child in suite.get("suites", []):
            walk(child, file)

    for s in data.get("suites", []):
        walk(s, s.get("file", ""))
    return out


# --------------------------------------------------------------------------------------------------
# running the API tests
# --------------------------------------------------------------------------------------------------


def run_pytest(nodeids: list[str], extra: list[str]) -> tuple[int, dict[str, dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="parity-") as tmp:
        out = Path(tmp) / "parity.json"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "tests.parity.plugin",
            "-p",
            "no:cacheprovider",
            f"--parity-json={out}",
            *extra,
            "tests/parity",
            *nodeids,
        ]
        print(
            f"$ cd {BACKEND.relative_to(ROOT)} && python -m pytest -p tests.parity.plugin tests/parity + {len(nodeids)} referenced tests"
        )
        sys.stdout.flush()
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        code = subprocess.call(cmd, cwd=BACKEND, env=env)
        if not out.is_file():
            return code, {}
        data = json.loads(out.read_text(encoding="utf-8"))
    folded: dict[str, dict[str, Any]] = {}
    rank = {"passed": 0, "skipped": 1, "failed": 2}
    for nid, rec in data["tests"].items():
        base = nid.split("[", 1)[0]
        cur = folded.setdefault(base, {"outcome": "passed", "duration": 0.0, "rows": [], "detail": ""})
        cur["duration"] += rec.get("duration", 0.0)
        cur["rows"] = sorted(set(cur["rows"]) | set(rec.get("rows", [])))
        if rank[rec["outcome"]] > rank[cur["outcome"]]:
            cur["outcome"], cur["detail"] = rec["outcome"], rec.get("detail", "")
    return code, folded


# --------------------------------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------------------------------


@dataclass
class Result:
    row: Any
    tests: list[str] = field(default_factory=list)
    api: str = NA
    api_note: str = ""
    ui: str = NA
    ui_note: str = ""
    status: str = PASS


def evaluate(
    rows: tuple[Any, ...],
    marked: dict[str, list[str]],
    found: set[str],
    titles: dict[str, set[str]],
    results: dict[str, dict[str, Any]] | None,
    pw: dict[str, str] | None,
) -> list[Result]:
    by_row: dict[str, list[str]] = defaultdict(list)
    for nid, ids in marked.items():
        for rid in ids:
            by_row[rid].append(nid)
    out = []
    for row in rows:
        r = Result(row, tests=[*row.api, *sorted(by_row.get(row.id, []))])
        stale = [t for t in row.api if t not in found]
        # API column
        if stale:
            r.api, r.api_note = MISSING, "stale reference: " + ", ".join(stale)
        elif not r.tests:
            r.api, r.api_note = (GAP, "no API test (declared gap)") if row.gap else (MISSING, "no API test")
        elif results is None:
            r.api, r.api_note = NOTRUN, f"{len(r.tests)} test(s)"
        else:
            outcomes = {t: results.get(t, {}).get("outcome", "not run") for t in r.tests}
            bad = {t: o for t, o in outcomes.items() if o != "passed"}
            r.api = FAIL if bad else PASS
            r.api_note = f"{len(r.tests)} test(s)" + (
                "; " + ", ".join(f"{t.split('::')[-1]}: {o}" for t, o in bad.items()) if bad else ""
            )
        # UI column
        if row.ui:
            missing = [u for u in row.ui if u.split("::", 1)[1] not in titles.get(u.split("::", 1)[0], set())]
            if missing:
                r.ui, r.ui_note = MISSING, "title not found: " + "; ".join(missing)
            elif pw is not None:
                states = {u: pw.get(u, "not run") for u in row.ui}
                bad_ui = {u: s for u, s in states.items() if s != "passed"}
                r.ui = FAIL if bad_ui else PASS
                r.ui_note = "; ".join(f"{u.split('::', 1)[1][:40]}: {s}" for u, s in bad_ui.items())
            else:
                r.ui = SPEC
                r.ui_note = ", ".join(_ui_ref(u) for u in row.ui)
            if row.ui_gap and r.ui in (PASS, SPEC):
                r.ui_note += f" (partial: {row.ui_gap})"
        elif row.screen:
            r.ui, r.ui_note = (GAP, row.ui_gap) if row.ui_gap else (MISSING, "screen without a Playwright test")
        elif row.ui_gap:
            r.ui, r.ui_note = GAP, row.ui_gap
        # row
        cols = {r.api, r.ui}
        if FAIL in cols:
            r.status = FAIL
        elif MISSING in cols:
            r.status = MISSING
        elif GAP in cols or row.gap or (row.ui_gap and r.ui in (PASS, SPEC)):
            r.status = GAP
        elif NOTRUN in cols:
            r.status = NOTRUN
        else:
            r.status = PASS
        out.append(r)
    return out


def _ui_ref(u: str) -> str:
    spec, title = u.split("::", 1)
    m = re.match(r"(\d+)\.", title)
    return f"{spec.split('.')[0]} #{m.group(1)}" if m else f"{spec.split('.')[0]}: {title[:48]}"


# --------------------------------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------------------------------


def print_table(res: list[Result]) -> None:
    w = max(len(r.row.id) for r in res)
    print(f"\n{'ROW':<{w}}  {'API':<8} {'UI':<8} {'RESULT':<8} BEHAVIOUR")
    print("-" * (w + 100))
    for r in res:
        line = f"{r.row.id:<{w}}  {r.api:<8} {r.ui:<8} {r.status:<8} {r.row.behaviour[:72]}"
        print(line)
        if r.status in (FAIL, MISSING):
            for note in (r.api_note if r.api in (FAIL, MISSING) else "", r.ui_note if r.ui in (FAIL, MISSING) else ""):
                if note:
                    print(f"{'':<{w}}  -> {note}")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "?"


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def write_report(path: Path, res: list[Result], meta: dict[str, Any], details: dict[str, str]) -> None:
    c = Counter(r.status for r in res)
    kinds = Counter("screen" if r.row.screen else "behaviour" for r in res)
    diffs = [r for r in res if r.row.difference]
    gaps = [r for r in res if r.status == GAP]
    bad = [r for r in res if r.status in (FAIL, MISSING)]
    lines = [
        "# CRBS superset gate — measured result",
        "",
        (
            f"Generated by `python3 scripts/parity_check.py` on {meta['when']} (commit `{meta['commit']}`"
            f"{', uncommitted changes' if meta['dirty'] else ''}). Inventory: "
            "`smartsched/backend/tests/parity/inventory.py` "
            f"({len(res)} rows: {kinds['behaviour']} behaviour / audit rows, {kinds['screen']} CRBS screens)."
        ),
        "",
        f"**Result: {'PASS' if not bad else 'FAIL'}** — PASS {c[PASS]} · GAP {c[GAP]} (declared, with reason) · "
        f"FAIL {c[FAIL]} · MISSING {c[MISSING]}"
        + (f" · NOT RUN {c[NOTRUN]}" if c[NOTRUN] else "")
        + f". API tests run: {meta['tests_run']} ({meta['tests_passed']} passed) in {meta['seconds']:.0f} s on the real "
        "Bahar 2026 fixtures (`tests/crbs_env`).",
        "",
        "Columns: **API** = the acceptance tests of the row (existing `tests/test_crbs_*` tests referenced by node id, "
        "and `tests/parity/*` tests marked `@pytest.mark.parity`); **UI** = Playwright tests in "
        "`smartsched/frontend/e2e/bookings.spec.ts` / `calendar.spec.ts` by title ("
        + (
            "results from the Playwright JSON report given"
            if meta["playwright"]
            else "`SPEC` = the title exists; the specs run against the real backend in the pod CI `e2e-real` gate"
        )
        + "); `-` = no screen involved. **GAP** rows are not hidden: each names what is missing and the proposed fix.",
        "",
        "| Row | Behaviour / screen | CRBS | API | UI | Result | Deliberate difference | Gap / note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in res:
        note = r.row.gap or (r.row.ui_gap if r.ui in (GAP, PASS, SPEC) and r.row.ui_gap else "")
        if r.status in (FAIL, MISSING):
            note = "; ".join(x for x in (r.api_note if r.api in (FAIL, MISSING) else "", r.ui_note) if x)
        ui = r.ui if r.ui != SPEC else "SPEC " + ", ".join(_ui_ref(u) for u in r.row.ui)
        lines.append(
            f"| {r.row.id} | {_md(r.row.behaviour)} | {_md(r.row.crbs)} | {r.api} ({len(r.tests)}) | {_md(ui)} | "
            f"**{r.status}** | {_md(r.row.difference)} | {_md(note)} |"
        )
    lines += ["", "## Failing or uncovered rows", ""]
    if not bad:
        lines.append("None.")
    for r in bad:
        lines.append(f"- **{r.row.id}** {r.row.behaviour}: {r.api_note} {r.ui_note}".rstrip())
        for t in r.tests:
            if t in details:
                lines.append(f"  - `{t}`: `{_md(details[t][-300:])}`")
    lines += ["", "## Declared gaps (owner, reason, proposed fix)", ""]
    for r in gaps:
        text = r.row.gap or r.row.ui_gap or r.api_note
        lines.append(f"- **{r.row.id}** {r.row.behaviour} — {text}")
    lines += ["", "## Deliberate differences asserted by the tests", ""]
    for r in diffs:
        lines.append(f"- **{r.row.id}** {r.row.behaviour} — {r.row.difference}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="markdown report path")
    ap.add_argument("--no-report", action="store_true", help="do not write the report")
    ap.add_argument("--json", type=Path, help="also write the per-row result as JSON")
    ap.add_argument("--dry-run", action="store_true", help="check the mapping only; run no tests, write no report")
    ap.add_argument("--strict", action="store_true", help="declared gaps fail the gate too")
    ap.add_argument("--playwright-json", type=Path, help="Playwright JSON report for the UI column")
    ap.add_argument("--pytest-arg", action="append", default=[], help="extra pytest argument (repeatable)")
    args = ap.parse_args(argv)

    rows = load_inventory()
    errors: list[str] = []
    ids = [r.id for r in rows]
    errors += [f"duplicate row id {i}" for i, n in Counter(ids).items() if n > 1]
    marked = marked_tests()
    known = set(ids)
    errors += [f"{nid} marks unknown row {rid}" for nid, rids in marked.items() for rid in rids if rid not in known]
    referenced = {t for r in rows for t in r.api}
    found = existing_nodeids(referenced)
    titles = ui_titles()
    pw = playwright_results(args.playwright_json) if args.playwright_json else None

    results: dict[str, dict[str, Any]] | None = None
    started = dt.datetime.now(dt.UTC)
    code = 0
    if not args.dry_run:
        code, results = run_pytest(sorted(found), args.pytest_arg)
        if not results:
            errors.append(f"pytest produced no results (exit status {code})")
            results = {}
        unexpected = sorted(
            t for t, rec in results.items() if rec["outcome"] == "failed" and t not in referenced and t not in marked
        )
        errors += [f"unmapped test failed: {t}" for t in unexpected]
    seconds = (dt.datetime.now(dt.UTC) - started).total_seconds()
    res = evaluate(rows, marked, found, titles, results, pw)
    print_table(res)

    c = Counter(r.status for r in res)
    bad = c[FAIL] + c[MISSING] + (c[GAP] if args.strict else 0)
    print(
        f"\n{len(res)} rows: PASS {c[PASS]}  GAP {c[GAP]}  FAIL {c[FAIL]}  MISSING {c[MISSING]}"
        + (f"  NOT RUN {c[NOTRUN]}" if c[NOTRUN] else "")
    )
    for e in errors:
        print(f"ERROR: {e}")
    if not args.dry_run and not args.no_report:
        run = results or {}
        meta = {
            "when": started.strftime("%Y-%m-%d %H:%M UTC"),
            "commit": _git("rev-parse", "--short", "HEAD"),
            "dirty": bool(_git("status", "--porcelain")),
            "tests_run": len(run),
            "tests_passed": sum(1 for x in run.values() if x["outcome"] == "passed"),
            "seconds": seconds,
            "playwright": pw is not None,
        }
        details = {t: rec.get("detail", "") for t, rec in run.items() if rec["outcome"] != "passed"}
        write_report(args.report, res, meta, details)
        print(f"report: {args.report.relative_to(ROOT) if args.report.is_relative_to(ROOT) else args.report}")
    if args.json:
        args.json.write_text(
            json.dumps(
                [{"id": r.row.id, "api": r.api, "ui": r.ui, "status": r.status, "tests": r.tests} for r in res],
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return 1 if (bad or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
