"""Alembic 0003_council creates the blackboard tables and matches the ORM models."""

from __future__ import annotations

import sqlite3

from app.core import db as dbmod
from app.main import init_database
from app.models import Base


async def test_council_tables_are_migrated(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'dev.db'}"
    dbmod.configure_engine(url)
    try:
        assert await init_database(url, "dev") == "migrate"
        con = sqlite3.connect(tmp_path / "dev.db")
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        assert {"council_jobs", "council_steps", "council_artifacts"} <= tables
        for table in ("council_jobs", "council_steps", "council_artifacts"):
            cols = {r[1] for r in con.execute(f"pragma table_info({table})")}
            assert cols == {c.name for c in Base.metadata.tables[table].columns}, table
        assert con.execute("select version_num from alembic_version").fetchone()[0] == "0003_council"
        con.close()
    finally:
        await dbmod.dispose_engine()
