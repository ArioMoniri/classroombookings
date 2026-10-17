"""P1 approval workflows: rules, approver designation, decisions, in-app notifications."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.importers import normalize as n


class StepApprovers(BaseModel):
    #: designated = every designated approver whose "approves for" covers the room; users = the listed ones
    type: Literal["designated", "users"] = "designated"
    ids: list[int] = Field(default_factory=list, max_length=50)


class Step(BaseModel):
    approvers: StepApprovers = Field(default_factory=StepApprovers)
    min_approvals: int = Field(default=1, ge=1, le=10)


class RuleIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    entity_type: Literal["room", "room_group", "tag"]
    entity_id: int | None = None
    #: room type (solver tag), e.g. TIP, PC, AMPHI
    tag: str | None = Field(default=None, max_length=16)
    term_id: int | None = None
    steps: list[Step] = Field(default_factory=lambda: [Step()], min_length=1, max_length=5)
    hold_minutes: int = Field(default=0, ge=0, le=10080)
    lead_time_workdays: int = Field(default=0, ge=0, le=60)
    expires_before_start_minutes: int = Field(default=0, ge=0, le=10080)
    allow_self_approve: bool = False
    active: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return n.clean_text(v) if v is not None else None


class RuleOut(BaseModel):
    id: int
    rule_id: int | None
    name: str | None
    entity_type: str
    entity_id: int | None
    tag: str | None
    term_id: int | None
    steps: list[dict[str, Any]]
    hold_minutes: int
    lead_time_workdays: int
    expires_before_start_minutes: int
    allow_self_approve: bool
    active: bool
    created_by: int | None
    created_at: str | None


class ScopeIn(BaseModel):
    #: all = every room; room / room_group = ``id``; tag = room type such as TIP or PC
    type: Literal["all", "room", "room_group", "tag"]
    id: int | None = None
    tag: str | None = Field(default=None, max_length=16)


class ApproverIn(BaseModel):
    scopes: list[ScopeIn] = Field(default_factory=list, max_length=100)


class ApproverOut(BaseModel):
    user_id: int
    name: str | None
    email: str | None
    can_decide: bool
    scopes: list[dict[str, Any]]


class AlternativeIn(BaseModel):
    room_id: int | None = None
    date: dt.date | None = None
    period_id: int | None = None
    start_period: int | None = Field(default=None, ge=1, le=18)
    end_period: int | None = Field(default=None, ge=1, le=18)


class DecideIn(BaseModel):
    decision: Literal["approve", "reject"]
    #: approve: a note for the requester; reject: the reason's free text when ``reason`` is not given
    note: str | None = Field(default=None, max_length=1000)
    #: reject: why (free text; required when ``reason_code`` is missing or "other"); wins over ``note``
    reason: str | None = Field(default=None, max_length=1000)
    #: reject: room_unavailable | capacity | policy | other (validated by the service, 422 in Turkish and English)
    reason_code: str | None = Field(default=None, max_length=32)
    #: approve: "approve in another room / time"; reject: the suggestion shown to the requester
    alternative: AlternativeIn | None = None
    #: recurring requests: approve only these dates (the others are declined)
    instances: list[dt.date] | None = Field(default=None, max_length=200)


class RuleCheckOut(BaseModel):
    room_id: int
    #: book | request | none for the caller
    action: str
    rule: dict[str, Any] | None
    approvers: list[dict[str, Any]]
    summary_tr: str
    summary_en: str


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    link: str | None
    booking_id: int | None
    request_id: int | None
    #: structured payload: room, dates, periods [{name, start, end, start_period, end_period}], decision,
    #: reason, reason_code, decided_by {id, name}, requester {id, name}, request_ids, group_id, ...
    data: dict[str, Any] | None = None
    read_at: str | None
    created_at: str | None


class ReadIn(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=500)
    all: bool = False


class ChannelPrefOut(BaseModel):
    name: str
    label_tr: str
    label_en: str
    #: the user's master switch for the channel
    enabled: bool
    #: whether the channel can reach the user (e-mail: the account has an address)
    available: bool
    default_enabled: bool


class EventPrefOut(BaseModel):
    event: str
    label_tr: str
    label_en: str
    #: channel name -> on (the master switch and the event's own switch together)
    channels: dict[str, bool]


class NotificationPrefsOut(BaseModel):
    channels: list[ChannelPrefOut]
    events: list[EventPrefOut]


class NotificationPrefsIn(BaseModel):
    """Partial update: only the named switches change. ``channels``: master switch per channel (off = off for every
    event); ``events``: event -> channel -> on."""

    channels: dict[str, bool] = Field(default_factory=dict, max_length=20)
    events: dict[str, dict[str, bool]] = Field(default_factory=dict, max_length=50)
