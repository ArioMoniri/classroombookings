"""aws-bootstrap.yml: the POD_ACTION line selects the pod (pod=gracious|universal or branch=<deploy branch>)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/aws-bootstrap.yml"


def resolve(tmp_path: Path, line: str) -> tuple[int, dict[str, str], str]:
    wf = yaml.safe_load(WORKFLOW.read_text())
    script = next(s for s in wf["jobs"]["pod"]["steps"] if s.get("id") == "cmd")["run"]
    (tmp_path / "infra/aws").mkdir(parents=True)
    (tmp_path / "infra/aws/POD_ACTION").write_text(line + "\n")
    out = tmp_path / "out"
    r = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(out), "GITHUB_EVENT_NAME": "push"})
    vals = dict(x.split("=", 1) for x in out.read_text().split()) if out.exists() else {}
    return r.returncode, vals, r.stdout + r.stderr


@pytest.mark.parametrize(("line", "pod"), [
    ("up 2026-10-15T21:00Z", "gracious"),
    ("up pod=universal 2026-10-15T21:00Z", "universal"),
    ("status branch=claude/smartsched-universal region=eu-central-1", "universal"),
    ("start branch=claude/gracious-cerf-w1598m", "gracious"),
    ("down destroy pod=universal", "universal"),
])
def test_pod_from_the_action_line(tmp_path: Path, line: str, pod: str) -> None:
    code, vals, log = resolve(tmp_path, line)
    assert code == 0, log
    assert vals["pod"] == pod


@pytest.mark.parametrize(("line", "needle"), [("up pod=main", "unknown pod"),
                                               ("down pod=universal", "down destroy")])
def test_bad_lines_fail(tmp_path: Path, line: str, needle: str) -> None:
    code, _, log = resolve(tmp_path, line)
    assert code == 1 and needle in log


def test_every_bootstrap_call_names_the_pod() -> None:
    text = WORKFLOW.read_text().replace("\\\n", " ")  # join shell line continuations
    calls = [ln for ln in text.splitlines() if "smartsched_aws.py" in ln and "/tmp/venv/bin/python" in ln]
    assert calls
    for ln in calls:
        if " preflight " in ln:
            continue  # credentials only, no pod resources
        assert '--pod "$POD_NAME"' in ln, ln
