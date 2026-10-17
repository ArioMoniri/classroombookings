"""Alembic ``0038_email_templates`` (wave 3b W3-MAIL): ``notification_outbox`` gains ``link`` and ``locale``; existing
rows are kept untouched; the columns match the model; the downgrade drops them again and keeps the rows."""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.test_crbs_migration import _cfg, _run  # noqa: F401

REV, PREV = "0038_email_templates", "0037_identity_providers"


def _cols(path) -> dict[str, str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[1]: r[2] for r in con.execute("pragma table_info(notification_outbox)")}
    finally:
        con.close()


def test_outbox_columns_round_trip(tmp_path) -> None:
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREV)
    con = sqlite3.connect(path)
    con.execute(
        "insert into notification_outbox (id, kind, to_email, subject, body, status, attempts, created_at) "
        "values (5, 'booking_created', 'ayse.yilmaz@uni.edu.tr', 'Sizin adınıza rezervasyon yapıldı', "
        "'Fatih Bey sizin adınıza 1 rezervasyon yaptı:\n- A 102', 'UNSENT', 0, '2026-02-16 08:00:00')"
    )
    con.commit()
    con.close()
    assert "link" not in _cols(path)
    _run(url, command.upgrade, REV)
    cols = _cols(path)
    assert cols["link"].upper().startswith("VARCHAR") and cols["locale"].upper().startswith("VARCHAR")
    from app.models import NotificationOutbox

    assert {"link", "locale"} <= set(NotificationOutbox.__table__.columns.keys())
    con = sqlite3.connect(path)
    row = con.execute("select subject, body, link, locale from notification_outbox where id = 5").fetchone()
    con.close()
    assert row == (
        "Sizin adınıza rezervasyon yapıldı",
        "Fatih Bey sizin adınıza 1 rezervasyon yaptı:\n- A 102",
        None,
        None,
    )
    _run(url, command.downgrade, PREV)
    assert "link" not in _cols(path) and "locale" not in _cols(path)
    con = sqlite3.connect(path)
    assert con.execute("select count(*) from notification_outbox").fetchone()[0] == 1
    con.close()
