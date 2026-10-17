"""WG-01 alembic ``0040_welcome_guide``: ``welcome_progress`` (per user, cascade) and ``welcome_content`` (admin text
overrides). Upgrade and downgrade on SQLite and on PostgreSQL (``tests/pg_support``; skipped without a server), one
head, and on PostgreSQL the row-level security policy of ``welcome_progress``: a signed-in user reads and writes only
their own rows; an administrator reads everyone's only inside ``rls.system_scope`` (the stats aggregate)."""

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

REV, PREV = "0040_welcome_guide", "0039_calendar_classes"


def _tables(path) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()


def test_wg_01_single_head_is_the_welcome_guide() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    rev = script.get_revision(REV)
    assert rev is not None and rev.down_revision == PREV


def test_wg_01_sqlite_round_trip(tmp_path) -> None:
    path = tmp_path / "w.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, REV)
    assert {"welcome_progress", "welcome_content"} <= _tables(path)
    con = sqlite3.connect(path)
    con.execute("pragma foreign_keys = on")
    con.execute(
        "insert into users (id, email, role, is_active, created_at, force_password_reset, auth_source, token_version)"
        " values (7, 'ayse.yilmaz@uni.edu.tr', 'TEACHER', 1, '2026-02-16 08:00:00', 0, 'local', 0)"
    )
    con.execute(
        "insert into welcome_progress (user_id, guide_key, audience, audience_hash, content_version, state, items,"
        " snooze_count, first_shown_at, updated_at) values (7, 'sheet', 'academician', 'abcd', 0, 'snoozed', '{}', 1,"
        " '2026-10-17 09:00:00', '2026-10-17 09:00:00')"
    )
    try:
        con.execute(
            "insert into welcome_progress (user_id, guide_key, audience, audience_hash, content_version, state, items,"
            " snooze_count, first_shown_at, updated_at) values (7, 'sheet', 'staff', 'abcd', 0, 'shown', '{}', 0,"
            " '2026-10-17 09:00:00', '2026-10-17 09:00:00')"
        )
        raise AssertionError("two sheet rows for one user accepted")
    except sqlite3.IntegrityError:
        pass
    con.execute(
        "insert into welcome_content (audience, locale, field, text, version, updated_by_id, updated_at)"
        " values ('academician', 'tr', 'title', 'Hoş geldiniz, {ad}', 1, 7, '2026-10-17 09:00:00')"
    )
    con.commit()
    # the account goes, its progress goes with it (ON DELETE CASCADE); the text stays (updated_by SET NULL)
    con.execute("delete from users where id = 7")
    con.commit()
    assert con.execute("select count(*) from welcome_progress").fetchone()[0] == 0
    assert con.execute("select updated_by_id from welcome_content").fetchall() == [(None,)]
    con.close()
    from app.models.welcome import WelcomeContent, WelcomeProgress

    con = sqlite3.connect(path)
    for model in (WelcomeProgress, WelcomeContent):
        have = {r[1] for r in con.execute(f"pragma table_info({model.__tablename__})")}
        assert {c.name for c in model.__table__.columns} <= have, model.__tablename__
    con.close()
    _run(url, command.downgrade, PREV)
    assert not ({"welcome_progress", "welcome_content"} & _tables(path))
    _run(url, command.upgrade, "head")


def test_wg_01_postgres_round_trip(pg_server) -> None:  # noqa: F811
    name = f"t_{uuid.uuid4().hex[:12]}"
    base, _, query = pg_server.partition("?")
    admin = create_engine(pg_server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = f"{base.rsplit('/', 1)[0]}/{name}" + (f"?{query}" if query else "")
    try:
        _run(url, command.upgrade, REV)
        eng = create_engine(url)
        insp = inspect(eng)
        assert {"welcome_progress", "welcome_content"} <= set(insp.get_table_names())
        with eng.connect() as c:
            on = c.execute(text("select relrowsecurity from pg_class where relname = 'welcome_progress'")).scalar()
            assert on is True
            pols = c.execute(text("select polname from pg_policy p join pg_class t on t.oid = p.polrelid "
                                  "where t.relname = 'welcome_progress'")).scalars().all()
            assert pols == ["rls_owner"]
        eng.dispose()
        _run(url, command.downgrade, PREV)
        eng = create_engine(url)
        assert "welcome_progress" not in inspect(eng).get_table_names()
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


async def test_wg_01_postgres_rls_owner_only(pg):  # type: ignore[no-untyped-def]
    from tests.test_w3_sec_rls_postgres import _as, _seed_people

    ids = await _seed_people()
    async with dbmod.get_session_factory()() as s:
        for key in ("a", "b"):
            await s.execute(
                text(
                    "insert into welcome_progress (user_id, guide_key, audience, audience_hash, content_version,"
                    " state, items, snooze_count, first_shown_at, updated_at) values (:u, 'sheet', 'academician',"
                    " 'abcd', 0, 'shown', '{}', 0, now(), now())"
                ),
                {"u": ids[key]},
            )
        await s.commit()
    s = await _as(ids["a"])
    try:
        got = (await s.execute(text("select user_id from welcome_progress"))).scalars().all()
        assert got == [ids["a"]]
        # another person's row cannot be written either
        res = await s.execute(text("update welcome_progress set state = 'dismissed' where user_id = :u"),
                              {"u": ids["b"]})
        assert res.rowcount == 0  # type: ignore[attr-defined]
        await s.rollback()
    finally:
        await s.close()
    s = await _as(ids["admin"])
    try:
        mine = (await s.execute(text("select count(*) from welcome_progress"))).scalar_one()
        assert mine == 0  # the administrator holds every permission, still sees no one's progress row
        async with rls.system_scope(s):
            assert (await s.execute(text("select count(*) from welcome_progress"))).scalar_one() == 2
        assert (await s.execute(text("select count(*) from welcome_progress"))).scalar_one() == 0
    finally:
        await s.close()
