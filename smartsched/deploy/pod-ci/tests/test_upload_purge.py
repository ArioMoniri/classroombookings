"""30-day retention purge for stored uploads (review P19-Q3 / KVKK): smartsched/deploy/purge-uploads.sh and the
pod's daily timer. Room photos and the organisation logo (uploads/rooms, public assets) are never purged."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from podfakes import POD_CI, REPO

SCRIPT = REPO / "smartsched/deploy/purge-uploads.sh"
DAY = 86400


def tree(root: Path) -> dict[str, Path]:
    now = time.time()
    files = {
        "rooms/3.jpg": 400, "rooms/org-logo.png": 90,  # public assets: kept whatever their age
        "imports/7_Bahar.xlsx": 31, "imports/8_Guz.xlsx": 29,
        "intake/12/memo.pdf": 45, "intake/13/new.eml": 1,
    }
    out = {}
    for rel, age in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        os.utime(p, (now - age * DAY, now - age * DAY))
        out[rel] = p
    return out


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=60,
                          env={**os.environ, **(env or {})})


def test_purges_files_older_than_30_days_except_room_assets(tmp_path: Path) -> None:
    f = tree(tmp_path)
    r = run("--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    left = {k for k, p in f.items() if p.exists()}
    assert left == {"rooms/3.jpg", "rooms/org-logo.png", "imports/8_Guz.xlsx", "intake/13/new.eml"}
    assert not (tmp_path / "intake/12").exists()  # emptied job directory removed
    assert (tmp_path / "imports").is_dir() and (tmp_path / "rooms").is_dir()  # top-level dirs stay
    assert "removed 2 file(s)" in r.stdout


def test_dry_run_and_days(tmp_path: Path) -> None:
    f = tree(tmp_path)
    r = run("--dir", str(tmp_path), "--dry-run")
    assert r.returncode == 0 and all(p.exists() for p in f.values())
    assert "would remove" in r.stdout and "imports/7_Bahar.xlsx" in r.stdout and "rooms/" not in r.stdout
    r = run("--dir", str(tmp_path), "--days", "7")
    assert r.returncode == 0
    assert not f["imports/8_Guz.xlsx"].exists() and f["intake/13/new.eml"].exists()


def test_refuses_bad_input(tmp_path: Path) -> None:
    assert run("--dir", str(tmp_path / "absent")).returncode == 0  # nothing uploaded yet
    assert run("--dir", str(tmp_path), "--days", "0").returncode == 2
    assert run("--dir", "/", "--days", "30").returncode == 2  # never the filesystem root


def test_compose_mode_runs_in_a_one_off_backend_container(tmp_path: Path) -> None:
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / ".env").write_text("UPLOAD_RETENTION_DAYS=45\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FAKE_LOG"\ncat > /dev/null\n')
    (bin_dir / "docker").chmod(0o755)
    r = run("--deploy-dir", str(deploy), env={"PATH": f"{bin_dir}:{os.environ['PATH']}",
                                             "FAKE_LOG": str(tmp_path / "log")})
    assert r.returncode == 0, r.stderr
    call = (tmp_path / "log").read_text().strip()
    assert call.startswith("compose --env-file .env -f docker-compose.yml run --rm --no-deps -T --entrypoint bash")
    assert "backend -s -- --in-container --days 45" in call


def test_pod_timer_runs_the_purge_daily_and_catches_up_after_a_stop() -> None:
    svc = (POD_CI / "systemd/smartsched-upload-purge.service").read_text()
    timer = (POD_CI / "systemd/smartsched-upload-purge.timer").read_text()
    assert "ExecStart=/opt/smartsched/src/smartsched/deploy/purge-uploads.sh" in svc
    assert "SupplementaryGroups=docker" in svc and "Type=oneshot" in svc
    assert "OnCalendar=daily" in timer and "Persistent=true" in timer  # the pod idle-stops: run after boot
    assert "smartsched-upload-purge.timer" in (POD_CI / "install.sh").read_text()
    env_example = (REPO / "smartsched/deploy/.env.example").read_text()
    assert "\nUPLOAD_RETENTION_DAYS=30\n" in env_example
