"""CAL-01 alembic ``0039_calendar_classes``: scope columns on ``calendar_feed_tokens``, the new
``calendar_class_revisions`` table, the push columns of ``calendar_connections`` / ``oauth_states``, and
``calendar_event_links.item_key`` (backfilled ``booking:<id>``, unique per connection) / ``calendar_sync_jobs.item_key``.
Upgrade and downgrade on SQLite and on PostgreSQL (``tests/pg_support``; skipped without a server); one head."""

from __future__ import annotations

import sqlite3
import uuid

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.main import BACKEND_DIR
from sqlalchemy import create_engine, inspect, text

from tests.pg_support import pg_server  # noqa: F401
from tests.test_crbs_migration import _run

REV, PREV = "0039_calendar_classes", "0038_email_templates"


def _cols(path, table: str) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute(f"pragma table_info({table})")}
    finally:
        con.close()


def test_cal_01_single_head() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1


def test_cal_01_sqlite_round_trip_backfills_item_keys(tmp_path) -> None:
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREV)
    con = sqlite3.connect(path)
    con.execute(
        "insert into users (id, email, role, is_active, created_at, force_password_reset, auth_source, token_version)"
        " values (7, 'ayse.yilmaz@uni.edu.tr', 'TEACHER', 1, '2026-02-16 08:00:00', 0, 'local', 0)"
    )
    con.execute(
        "insert into calendar_connections (id, user_id, provider, status, created_at) "
        "values (3, 7, 'google', 'ACTIVE', '2026-02-16 08:00:00')"
    )
    con.execute(
        "insert into calendar_event_links (id, connection_id, booking_id, calendar_id, external_id, synced_at) "
        "values (1, 3, 42, 'primary', 'smartsched3p42', '2026-02-16 08:00:00')"
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, REV)
    assert {"scope_kind", "scope_id", "consent_id", "fields"} <= _cols(path, "calendar_feed_tokens")
    assert {"export_scopes", "owned_calendar", "account_verified", "last_reconciled_at"} <= _cols(
        path, "calendar_connections"
    )
    assert "item_key" in _cols(path, "calendar_event_links") and "item_key" in _cols(path, "calendar_sync_jobs")
    assert "export_scopes" in _cols(path, "oauth_states")
    assert {
        "uid",
        "term_id",
        "fingerprint",
        "sequence",
        "last_modified",
        "ended_at",
        "instructor_ids",
        "starts_at",
    } <= (_cols(path, "calendar_class_revisions"))
    con = sqlite3.connect(path)
    assert con.execute("select item_key, booking_id from calendar_event_links").fetchall() == [("booking:42", 42)]
    # a class link has no booking id; the key is unique per connection
    con.execute(
        "insert into calendar_event_links (connection_id, booking_id, item_key, calendar_id, external_id, synced_at)"
        " values (3, NULL, 'class:class-ab12@smartsched', 'c1', 'e1', '2026-02-16 08:00:00')"
    )
    try:
        con.execute(
            "insert into calendar_event_links (connection_id, booking_id, item_key, calendar_id, external_id, "
            "synced_at) values (3, NULL, 'class:class-ab12@smartsched', 'c1', 'e2', '2026-02-16 08:00:00')"
        )
        raise AssertionError("duplicate item_key accepted")
    except sqlite3.IntegrityError:
        pass
    con.commit()
    owned = con.execute("select owned_calendar from calendar_connections where id = 3").fetchone()[0]
    assert owned in (0, False)
    con.close()
    from app.models import CalendarClassRevision, CalendarConnection, CalendarEventLink, CalendarFeedToken

    assert {"scope_kind", "scope_id", "consent_id", "fields"} <= set(CalendarFeedToken.__table__.columns.keys())
    assert "item_key" in CalendarEventLink.__table__.columns.keys()
    assert "export_scopes" in CalendarConnection.__table__.columns.keys()
    assert CalendarClassRevision.__tablename__ == "calendar_class_revisions"
    _run(url, command.downgrade, PREV)
    assert "scope_kind" not in _cols(path, "calendar_feed_tokens")
    assert "item_key" not in _cols(path, "calendar_event_links")
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert "calendar_class_revisions" not in tables
    # the booking link survives, the class link (no booking) is dropped
    assert con.execute("select booking_id from calendar_event_links").fetchall() == [(42,)]
    con.close()
    _run(url, command.upgrade, "head")


def test_cal_01_postgres_round_trip(pg_server) -> None:  # noqa: F811
    name = f"t_{uuid.uuid4().hex[:12]}"
    base, _, query = pg_server.partition("?")
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = f"{base.rsplit('/', 1)[0]}/{name}" + (f"?{query}" if query else "")
    try:
        _run(url, command.upgrade, PREV)
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(
                text(
                    "insert into users (id, email, role, is_active, created_at, force_password_reset, auth_source,"
                    " token_version) values (7, 'ayse.yilmaz@uni.edu.tr', 'TEACHER', true, now(), false, 'local', 0)"
                )
            )
            c.execute(
                text(
                    "insert into calendar_connections (id, user_id, provider, status, created_at) "
                    "values (3, 7, 'google', 'ACTIVE', now())"
                )
            )
            c.execute(
                text(
                    "insert into calendar_event_links (connection_id, booking_id, calendar_id, external_id, synced_at)"
                    " values (3, 42, 'primary', 'smartsched3p42', now())"
                )
            )
        eng.dispose()
        _run(url, command.upgrade, REV)
        eng = create_engine(url)
        insp = inspect(eng)
        assert "calendar_class_revisions" in insp.get_table_names()
        assert "item_key" in {c["name"] for c in insp.get_columns("calendar_event_links")}
        with eng.connect() as c:
            assert c.execute(text("select item_key from calendar_event_links")).scalar_one() == "booking:42"
        eng.dispose()
        _run(url, command.downgrade, PREV)
        eng = create_engine(url)
        assert "calendar_class_revisions" not in inspect(eng).get_table_names()
        eng.dispose()
        _run(url, command.upgrade, REV)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
