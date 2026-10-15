"""gates/backend.sh: a PostgreSQL service container for the PostgreSQL tests, and a migrations check that needs
exactly one Alembic head (never a pinned revision). Docker is a recording fake (tests/test_e2e_stack.py)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from podfakes import POD_CI, REPO
from test_e2e_stack import gate_env

GATE = POD_CI / "gates/backend.sh"
COMPOSE = REPO / "smartsched/deploy/docker-compose.yml"


def run_gate(tmp_path: Path, unhealthy: bool = False) -> tuple[subprocess.CompletedProcess[str], str]:
    env = gate_env(tmp_path)
    src = tmp_path / "ws/src/smartsched/deploy"
    src.mkdir(parents=True)
    shutil.copy(COMPOSE, src / "docker-compose.yml")
    env.update({"PG_READY_TRIES": "2", "PG_READY_SLEEP": "0"})
    if unhealthy:
        (tmp_path / "unhealthy").write_text("1")
    r = subprocess.run(["bash", str(GATE)], env=env, capture_output=True, text=True, timeout=60)
    log = (tmp_path / "docker.log").read_text() if (tmp_path / "docker.log").exists() else ""
    return r, log


def test_postgres_service_uses_the_compose_pin_and_reaches_the_tests(tmp_path: Path) -> None:
    r, log = run_gate(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    pin = re.search(r"image:\s*(postgres:\S+)", COMPOSE.read_text())
    assert pin and "@sha256:" in pin.group(1)
    lines = log.splitlines()
    pg = next(c for c in lines if c.startswith("run -d ") and "--network-alias postgres" in c)
    assert pin.group(1) in pg and "--tmpfs /var/lib/postgresql/data" in pg and "--network smartsched-ci-pg-" in pg
    tests = next(c for c in lines if c.startswith("run --rm --init") and "TEST_POSTGRES_URL=" in c)
    assert "--network smartsched-ci-pg-7-abc1234" in tests
    assert "TEST_POSTGRES_URL=postgresql+psycopg://postgres:ci-7-abc1234@postgres:5432/postgres" in tests
    assert any(c.startswith("exec ") and "pg_isready" in c for c in lines)
    assert lines[-2:] == ["rm -f smartsched-ci-pg-7-abc1234", "network rm smartsched-ci-pg-7-abc1234"]


def test_migrations_check_counts_heads_instead_of_pinning_one(tmp_path: Path) -> None:
    _, log = run_gate(tmp_path)
    assert "alembic heads" in log and 'grep -c "(head)"' in log
    assert 'DATABASE_URL="$PG_MIGRATE_URL" alembic upgrade head' in log
    assert not re.search(r"\b00\d\d_[a-z_]+", GATE.read_text()), "the gate must not name a migration revision"


def test_gate_fails_and_cleans_up_when_postgres_never_gets_ready(tmp_path: Path) -> None:
    r, log = run_gate(tmp_path, unhealthy=True)
    assert r.returncode == 1 and "postgres did not become ready" in r.stdout
    lines = log.splitlines()
    assert not any("TEST_POSTGRES_URL=" in c for c in lines)  # the tests never ran against nothing
    assert any(c.startswith("logs ") for c in lines) and lines[-1].startswith("network rm ")
