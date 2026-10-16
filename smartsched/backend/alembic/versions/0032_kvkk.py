"""KVKK compliance (booking enhancements wave 2, A4; docs/product/booking-enhancements.md §4.7)

* ``retention_policies``, ``privacy_notices``, ``notice_acks``, ``consents``, ``dsr_requests``,
  ``audit_purge_windows`` (app/models/kvkk.py). No retention policy row is created here: the service adds them
  disabled on first use, so nothing is destroyed before an administrator enables a policy.
* The append-only triggers of ``audit_events`` (alembic 0014) are recreated with the two KVKK exceptions
  (app/models/audit.py): DELETE of rows older than 365 days and than an open retention window's cutoff; UPDATE of
  one person's actor columns and snapshots during an anonymise window. Everything else is still refused.

No existing row changes.

Revision ID: 0032_kvkk
Revises: 0031_invigilation
Create Date: 2026-10-16 15:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0032_kvkk"
down_revision = "0031_invigilation"
branch_labels = None
depends_on = None

_IMMUTABLE = ("id", "ts", "action", "entity_type", "entity_id", "term_id", "reversible", "undo_of", "parent_id")
SQLITE = (
    "DROP TRIGGER IF EXISTS audit_events_no_update",
    "DROP TRIGGER IF EXISTS audit_events_no_delete",
    "CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events WHEN NOT ("
    + " AND ".join(f"NEW.{c} IS OLD.{c}" for c in _IMMUTABLE)
    + " AND NEW.actor_type IS OLD.actor_type AND (NEW.actor_id IS NULL OR NEW.actor_id IS OLD.actor_id)"
    " AND EXISTS (SELECT 1 FROM audit_purge_windows w WHERE w.kind = 'anonymise' AND (w.subject_actor_id = OLD.actor_id"
    " OR (OLD.entity_type = 'user' AND OLD.entity_id = CAST(w.subject_actor_id AS TEXT)))))"
    " BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    "CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events WHEN NOT ("
    "COALESCE(OLD.ts, '9999') < datetime('now', '-365 days')"
    " AND COALESCE(OLD.ts, '9999') < COALESCE((SELECT max(cutoff) FROM audit_purge_windows WHERE kind = 'retention'),"
    " '0000'))"
    " BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
)
POSTGRES = (
    "CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
    "IF TG_OP = 'DELETE' THEN "
    "IF OLD.ts < (now() AT TIME ZONE 'UTC') - interval '365 days' AND OLD.ts < COALESCE((SELECT max(cutoff) FROM "
    "audit_purge_windows WHERE kind = 'retention'), '-infinity'::timestamp) THEN RETURN OLD; END IF; "
    "ELSIF TG_OP = 'UPDATE' THEN "
    "IF "
    + " AND ".join(f"NEW.{c} IS NOT DISTINCT FROM OLD.{c}" for c in _IMMUTABLE)
    + " AND NEW.actor_type IS NOT DISTINCT FROM OLD.actor_type"
    " AND (NEW.actor_id IS NULL OR NEW.actor_id IS NOT DISTINCT FROM OLD.actor_id)"
    " AND EXISTS (SELECT 1 FROM audit_purge_windows w WHERE w.kind = 'anonymise' AND (w.subject_actor_id = OLD.actor_id"
    " OR (OLD.entity_type = 'user' AND OLD.entity_id = w.subject_actor_id::text))) THEN RETURN NEW; END IF; "
    "END IF; RAISE EXCEPTION 'audit_events is append-only'; END $$",
    "DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events",
    "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()",
)
# the 0014 triggers, restored by the downgrade
OLD_SQLITE = (
    "DROP TRIGGER IF EXISTS audit_events_no_update",
    "DROP TRIGGER IF EXISTS audit_events_no_delete",
    "CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
)
OLD_POSTGRES = (
    "CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$",
    "DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events",
    "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()",
)


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_class", sa.String(length=32), nullable=False),
        sa.Column("retain_days", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("legal_hold", sa.Boolean(), nullable=False),
        sa.Column("legal_hold_reason", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_result", sa.JSON(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_class"),
    )
    op.create_table(
        "privacy_notices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", "language", name="uq_privacy_notices_version_language"),
    )
    op.create_table(
        "notice_acks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notice_id", sa.Integer(), nullable=False),
        sa.Column("acked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["notice_id"], ["privacy_notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "notice_id", name="uq_notice_acks_user_notice"),
    )
    op.create_index("ix_notice_acks_user_id", "notice_acks", ["user_id"])
    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
        sa.Column("notice_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["notice_id"], ["privacy_notices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consents_user_id", "consents", ["user_id"])
    op.create_table(
        "dsr_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("subject_label", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("handled_by", sa.Integer(), nullable=True),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("download_expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["handled_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dsr_requests_user_id", "dsr_requests", ["user_id"])
    op.create_index("ix_dsr_requests_status", "dsr_requests", ["status"])
    op.create_table(
        "audit_purge_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("cutoff", sa.DateTime(), nullable=True),
        sa.Column("subject_actor_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    dialect = op.get_bind().dialect.name
    for stmt in {"sqlite": SQLITE, "postgresql": POSTGRES}.get(dialect, ()):
        op.execute(stmt)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    for stmt in {"sqlite": OLD_SQLITE, "postgresql": OLD_POSTGRES}.get(dialect, ()):
        op.execute(stmt)
    op.drop_table("audit_purge_windows")
    op.drop_index("ix_dsr_requests_status", table_name="dsr_requests")
    op.drop_index("ix_dsr_requests_user_id", table_name="dsr_requests")
    op.drop_table("dsr_requests")
    op.drop_index("ix_consents_user_id", table_name="consents")
    op.drop_table("consents")
    op.drop_index("ix_notice_acks_user_id", table_name="notice_acks")
    op.drop_table("notice_acks")
    op.drop_table("privacy_notices")
    op.drop_table("retention_policies")
