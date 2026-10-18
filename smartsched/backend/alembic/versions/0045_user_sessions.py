"""Server-side session list (AU-15; app/models/mfa.py ``UserSession``, app/services/sessions.py)

``user_sessions``: one row per signed-in token, keyed by the SHA-256 of the token's ``jti`` (unique), the token version
it carries, created / expires / last seen, the browser + OS family, the client network (/24 or /48) and the
revocation. Cascades with ``users``. PostgreSQL: owner-only row-level security (0035 pattern; the request check runs
in the system context before the request binds its user). SQLite: a plain table.

Revision ID: 0045_user_sessions
Revises: 0044_helper
Create Date: 2026-10-18 12:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0045_user_sessions"
down_revision = "0044_helper"
branch_labels = None
depends_on = None

POLICIES: tuple[tuple[str, str, str, str], ...] = (
    ("user_sessions", "rls_owner", "ALL", "smartsched_rls_system() OR user_id = smartsched_rls_uid()"),
)


def _has_rls_helpers() -> bool:
    row = op.get_bind().execute(sa.text("SELECT 1 FROM pg_proc WHERE proname = 'smartsched_rls_uid'")).first()
    return row is not None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("tv", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("device", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("network", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.String(length=32), nullable=True),
        sa.UniqueConstraint("jti_hash", name="uq_user_sessions_jti_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    if op.get_bind().dialect.name != "postgresql" or not _has_rls_helpers():
        return
    op.execute("ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY")
    for table, name, cmd, using in POLICIES:
        op.execute(f"CREATE POLICY {name} ON {table} AS PERMISSIVE FOR {cmd} USING ({using}) WITH CHECK ({using})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table, name, _cmd, _using in POLICIES:
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
