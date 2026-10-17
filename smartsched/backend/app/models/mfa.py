"""Two-step sign-in, passkeys and trusted devices (AU-B, alembic 0043_mfa; docs/research/2026-10-18-auth-backend.md).

Every row belongs to one person (``ON DELETE CASCADE`` with the account) and, on PostgreSQL, sits behind the owner-only
row-level security policy (``rls_owner``): the signed-in user's own rows, or the system context (sign-in runs
unauthenticated; administrator resets run in ``rls.system_scope``).

Nothing here is readable as a secret: the TOTP seed is Fernet-encrypted with the key derived from ``APP_SECRET``
(like the other stored secrets), recovery codes are argon2id hashes, trusted-device and challenge tokens are SHA-256
hashes; WebAuthn keeps only public keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class UserMfa(Base):
    """One row per person who started using a second factor (or whom the policy started counting for)."""

    __tablename__ = "user_mfa"
    __table_args__ = (UniqueConstraint("webauthn_user_handle", name="uq_user_mfa_webauthn_user_handle"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    #: Fernet token of the Base32 TOTP secret (``None`` = the authenticator app is off)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: the last TOTP step accepted (a code works once; RFC 6238 replay rule)
    totp_last_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: an enrolment in progress: encrypted secret + when it started (valid 15 minutes)
    totp_pending_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_pending_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: random WebAuthn user handle (base64url, never the e-mail or the id)
    webauthn_user_handle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: consecutive failed second-factor attempts and the lock they caused
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: first sign-in under ``auth.mfa_policy = required_for_roles`` (the grace period counts from here)
    required_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: argon2id hash of the 16 canonical characters
    code_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"
    __table_args__ = (UniqueConstraint("credential_id", name="uq_webauthn_credentials_credential_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: base64url credential id (unique across the installation: passkey-first sign-in finds the account by it)
    credential_id: Mapped[str] = mapped_column(String(1400))
    #: base64url COSE public key
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    transports: Mapped[list[str]] = mapped_column(JSON, default=list)
    name: Mapped[str] = mapped_column(String(64))
    aaguid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    #: BE / BS flags: a synced passkey (iCloud Keychain, Google Password Manager, 1Password, ...)
    backup_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TrustedDevice(Base):
    __tablename__ = "trusted_devices"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_trusted_devices_token_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: SHA-256 hex of the 256-bit device token (the token lives only in the browser's httpOnly cookie)
    token_hash: Mapped[str] = mapped_column(String(64))
    #: browser + OS family ("Safari, iPhone"), no version, no address
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthChallenge(Base):
    """A short-lived step of a sign-in or a ceremony: the second factor after the password (``mfa``), enrolment that
    the policy forces (``setup``), passkey registration (``register``) and passkey-first sign-in (``passkey``, no user
    yet). The client holds a signed token naming ``jti``; the row makes it single use and counts the tries."""

    __tablename__ = "auth_challenges"
    __table_args__ = (UniqueConstraint("jti", name="uq_auth_challenges_jti"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    #: base64url WebAuthn challenge (registration / assertion), else ``None``
    challenge: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: how the password step went (``auth_method``: local / ldap) and other non-secret context
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


__all__ = ["AuthChallenge", "MfaRecoveryCode", "TrustedDevice", "UserMfa", "WebAuthnCredential"]
