"""F1: dev startup migrates SQLite databases instead of ``create_all`` (schema drift broke every run)."""

from __future__ import annotations

import logging
import sqlite3

from app.core import db as dbmod
from app.main import init_database


async def test_new_dev_db_is_migrated_and_idempotent(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'dev.db'}"
    dbmod.configure_engine(url)
    try:
        assert await init_database(url, "dev") == "migrate"
        con = sqlite3.connect(tmp_path / "dev.db")
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        cols = {r[1] for r in con.execute("pragma table_info(constraints)")}
        assert "alembic_version" in tables and "rooms" in tables and "source_ref" in cols
        con.close()
        assert await init_database(url, "dev") == "migrate"  # second start: no-op upgrade
    finally:
        await dbmod.dispose_engine()


async def test_legacy_create_all_db_reports_missing_columns(tmp_path, caplog):
    path = tmp_path / "legacy.db"
    url = f"sqlite+aiosqlite:///{path}"
    dbmod.configure_engine(url)
    try:
        await dbmod.create_all()
        await dbmod.dispose_engine()
        con = sqlite3.connect(path)
        con.execute("alter table constraints drop column source_ref")
        con.commit()
        con.close()
        dbmod.configure_engine(url)
        with caplog.at_level(logging.WARNING, logger="smartsched"):
            assert await init_database(url, "dev") == "legacy"
        assert any("constraints.source_ref" in r.getMessage() for r in caplog.records)
    finally:
        await dbmod.dispose_engine()


async def test_test_environment_keeps_create_all(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 't.db'}"
    dbmod.configure_engine(url)
    try:
        assert await init_database(url, "test") == "create_all"
    finally:
        await dbmod.dispose_engine()
