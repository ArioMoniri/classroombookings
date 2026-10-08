"""Alembic ``0003_crbs_parity``: upgrade from ``0002_studio`` keeps existing users and links them to the
seeded roles; downgrade removes the CRBS tables/columns without touching the rest; upgrade again works;
and the migrated schema equals the ORM models (no autogenerate diff)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from app.models import Base
from sqlalchemy import create_engine

BACKEND = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _run(url: str, fn, *args) -> None:  # type: ignore[no-untyped-def]
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        fn(_cfg(url), *args)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def test_upgrade_downgrade_roundtrip(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "0002_studio")
    con = sqlite3.connect(path)
    con.execute(
        "insert into users (email, password_hash, full_name, role, is_active, created_at) "
        "values ('planlama@uni.edu.tr', 'x', 'Fatih Demir', 'PLANNER', 1, '2026-10-01 09:00:00')"
    )
    con.commit()
    con.close()

    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"roles", "permissions", "bookings", "booking_slots", "booking_series", "room_acl", "holidays"} <= tables
    roles = dict(con.execute("select code, id from roles"))
    assert set(roles) == {"ADMIN", "TEACHER", "PLANNER", "VIEWER"}
    teacher = {
        r[0]
        for r in con.execute(
            "select p.name from permissions p join role_permissions rp on rp.permission_id = p.id where rp.role_id = ?",
            (roles["TEACHER"],),
        )
    }
    assert teacher == {"room.view", "book_single.create", "book_single.view_other_notes", "book_recur.view_other_notes"}
    assert con.execute("select count(*) from permissions").fetchone()[0] == 31
    row = con.execute("select role_id, force_password_reset, auth_source from users").fetchone()
    assert row == (roles["PLANNER"], 0, "local")
    unique = [r for r in con.execute("pragma index_list(booking_slots)") if r[2]]
    assert unique, "booking_slots must carry the unique room/date/period key"
    con.close()

    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"render_as_batch": True}), Base.metadata)
    eng.dispose()
    assert diff == []

    _run(url, command.downgrade, "0002_studio")
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert "roles" not in tables and "bookings" not in tables and "studio_drafts" in tables
    cols = {r[1] for r in con.execute("pragma table_info(users)")}
    assert "role_id" not in cols and "username" not in cols
    assert con.execute("select email, role from users").fetchall() == [("planlama@uni.edu.tr", "PLANNER")]
    con.close()

    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    assert con.execute("select count(*) from roles").fetchone()[0] == 4
    con.close()
