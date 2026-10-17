"""Deploy-time settings on the AWS pod: `smartsched_aws.py up --org-name ...` stores them in SSM
{prefix}/bootstrap/*; the pod's first deploy (pod-bootstrap.sh) and every pod CI deploy hand them to deploy.sh as
environment variables (never argv), where seed/bootstrap_settings.py writes each group once."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from podfakes import POD_CI, REPO, SHA_A, FakeReporter, FakeRun
from test_worker import CheckoutStubWorker, FakeExecute, queue

from podci import envfile
from podci.cloud import NoCloud
from podci.config import Config
from podci.state import Store

_spec = importlib.util.spec_from_file_location("deploy_bootstrap_pod",
                                              REPO / "smartsched/deploy/seed/bootstrap_settings.py")
assert _spec and _spec.loader
boot = importlib.util.module_from_spec(_spec)
sys.modules["deploy_bootstrap_pod"] = boot
_spec.loader.exec_module(boot)


def test_bootstrap_keys_are_the_tools_keys_plus_observability() -> None:
    assert (*boot.ALL_KEYS, "OBSERVABILITY") == envfile.BOOTSTRAP_KEYS


def test_bootstrap_env_keeps_known_non_empty_keys_only() -> None:
    got = envfile.bootstrap_env({"ORG_NAME": "Örnek Üniversitesi", "AI_API_KEY": "sk-x", "PATH": "/evil",
                                 "LD_PRELOAD": "/x.so", "SMTP_HOST": "", "OBSERVABILITY": "1"})
    assert got == {"ORG_NAME": "Örnek Üniversitesi", "AI_API_KEY": "sk-x", "OBSERVABILITY": "1"}


def test_shell_exports_are_quoted_and_source_back(tmp_path: Path) -> None:
    values = {"ORG_NAME": "Ali'nin $(rm -rf /) Üniversitesi", "SMTP_PASSWORD": 'p"w`x`'}
    f = tmp_path / "b.env"
    f.write_text(envfile.shell_exports(values))
    r = subprocess.run(["bash", "-c", f'set -a; . {f}; printf "%s\\n%s" "$ORG_NAME" "$SMTP_PASSWORD"'],
                       capture_output=True, text=True, check=True)
    assert r.stdout == f"{values['ORG_NAME']}\n{values['SMTP_PASSWORD']}"


def test_cli_bootstrap_env_writes_a_private_file_from_ssm(tmp_path: Path, monkeypatch: object) -> None:
    from podci import cli

    cloud = NoCloud({"bootstrap/ORG_NAME": "Uni", "bootstrap/AI_API_KEY": "sk-x", "bootstrap/NOPE": "x",
                     "admin_password": "never"})
    monkeypatch.setattr(cli, "make_cloud", lambda cfg: cloud)  # type: ignore[attr-defined]
    out = tmp_path / "bootstrap.env"
    assert cli.main(["bootstrap-env", str(out)]) == 0
    text = out.read_text()
    assert "ORG_NAME=Uni" in text and "AI_API_KEY=" in text and "NOPE" not in text and "never" not in text
    assert oct(out.stat().st_mode & 0o777) == "0o600"


def test_pod_ci_deploys_pass_the_ssm_settings_as_env(cfg: Config, store: Store) -> None:
    queue(store)
    ex = FakeExecute()
    cloud = NoCloud({"bootstrap/ORG_NAME": "Uni", "bootstrap/SMTP_PASSWORD": "pw"})
    CheckoutStubWorker(cfg, store, FakeReporter(), cloud, lambda: "tok", execute=ex, run_cmd=FakeRun(),
                       log=lambda _: None, disk_usage=lambda: 10.0).work()
    deploy_env = ex.envs[ex.scripts.index("deploy.sh")]
    assert deploy_env["ORG_NAME"] == "Uni" and deploy_env["SMTP_PASSWORD"] == "pw"
    gate_envs = [e for s, e in zip(ex.scripts, ex.envs, strict=True) if s != "deploy.sh"]
    assert all("SMTP_PASSWORD" not in e for e in gate_envs)  # test gates never see them
    assert SHA_A


def test_pod_ci_deploy_survives_an_ssm_outage(cfg: Config, store: Store) -> None:
    class Broken(NoCloud):
        def get_params_under(self, sub: str) -> dict[str, str]:
            raise RuntimeError("ssm down")

    queue(store)
    ex = FakeExecute()
    CheckoutStubWorker(cfg, store, FakeReporter(), Broken(), lambda: "tok", execute=ex, run_cmd=FakeRun(),
                       log=lambda _: None, disk_usage=lambda: 10.0).work()
    assert "deploy.sh" in ex.scripts


def test_pod_bootstrap_sources_the_settings_for_the_first_deploy() -> None:
    text = (POD_CI / "pod-bootstrap.sh").read_text()
    assert "podci bootstrap-env" in text
    i_env, i_deploy = text.index("podci bootstrap-env"), text.index("./deploy.sh --tls")
    assert i_env < i_deploy
    assert "set -a" in text and "rm -f" in text
    r = subprocess.run(["bash", "-n", str(POD_CI / "pod-bootstrap.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert os.access(POD_CI / "pod-bootstrap.sh", os.R_OK)
