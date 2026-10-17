"""Several identity providers set by administrators (wave 3b W3-IDP; app/services/identity/**, app/services/sso.py):

* ``sso_providers`` gains ``kind`` (entra | google_workspace | oidc | saml), ``display_name``, ``sort_order``,
  ``allowed_domains``, ``invite_only``, ``options`` (non-secret kind settings) and the last check
  (``last_check_at`` / ``last_check_ok`` / ``last_check_detail``); ``name`` (the URL slug) widens to 40 characters.
* The existing Entra row is kept as it is (``kind = 'entra'``, every value unchanged): lossless.
* ``provider`` columns of the identity, invite, mapping and state tables widen to 40 characters (slugs such as
  ``yetkim-federasyonu``); ``user_identities.subject`` widens to 255 (OIDC ``sub``, SAML persistent NameID).

Downgrade: the rows of the new kinds (and their identities, invites, mappings and states) are removed, the Entra row
and its rows stay; the columns narrow back.

Revision ID: 0037_identity_providers
Revises: 0036_error_events
Create Date: 2026-10-17 21:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0037_identity_providers"
down_revision = "0036_error_events"
branch_labels = None
depends_on = None

_SLUG_TABLES = ("user_identities", "sso_invites", "sso_role_mappings", "sso_auth_states")


def upgrade() -> None:
    with op.batch_alter_table("sso_providers") as b:
        b.alter_column("name", existing_type=sa.String(length=16), type_=sa.String(length=40), existing_nullable=False)
        b.add_column(sa.Column("kind", sa.String(length=24), server_default="entra", nullable=False))
        b.add_column(sa.Column("display_name", sa.String(length=80), nullable=True))
        b.add_column(sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
        b.add_column(sa.Column("allowed_domains", sa.JSON(), nullable=True))
        b.add_column(sa.Column("invite_only", sa.Boolean(), server_default=sa.false(), nullable=False))
        b.add_column(sa.Column("options", sa.JSON(), nullable=True))
        b.add_column(sa.Column("last_check_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("last_check_ok", sa.Boolean(), nullable=True))
        b.add_column(sa.Column("last_check_detail", sa.String(length=255), nullable=True))
    for table in _SLUG_TABLES:
        with op.batch_alter_table(table) as b:
            b.alter_column(
                "provider", existing_type=sa.String(length=16), type_=sa.String(length=40), existing_nullable=False
            )
    with op.batch_alter_table("user_identities") as b:
        b.alter_column(
            "subject", existing_type=sa.String(length=64), type_=sa.String(length=255), existing_nullable=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    others = sa.text("select name from sso_providers where kind <> 'entra' or length(name) > 16")
    slugs = [r[0] for r in bind.execute(others)]
    for slug in slugs:
        for table in _SLUG_TABLES:
            bind.execute(sa.text(f"delete from {table} where provider = :p"), {"p": slug})  # noqa: S608 - fixed names
        bind.execute(sa.text("delete from sso_providers where name = :p"), {"p": slug})
    bind.execute(sa.text("delete from user_identities where length(subject) > 64"))
    with op.batch_alter_table("user_identities") as b:
        b.alter_column(
            "subject", existing_type=sa.String(length=255), type_=sa.String(length=64), existing_nullable=False
        )
    for table in _SLUG_TABLES:
        with op.batch_alter_table(table) as b:
            b.alter_column(
                "provider", existing_type=sa.String(length=40), type_=sa.String(length=16), existing_nullable=False
            )
    with op.batch_alter_table("sso_providers") as b:
        for col in (
            "last_check_detail",
            "last_check_ok",
            "last_check_at",
            "options",
            "invite_only",
            "allowed_domains",
            "sort_order",
            "display_name",
            "kind",
        ):
            b.drop_column(col)
        b.alter_column("name", existing_type=sa.String(length=40), type_=sa.String(length=16), existing_nullable=False)
