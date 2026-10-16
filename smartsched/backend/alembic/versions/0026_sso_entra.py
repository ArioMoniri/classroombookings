"""Sign-in with Microsoft Entra ID (owner decisions 2026-10-15; app/services/sso.py, docs/deploy/sso-entra.md):

* ``sso_providers``: the pinned tenant, client id, encrypted client secret and the guard switches (``self_signup``
  on, ``oidc_only_non_admins`` / ``role_mapping_enabled`` / ``allow_admin_mapping`` off, ``invite_days`` 30);
* ``user_identities``: the IdP identity of a user, unique on ``(provider, tenant_id, subject)`` (= ``tid + oid``)
  and on ``(user_id, provider)``;
* ``sso_invites``: admin invites / "bind on next SSO login", one per user and one per address, the link token
  hashed (lookup) and encrypted (copy link);
* ``sso_role_mappings``: optional Entra app role / group object id -> role;
* ``sso_auth_states``: single-use login / link states (PKCE verifier encrypted, nonce hashed) and one-time tickets.

No row is written: Entra sign-in stays off until an administrator stores the tenant, the client and the secret.

Revision ID: 0026_sso_entra
Revises: 0025_approval_first
Create Date: 2026-10-16 09:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0026_sso_entra"
down_revision = "0025_approval_first"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sso_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("client_secret_enc", sa.Text(), nullable=True),
        sa.Column("self_signup", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("domain_hint", sa.String(length=255), nullable=True),
        sa.Column("default_role_id", sa.Integer(), nullable=True),
        sa.Column("oidc_only_non_admins", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("role_mapping_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("allow_admin_mapping", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("invite_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["default_role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("email_at_login", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "tenant_id", "subject", name="uq_user_identities_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.create_table(
        "sso_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_enc", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "email", name="uq_sso_invites_email"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "sso_role_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("claim", sa.String(length=8), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "claim", "value", name="uq_sso_role_mappings_value"),
    )
    op.create_index("ix_sso_role_mappings_role_id", "sso_role_mappings", ["role_id"])
    op.create_table(
        "sso_auth_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=8), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=True),
        sa.Column("code_verifier_enc", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("return_path", sa.String(length=255), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_sso_auth_states_expires_at", "sso_auth_states", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sso_auth_states_expires_at", table_name="sso_auth_states")
    op.drop_table("sso_auth_states")
    op.drop_index("ix_sso_role_mappings_role_id", table_name="sso_role_mappings")
    op.drop_table("sso_role_mappings")
    op.drop_table("sso_invites")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_table("sso_providers")
