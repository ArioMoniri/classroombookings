"""RF-B alembic ``0047_rf_import_safety``: ``import_jobs.created_by_id`` / ``actor``, ``weeks.edited`` and the
``catalog_aliases`` table. One head; SQLite round trip keeps old rows (actor unknown, weeks not edited)."""

from __future__ import annotations

import sqlite3

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.main import BACKEND_DIR

from tests.test_crbs_migration import _run

REV, PREV = "0047_rf_import_safety", "0046_ai_quota_units"


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


def test_sqlite_round_trip_keeps_old_rows(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREV)
    con = sqlite3.connect(path)
    con.execute(
        "insert into terms (code, name, kind, week_count, is_active, created_at, updated_at)"
        " values ('2026-GUZ', 'Güz', 'REGULAR', 14, 0, '2026-10-18 08:00:00', '2026-10-18 08:00:00')"
    )
    con.execute("insert into weeks (term_id, \"index\", kind, label) values (1, 1, 'LECTURE', '21-27 Eylül')")
    con.execute(
        "insert into import_jobs (kind, filename, status, summary, created_at)"
        " values ('weekly-grid', 'guz.xlsx', 'DONE', '{}', '2026-10-18 08:00:00')"
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, REV)
    assert {"created_by_id", "actor"} <= _columns(path, "import_jobs")
    assert "edited" in _columns(path, "weeks")
    assert {"entity", "alias", "target_id"} <= _columns(path, "catalog_aliases")
    con = sqlite3.connect(path)
    assert con.execute("select created_by_id, actor from import_jobs").fetchall() == [(None, None)]
    assert con.execute("select edited from weeks").fetchall() == [(0,)]
    con.close()
    _run(url, command.downgrade, PREV)
    assert "actor" not in _columns(path, "import_jobs") and "edited" not in _columns(path, "weeks")
    assert not _columns(path, "catalog_aliases")
    _run(url, command.upgrade, "head")
