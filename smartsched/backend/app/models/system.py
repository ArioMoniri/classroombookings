"""Settings, users, import jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted when is_secret
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: optional since CRBS parity (CRBS users may have only a username); unique when present
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # = CRBS displayname
    #: code of the user's role (ADMIN, PLANNER, VIEWER, TEACHER) or CUSTOM; kept in sync with role_id
    role: Mapped[str] = mapped_column(String(8), default="VIEWER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    legacy_crbs_user_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # CRBS parity (docs/CRBS_PARITY.md)
    username: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    firstname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lastname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ext: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    force_password_reset: Mapped[bool] = mapped_column(Boolean, default=False)
    auth_source: Mapped[str] = mapped_column(String(8), default="local")  # local | ldap
    # calendar_token (plaintext) moved to calendar_feed_tokens.token_hash in alembic 0011_integrations
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: bumped to sign the user out everywhere (sign-out, password change/reset, disabling, role change); access
    #: tokens carry it as the ``tv`` claim and a token with an older value answers 401 (parity B-AUTH-11)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    term_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")  # QUEUED, RUNNING, DONE, FAILED
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # review M6
