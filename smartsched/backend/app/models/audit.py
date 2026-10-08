"""P7 audit log (docs/product/booking-enhancements.md §4.6): one append-only row per meaningful change.

Rows are written only through :mod:`app.services.audit` (explicit ``record`` calls from the booking, feature and
approval services, and the ``track`` flush hook for the administration tables). The table refuses UPDATE and
DELETE at the database level (triggers created with the table, here for ``create_all`` and in alembic
``0009_audit_events``); an undo is a new row pointing at the original (``undo_of``), never an edit of it."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text, event, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id", "id"),
        Index("ix_audit_events_actor", "actor_id", "id"),
        Index("ix_audit_events_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor_type: Mapped[str] = mapped_column(String(16), default="user")  # user | system | anonymous
    #: no foreign key: the row outlives the account (KVKK retention nulls it later through a migration-owned job)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)  # snapshot of the name
    action: Mapped[str] = mapped_column(String(64), index=True)  # booking.cancel, room.update, ...
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    term_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: only the changed fields: {field: [old, new]}
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: HMAC of the client address truncated to /24 (IPv4) or /48 (IPv6): KVKK data minimisation
    ip_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reversible: Mapped[bool] = mapped_column(Boolean, default=False)
    undo_of: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    #: bulk operations: one parent row, one child row per entity
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


#: DB-level append-only guard; the same statements run in alembic 0009_audit_events
APPEND_ONLY_SQLITE = (
    "CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
)
APPEND_ONLY_POSTGRES = (
    "CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$",
    "DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events",
    "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()",
)


@event.listens_for(AuditEvent.__table__, "after_create")
def _append_only(target: Any, connection: Any, **kw: Any) -> None:  # noqa: ARG001
    statements = {"sqlite": APPEND_ONLY_SQLITE, "postgresql": APPEND_ONLY_POSTGRES}.get(connection.dialect.name, ())
    for stmt in statements:
        connection.execute(text(stmt))
