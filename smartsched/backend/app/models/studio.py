"""Generator Studio state: per-user drafts, university-wide presets and imported-value snapshots.

* ``studio_drafts``: one row per (term, user, kind). Holds what a planner shaped in the studio
  (scope, left-out classes, pins, per-draft rule overrides) without touching term-wide data.
  Optimistic concurrency through ``version``.
* ``studio_presets``: portable snapshots of rules (names, not ids), scope defaults and include /
  exclude filters; any PLANNER can use them, ADMIN can delete them.
* ``imported_snapshots``: the normalised values of a meeting request / section *before the first
  studio edit* so any field can be reverted ("changed vs imported"). ``fingerprint`` is a hash of
  the imported source row; a re-import with different content makes the snapshot stale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utcnow


class StudioPreset(TimestampMixin, Base):
    __tablename__ = "studio_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(8), default="COURSE")  # COURSE | EXAM
    rules: Mapped[list[Any]] = mapped_column(JSON, default=list)  # portable rule dicts (names, not ids)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {horizon, horizon_params}
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {exclude: {...}, include_only: {...}}
    disabled_builtin_kinds: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class StudioDraft(TimestampMixin, Base):
    __tablename__ = "studio_drafts"
    __table_args__ = (UniqueConstraint("term_id", "user_id", "kind", name="uq_studio_drafts_term_user_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8), default="COURSE")  # COURSE | EXAM
    version: Mapped[int] = mapped_column(Integer, default=1)
    horizon: Mapped[str] = mapped_column(String(8), default="TERM")  # WEEK | MONTH | TERM
    horizon_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    #: meeting_request ids (COURSE) or exam_request ids (EXAM) left out of this draft only
    excluded_event_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: [{event_id, room_ids?, day?, start_period?}] honoured only by runs generated from this draft
    pins: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: constraint ids switched off for this draft only (term rows stay enabled)
    disabled_rule_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #: {"<constraint id>": {"hardness": "soft", "weight": 8}} applied on top of the term rows
    rule_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preset_id: Mapped[int | None] = mapped_column(ForeignKey("studio_presets.id", ondelete="SET NULL"), nullable=True)
    last_step: Mapped[str | None] = mapped_column(String(16), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # time_limit_s, seed, weights, ...
    last_precheck: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ImportedSnapshot(Base):
    __tablename__ = "imported_snapshots"
    __table_args__ = (UniqueConstraint("entity", "entity_id", name="uq_imported_snapshots_entity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(16))  # meeting | section
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
