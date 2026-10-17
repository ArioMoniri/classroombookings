"""Dependency audit report steps of the validate gate (security follow-up wave3-sec2, docs/SECURITY.md §6 / F13).

``gates/audit-report.sh`` runs ``pip-audit --no-deps -r requirements.lock`` (python image) and ``npm audit
--omit=dev`` (Playwright image, lockfile only). Both print; neither can fail the gate, also when a tool or the
advisory database is unreachable. ``validate.sh`` calls it and keeps its own exit code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from podfakes import POD_CI
from test_e2e_stack import gate_env

GATES = POD_CI / "gates"


def _run(tmp_path: Path, fail: bool) -> subprocess.CompletedProcess[str]:
    env = gate_env(tmp_path)
    if fail:  # every docker call fails (advisories found, no network, missing image ...)
        (tmp_path / "bin" / "docker").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FAKE_LOG"\nexit 1\n')
    (tmp_path / "ws" / "src").mkdir(parents=True, exist_ok=True)
    return subprocess.run(["bash", str(GATES / "audit-report.sh")], env=env, capture_output=True, text=True, timeout=60)


def test_audit_steps_run_both_audits_and_never_fail(tmp_path: Path) -> None:
    for fail in (False, True):
        sub = tmp_path / ("fail" if fail else "ok")
        sub.mkdir()
        r = _run(sub, fail)
        assert r.returncode == 0, r.stdout + r.stderr
        runs = [c for c in (sub / "docker.log").read_text().splitlines() if c.startswith("run ")]
        assert any("pip-audit --no-deps -r smartsched/backend/requirements.lock" in c for c in runs), runs
        assert any("npm audit --omit=dev" in c for c in runs), runs
        assert "report only" in r.stdout
        if fail:
            assert "did not complete" in r.stdout


def test_validate_gate_calls_the_report_and_keeps_its_exit_code() -> None:
    text = (GATES / "validate.sh").read_text()
    assert 'bash "$GATES_DIR/audit-report.sh" || true' in text
    assert text.rstrip().endswith('exit "$docs_rc"')
