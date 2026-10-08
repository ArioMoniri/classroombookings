"""T1 "find me a room" request/response bodies (``POST /rooms/find``)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.importers import normalize as n


class FeatureFilter(BaseModel):
    #: feature id, or its name (Turkish-case-insensitive: "projeksiyon", "PC SAYISI")
    field: int | str
    #: NUMBER: gte (default) | lte | eq; SELECT: in; MULTISELECT: has; TEXT: contains; BOOLEAN: eq
    op: Literal["eq", "gte", "lte", "in", "has", "contains"] | None = None
    #: BOOLEAN: true (default) / "evet"; NUMBER: 40 or "4,5"; SELECT/MULTISELECT: option id(s) or text(s)
    value: Any = None


class Flex(BaseModel):
    #: alternatives at ±1..±periods (0-2)
    periods: int = Field(default=2, ge=0, le=2)
    #: alternatives on the other weekdays of the same week (single-date searches)
    other_days: bool = False


class FindIn(BaseModel):
    term_id: int | None = None
    #: one or more dates ...
    date: dt.date | None = None
    dates: list[dt.date] = Field(default_factory=list, max_length=120)
    #: ... or a range (optionally only some ISO weekdays 1..7) ...
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    weekdays: list[int] = Field(default_factory=list)
    #: ... or a weekday in term weeks (all lecture weeks when ``weeks`` is empty)
    weekday: int | None = Field(default=None, ge=1, le=7)
    weeks: list[int] = Field(default_factory=list, max_length=60)
    #: "10:10", "10.10" or a period number 1..18
    start: str | int
    end: str | int | None = None
    duration_periods: int | None = Field(default=None, ge=1, le=18)
    duration_min: int | None = Field(default=None, ge=10, le=900)
    #: slide a ``duration`` block from ``start`` up to this end ("any 2 periods between 10:10 and 15:50")
    window_end: str | int | None = None
    #: 0 = any size
    headcount: int = Field(default=0, ge=0, le=5000)
    purpose: Literal["teaching", "exam"] = "teaching"
    features: list[FeatureFilter] = Field(default_factory=list, max_length=20)
    #: solver tags or words for them: "PC", "bilgisayar", "TIP", "amfi"
    tags: list[str] = Field(default_factory=list, max_length=10)
    #: "A", "a blok", "C BLOĞU"
    buildings: list[str] = Field(default_factory=list, max_length=10)
    preferred_building: str | None = None
    room_group_id: int | None = None
    #: free text over room code, name, location, notes and features (Turkish-insensitive)
    text: str | None = Field(default=None, max_length=200)
    include_busy: bool = True
    include_requestable: bool = True
    flex: Flex = Field(default_factory=Flex)
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("start", "end", "window_end", mode="before")
    @classmethod
    def _clock(cls, v: Any) -> Any:
        if isinstance(v, str):
            return n.clean_text(v) or None
        return v

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, v: list[int]) -> list[int]:
        if any(not 1 <= d <= 7 for d in v):
            raise ValueError("weekdays are ISO numbers 1 (Monday) .. 7 (Sunday)")
        return v


class Reason(BaseModel):
    tr: str
    en: str


class PerDate(BaseModel):
    date: dt.date
    status: str
    reason: str | None = None


class Fit(BaseModel):
    waste_pct: int | None
    score: float


class FindResult(BaseModel):
    room_id: int
    code: str
    name: str
    building: str | None
    capacity: int
    exam_capacity: int
    tags: list[str]
    features: list[str]
    #: free | requestable | partial | busy | too_small | feature_missing | capacity_unknown | closed
    status: str
    #: book | request | none
    action: str
    start_period: int
    end_period: int
    reason: Reason
    reasons: list[Reason]
    busy_with: str | None
    fit: Fit
    free_dates: int
    open_dates: int
    per_date: list[PerDate] | None = None


class Alternative(BaseModel):
    kind: Literal["time", "day", "near_miss"]
    room_id: int
    code: str
    name: str
    dates: list[dt.date]
    start_period: int
    end_period: int
    reason: Reason


class FindOut(BaseModel):
    query_echo: dict[str, Any]
    term_id: int
    slots: list[dict[str, Any]]
    duration_periods: int
    time: dict[str, str]
    closed_dates: list[dict[str, Any]]
    preferred_building: str | None
    summary: dict[str, Any]
    results: list[FindResult]
    alternatives: list[Alternative]
    timing_ms: float
