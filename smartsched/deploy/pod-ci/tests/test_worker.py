"""Worker: gate sequencing, needs/skips, statuses per gate, deploy gating, errors, one job at a time."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from podfakes import REPO, SHA_A, SHA_B, FakeReporter, FakeRun

from podci import runner
from podci.cloud import NoCloud
from podci.config import Config
from podci.gates import DEPLOY, GATES
from podci.state import ERROR, FAILURE, QUEUED, RUNNING, SUCCESS, Store

DEPLOY_BRANCH = "claude/gracious-cerf-w1598m"


class FakeExecute:
    def __init__(self, fail: set[str] | None = None):
        self.fail = fail or set()
        self.scripts: list[str] = []
        self.argvs: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def __call__(self, argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None, timeout: int) -> int:
        script = Path(argv[1]).name  # argv = ["bash", <script>, *gate.args]
        self.scripts.append(script)
        self.argvs.append(argv)
        self.envs.append(env)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"ran {script}\n")
        gate = log_path.stem  # logs/<run id>/<gate name>.log
        return 1 if script.removesuffix(".sh") in self.fail or gate in self.fail else 0


class CheckoutStubWorker(runner.Worker):
    """The checkout writes a minimal tree instead of fetching from GitHub."""

    def _checkout(self, run: Any, ws: Path, log_path: Path) -> None:
        lock = ws / "src/smartsched/frontend/package-lock.json"
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({"packages": {"node_modules/@playwright/test": {"version": "1.56.1"}}}))
        log_path.write_text("checkout\n")


def make(cfg: Config, store: Store, execute: FakeExecute, rep: FakeReporter | None = None,
         cloud: NoCloud | None = None) -> CheckoutStubWorker:
    return CheckoutStubWorker(cfg, store, rep or FakeReporter(), cloud or NoCloud(), lambda: "tok", execute=execute,
                      run_cmd=FakeRun(), log=lambda _: None, disk_usage=lambda: 10.0)


def queue(store: Store, branch: str = DEPLOY_BRANCH, sha: str = SHA_A) -> int:
    run = store.enqueue(branch, sha, deploy=branch == DEPLOY_BRANCH)
    assert run
    store.set_head(branch, sha)
    return run.id


def test_green_run_on_deploy_branch_deploys(cfg: Config, store: Store) -> None:
    ex, rep, cloud = FakeExecute(), FakeReporter(), NoCloud()
    rid = queue(store)
    assert make(cfg, store, ex, rep, cloud).work() == 1
    run = store.get(rid)
    assert run and run.state == SUCCESS and run.summary == "all gates passed, deployed"
    assert ex.scripts == [g.script for g in GATES] + [DEPLOY.script]
    assert all(s.state == SUCCESS for s in store.steps(rid))
    assert rep.last("pod-ci", SHA_A) == "success"
    for g in GATES:
        assert rep.last(f"pod-ci/{g.name}", SHA_A) == "success"
    assert rep.last("pod-ci/deploy", SHA_A) == "success"
    # gate env: pinned images derived from the repo, run tag, workspace
    env = ex.envs[1]
    assert env["PW_IMAGE"] == "mcr.microsoft.com/playwright:v1.56.1-noble"
    assert env["PY_IMAGE"].startswith("smartsched-podci-python:") and env["RUN_TAG"] == f"{rid}-{SHA_A[:7]}"
    # deploy: checkout of the exact sha, nginx /ci/ rendered, self-update requested
    conf = (cfg.deploy_dir / "smartsched/deploy/nginx/default.conf").read_text()
    assert "location /ci/" in conf
    assert (cfg.state_dir / "update-request").read_text().strip() == SHA_A
    # idle alarm paused during the job and re-enabled afterwards
    toggles = [e[1] for e in cloud.events if e[0] == "alarm_actions"]
    assert toggles[0] is True and False in toggles and toggles[-1] is True
    # workspace removed, logs kept
    assert not (cfg.work_dir / str(rid)).exists() and (cfg.logs_dir / str(rid) / "backend.log").exists()


def test_failed_gate_skips_dependents_and_deploy(cfg: Config, store: Store) -> None:
    ex, rep = FakeExecute(fail={"frontend"}), FakeReporter()
    rid = queue(store)
    make(cfg, store, ex, rep).work()
    states = {s.name: s.state for s in store.steps(rid)}
    assert states["frontend"] == FAILURE
    assert states["e2e-real"] == states["deploy"] == "skipped"
    assert "e2e-mock" not in states  # no mock gate: browser tests run against the real backend only
    assert states["backend"] == states["images"] == SUCCESS  # independent gates still run
    run = store.get(rid)
    assert states["frontend-unit-1"] == states["frontend-unit-2"] == "skipped"  # vitest needs the frontend gate
    assert run and run.state == FAILURE
    assert run.summary.startswith("failed: frontend, frontend-unit-1, frontend-unit-2, e2e-real")
    assert "deploy.sh" not in ex.scripts
    assert rep.last("pod-ci", SHA_A) == "failure" and rep.last("pod-ci/frontend") == "failure"
    assert rep.last("pod-ci/e2e-real") == "error"  # skipped blocking gate is not green


def test_non_blocking_watchdog_failure_keeps_run_green(cfg: Config, store: Store) -> None:
    rid = queue(store, branch="claude/smartsched-universal")
    rep = FakeReporter()
    make(cfg, store, FakeExecute(fail={"watchdog"}), rep).work()
    run = store.get(rid)
    assert run and run.state == SUCCESS and not run.deploy
    assert rep.last("pod-ci/watchdog") == "success"
    assert store.step(rid, "deploy") is None  # non-deploy branch has no deploy step


def test_superseded_head_is_tested_but_not_deployed(cfg: Config, store: Store) -> None:
    rid = queue(store)
    store.set_head(DEPLOY_BRANCH, SHA_B)  # a newer commit arrived while this one ran
    ex = FakeExecute()
    make(cfg, store, ex).work(max_runs=1)
    run = store.get(rid)
    assert run and run.state == SUCCESS and "deploy skipped (a newer commit is queued)" in run.summary
    assert "deploy.sh" not in ex.scripts


def test_infrastructure_error_marks_run_error_and_worker_survives(cfg: Config, store: Store) -> None:
    class Broken(CheckoutStubWorker):
        def _checkout(self, run: Any, ws: Path, log_path: Path) -> None:
            raise RuntimeError("github down for tok")

    rep = FakeReporter()
    rid = queue(store)
    rid2 = queue(store, "claude/smartsched-universal", SHA_B)
    w = Broken(cfg, store, rep, NoCloud(), lambda: "tok", execute=FakeExecute(), run_cmd=FakeRun(),
               log=lambda _: None, disk_usage=lambda: 10.0)
    assert w.work() == 2
    run = store.get(rid)
    assert run and run.state == ERROR and "tok" not in run.summary  # token redacted
    assert all(s.state == "skipped" for s in store.steps(rid))
    assert store.get(rid2).state == ERROR  # type: ignore[union-attr]
    assert rep.last("pod-ci", SHA_A) == "error"


def test_one_job_at_a_time(cfg: Config, store: Store) -> None:
    queue(store)
    with runner.exclusive(cfg.state_dir / "worker.lock") as got:
        assert got
        assert make(cfg, store, FakeExecute()).work() == 0  # second worker backs off
    assert store.next_queued() is not None


def test_restart_resumes_interrupted_run(cfg: Config, store: Store) -> None:
    rid = queue(store)
    store.transition(rid, RUNNING)  # previous worker died here
    ex = FakeExecute()
    make(cfg, store, ex).work()
    run = store.get(rid)
    assert run and run.state == SUCCESS and run.attempts == 2
    assert store.next_queued() is None


def test_disk_cleanup_runs_before_a_job_when_full(cfg: Config, store: Store) -> None:
    queue(store)
    usage = iter([85.0, 85.0, 85.0, 60.0])
    fake = FakeRun()
    w = CheckoutStubWorker(cfg, store, FakeReporter(), NoCloud(), lambda: "tok", execute=FakeExecute(), run_cmd=fake,
                   log=lambda _: None, disk_usage=lambda: next(usage, 60.0))
    w.work()
    assert ["docker", "image", "prune", "-f"] in fake.calls


def test_queued_state_after_poll_then_work(cfg: Config, store: Store) -> None:
    rid = queue(store)
    assert store.get(rid).state == QUEUED  # type: ignore[union-attr]


def test_gate_scripts_exist_and_needs_are_known() -> None:
    names = {g.name for g in GATES}
    for g in (*GATES, DEPLOY):
        assert (REPO / "smartsched/deploy/pod-ci/gates" / g.script).exists(), g.script
        assert set(g.needs) <= names
    assert GATES[0].name == "prepare"


def test_worker_exits_when_installed_code_changes(cfg: Config, store: Store, tmp_path: Path) -> None:
    """GATES is imported once per process: after install.sh swaps the code, the next run needs a new worker."""
    install = tmp_path / "opt-smartsched-ci"
    shutil.copytree(cfg.install_dir / "podci", install / "podci", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(cfg.install_dir / "gates", install / "gates")
    cfg = Config(state_dir=cfg.state_dir, deploy_dir=cfg.deploy_dir, install_dir=install, cloud=False,
                 public_url=cfg.public_url, token_file="")
    stamp = runner.code_stamp(install)
    assert stamp == runner.code_stamp(install)
    ex = FakeExecute()
    rid = queue(store, "claude/smartsched-universal", SHA_A)
    rid2 = queue(store, "claude/smartsched-universal", SHA_B)

    class Reinstalled(FakeExecute):
        def __call__(self, argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None,
                     timeout: int) -> int:
            with (install / "podci/gates.py").open("a") as fh:  # install.sh --upgrade mid-run
                fh.write("# new limits\n")
            return super().__call__(argv, log_path, env, cwd, timeout)

    logs: list[str] = []
    w = CheckoutStubWorker(cfg, store, FakeReporter(), NoCloud(), lambda: "tok", execute=Reinstalled(),
                           run_cmd=FakeRun(), log=logs.append, disk_usage=lambda: 10.0)
    assert w.work() == 1
    assert runner.code_stamp(install) != stamp
    assert store.get(rid).state == SUCCESS  # type: ignore[union-attr]
    assert store.get(rid2).state == QUEUED  # type: ignore[union-attr]  # left for the next worker
    assert any("changed; exiting" in line for line in logs)
    assert make(cfg, store, ex).work() == 1  # a fresh worker (new stamp) takes it
    assert store.get(rid2).state == SUCCESS  # type: ignore[union-attr]


def test_vitest_shards_run_as_their_own_gates(cfg: Config, store: Store) -> None:
    """One failed vitest shard fails the run and skips e2e-real; the other shard and the static checks still run."""
    ex, rep = FakeExecute(fail={"frontend-unit-2"}), FakeReporter()
    rid = queue(store, "claude/smartsched-universal")
    make(cfg, store, ex, rep).work()
    states = {s.name: s.state for s in store.steps(rid)}
    assert states["frontend"] == states["frontend-unit-1"] == SUCCESS
    assert states["frontend-unit-2"] == FAILURE and states["e2e-real"] == "skipped"
    shards = [a[2:] for a in ex.argvs if Path(a[1]).name == "frontend-unit.sh"]
    assert shards == [["1/2"], ["2/2"]]
    timeouts = {g.name: g.timeout for g in GATES}
    assert timeouts["frontend"] == timeouts["frontend-unit-1"] == timeouts["frontend-unit-2"] == 1800
