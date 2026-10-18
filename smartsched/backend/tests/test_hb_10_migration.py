"""HB-10 alembic ``0046_ai_quota_units``: the unit snapshot columns on ``ai_usage`` and the shared
``ai_reservations`` table. One head; upgrade and downgrade on SQLite and on PostgreSQL (``tests/pg_support``;
skipped without a server); old rows keep NULL units."""

from __future__ import annotations

import sqlite3
import uuid

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.main import BACKEND_DIR
from sqlalchemy import create_engine, inspect, text

from tests.pg_support import pg_server  # noqa: F401
from tests.test_crbs_migration import _run

REV, PREV = "0046_ai_quota_units", "0045_user_sessions"


def _columns(path, table: str) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute(f"pragma table_info({table})")}
    finally:
        con.close()


def test_chains_on_the_previous_head_and_heads_stay_single() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1
    rev = script.get_revision(REV)
    assert rev is not None and rev.down_revision == PREV


def test_sqlite_round_trip_keeps_old_rows(tmp_path) -> None:
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREV)
    con = sqlite3.connect(path)
    con.execute(
        "insert into ai_usage (created_at, user_id, feature, provider, model, input_tokens, output_tokens,"
        " cache_read_tokens, cache_write_tokens, cost_usd, latency_ms, outcome, prompt_chars)"
        " values ('2026-10-18 08:00:00', null, 'chat', 'anthropic', 'claude', 10, 0, 0, 0, 0, 0, 'ok', 0)"
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, REV)
    assert {"department_id", "faculty_id"} <= _columns(path, "ai_usage")
    assert {"kind", "user_id", "faculty_id", "department_id", "tokens", "expires_at"} <= _columns(
        path, "ai_reservations"
    )
    con = sqlite3.connect(path)
    assert con.execute("select department_id, faculty_id, input_tokens from ai_usage").fetchall() == [(None, None, 10)]
    con.close()
    _run(url, command.downgrade, PREV)
    assert "faculty_id" not in _columns(path, "ai_usage") and not _columns(path, "ai_reservations")
    _run(url, command.upgrade, "head")


def test_postgres_round_trip(pg_server) -> None:  # noqa: F811
    name = f"t_{uuid.uuid4().hex[:12]}"
    base, _, query = pg_server.partition("?")
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = f"{base.rsplit('/', 1)[0]}/{name}" + (f"?{query}" if query else "")
    try:
        _run(url, command.upgrade, REV)
        eng = create_engine(url)
        insp = inspect(eng)
        assert "ai_reservations" in insp.get_table_names()
        assert {"department_id", "faculty_id"} <= {c["name"] for c in insp.get_columns("ai_usage")}
        assert "ix_ai_usage_created_faculty" in {i["name"] for i in insp.get_indexes("ai_usage")}
        eng.dispose()
        _run(url, command.downgrade, PREV)
        eng = create_engine(url)
        assert "ai_reservations" not in inspect(eng).get_table_names()
        eng.dispose()
        _run(url, command.upgrade, "head")
    finally:
        admin.dispose()
        drop = create_engine(pg_server, isolation_level="AUTOCOMMIT")
        with drop.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        drop.dispose()
