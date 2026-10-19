"""Poller (new commits -> queued runs) and worker (one run at a time: gates, statuses, deploy)."""

from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from podci import disk, envfile, gitops, nginx
from podci.cloud import Cloud
from podci.config import Config
from podci.gates import DEPLOY, GATES, Gate, playwright_image, python_ci_image
from podci.github import StatusReporter
from podci.state import (
    ERROR,
    FAILURE,
    QUEUED,
    RUNNING,
    STEP_RUNNING,
    STEP_SKIPPED,
    SUCCESS,
    SUPERSEDED,
    Run,
    Store,
)

Execute = Callable[[list[str], Path, dict[str, str], Path | None, int], int]
# state_dir file: the last commit whose deploy passed its health check (rollback target, boot stack)
DEPLOYED_SHA = "deployed-sha"
Log = Callable[[str], None]


CANCELLED_EXIT = 143  # a gate killed because its run was cancelled (superseded / preempted)


def _kill_group(proc: subprocess.Popen[bytes], grace: float = 30) -> None:
    """SIGTERM the gate's process group, SIGKILL it after `grace` seconds."""
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def remove_run_containers(run_tag: str, run: Callable[..., Any] = subprocess.run) -> None:
    """docker rm -f every container of a run: labelled smartsched-ci.run=<RUN_TAG> (lib.sh docker_common) or named
    podci-<RUN_TAG>-* (e2e-real.sh, backend gates); then the run's networks. Never touches the app stack."""
    if not run_tag:
        return
    ids: list[str] = []
    for flt in (f"label=smartsched-ci.run={run_tag}", f"name=podci-{run_tag}-"):
        try:
            proc = run(["docker", "ps", "-aq", "--filter", flt], capture_output=True, text=True, timeout=60)
            ids += [i for i in str(proc.stdout or "").split() if i not in ids]
        except (OSError, subprocess.SubprocessError):
            continue
    try:
        if ids:
            run(["docker", "rm", "-f", *ids], capture_output=True, timeout=120)
        nets = run(["docker", "network", "ls", "-q", "--filter", f"label=smartsched-ci.run={run_tag}"],
                   capture_output=True, text=True, timeout=60)
        net_ids = str(nets.stdout or "").split()
        if net_ids:
            run(["docker", "network", "rm", *net_ids], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        pass


def run_logged(argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None, timeout: int,
               cancel: threading.Event | None = None, slice_seconds: float = 5.0, kill_grace: float = 30) -> int:
    """Run argv with stdout+stderr appended to log_path; kill the whole process group on timeout. With `cancel`
    the wait runs in slices: once the event is set the group gets SIGTERM, SIGKILL after kill_grace seconds, and the
    run's containers (RUN_TAG in env) are removed (docker rm -f); returns CANCELLED_EXIT."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as fh:
        proc = subprocess.Popen(argv, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=str(cwd) if cwd else None,
                                start_new_session=True)
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                _kill_group(proc, kill_grace)
                fh.write(f"\n[pod-ci] TIMEOUT after {timeout} s\n".encode())
                return 124
            try:
                return proc.wait(timeout=min(left, slice_seconds) if cancel is not None else left)
            except subprocess.TimeoutExpired:
                pass
            if cancel is not None and cancel.is_set():
                _kill_group(proc, kill_grace)
                remove_run_containers(env.get("RUN_TAG", ""))
                fh.write(b"\n[pod-ci] CANCELLED (run cancelled: superseded or preempted)\n")
                return CANCELLED_EXIT


@contextmanager
def exclusive(path: Path) -> Iterator[bool]:
    """Non-blocking flock: yields False when another worker holds it (one job at a time)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh: IO[str] = open(path, "a+")  # noqa: SIM115 - held for the duration of the context
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        fh.close()


POD_ACTION = "infra/aws/POD_ACTION"
Changed = Callable[[str, str, str], "list[str] | None"]


def mirror_changed_files(cfg: Config, token: str, run: Callable[..., Any] = subprocess.run) -> Changed:
    """(branch, old, new) -> files changed between two heads, from the pod's mirror (fetched first); None when git
    could not tell (then the new head is queued as usual)."""
    def changed(branch: str, old: str, new: str) -> list[str] | None:
        if not (cfg.mirror_dir / "HEAD").exists():  # the worker creates the mirror; a first clone is not for poll
            return None
        try:
            gitops.fetch_into_mirror(cfg.mirror_dir, cfg.repo_url, branch, new, token, run=run)
            gitops.fetch_into_mirror(cfg.mirror_dir, cfg.repo_url, branch, old, token, run=run)
        except (gitops.GitError, OSError, subprocess.SubprocessError):
            return None
        return gitops.changed_files(cfg.mirror_dir, old, new, run=run)
    return changed


def pod_action_only(files: list[str] | None) -> bool:
    return bool(files) and all(f == POD_ACTION for f in files or ())


def _final_status(run: Run) -> tuple[str, str] | None:
    if run.state == SUCCESS:
        return "success", run.summary
    if run.state == FAILURE:
        return "failure", run.summary
    if run.state == ERROR:
        return "error", run.summary
    return None


def poll(cfg: Config, store: Store, reporter: StatusReporter, token: str,
         ls_remote: Callable[..., dict[str, str]] = gitops.ls_remote, log: Log = print,
         changed: Changed | None = None) -> list[Run]:
    """git ls-remote the configured branches; enqueue each new head (supersedes older queued runs). A head whose diff
    from the previous head only touches infra/aws/POD_ACTION (the owner's pod trigger) is not queued: it is an alias
    of the previous head (same code), which gets that run's statuses."""
    heads = ls_remote(cfg.repo_url, cfg.branches, token)
    queued: list[Run] = []
    for branch in cfg.branches:
        sha = heads.get(branch)
        if not sha:
            log(f"branch {branch} not found on {cfg.repo}")
            continue
        prev = store.head(branch)
        if prev == sha:
            continue
        if prev and changed is not None and store.find(branch, sha) is None and pod_action_only(
                changed(branch, prev, sha)):
            root = store.add_alias(branch, sha, prev)
            store.set_head(branch, sha)
            log(f"{branch}@{sha[:7]} only changes {POD_ACTION}: not queued, same code as {root[:7]}")
            base = store.find(branch, root)
            final = _final_status(base) if base else None
            if base is not None and final is not None:
                reporter.post(sha, final[0], cfg.status_context, f"same code as {root[:7]}: {final[1]}"[:140],
                              cfg.run_url(base.id))
            elif base is not None and base.state in (QUEUED, RUNNING):
                reporter.post(sha, "pending", cfg.status_context, f"same code as {root[:7]} (run #{base.id})",
                              cfg.run_url(base.id))
            continue
        store.set_head(branch, sha)
        run = store.enqueue(branch, sha, deploy=branch == cfg.deploy_branch)
        if run is None:
            continue
        log(f"queued run #{run.id}: {branch}@{run.short}")
        for old in store.supersede_older(branch, run.id):
            log(f"run #{old.id} superseded by #{run.id}")
            reporter.post(old.sha, "error", cfg.status_context, f"not run: superseded by {run.short}",
                          cfg.run_url(old.id))
        reporter.post(sha, "pending", cfg.status_context, "queued on the SmartSched pod", cfg.run_url(run.id))
        queued.append(run)
    return queued


def code_stamp(install_dir: Path) -> str:
    """Hash of the installed pod CI code (podci/*.py, gates/*): GATES and its timeouts are imported once per worker
    process, so a worker that keeps draining the queue after install.sh replaced the code would run the new gate
    scripts under the old gate list and limits (pod run #81: frontend killed at the old 1800 s, gates.py said 3600)."""
    h = hashlib.sha256()
    for sub, pattern in (("podci", "*.py"), ("gates", "*")):
        for f in sorted((install_dir / sub).glob(pattern)):
            if f.is_file():
                h.update(f"{sub}/{f.name}\0".encode())
                h.update(f.read_bytes())
    return h.hexdigest()


def mem_total_mb() -> int:
    """MemTotal of /proc/meminfo in MiB (0 when unknown: then the worker stays at one gate at a time)."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


@dataclass(frozen=True)
class Slots:
    """How many gates run at once and what one slot gets. count == 1: today's sequential worker, cfg.gate_cpus and
    cfg.gate_memory (lib.sh defaults for the node containers). count > 1: CPUs and memory are split per slot."""
    count: int
    cpus: int = 0
    memory_mb: int = 0

    def env(self, weight: int) -> dict[str, str]:
        if self.count <= 1:
            return {}
        w = max(1, min(weight, self.count))
        mem = self.memory_mb * w
        # GATE_MEMORY leaves 1 GiB of the slot for a side container (postgres --memory 1g, e2e's smtp / empty backend)
        gate_mb = max(2048, mem - 1024)
        return {"GATE_CPUS": str(self.cpus * w), "GATE_MEMORY": f"{gate_mb}m", "NODE_MEMORY": f"{mem}m",
                "NODE_HEAP_MB": str(mem * 3 // 4)}


def plan_slots(cfg: Config, cpu_count: int, memory_mb: int) -> Slots:
    """PODCI_PARALLEL (0 = cpu_count // 2), capped so every slot has slot_min_mb of the memory left after
    memory_reserve_mb (the app stack): the sum of the gates' container caps stays inside the pod."""
    want = cfg.parallel if cfg.parallel > 0 else max(1, cpu_count // 2)
    budget = memory_mb - cfg.memory_reserve_mb
    count = max(1, min(want, budget // cfg.slot_min_mb if budget > 0 else 1))
    if count == 1:
        return Slots(1)
    return Slots(count, cpus=max(1, cpu_count // count), memory_mb=budget // count)


class Worker:
    def __init__(self, cfg: Config, store: Store, reporter: StatusReporter, cloud: Cloud,
                 token: Callable[[], str], execute: Execute | None = None,
                 run_cmd: Callable[..., Any] = subprocess.run,
                 log: Log = print, disk_usage: Callable[[], float] = disk.usage_percent,
                 gates: tuple[Gate, ...] = GATES, cpu_count: int | None = None, memory_mb: int | None = None):
        self.cfg, self.store, self.reporter, self.cloud = cfg, store, reporter, cloud
        # set when the running run is cancelled (Rule A: superseded, Rule C: preempted); run_logged honours it
        self.cancel = threading.Event()
        self._abort: tuple[str, str] | None = None  # (SUPERSEDED | QUEUED, description) of the running run
        if execute is None:
            def execute(argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None, timeout: int) -> int:
                return run_logged(argv, log_path, env, cwd, timeout, cancel=self.cancel)
        self.token, self.execute, self.run_cmd, self.log = token, execute, run_cmd, log
        self.disk_usage = disk_usage
        self.gates = gates
        self.slots = plan_slots(cfg, (os.cpu_count() or 1) if cpu_count is None else cpu_count,
                                mem_total_mb() if memory_mb is None else memory_mb)

    # ---- loop ---------------------------------------------------------------------------------
    def work(self, max_runs: int | None = None) -> int:
        with exclusive(self.cfg.state_dir / "worker.lock") as got:
            if not got:
                self.log("another worker is running; exiting")
                return 0
            requeued, failed, superseded = self.store.recover_interrupted(self.cfg.max_attempts)
            for r in superseded:
                self.log(f"run #{r.id} interrupted; {r.summary}")
                self.reporter.post(r.sha, "error", self.cfg.status_context, f"not finished: {r.summary}",
                                   self.cfg.run_url(r.id))
            for r in requeued:
                self.log(f"run #{r.id} requeued after an interrupted worker")
            for r in failed:
                self.reporter.post(r.sha, "error", self.cfg.status_context, "pod CI worker was interrupted",
                                   self.cfg.run_url(r.id))
            self._kill_leftover_containers()
            self._safe(lambda: self.cloud.set_alarm_actions(not serving_site(self.cfg)), "re-enable idle alarm")
            stamp = code_stamp(self.cfg.install_dir)
            done = 0
            while (run := self.store.next_queued(deploy_branch=self.cfg.deploy_branch)) is not None:
                if code_stamp(self.cfg.install_dir) != stamp:
                    # smartsched-ci-worker.timer (OnUnitInactiveSec=5min) starts a fresh worker on the new code
                    self.log(f"pod CI code in {self.cfg.install_dir} changed; exiting so a new worker loads it")
                    break
                self._safe(lambda: self.cloud.set_alarm_actions(False), "pause idle alarm")
                self._safe(lambda: self.cloud.heartbeat(True), "heartbeat")
                try:
                    self.run_one(run)
                finally:
                    self._safe(lambda: self.cloud.set_alarm_actions(not serving_site(self.cfg)), "re-enable idle alarm")
                    self._safe(lambda: self.cloud.heartbeat(self.store.active()), "heartbeat")
                done += 1
                if max_runs is not None and done >= max_runs:
                    break
            return done

    def _safe(self, fn: Callable[[], object], what: str) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - cloud hiccups never fail CI
            self.log(f"warning: {what} failed: {exc}")

    def _kill_leftover_containers(self) -> None:
        self.run_cmd(["sh", "-c", "docker ps -aq --filter label=smartsched-ci.run | xargs -r docker rm -f; "
                      "docker network ls -q --filter label=smartsched-ci.run | xargs -r docker network rm"],
                     capture_output=True, timeout=120)

    # ---- one run ------------------------------------------------------------------------------
    def context(self, gate: str | None = None) -> str:
        return self.cfg.status_context + (f"/{gate}" if gate else "")

    def status(self, run: Run, state: str, description: str, gate: str | None = None) -> None:
        self.reporter.post(run.sha, state, self.context(gate), description, self.cfg.run_url(run.id))

    def run_one(self, run: Run) -> str:
        cfg = self.cfg
        disk.prune_artifacts(cfg)
        disk.ensure(cfg, self.store, lambda argv: self.run_cmd(argv, capture_output=True, timeout=900).returncode,
                    usage=self.disk_usage, log=self.log)
        self.cancel.clear()
        self._abort = None
        run = self.store.transition(run.id, RUNNING)
        steps = [(g.name, g.blocking) for g in self.gates] + ([(DEPLOY.name, True)] if run.deploy else [])
        self.store.add_steps(run.id, steps)
        self.status(run, "pending", f"running on the pod (attempt {run.attempts})")
        for g in self.gates:
            self.status(run, "pending", "waiting", g.name)
        ws = cfg.work_dir / str(run.id)
        logs = cfg.logs_dir / str(run.id)
        try:
            shutil.rmtree(ws, ignore_errors=True)
            logs.mkdir(parents=True, exist_ok=True)
            self._checkout(run, ws, logs / "checkout.log")
            env = self._gate_env(run, ws, logs)
            results = self._run_gates(run, env, logs)
            really_failed = [g.name for g in self.gates if g.blocking and results.get(g.name) == FAILURE]
            if self._abort is not None and not really_failed:
                return self._finish_aborted(run, *self._abort)
            blocking_failed = [g.name for g in self.gates if g.blocking and results[g.name] != SUCCESS]
            final = FAILURE if blocking_failed else SUCCESS
            summary = f"failed: {', '.join(blocking_failed)}" if blocking_failed else "all gates passed"
            if self._abort is not None:  # a failed run stays failed; its remaining gates were stopped
                summary = f"failed: {', '.join(really_failed)}; remaining gates stopped ({self._abort[1]})"
                remove_run_containers(f"{run.id}-{run.short}", run=self.run_cmd)
            if run.deploy:
                allowed, reason = self._deploy_allowed(run) if final == SUCCESS else (False, "gates failed")
                if allowed:
                    if self._deploy(run, logs) != SUCCESS:
                        final, summary = FAILURE, "gates passed, deploy failed"
                    else:
                        summary = "all gates passed, deployed"
                else:
                    self.store.step_transition(run.id, DEPLOY.name, STEP_SKIPPED)
                    summary += f"; deploy skipped ({reason})"
        except Exception as exc:  # noqa: BLE001 - infrastructure error: record it, report it, keep the worker alive
            self.log(f"run #{run.id} error: {exc}")
            final, summary = ERROR, f"pod CI error: {gitops.redact(str(exc), self._token_or_empty())[:300]}"
            for st in self.store.steps(run.id):
                if st.state == STEP_RUNNING:
                    self.store.step_transition(run.id, st.name, ERROR)
                elif st.state == "pending":
                    self.store.step_transition(run.id, st.name, STEP_SKIPPED)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        self.store.transition(run.id, final, summary=summary)
        state = {SUCCESS: "success", FAILURE: "failure"}.get(final, "error")
        self.status(run, state, summary)
        for alias in self.store.aliases_of(run.branch, run.sha):  # POD_ACTION-only heads carrying this code
            self.reporter.post(alias, state, self.context(), f"same code as {run.short}: {summary}"[:140],
                               self.cfg.run_url(run.id))
        self.log(f"run #{run.id} {run.branch}@{run.short}: {final} ({summary})")
        return final

    def _finish_aborted(self, run: Run, new_state: str, description: str) -> str:
        """A cancelled run (gates already stopped): superseded -> terminal, preempted -> queued again."""
        remove_run_containers(f"{run.id}-{run.short}", run=self.run_cmd)
        for st in self.store.steps(run.id):
            if st.state == STEP_RUNNING:
                self.store.step_transition(run.id, st.name, ERROR)
            elif st.state == "pending":
                self.store.step_transition(run.id, st.name, STEP_SKIPPED)
        if new_state == QUEUED:
            self.store.requeue(run.id, summary=description)
            self.status(run, "pending", f"requeued: {description}"[:140])
            self.log(f"run #{run.id} {run.branch}@{run.short}: requeued ({description})")
            return QUEUED
        self.store.transition(run.id, new_state, summary=description)
        self.status(run, "error", description[:140])
        self.log(f"run #{run.id} {run.branch}@{run.short}: {new_state} ({description})")
        return new_state

    def _deploy_allowed(self, run: Run) -> tuple[bool, str]:
        """A green deploy-branch run deploys when nothing was deployed yet or its commit descends from the deployed
        one (a newer queued commit deploys later, when it is green). Never an older commit over a newer deploy. A
        rewritten history (neither descends from the other) deploys only the branch's current head."""
        deployed = self.last_good_sha()
        if not deployed or deployed == run.sha:
            return True, ""
        mirror = self.cfg.mirror_dir
        try:  # the deployed commit may predate the mirror (pod-bootstrap.sh's checkout)
            gitops.fetch_into_mirror(mirror, self.cfg.repo_url, run.branch, deployed, self.token(), run=self.run_cmd)
        except Exception as exc:  # noqa: BLE001
            self.log(f"warning: deployed {deployed[:7]} not fetched into the mirror: {exc}")
        forward = gitops.is_ancestor(mirror, deployed, run.sha, run=self.run_cmd)
        if forward:
            return True, ""
        backward = gitops.is_ancestor(mirror, run.sha, deployed, run=self.run_cmd)
        if backward:
            return False, f"older than the deployed {deployed[:7]}"
        if forward is False and backward is False and self.store.effective_head(run.branch) == run.sha:
            return True, ""
        return False, f"not a descendant of the deployed {deployed[:7]}"

    def _token_or_empty(self) -> str:
        try:
            return self.token()
        except Exception:  # noqa: BLE001
            return ""

    def _checkout(self, run: Run, ws: Path, log_path: Path) -> None:
        token = self.token()
        gitops.fetch_into_mirror(self.cfg.mirror_dir, self.cfg.repo_url, run.branch, run.sha, token, run=self.run_cmd)
        gitops.export_tree(self.cfg.mirror_dir, run.sha, ws / "src", run=self.run_cmd)
        log_path.write_text(f"exported {run.branch}@{run.sha} into {ws / 'src'}\n", encoding="utf-8")

    def _gate_env(self, run: Run, ws: Path, logs: Path | None = None) -> dict[str, str]:
        cfg = self.cfg
        src = ws / "src"
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "DOCKER_HOST", "TZ")}
        env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        env.update({
            "WS": str(ws), "CACHE_DIR": str(cfg.cache_dir), "RUN_TAG": f"{run.id}-{run.short}",
            "CI_UID": str(os.getuid()), "CI_GID": str(os.getgid()), "GATE_CPUS": cfg.gate_cpus,
            "GATE_MEMORY": cfg.gate_memory, "GATES_DIR": str(cfg.gates_dir), "PY_BASE_IMAGE": cfg.python_image,
            "PY_IMAGE": python_ci_image(cfg.gates_dir, cfg.python_image), "PW_IMAGE": playwright_image(src),
            "HOME": str(cfg.state_dir), "DOCKER_BUILDKIT": "1", "RUN_SHA": run.sha,
            # images.sh keeps this commit's images (ci-<full sha>) for the deploy step of a deploy-branch run
            "RUN_DEPLOY": "1" if run.deploy else "0",
        })
        if logs is not None:  # kept with the run's logs after the workspace is deleted (e2e error-context.md)
            env["ARTIFACT_DIR"] = str(logs / "artifacts")
        return env

    def _run_gates(self, run: Run, env: dict[str, str], logs: Path) -> dict[str, str]:
        """Every gate once, along the `needs` DAG: a gate starts when its needs succeeded and its `after` gates
        finished (in GATES order among the ready ones), at most self.slots.count slots at once (a gate takes
        `weight` slots); a gate whose need failed or was skipped is skipped. Only the subprocess runs in a thread:
        the store and the status posts stay on this thread, which re-checks every cfg.check_interval seconds:
          Rule A  a newer commit of the branch is queued -> the run is cancelled (superseded)
          Rule C  a non-deploy-branch run while a deploy-branch run is queued -> cancelled and requeued
          Rule B  (cfg.fail_fast) a blocking gate failed -> no new gate starts; running gates finish
        A cancel sets self.cancel (run_logged kills the gates) and records self._abort for run_one."""
        results: dict[str, str] = {}
        running: dict[Future[int], tuple[Gate, float]] = {}
        pending = list(self.gates)
        free = self.slots.count
        failed_at: str | None = None
        with ThreadPoolExecutor(max_workers=self.slots.count, thread_name_prefix="gate") as pool:
            try:
                while pending or running:
                    if self._abort is None:
                        self._abort = self._check_abort(run)
                        if self._abort is not None:
                            self.log(f"run #{run.id}: {self._abort[1]}; stopping its gates")
                            self.cancel.set()
                    if self._abort is not None:
                        for g in pending:
                            results[g.name] = self._skip_gate(run, g, [], reason=self._abort[1])
                        pending.clear()
                    elif failed_at is not None and self.cfg.fail_fast:
                        for g in pending:
                            results[g.name] = self._skip_gate(run, g, [],
                                                              reason=f"not run: run already failed at {failed_at}")
                        pending.clear()
                    for g in list(pending):
                        if any(n not in results for n in (*g.needs, *g.after)):
                            continue
                        unmet = [n for n in g.needs if results[n] != SUCCESS]
                        if unmet:
                            pending.remove(g)
                            results[g.name] = self._skip_gate(run, g, unmet)
                            continue
                        weight = max(1, min(g.weight, self.slots.count))
                        if weight > free:
                            continue
                        pending.remove(g)
                        free -= weight
                        argv, log_path, gate_env = self._start_gate(run, g, env, logs)
                        fut = pool.submit(self.execute, argv, log_path, gate_env, None, g.timeout)
                        running[fut] = (g, time.monotonic())
                    if not running:
                        if pending:  # needs that no gate provides: never runnable
                            for g in pending:
                                results[g.name] = self._skip_gate(run, g, [n for n in g.needs if n not in results])
                            pending.clear()
                        break
                    done, _ = wait(running, timeout=self.cfg.check_interval, return_when=FIRST_COMPLETED)
                    for fut in done:
                        g, started = running.pop(fut)
                        free += max(1, min(g.weight, self.slots.count))
                        results[g.name] = self._finish_gate(run, g, fut.result(), started)
                        if g.blocking and results[g.name] != SUCCESS and failed_at is None:
                            failed_at = g.name
            finally:
                wait(running)  # never leave a gate subprocess behind an exception
        return results

    def _check_abort(self, run: Run) -> tuple[str, str] | None:
        if not run.deploy and run.branch != self.cfg.deploy_branch:
            first = self.store.queued_deploy_run(self.cfg.deploy_branch)
            if first is not None:
                return QUEUED, f"preempted by deploy-branch run #{first.id} ({first.short})"
        newer = self.store.newer_queued(run.branch, run.id)
        if newer is None:
            return None
        grace = self.cfg.supersede_grace_minutes * 60
        started = self.store.get(run.id)
        elapsed = self.store.now() - (started.started_at if started and started.started_at else self.store.now())
        if run.deploy and grace > 0 and elapsed >= grace:
            return None  # far enough along: finish, deploy when green; the newer commit deploys after it
        return SUPERSEDED, f"cancelled, superseded by {newer.short} (run #{newer.id})"

    def _skip_gate(self, run: Run, g: Gate, unmet: list[str], reason: str | None = None) -> str:
        self.store.step_transition(run.id, g.name, STEP_SKIPPED)
        description = reason or f"skipped: needs {', '.join(unmet)}"
        cancelled = self._abort is not None
        self.status(run, "error" if g.blocking or cancelled else "success", description[:140], g.name)
        return STEP_SKIPPED

    def _start_gate(self, run: Run, g: Gate, env: dict[str, str],
                    logs: Path) -> tuple[list[str], Path, dict[str, str]]:
        log_path = logs / f"{g.name}.log"
        self.store.step_transition(run.id, g.name, STEP_RUNNING, log_path=str(log_path))
        self.status(run, "pending", f"running: {g.description}", g.name)
        gate_env = {**env, "GATE_NAME": g.name, **self.slots.env(g.weight)}
        return ["bash", str(self.cfg.gates_dir / g.script), *g.args], log_path, gate_env

    def _finish_gate(self, run: Run, g: Gate, code: int, started: float) -> str:
        if self._abort is not None and code != 0:
            self.store.step_transition(run.id, g.name, ERROR, exit_code=code)
            self.status(run, "error", self._abort[1][:140], g.name)
            return ERROR
        state = SUCCESS if code == 0 else FAILURE
        self.store.step_transition(run.id, g.name, state, exit_code=code)
        took = f"{int(time.monotonic() - started)} s"
        if state == SUCCESS:
            self.status(run, "success", f"{g.description} ({took})", g.name)
        elif g.blocking:
            self.status(run, "failure", f"exit {code} after {took}", g.name)
        else:
            self.status(run, "success", f"non-blocking, exit {code} ({took})", g.name)
        return state

    @property
    def deployed_sha_path(self) -> Path:
        """The last commit whose deploy passed its health check (written here and by pod-bootstrap.sh)."""
        return self.cfg.state_dir / DEPLOYED_SHA

    def last_good_sha(self) -> str | None:
        try:
            sha = self.deployed_sha_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return sha or None

    def _checkout_deploy(self, sha: str, branch: str, log_path: Path) -> None:
        cfg = self.cfg
        token = self.token()
        gitops.git(["-C", str(cfg.deploy_dir), "fetch", "--quiet", "origin", branch], token, run=self.run_cmd)
        gitops.git(["-C", str(cfg.deploy_dir), "checkout", "--quiet", "--force", "--detach", sha], token,
                   run=self.run_cmd)
        nginx.apply(cfg.deploy_dir / "smartsched/deploy/nginx/default.conf", f"{cfg.web_bind}:{cfg.web_port}")
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"checked out {sha} in {cfg.deploy_dir}; /ci/ location rendered into nginx\n")

    def _deploy_env(self, sha: str = "") -> dict[str, str]:
        cfg = self.cfg
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cfg.state_dir),
                "DEPLOY_DIR": str(cfg.deploy_dir), "DEPLOY_FLAGS": " ".join(cfg.deploy_flags),
                "DEPLOY_SHA": sha, **self._bootstrap_env()}

    def _bootstrap_env(self) -> dict[str, str]:
        """Deploy-time settings from SSM {prefix}/bootstrap/* (smartsched_aws.py up): deploy.sh writes each group
        into the database once (seed/bootstrap_settings.py; the admin panel wins later). Only the deploy step gets
        them, never a test gate. SSM unreachable = deploy without them (they are retried on the next deploy)."""
        try:
            return envfile.bootstrap_env(self.cloud.get_params_under("bootstrap"))
        except Exception as exc:  # noqa: BLE001
            self.log(f"deploy-time settings not read from SSM ({type(exc).__name__}); deploying without them")
            return {}

    def _deploy(self, run: Run, logs: Path) -> str:
        """deploy.sh --update never stops the running stack first (build, then `up -d`), so a failed build
        leaves the live stack as it was. A failed deploy (build, migrations or health) is rolled back to the
        last good commit (DEPLOYED_SHA) so the pod checkout, the images and a reboot all come back to it."""
        cfg = self.cfg
        log_path = logs / "deploy.log"
        self.store.step_transition(run.id, DEPLOY.name, STEP_RUNNING, log_path=str(log_path))
        self.status(run, "pending", "deploying", DEPLOY.name)
        previous = self.last_good_sha()
        try:
            self._checkout_deploy(run.sha, run.branch, log_path)
        except Exception as exc:  # noqa: BLE001
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"checkout failed: {exc}\n")
            self.store.step_transition(run.id, DEPLOY.name, FAILURE, exit_code=1)
            self.status(run, "failure", "checkout failed", DEPLOY.name)
            if previous and previous != run.sha:
                self._rollback(previous, run.branch, log_path)
            return FAILURE
        code = self.execute(["bash", str(cfg.gates_dir / DEPLOY.script)], log_path, self._deploy_env(run.sha), None,
                            DEPLOY.timeout)
        state = SUCCESS if code == 0 else FAILURE
        self.store.step_transition(run.id, DEPLOY.name, state, exit_code=code)
        description = "deployed" if state == SUCCESS else f"deploy.sh exit {code}"
        if state == SUCCESS:
            self.deployed_sha_path.write_text(run.sha + "\n", encoding="utf-8")
            # smartsched-ci-update.path (root) re-installs pod CI from the deployed checkout.
            (cfg.state_dir / "update-request").write_text(run.sha + "\n", encoding="utf-8")
        elif previous and previous != run.sha:
            back = self._rollback(previous, run.branch, log_path)
            description += f"; rolled back to {previous[:7]}" if back else f"; rollback to {previous[:7]} failed"
        else:
            description += "; no earlier good deploy to roll back to"
        self.status(run, "success" if state == SUCCESS else "failure", description, DEPLOY.name)
        return state

    def _rollback(self, sha: str, branch: str, log_path: Path) -> bool:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"\n==== rollback to the last good deploy {sha}\n")
        try:
            self._checkout_deploy(sha, branch, log_path)
        except Exception as exc:  # noqa: BLE001
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"rollback checkout failed: {exc}\n")
            self.log(f"rollback to {sha[:7]} failed: {exc}")
            return False
        code = self.execute(["bash", str(self.cfg.gates_dir / DEPLOY.script)], log_path, self._deploy_env(sha), None,
                            DEPLOY.timeout)
        self.log(f"rollback to {sha[:7]}: {'ok' if code == 0 else f'deploy.sh exit {code}'}")
        return code == 0


