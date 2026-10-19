"""Worker: gate sequencing, needs/skips, statuses per gate, deploy gating, errors, one job at a time."""

from __future__ import annotations

import dataclasses
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from podfakes import REPO, SHA_A, SHA_B, FakeReporter, FakeRun

from podci import runner
from podci.cloud import NoCloud
from podci.config import Config
from podci.gates import DEPLOY, GATES, Gate
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
    # idle alarm paused during the job; after a good deploy the pod serves the site, so it stays disarmed
    toggles = [e[1] for e in cloud.events if e[0] == "alarm_actions"]
    assert toggles[0] is True and False in toggles and toggles[-1] is False
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


def test_worker_runs_the_deploy_branch_before_older_runs_of_other_branches(cfg: Config, store: Store) -> None:
    ex = FakeExecute()
    other = queue(store, "claude/smartsched-universal", SHA_A)
    deploy = queue(store, DEPLOY_BRANCH, SHA_B)
    order: list[int] = []

    class Recording(CheckoutStubWorker):
        def run_one(self, run: Any) -> str:
            order.append(run.id)
            return super().run_one(run)

    w = Recording(cfg, store, FakeReporter(), NoCloud(), lambda: "tok", execute=ex, run_cmd=FakeRun(),
                  log=lambda _: None, disk_usage=lambda: 10.0)
    assert w.work() == 2
    assert order == [deploy, other]


def test_plan_slots_scales_cpus_and_memory_and_respects_the_memory_cap() -> None:
    c7g = 15_800  # c7g.2xlarge: 8 vCPU, 16 GB (MemTotal ~15.4 GiB)
    slots = runner.plan_slots(Config(), cpu_count=8, memory_mb=c7g)
    assert slots.count == 3  # cpu_count // 2 = 4 wanted, (15800 - 3072) // 4096 = 3 fit
    assert slots.cpus == 2 and slots.memory_mb == (c7g - 3072) // 3
    one = slots.env(1)
    assert one["GATE_CPUS"] == "2" and one["NODE_MEMORY"] == f"{slots.memory_mb}m"
    assert one["GATE_MEMORY"] == f"{slots.memory_mb - 1024}m" and int(one["NODE_HEAP_MB"]) < slots.memory_mb
    two = slots.env(2)
    assert two["GATE_CPUS"] == "4" and two["NODE_MEMORY"] == f"{2 * slots.memory_mb}m"
    # the caps of everything that can run at once stay inside MemTotal minus the app stack's reserve
    assert slots.count * slots.memory_mb <= c7g - 3072 <= 13 * 1024
    assert runner.plan_slots(Config(parallel=1), cpu_count=8, memory_mb=c7g).count == 1
    assert runner.plan_slots(Config(parallel=2), cpu_count=8, memory_mb=c7g).count == 2
    assert runner.plan_slots(Config(parallel=8), cpu_count=8, memory_mb=c7g).count == 3
    assert runner.plan_slots(Config(), cpu_count=8, memory_mb=0).count == 1  # MemTotal unknown: sequential
    assert runner.plan_slots(Config(), cpu_count=2, memory_mb=c7g).count == 1


class ConcurrentExecute(FakeExecute):
    """Thread-safe: records start/finish order and the peak of gates running at once (each runs ~20 ms)."""

    def __init__(self, fail: set[str] | None = None):
        super().__init__(fail)
        self.lock = threading.Lock()
        self.now = self.peak = 0
        self.events: list[tuple[str, str]] = []

    def __call__(self, argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None, timeout: int) -> int:
        gate = log_path.stem
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
            self.events.append(("start", gate))
        time.sleep(0.02)
        with self.lock:
            code = super().__call__(argv, log_path, env, cwd, timeout)
            self.now -= 1
            self.events.append(("end", gate))
        return code


def parallel_worker(cfg: Config, store: Store, ex: FakeExecute, rep: FakeReporter | None = None,
                    gates: tuple[Gate, ...] = GATES) -> CheckoutStubWorker:
    return CheckoutStubWorker(dataclasses.replace(cfg, parallel=0), store, rep or FakeReporter(), NoCloud(),
                              lambda: "tok", execute=ex, run_cmd=FakeRun(), log=lambda _: None,
                              disk_usage=lambda: 10.0, gates=gates, cpu_count=8, memory_mb=15_800)


def test_gates_run_concurrently_along_the_needs_dag_within_the_slot_cap(cfg: Config, store: Store) -> None:
    ex, rep = ConcurrentExecute(), FakeReporter()
    rid = queue(store)
    w = parallel_worker(cfg, store, ex, rep)
    assert w.slots.count == 3
    w.work()
    run = store.get(rid)
    assert run and run.state == SUCCESS and run.summary == "all gates passed, deployed"
    assert 1 < ex.peak <= 3  # concurrent, never more than the slots
    order = [(kind, g) for kind, g in ex.events if g != "deploy"]
    for g in GATES:
        start = order.index(("start", g.name))
        for need in (*g.needs, *g.after):  # a gate starts only after its needs (and `after` gates) ended
            assert order.index(("end", need)) < start, (need, g.name)
    weights = {g.name: g.weight for g in GATES}
    running: set[str] = set()
    for kind, g in order:  # e2e-real / images take two slots
        running.add(g) if kind == "start" else running.discard(g)
        assert sum(weights[x] for x in running) <= 3, running
    envs = {e["GATE_NAME"]: e for e in ex.envs if "GATE_NAME" in e}  # deploy.sh has its own env
    assert envs["backend-unit-2"]["GATE_CPUS"] == "2" and envs["e2e-real"]["GATE_CPUS"] == "4"
    assert set(envs) == {g.name for g in GATES}
    assert ex.scripts[-1] == "deploy.sh"  # the deploy waits for every gate
    assert all(rep.last(f"pod-ci/{g.name}") == "success" for g in GATES)


def test_a_failed_gate_skips_only_its_dependants_when_parallel(cfg: Config, store: Store) -> None:
    ex = ConcurrentExecute(fail={"backend-unit-2"})
    rid = queue(store)
    parallel_worker(cfg, store, ex).work()
    states = {s.name: s.state for s in store.steps(rid)}
    assert states["backend-unit-2"] == FAILURE
    assert states["e2e-real"] == states["planner"] == states["parity"] == states["deploy"] == "skipped"
    assert states["backend-unit-1"] == states["backend-unit-3"] == states["frontend-unit-2"] == SUCCESS
    assert states["images"] == states["infra"] == SUCCESS
    run = store.get(rid)
    assert run and run.state == FAILURE and run.summary.startswith("failed: backend-unit-2, e2e-real")


def test_after_orders_without_requiring_success(cfg: Config, store: Store) -> None:
    """parity reads e2e-real's report: it waits for e2e-real to end, and still runs when e2e-real failed."""
    gates = (Gate("prepare", "prepare.sh", "p"), Gate("e2e-real", "e2e-real.sh", "e", needs=("prepare",)),
             Gate("parity", "parity.sh", "x", needs=("prepare",), after=("e2e-real",)),
             Gate("never", "never.sh", "n", needs=("missing",)))
    ex = ConcurrentExecute(fail={"e2e-real"})
    rid = queue(store, "claude/smartsched-universal")
    parallel_worker(cfg, store, ex, gates=gates).work()
    states = {s.name: s.state for s in store.steps(rid)}
    assert states == {"prepare": SUCCESS, "e2e-real": FAILURE, "parity": SUCCESS, "never": "skipped"}
    assert ex.events.index(("end", "e2e-real")) < ex.events.index(("start", "parity"))
