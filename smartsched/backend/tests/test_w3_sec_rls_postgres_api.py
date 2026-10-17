"""W3-SEC: the booking, approval, KVKK, calendar-feed and teacher-preference API suites, re-run on PostgreSQL with
row-level security on (alembic 0035_rls_policies, app/core/rls.py): the policies must not break any API path.

The test functions are the original ones (imported from their modules); only the ``client`` fixture differs: it
points the app at a fresh PostgreSQL database migrated with Alembic (cloned from one migrated template per session).
Same skip rules as tests/test_w3_sec_rls_postgres.py (``SMARTSCHED_PG_URL`` / ``TEST_POSTGRES_URL`` / local binaries).
"""

from __future__ import annotations

import importlib
import inspect
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

if os.environ.get("SMARTSCHED_PG_URL"):
    os.environ.setdefault("TEST_POSTGRES_URL", os.environ["SMARTSCHED_PG_URL"])

from app.core import db as dbmod  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.seed import seed_admin  # noqa: E402
from app.workers import queue as qmod  # noqa: E402

from tests.pg_support import pg_server  # noqa: E402, F401

SUITES = (
    "tests.test_wave1_approvals",
    "tests.test_approval_first_bookings",
    "tests.test_approvals_sweeper",
    "tests.test_wave2_kvkk",
    "tests.test_calendar_feeds",
    "tests.test_p19_t2_teacher_preferences",
    "tests.test_crbs_bookings",
    "tests.test_wave2_conflicts",
)


def _split(url: str) -> tuple[str, str]:
    base, _, query = url.partition("?")
    return base.rsplit("/", 1)[0], (f"?{query}" if query else "")


@pytest.fixture(scope="session")
def pg_template(pg_server: str) -> Iterator[str]:  # noqa: F811
    from alembic import command

    from tests.test_crbs_migration import _run

    name = f"tpl_{uuid.uuid4().hex[:10]}"
    root, query = _split(pg_server)
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    _run(f"{root}/{name}{query}", command.upgrade, "head")
    try:
        yield name
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def pg_db(pg_server: str, pg_template: str) -> Iterator[str]:  # noqa: F811
    name = f"t_{uuid.uuid4().hex[:12]}"
    root, query = _split(pg_server)
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{pg_template}"'))
    try:
        yield f"{root}/{name}{query}"
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def client(pg_db, tmp_path, monkeypatch) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    dbmod.configure_engine(pg_db)
    async with dbmod.get_session_factory()() as s:
        await seed_admin(s)
    qmod.reset_queue()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await qmod.get_queue().shutdown()
    await dbmod.dispose_engine()


@pytest.fixture
async def engine(pg_db):  # type: ignore[no-untyped-def]
    eng = dbmod.configure_engine(pg_db)
    yield eng
    await dbmod.dispose_engine()


def _adopt() -> None:
    """Pull every test function and module fixture of :data:`SUITES` into this module (``client`` and ``engine``
    stay the PostgreSQL ones above)."""
    g = globals()
    for mod_name in SUITES:
        mod = importlib.import_module(mod_name)
        short = mod_name.rsplit(".", 1)[1].removeprefix("test_")
        for attr, obj in vars(mod).items():
            if attr in {"client", "engine", "session", "pg_server", "pg_url"}:
                continue
            if attr.startswith("test_") and inspect.isfunction(obj) and obj.__module__ == mod.__name__:
                g[f"test_pg_{short}__{attr.removeprefix('test_')}"] = obj
            elif type(obj).__name__ == "FixtureFunctionDefinition" and attr not in g:
                g[attr] = obj


_adopt()
