"""Phase 19 learning lane (P19-L1) + catalogue batch (P19-C4) + priority columns (P19-M2).

* ``learning_resets``, ``learned_observations``, ``learned_priors``, ``suggestion_feedback`` (app/models/learning.py)
* ``instructors.user_id`` (nullable, unique, FK users ON DELETE SET NULL): the Instructor <-> User link
* ``source_key`` (unique, nullable) + ``archived`` (default false) on faculties, programs, courses, instructors
* ``sections.enrolment_estimated`` (default false), ``meeting_requests.duration_periods`` (nullable: time-flexible
  requests; how the solver bridge places a request without ``start_period`` is the bridge owner's decision)
* unique ``(faculty_id, canonical_name)`` on programs. ``programs.canonical_name`` is already unique on its own, so
  existing data cannot clash; the global index stays until the importers look programmes up per faculty
* ``sections.priority`` (smallint, default 0) and ``meeting_requests.priority`` (nullable per-request override)

``constraints.source`` gains the value ``LEARNED`` (String(8), no CHECK constraint: nothing to migrate).

Revision ID: 0023_learning
Revises: 0022_kvkk_signoff_unseed
Create Date: 2026-10-15 20:40:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_learning"
down_revision = "0022_kvkk_signoff_unseed"
branch_labels = None
depends_on = None

CATALOG = ("faculties", "programs", "courses", "instructors")


def upgrade() -> None:
    op.create_table(
        "learning_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("scope_type", sa.String(8), nullable=False),
        sa.Column("scope_value", sa.String(64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("watermark", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("undone_at", sa.DateTime(), nullable=True),
        sa.Column("undone_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("purged_at", sa.DateTime(), nullable=True),
        sa.Column("counts", sa.JSON(), nullable=False),
    )
    op.create_index("ix_learning_resets_scope", "learning_resets", ["scope_type", "scope_value"])

    op.create_table(
        "learned_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_key", sa.String(64), nullable=False),
        sa.Column("attribute", sa.String(16), nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("sign", sa.SmallInteger(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("source_table", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reset_id", sa.Integer(), sa.ForeignKey("learning_resets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "source_table",
            "source_id",
            "kind",
            "subject_type",
            "subject_key",
            "attribute",
            "value",
            name="uq_learned_observations_source",
        ),
    )
    op.create_index("ix_learned_observations_term_id", "learned_observations", ["term_id"])
    op.create_index("ix_learned_observations_reset_id", "learned_observations", ["reset_id"])
    op.create_index("ix_learned_observations_subject", "learned_observations", ["subject_type", "subject_key"])

    op.create_table(
        "learned_priors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_key", sa.String(64), nullable=False),
        sa.Column("attribute", sa.String(16), nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("support", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("terms_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("suggestible", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=True),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "term_id", "subject_type", "subject_key", "attribute", "value", name="uq_learned_priors_scope"
        ),
    )
    op.create_index("ix_learned_priors_term_id", "learned_priors", ["term_id"])

    op.create_table(
        "suggestion_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prior_id", sa.Integer(), sa.ForeignKey("learned_priors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("term_id", sa.Integer(), sa.ForeignKey("terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_key", sa.String(64), nullable=False),
        sa.Column("attribute", sa.String(16), nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("snooze_mode", sa.String(16), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(), nullable=True),
        sa.Column("constraint_id", sa.Integer(), sa.ForeignKey("constraints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reset_id", sa.Integer(), sa.ForeignKey("learning_resets.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_suggestion_feedback_prior_id", "suggestion_feedback", ["prior_id"])
    op.create_index("ix_suggestion_feedback_reset_id", "suggestion_feedback", ["reset_id"])
    op.create_index("ix_suggestion_feedback_scope", "suggestion_feedback", ["term_id", "subject_type", "subject_key"])

    for table in CATALOG:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("source_key", sa.String(255), nullable=True))
            batch.add_column(sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
            batch.create_unique_constraint(f"uq_{table}_source_key", ["source_key"])
    with op.batch_alter_table("instructors") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_instructors_user_id", "users", ["user_id"], ["id"], ondelete="SET NULL")
        batch.create_unique_constraint("uq_instructors_user_id", ["user_id"])
    with op.batch_alter_table("programs") as batch:
        batch.create_unique_constraint("uq_programs_faculty_canonical", ["faculty_id", "canonical_name"])
    with op.batch_alter_table("sections") as batch:
        batch.add_column(sa.Column("enrolment_estimated", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("0")))
    with op.batch_alter_table("meeting_requests") as batch:
        batch.add_column(sa.Column("duration_periods", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("priority", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("meeting_requests") as batch:
        batch.drop_column("priority")
        batch.drop_column("duration_periods")
    with op.batch_alter_table("sections") as batch:
        batch.drop_column("priority")
        batch.drop_column("enrolment_estimated")
    with op.batch_alter_table("programs") as batch:
        batch.drop_constraint("uq_programs_faculty_canonical", type_="unique")
    with op.batch_alter_table("instructors") as batch:
        batch.drop_constraint("uq_instructors_user_id", type_="unique")
        batch.drop_constraint("fk_instructors_user_id", type_="foreignkey")
        batch.drop_column("user_id")
    for table in reversed(CATALOG):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"uq_{table}_source_key", type_="unique")
            batch.drop_column("archived")
            batch.drop_column("source_key")

    op.drop_index("ix_suggestion_feedback_scope", table_name="suggestion_feedback")
    op.drop_index("ix_suggestion_feedback_reset_id", table_name="suggestion_feedback")
    op.drop_index("ix_suggestion_feedback_prior_id", table_name="suggestion_feedback")
    op.drop_table("suggestion_feedback")
    op.drop_index("ix_learned_priors_term_id", table_name="learned_priors")
    op.drop_table("learned_priors")
    op.drop_index("ix_learned_observations_subject", table_name="learned_observations")
    op.drop_index("ix_learned_observations_reset_id", table_name="learned_observations")
    op.drop_index("ix_learned_observations_term_id", table_name="learned_observations")
    op.drop_table("learned_observations")
    op.drop_index("ix_learning_resets_scope", table_name="learning_resets")
    op.drop_table("learning_resets")
