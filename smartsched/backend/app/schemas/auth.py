from __future__ import annotations

from pydantic import BaseModel, field_validator

from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or len(v) < 3:
            raise ValueError("invalid email")
        return v


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
