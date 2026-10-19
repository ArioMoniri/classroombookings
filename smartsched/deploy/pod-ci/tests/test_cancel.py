"""Cancel + fail-fast: superseded runs (Rule A), fail-fast (Rule B), preemption (Rule C), run_logged's cancel, and
POD_ACTION-only heads that are aliases of the previous head instead of new runs."""

from __future__ import annotations

import dataclasses
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from podfakes import SHA_A, SHA_B, SHA_C, Clock, FakeReporter, FakeRun
from test_worker import DEPLOY_BRANCH, CheckoutStubWorker, ConcurrentExecute, FakeExecute, queue

from podci import runner
from podci.cloud import NoCloud
from podci.config import Config
from podci.gates import GATES
from podci.state import ERROR, FAILURE, QUEUED, SUCCESS, SUPERSEDED, Store

UNIVERSAL = "claude/smartsched-universal"


class Hook(FakeExecute):
    """At gate `at`: call `action` (e.g. a push lands), then block until the worker cancels the run (run_logged's
    behaviour) or a short timeout passes."""

    def __init__(self, at: str, action: Any, fail: set[str] | None = None):
        super().__init__(fail)
        self.at, self.action = at, action
        self.worker: runner.Worker | None = None
        self.cancelled: list[str] = []

    def __call__(self, argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None, timeout: int) -> int:
        code = super().__call__(argv, log_path, env, cwd, timeout)
        if log_path.stem == self.at and self.action is not None:
            action, self.action = self.action, None
            action()
            assert self.worker is not None
            if self.worker.cancel.wait(5):
                self.cancelled.append(log_path.stem)
                return runner.CANCELLED_EXIT
        return code


def push(cfg: Config, branch: str, sha: str, clock: Clock | None = None) -> int:
    """What the poller process does on a push, from a gate thread: its own sqlite connection."""
    return queue(Store(cfg.db_path, clock=clock or time.time), branch, sha)


def worker(cfg: Config, store: Store, ex: FakeExecute, rep: FakeReporter | None = None,
           run_cmd: FakeRun | None = None, **over: Any) -> CheckoutStubWorker:
    w = CheckoutStubWorker(dataclasses.replace(cfg, check_interval=0.01, **over), store, rep or FakeReporter(),
                           NoCloud(), lambda: "tok", execute=ex, run_cmd=run_cmd or FakeRun(), log=lambda _: None,
                           disk_usage=lambda: 10.0)
    if isinstance(ex, Hook):
        ex.worker = w
    return w


def test_a_newer_commit_cancels_the_running_run_as_superseded(cfg: Config, store: Store) -> None:
    rid = queue(store, UNIVERSAL, SHA_A)
    newer: list[int] = []
    ex = Hook("backend", lambda: newer.append(push(cfg, UNIVERSAL, SHA_B)))
    rep, fake = FakeReporter(), FakeRun()
    w = worker(cfg, store, ex, rep, run_cmd=fake)
    w.run_one(store.get(rid))  # type: ignore[arg-type]
    run = store.get(rid)
    assert run and run.state == SUPERSEDED
    assert run.summary == f"cancelled, superseded by {SHA_B[:7]} (run #{newer[0]})"
    assert ex.cancelled == ["backend"] and "backend-unit-1.sh" not in ex.scripts
    states = {s.name: s.state for s in store.steps(rid)}
    assert states["backend"] == ERROR and states["frontend"] == states["e2e-real-1"] == "skipped"
    assert all(v != SUCCESS for k, v in states.items() if k not in ("prepare", "validate", "backend-deps"))
    assert rep.last("pod-ci", SHA_A) == "error" and rep.last("pod-ci/frontend", SHA_A) == "error"
    assert any(p[2] == "pod-ci" and p[3].startswith("cancelled, superseded by") for p in rep.posts)
    # the run's containers are removed by label and by name (gate scripts name them podci-<run tag>-*)
    tag = f"{rid}-{SHA_A[:7]}"
    assert ["docker", "ps", "-aq", "--filter", f"label=smartsched-ci.run={tag}"] in fake.calls
    assert ["docker", "ps", "-aq", "--filter", f"name=podci-{tag}-"] in fake.calls
    assert store.get(newer[0]).state == QUEUED  # type: ignore[union-attr]


