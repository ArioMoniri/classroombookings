"""Parity B-AUTH-11: ``users.token_version``. Access tokens carry it as the ``tv`` claim; sign-out, password
changes and resets, disabling an account and role changes bump it, so earlier tokens answer 401 at once instead
of living until they expire (JWT_EXPIRE_MINUTES).

Revision ID: 0006_token_version
Revises: 0005_crbs_legacy_ids
Create Date: 2026-10-08 15:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_token_version"
down_revision = "0005_crbs_legacy_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")
