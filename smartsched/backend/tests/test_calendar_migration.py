"""alembic 0011_integrations: existing plaintext ``users.calendar_token`` links become SHA-256 rows (the links keep
working) and the plaintext column is gone; the migrated schema matches the models."""

from __future__ import annotations

import hashlib
import os
import sqlite3

from alembic import command
from alembic.config import Config
from app.main import BACKEND_DIR


def _cfg(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _run(url: str, fn, rev: str) -> None:  # type: ignore[no-untyped-def]
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        fn(_cfg(url), rev)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def test_plaintext_tokens_are_hashed_and_dropped(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "0006_token_version")
    con = sqlite3.connect(path)
    token = "Ab3_legacy-token-from-crbs-parity-00000000"
    con.execute(
        "INSERT INTO users (email, role, is_active, created_at, force_password_reset, auth_source, calendar_token,"
        " token_version) VALUES ('takvim@uni.edu.tr', 'TEACHER', 1, '2026-10-08 12:00:00', 0, 'local', ?, 0)",
        (token,),
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("pragma table_info(users)")}
    assert "calendar_token" not in cols
    rows = con.execute("SELECT token_hash, hint FROM calendar_feed_tokens").fetchall()
    assert rows == [(hashlib.sha256(token.encode()).hexdigest(), token[-4:])]
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {
        "calendar_connections",
        "calendar_event_links",
        "calendar_sync_jobs",
        "calendar_event_revisions",
        "oauth_states",
        "webhook_endpoints",
        "webhook_deliveries",
    } <= tables
    con.close()
    _run(url, command.downgrade, "0006_token_version")
    con = sqlite3.connect(path)
    assert "calendar_token" in {r[1] for r in con.execute("pragma table_info(users)")}
    assert "calendar_feed_tokens" not in {
        r[0] for r in con.execute("select name from sqlite_master where type='table'")
    }
    con.close()


def test_integration_tables_match_the_models(tmp_path):
    """Every integrations table / column of the ORM exists after ``alembic upgrade head``."""
    from app.models import integrations
    from app.models.base import Base

    path = tmp_path / "h.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    for name, table in Base.metadata.tables.items():
        if table not in {m.__table__ for m in vars(integrations).values() if hasattr(m, "__table__")}:
            continue
        have = {r[1] for r in con.execute(f"pragma table_info({name})")}
        assert {c.name for c in table.columns} <= have, name
    con.close()