def test_a_deploy_run_past_the_grace_finishes_and_deploys(cfg: Config, store: Store, clock: Clock) -> None:
    rid = queue(store, DEPLOY_BRANCH, SHA_A)

    def late_push() -> None:
        clock.advance(31 * 60)
        push(cfg, DEPLOY_BRANCH, SHA_B, clock)

    ex = Hook("backend", late_push)
    w = worker(cfg, store, ex)
    w.run_one(store.get(rid))  # type: ignore[arg-type]
    run = store.get(rid)
    assert run and run.state == SUCCESS and run.summary == "all gates passed, deployed"
    assert ex.cancelled == [] and ex.scripts[-1] == "deploy.sh"


def test_a_deploy_run_within_the_grace_is_superseded(cfg: Config, store: Store, clock: Clock) -> None:
    rid = queue(store, DEPLOY_BRANCH, SHA_A)
    ex = Hook("backend", lambda: push(cfg, DEPLOY_BRANCH, SHA_B, clock))
    worker(cfg, store, ex).run_one(store.get(rid))  # type: ignore[arg-type]
    run = store.get(rid)
    assert run and run.state == SUPERSEDED and "deploy.sh" not in ex.scripts
    assert store.step(rid, "deploy").state == "skipped"  # type: ignore[union-attr]


def test_a_failed_run_stays_failed_when_superseded(cfg: Config, store: Store) -> None:
    rid = queue(store, UNIVERSAL, SHA_A)
    ex = Hook("backend-unit-1", lambda: push(cfg, UNIVERSAL, SHA_B), fail={"backend"})
    w = worker(cfg, store, ex, fail_fast=False)
    w.run_one(store.get(rid))  # type: ignore[arg-type]
    run = store.get(rid)
    assert run and run.state == FAILURE and run.summary.startswith("failed: backend; remaining gates stopped")


def test_fail_fast_starts_no_new_gate_after_a_blocking_failure(cfg: Config, store: Store) -> None:
    rid = queue(store)
    ex, rep = FakeExecute(fail={"frontend"}), FakeReporter()
    worker(cfg, store, ex, rep).work()
    states = {s.name: s.state for s in store.steps(rid)}
    order = [g.name for g in GATES]
    after = order[order.index("frontend") + 1:]
    assert states["frontend"] == FAILURE and all(states[g] == "skipped" for g in after)
    assert all(states[g] == SUCCESS for g in order[:order.index("frontend")])
    assert "images.sh" not in ex.scripts and "deploy.sh" not in ex.scripts
    run = store.get(rid)
    assert run and run.state == FAILURE  # nothing becomes green
    desc = [p[3] for p in rep.posts if p[2] == "pod-ci/images"][-1]
    assert desc == "not run: run already failed at frontend" and rep.last("pod-ci/images") == "error"
    assert rep.last("pod-ci/watchdog") == "success"  # non-blocking skip stays neutral


def test_fail_fast_lets_running_gates_finish(cfg: Config, store: Store) -> None:
    ex = ConcurrentExecute(fail={"backend-unit-2"})
    rid = queue(store)

    class Observing(CheckoutStubWorker):
        """Records when the worker itself sees the failure: the executor's "end" comes a moment earlier (the future
        is not done yet), and gates the worker starts in that window are legitimate."""

        def _finish_gate(self, run: Any, g: Any, code: int, started: float) -> str:
            state = super()._finish_gate(run, g, code, started)
            if g.blocking and state != SUCCESS:
                with ex.lock:
                    ex.events.append(("observed", g.name))
            return state

    w = Observing(dataclasses.replace(cfg, parallel=0, check_interval=0.01), store, FakeReporter(),
                  NoCloud(), lambda: "tok", execute=ex, run_cmd=FakeRun(), log=lambda _: None,
                  disk_usage=lambda: 10.0, cpu_count=8, memory_mb=15_800)
    w.work()
    seen = ex.events.index(("observed", "backend-unit-2"))
    assert ex.events.index(("end", "backend-unit-2")) < seen
    started_before = {g for k, g in ex.events[:seen] if k == "start"}
    assert not any(k == "start" for k, _ in ex.events[seen + 1:])  # nothing new once the worker saw the failure
    states = {s.name: s.state for s in store.steps(rid)}
    for g in started_before - {"backend-unit-2"}:
        assert states[g] == SUCCESS, g  # gates already running finished normally
    assert all(states[g] == "skipped" for g in states if g not in started_before)
    assert store.get(rid).state == FAILURE  # type: ignore[union-attr]


