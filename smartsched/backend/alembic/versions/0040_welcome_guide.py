"""Welcome guide per role (WG-01; docs/design/v3/welcome-guide.md §6.3, app/models/welcome.py)

* ``welcome_progress``: per person and guide part (sheet, tour, checklist, hint.*), unique (user_id, guide_key),
  ``ON DELETE CASCADE`` with the account;
* ``welcome_content``: an administrator's text override per audience, locale and field (≤ 200 characters), unique
  (audience, locale, field); the editor is ``SET NULL`` when the account is deleted.

The switches (settings group ``welcome``) are ordinary ``settings`` rows with code defaults: nothing to seed.

PostgreSQL: ``welcome_progress`` gets row-level security in the 0035_rls_policies pattern (owner only: the signed-in
user's own rows, or the system context; administrators' aggregates run in ``rls.system_scope``). The tables get the
RLS role's default privileges from 0035. SQLite: plain tables.

Revision ID: 0040_welcome_guide
Revises: 0039_calendar_classes
Create Date: 2026-10-17 23:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0040_welcome_guide"
down_revision = "0039_calendar_classes"
branch_labels = None
depends_on = None

#: (table, policy name, command, USING expression); the helper functions come from 0035_rls_policies
POLICIES: tuple[tuple[str, str, str, str], ...] = (
    ("welcome_progress", "rls_owner", "ALL", "smartsched_rls_system() OR user_id = smartsched_rls_uid()"),
)


def _has_rls_helpers() -> bool:
    row = op.get_bind().execute(sa.text("SELECT 1 FROM pg_proc WHERE proname = 'smartsched_rls_uid'")).first()
    return row is not None


def upgrade() -> None:
    op.create_table(
        "welcome_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guide_key", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("audience_hash", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="shown"),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("snooze_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snoozed_until", sa.DateTime(), nullable=True),
        sa.Column("first_shown_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "guide_key", name="uq_welcome_progress_user_key"),
    )
    op.create_index("ix_welcome_progress_user_id", "welcome_progress", ["user_id"])
    op.create_index("ix_welcome_progress_key_shown", "welcome_progress", ["guide_key", "first_shown_at"])
    op.create_table(
        "welcome_content",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audience", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("audience", "locale", "field", name="uq_welcome_content_field"),
    )
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
    op.drop_table("welcome_content")
    op.drop_index("ix_welcome_progress_key_shown", table_name="welcome_progress")
    op.drop_index("ix_welcome_progress_user_id", table_name="welcome_progress")
    op.drop_table("welcome_progress")
