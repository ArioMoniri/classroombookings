"""Poller (new commits -> queued runs) and worker (one run at a time: gates, statuses, deploy)."""

from __future__ import annotations

import fcntl
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from podci import disk, gitops, nginx
from podci.cloud import Cloud
from podci.config import Config
from podci.gates import DEPLOY, GATES, Gate, playwright_image, python_ci_image
from podci.github import StatusReporter
from podci.state import (
    ERROR,
    FAILURE,
    RUNNING,
    STEP_RUNNING,
    STEP_SKIPPED,
    SUCCESS,
    Run,
    Store,
)

Execute = Callable[[list[str], Path, dict[str, str], Path | None, int], int]
Log = Callable[[str], None]


def run_logged(argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None, timeout: int) -> int:
    """Run argv with stdout+stderr appended to log_path; kill the whole process group on timeout."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as fh:
        proc = subprocess.Popen(argv, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=str(cwd) if cwd else None,
                                start_new_session=True)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            fh.write(f"\n[pod-ci] TIMEOUT after {timeout} s\n".encode())
            return 124


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


def poll(cfg: Config, store: Store, reporter: StatusReporter, token: str,
         ls_remote: Callable[..., dict[str, str]] = gitops.ls_remote, log: Log = print) -> list[Run]:
    """git ls-remote the configured branches; enqueue each new head (supersedes older queued runs)."""
    heads = ls_remote(cfg.repo_url, cfg.branches, token)
    queued: list[Run] = []
    for branch in cfg.branches:
        sha = heads.get(branch)
        if not sha:
            log(f"branch {branch} not found on {cfg.repo}")
            continue
        if store.head(branch) == sha:
            continue
        store.set_head(branch, sha)
        run = store.enqueue(branch, sha, deploy=branch == cfg.deploy_branch)
        if run is None:
            continue
        log(f"queued run #{run.id}: {branch}@{run.short}")
        for old in store.supersede_older(branch, run.id):
            reporter.post(old.sha, "error", cfg.status_context, f"not run: superseded by {run.short}",
                          cfg.run_url(old.id))
        reporter.post(sha, "pending", cfg.status_context, "queued on the SmartSched pod", cfg.run_url(run.id))
        queued.append(run)
    return queued


class Worker:
    def __init__(self, cfg: Config, store: Store, reporter: StatusReporter, cloud: Cloud,
                 token: Callable[[], str], execute: Execute = run_logged, run_cmd: Callable[..., Any] = subprocess.run,
                 log: Log = print, disk_usage: Callable[[], float] = disk.usage_percent,
                 gates: tuple[Gate, ...] = GATES):
        self.cfg, self.store, self.reporter, self.cloud = cfg, store, reporter, cloud
        self.token, self.execute, self.run_cmd, self.log = token, execute, run_cmd, log
        self.disk_usage = disk_usage
        self.gates = gates

    # ---- loop ---------------------------------------------------------------------------------
    def work(self, max_runs: int | None = None) -> int:
        with exclusive(self.cfg.state_dir / "worker.lock") as got:
            if not got:
                self.log("another worker is running; exiting")
                return 0
            requeued, failed = self.store.recover_interrupted(self.cfg.max_attempts)
            for r in requeued:
                self.log(f"run #{r.id} requeued after an interrupted worker")
            for r in failed:
                self.reporter.post(r.sha, "error", self.cfg.status_context, "pod CI worker was interrupted",
                                   self.cfg.run_url(r.id))
            self._kill_leftover_containers()
            self._safe(lambda: self.cloud.set_alarm_actions(True), "re-enable idle alarm")
            done = 0
            while (run := self.store.next_queued()) is not None:
                self._safe(lambda: self.cloud.set_alarm_actions(False), "pause idle alarm")
                self._safe(lambda: self.cloud.heartbeat(True), "heartbeat")
                try:
                    self.run_one(run)
                finally:
                    self._safe(lambda: self.cloud.set_alarm_actions(True), "re-enable idle alarm")
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
        disk.ensure(cfg, self.store, lambda argv: self.run_cmd(argv, capture_output=True, timeout=900).returncode,
                    usage=self.disk_usage, log=self.log)
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
            env = self._gate_env(run, ws)
            results: dict[str, str] = {}
            for g in self.gates:
                results[g.name] = self._run_gate(run, g, env, logs)
            blocking_failed = [g.name for g in self.gates if g.blocking and results[g.name] != SUCCESS]
            final = FAILURE if blocking_failed else SUCCESS
            summary = f"failed: {', '.join(blocking_failed)}" if blocking_failed else "all gates passed"
            if run.deploy:
                if final == SUCCESS and self.store.head(run.branch) == run.sha:
                    if self._deploy(run, logs) != SUCCESS:
                        final, summary = FAILURE, "gates passed, deploy failed"
                    else:
                        summary = "all gates passed, deployed"
                else:
                    reason = "gates failed" if final != SUCCESS else "a newer commit is queued"
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
        self.status(run, {SUCCESS: "success", FAILURE: "failure"}.get(final, "error"), summary)
        self.log(f"run #{run.id} {run.branch}@{run.short}: {final} ({summary})")
        return final

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

    def _gate_env(self, run: Run, ws: Path) -> dict[str, str]:
        cfg = self.cfg
        src = ws / "src"
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "DOCKER_HOST", "TZ")}
        env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        env.update({
            "WS": str(ws), "CACHE_DIR": str(cfg.cache_dir), "RUN_TAG": f"{run.id}-{run.short}",
            "CI_UID": str(os.getuid()), "CI_GID": str(os.getgid()), "GATE_CPUS": cfg.gate_cpus,
            "GATE_MEMORY": cfg.gate_memory, "GATES_DIR": str(cfg.gates_dir), "PY_BASE_IMAGE": cfg.python_image,
            "PY_IMAGE": python_ci_image(cfg.gates_dir, cfg.python_image), "PW_IMAGE": playwright_image(src),
            "HOME": str(cfg.state_dir), "DOCKER_BUILDKIT": "1",
        })
        return env

    def _run_gate(self, run: Run, g: Gate, env: dict[str, str], logs: Path) -> str:
        unmet = [n for n in g.needs if (s := self.store.step(run.id, n)) is None or s.state != SUCCESS]
        if unmet:
            self.store.step_transition(run.id, g.name, STEP_SKIPPED)
            self.status(run, "error" if g.blocking else "success", f"skipped: needs {', '.join(unmet)}", g.name)
            return STEP_SKIPPED
        log_path = logs / f"{g.name}.log"
        self.store.step_transition(run.id, g.name, STEP_RUNNING, log_path=str(log_path))
        self.status(run, "pending", f"running: {g.description}", g.name)
        started = time.monotonic()
        code = self.execute(["bash", str(self.cfg.gates_dir / g.script)], log_path, env, None, g.timeout)
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

    def _deploy(self, run: Run, logs: Path) -> str:
        cfg = self.cfg
        log_path = logs / "deploy.log"
        self.store.step_transition(run.id, DEPLOY.name, STEP_RUNNING, log_path=str(log_path))
        self.status(run, "pending", "deploying", DEPLOY.name)
        try:
            token = self.token()
            gitops.git(["-C", str(cfg.deploy_dir), "fetch", "--quiet", "origin", run.branch], token, run=self.run_cmd)
            gitops.git(["-C", str(cfg.deploy_dir), "checkout", "--quiet", "--force", "--detach", run.sha], token,
                       run=self.run_cmd)
            nginx.apply(cfg.deploy_dir / "smartsched/deploy/nginx/default.conf", f"{cfg.web_bind}:{cfg.web_port}")
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"checked out {run.sha} in {cfg.deploy_dir}; /ci/ location rendered into nginx\n")
        except Exception as exc:  # noqa: BLE001
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"checkout failed: {exc}\n")
            self.store.step_transition(run.id, DEPLOY.name, FAILURE, exit_code=1)
            self.status(run, "failure", "checkout failed", DEPLOY.name)
            return FAILURE
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cfg.state_dir),
               "DEPLOY_DIR": str(cfg.deploy_dir), "DEPLOY_FLAGS": " ".join(cfg.deploy_flags)}
        code = self.execute(["bash", str(cfg.gates_dir / DEPLOY.script)], log_path, env, None, DEPLOY.timeout)
        state = SUCCESS if code == 0 else FAILURE
        self.store.step_transition(run.id, DEPLOY.name, state, exit_code=code)
        self.status(run, "success" if state == SUCCESS else "failure",
                    "deployed" if state == SUCCESS else f"deploy.sh exit {code}", DEPLOY.name)
        if state == SUCCESS:
            # smartsched-ci-update.path (root) re-installs pod CI from the deployed checkout.
            (cfg.state_dir / "update-request").write_text(run.sha + "\n", encoding="utf-8")
        return state


def cpu_times(stat: str | None = None) -> tuple[float, float]:
    """(busy, total) jiffies from /proc/stat's aggregate cpu line."""
    text = stat if stat is not None else Path("/proc/stat").read_text(encoding="utf-8")
    parts = [float(x) for x in text.splitlines()[0].split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)  # idle + iowait
    total = sum(parts[:8])  # guest time is already included in user/nice
    return total - idle, total