def test_a_deploy_branch_run_preempts_a_universal_run(cfg: Config, store: Store) -> None:
    other = queue(store, UNIVERSAL, SHA_A)
    deploy: list[int] = []
    ex = Hook("backend", lambda: deploy.append(push(cfg, DEPLOY_BRANCH, SHA_C)))
    order: list[int] = []

    class Recording(CheckoutStubWorker):
        def run_one(self, run: Any) -> str:
            order.append(run.id)
            return super().run_one(run)

    rep = FakeReporter()
    w = Recording(dataclasses.replace(cfg, check_interval=0.01), store, rep, NoCloud(), lambda: "tok", execute=ex,
                  run_cmd=FakeRun(), log=lambda _: None, disk_usage=lambda: 10.0)
    ex.worker = w
    assert w.work() == 3
    assert order == [other, deploy[0], other]  # requeued, the deploy run first, then the universal run again
    assert store.get(deploy[0]).summary == "all gates passed, deployed"  # type: ignore[union-attr]
    run = store.get(other)
    assert run and run.state == SUCCESS and run.attempts == 2
    assert any(p[0] == SHA_A and p[3].startswith("requeued: preempted by deploy-branch run") for p in rep.posts)


def test_run_logged_cancel_kills_the_group_and_escalates_to_sigkill(tmp_path: Path) -> None:
    cancel = threading.Event()
    log = tmp_path / "g.log"
    threading.Timer(0.2, cancel.set).start()
    t0 = time.monotonic()
    # ignores SIGTERM (inherited by sleep): only the SIGKILL after kill_grace ends it
    code = runner.run_logged(["sh", "-c", "trap '' TERM; sleep 30"], log, {"PATH": "/usr/bin:/bin"}, None, 60,
                             cancel=cancel, slice_seconds=0.05, kill_grace=0.5)
    assert code == runner.CANCELLED_EXIT and time.monotonic() - t0 < 10
    assert "CANCELLED" in log.read_text()
    # without a cancel the timeout still applies
    assert runner.run_logged(["sleep", "5"], log, {"PATH": "/usr/bin:/bin"}, None, 1, kill_grace=1) == 124


def test_remove_run_containers_by_label_and_name() -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        out = "c1\nc2\n" if "label=smartsched-ci.run=7-aaaaaaa" in argv and "ps" in argv else ""
        out = "c2\nc3\n" if "name=podci-7-aaaaaaa-" in argv else out
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    runner.remove_run_containers("7-aaaaaaa", run=run)
    assert ["docker", "rm", "-f", "c1", "c2", "c3"] in calls
    runner.remove_run_containers("", run=run)  # no tag: never a blanket removal
    assert len([c for c in calls if c[:3] == ["docker", "rm", "-f"]]) == 1


# ---- POD_ACTION-only heads ----------------------------------------------------------------------
def ls(heads: dict[str, str]) -> Any:
    return lambda url, branches, token: {b: heads[b] for b in branches if b in heads}


