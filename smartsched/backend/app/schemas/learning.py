"""Request bodies of ``/learning/*`` (P19-L3 / P19-L4). Responses are the service dicts (documented in
``app/api/v1/learning.py``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AcceptIn(BaseModel):
    #: 1..5 (Q7: learned 5 < explicit 10); default 5
    weight: int | None = Field(default=None, ge=1, le=10)
    #: optional other kind from the learned allowlist (``same_room_across_weeks`` for a room / building
    #: suggestion); anything else, structural kinds included, is refused with 422
    kind: str | None = Field(default=None, max_length=64)
    #: term (default): this term's classes; persistent (planning.admin): also remembered as the person's preference,
    #: so the same suggestion in a later term is marked ``persistent_accept`` (still accepted by a person)
    scope: Literal["term", "persistent"] = "term"


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class SnoozeIn(BaseModel):
    until: Literal["next_solve", "P7D", "next_term"] = "next_solve"


class RefreshIn(BaseModel):
    term_id: int | None = None


class ResetIn(BaseModel):
    scope: Literal["person", "term", "all"]
    #: instructor id (person), term id (term), omitted for all
    value: int | str | None = None
    reason: str = Field(min_length=3, max_length=500)


class EraseIn(BaseModel):
    instructor_id: int
    reason: str = Field(min_length=3, max_length=500)


__all__ = ["AcceptIn", "EraseIn", "RefreshIn", "RejectIn", "ResetIn", "SnoozeIn"]
