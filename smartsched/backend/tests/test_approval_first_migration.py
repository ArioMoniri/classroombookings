"""Alembic ``0025_approval_first``: reason codes and ``decided_by`` on approval requests, ``reason_code`` on decisions,
``inapp_notifications.data``, the ``notification_deliveries`` ledger (unique per occurrence, recipient, channel) and
the permission ``bookings.skip_approval`` (Administrator); existing rows are kept, the schema equals the ORM models,
the downgrade round-trips."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command

from tests.test_crbs_migration import _run
from tests.test_p19_learning_migration import _cols, _diff

PREVIOUS = "0024_moderation_indexes"


def _admin_perms(con: sqlite3.Connection) -> set[str]:
    q = (
        "select p.name from permissions p join role_permissions rp on rp.permission_id = p.id "
        "join roles r on r.id = rp.role_id where r.code = 'ADMIN'"
    )
    return {r[0] for r in con.execute(q)}


def test_upgrade_keeps_rows_adds_the_ledger_and_round_trips(tmp_path):
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREVIOUS)
    con = sqlite3.connect(path)
    con.execute(
        "insert into users (id, email, full_name, role, is_active, created_at) "
        "values (7, 'ayse.yilmaz@uni.edu.tr', 'Ayşe Yılmaz', 'TEACHER', 1, '2026-02-16 08:00:00')"
    )
    con.execute(
        "insert into inapp_notifications (id, user_id, kind, title, body, created_at) values "
        "(1, 7, 'approval.rejected', 'Oda talebiniz reddedildi: A 201, 18.02.2026 P3', 'Tıp Fakültesi sınavı', "
        "'2026-02-16 08:05:00')"
    )
    con.commit()
    assert "bookings.skip_approval" not in _admin_perms(con)
    con.close()

    _run(url, command.upgrade, "head")
    con = sqlite3.connect(path)
    assert {"decided_by", "reason_code"} <= set(_cols(con, "approval_requests"))
    assert "reason_code" in _cols(con, "approval_decisions")
    assert con.execute("select title, data from inapp_notifications").fetchall() == [
        ("Oda talebiniz reddedildi: A 201, 18.02.2026 P3", None)
    ]
    assert "bookings.skip_approval" in _admin_perms(con)
    row = "insert into notification_deliveries (event, event_key, user_id, channel, status, created_at) values (?, ?, 7, ?, 'sent', '2026-02-16')"
    con.execute(row, ("approval.rejected", "approval_request:1:rejected", "email"))
    con.execute(row, ("approval.rejected", "approval_request:1:rejected", "in_app"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(row, ("approval.rejected", "approval_request:1:rejected", "email"))
    con.commit()
    con.close()
    assert _diff(path) == []

    _run(url, command.downgrade, PREVIOUS)
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert "notification_deliveries" not in tables
    assert "data" not in _cols(con, "inapp_notifications") and "reason_code" not in _cols(con, "approval_requests")
    assert con.execute("select count(*) from inapp_notifications").fetchone() == (1,)
    assert "bookings.skip_approval" not in _admin_perms(con)
    con.close()
    _run(url, command.upgrade, "head")
    assert _diff(path) == []