def test_a_pod_action_only_push_is_an_alias_not_a_run(cfg: Config, store: Store) -> None:
    rep, logs = FakeReporter(), []
    seen: list[tuple[str, str, str]] = []

    def changed(branch: str, old: str, new: str) -> list[str]:
        seen.append((branch, old, new))
        return [runner.POD_ACTION]

    runner.poll(cfg, store, rep, "tok", ls_remote=ls({DEPLOY_BRANCH: SHA_A}), log=logs.append, changed=changed)
    base = store.find(DEPLOY_BRANCH, SHA_A)
    assert base and seen == []  # the first head is always queued
    runner.poll(cfg, store, rep, "tok", ls_remote=ls({DEPLOY_BRANCH: SHA_B}), log=logs.append, changed=changed)
    assert store.find(DEPLOY_BRANCH, SHA_B) is None and store.head(DEPLOY_BRANCH) == SHA_B
    assert store.effective_head(DEPLOY_BRANCH) == SHA_A and store.get(base.id).state == QUEUED  # type: ignore[union-attr]
    assert rep.last("pod-ci", SHA_B) == "pending"
    # a second POD_ACTION-only push resolves to the same code
    runner.poll(cfg, store, rep, "tok", ls_remote=ls({DEPLOY_BRANCH: SHA_C}), log=logs.append, changed=changed)
    assert store.effective_head(DEPLOY_BRANCH) == SHA_A and store.aliases_of(DEPLOY_BRANCH, SHA_A) == [SHA_B, SHA_C]
    # the run's final status reaches the aliases; the run still deploys (it is the effective head)
    w = worker(cfg, store, FakeExecute(), rep)
    w.work()
    assert store.get(base.id).summary == "all gates passed, deployed"  # type: ignore[union-attr]
    assert rep.last("pod-ci", SHA_B) == rep.last("pod-ci", SHA_C) == "success"


def test_a_code_change_is_queued_and_supersedes_with_a_log_line(cfg: Config, store: Store) -> None:
    rep, logs = FakeReporter(), []
    changed = lambda b, o, n: [runner.POD_ACTION, "smartsched/backend/app.py"]  # noqa: E731
    runner.poll(cfg, store, rep, "tok", ls_remote=ls({UNIVERSAL: SHA_A}), log=logs.append, changed=changed)
    runner.poll(cfg, store, rep, "tok", ls_remote=ls({UNIVERSAL: SHA_B}), log=logs.append, changed=changed)
    old, new = store.find(UNIVERSAL, SHA_A), store.find(UNIVERSAL, SHA_B)
    assert old and new and new.state == QUEUED
    assert f"run #{old.id} superseded by #{new.id}" in logs
    # git could not tell (None): queued as usual
    runner.poll(cfg, store, rep, "tok", ls_remote=ls({UNIVERSAL: SHA_C}), log=logs.append,
                changed=lambda b, o, n: None)
    assert store.find(UNIVERSAL, SHA_C) is not None


def test_pod_action_alias_of_a_finished_run_gets_its_status(cfg: Config, store: Store) -> None:
    rep = FakeReporter()
    rid = queue(store, UNIVERSAL, SHA_A)
    store.transition(rid, "running")
    store.transition(rid, FAILURE, summary="failed: backend")
    runner.poll(cfg, store, rep, "tok", ls_remote=ls({UNIVERSAL: SHA_B}), log=lambda _: None,
                changed=lambda b, o, n: [runner.POD_ACTION])
    assert rep.last("pod-ci", SHA_B) == "failure"
    assert store.find(UNIVERSAL, SHA_B) is None


def test_mirror_changed_files_uses_git_diff_name_only(cfg: Config) -> None:
    fake = FakeRun()
    assert runner.mirror_changed_files(cfg, "tok", run=fake)(DEPLOY_BRANCH, SHA_A, SHA_B) is None  # no mirror yet
    assert fake.calls == []
    cfg.mirror_dir.mkdir(parents=True)
    (cfg.mirror_dir / "HEAD").write_text("ref: refs/heads/main\n")

    def run(argv: list[str], **kw: Any) -> Any:
        res = fake(argv, **kw)
        if "diff" in argv:
            res.stdout = f"{runner.POD_ACTION}\n"
        return res

    files = runner.mirror_changed_files(cfg, "tok", run=run)(DEPLOY_BRANCH, SHA_A, SHA_B)
    assert files == [runner.POD_ACTION]
    assert ["git", "--git-dir", str(cfg.mirror_dir), "diff", "--name-only", SHA_A, SHA_B] in fake.calls
    assert runner.pod_action_only(files) and not runner.pod_action_only([]) and not runner.pod_action_only(None)
