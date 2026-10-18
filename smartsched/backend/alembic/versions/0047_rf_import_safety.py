"""Re-import safety and import history (RF-06 / RF-08 / RF-09; audit docs/testing/audits/2026-10-17-no-mock-and-editability.md)

* ``import_jobs.created_by_id`` (users, ``SET NULL``) and ``import_jobs.actor`` (``user`` | ``system``): who imported.
  Uploads record the person; CLI imports (the deploy seed among them) record ``system``. Old rows keep NULL (unknown).
* ``weeks.edited``: an admin changed the week's kind, label or start date (``PUT /terms/{id}/weeks`` or
  ``PATCH /terms/{id}/weeks/{index}``); a board re-import keeps those weeks as they are. Old rows: false.
* ``catalog_aliases``: the old canonical name of a renamed programme, faculty or instructor (``entity``, ``alias``
  -> ``target_id``), so the next import maps the file's old spelling to the renamed row instead of creating a
  duplicate. Catalogue data, not per-person: no row-level security.

Works on SQLite (batch mode) and PostgreSQL.

Revision ID: 0047_rf_import_safety
Revises: 0046_ai_quota_units
Create Date: 2026-10-18 15:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0047_rf_import_safety"
down_revision = "0046_ai_quota_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_jobs") as batch:
        batch.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("actor", sa.String(length=16), nullable=True))
        batch.create_foreign_key("fk_import_jobs_created_by", "users", ["created_by_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_import_jobs_created_by_id", ["created_by_id"])
    with op.batch_alter_table("weeks") as batch:
        batch.add_column(sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "catalog_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity", sa.String(length=16), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("entity", "alias", name="uq_catalog_aliases_entity_alias"),
    )
    op.create_index("ix_catalog_aliases_target", "catalog_aliases", ["entity", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_catalog_aliases_target", table_name="catalog_aliases")
    op.drop_table("catalog_aliases")
    with op.batch_alter_table("weeks") as batch:
        batch.drop_column("edited")
    with op.batch_alter_table("import_jobs") as batch:
        batch.drop_index("ix_import_jobs_created_by_id")
        batch.drop_constraint("fk_import_jobs_created_by", type_="foreignkey")
        batch.drop_column("actor")
        batch.drop_column("created_by_id")
