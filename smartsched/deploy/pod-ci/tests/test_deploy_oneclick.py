"""One-click deploy (smartsched/deploy/deploy.sh): every deploy-time setting is a flag or an env variable, a dry
deploy of each seed profile runs end to end behind a fake docker, secrets never reach .env or a command line."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from podfakes import REPO

DEPLOY = REPO / "smartsched/deploy"
SCRIPT = DEPLOY / "deploy.sh"
_spec = importlib.util.spec_from_file_location("deploy_bootstrap_oc", DEPLOY / "seed/bootstrap_settings.py")
assert _spec and _spec.loader
boot = importlib.util.module_from_spec(_spec)
sys.modules["deploy_bootstrap_oc"] = boot
_spec.loader.exec_module(boot)

AI_KEY = "sk-ant-api03-" + "k" * 40
SMTP_PW = "smtp-secret-pw-99"


def fake_env(tmp_path: Path, healthy: bool = True) -> dict[str, str]:
    """docker records its argv in docker.log (one call per line); curl answers healthy (or never)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "docker.log"
    (bin_dir / "docker").write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {log}\n"
        "[ \"$1 $2\" = 'compose version' ] && [ \"$3\" = --short ] && echo 2.29.0\n"
        "exit 0\n")
    (bin_dir / "curl").write_text("#!/bin/sh\nexit 0\n" if healthy else "#!/bin/sh\nexit 7\n")
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
    for name in ("docker", "curl", "sleep"):
        (bin_dir / name).chmod(0o755)
    drop = {"ADMIN_EMAIL", "SEED_PROFILE", "OBSERVABILITY", *boot.ALL_KEYS}
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update({"PATH": f"{bin_dir}:{env.get('PATH', '/usr/bin:/bin')}", "ENV_FILE": str(tmp_path / ".env"),
                "PROFILE_FILE": str(tmp_path / "profile.env"), "SEED_FILES_DIR": str(tmp_path / "files")})
    (tmp_path / "files").mkdir()
    return env


def deploy(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), "--no-build", *args], env=env, capture_output=True, text=True,
                          timeout=120)


def calls(tmp_path: Path) -> list[str]:
    f = tmp_path / "docker.log"
    return f.read_text().splitlines() if f.exists() else []


def env_file(tmp_path: Path) -> dict[str, str]:
    out = {}
    for line in (tmp_path / ".env").read_text().splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def test_bash_syntax() -> None:
    for script in ("deploy.sh", "backup.sh", "validate.sh", "purge-uploads.sh", "pod-ci/pod-bootstrap.sh",
                   "pod-ci/install.sh"):
        r = subprocess.run(["bash", "-n", str(DEPLOY / script)], capture_output=True, text=True)
        assert r.returncode == 0, f"{script}: {r.stderr}"


def test_help_lists_every_deploy_time_flag() -> None:
    r = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    for flag in ("--domain", "--admin-email", "--profile", "--org-name", "--ai-provider", "--smtp-host",
                 "--smtp-port", "--smtp-security", "--smtp-user", "--smtp-from", "--security-contact",
                 "--observability", "--no-tls", "AI_API_KEY", "SMTP_PASSWORD"):
        assert flag in r.stdout, flag


def test_settings_keys_match_the_bootstrap_tool() -> None:
    text = SCRIPT.read_text()
    m = re.search(r"^SETTINGS_KEYS=\(([^)]*)\)", text, re.M)
    assert m, "SETTINGS_KEYS=(...) in deploy.sh"
    assert tuple(m.group(1).split()) == boot.ALL_KEYS


@pytest.mark.parametrize("profile", ["institution", "empty"])
def test_dry_deploy_of_each_profile(tmp_path: Path, profile: str) -> None:
    env = fake_env(tmp_path)
    (tmp_path / "profile.env").write_text(f"SEED_PROFILE={profile}\n")
    if profile == "institution":
        for f in ("bahar_derslikler_takvimi_2026.xlsx", "bahar_derslik_planlama_listesi_v5.xlsx",
                  "guz_derslikler_takvimi_2026_2027.xlsx", "guz_derslik_planlama_2026_2027_v2.xlsx",
                  "final_derslikler_takvimi_2026_v2.xlsx", "final_planlama_listesi_2026_v2.xlsx", "room_master.csv"):
            (tmp_path / "files" / f).write_text("x")
    r = deploy(env, "--admin-email", "admin@uni.edu.tr")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(tmp_path)
    assert any(" up -d " in f" {c} " for c in log)
    seeded = [c for c in log if "/seed/tool/seed.py run" in c]
    assert bool(seeded) == (profile == "institution")
    assert not [c for c in log if "bootstrap_settings.py" in c]  # no deploy-time settings given: no extra container
    assert "SmartSched is up:  http://localhost:8080" in r.stdout
    assert f"Seed profile:      {profile}" in r.stdout
    assert env_file(tmp_path)["ADMIN_EMAIL"] == "admin@uni.edu.tr"