def heartbeat(cfg: Config, store: Store, cloud: Cloud, now: float, uptime: float,
              sample: tuple[float, float] | None = None, log: Log = print) -> dict[str, Any]:
    """Publish Heartbeat/CIJobRunning, record a CPU sample and stop the pod when it is idle: no CI run
    queued/running or finished in the window, CPU < idle_cpu % over the last idle_minutes, and up for
    longer than the window. The CloudWatch alarm (CPU only) is the backstop if this process is broken."""
    busy, total = sample or cpu_times()
    window = cfg.idle_minutes * 60
    store.add_cpu_sample(now, busy, total, keep_seconds=2 * window)
    active = store.active()
    out: dict[str, Any] = {"ci_active": active, "cpu_percent": None, "stop": False}
    try:
        cloud.heartbeat(store.running())
    except Exception as exc:  # noqa: BLE001
        log(f"warning: heartbeat failed: {exc}")
    span = store.cpu_window(now - window)
    if span is not None:
        (_, b0, t0), (_, b1, t1) = span
        out["cpu_percent"] = round(100.0 * (b1 - b0) / (t1 - t0), 2) if t1 > t0 else None
    last = store.last_finished_at()
    idle = (cfg.idle_stop and not active and uptime > window and out["cpu_percent"] is not None
            and out["cpu_percent"] < cfg.idle_cpu and (last is None or now - last > window))
    if idle:
        log(f"idle for {cfg.idle_minutes} min (CPU {out['cpu_percent']}%, no CI job): stopping the pod")
        out["stop"] = True
        try:
            cloud.stop_self()
        except Exception as exc:  # noqa: BLE001
            log(f"warning: self-stop failed: {exc}")
    return out
