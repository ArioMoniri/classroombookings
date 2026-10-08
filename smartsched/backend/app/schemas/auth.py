from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    """``email`` (historic field; a username typed into it works too) or ``username`` + password."""

    email: str | None = None
    username: str | None = None
    password: str

    @model_validator(mode="after")
    def _identifier(self) -> LoginIn:
        if not (self.email or "").strip() and not (self.username or "").strip():
            raise ValueError("email or username is required")
        return self

    @property
    def identifier(self) -> str:
        return (self.username or self.email or "").strip()


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    password_change_required: bool = False


class UserOut(ORMModel):
    id: int
    email: str | None = None
    full_name: str | None = None
    role: str
    is_active: bool
    username: str | None = None
    role_id: int | None = None
    department_id: int | None = None
    force_password_reset: bool = False
    auth_source: str = "local"
    permissions: list[str] = Field(default_factory=list)


class ChangePasswordIn(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=256)


class ResetRequestIn(BaseModel):
    email: str


class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=8, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class ProfileIn(BaseModel):
    email: str | None = None
    firstname: str | None = Field(default=None, max_length=255)
    lastname: str | None = Field(default=None, max_length=255)
    displayname: str | None = Field(default=None, max_length=255)
    ext: str | None = Field(default=None, max_length=32)
    language: str | None = Field(default=None, max_length=32)


class ProfileOut(BaseModel):
    id: int
    email: str | None = None
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    displayname: str | None = None
    ext: str | None = None
    language: str | None = None
    department_id: int | None = None
    role: str
    role_name: str | None = None
