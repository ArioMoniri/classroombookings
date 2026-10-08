"""Self-checks of the CRBS superset gate: the inventory is complete and consistent (every referenced test and
Playwright title exists, every row is covered or declares its gap), and ``scripts/parity_check.py`` turns a
failing or missing test into a failing row and a non-zero exit status."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.parity.inventory import BY_ID, ROWS, Row

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "scripts" / "parity_check.py"
BACKEND = REPO / "smartsched" / "backend"

pytestmark = pytest.mark.skipif(not SCRIPT.is_file(), reason="needs the repository checkout (scripts/)")


def _checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("parity_check", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["parity_check"] = mod
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no scripts/__pycache__ in the checkout
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


def test_every_row_is_covered_or_declares_its_gap():
    pc = _checker()
    marked = pc.marked_tests()
    referenced = {t for r in ROWS for t in r.api}
    found = pc.existing_nodeids(referenced)
    assert referenced - found == set(), "stale test references in tests/parity/inventory.py"
    unknown = {(nid, rid) for nid, rids in marked.items() for rid in rids if rid not in BY_ID}
    assert unknown == set()
    assert len(BY_ID) == len(ROWS), "duplicate row ids"
    titles = pc.ui_titles()
    if not any(titles.values()):
        pytest.skip("frontend e2e specs not in this checkout")
    res = pc.evaluate(ROWS, marked, found, titles, None, None)
    assert [(r.row.id, r.api_note, r.ui_note) for r in res if r.status == pc.MISSING] == []
    # every declared gap says why, and every screen row has a UI test or a UI gap
    for r in ROWS:
        assert r.gap == "" or len(r.gap) > 40, r.id
        if r.screen:
            assert r.ui or r.ui_gap, r.id
    # each new acceptance test in tests/parity names at least one row
    for path in sorted(Path(__file__).parent.glob("test_parity_*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        for name in pc._test_functions(path):
            assert f"{rel}::{name}" in marked, f"{name} has no @pytest.mark.parity"


def test_a_failing_or_missing_test_fails_its_row():
    pc = _checker()
    rows = (
        Row("B-T-01", "T", "covered by a passing test", "x", ("tests/a.py::test_ok",)),
        Row("B-T-02", "T", "covered by a failing test", "x", ("tests/a.py::test_bad",)),
        Row("B-T-03", "T", "nothing at all", "x"),
        Row("B-T-04", "T", "declared gap", "x", gap="later part: needs a real CRBS install on the pod"),
        Row("S-T-05", "T", "screen without e2e", "x", ("tests/a.py::test_ok",), screen=True),
        Row("S-T-06", "T", "screen, title gone", "x", ("tests/a.py::test_ok",), ui=("bookings.spec.ts::gone",)),
    )
    results = {
        "tests/a.py::test_ok": {"outcome": "passed"},
        "tests/a.py::test_bad": {"outcome": "failed"},
    }
    found = set(results)
    res = {r.row.id: r for r in pc.evaluate(rows, {}, found, {"bookings.spec.ts": {"x"}}, results, None)}
    assert res["B-T-01"].status == pc.PASS
    assert res["B-T-02"].status == pc.FAIL and "test_bad: failed" in res["B-T-02"].api_note
    assert res["B-T-03"].status == pc.MISSING
    assert res["B-T-04"].status == pc.GAP
    assert res["S-T-05"].status == pc.MISSING and res["S-T-05"].ui == pc.MISSING
    assert res["S-T-06"].status == pc.MISSING and "title not found" in res["S-T-06"].ui_note
    # a stale reference is MISSING, not silently passing
    stale = pc.evaluate(rows[:1], {}, set(), {}, results, None)[0]
    assert stale.status == pc.MISSING and "stale reference" in stale.api_note


def test_playwright_json_report_drives_the_ui_column(tmp_path):
    pc = _checker()
    report = {
        "suites": [
            {
                "file": "bookings.spec.ts",
                "specs": [
                    {"title": "3. ok", "tests": [{"results": [{"status": "failed"}, {"status": "passed"}]}]},
                    {"title": "4. bad", "tests": [{"results": [{"status": "failed"}]}]},
                ],
                "suites": [],
            }
        ]
    }
    path = tmp_path / "pw.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    pw = pc.playwright_results(path)
    assert pw == {"bookings.spec.ts::3. ok": "passed", "bookings.spec.ts::4. bad": "failed"}
    rows = (
        Row("B-U-01", "U", "ui ok", "x", ("tests/a.py::test_ok",), ui=("bookings.spec.ts::3. ok",)),
        Row("B-U-02", "U", "ui bad", "x", ("tests/a.py::test_ok",), ui=("bookings.spec.ts::4. bad",)),
    )
    titles = {"bookings.spec.ts": {"3. ok", "4. bad"}}
    res = pc.evaluate(rows, {}, {"tests/a.py::test_ok"}, titles, {"tests/a.py::test_ok": {"outcome": "passed"}}, pw)
    assert [r.status for r in res] == [pc.PASS, pc.FAIL]


def test_the_result_plugin_records_outcomes_and_markers(tmp_path):
    """The plugin pytest loads for the gate (``-p tests.parity.plugin``), on a throw-away test module."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.parity('B-X-01')\n"
        "def test_ok():\n    assert 'İ'.lower() != 'i'\n\n"
        "@pytest.mark.parity('B-X-02', 'S-X-03')\n"
        "@pytest.mark.parametrize('n', [1, 2])\n"
        "def test_param(n):\n    assert n == 1\n",
        encoding="utf-8",
    )
    out = tmp_path / "parity.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "tests.parity.plugin",
            "-p",
            "no:cacheprovider",
            f"--rootdir={tmp_path}",
            "-c",
            str(tmp_path / "pytest.ini"),
            f"--parity-json={out}",
            str(tmp_path / "test_sample.py"),
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(BACKEND), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=120,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    tests = {k.split("::", 1)[1]: v for k, v in data["tests"].items()}
    assert tests["test_ok"]["outcome"] == "passed" and tests["test_ok"]["rows"] == ["B-X-01"]
    assert tests["test_param[1]"]["outcome"] == "passed" and tests["test_param[2]"]["outcome"] == "failed"
    assert (
        tests["test_param[2]"]["rows"] == ["B-X-02", "S-X-03"] and "assert 2 == 1" in tests["test_param[2]"]["detail"]
    )
