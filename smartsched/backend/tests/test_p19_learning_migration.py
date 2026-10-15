"""Alembic ``0023_learning`` (P19-L1 + P19-C4 + the P19-M2 priority columns): an upgraded database keeps its rows
(new flags default to false / priority 0), the learning tables and the Instructor <-> User link exist, the schema
equals the ORM models (autogenerate diff empty), the downgrade round-trips and a fresh database upgrades."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from app.models import Base
from app.models.scheduling import CONSTRAINT_SOURCES
from sqlalchemy import create_engine

from tests.test_crbs_migration import _run

PREVIOUS = "0022_kvkk_signoff_unseed"
TABLES = {"learned_observations", "learned_priors", "suggestion_feedback", "learning_resets"}


def _cols(con: sqlite3.Connection, table: str) -> dict[str, tuple]:
    return {r[1]: r for r in con.execute(f"pragma table_info({table})")}


def _diff(path) -> list:  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"render_as_batch": True}), Base.metadata)
    eng.dispose()
    return diff


def test_upgrade_keeps_rows_and_matches_the_models(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREVIOUS)
    con = sqlite3.connect(path)
    # real Bahar rows: the Faculty of Medicine's Tıp programme and the MAT 112 instructor slot (name not needed)
    con.execute("insert into faculties (id, name, canonical_name) values (1, 'Tıp Fakültesi', 'tip fakultesi')")
    con.execute(
        "insert into programs (id, faculty_id, name, canonical_name, is_evening) values (1, 1, 'Tıp', 'tip', 0)"
    )
    con.execute("insert into instructors (id, full_name, canonical_name) values (1, 'Öğr. Gör. X', 'x')")
    con.execute("insert into courses (id, code, display_code) values (1, 'MAT112', 'MAT 112')")
    con.execute(
        "insert into terms (id, code, name, kind, week_count, periods_json, is_active, created_at, updated_at) "
        "values (1, '2026-BAHAR', '2026 Bahar', 'REGULAR', 14, '[]', 1, '2026-02-01 00:00:00', '2026-02-01 00:00:00')"
    )
    con.execute(
        "insert into sections (id, term_id, course_id, program_id, label, class_years, enrolment, mode, source_key, "
        "archived, created_at, updated_at) values (1, 1, 1, 1, '1', '[]', 180, 'F2F', 'k1', 0, "
        "'2026-02-01 00:00:00', '2026-02-01 00:00:00')"
    )
    con.execute(
        "insert into meeting_requests (id, section_id, day, days, start_period, end_period, weeks, requested_room_ids, "
        "requested_tags, flexible_day, needs_room, definitive_room_text, definitive_room_ids, status, parse_warnings, "
        "archived, created_at, updated_at) values (1, 1, 4, '[4]', 7, 9, '[]', '[]', '[]', 0, 1, 'A 204', '[]', "
        "'LOCKED', '[]', 0, '2026-02-01 00:00:00', '2026-02-01 00:00:00')"
    )
    con.commit()
    con.close()

    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert tables >= TABLES
    for table in ("faculties", "programs", "courses", "instructors"):
        cols = _cols(con, table)
        assert {"source_key", "archived"} <= set(cols), table
        assert con.execute(f"select archived, source_key from {table}").fetchall() == [(0, None)]
    assert "user_id" in _cols(con, "instructors")
    assert con.execute("select enrolment_estimated, priority from sections").fetchall() == [(0, 0)]
    assert con.execute("select duration_periods, priority from meeting_requests").fetchall() == [(None, None)]
    # one programme name per faculty; a second user link to the same account is refused
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "insert into programs (faculty_id, name, canonical_name, is_evening, archived) values (1, 'Tıp', 'tip', 0, 0)"
        )
    con.execute(
        "insert into users (id, email, role, is_active, created_at) values (7, 'h@x', 'TEACHER', 1, '2026-01-01')"
    )
    con.execute("update instructors set user_id = 7 where id = 1")
    con.execute("insert into instructors (id, full_name, canonical_name, archived) values (2, 'Y', 'y', 0)")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update instructors set user_id = 7 where id = 2")
    con.commit()
    con.close()

    assert _diff(path) == []

    _run(url, command.downgrade, PREVIOUS)
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert not (tables & TABLES)
    assert "user_id" not in _cols(con, "instructors") and "priority" not in _cols(con, "sections")
    assert con.execute("select count(*) from meeting_requests").fetchone() == (1,)
    con.close()
    _run(url, command.upgrade, "head")
    assert _diff(path) == []


def test_fresh_database_upgrades_to_head(tmp_path):
    path = tmp_path / "fresh.db"
    _run(f"sqlite+aiosqlite:///{path}", command.upgrade, "head")
    assert _diff(path) == []


def test_learned_is_a_constraint_source():
    assert "LEARNED" in CONSTRAINT_SOURCES
