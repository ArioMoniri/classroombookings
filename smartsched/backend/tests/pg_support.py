"""A real PostgreSQL for the concurrency tests (ROADMAP: booking race and competing approvals on Postgres).

``TEST_POSTGRES_URL`` (CI service, e.g. ``postgresql+psycopg://postgres:pw@localhost:5432/postgres``) is used when
set; otherwise a throwaway cluster is started from the local PostgreSQL binaries (``initdb`` + ``pg_ctl``, Unix
socket only, no TCP port), owned by the ``postgres`` system user when the tests run as root. Without either the
tests are skipped. Every test gets a fresh database, migrated with Alembic (the production path, not create_all).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

PG_BIN = Path("/usr/lib/postgresql/16/bin")
SOCKET_PORT = "18891"  # names the Unix socket only (listen_addresses is empty)


def _as_postgres(cmd: list[str]) -> list[str]:
    if os.geteuid() != 0:
        return cmd
    return ["su", "postgres", "-s", "/bin/sh", "-c", " ".join(cmd)]


@pytest.fixture(scope="session")
def pg_server() -> Iterator[str]:
    """``postgresql+psycopg://...`` of a server where databases may be created."""
    url = os.environ.get("TEST_POSTGRES_URL")
    if url:
        yield url
        return
    if not (PG_BIN / "initdb").exists():
        pytest.skip("no PostgreSQL: set TEST_POSTGRES_URL or install postgresql-16")
    root = Path(tempfile.mkdtemp(prefix="backend-backlog-pg-"))
    os.chmod(root, 0o777)
    data = root / "data"
    try:
        subprocess.run(
            _as_postgres([str(PG_BIN / "initdb"), "-D", str(data), "-A", "trust", "-U", "postgres", "-E", "UTF8"]),
            check=True,
            capture_output=True,
        )
        opts = f"'-p {SOCKET_PORT} -k {root} -c listen_addresses= -c max_connections=60'"
        subprocess.run(
            _as_postgres([str(PG_BIN / "pg_ctl"), "-D", str(data), "-o", opts, "-l", str(root / "log"), "-w", "start"]),
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        shutil.rmtree(root, ignore_errors=True)
        pytest.skip(f"could not start a local PostgreSQL: {exc}")
    try:
        yield f"postgresql+psycopg://postgres@/postgres?host={root}&port={SOCKET_PORT}"
    finally:
        subprocess.run(
            _as_postgres([str(PG_BIN / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"]), capture_output=True
        )
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def pg_url(pg_server: str) -> Iterator[str]:
    """A fresh database on ``pg_server``, migrated to head with Alembic."""
    from alembic import command

    from tests.test_crbs_migration import _run

    name = f"t_{uuid.uuid4().hex[:12]}"
    base, _, query = pg_server.partition("?")
    admin = create_engine(pg_server.replace("+psycopg", "+psycopg"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = f"{base.rsplit('/', 1)[0]}/{name}" + (f"?{query}" if query else "")
    _run(url, command.upgrade, "head")
    try:
        yield url
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
