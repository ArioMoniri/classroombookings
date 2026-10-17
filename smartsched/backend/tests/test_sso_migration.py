"""Alembic ``*_sso_entra``: the Entra ID sign-in tables (``sso_providers``, ``user_identities``, ``sso_invites``,
``sso_role_mappings``, ``sso_auth_states``) equal the ORM models, existing users are kept, the unique keys hold
(one identity per ``tid + oid``, one per user, one invite per address) and the downgrade round-trips."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.models import Base
from sqlalchemy import create_engine

from tests.test_crbs_migration import _cfg, _run

IDP_REV = "0037_identity_providers"
TABLES = ("sso_providers", "user_identities", "sso_invites", "sso_role_mappings", "sso_auth_states")


def _revision() -> tuple[str, str]:
    script = ScriptDirectory.from_config(_cfg("sqlite+aiosqlite:///:memory:"))
    (rev,) = [r for r in script.walk_revisions() if r.revision.endswith("_sso_entra")]
    down = rev.down_revision
    assert isinstance(down, str)
    return rev.revision, down


def _sso_diff(path) -> list:  # type: ignore[no-untyped-def]
    """Differences between the migrated schema and the models for the SSO tables only (other agents' tables are
    checked by their own migration tests)."""
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"render_as_batch": True}), Base.metadata)
    eng.dispose()

    def mine(entry) -> bool:  # type: ignore[no-untyped-def]
        items = entry if isinstance(entry, list) else [entry]
        text = repr(items)
        return any(t in text for t in TABLES)

    return [d for d in diff if mine(d)]


def test_upgrade_keeps_users_matches_the_models_and_round_trips(tmp_path):
    rev, previous = _revision()
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, previous)
    con = sqlite3.connect(path)
    con.execute(
        "insert into users (id, email, full_name, role, is_active, created_at, auth_source, token_version) "
        "values (7, 'sehriban.serbest@uni.edu.tr', 'Şehriban Serbest', 'TEACHER', 1, '2026-02-16 08:00:00', 'local', 0)"
    )
    con.commit()
    con.close()
    _run(url, command.upgrade, rev)
    # the models are the shape after 0037_identity_providers (several providers; test_w3b_idp_migration.py)
    _run(url, command.upgrade, IDP_REV)
    assert _sso_diff(path) == []
    con = sqlite3.connect(path)
    con.execute("pragma foreign_keys=on")
    assert con.execute("select full_name from users where id = 7").fetchone() == ("Şehriban Serbest",)
    ident = (
        "insert into user_identities (user_id, provider, issuer, tenant_id, subject, origin, created_at) "
        "values (?, 'entra', 'https://login.microsoftonline.com/t/v2.0', 't', ?, 'provision', '2026-10-15')"
    )
    con.execute(ident, (7, "oid-1"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ident, (7, "oid-2"))  # one Entra identity per user
    con.execute(
        "insert into users (id, email, role, is_active, created_at, auth_source, token_version) "
        "values (8, 'x@uni.edu.tr', 'TEACHER', 1, '2026-10-15', 'oidc', 0)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ident, (8, "oid-1"))  # one SmartSched user per (tid, oid)
    invite = (
        "insert into sso_invites (provider, user_id, email, kind, token_hash, token_enc, created_at, expires_at) "
        "values ('entra', ?, 'x@uni.edu.tr', 'invite', ?, 'enc', '2026-10-15', '2026-11-14')"
    )
    con.execute(invite, (8, "h1"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(invite, (7, "h2"))  # one open invite per address
    con.execute(
        "insert into sso_providers (name, enabled, self_signup, oidc_only_non_admins, role_mapping_enabled, "
        "allow_admin_mapping, invite_days, updated_at) values ('entra', 0, 1, 0, 0, 0, 30, '2026-10-15')"
    )
    con.commit()
    con.execute("delete from users where id = 8")  # cascades to its invite
    assert con.execute("select count(*) from sso_invites").fetchone() == (0,)
    con.commit()
    con.close()
    _run(url, command.downgrade, previous)
    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
    assert not names & set(TABLES)
    assert con.execute("select email from users where id = 7").fetchone() == ("sehriban.serbest@uni.edu.tr",)
    con.close()
    _run(url, command.upgrade, IDP_REV)
    assert _sso_diff(path) == []
