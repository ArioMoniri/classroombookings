"""AI proposal decisions: every reviewed AI / upload / learned proposal and its outcome.

``accepted`` (with the created constraint id), ``rejected`` by the server (reasons, e.g. the per-source
allowlist of review D1) or ``declined`` by the planner in review. Input of the Phase 19 learning lane; never
read by the solver.

Revision ID: 0018_ai_proposal_decisions
Revises: 0017_course_code_fold
Create Date: 2026-10-15 16:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_ai_proposal_decisions"
down_revision = "0017_course_code_fold"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_proposal_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="CASCADE"), nullable=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("schedule_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("hardness", sa.String(8), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.JSON(), nullable=True),
        sa.Column("nl_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("constraint_id", sa.Integer(), sa.ForeignKey("constraints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_proposal_decisions_term_id", "ai_proposal_decisions", ["term_id"])
    op.create_index("ix_ai_proposal_decisions_run_id", "ai_proposal_decisions", ["run_id"])
    op.create_index("ix_ai_proposal_decisions_decision", "ai_proposal_decisions", ["decision"])


def downgrade() -> None:
    op.drop_index("ix_ai_proposal_decisions_decision", table_name="ai_proposal_decisions")
    op.drop_index("ix_ai_proposal_decisions_run_id", table_name="ai_proposal_decisions")
    op.drop_index("ix_ai_proposal_decisions_term_id", table_name="ai_proposal_decisions")
    op.drop_table("ai_proposal_decisions")
