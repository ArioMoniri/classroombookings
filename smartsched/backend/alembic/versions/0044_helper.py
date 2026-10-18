"""AI helper tables (HB-04; docs/research/2026-10-17-ai-helper-architecture.md §5.4, §5.7; app/models/helper.py)

* ``helper_action_invocations``: one row per confirmed helper write; ``nonce`` unique (the once-only claim of the
  signed confirm token), ``undo_of`` self-reference ``SET NULL``;
* ``helper_threads`` / ``helper_messages``: conversation history (30 days by default);
* ``helper_notes``: memory the person chose to keep (≤ 20, ≤ 200 characters, 180 days since last use);
* ``helper_events``: telemetry without prompt text; ``user_id`` ``SET NULL`` (and nulled after 90 days by the purge).

Every per-person table goes with the account (``ON DELETE CASCADE``). PostgreSQL: owner-only row-level security in
the 0035_rls_policies pattern (the signed-in user's own rows, or the system context; aggregates and purges run in
``rls.system_scope``); the RLS role gets the tables through 0035's default privileges. SQLite: plain tables.

Revision ID: 0044_helper
Revises: 0043_mfa
Create Date: 2026-10-18 01:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0044_helper"
down_revision = "0043_mfa"
branch_labels = None
depends_on = None

OWNER = "smartsched_rls_system() OR user_id = smartsched_rls_uid()"
#: (table, policy name, command, USING expression); the helper functions come from 0035_rls_policies
POLICIES: tuple[tuple[str, str, str, str], ...] = (
    ("helper_action_invocations", "rls_owner", "ALL", OWNER),
    ("helper_threads", "rls_owner", "ALL", OWNER),
    ("helper_messages", "rls_owner", "ALL", OWNER),
    ("helper_notes", "rls_owner", "ALL", OWNER),
    ("helper_events", "rls_owner", "ALL", OWNER),
)


def _has_rls_helpers() -> bool:
    row = op.get_bind().execute(sa.text("SELECT 1 FROM pg_proc WHERE proname = 'smartsched_rls_uid'")).first()
    return row is not None


def upgrade() -> None:
    op.create_table(
        "helper_action_invocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("args_hash", sa.String(length=64), nullable=False),
        sa.Column("preview_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="confirmed"),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("audit_id", sa.Integer(), nullable=True),
        sa.Column("undo_event_id", sa.Integer(), nullable=True),
        sa.Column(
            "undo_of",
            sa.Integer(),
            sa.ForeignKey("helper_action_invocations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(length=48), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("nonce", name="uq_helper_invocations_nonce"),
    )
    op.create_index("ix_helper_invocations_user_created", "helper_action_invocations", ["user_id", "created_at"])
    op.create_table(
        "helper_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_helper_threads_user_id", "helper_threads", ["user_id"])
    op.create_index("ix_helper_threads_last_at", "helper_threads", ["last_at"])
    op.create_table(
        "helper_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.Integer(), sa.ForeignKey("helper_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("cards", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_helper_messages_thread_id", "helper_messages", ["thread_id"])
    op.create_index("ix_helper_messages_user_id", "helper_messages", ["user_id"])
    op.create_table(
        "helper_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_helper_notes_user_id", "helper_notes", ["user_id"])
    op.create_index("ix_helper_notes_expires_at", "helper_notes", ["expires_at"])
    op.create_table(
        "helper_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("turn_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("feature_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=8), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_helper_events_user_id", "helper_events", ["user_id"])
    op.create_index("ix_helper_events_ts_kind", "helper_events", ["ts", "kind"])
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
    op.drop_index("ix_helper_events_ts_kind", table_name="helper_events")
    op.drop_index("ix_helper_events_user_id", table_name="helper_events")
    op.drop_table("helper_events")
    op.drop_index("ix_helper_notes_expires_at", table_name="helper_notes")
    op.drop_index("ix_helper_notes_user_id", table_name="helper_notes")
    op.drop_table("helper_notes")
    op.drop_index("ix_helper_messages_user_id", table_name="helper_messages")
    op.drop_index("ix_helper_messages_thread_id", table_name="helper_messages")
    op.drop_table("helper_messages")
    op.drop_index("ix_helper_threads_last_at", table_name="helper_threads")
    op.drop_index("ix_helper_threads_user_id", table_name="helper_threads")
    op.drop_table("helper_threads")
    op.drop_index("ix_helper_invocations_user_created", table_name="helper_action_invocations")
    op.drop_table("helper_action_invocations")
