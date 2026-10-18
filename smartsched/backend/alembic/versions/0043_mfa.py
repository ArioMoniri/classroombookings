"""Two-step sign-in, passkeys, trusted devices (AU-B; app/models/mfa.py, docs/research/2026-10-18-auth-backend.md)

* ``user_mfa``: per person, the Fernet-encrypted TOTP secret (and an enrolment in progress), the last accepted step,
  the WebAuthn user handle, the failure count / lock and the policy's grace start;
* ``mfa_recovery_codes``: argon2id hashes, single use;
* ``webauthn_credentials``: credential id (unique), COSE public key, sign count, transports, name, AAGUID, BE/BS flags,
  created / last used;
* ``trusted_devices``: SHA-256 of the 30-day device token, label, expiry, revocation;
* ``auth_challenges``: single-use sign-in / ceremony steps (jti, purpose, WebAuthn challenge, tries, expiry).

A fresh install (no account yet) gets ``auth.passkey_first_factor = 1`` (owner default 2026-10-18: passwordless passkey
sign-in on for new installations); an existing database is left unchanged.

Every table cascades with ``users``. The organisation policy (``auth.mfa_policy``, ``auth.mfa_roles``,
``auth.mfa_grace_days``, ``auth.passkeys_enabled``, ``auth.passkey_first_factor``) is ordinary ``settings`` rows with
code defaults (app/services/mfa.py).

PostgreSQL: the five tables get the owner-only row-level security policy of the 0035_rls_policies pattern (the
signed-in user's own rows, or the system context: sign-in is unauthenticated, administrator resets run in
``rls.system_scope``). The RLS role reaches them through the default privileges of 0035. SQLite: plain tables.

Revision ID: 0043_mfa
Revises: 0042_ai_usage_audio
Create Date: 2026-10-18 01:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0043_mfa"
down_revision = "0042_ai_usage_audio"
branch_labels = None
depends_on = None

OWNER = "smartsched_rls_system() OR user_id = smartsched_rls_uid()"
#: (table, policy name, command, USING expression); the helper functions come from 0035_rls_policies
POLICIES: tuple[tuple[str, str, str, str], ...] = tuple(
    (t, "rls_owner", "ALL", OWNER)
    for t in ("user_mfa", "mfa_recovery_codes", "webauthn_credentials", "trusted_devices", "auth_challenges")
)


def _has_rls_helpers() -> bool:
    row = op.get_bind().execute(sa.text("SELECT 1 FROM pg_proc WHERE proname = 'smartsched_rls_uid'")).first()
    return row is not None


def _seed_fresh_install() -> None:
    """Owner default 2026-10-18: passkey-only sign-in is ON for new installs (a database without any account yet);
    an existing installation keeps the code default (off) until an administrator switches it on."""
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one():
        return
    if bind.execute(sa.text("SELECT 1 FROM settings WHERE key = 'auth.passkey_first_factor'")).first() is not None:
        return
    bind.execute(
        sa.text(
            "INSERT INTO settings (key, value, is_secret, updated_at) "
            "VALUES ('auth.passkey_first_factor', '1', :f, CURRENT_TIMESTAMP)"
        ),
        {"f": False},
    )


def _user_fk(nullable: bool = False) -> sa.Column:
    return sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "user_mfa",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("totp_secret_enc", sa.Text(), nullable=True),
        sa.Column("totp_enabled_at", sa.DateTime(), nullable=True),
        sa.Column("totp_last_step", sa.Integer(), nullable=True),
        sa.Column("totp_pending_enc", sa.Text(), nullable=True),
        sa.Column("totp_pending_at", sa.DateTime(), nullable=True),
        sa.Column("webauthn_user_handle", sa.String(length=64), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("required_since", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("webauthn_user_handle", name="uq_user_mfa_webauthn_user_handle"),
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_mfa_recovery_codes_user_id", "mfa_recovery_codes", ["user_id"])
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column("credential_id", sa.String(length=1400), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transports", sa.JSON(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("aaguid", sa.String(length=36), nullable=True),
        sa.Column("backup_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("credential_id", name="uq_webauthn_credentials_credential_id"),
    )
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])
    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_trusted_devices_token_hash"),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(length=64), nullable=False),
        _user_fk(nullable=True),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("challenge", sa.String(length=128), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("jti", name="uq_auth_challenges_jti"),
    )
    op.create_index("ix_auth_challenges_user_id", "auth_challenges", ["user_id"])
    op.create_index("ix_auth_challenges_expires_at", "auth_challenges", ["expires_at"])
    _seed_fresh_install()
    if op.get_bind().dialect.name != "postgresql" or not _has_rls_helpers():
        return
    for table in sorted({t for t, *_ in POLICIES}):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for table, name, cmd, using in POLICIES:
        check = f" WITH CHECK ({using})" if cmd == "ALL" else ""
        op.execute(f"CREATE POLICY {name} ON {table} AS PERMISSIVE FOR {cmd} USING ({using}){check}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table, name, _cmd, _using in POLICIES:
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    op.drop_index("ix_auth_challenges_expires_at", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_user_id", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_table("trusted_devices")
    op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
    op.drop_index("ix_mfa_recovery_codes_user_id", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_table("user_mfa")
