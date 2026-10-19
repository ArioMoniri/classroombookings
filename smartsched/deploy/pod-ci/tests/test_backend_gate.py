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


def run_gate(tmp_path: Path, unhealthy: bool = False,
             gate: Path = GATE) -> tuple[subprocess.CompletedProcess[str], str]:
    env = gate_env(tmp_path)
    src = tmp_path / "ws/src/smartsched/deploy"
    src.mkdir(parents=True)
    shutil.copy(COMPOSE, src / "docker-compose.yml")
    env.update({"PG_READY_TRIES": "2", "PG_READY_SLEEP": "0"})
    if unhealthy:
        (tmp_path / "unhealthy").write_text("1")
    r = subprocess.run(["bash", str(gate)], env=env, capture_output=True, text=True, timeout=60)
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
    # one postgres per gate (GATE_NAME, default backend): gates may run concurrently
    assert lines[-2:] == ["rm -f smartsched-ci-pg-7-abc1234-backend", "network rm smartsched-ci-pg-7-abc1234-backend"]


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


def test_saml_library_comes_from_the_lock_and_is_required(tmp_path: Path) -> None:
    # SAML 2.0 is built in (owner 2026-10-17): signxml is pinned in requirements.lock, installed with it, and the
    # gate fails if it is missing instead of letting tests/test_w3b_idp_saml.py skip.
    _, log = run_gate(tmp_path, gate=POD_CI / "gates/backend-deps.sh")  # the venv is built once per run here
    assert "--require-hashes -r smartsched/backend/requirements-dev.lock" in log
    assert re.search(r'^python -c "import signxml', log, re.M)
    (tmp_path / "b").mkdir()
    _, log = run_gate(tmp_path / "b", gate=GATE)  # and checked again where the tests run
    assert re.search(r'^python -c "import signxml', log, re.M) and "pip install" not in log
    for name in ("requirements.lock", "requirements-dev.lock"):
        lock = (REPO / "smartsched/backend" / name).read_text()
        assert re.search(r"^signxml==\d+\.\d+\.\d+ \\$", lock, re.M), name


UNIT = POD_CI / "gates/backend-unit.sh"


def test_backend_gate_runs_the_static_checks_and_leaves_pytest_to_the_shards(tmp_path: Path) -> None:
    _, log = run_gate(tmp_path)
    assert "make lint type" in log and "make check" not in log and "python -m pytest tests/solver -q" in log
    from podci.gates import GATES

    gates = {g.name: g for g in GATES}
    shards = [g for g in GATES if g.script == "backend-unit.sh"]
    assert [g.args for g in shards] == [("1/3",), ("2/3",), ("3/3",)]
    assert all(g.timeout == 3600 for g in shards) and gates["backend"].timeout == 1800
    for name in ("e2e-real-1", "e2e-real-2", "e2e-real-3", "parity", "planner"):
        assert {"backend", *(g.name for g in shards)} <= set(gates[name].needs), name


def test_backend_unit_shard_runs_pytest_on_its_files_against_postgres(tmp_path: Path) -> None:
    env = gate_env(tmp_path)
    src = tmp_path / "ws/src/smartsched/deploy"
    src.mkdir(parents=True)
    shutil.copy(COMPOSE, src / "docker-compose.yml")
    env.update({"PG_READY_TRIES": "2", "PG_READY_SLEEP": "0"})
    env["GATE_NAME"] = "backend-unit-2"
    r = subprocess.run(["bash", str(UNIT), "2/3"], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    log = (tmp_path / "docker.log").read_text()
    tests = next(c for c in log.splitlines() if c.startswith("run --rm --init") and "TEST_POSTGRES_URL=" in c)
    assert "-e SHARD_INDEX=2 -e SHARD_COUNT=3" in tests
    assert "--network smartsched-ci-pg-7-abc1234-backend-unit-2" in tests  # its own postgres, not backend's
    assert 'python -m pytest -q --ignore=tests/solver -m "not slow"' in log
    assert log.splitlines()[-1].startswith("network rm ")
    for bad in ("0/3", "4/3", "1", "1/3; rm -rf /"):
        b = subprocess.run(["bash", str(UNIT), bad], env=env, capture_output=True, text=True, timeout=60)
        assert b.returncode == 2 and "bad shard" in b.stdout, bad


def test_backend_unit_shards_partition_every_make_test_file() -> None:
    """The shard file lists (the pipeline of backend-unit.sh, run on the real tests/) cover each file once."""
    script = UNIT.read_text()
    pipeline = re.search(r"mapfile -t files < <\((.*?)\)\necho", script, re.S)
    assert pipeline
    cmd = pipeline.group(1).replace("\\\n", " ")
    backend = REPO / "smartsched/backend"
    shards = []
    for i in (1, 2, 3):
        out = subprocess.run(["bash", "-c", cmd], cwd=backend, env={"PATH": "/usr/bin:/bin", "SHARD_INDEX": str(i),
                             "SHARD_COUNT": "3"}, capture_output=True, text=True, check=True).stdout.split()
        shards.append(out)
    every = sorted(str(p.relative_to(backend)) for p in (backend / "tests").rglob("*.py")
                   if (p.name.startswith("test_") or p.name.endswith("_test.py"))
                   and not str(p.relative_to(backend)).startswith("tests/solver/"))
    assert all(shards) and sorted(f for s in shards for f in s) == every
    assert len(every) > 100
