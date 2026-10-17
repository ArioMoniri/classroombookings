"""Alembic migrations of the booking enhancements wave 2 (P8 ``0029_booking_policies``, P2 ``0030_booking_conflicts``): the tables appear, the
schema equals the ORM models (autogenerate diff empty), existing rows are kept and the downgrade round-trips."""

from __future__ import annotations

import sqlite3

import pytest
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


def test_kvkk_migration_and_audit_trigger_exceptions(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, "0031_invigilation")
    _run(url, command.upgrade, "0032_kvkk")
    kvkk = {"retention_policies", "privacy_notices", "notice_acks", "consents", "dsr_requests", "audit_purge_windows"}
    assert kvkk <= _tables(path)
    con = sqlite3.connect(path)
    ins = (
        "insert into audit_events (ts, actor_type, actor_id, actor_label, action, entity_type, entity_id, reversible) "
        "values (?, 'user', 7, 'Ayşe Yılmaz', 'booking.create', 'booking', '1', 0)"
    )
    con.execute(ins, ("2024-01-02 10:00:00.000000",))
    con.execute(ins, ("2026-10-15 10:00:00.000000",))
    con.commit()
    for stmt in (
        "update audit_events set action = 'x'",
        "update audit_events set actor_id = null",
        "delete from audit_events",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute(stmt)
    # a retention window lets only rows older than its cutoff and than 365 days go
    con.execute(
        "insert into audit_purge_windows (kind, cutoff, created_at) values ('retention', '2026-10-16 00:00:00', "
        "'2026-10-16 00:00:00')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("delete from audit_events")
    con.execute("delete from audit_events where ts < '2025-01-01'")
    con.execute("delete from audit_purge_windows")
    # an anonymise window for person 7: actor columns may go, the action may not change
    con.execute(
        "insert into audit_purge_windows (kind, subject_actor_id, created_at) values ('anonymise', 7, "
        "'2026-10-16 00:00:00')"
    )
    con.execute("update audit_events set actor_id = null, actor_label = 'Silinmiş kullanıcı #1' where actor_id = 7")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("update audit_events set action = 'x'")
    con.commit()
    con.close()
    _run(url, command.upgrade, "heads")
    assert [d for d in _diff(path) if any(t in repr(d) for t in kvkk)] == []
    _run(url, command.downgrade, "0031_invigilation")
    assert not kvkk & _tables(path)
    con = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("delete from audit_events")
    con.close()
