"""AU-01 alembic ``0043_mfa``: the five per-person tables of two-step sign-in (``user_mfa``, ``mfa_recovery_codes``,
``webauthn_credentials``, ``trusted_devices``, ``auth_challenges``). One head; upgrade and downgrade on SQLite and on
PostgreSQL (``tests/pg_support``; skipped without a server); cascade with the account; and on PostgreSQL the owner-only
row-level security policy: a signed-in user reads only their own rows, an administrator sees nobody's outside
``rls.system_scope`` (the admin reset)."""

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

REV, PREV = "0043_mfa", "0042_ai_usage_audio"
TABLES = {"user_mfa", "mfa_recovery_codes", "webauthn_credentials", "trusted_devices", "auth_challenges"}


def _tables(path) -> set[str]:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()


def test_au_b_migration_chains_on_the_previous_head_and_heads_stay_single() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1
    rev = script.get_revision(REV)
    assert rev is not None and rev.down_revision == PREV


def test_au_b_sqlite_round_trip_and_cascade(tmp_path) -> None:
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, REV)
    assert TABLES <= _tables(path)
    con = sqlite3.connect(path)
    # a fresh install: passwordless passkey sign-in is on (owner default 2026-10-18)
    assert con.execute("select value from settings where key = 'auth.passkey_first_factor'").fetchall() == [("1",)]
    con.execute("pragma foreign_keys = on")
    con.execute(
        "insert into users (id, email, role, is_active, created_at, force_password_reset, auth_source, token_version)"
        " values (7, 'ayse.yilmaz@uni.edu.tr', 'TEACHER', 1, '2026-10-18 08:00:00', 0, 'local', 0)"
    )
    con.execute("insert into user_mfa (user_id, failed_count, updated_at) values (7, 0, '2026-10-18 08:00:00')")
    con.execute(
        "insert into mfa_recovery_codes (user_id, code_hash, created_at) values (7, '$argon2id$x', '2026-10-18 08:00:00')"
    )
    con.execute(
        "insert into webauthn_credentials (user_id, credential_id, public_key, sign_count, transports, name,"
        " backup_eligible, backed_up, created_at) values (7, 'cred-1', 'pk', 0, '[]', 'iPhone', 0, 0,"
        " '2026-10-18 08:00:00')"
    )
    try:
        con.execute(
            "insert into webauthn_credentials (user_id, credential_id, public_key, sign_count, transports, name,"
            " backup_eligible, backed_up, created_at) values (7, 'cred-1', 'pk2', 0, '[]', 'Kopya', 0, 0,"
            " '2026-10-18 08:00:00')"
        )
        raise AssertionError("a credential id registered twice")
    except sqlite3.IntegrityError:
        pass
    con.execute(
        "insert into trusted_devices (user_id, token_hash, label, created_at, expires_at) values (7, 'h', 'Safari',"
        " '2026-10-18 08:00:00', '2026-11-17 08:00:00')"
    )
    con.execute(
        "insert into auth_challenges (jti, user_id, purpose, data, attempts, created_at, expires_at) values"
        " ('j1', 7, 'mfa', '{}', 0, '2026-10-18 08:00:00', '2026-10-18 08:05:00')"
    )
    con.commit()
    con.execute("delete from users where id = 7")
    con.commit()
    for t in TABLES:
        assert con.execute(f"select count(*) from {t}").fetchone()[0] == 0, t
    con.close()
    from app.models.mfa import AuthChallenge, MfaRecoveryCode, TrustedDevice, UserMfa, WebAuthnCredential

    con = sqlite3.connect(path)
    for model in (UserMfa, MfaRecoveryCode, WebAuthnCredential, TrustedDevice, AuthChallenge):
        have = {r[1] for r in con.execute(f"pragma table_info({model.__tablename__})")}
        assert {c.name for c in model.__table__.columns} <= have, model.__tablename__
    con.close()
    _run(url, command.downgrade, PREV)
    assert not (TABLES & _tables(path))
    _run(url, command.upgrade, "head")


def test_au_b_existing_install_keeps_passkey_sign_in_off(tmp_path) -> None:
    path = tmp_path / "old.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREV)
    con = sqlite3.connect(path)
    con.execute(
        "insert into users (id, email, role, is_active, created_at, force_password_reset, auth_source, token_version)"
        " values (1, 'admin@uni.edu.tr', 'ADMIN', 1, '2026-02-16 08:00:00', 0, 'local', 0)"
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, REV)
    con = sqlite3.connect(path)
    assert con.execute("select count(*) from settings where key like 'auth.%'").fetchone()[0] == 0
    con.close()


def test_au_b_postgres_round_trip(pg_server) -> None:  # noqa: F811
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
            for t in TABLES:
                on = c.execute(text("select relrowsecurity from pg_class where relname = :t"), {"t": t}).scalar()
                assert on is True, t
                pols = (
                    c.execute(
                        text(
                            "select polname from pg_policy p join pg_class t on t.oid = p.polrelid "
                            "where t.relname = :t"
                        ),
                        {"t": t},
                    )
                    .scalars()
                    .all()
                )
                assert pols == ["rls_owner"], t
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


async def test_au_b_postgres_rls_owner_only(pg):  # type: ignore[no-untyped-def]
    from tests.test_w3_sec_rls_postgres import _as, _seed_people

    ids = await _seed_people()
    async with dbmod.get_session_factory()() as s:
        for key in ("a", "b"):
            await s.execute(
                text(
                    "insert into webauthn_credentials (user_id, credential_id, public_key, sign_count, transports,"
                    " name, backup_eligible, backed_up, created_at) values (:u, :c, 'pk', 0, '[]', 'Telefon', false,"
                    " false, now())"
                ),
                {"u": ids[key], "c": f"cred-{key}"},
            )
            await s.execute(
                text("insert into user_mfa (user_id, failed_count, updated_at) values (:u, 0, now())"), {"u": ids[key]}
            )
        await s.commit()
    s = await _as(ids["a"])
    try:
        for table in ("webauthn_credentials", "user_mfa"):
            got = (await s.execute(text(f"select user_id from {table}"))).scalars().all()
            assert got == [ids["a"]], table
        res = await s.execute(text("update user_mfa set failed_count = 9 where user_id = :u"), {"u": ids["b"]})
        assert res.rowcount == 0  # type: ignore[attr-defined]
        await s.rollback()
    finally:
        await s.close()
    s = await _as(ids["admin"])
    try:
        assert (await s.execute(text("select count(*) from webauthn_credentials"))).scalar_one() == 0
        async with rls.system_scope(s):
            assert (await s.execute(text("select count(*) from webauthn_credentials"))).scalar_one() == 2
    finally:
        await s.close()