def cpu_times(stat: str | None = None) -> tuple[float, float]:
    """(busy, total) jiffies from /proc/stat's aggregate cpu line."""
    text = stat if stat is not None else Path("/proc/stat").read_text(encoding="utf-8")
    parts = [float(x) for x in text.splitlines()[0].split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)  # idle + iowait
    total = sum(parts[:8])  # guest time is already included in user/nice
    return total - idle, total


def serving_site(cfg: Config) -> bool:
    """A deploy passed its health check on this pod (DEPLOYED_SHA): the pod is the website's host from now on."""
    return (cfg.state_dir / DEPLOYED_SHA).is_file()


def idle_window_minutes(cfg: Config, serving: bool) -> int:
    """The idle self-stop window: idle_minutes, but at least idle_minutes_predeploy until the first deploy (a pod
    whose first deploy is still pending must not stop an hour after a red run while the fix is being pushed)."""
    return cfg.idle_minutes if serving else max(cfg.idle_minutes, cfg.idle_minutes_predeploy)


def heartbeat(cfg: Config, store: Store, cloud: Cloud, now: float, uptime: float,
              sample: tuple[float, float] | None = None, log: Log = print) -> dict[str, Any]:
    """Publish Heartbeat/CIJobRunning, record a CPU sample and stop the pod when it is idle: no CI run
    queued/running or finished in the window, CPU < idle_cpu % over the last idle window, and up for
    longer than the window. The CloudWatch alarm (CPU only) is the backstop if this process is broken; before the
    first deploy it stays disarmed until the (longer) pre-deploy window has passed without CI work."""
    busy, total = sample or cpu_times()
    serving = serving_site(cfg)
    minutes = idle_window_minutes(cfg, serving)
    window = minutes * 60
    store.add_cpu_sample(now, busy, total, keep_seconds=2 * window)
    active = store.active()
    out: dict[str, Any] = {"ci_active": active, "cpu_percent": None, "stop": False, "idle_minutes": minutes}
    try:
        cloud.heartbeat(store.running())
    except Exception as exc:  # noqa: BLE001
        log(f"warning: heartbeat failed: {exc}")
    span = store.cpu_window(now - window)
    if span is not None:
        (_, b0, t0), (_, b1, t1) = span
        out["cpu_percent"] = round(100.0 * (b1 - b0) / (t1 - t0), 2) if t1 > t0 else None
    last = store.last_finished_at()
    # A pod with a good deploy serves the website: it never stops itself, and the CloudWatch backstop stays
    # disarmed (an hour of low CPU is a quiet site, not an idle CI box; the site kept going dark, 2026-10-19).
    out["serving"] = serving
    quiet = 0.0 if active else min(uptime, now - last if last is not None else uptime)
    if serving or (cfg.idle_stop and quiet < window):
        # serving: always disarmed. First deploy pending: the 60-min CPU alarm would undercut the longer window
        try:
            cloud.set_alarm_actions(False)
        except Exception as exc:  # noqa: BLE001
            log(f"warning: disarming the idle alarm failed: {exc}")
    elif cfg.idle_stop:
        try:
            cloud.set_alarm_actions(True)
        except Exception as exc:  # noqa: BLE001
            log(f"warning: re-arming the idle alarm failed: {exc}")
    idle = (cfg.idle_stop and not serving and not active and uptime > window and out["cpu_percent"] is not None
            and out["cpu_percent"] < cfg.idle_cpu and (last is None or now - last > window))
    if idle:
        log(f"idle for {minutes} min (CPU {out['cpu_percent']}%, no CI job): stopping the pod")
        out["stop"] = True
        try:
            cloud.stop_self()
        except Exception as exc:  # noqa: BLE001
            log(f"warning: self-stop failed: {exc}")
    return out
