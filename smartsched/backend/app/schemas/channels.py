"""Request bodies of the notification-channel API (``app/api/v1/channels.py``). Responses are plain dicts built by
``app.services.channels`` (secrets appear only as ``{name: configured}`` flags)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SignoffIn(BaseModel):
    signed: bool
    legal_basis: str | None = Field(default=None, max_length=500)
    officer: str | None = Field(default=None, max_length=200)


class ChannelConfigIn(BaseModel):
    """Every field is optional: what is not sent keeps its value. ``secrets``: name -> value ("" or null clears);
    ``options``: name -> value (null clears)."""

    enabled: bool | None = None
    content_mode: str | None = Field(default=None, max_length=32)
    options: dict[str, Any] | None = None
    secrets: dict[str, str | None] | None = None
    kvkk_signoff: SignoffIn | None = None
    risk_ack: bool | None = None


class VapidIn(BaseModel):
    rotate: bool = False


class DepartmentTargetIn(BaseModel):
    url: str = Field(max_length=2048)


class PhoneLinkIn(BaseModel):
    phone: str = Field(max_length=64)
    consent: bool = False


class CodeIn(BaseModel):
    code: str = Field(max_length=32)


class PushKeysIn(BaseModel):
    p256dh: str = Field(max_length=256)
    auth: str = Field(max_length=64)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=2048)
    keys: PushKeysIn
    expirationTime: int | None = None  # noqa: N815 - the browser's PushSubscription.toJSON() name


class WebPushLinkIn(BaseModel):
    subscription: PushSubscriptionIn
    label: str | None = Field(default=None, max_length=64)
