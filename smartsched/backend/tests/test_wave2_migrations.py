"""Alembic migrations of the booking enhancements wave 2 (P8 ``0029_booking_policies``, P2 ``0030_booking_conflicts``): the tables appear, the
schema equals the ORM models (autogenerate diff empty), existing rows are kept and the downgrade round-trips."""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.test_crbs_migration import _run
from tests.test_p19_learning_migration import _diff


def _tables(path) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
    finally:
        con.close()


def test_booking_policies_migration(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "0028_p19_gaps")
    con = sqlite3.connect(path)
    con.execute(
        "insert into terms (id, code, name, kind, week_count, periods_json, is_active, created_at, updated_at) "
        "values (1, '2026-BAHAR', '2026 Bahar', 'REGULAR', 14, '[]', 1, '2026-02-01 00:00:00', '2026-02-01 00:00:00')"
    )
    con.commit()
    con.close()
    assert "booking_policies" not in _tables(path)
    _run(url, command.upgrade, "0029_booking_policies")
    assert "booking_policies" in _tables(path)
    con = sqlite3.connect(path)
    assert con.execute("select code from terms").fetchall() == [("2026-BAHAR",)]
    con.execute(
        "insert into booking_policies (name, term_id, scope_type, role_codes, effect, min_notice_workdays, "
        "quiet_hours, blackouts, created_at) values ('3 iş günü', 1, 'all', '[\"TEACHER\"]', 'refuse', 3, '[]', '[]', "
        "'2026-10-16 12:00:00')"
    )
    con.commit()
    assert con.execute("select enabled from booking_policies").fetchone() == (1,)
    con.close()
    _run(url, command.upgrade, "heads")
    assert [d for d in _diff(path) if "booking_policies" in repr(d)] == []
    _run(url, command.downgrade, "0028_p19_gaps")
    assert "booking_policies" not in _tables(path)


def test_booking_conflicts_migration(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "0029_booking_policies")
    assert "booking_conflicts" not in _tables(path)
    _run(url, command.upgrade, "0030_booking_conflicts")
    assert "booking_conflicts" in _tables(path)
    _run(url, command.upgrade, "heads")
    assert [d for d in _diff(path) if "booking_conflicts" in repr(d)] == []
    _run(url, command.downgrade, "0029_booking_policies")
    assert "booking_conflicts" not in _tables(path)
