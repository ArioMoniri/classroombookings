"""Parity gate fidelity (review P19-Q2 / D18): the pod parity gate always judges the UI rows by the e2e-real
Playwright JSON report, so a skipped, missing or not-run mapped spec fails the row, and a missing report fails
the gate instead of silently falling back to "the title exists"."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from podfakes import POD_CI, REPO


def load_parity() -> ModuleType:
    spec = importlib.util.spec_from_file_location("parity_check", REPO / "scripts/parity_check.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["parity_check"] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


pc = load_parity()


@dataclass(frozen=True)
class Row:  # the fields evaluate() reads from tests/parity/inventory.Row
    id: str
    api: tuple[str, ...] = ()
    ui: tuple[str, ...] = ()
    gap: str = ""
    ui_gap: str = ""
    screen: bool = False


API = "tests/parity/test_x.py::test_x"
API_OK = {API: {"outcome": "passed"}}


def report(tmp_path: Path, tests: dict[str, str], file: str = "bookings.spec.ts") -> Path:
    specs = [{"title": t, "tests": [{"results": [{"status": s}] if s != "none" else []}]} for t, s in tests.items()]
    p = tmp_path / "playwright-report.json"
    p.write_text(json.dumps({"suites": [{"file": file, "specs": [], "suites": [{"title": "d", "specs": specs}]}]}))
    return p


def test_reserve_spec_is_a_ui_spec() -> None:
    assert "reserve.spec.ts" in pc.UI_SPECS
    assert set(pc.UI_SPECS) >= {"bookings.spec.ts", "calendar.spec.ts", "admin-gaps.spec.ts", "reserve.spec.ts"}


@pytest.mark.parametrize(("state", "expected"), [("passed", "PASS"), ("skipped", "FAIL"), ("failed", "FAIL"),
                                                  ("none", "FAIL")])
def test_ui_row_follows_the_playwright_result(tmp_path: Path, state: str, expected: str) -> None:
    row = Row("B-X-01", api=(API,), ui=("bookings.spec.ts::books a slot",))
    pw = pc.playwright_results(report(tmp_path, {"books a slot": state}))
    (r,) = pc.evaluate((row,), {}, {API}, {"bookings.spec.ts": {"books a slot"}}, API_OK, pw)
    assert r.ui == expected and r.status == expected


def test_mapped_title_absent_from_the_report_fails(tmp_path: Path) -> None:
    """Title still in the source but not run (testMatch excludes the file, or a describe.skip)."""
    row = Row("B-X-02", api=(API,), ui=("reserve.spec.ts::reserves a free slot",))
    pw = pc.playwright_results(report(tmp_path, {"something else": "passed"}))
    (r,) = pc.evaluate((row,), {}, {API}, {"reserve.spec.ts": {"reserves a free slot"}}, API_OK, pw)
    assert r.ui == "FAIL" and "not run" in r.ui_note


def test_missing_report_fails_every_ui_row_without_crashing(tmp_path: Path,
                                                            capsys: pytest.CaptureFixture[str]) -> None:
    assert pc.playwright_results(tmp_path / "absent.json") == {}
    rc = pc.main(["--dry-run", "--playwright-json", str(tmp_path / "absent.json")])
    assert rc == 1  # UI rows cannot be proven without the e2e-real report
    assert "ERROR: no Playwright report at" in capsys.readouterr().out


FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
"""


def test_parity_gate_always_passes_the_e2e_report(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "docker.log"),
           "WS": str(tmp_path / "ws"), "CACHE_DIR": str(tmp_path / "c"), "RUN_TAG": "1-a", "CI_UID": "1",
           "CI_GID": "1", "GATES_DIR": str(POD_CI / "gates"), "PY_IMAGE": "py:x"}
    r = subprocess.run(["bash", str(POD_CI / "gates/parity.sh")], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    script = (tmp_path / "docker.log").read_text()
    assert "--playwright-json /w/playwright-report.json" in script
    assert "[ -f /w/playwright-report.json ] &&" not in script  # no silent fallback to titles only


def test_report_names_the_tested_commit_without_a_git_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pod exports the tree with `git archive` (no .git): the gate passes the commit instead of `?`."""
    monkeypatch.setenv("PARITY_COMMIT", "e48ee08")
    assert pc.commit_info() == ("e48ee08", False)
    monkeypatch.delenv("PARITY_COMMIT")
    monkeypatch.setattr(pc, "_git", lambda *a: "?")
    assert pc.commit_info() == ("?", False)  # unknown, not "uncommitted changes"
    assert 'PARITY_COMMIT="${RUN_TAG#*-}"' in (POD_CI / "gates/parity.sh").read_text()
