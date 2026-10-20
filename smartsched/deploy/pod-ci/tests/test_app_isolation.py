"""Pod CI never touches the live app stack and the app never touches pod CI.

Gracious run #150 (2026-10-20): the deploy reused the images gate's images (retagged to the compose tag). They were
built with `--label smartsched-ci.run=<run>`, containers inherit their image's labels, and the next worker's leftover
cleanup (`docker ps -aq --filter label=smartsched-ci.run | xargs docker rm -f`) removed the live backend and frontend
right after the deploy: 502 until the stack was restarted. Also: the stack guard that heals a serving site."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from podfakes import POD_CI, FakeReporter, FakeRun
from test_worker import CheckoutStubWorker, FakeExecute, queue

from podci import runner
from podci.cloud import NoCloud
from podci.config import Config
from podci.state import Store

GATES = POD_CI / "gates"


class Docker:
    """A tiny docker: containers with names and labels; `ps -aq --filter`, `inspect --format`, `rm -f`, networks."""

    def __init__(self) -> None:
        self.containers: dict[str, dict[str, Any]] = {}
        self.removed: list[str] = []
        self.calls: list[list[str]] = []

    def add(self, cid: str, name: str, **labels: str) -> None:
        self.containers[cid] = {"name": name, "labels": labels}

    def matches(self, cid: str, flt: str) -> bool:
        c = self.containers[cid]
        key, _, value = flt.partition("=")
        if key == "label":
            k, eq, v = value.partition("=")
            return k in c["labels"] and (not eq or c["labels"][k] == v)
        if key == "name":
            return value in c["name"]
        return False

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        out = ""
        if argv[:3] == ["docker", "ps", "-aq"]:
            out = "\n".join(c for c in self.containers if self.matches(c, argv[4]))
        elif argv[:2] == ["docker", "inspect"]:
            out = "\n".join(f"{c}|/{self.containers[c]['name']}|"
                            f"{self.containers[c]['labels'].get('com.docker.compose.project', '')}"
                            for c in argv[4:] if c in self.containers)
        elif argv[:3] == ["docker", "rm", "-f"]:
            for c in argv[3:]:
                self.containers.pop(c, None)
                self.removed.append(c)
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")


def pod_after_run_150() -> Docker:
    d = Docker()
    app = {"com.docker.compose.project": "smartsched"}
    # the live backend / frontend run the retagged ci images: they inherited the images gate's run label
    d.add("app-backend", "smartsched-backend-1", **app, **{"com.docker.compose.service": "backend",
                                                            "smartsched-ci.run": "150-d70920e"})
    d.add("app-frontend", "smartsched-frontend-1", **app, **{"com.docker.compose.service": "frontend",
                                                              "smartsched-ci.run": "150-d70920e"})
    d.add("app-db", "smartsched-db-1", **app, **{"com.docker.compose.service": "db"})
    d.add("ci-left", "podci-149-abcdef0-e2e1-backend", **{"smartsched-ci.run": "149-abcdef0"})
    d.add("ci-151", "podci-151-1234567-e2e2-smtp", **{"smartsched-ci.run": "151-1234567"})
    d.add("ci-pg", "podci-151-1234567-backend-unit-1-pg", **{"smartsched-ci.run": "151-1234567"})
    return d


def test_the_old_leftover_filter_matched_the_live_app_containers() -> None:
    """The cause, reproduced: a bare label filter selects containers that inherited the label from their image."""
    d = pod_after_run_150()
    hits = d(["docker", "ps", "-aq", "--filter", "label=smartsched-ci.run"]).stdout.split()
    assert "app-backend" in hits and "app-frontend" in hits


def test_a_new_workers_leftover_cleanup_never_removes_the_app_stack(cfg: Config, store: Store) -> None:
    d = pod_after_run_150()
    w = CheckoutStubWorker(cfg, store, FakeReporter(), NoCloud(), lambda: "tok", execute=FakeExecute(), run_cmd=d,
                           log=lambda _: None, disk_usage=lambda: 10.0)
    w.work()  # startup: recover interrupted runs, remove leftover CI containers
    assert {"app-backend", "app-frontend", "app-db"} <= set(d.containers)
    assert {"ci-left", "ci-151", "ci-pg"}.isdisjoint(d.containers)  # CI leftovers still go


def test_a_runs_cleanup_never_removes_the_app_stack_or_another_run() -> None:
    d = pod_after_run_150()
    runner.remove_run_containers("150-d70920e", run=d)  # the deployed run's tag, which the app images carry
    assert {"app-backend", "app-frontend"} <= set(d.containers) and d.removed == []
    runner.remove_run_containers("151-1234567", run=d)
    assert set(d.removed) == {"ci-151", "ci-pg"} and "ci-left" in d.containers
    runner.remove_run_containers("", run=d)  # no tag: never a blanket removal
    assert set(d.removed) == {"ci-151", "ci-pg"}


def test_unknown_container_identity_removes_nothing() -> None:
    d = pod_after_run_150()

    def run(argv: list[str], **kw: Any) -> Any:
        if argv[:2] == ["docker", "inspect"]:
            raise subprocess.TimeoutExpired(argv, 60)
        return d(argv, **kw)

    runner.remove_all_ci_containers(run=run)
    assert d.removed == []


def test_images_never_carry_the_ci_run_label_and_gates_never_drive_the_app_project() -> None:
    images = (GATES / "images.sh").read_text()
    assert '--label "smartsched-ci.image=${RUN_TAG}"' in images and "smartsched-ci.run=" not in images
    lib = (GATES / "lib.sh").read_text()
    assert "com.docker.compose" not in lib  # gate containers never look like app (compose) containers
    for script in GATES.glob("*.sh"):
        text = script.read_text()
        assert "COMPOSE_PROJECT_NAME" not in text and " -p smartsched" not in text, script.name
        if script.name not in ("deploy.sh", "stack-up.sh"):
            for verb in (" down", " rm", " up ", " restart", " stop"):
                assert not any("docker compose" in ln and verb in ln for ln in text.splitlines()), (script.name, verb)


def test_the_app_never_gets_the_run_identity(cfg: Config, store: Store) -> None:
    """The reverse: the deploy step's env carries no RUN_TAG / compose project override, the gates' env no compose
    project (deploy.sh's --remove-orphans only ever sees its own project's containers)."""
    ex = FakeExecute()
    queue(store)
    CheckoutStubWorker(cfg, store, FakeReporter(), NoCloud(), lambda: "tok", execute=ex, run_cmd=FakeRun(),
                       log=lambda _: None, disk_usage=lambda: 10.0).work()
    deploy_env = ex.envs[ex.scripts.index("deploy.sh")]
    assert not {"RUN_TAG", "COMPOSE_PROJECT_NAME", "GATE_NAME"} & set(deploy_env)
    assert all("COMPOSE_PROJECT_NAME" not in e for e in ex.envs)


# ---- stack guard ---------------------------------------------------------------------------------------
class Ps:
    def __init__(self, services: list[str], stack_up_rc: int = 0) -> None:
        self.services, self.rc, self.calls = services, stack_up_rc, []  # type: ignore[var-annotated]

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, kw.get("env")))
        if argv[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(argv, 0, stdout="\n".join(self.services), stderr="")
        return subprocess.CompletedProcess(argv, self.rc, stdout="==== docker compose up -d --no-build\nok\n",
                                           stderr="")

    def stack_ups(self) -> list[Any]:
        return [(a, e) for a, e in self.calls if a[:1] == ["bash"]]


def serving(cfg: Config) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / runner.DEPLOYED_SHA).write_text("d" * 40 + "\n")


ALL = ["db", "backend", "frontend", "proxy", "caddy", "grafana"]


def test_stack_guard_restarts_the_last_good_deploy_when_app_services_vanish(cfg: Config) -> None:
    serving(cfg)
    ps, logs = Ps(["db", "proxy", "caddy", "grafana"]), []
    assert runner.stack_guard(cfg, run=ps, health=lambda: False, log=logs.append) == "healed"
    (argv, env), = ps.stack_ups()
    assert argv == ["bash", str(cfg.gates_dir / "stack-up.sh")]
    assert env["PODCI_DEPLOY_DIR"] == str(cfg.deploy_dir) and env["PODCI_DEPLOY_FLAGS"] == "--tls"
    assert any("['backend', 'frontend']" in line and "stack-up.sh" in line for line in logs)
    ps_argv = ps.calls[0][0]
    assert "label=com.docker.compose.project=smartsched" in ps_argv and "status=running" in ps_argv


def test_stack_guard_leaves_a_healthy_stack_and_waits_for_a_second_failed_health(cfg: Config) -> None:
    serving(cfg)
    ps = Ps(ALL)
    assert runner.stack_guard(cfg, run=ps, health=lambda: True, log=lambda _: None) == "ok"
    assert runner.stack_guard(cfg, run=ps, health=lambda: False, log=lambda _: None) == "unhealthy once"
    assert ps.stack_ups() == []
    assert runner.stack_guard(cfg, run=ps, health=lambda: False, log=lambda _: None) == "healed"
    assert len(ps.stack_ups()) == 1
    assert runner.stack_guard(cfg, run=ps, health=lambda: False, log=lambda _: None) == "unhealthy once"


def test_stack_guard_does_nothing_before_the_first_deploy_or_during_a_deploy(cfg: Config) -> None:
    ps = Ps([])
    assert runner.stack_guard(cfg, run=ps, health=lambda: False, log=lambda _: None) == "no deploy yet"
    serving(cfg)
    with runner.held(cfg.state_dir / runner.DEPLOY_LOCK):  # what the deploy step holds
        assert runner.stack_guard(cfg, run=ps, health=lambda: False, log=lambda _: None) == "deploy running"
    assert ps.calls == []


def test_the_deploy_step_holds_the_deploy_lock(cfg: Config, store: Store) -> None:
    seen: list[str] = []

    class Probe(FakeExecute):
        def __call__(self, argv: list[str], log_path: Path, env: dict[str, str], cwd: Path | None,
                     timeout: int) -> int:
            if Path(argv[1]).name == "deploy.sh":
                serving(cfg)
                seen.append(runner.stack_guard(cfg, run=Ps([]), health=lambda: False, log=lambda _: None))
            return super().__call__(argv, log_path, env, cwd, timeout)

    queue(store)
    CheckoutStubWorker(cfg, store, FakeReporter(), NoCloud(), lambda: "tok", execute=Probe(), run_cmd=FakeRun(),
                       log=lambda _: None, disk_usage=lambda: 10.0).work()
    assert seen == ["deploy running"]


def test_poll_runs_the_stack_guard() -> None:
    cli = (POD_CI / "podci/cli.py").read_text()
    poll = cli[cli.index('if cmd == "poll":'):cli.index('if cmd == "work":')]
    assert "runner.stack_guard(cfg, log=log)" in poll
