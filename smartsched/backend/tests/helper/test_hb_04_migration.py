"""HB-04 alembic ``0044_helper``: the helper tables on SQLite and PostgreSQL, one head, cascades with the account, the
unique nonce (the once-only claim), and the owner-only row-level security on PostgreSQL (a teacher reads and writes
only their own rows; administrators read everyone's only inside ``rls.system_scope``)."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core import db as dbmod
from app.core import rls
from app.main import BACKEND_DIR
from sqlalchemy import create_engine, inspect, text

from tests.pg_support import pg_server, pg_url  # noqa: F401
from tests.test_crbs_migration import _run

REV, PREV = "0044_helper", "0043_mfa"
TABLES = {"helper_action_invocations", "helper_threads", "helper_messages", "helper_notes", "helper_events"}
NOW = "'2026-10-18 09:00:00'"


def _tables(path) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()


def test_hb_04_single_head_and_parent() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1
    rev = script.get_revision(REV)
    assert rev is not None and rev.down_revision == PREV


def _insert_rows(con, uid: int, nonce: str) -> None:  # type: ignore[no-untyped-def]
    con.execute(
        "insert into helper_action_invocations (user_id, action, args_hash, preview_hash, nonce, status, created_at,"
        f" expires_at) values ({uid}, 'create_booking', 'a', 'p', '{nonce}', 'done', {NOW}, {NOW})"
    )
    con.execute(f"insert into helper_threads (user_id, title, created_at, last_at) values ({uid}, 'Salon', {NOW}, {NOW})")
    tid = con.execute("select max(id) from helper_threads").fetchone()[0]
    con.execute(
        "insert into helper_messages (thread_id, user_id, role, text, cards, created_at)"
        f" values ({tid}, {uid}, 'user', 'yarın boş salon', '[]', {NOW})"
    )
    con.execute(
        "insert into helper_notes (user_id, text, source, created_at, last_used_at, expires_at)"
        f" values ({uid}, 'Tercih: B blok', 'user_button', {NOW}, {NOW}, {NOW})"
    )
    con.execute(f"insert into helper_events (ts, user_id, kind) values ({NOW}, {uid}, 'query')")


def test_hb_04_sqlite_round_trip(tmp_path) -> None:
    path = tmp_path / "h.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, REV)
    assert TABLES <= _tables(path)
    con = sqlite3.connect(path)
    con.execute("pragma foreign_keys = on")
    con.execute(
        "insert into users (id, email, role, is_active, created_at, force_password_reset, auth_source, token_version)"
        " values (7, 'ayse.yilmaz@uni.edu.tr', 'TEACHER', 1, '2026-02-16 08:00:00', 0, 'local', 0)"
    )
    _insert_rows(con, 7, "n1")
    with pytest.raises(sqlite3.IntegrityError):  # the nonce is claimed once
        _insert_rows(con, 7, "n1")
    con.commit()
    # the account goes, its helper rows go with it; telemetry keeps the row without the person
    con.execute("delete from users where id = 7")
    con.commit()
    for table in ("helper_action_invocations", "helper_threads", "helper_messages", "helper_notes"):
        assert con.execute(f"select count(*) from {table}").fetchone()[0] == 0, table
    assert con.execute("select user_id from helper_events").fetchall() == [(None,)]
    con.close()
    from app.models import helper as hm

    con = sqlite3.connect(path)
    for model in (hm.HelperActionInvocation, hm.HelperThread, hm.HelperMessage, hm.HelperNote, hm.HelperEvent):
        have = {r[1] for r in con.execute(f"pragma table_info({model.__tablename__})")}
        assert {c.name for c in model.__table__.columns} <= have, model.__tablename__
    con.close()
    _run(url, command.downgrade, PREV)
    assert not (TABLES & _tables(path))
    _run(url, command.upgrade, "head")


def test_hb_04_postgres_round_trip(pg_server) -> None:  # noqa: F811
    name = f"t_{uuid.uuid4().hex[:12]}"
    base, _, query = pg_server.partition("?")
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = f"{base.rsplit('/', 1)[0]}/{name}" + (f"?{query}" if query else "")
    try:
        _run(url, command.upgrade, REV)
        eng = create_engine(url)
        assert TABLES <= set(inspect(eng).get_table_names())
        with eng.connect() as c:
            for table in sorted(TABLES):
                on = c.execute(text("select relrowsecurity from pg_class where relname = :t"), {"t": table}).scalar()
                assert on is True, table
                pols = c.execute(
                    text("select polname from pg_policy p join pg_class t on t.oid = p.polrelid where t.relname = :t"),
                    {"t": table},
                ).scalars().all()
                assert pols == ["rls_owner"], table
        eng.dispose()
        _run(url, command.downgrade, PREV)
        eng = create_engine(url)
        assert not (TABLES & set(inspect(eng).get_table_names()))
        eng.dispose()
        _run(url, command.upgrade, "head")
    finally:
        admin.dispose()
        drop = create_engine(pg_server, isolation_level="AUTOCOMMIT")
        with drop.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        drop.dispose()


@pytest.fixture
async def pg(pg_url) -> AsyncIterator[str]:  # noqa: F811
    dbmod.configure_engine(pg_url)
    yield pg_url
    await dbmod.dispose_engine()


async def test_hb_04_postgres_rls_owner_only(pg):  # type: ignore[no-untyped-def]
    from tests.test_w3_sec_rls_postgres import _as, _seed_people

    ids = await _seed_people()
    async with dbmod.get_session_factory()() as s:
        for key in ("a", "b"):
            uid = ids[key]
            await s.execute(
                text(
                    "insert into helper_notes (user_id, text, source, created_at, last_used_at, expires_at)"
                    " values (:u, 'Tercih: B blok', 'user_button', now(), now(), now() + interval '180 days')"
                ),
                {"u": uid},
            )
            await s.execute(
                text(
                    "insert into helper_action_invocations (user_id, action, args_hash, preview_hash, nonce, status,"
                    " created_at, expires_at) values (:u, 'create_booking', 'a', 'p', :n, 'done', now(), now())"
                ),
                {"u": uid, "n": f"nonce-{key}"},
            )
        await s.commit()
    s = await _as(ids["a"])
    try:
        for table in ("helper_notes", "helper_action_invocations"):
            got = (await s.execute(text(f"select user_id from {table}"))).scalars().all()
            assert got == [ids["a"]], table
        res = await s.execute(text("delete from helper_notes where user_id = :u"), {"u": ids["b"]})
        assert res.rowcount == 0  # type: ignore[attr-defined]
        with pytest.raises(Exception):  # noqa: B017 - the policy's WITH CHECK refuses a row for someone else
            await s.execute(
                text(
                    "insert into helper_notes (user_id, text, source, created_at, last_used_at, expires_at)"
                    " values (:u, 'x', 'user_button', now(), now(), now())"
                ),
                {"u": ids["b"]},
            )
        await s.rollback()
    finally:
        await s.close()
    s = await _as(ids["admin"])
    try:
        assert (await s.execute(text("select count(*) from helper_notes"))).scalar_one() == 0
        async with rls.system_scope(s):
            assert (await s.execute(text("select count(*) from helper_notes"))).scalar_one() == 2
    finally:
        await s.close()
