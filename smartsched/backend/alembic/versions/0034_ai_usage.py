"""AI gateway usage metering (wave 3 W3-AI; app/models/ai_usage.py, app/services/ai_usage.py)

* ``ai_usage``: one row per model call through the gateway and per call a guardrail or a limit refused: user,
  feature, provider, model, input / output / cache tokens, estimated cost, latency, outcome, reason code. No prompt
  or answer text is stored.

Revision ID: 0034_ai_usage
Revises: 0033_invig_progress
Create Date: 2026-10-17 19:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0034_ai_usage"
down_revision = "0033_invig_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feature", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=48), nullable=True),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])
    op.create_index("ix_ai_usage_outcome_created", "ai_usage", ["outcome", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_outcome_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_created_at", table_name="ai_usage")
    op.drop_table("ai_usage")
