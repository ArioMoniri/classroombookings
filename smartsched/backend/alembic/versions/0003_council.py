"""ingestion council: council_jobs, council_steps, council_artifacts

Revision ID: 0003_council
Revises: 0002_studio
Create Date: 2026-10-08 10:30:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_council"
down_revision = "0002_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "council_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("ai_mode", sa.String(length=16), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("year_hint", sa.Integer(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("commits", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_council_jobs_status", "council_jobs", ["status"])
    op.create_table(
        "council_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("file_index", sa.Integer(), nullable=True),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["council_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_council_steps_job_id", "council_steps", ["job_id"])
    op.create_table(
        "council_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("file_index", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["council_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["council_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_council_artifacts_job_id", "council_artifacts", ["job_id"])
    op.create_index("ix_council_artifacts_kind", "council_artifacts", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_council_artifacts_kind", table_name="council_artifacts")
    op.drop_index("ix_council_artifacts_job_id", table_name="council_artifacts")
    op.drop_table("council_artifacts")
    op.drop_index("ix_council_steps_job_id", table_name="council_steps")
    op.drop_table("council_steps")
    op.drop_index("ix_council_jobs_status", table_name="council_jobs")
    op.drop_table("council_jobs")
