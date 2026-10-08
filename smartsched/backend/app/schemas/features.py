"""P10 typed room features: request/response bodies (``/room-admin/features``, ``/rooms/facets``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FeatureType = Literal["BOOLEAN", "CHECKBOX", "NUMBER", "SELECT", "MULTISELECT", "TEXT"]
Category = Literal["av", "seating", "accessibility", "lab", "other"]


class FeatureIn(BaseModel):
    name: str = Field(max_length=64)
    type: FeatureType
    options: list[str] = Field(default_factory=list, max_length=200)
    filterable: bool = True
    public: bool = True
    icon: str | None = Field(default=None, max_length=64)
    unit: str | None = Field(default=None, max_length=16)
    solver_tag: str | None = Field(default=None, max_length=16)
    category: Category | None = None


class FeatureOption(BaseModel):
    id: int
    value: str


class FeatureOut(BaseModel):
    id: int
    name: str
    #: stored type (CRBS CHECKBOX stays CHECKBOX)
    type: str
    #: normalised type: BOOLEAN | NUMBER | SELECT | MULTISELECT | TEXT
    kind: str
    options: list[FeatureOption]
    filterable: bool
    public: bool
    icon: str | None
    unit: str | None
    solver_tag: str | None
    category: str | None
    pos: int
    #: facets only: value -> number of rooms (option id for SELECT/MULTISELECT, "true"/"false" for BOOLEAN)
    counts: dict[str, int] | None = None


class FeatureDeleteOut(BaseModel):
    deleted: int
    impact: dict[str, Any] | None = None


class RoomFeaturesOut(BaseModel):
    room_id: int
    code: str
    tags: list[str]
    #: field id (as text) -> typed value
    values: dict[str, Any]
    #: field name -> human value (option texts)
    display: dict[str, Any]


class BulkReport(BaseModel):
    dry_run: bool
    rooms: int
    cells: int
    errors: int
    unknown_columns: list[str]
    applied: int
    report: list[dict[str, Any]]
