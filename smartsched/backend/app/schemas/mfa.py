"""Request bodies of the two-step sign-in routes (AU-B; app/api/v1/mfa.py)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PasswordIn(BaseModel):
    password: str = Field(default="", max_length=256)


class CodeIn(BaseModel):
    code: str = Field(max_length=64)


class DisableIn(BaseModel):
    password: str = Field(default="", max_length=256)
    code: str = Field(default="", max_length=64)


class VerifyIn(BaseModel):
    challenge_token: str = Field(max_length=2048)
    method: Literal["totp", "recovery"] = "totp"
    code: str = Field(max_length=64)
    trust_device: bool = False


class ChallengeIn(BaseModel):
    challenge_token: str = Field(max_length=2048)


class SetupConfirmIn(ChallengeIn):
    code: str = Field(max_length=64)


class CredentialIn(ChallengeIn):
    credential: dict[str, Any]
    trust_device: bool = False


class RegisterIn(ChallengeIn):
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=64)


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PolicyIn(BaseModel):
    mfa_policy: Literal["off", "optional", "required_for_roles"] | None = None
    mfa_roles: list[Literal["ADMIN", "PLANNER", "TEACHER", "VIEWER", "CUSTOM"]] | None = Field(
        default=None, max_length=5
    )
    mfa_grace_days: int | None = Field(default=None, ge=0, le=90)
    passkeys_enabled: bool | None = None
    passkey_first_factor: bool | None = None
    trusted_device_days: Literal[0, 7, 30] | None = None


class AdminResetIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    identity_check: Literal["in_person", "video_call", "phone_callback", "other"]
    keep_passkeys: bool = False


class ResetLinkIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
