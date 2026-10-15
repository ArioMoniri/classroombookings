"""Write locks (review 2026-10-15 D8): one row per locked scope, e.g. ``term:2026-BAHAR`` while an import or a
commit writes that term. See :mod:`app.services.term_lock`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class TermLock(Base):
    __tablename__ = "term_locks"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    holder: Mapped[str] = mapped_column(String(255))  # "import:12 planning-list (file.xlsx)"
    token: Mapped[str] = mapped_column(String(36))  # owner token: only the holder releases / extends
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)  # a dead holder's lock is taken over after this
