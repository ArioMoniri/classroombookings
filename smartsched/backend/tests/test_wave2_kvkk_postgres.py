"""A4 on PostgreSQL: the recreated ``audit_events`` trigger (alembic 0032_kvkk) refuses UPDATE / DELETE except through
the KVKK windows. Skipped without local PostgreSQL binaries or ``TEST_POSTGRES_URL`` (tests/pg_support.py)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.pg_support import pg_server, pg_url  # noqa: F401

INS = (
    "insert into audit_events (ts, actor_type, actor_id, actor_label, action, entity_type, entity_id, reversible) "
    "values (:ts, 'user', 7, 'Ayşe Yılmaz', 'booking.create', 'booking', '1', false)"
)


def test_audit_trigger_exceptions_on_postgres(pg_url):  # noqa: F811
    eng = create_engine(pg_url.replace("+psycopg", "+psycopg"))
    with eng.begin() as c:
        c.execute(text(INS), {"ts": "2024-01-02 10:00:00"})
        c.execute(text(INS), {"ts": "2026-10-15 10:00:00"})
    for stmt in ("update audit_events set action = 'x'", "delete from audit_events"):
        with pytest.raises(DBAPIError, match="append-only"), eng.begin() as c:
            c.execute(text(stmt))
    with eng.begin() as c:
        c.execute(text("insert into audit_purge_windows (kind, cutoff, created_at) values ('retention', now(), now())"))
        assert c.execute(text("delete from audit_events where ts < '2025-01-01'")).rowcount == 1
        c.execute(text("delete from audit_purge_windows"))
    with pytest.raises(DBAPIError, match="append-only"), eng.begin() as c:
        c.execute(text("insert into audit_purge_windows (kind, cutoff, created_at) values ('retention', now(), now())"))
        c.execute(text("delete from audit_events"))  # the recent row stays (365-day floor)
    with eng.begin() as c:
        c.execute(
            text("insert into audit_purge_windows (kind, subject_actor_id, created_at) values ('anonymise', 7, now())")
        )
        c.execute(
            text("update audit_events set actor_id = null, actor_label = 'Silinmiş kullanıcı #1' where actor_id = 7")
        )
        c.execute(text("delete from audit_purge_windows"))
    with pytest.raises(DBAPIError, match="append-only"), eng.begin() as c:
        c.execute(text("update audit_events set actor_label = 'x'"))
    with eng.connect() as c:
        assert c.execute(text("select actor_id, actor_label from audit_events")).all() == [
            (None, "Silinmiş kullanıcı #1")
        ]
    eng.dispose()
