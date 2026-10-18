"""Voice metering on ``ai_usage`` (VO-02; docs/research/2026-10-17-voice-ai.md §3.3)

* ``audio_ms`` (integer, default 0): the length of the audio a speech-to-text call processed (the provider's
  reported length, else the clip header's);
* ``modality`` (``text`` | ``audio_in`` | ``audio_out``, default ``text``): every existing row is a text call.

The audio-second limits live in the ``ai.limits`` setting (no schema). Works on SQLite (batch mode) and PostgreSQL;
the row-level security policy of ``ai_usage`` (0035_rls_policies) is per row and needs no change.

Revision ID: 0042_ai_usage_audio
Revises: 0041_adaptive
Create Date: 2026-10-17 23:55:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0042_ai_usage_audio"
down_revision = "0041_adaptive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage") as batch:
        batch.add_column(sa.Column("audio_ms", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("modality", sa.String(length=12), nullable=False, server_default="text"))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage") as batch:
        batch.drop_column("modality")
        batch.drop_column("audio_ms")
