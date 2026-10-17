"""I/O of the provider administration (``/api/v1/auth/sso/admin/providers*``). Inputs are partial updates; the
secret is write-only (no output field carries it). Values are validated and normalised in
app/services/identity/providers.py (bilingual 422s)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProviderCreateIn(BaseModel):
    kind: Literal["entra", "google_workspace", "oidc", "saml"]
    preset: str | None = Field(default=None, max_length=24)
    display_name: str | None = Field(default=None, max_length=80)
    #: the URL slug; default from the kind / preset (``keycloak``, ``google``, ``yetkim``)
    name: str | None = Field(default=None, max_length=40)


class ProviderIn(BaseModel):
    #: the ``version`` of the answer the editor started from; a different current version answers 409 ``conflict``
    version: str | None = Field(default=None, max_length=40)
    name: str | None = Field(default=None, max_length=40)
    display_name: str | None = Field(default=None, max_length=80)
    enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    allowed_domains: list[str] | None = Field(default=None, max_length=50)
    invite_only: bool | None = None
    #: just-in-time provisioning of a first sign-in (as the default role); off or ``invite_only`` = invites only
    self_signup: bool | None = None
    default_role_id: int | None = None
    role_mapping_enabled: bool | None = None
    allow_admin_mapping: bool | None = None
    oidc_only_non_admins: bool | None = None
    invite_days: int | None = Field(default=None, ge=1, le=365)
    domain_hint: str | None = Field(default=None, max_length=255)
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = Field(default=None, max_length=1024)
    secret_expires: str | None = Field(default=None, max_length=10)
    tenant_id: str | None = Field(default=None, max_length=80)
    issuer: str | None = Field(default=None, max_length=255)
    hosted_domains: list[str] | None = Field(default=None, max_length=20)
    groups_claim: str | None = Field(default=None, max_length=120)
    roles_claim: str | None = Field(default=None, max_length=120)
    trust_email: bool | None = None
    scopes: list[str] | None = Field(default=None, max_length=10)
    metadata_url: str | None = Field(default=None, max_length=500)
    metadata_xml: str | None = Field(default=None, max_length=524288)
    idp_entity_id: str | None = Field(default=None, max_length=255)
    email_attribute: str | None = Field(default=None, max_length=255)
    name_attribute: str | None = Field(default=None, max_length=255)
    groups_attribute: str | None = Field(default=None, max_length=255)
    subject_attribute: str | None = Field(default=None, max_length=255)


class OrderIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=50)


class ProviderMappingIn(BaseModel):
    claim: Literal["role", "group"]
    value: str = Field(min_length=1, max_length=160)
    role_id: int


class BulkInviteIn(BaseModel):
    csv: str = Field(min_length=1, max_length=200_000)
    provider: str | None = Field(default=None, max_length=40)
    role_id: int | None = None
    days: int | None = Field(default=None, ge=1, le=365)
    send_email: bool = False
    locale: Literal["tr", "en"] | None = None


class ResendIn(BaseModel):
    locale: Literal["tr", "en"] | None = None


class LocalPasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=256)
