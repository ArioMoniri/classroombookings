"""Phase 19 backend gaps: program wizard drafts (P19-W-01) and person / programme priority (P19-P-04)

* ``program_drafts``: the wizard's server-side draft (JSON payload per user + term, version, per-path merge memory,
  status draft / committed / undone, the programme and audit event of the commit);
* ``priority_overrides``: a person's (instructor) or a programme's priority for one term, unique per subject;
* ``suggestion_feedback.scope``: an accepted suggestion's scope, term or persistent (P19-S-02); the action may now
  also be ``RESTORE`` (the undo of a dismissal, snooze or acceptance, P19-S-03).

No existing row changes.

Revision ID: 0028_p19_gaps
Revises: 0027_notify_channels
Create Date: 2026-10-16 09:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0028_p19_gaps"
down_revision = "0027_notify_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "program_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("step", sa.String(length=32), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("commit_audit_id", sa.Integer(), nullable=True),
        sa.Column("committed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_program_drafts_owner_term", "program_drafts", ["owner_id", "term_id"])
    op.create_index("ix_program_drafts_term_status", "program_drafts", ["term_id", "status"])
    op.create_table(
        "priority_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "subject_type", "subject_id", name="uq_priority_overrides_subject"),
    )
    with op.batch_alter_table("suggestion_feedback") as batch:
        batch.add_column(sa.Column("scope", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("suggestion_feedback") as batch:
        batch.drop_column("scope")
    op.drop_table("priority_overrides")
    op.drop_index("ix_program_drafts_term_status", table_name="program_drafts")
    op.drop_index("ix_program_drafts_owner_term", table_name="program_drafts")
    op.drop_table("program_drafts")
