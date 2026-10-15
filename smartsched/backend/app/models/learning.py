"""Learned suggestions with resettable memory (Phase 19 P19-L1; review 2026-10-15 §3b).

* ``learned_observations``: append-only evidence extracted from existing tables (definitive rooms, planner
  corrections, manual moves and locks, request text, booking series, approvals, suggestion decisions). One row
  per (source row, kind, subject, attribute, value): re-running an extractor adds nothing. ``reset_id`` hides a
  row from the priors (memory reset); a purge deletes it. No personal text is stored: subjects are ids.
* ``learned_priors``: per target term, the decayed score + Wilson confidence of one (subject, attribute, value),
  its proposal (a soft targeted rule) and a TR/EN explanation template. ``{subject}`` in the stored text is
  filled at read time from the FK, so no instructor name is ever stored here (KVKK).
* ``suggestion_feedback``: each accept / reject / snooze, keyed by the prior's scope (term + subject + attribute
  + value) so a decision survives a recompute.
* ``learning_resets``: one row per memory reset (person / term / all) or KVKK erasure, with the watermark that
  keeps reset evidence from being learned again, the 30-day undo window and the purge stamp.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

#: who or what an observation is about (ids, never names)
SUBJECT_TYPES = ("instructor", "course", "section", "program", "user")
#: what the observation says about the subject
ATTRIBUTES = ("room", "building", "day", "period", "day_period", "tag")
RESET_SCOPES = ("person", "term", "all")
FEEDBACK_ACTIONS = ("ACCEPT", "REJECT", "SNOOZE")


class LearningReset(Base):
    __tablename__ = "learning_resets"
    __table_args__ = (Index("ix_learning_resets_scope", "scope_type", "scope_value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: RESET (undoable for 30 days, then purged) | ERASURE (KVKK: purged at once, never undone)
    kind: Mapped[str] = mapped_column(String(8), default="RESET")
    scope_type: Mapped[str] = mapped_column(String(8))  # person | term | all
    #: instructor id (person), term id (term), null (all)
    scope_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    #: evidence dated up to the watermark is never learned again for this scope (until the reset is undone)
    watermark: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    undone_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: what the reset hid: {"observations": n, "feedback": n, "suggestions": n}
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LearnedObservation(Base):
    __tablename__ = "learned_observations"
    __table_args__ = (
        # one observation per source row, kind and (subject, attribute, value): a request row yields course,
        # section, instructor and programme evidence for each of its rooms and its building
        UniqueConstraint(
            "source_table",
            "source_id",
            "kind",
            "subject_type",
            "subject_key",
            "attribute",
            "value",
            name="uq_learned_observations_source",
        ),
        Index("ix_learned_observations_subject", "subject_type", "subject_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: when the evidence happened (the source row's time): the reset watermark is compared with it
    ts: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_key: Mapped[str] = mapped_column(String(64))
    attribute: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(64))
    sign: Mapped[int] = mapped_column(SmallInteger, default=1)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    source_table: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reset_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_resets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: non-personal provenance for "Kanıtı göster": request id, course code, section label, day/periods, rooms
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class LearnedPrior(Base):
    __tablename__ = "learned_priors"
    __table_args__ = (
        UniqueConstraint(
            "term_id", "subject_type", "subject_key", "attribute", "value", name="uq_learned_priors_scope"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: the target term the prior was computed for (decay counts terms from it)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), index=True)
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_key: Mapped[str] = mapped_column(String(64))
    attribute: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    #: positive evidence rows, the subject's rows of this attribute (positive + negative), distinct terms
    support: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    terms_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    #: passes the thresholds and has a rule to propose
    suggestible: Mapped[bool] = mapped_column(Boolean, default=False)
    #: false once no visible evidence is left (after a reset); the row is kept so its id stays stable
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: {"kind", "params"} of the soft targeted rule accepting would add (None: nothing to propose)
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: {"tr", "en"} with ``{subject}`` filled at read time (no names stored)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    #: {"terms": [{"term_id", "code", "pos", "total"}], "request_ids": [...], "kinds": {...}, "cross_season"}
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SuggestionFeedback(Base):
    __tablename__ = "suggestion_feedback"
    __table_args__ = (Index("ix_suggestion_feedback_scope", "term_id", "subject_type", "subject_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prior_id: Mapped[int | None] = mapped_column(
        ForeignKey("learned_priors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"))
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_key: Mapped[str] = mapped_column(String(64))
    attribute: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(8))  # ACCEPT | REJECT | SNOOZE
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: SNOOZE: next_solve | P7D | next_term
    snooze_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    constraint_id: Mapped[int | None] = mapped_column(ForeignKey("constraints.id", ondelete="SET NULL"), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reset_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_resets.id", ondelete="SET NULL"), nullable=True, index=True
    )


__all__ = [
    "ATTRIBUTES",
    "FEEDBACK_ACTIONS",
    "RESET_SCOPES",
    "SUBJECT_TYPES",
    "LearnedObservation",
    "LearnedPrior",
    "LearningReset",
    "SuggestionFeedback",
]
