"""I/O of the Entra ID sign-in (``/api/v1/auth/sso/*``; app/services/sso.py). The client secret is write-only: no
output model has a field for it, only ``client_secret_set``."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas import messages
from app.schemas.auth import TokenOut
from app.services import sso as svc


class RoleRef(BaseModel):
    id: int
    code: str | None
    name: str


class SsoConfigIn(BaseModel):
    """Partial update: omitted fields keep their value; an empty ``client_secret`` keeps the stored secret."""

    enabled: bool | None = None
    tenant_id: str | None = Field(default=None, max_length=80)
    client_id: str | None = Field(default=None, max_length=80)
    client_secret: str | None = Field(default=None, max_length=512)
    #: the ``sso_self_signup`` setting (default on): off = invite-only
    self_signup: bool | None = None
    #: login page hint (``uni.edu.tr``); "" clears
    domain_hint: str | None = Field(default=None, max_length=255)
    default_role_id: int | None = None
    oidc_only_non_admins: bool | None = None
    role_mapping_enabled: bool | None = None
    allow_admin_mapping: bool | None = None
    invite_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("tenant_id")
    @classmethod
    def _tenant(cls, v: str | None) -> str | None:
        return messages.validated(svc.clean_tenant, v) if v is not None else None

    @field_validator("domain_hint")
    @classmethod
    def _domain(cls, v: str | None) -> str | None:
        return messages.validated(svc.clean_domain, v) if v is not None else None

    @field_validator("client_id")
    @classmethod
    def _client(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return messages.validated(lambda x: svc.clean_guid(x, "client_id (application id)"), v)

    @field_validator("client_secret")
    @classmethod
    def _secret(cls, v: str | None) -> str | None:
        if v is None:
            return None
        text = v.strip()
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
            raise messages.coded(
                "sso_secret_control_chars",
                "Gizli anahtar denetim karakterleri içeriyor; yeniden yapıştırın.",
                "the client secret contains control characters; paste it again",
            )
        return text


class SsoConfigOut(BaseModel):
    name: str = svc.PROVIDER
    label: str = svc.LABEL
    enabled: bool
    #: tenant, client id, secret and the public URL are all present (the start button works when enabled too)
    configured: bool
    tenant_id: str | None
    client_id: str | None
    client_secret_set: bool
    #: which values come from the environment (SSM) instead of the settings screen
    from_environment: list[str]
    authority: str | None
    redirect_uri: str | None
    public_url_source: str | None
    self_signup: bool
    domain_hint: str | None
    default_role: RoleRef | None
    oidc_only_non_admins: bool
    role_mapping_enabled: bool
    allow_admin_mapping: bool
    invite_days: int
    #: active administrators with a local password (they always keep password sign-in)
    break_glass_admins: int
    updated_at: datetime | None


class MappingIn(BaseModel):
    claim: Literal["role", "group"]
    value: str = Field(min_length=1, max_length=160)
    role_id: int


class MappingOut(BaseModel):
    id: int
    claim: str
    value: str
    role: RoleRef
    created_at: datetime


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=16)
    role_id: int | None = None
    department_id: int | None = None
    #: optional link to an instructor record (flow F-05; ``instructors.user_id``)
    instructor_id: int | None = None
    days: int | None = Field(default=None, ge=1, le=365)


class BindIn(BaseModel):
    #: the UPN / e-mail the user signs in with at Microsoft; default: the account's e-mail
    email: str | None = Field(default=None, max_length=255)
    days: int | None = Field(default=None, ge=1, le=365)


class InviteOut(BaseModel):
    id: int
    user_id: int
    email: str
    kind: str
    status: Literal["invited", "invite_expired"]
    created_at: datetime
    expires_at: datetime
    created_by: int | None
    #: ``/login?invite=<token>`` to copy or e-mail (setup.users only)
    link: str | None


class PublicInviteOut(BaseModel):
    kind: str
    inviter_name: str | None
    role_name: str | None
    invited_masked: str | None
    #: the invited UPN, passed to the start URL as ``login_hint``
    login_hint: str
    days_left: int
    expires_at: datetime


class InstructorIn(BaseModel):
    instructor_id: int | None


class InstructorOut(BaseModel):
    user_id: int
    instructor_id: int | None


class LinkIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirm: bool

    @field_validator("confirm")
    @classmethod
    def _confirmed(cls, v: bool) -> bool:
        if v is not True:
            raise messages.coded(
                "sso_link_unconfirmed",
                "Bağlamayı onaylamanız gerekir: Microsoft hesabı bu SmartSched hesabına giriş yapacak.",
                "confirm must be true: the Microsoft account will sign in to this SmartSched account",
            )
        return v


class AuthorizeOut(BaseModel):
    authorize_url: str


class ExchangeIn(BaseModel):
    ticket: str = Field(min_length=16, max_length=128)


class SsoTokenOut(TokenOut):
    """``TokenOut`` plus where to go: ``welcome`` is ``self`` / ``invited`` / ``bound`` on the sign-in that created
    or bound the account (the panel shows ``/welcome``), else ``None``."""

    next: str | None = None
    welcome: str | None = None
    inviter_name: str | None = None


class SsoMeOut(BaseModel):
    provider: str = svc.PROVIDER
    linked: bool
    email_at_login: str | None = None
    display_name: str | None = None
    linked_at: datetime | None = None
    last_login_at: datetime | None = None
    #: a pending invite / bind mark for this account
    pending_bind: bool = False
    has_password: bool


class ProviderOut(BaseModel):
    name: str
    label: str
    enabled: bool
    start_url: str


class MicrosoftAuthOut(BaseModel):
    enabled: bool
    label: str
    start_url: str
    domain_hint: str | None
    self_signup: bool


class PublicAuthOut(BaseModel):
    """The ``auth`` block of the login page (sign-in.md §14)."""

    microsoft: MicrosoftAuthOut
    local_enabled: bool
    ldap_enabled: bool
    self_signup_role_name: str | None
    #: the role's code (``TEACHER``) and its display name in both languages (built-in names localised, T-R1-30)
    self_signup_role_code: str | None = None
    self_signup_role_label: dict[str, str] | None = None


class ProvidersOut(BaseModel):
    auth: PublicAuthOut
    providers: list[ProviderOut]
    #: ``error`` code of a redirect -> {"tr": ..., "en": ...}
    messages: dict[str, dict[str, str]]
