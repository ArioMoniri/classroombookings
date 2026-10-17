"""Alembic ``0037_identity_providers`` (wave 3b W3-IDP): the single Entra row becomes one provider of kind ``entra``
with every value kept (tenant pin, client, encrypted secret, guard switches, sign-up role, invite days, updated
metadata); its identities, invites and mappings stay attached; the new columns match the models; the downgrade keeps
the Entra row and drops the providers of the new kinds."""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.test_crbs_migration import _cfg, _run  # noqa: F401
from tests.test_sso_migration import _sso_diff

REV, PREV = "0037_identity_providers", "0036_error_events"
TENANT = "3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a"
CLIENT = "6b1d9e2f-0c4a-4f8e-9d3b-7a5c2e1f8b0d"


def _seed_entra(path) -> None:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(path)
    con.execute(
        "insert into users (id, email, full_name, role, is_active, created_at, auth_source, token_version) "
        "values (7, 'şehriban.serbest@uni.edu.tr', 'Şehriban Serbest', 'ADMIN', 1, '2026-02-16 08:00:00', 'local', 0)"
    )
    con.execute(
        "insert into users (id, email, full_name, role, is_active, created_at, auth_source, token_version) "
        "values (8, 'ayse.yilmaz@uni.edu.tr', 'Ayşe Yılmaz', 'TEACHER', 1, '2026-10-15', 'oidc', 0)"
    )
    con.execute(
        "insert into sso_providers (id, name, enabled, tenant_id, client_id, client_secret_enc, self_signup, "
        "domain_hint, default_role_id, oidc_only_non_admins, role_mapping_enabled, allow_admin_mapping, invite_days, "
        "updated_at, updated_by) values (1, 'entra', 1, ?, ?, 'gAAAA-enc', 0, 'uni.edu.tr', null, 1, 1, 0, 45, "
        "'2026-10-16 10:11:12', 7)",
        (TENANT, CLIENT),
    )
    con.execute(
        "insert into user_identities (user_id, provider, issuer, tenant_id, subject, origin, created_at) "
        "values (8, 'entra', ?, ?, '00000000-0000-0000-66f3-3332eca7ea81', 'provision', '2026-10-15')",
        (f"https://login.microsoftonline.com/{TENANT}/v2.0", TENANT),
    )
    con.execute(
        "insert into sso_role_mappings (provider, claim, value, role_id, created_by, created_at) "
        "select 'entra', 'role', 'SmartSched.Planner', id, 7, '2026-10-15' from roles limit 1"
    )
    con.commit()
    con.close()


def test_entra_row_is_migrated_losslessly_and_round_trips(tmp_path) -> None:
    path = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{path}"
    _run(url, command.upgrade, PREV)
    _seed_entra(path)
    _run(url, command.upgrade, REV)
    assert _sso_diff(path) == []
    con = sqlite3.connect(path)
    row = con.execute(
        "select name, kind, enabled, tenant_id, client_id, client_secret_enc, self_signup, domain_hint, "
        "oidc_only_non_admins, role_mapping_enabled, allow_admin_mapping, invite_days, updated_at, updated_by, "
        "display_name, sort_order, invite_only, allowed_domains from sso_providers"
    ).fetchall()
    assert len(row) == 1
    kept, new = row[0][:14], row[0][14:]
    assert kept[:12] == ("entra", "entra", 1, TENANT, CLIENT, "gAAAA-enc", 0, "uni.edu.tr", 1, 1, 0, 45)
    assert str(kept[12]).startswith("2026-10-16 10:11:12") and kept[13] == 7  # "Son değişiklik" kept
    assert new == (None, 0, 0, None)  # default label, first in order, not invite-only, no domain restriction
    assert con.execute("select provider, subject from user_identities").fetchall() == [
        ("entra", "00000000-0000-0000-66f3-3332eca7ea81")
    ]
    assert con.execute("select provider, value from sso_role_mappings").fetchall() == [("entra", "SmartSched.Planner")]
    # a provider of a new kind with a long slug and a long SAML subject fits now
    con.execute(
        "insert into sso_providers (name, kind, enabled, self_signup, oidc_only_non_admins, role_mapping_enabled, "
        "allow_admin_mapping, invite_days, invite_only, sort_order, updated_at) values "
        "('yetkim-federasyonu-saml', 'saml', 0, 1, 0, 0, 0, 30, 1, 3, '2026-10-17')"
    )
    con.execute(
        "insert into user_identities (user_id, provider, issuer, tenant_id, subject, origin, created_at) values "
        "(7, 'yetkim-federasyonu-saml', 'https://idp.uni.edu.tr/idp/shibboleth', 'x', ?, 'provision', '2026-10-17')",
        ("a" * 200,),
    )
    con.commit()
    con.close()
    _run(url, command.downgrade, PREV)
    con = sqlite3.connect(path)
    assert con.execute("select name, tenant_id, invite_days from sso_providers").fetchall() == [("entra", TENANT, 45)]
    assert con.execute("select provider from user_identities").fetchall() == [("entra",)]
    con.close()
    _run(url, command.upgrade, REV)
    assert _sso_diff(path) == []
