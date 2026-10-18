"""HB-14 alembic ``0048_helper_feedback``: three nullable columns on ``helper_events`` (``reason``, ``query``,
``note``), one head, SQLite and PostgreSQL round trips (the row-level-security policy of 0044 stays)."""

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

REV, PREV = "0048_helper_feedback", "0047_rf_import_safety"
COLUMNS = {"reason", "query", "note"}


def test_hb_14_single_head_and_parent() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1
    rev = script.get_revision(REV)
    assert rev is not None and rev.down_revision == PREV


def _cols(path) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute("pragma table_info(helper_events)")}
    finally:
        con.close()


def test_hb_14_sqlite_round_trip(tmp_path) -> None:
    path = tmp_path / "h.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, REV)
    assert COLUMNS <= _cols(path)
    from app.models.helper import HelperEvent

    assert {c.name for c in HelperEvent.__table__.columns} <= _cols(path)
    con = sqlite3.connect(path)
    con.execute(
        "insert into helper_events (ts, kind, reason, query, note) values"
        " ('2026-10-18 09:00:00', 'thumb_down', 'wrong_page', NULL, 'Yanlış sayfa')"
    )
    con.commit()
    con.close()
    _run(url, command.downgrade, PREV)
    assert not (COLUMNS & _cols(path)) and "kind" in _cols(path)
    _run(url, command.upgrade, "head")


def test_hb_14_postgres_round_trip(pg_server) -> None:  # noqa: F811
    name = f"t_{uuid.uuid4().hex[:12]}"
    base, _, query = pg_server.partition("?")
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = f"{base.rsplit('/', 1)[0]}/{name}" + (f"?{query}" if query else "")
    try:
        _run(url, command.upgrade, REV)
        eng = create_engine(url)
        have = {c["name"] for c in inspect(eng).get_columns("helper_events")}
        assert COLUMNS <= have
        with eng.connect() as c:
            on = c.execute(text("select relrowsecurity from pg_class where relname = 'helper_events'")).scalar()
            assert on is True
        eng.dispose()
        _run(url, command.downgrade, PREV)
        eng = create_engine(url)
        assert not (COLUMNS & {c["name"] for c in inspect(eng).get_columns("helper_events")})
        eng.dispose()
        _run(url, command.upgrade, "head")
    finally:
        admin.dispose()
        drop = create_engine(pg_server, isolation_level="AUTOCOMMIT")
        with drop.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        drop.dispose()
