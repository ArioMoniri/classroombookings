"""Login through the institution's identity provider (Microsoft Entra ID; owner decision 2026-10-15,
docs/product/2026-10-15-integrations-options.md §5.5). Alembic ``0026_sso_entra``.

* ``sso_providers``: one row per provider (``entra``): the pinned tenant, the client id, the client secret
  (Fernet, APP_SECRET; never returned), and the guard switches.
* ``user_identities``: the IdP identity of a SmartSched user, keyed by the immutable ``(tenant id, oid)`` -- never
  the e-mail. ``email_at_login`` / ``display_name`` are kept for display only. No IdP token is ever stored.
* ``sso_invites``: an administrator's "invite" (new account) or "bind on next SSO login" (existing account): the
  first Entra login of the pinned tenant whose verified UPN equals ``email`` binds ``(tid, oid)`` once. The invite
  link token is stored hashed (lookup) and encrypted ("copy link").
* ``sso_role_mappings``: optional (off by default) Entra app role / group object id -> SmartSched role.
* ``sso_auth_states``: single-use, short-lived rows: the login / link ``state`` (hashed) with the PKCE verifier
  (encrypted) and the nonce (hashed), and the one-time ``ticket`` the panel exchanges for a session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class SsoProvider(Base):
    __tablename__ = "sso_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(16), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    #: the directory (tenant) id, a GUID; "common" / "organizations" / "consumers" are refused
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``sso_self_signup`` (owner decision 2026-10-15, default on): a first sign-in of the pinned tenant creates an
    #: account with the lowest role; off = invite-only
    self_signup: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    #: the institution's sign-in domain shown on the login page (``uni.edu.tr``); display only, never a check
    domain_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"), nullable=True)
    #: password sign-in (local and LDAP) refused for everyone but administrators
    oidc_only_non_admins: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    #: roles from sso_role_mappings at every login (off: roles are managed in SmartSched only)
    role_mapping_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    #: a mapping may name a privileged role (Administrator, setup.roles) only while this is on
    allow_admin_mapping: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    invite_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "tenant_id", "subject", name="uq_user_identities_subject"),
        UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    issuer: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(36))
    #: Entra ``oid`` (immutable object id of the user in the tenant)
    subject: Mapped[str] = mapped_column(String(64))
    email_at_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: how the identity was attached: provision | invite | bind | link
    origin: Mapped[str] = mapped_column(String(16), default="provision")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SsoInvite(Base):
    __tablename__ = "sso_invites"
    __table_args__ = (UniqueConstraint("provider", "email", name="uq_sso_invites_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    #: folded (Turkish-aware, lower case) UPN / e-mail the verified id_token must carry
    email: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(8))  # invite | bind
    #: the invite link token (``/login?invite=<token>``): SHA-256 for the lookup, Fernet so "copy link" works
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_enc: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class SsoRoleMapping(Base):
    __tablename__ = "sso_role_mappings"
    __table_args__ = (UniqueConstraint("provider", "claim", "value", name="uq_sso_role_mappings_value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    claim: Mapped[str] = mapped_column(String(8))  # role (app role value) | group (group object id)
    value: Mapped[str] = mapped_column(String(128))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SsoAuthState(Base):
    __tablename__ = "sso_auth_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    provider: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str] = mapped_column(String(8))  # login | link | ticket
    nonce_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_verifier_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: link: the signed-in user who confirmed; ticket: the user the session is for
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    return_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: login: ``{"invite_id"}`` when started from an invite link; ticket: ``{"welcome", "inviter"}``
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
