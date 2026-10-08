"""Review 2026-10-08 fixes: chat-apply claims (M2), job heartbeats (M6), canonical cohort keys in stored
constraint params (usability U1: ``PROG:Hemşirelik:Y1`` -> ``PROG:hemşirelik:Y1``, as the bridge builds them).

Meeting identity (M4) needs no schema change: ``meeting_requests.source_key`` keeps its column and the
planning-list importer re-keys legacy content-hash keys (``PL:<term>:<16 hex>#n``) to the stable
``PL:<term>:id:<section+day digest>#n`` form on the next import of that term, before matching rows.

Revision ID: 0004_review_fixes
Revises: 0003_crbs_parity
Create Date: 2026-10-08 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_review_fixes"
down_revision = "0003_crbs_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_apply_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("schedule_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("diff_id", sa.String(length=64), nullable=False),
        sa.Column("child_run_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("run_id", "diff_id", name="uq_chat_apply_claims_run_diff"),
    )
    op.create_index("ix_chat_apply_claims_run_id", "chat_apply_claims", ["run_id"])
    with op.batch_alter_table("schedule_runs") as b:
        b.add_column(sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("import_jobs") as b:
        b.add_column(sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    _canonical_cohort_params()


def _canonical_cohort_params() -> None:
    """Data migration: cohort / programme selectors of stored rules in the canonical form."""
    from app.importers.normalize import normalize_selector_params

    constraints = sa.table("constraints", sa.column("id", sa.Integer()), sa.column("params", sa.JSON()))
    bind = op.get_bind()
    for cid, params in bind.execute(sa.select(constraints.c.id, constraints.c.params)).all():
        if not isinstance(params, dict):
            continue
        norm = normalize_selector_params(params)
        if norm != params:
            bind.execute(constraints.update().where(constraints.c.id == cid).values(params=norm))


def downgrade() -> None:
    with op.batch_alter_table("import_jobs") as b:
        b.drop_column("heartbeat_at")
    with op.batch_alter_table("schedule_runs") as b:
        b.drop_column("heartbeat_at")
    op.drop_index("ix_chat_apply_claims_run_id", table_name="chat_apply_claims")
    op.drop_table("chat_apply_claims")
