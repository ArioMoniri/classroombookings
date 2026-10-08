"""User management (``/users``). Password hashes are never serialised.

CRBS parity: users have an optional ``username`` (login name, Turkish-insensitive), first/last name, display
name (= ``full_name``), extension, role (``role_id`` or a seeded role ``code``), department and the
``force_password_reset`` flag."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.identity import clean_email, fold_username
from app.schemas.common import ORMModel

ROLE_PATTERN = "^(ADMIN|PLANNER|VIEWER|TEACHER)$"


class ApproverScopeIn(BaseModel):
    type: Literal["all", "room", "room_group", "tag"]
    id: int | None = None
    tag: str | None = Field(default=None, max_length=16)


def _email(v: str) -> str:
    return clean_email(v)


class _UserFields(BaseModel):
    username: str | None = Field(default=None, max_length=255)
    firstname: str | None = Field(default=None, max_length=255)
    lastname: str | None = Field(default=None, max_length=255)
    displayname: str | None = Field(default=None, max_length=255)  # alias of full_name
    ext: str | None = Field(default=None, max_length=32)
    role_id: int | None = None
    department_id: int | None = None
    force_password_reset: bool | None = None
    #: P1: designate an administrator as approver ("approves for": all / room / room_group / tag scopes);
    #: ``[]`` removes the designation, omitted leaves it unchanged
    approves_for: list[ApproverScopeIn] | None = None

    @field_validator("username")
    @classmethod
    def _norm_username(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return fold_username(v)


class UserCreate(_UserFields):
    email: str | None = None
    full_name: str | None = None
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    password: str | None = Field(default=None, min_length=8, max_length=256)
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str | None) -> str | None:
        return _email(v) if v is not None and v.strip() else None

    @model_validator(mode="after")
    def _identity(self) -> UserCreate:
        if not self.email and not self.username:
            raise ValueError("email or username is required")
        if self.role is None and self.role_id is None:
            self.role = "VIEWER"
        return self


class UserUpdate(_UserFields):
    email: str | None = None
    full_name: str | None = None
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str | None) -> str | None:
        return _email(v) if v is not None else None


class PasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class UserAdminOut(ORMModel):
    id: int
    email: str | None = None
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: dt.datetime | None = None
    has_password: bool = False
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    displayname: str | None = None
    ext: str | None = None
    role_id: int | None = None
    role_name: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    last_login_at: dt.datetime | None = None
    force_password_reset: bool = False
    auth_source: str = "local"
    approves_for: list[dict[str, Any]] = Field(default_factory=list)