def test_profile_flag_overrides_the_file_and_refuses_unknown(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    (tmp_path / "profile.env").write_text("SEED_PROFILE=institution\n")
    r = deploy(env, "--admin-email=admin@uni.edu.tr", "--profile=empty")
    assert r.returncode == 0, r.stderr
    assert "Seed profile:      empty" in r.stdout and not [c for c in calls(tmp_path) if "seed.py run" in c]
    bad = deploy(fake_env(tmp_path / "b"), "--admin-email", "admin@uni.edu.tr", "--profile", "demo")
    assert bad.returncode != 0 and "empty or institution" in bad.stderr


def test_domain_flag_writes_tls_env_and_adds_caddy(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    r = deploy(env, "--admin-email", "admin@uni.edu.tr", "--domain", "panel.uni.edu.tr")
    assert r.returncode == 0, r.stdout + r.stderr
    e = env_file(tmp_path)
    assert e["TLS_DOMAIN"] == "panel.uni.edu.tr" and e["PUBLIC_URL"] == "https://panel.uni.edu.tr"
    assert e["CORS_ORIGINS"] == '["https://panel.uni.edu.tr"]' and e["ACME_EMAIL"] == "admin@uni.edu.tr"
    assert all("docker-compose.caddy.yml" in c for c in calls(tmp_path) if c.startswith("compose ") and " up " in c)
    assert "SmartSched is up:  https://panel.uni.edu.tr" in r.stdout
    # later runs keep HTTPS without repeating the flag; --no-tls drops it for one run
    (tmp_path / "docker.log").unlink()
    assert deploy(env).returncode == 0
    ups = [c for c in calls(tmp_path) if " up -d" in c]
    assert ups and all("docker-compose.caddy.yml" in c for c in ups)
    (tmp_path / "docker.log").unlink()
    assert deploy(env, "--no-tls").returncode == 0
    assert not [c for c in calls(tmp_path) if "docker-compose.caddy.yml" in c]


@pytest.mark.parametrize("bad", ["http://x.tr", "a b", "x;rm"])
def test_domain_flag_refuses_non_hostnames(tmp_path: Path, bad: str) -> None:
    r = deploy(fake_env(tmp_path), "--admin-email", "admin@uni.edu.tr", "--domain", bad)
    assert r.returncode != 0 and "--domain" in r.stderr


def test_settings_go_to_the_database_once_never_to_env_or_argv(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    env.update({"AI_API_KEY": AI_KEY, "SMTP_PASSWORD": SMTP_PW})
    r = deploy(env, "--admin-email", "admin@uni.edu.tr", "--org-name", "Örnek Üniversitesi", "--smtp-host",
               "smtp.uni.edu.tr", "--smtp-port", "587", "--smtp-user", "noreply@uni.edu.tr", "--smtp-from",
               "noreply@uni.edu.tr", "--security-contact", "security@uni.edu.tr", "--ai-provider", "anthropic")
    assert r.returncode == 0, r.stdout + r.stderr
    runs = [c for c in calls(tmp_path) if "bootstrap_settings.py run" in c]
    assert len(runs) == 1
    for k in ("ORG_NAME", "AI_API_KEY", "AI_PROVIDER", "SMTP_HOST", "SMTP_PASSWORD", "SECURITY_CONTACT"):
        assert f"-e {k} " in runs[0], k
    everything = "\n".join(calls(tmp_path)) + (tmp_path / ".env").read_text() + r.stdout + r.stderr
    assert AI_KEY not in everything and SMTP_PW not in everything
    assert "AI_API_KEY=<set>" in r.stdout  # the plan, before the build


def test_bad_settings_stop_before_anything_is_built(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    r = deploy(env, "--admin-email", "admin@uni.edu.tr", "--smtp-port", "587")
    assert r.returncode != 0 and "SMTP_HOST" in r.stderr
    assert not [c for c in calls(tmp_path) if " up " in f" {c} " or " build" in c]


def test_admin_password_is_shown_once_on_the_first_deploy(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    env["SHOW_ADMIN_PASSWORD"] = "1"  # a terminal; a pod / CI log never shows it (stdout is not a TTY)
    first = deploy(env, "--admin-email", "admin@uni.edu.tr")
    pw = env_file(tmp_path)["ADMIN_PASSWORD"]
    assert first.returncode == 0 and pw in first.stdout and "shown once" in first.stdout
    second = deploy(env)
    assert second.returncode == 0 and pw not in second.stdout and "ADMIN_PASSWORD in" in second.stdout
    quiet = fake_env(tmp_path / "q")
    r = deploy(quiet, "--admin-email", "admin@uni.edu.tr")
    assert env_file(tmp_path / "q")["ADMIN_PASSWORD"] not in r.stdout  # not a TTY: never printed


def test_admin_email_flag_after_the_first_start_warns(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    assert deploy(env, "--admin-email", "admin@uni.edu.tr").returncode == 0
    r = deploy(env, "--admin-email", "other@uni.edu.tr")
    assert r.returncode == 0 and "first start only" in r.stderr
    assert env_file(tmp_path)["ADMIN_EMAIL"] == "admin@uni.edu.tr"


def test_observability_flag_and_env(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    assert deploy(env, "--admin-email", "admin@uni.edu.tr", "--observability").returncode == 0
    assert any("--profile observability" in c for c in calls(tmp_path) if " up -d" in c)
    env2 = fake_env(tmp_path / "o")
    env2["OBSERVABILITY"] = "1"
    assert deploy(env2, "--admin-email", "admin@uni.edu.tr").returncode == 0
    assert env_file(tmp_path / "o")["OBSERVABILITY"] == "1"
    assert any("--profile observability" in c for c in calls(tmp_path / "o") if " up -d" in c)
