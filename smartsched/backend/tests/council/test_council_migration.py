"""Alembic 0020_council creates the blackboard tables and matches the ORM models.

The test does not pin the head: after ``upgrade head`` the council tables and columns must exist, the database
must be at the script's (single) head, and 0020_council must be in that head's history, so a later migration
does not break it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core import db as dbmod
from app.main import init_database
from app.models import Base

BACKEND = Path(__file__).resolve().parents[2]


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
        current = con.execute("select version_num from alembic_version").fetchone()[0]
        con.close()
        script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
        assert script.get_heads() == [current]  # upgraded to the one head, whatever its number
        history = {rev.revision for rev in script.walk_revisions(base="base", head=current)}
        assert "0020_council" in history
    finally:
        await dbmod.dispose_engine()
