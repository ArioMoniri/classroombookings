"""envfile (secrets generated on the pod), config loading, disk cleanup, heartbeat/idle stop, scripts."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from podfakes import POD_CI, REPO, Clock

from podci import config as config_mod
from podci import disk, envfile, runner
from podci.cloud import NoCloud
from podci.config import Config
from podci.state import RUNNING, Store

EXAMPLE = REPO / "smartsched/deploy/.env.example"


def test_prepare_env_generates_on_pod_and_keeps_secrets(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    gen = envfile.prepare(env, EXAMPLE, {"TLS_DOMAIN": "1-2-3-4.sslip.io", "ADMIN_EMAIL": "a@b.c",
                                         "CORS_ORIGINS": '["https://1-2-3-4.sslip.io"]'})
    assert {"APP_SECRET", "JWT_SECRET", "POSTGRES_PASSWORD", "ADMIN_PASSWORD"} <= set(gen)
    assert "AUTH_SECRET" not in gen  # dead config (no-placeholder audit m3): the frontend never read it
    parsed = envfile.parse(env.read_text())
    assert "__GENERATE__" not in env.read_text().split("# ---- database")[1]
    assert re.fullmatch(r"[A-Za-z0-9]{20}", parsed["ADMIN_PASSWORD"])
    assert re.fullmatch(r"[0-9a-f]{64}", parsed["JWT_SECRET"]) and parsed["JWT_SECRET"] != parsed["APP_SECRET"]
    assert parsed["CORS_ORIGINS"] == '["https://1-2-3-4.sslip.io"]'
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    # re-run (reboot / re-bootstrap): secrets are kept, values re-applied
    assert envfile.prepare(env, EXAMPLE, {"TLS_DOMAIN": "x.sslip.io"}) == []
    again = envfile.parse(env.read_text())
    assert again["ADMIN_PASSWORD"] == parsed["ADMIN_PASSWORD"] and again["TLS_DOMAIN"] == "x.sslip.io"
    ssm = envfile.ssm_values(env)
    assert ssm["admin_password"] == (parsed["ADMIN_PASSWORD"], True)
    assert ssm["admin_email"] == ("a@b.c", False)
    assert set(ssm) == {"admin_email", "admin_password", "app/APP_SECRET", "app/JWT_SECRET", "app/POSTGRES_PASSWORD"}


def test_pod_admin_email_replaces_the_empty_example_and_password_is_long(tmp_path: Path) -> None:
    """m1: .env.example ships ADMIN_EMAIL empty; the pod passes the real address (pod-bootstrap.sh)."""
    assert re.search(r"^ADMIN_EMAIL=$", EXAMPLE.read_text(), re.M)
    env = tmp_path / ".env"
    envfile.prepare(env, EXAMPLE, {"ADMIN_EMAIL": "planner@university.edu.tr", "ENVIRONMENT": "prod"})
    parsed = envfile.parse(env.read_text())
    assert parsed["ADMIN_EMAIL"] == "planner@university.edu.tr" and parsed["ENVIRONMENT"] == "prod"
    assert len(parsed["ADMIN_PASSWORD"]) >= 12  # backend refuses a shorter ADMIN_PASSWORD in prod (M3)
    assert all(len(envfile.random_password()) == 20 for _ in range(50))


def test_existing_pod_env_with_auth_secret_is_not_synced(tmp_path: Path) -> None:
    """Older pods keep AUTH_SECRET in .env (and /smartsched/app/AUTH_SECRET in SSM, harmless): never re-synced."""
    env = tmp_path / ".env"
    envfile.prepare(env, EXAMPLE, {"ADMIN_EMAIL": "a@b.c"})
    env.write_text(env.read_text() + "AUTH_SECRET=" + "f" * 64 + "\n")
    assert "app/AUTH_SECRET" not in envfile.ssm_values(env)


def _fake_docker(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text("#!/bin/sh\n[ \"$1 $2\" = 'compose version' ] && [ \"$3\" = --short ] && echo 2.29.0\nexit 0\n")
    fake.chmod(0o755)
    # health never comes up behind a fake docker: curl fails at once, sleep is a no-op and every `date +%s`
    # jumps 400 s, so wait_healthy gives up on its first lap instead of after 300 s
    (bin_dir / "curl").write_text("#!/bin/sh\nexit 7\n")
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "date").write_text("#!/bin/sh\n[ -f \"$0.n\" ] || echo 0 > \"$0.n\"; n=$(cat \"$0.n\"); "
                                  "echo $((n + 400)) > \"$0.n\"; echo $n\n")
    for name in ("curl", "sleep", "date"):
        (bin_dir / name).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "ADMIN_EMAIL"}
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '/usr/bin:/bin')}"
    return env


@pytest.mark.parametrize("email", ["", "admin@example.edu.tr", "ops@Example.org"])
def test_deploy_sh_refuses_empty_or_example_admin_email(tmp_path: Path, email: str) -> None:
    env = _fake_docker(tmp_path)
    env["ENV_FILE"] = str(tmp_path / ".env")
    if email:
        env["ADMIN_EMAIL"] = email
    proc = subprocess.run(["bash", str(REPO / "smartsched/deploy/deploy.sh"), "--no-build"], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0 and "ADMIN_EMAIL" in proc.stderr, proc.stderr
    assert "AUTH_SECRET" not in (tmp_path / ".env").read_text()


def test_deploy_sh_takes_admin_email_from_the_environment_on_first_run(tmp_path: Path) -> None:
    env = _fake_docker(tmp_path)
    env["ENV_FILE"] = str(tmp_path / ".env")
    env["ADMIN_EMAIL"] = "planner@university.edu.tr"
    subprocess.run(["bash", str(REPO / "smartsched/deploy/deploy.sh"), "--no-build"], env=env,
                   capture_output=True, text=True, timeout=60)
    parsed = envfile.parse((tmp_path / ".env").read_text())
    assert parsed["ADMIN_EMAIL"] == "planner@university.edu.tr"
    assert re.fullmatch(r"[A-Za-z0-9]{20}", parsed["ADMIN_PASSWORD"])
    assert re.fullmatch(r"[0-9a-f]{64}", parsed["APP_SECRET"]) and "AUTH_SECRET" not in parsed


def test_config_file_and_env_override(tmp_path: Path) -> None:
    f = tmp_path / "ci.env"
    f.write_text((POD_CI / "ci.env.example").read_text() + "PODCI_PUBLIC_URL='https://x'\n")
    cfg = config_mod.load(f, {"PODCI_DISK_MAX_PERCENT": "65", "PODCI_IDLE_STOP": "0", "HOME": "/x"})
    assert cfg.branches == ("claude/gracious-cerf-w1598m", "claude/smartsched-universal")
    assert cfg.public_url == "https://x" and cfg.disk_max_percent == 65 and cfg.idle_stop is False
    assert cfg.deploy_flags == ("--tls",) and cfg.state_dir == Path("/var/lib/smartsched-ci")
    assert cfg.idle_cpu == 5.0 and cfg.run_url(7) == "https://x/ci/runs/7"


def test_disk_cleanup_stops_once_below_limit(cfg: Config, store: Store) -> None:
    cfg.work_dir.mkdir(parents=True)
    (cfg.work_dir / "stale").mkdir()
    calls: list[list[str]] = []
    levels = iter([90.0, 90.0, 90.0, 69.0])
    taken = disk.ensure(cfg, store, lambda argv: calls.append(argv) or 0, usage=lambda: next(levels),
                        log=lambda _: None)
    assert taken == ["stale workspaces", "runs beyond the last 50", "dangling images + build cache above 4 GB"]
    assert not (cfg.work_dir / "stale").exists()
    assert ["docker", "image", "prune", "-af"] not in calls  # never escalated further than needed
    assert disk.ensure(cfg, store, lambda a: 0, usage=lambda: 50.0, log=lambda _: None) == []


def stat_line(busy: int, idle: int) -> str:
    return f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 2 3 4\n"


def test_cpu_times() -> None:
    assert runner.cpu_times(stat_line(30, 70)) == (30.0, 100.0)


def test_idle_stop_only_when_quiet_for_the_window(cfg: Config, store: Store, clock: Clock) -> None:
    cloud = NoCloud()
    t0 = clock.t
    busy = 0.0
    total = 0.0
    out = {}
    for minute in range(0, 64, 2):  # 2 % CPU for an hour
        busy += 2.4
        total += 120.0
        out = runner.heartbeat(cfg, store, cloud, t0 + minute * 60, uptime=7200, sample=(busy, total),
                               log=lambda _: None)
        if minute < 60:
            assert out["stop"] is False
    assert out["stop"] is True and out["cpu_percent"] == pytest.approx(2.0)
    assert ("stop", "i-local") in cloud.events
    assert ("heartbeat", False) in cloud.events


def test_no_idle_stop_while_ci_active_or_recently_booted(cfg: Config, store: Store, clock: Clock) -> None:
    cloud = NoCloud()
    for minute in range(0, 70, 2):
        runner.heartbeat(cfg, store, cloud, clock.t + minute * 60, uptime=600, sample=(minute * 0.01, minute * 120.0),
                         log=lambda _: None)
    assert not any(e[0] == "stop" for e in cloud.events)  # uptime < window
    run = store.enqueue("b", "a" * 40, deploy=False)
    assert run
    store.transition(run.id, RUNNING)
    out = runner.heartbeat(cfg, store, cloud, clock.t + 75 * 60, uptime=99999, sample=(1.0, 99999.0),
                           log=lambda _: None)
    assert out["ci_active"] and not out["stop"]
    assert ("heartbeat", True) in cloud.events


def test_shell_scripts_parse() -> None:
    scripts = [*sorted((POD_CI / "gates").glob("*.sh")), POD_CI / "install.sh", POD_CI / "pod-bootstrap.sh"]
    for s in scripts:
        subprocess.run(["bash", "-n", str(s)], check=True)
    if shutil.which("shellcheck"):
        subprocess.run(["shellcheck", "-S", "warning", "-x", "-P", "SCRIPTDIR", *map(str, scripts)], check=True)


def test_systemd_units_reference_real_commands() -> None:
    units = {p.name: p.read_text() for p in (POD_CI / "systemd").iterdir()}
    for name, text in units.items():
        if name.endswith(".service"):
            assert "ExecStart=" in text, name
            m = re.search(r"python3 -m podci (\w[\w-]*)", text)
            if m:
                assert m.group(1) in {"poll", "work", "web"}, name
    assert "PathChanged=/var/lib/smartsched-ci/queue-signal" in units["smartsched-ci-worker.path"]
    assert "OnUnitActiveSec=2min" in units["smartsched-ci-poll.timer"]
    installed = (POD_CI / "install.sh").read_text()
    for unit in ("smartsched-ci-web.service", "smartsched-ci-poll.timer", "smartsched-ci-worker.path",
                 "smartsched-ci-update.path", "smartsched-ci-worker.timer"):
        assert unit in installed and unit in units
