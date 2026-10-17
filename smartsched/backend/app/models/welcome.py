"""Welcome guide per role (WG-01, alembic 0040_welcome_guide; docs/design/v3/welcome-guide.md §6.3).

``welcome_progress``: one row per person and guide part (``guide_key``: ``sheet``, ``tour``, ``checklist`` or a
feature hint ``hint.<key>``), so the guide is in the same state on every device. Minimal data (KVKK, spec §6.5): no
content, no clicks, no time on page. ``items`` holds, per part:

* ``sheet``: ``{"audiences": [...], "versions": {audience: content_version}}`` - the audiences the person was
  welcomed for (the role-change delta compares against it) and the admin text versions they saw;
* ``checklist``: ``{"done": {item: iso time}, "total": n}`` - the items done (server signals and view-only ticks);
* ``tour`` / ``hint.*``: ``{}``.

Rows go with the account (``ON DELETE CASCADE``), are listed by the DSR export and deleted by the erasure
(``app.services.welcome.dsr_rows`` / ``erase``). On PostgreSQL the ``rls_owner`` policy lets a signed-in user read and
write only their own rows; the completion stats run in ``rls.system_scope``.

``welcome_content``: an administrator's text override per audience, locale and field (text only; order, links and
icons are the product's). ``version`` is the audience's text revision when the row was written.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

#: ``welcome_progress.state`` values
STATES = ("shown", "snoozed", "dismissed", "started", "completed", "hidden", "seen")


class WelcomeProgress(Base):
    __tablename__ = "welcome_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "guide_key", name="uq_welcome_progress_user_key"),
        Index("ix_welcome_progress_key_shown", "guide_key", "first_shown_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    guide_key: Mapped[str] = mapped_column(String(64))
    #: the primary audience when the row was last written (stats group by it)
    audience: Mapped[str] = mapped_column(String(32), default="")
    audience_hash: Mapped[str] = mapped_column(String(16), default="")
    content_version: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(16), default="shown")
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    snooze_count: Mapped[int] = mapped_column(Integer, default=0)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_shown_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WelcomeContent(Base):
    __tablename__ = "welcome_content"
    __table_args__ = (UniqueConstraint("audience", "locale", "field", name="uq_welcome_content_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    audience: Mapped[str] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(5))
    field: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


__all__ = ["STATES", "WelcomeContent", "WelcomeProgress"]
