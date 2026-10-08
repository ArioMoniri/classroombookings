"""python3 -m podci <command>   (systemd units in ../systemd call these)

  poll            git ls-remote the branches, queue new commits, heartbeat + idle check, wake the worker
  work            run queued jobs one at a time (flock); safe to kill and restart
  web             serve /ci/ on PODCI_WEB_BIND:PODCI_WEB_PORT
  heartbeat       heartbeat metrics + idle self-stop only
  cleanup         disk cleanup to below PODCI_DISK_MAX_PERCENT
  rerun ID        queue a finished run again
  runs            print the last runs
  render-nginx FILE                 insert the /ci/ location into an nginx config (idempotent)
  prepare-env ENV EXAMPLE K=V...    create/update deploy/.env, generating secrets on the pod
  sync-secrets ENV                  store admin + app secrets from deploy/.env in SSM (SecureString)
  basic-auth FILE                   create the /ci/ basic-auth credentials once, store them in SSM
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

from podci import config as config_mod
from podci import disk, envfile, nginx, runner
from podci.cloud import Cloud, NoCloud
from podci.github import StatusReporter
from podci.state import Store


def log(msg: str) -> None:
    print(f"[pod-ci] {msg}", flush=True)


def make_cloud(cfg: config_mod.Config) -> Cloud:
    return Cloud(cfg.ssm_prefix, cfg.idle_alarm) if cfg.cloud else NoCloud()


def token_provider(cfg: config_mod.Config, cloud: Cloud):  # type: ignore[no-untyped-def]
    @lru_cache(maxsize=1)
    def token() -> str:
        if cfg.token_file:
            value = Path(cfg.token_file).read_text(encoding="utf-8").strip()
        else:
            value = (cloud.get_param("github_token") or "").strip()
        if not value:
            raise RuntimeError(f"no GitHub token: SSM {cfg.ssm_prefix}/github_token is missing (store "
                               "POD_GITHUB_TOKEN with the aws-bootstrap workflow)")
        return value
    return token


def uptime_seconds() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except OSError:
        return 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="podci", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    cfg = config_mod.load()
    cmd = a.command

    if cmd == "render-nginx":
        changed = nginx.apply(Path(a.args[0]), f"{cfg.web_bind}:{cfg.web_port}")
        log(f"{a.args[0]}: {'updated' if changed else 'already has /ci/'}")
        return 0
    if cmd == "prepare-env":
        env_file, example, *pairs = a.args
        values = dict(p.split("=", 1) for p in pairs)
        generated = envfile.prepare(Path(env_file), Path(example), values)
        log(f"{env_file}: set {sorted(values)}; generated {generated or 'nothing (kept existing secrets)'}")
        return 0

    cloud = make_cloud(cfg)
    if cmd == "sync-secrets":
        for name, (value, secure) in envfile.ssm_values(Path(a.args[0])).items():
            cloud.put_param(name, value, secure)
            log(f"stored {cfg.ssm_prefix}/{name} ({'SecureString' if secure else 'String'})")
        return 0
    if cmd == "basic-auth":
        path = Path(a.args[0])
        if not path.exists() or not path.read_text().strip():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"ci:{envfile.random_password(24)}\n", encoding="utf-8")
        path.chmod(0o600)
        cloud.put_param("ci/basic_auth", path.read_text().strip(), True)
        log(f"basic auth for /ci/ stored in {cfg.ssm_prefix}/ci/basic_auth (user 'ci')")
        return 0

    store = Store(cfg.db_path)
    token = token_provider(cfg, cloud)
    reporter = StatusReporter(cfg.repo, token, log=log)
    if cmd == "poll":
        try:
            runner.poll(cfg, store, reporter, token(), log=log)
        except Exception as exc:  # noqa: BLE001 - keep the heartbeat going when GitHub is unreachable
            log(f"poll failed: {exc}")
        runner.heartbeat(cfg, store, cloud, time.time(), uptime_seconds(), log=log)
        if store.active():  # smartsched-ci-worker.path (PathChanged) starts the worker unit
            (cfg.state_dir / "queue-signal").write_text(f"{time.time()}\n", encoding="utf-8")
        return 0
    if cmd == "work":
        runner.Worker(cfg, store, reporter, cloud, token, log=log).work()
        return 0
    if cmd == "heartbeat":
        log(str(runner.heartbeat(cfg, store, cloud, time.time(), uptime_seconds(), log=log)))
        return 0
    if cmd == "cleanup":
        taken = disk.ensure(cfg, store, lambda argv: subprocess.run(argv, check=False).returncode, log=log)
        log(f"cleanup: {taken or 'nothing needed'} (disk {disk.usage_percent():.0f}%)")
        return 0
    if cmd == "rerun":
        run = store.rerun(int(a.args[0]))
        log(f"run #{run.id} queued again")
        return 0
    if cmd == "runs":
        for r in store.recent(20):
            print(f"#{r.id:<5} {r.state:<10} {r.branch:<32} {r.short} {r.summary}")
        return 0
    if cmd == "web":
        from podci import web

        basic_file = cfg.state_dir / "basic_auth"
        basic = basic_file.read_text().strip() if basic_file.exists() else os.environ.get("PODCI_BASIC_AUTH")
        web.serve(cfg, basic)
        return 0
    print(__doc__, file=sys.stderr)
    return 2
