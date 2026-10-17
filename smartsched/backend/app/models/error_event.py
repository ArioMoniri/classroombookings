"""Grouped error events (W3-OPS, alembic 0036_error_events).

One row per *group*: every unhandled backend exception, every 5xx answer and every browser error report
(``POST /api/v1/ops/errors``) is reduced to a fingerprint (source + type + normalised message + in-app frames +
route template, ``app.core.observability.fingerprint``) and folded into its group: ``count`` and ``last_seen``
move, the first sample stack is kept. Text is PII-scrubbed before it is stored (``scrub``). ``status`` is set by
an admin on ``/admin/ops``: ``open`` -> ``resolved`` (a new occurrence reopens the group: regression) or
``ignored`` (stays ignored, keeps counting).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

OPEN = "open"
RESOLVED = "resolved"
IGNORED = "ignored"
STATUSES = (OPEN, RESOLVED, IGNORED)


class ErrorEvent(Base):
    __tablename__ = "error_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    #: backend | frontend
    source: Mapped[str] = mapped_column(String(16), index=True)
    #: exception class (``KeyError``), ``http_5xx`` for an error answer without an exception, the browser's error name
    kind: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(String(1000), default="")
    #: route template (``/api/v1/runs/{run_id}``) or the browser page path without query string
    route: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: role code of the signed-in user of the *last* occurrence (no user id: groups are not per person)
    user_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    release: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(10), default=OPEN, index=True)
    #: how often a resolved group came back
    reopened: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
