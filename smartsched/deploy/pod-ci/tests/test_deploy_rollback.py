"""A gate or deploy failure never leaves the pod without its last good stack (pod outage, run #51).

* gates failing: deploy.sh never runs (test_worker), so the running stack is untouched;
* deploy.sh failing (build, migrations, health): the pod checkout goes back to the last good commit
  (state_dir/deployed-sha) and deploy.sh runs again for it;
* a good deploy records its sha (the rollback target and what smartsched-stack.service starts at boot);
* boot: gates/stack-up.sh starts the existing stack with `up -d --no-build` and never stops anything.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from podfakes import POD_CI, SHA_A, SHA_B, FakeReporter, FakeRun
from test_worker import CheckoutStubWorker, FakeExecute, queue

from podci import runner
from podci.cloud import NoCloud
from podci.config import Config
from podci.state import FAILURE, SUCCESS, Store

GATES = POD_CI / "gates"


class FailDeployOnce(FakeExecute):
    """Every gate passes; the first deploy.sh fails, later ones (the rollback) succeed."""

    def __init__(self, rollback_ok: bool = True) -> None:
        super().__init__()
        self.deploys = 0
        self.rollback_ok = rollback_ok

    def __call__(self, argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None, timeout: int) -> int:
        super().__call__(argv, log_path, env, cwd, timeout)
        if Path(argv[1]).name != "deploy.sh":
            return 0
        self.deploys += 1
        return 1 if self.deploys == 1 or not self.rollback_ok else 0


def worker(cfg: Config, store: Store, ex: FakeExecute, rep: FakeReporter, run_cmd: FakeRun) -> CheckoutStubWorker:
    return CheckoutStubWorker(cfg, store, rep, NoCloud(), lambda: "tok", execute=ex, run_cmd=run_cmd,
                              log=lambda _: None, disk_usage=lambda: 10.0)


def checkouts(run_cmd: FakeRun) -> list[str]:
    return [c[-1] for c in run_cmd.calls if "checkout" in c]


def test_good_deploy_records_the_deployed_sha(cfg: Config, store: Store) -> None:
    rid = queue(store)
    worker(cfg, store, FakeExecute(), FakeReporter(), FakeRun()).work()
    assert store.get(rid).state == SUCCESS  # type: ignore[union-attr]
    assert (cfg.state_dir / runner.DEPLOYED_SHA).read_text().strip() == SHA_A


def test_failed_deploy_rolls_back_to_the_last_good_commit(cfg: Config, store: Store) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / runner.DEPLOYED_SHA).write_text(SHA_A + "\n")
    rid = queue(store, sha=SHA_B)
    ex, rep, run_cmd = FailDeployOnce(), FakeReporter(), FakeRun()
    worker(cfg, store, ex, rep, run_cmd).work()
    run = store.get(rid)
    assert run and run.state == FAILURE and run.summary == "gates passed, deploy failed"
    assert ex.scripts.count("deploy.sh") == 2  # the new commit, then the rollback
    assert checkouts(run_cmd) == [SHA_B, SHA_A]  # the pod checkout ends on the last good commit
    assert (cfg.state_dir / runner.DEPLOYED_SHA).read_text().strip() == SHA_A
    assert not (cfg.state_dir / "update-request").exists()  # pod CI is not reinstalled from the failed commit
    assert rep.last("pod-ci/deploy", SHA_B) == "failure"
    desc = [p for p in rep.posts if p[2] == "pod-ci/deploy" and p[1] == "failure"][-1][3]
    assert f"rolled back to {SHA_A[:7]}" in desc


def test_failed_rollback_is_reported(cfg: Config, store: Store) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / runner.DEPLOYED_SHA).write_text(SHA_A + "\n")
    queue(store, sha=SHA_B)
    rep = FakeReporter()
    worker(cfg, store, FailDeployOnce(rollback_ok=False), rep, FakeRun()).work()
    desc = [p for p in rep.posts if p[2] == "pod-ci/deploy" and p[1] == "failure"][-1][3]
    assert f"rollback to {SHA_A[:7]} failed" in desc


def test_first_deploy_failure_has_nothing_to_roll_back(cfg: Config, store: Store) -> None:
    queue(store)
    ex, rep, run_cmd = FailDeployOnce(), FakeReporter(), FakeRun()
    worker(cfg, store, ex, rep, run_cmd).work()
    assert ex.scripts.count("deploy.sh") == 1 and checkouts(run_cmd) == [SHA_A]
    assert not (cfg.state_dir / runner.DEPLOYED_SHA).exists()
    desc = [p for p in rep.posts if p[2] == "pod-ci/deploy" and p[1] == "failure"][-1][3]
    assert "no earlier good deploy" in desc


def test_deploy_script_never_stops_the_stack_first() -> None:
    script = (GATES / "deploy.sh").read_text()
    assert "deploy.sh --update" in script and " down" not in script
    deploy_sh = (POD_CI.parent / "deploy.sh").read_text()
    update = deploy_sh[deploy_sh.index("  update)"):deploy_sh.index("  up)")]
    assert "down" not in update and "up -d" in update  # build first, then recreate changed services only


# ---- boot: gates/stack-up.sh -----------------------------------------------------------------------------

FAKE = """#!/usr/bin/env bash
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$FAKE_LOG"
[[ "$(basename "$0")" == git ]] && echo "$FAKE_HEAD"
exit 0
"""


def boot_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("docker", "git"):
        (bin_dir / name).write_text(FAKE)
        (bin_dir / name).chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "calls.log"),
            "FAKE_HEAD": SHA_A, "PODCI_DEPLOY_DIR": str(tmp_path / "src"), "PODCI_STATE_DIR": str(tmp_path / "state"),
            **extra}


def run_boot(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(GATES / "stack-up.sh")], env=env, capture_output=True, text=True, timeout=30)


def test_boot_without_a_deploy_starts_nothing(tmp_path: Path) -> None:
    r = run_boot(boot_env(tmp_path))
    assert r.returncode == 0 and "nothing to start" in r.stdout
    assert not (tmp_path / "calls.log").exists()


def test_boot_starts_the_existing_stack_without_building_or_stopping(tmp_path: Path) -> None:
    deploy = tmp_path / "src/smartsched/deploy"
    deploy.mkdir(parents=True)
    (deploy / ".env").write_text("PROXY_PORT=8080\n")
    (tmp_path / "state").mkdir()
    (tmp_path / "state/deployed-sha").write_text(SHA_A + "\n")
    r = run_boot(boot_env(tmp_path, PODCI_DEPLOY_FLAGS="--tls"))
    assert r.returncode == 0, r.stdout + r.stderr
    calls = [c for c in (tmp_path / "calls.log").read_text().splitlines() if c.startswith("docker ")]
    assert calls[0] == ("docker compose --env-file .env -f docker-compose.yml -f docker-compose.caddy.yml "
                        "up -d --no-build")
    assert not any(w in c for c in calls for w in (" down", " build", " pull", " stop", " rm"))
    assert "warning" not in r.stdout


def test_boot_warns_when_the_checkout_is_not_the_last_good_deploy(tmp_path: Path) -> None:
    deploy = tmp_path / "src/smartsched/deploy"
    deploy.mkdir(parents=True)
    (deploy / ".env").write_text("")
    (tmp_path / "state").mkdir()
    (tmp_path / "state/deployed-sha").write_text(SHA_B + "\n")
    r = run_boot(boot_env(tmp_path, PODCI_DEPLOY_FLAGS=""))
    assert r.returncode == 0 and "warning: checkout at" in r.stdout
    calls = (tmp_path / "calls.log").read_text()
    assert "docker-compose.caddy.yml" not in calls and "up -d --no-build" in calls


def test_boot_unit_is_installed_and_enabled() -> None:
    unit = (POD_CI / "systemd/smartsched-stack.service").read_text()
    assert "After=network-online.target docker.service" in unit and "WantedBy=multi-user.target" in unit
    assert "/opt/smartsched-ci/gates/stack-up.sh" in unit and "User=smartsched-ci" in unit
    assert "systemctl enable smartsched-stack.service" in (POD_CI / "install.sh").read_text()
    assert "systemctl enable smartsched-stack.service" in (POD_CI / "pod-bootstrap.sh").read_text()


class LsRemote(FakeRun):
    def __call__(self, argv: list[str], **kw: object) -> subprocess.CompletedProcess[object]:
        if "ls-remote" in argv:
            self.calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, stdout=f"{SHA_B}\trefs/heads/{argv[-1].split('/', 2)[-1]}\n",
                                               stderr="")
        return super().__call__(argv, **kw)  # type: ignore[arg-type]


def test_first_deploy_command_deploys_the_branch_head_and_records_it(cfg: Config, store: Store) -> None:
    ex, run_cmd = FakeExecute(), LsRemote()
    assert worker(cfg, store, ex, FakeReporter(), run_cmd).first_deploy() == 0
    assert ex.scripts == ["deploy.sh"]
    assert checkouts(run_cmd) == [SHA_B]
    assert (cfg.state_dir / runner.DEPLOYED_SHA).read_text().strip() == SHA_B
    assert (cfg.state_dir / "update-request").read_text().strip() == SHA_B


def test_first_deploy_command_leaves_a_good_deploy_alone_unless_forced(cfg: Config, store: Store) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / runner.DEPLOYED_SHA).write_text(SHA_A + "\n")
    ex = FakeExecute()
    assert worker(cfg, store, ex, FakeReporter(), LsRemote()).first_deploy() == 0
    assert ex.scripts == []
    assert worker(cfg, store, ex, FakeReporter(), LsRemote()).first_deploy(force=True) == 0
    assert ex.scripts == ["deploy.sh"]


def test_failed_first_deploy_records_nothing(cfg: Config, store: Store) -> None:
    ex = FakeExecute(fail={"deploy"})
    assert worker(cfg, store, ex, FakeReporter(), LsRemote()).first_deploy() != 0
    assert not (cfg.state_dir / runner.DEPLOYED_SHA).exists()
    assert not (cfg.state_dir / "update-request").exists()
