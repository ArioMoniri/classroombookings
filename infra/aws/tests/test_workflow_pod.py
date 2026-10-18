"""aws-bootstrap.yml: the POD_ACTION line selects the pod (pod=gracious|universal or branch=<deploy branch>)."""

from __future__ import annotations

import subprocess
import sys
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
    # the step calls python3; the CI image has it in /usr/local/bin only, so put this interpreter on the PATH
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    r = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                       env={"PATH": f"{bindir}:/usr/bin:/bin", "GITHUB_OUTPUT": str(out), "GITHUB_EVENT_NAME": "push"})
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


# sweep 2026-10-18: deploy-time settings on the POD_ACTION line map to `smartsched_aws.py up` flags
# (docs/deploy/ONE-CLICK.md); the optional repo secrets reach `up` as environment variables only.


def flags(tmp_path: Path) -> list[str]:
    p = tmp_path / "pod-flags"
    return [x for x in p.read_text().split("\0") if x] if p.exists() else []


def test_settings_on_the_line_become_up_flags(tmp_path: Path) -> None:
    line = ('up pod=universal org="Örnek Üniversitesi" admin=it@uni.edu.tr smtp-host=smtp.uni.edu.tr '
            'smtp-port=587 smtp-security=starttls security=guvenlik@uni.edu.tr observability=off '
            'ai=openai 2026-10-18T08:00Z')
    code, vals, log = resolve(tmp_path, line)
    assert code == 0, log
    assert vals["pod"] == "universal" and vals["command"] == "up"
    assert flags(tmp_path) == [
        "--org-name", "Örnek Üniversitesi", "--admin-email", "it@uni.edu.tr", "--smtp-host", "smtp.uni.edu.tr",
        "--smtp-port", "587", "--smtp-security", "starttls", "--security-contact", "guvenlik@uni.edu.tr",
        "--no-observability", "--ai-provider", "openai",
    ]
    assert "Örnek" not in log  # only the flag names are logged


@pytest.mark.parametrize(("line", "needle"), [
    ("up domain=plan.uni.edu.tr", "sslip.io"),
    ("up orgname=X", "unknown setting 'orgname'"),
    ("up org=\"unclosed", "cannot parse"),
    ("up observability=maybe", "observability=on|off"),
])
def test_bad_settings_fail(tmp_path: Path, line: str, needle: str) -> None:
    code, _, log = resolve(tmp_path, line)
    assert code == 1 and needle in log, log


def test_settings_are_ignored_for_other_commands(tmp_path: Path) -> None:
    code, vals, log = resolve(tmp_path, "status org=X region=eu-central-1")
    assert code == 0, log
    assert vals["region"] == "eu-central-1" and flags(tmp_path) == []


def test_up_step_gets_the_optional_secrets_as_env_and_never_echoes_them() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text())
    step = next(s for s in wf["jobs"]["pod"]["steps"] if str(s.get("name", "")).startswith("smartsched_aws.py"))
    for key in ("AI_API_KEY", "SMTP_PASSWORD"):
        assert step["env"][key] == f"${{{{ secrets.{key} }}}}"
        assert f"${key}" not in step["run"] and f"${{{key}}}" not in step["run"]
    assert "pod-flags" in step["run"]
    assert set(wf[True]) == {"push", "workflow_dispatch"} and wf[True]["push"]["paths"] == ["infra/aws/POD_ACTION"]
