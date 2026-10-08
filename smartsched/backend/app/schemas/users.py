"""Admin user management (``/users``). Password hashes are never serialised."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

ROLE_PATTERN = "^(ADMIN|PLANNER|VIEWER)$"


def _email(v: str) -> str:
    v = v.strip().lower()
    if "@" not in v or len(v) < 3 or " " in v:
        raise ValueError("invalid email")
    return v


class UserCreate(BaseModel):
    email: str
    full_name: str | None = None
    role: str = Field(default="VIEWER", pattern=ROLE_PATTERN)
    password: str = Field(min_length=8, max_length=256)
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str) -> str:
        return _email(v)


class UserUpdate(BaseModel):
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
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: dt.datetime | None = None
    has_password: bool = False
