"""Phase 19 moderation read models (P19-M1): indexes for a person's sections across terms and a term's sections of
one course.

* ``ix_section_instructors_instructor`` on ``section_instructors(instructor_id)`` (the primary key leads with
  ``section_id``, so "every section of this instructor" scanned the table)
* ``ix_sections_term_course`` on ``sections(term_id, course_id)``

Revision ID: 0024_moderation_indexes
Revises: 0023_learning
Create Date: 2026-10-15 21:20:00

"""

from __future__ import annotations

from alembic import op


revision = "0024_moderation_indexes"
down_revision = "0023_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_section_instructors_instructor", "section_instructors", ["instructor_id"])
    op.create_index("ix_sections_term_course", "sections", ["term_id", "course_id"])


def downgrade() -> None:
    op.drop_index("ix_sections_term_course", table_name="sections")
    op.drop_index("ix_section_instructors_instructor", table_name="section_instructors")
