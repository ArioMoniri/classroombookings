"""alembic ``0041_adaptive`` (AS-03 / AS-05 / AS-13): season_profiles, season_segments, demand_events,
learning_versions, learned_prior_snapshots. Upgrade + downgrade on SQLite and PostgreSQL (``tests/pg_support``;
skipped without a server); exactly one head; the model tables match the migrated columns."""

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

REV = "0041_adaptive"
TABLES = ("season_profiles", "season_segments", "demand_events", "learning_versions", "learned_prior_snapshots")


def _prev() -> str:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    rev = ScriptDirectory.from_config(cfg).get_revision(REV)
    assert rev is not None
    return str(rev.down_revision)


def test_as_03_single_head() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


def _model_cols(table: str) -> set[str]:
    from app.models import Base

    return set(Base.metadata.tables[table].columns.keys())


def test_as_03_sqlite_round_trip(tmp_path) -> None:
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, _prev())
    _run(url, command.upgrade, REV)
    con = sqlite3.connect(path)
    try:
        for t in TABLES:
            cols = {r[1] for r in con.execute(f"pragma table_info({t})")}
            assert cols == _model_cols(t), (t, cols ^ _model_cols(t))
        # the ledger has no personal column (KVKK)
        cols = {r[1] for r in con.execute("pragma table_info(demand_events)")}
        assert not {"user_id", "email", "query", "text"} & cols
    finally:
        con.close()
    _run(url, command.downgrade, _prev())
    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert not set(TABLES) & names
    _run(url, command.upgrade, "head")


def test_as_03_postgres_round_trip(pg_server) -> None:  # noqa: F811
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
        for t in TABLES:
            assert {c["name"] for c in insp.get_columns(t)} == _model_cols(t)
        with eng.begin() as c:
            c.execute(
                text(
                    "insert into season_profiles (key, version, name_tr, name_en, applies_to, solver_weights, "
                    "booking_overlays, explanation, evidence, created_at, updated_at) values ('bahar', 1, 'Bahar', "
                    "'Spring', '[]', '{}', '[]', '{}', '{}', now(), now())"
                )
            )
            assert c.execute(text("select status, peak_threshold_pct from season_profiles")).one() == ("draft", 85)
        eng.dispose()
        _run(url, command.downgrade, _prev())
        eng = create_engine(url)
        assert not set(TABLES) & set(inspect(eng).get_table_names())
        eng.dispose()
        _run(url, command.upgrade, REV)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
