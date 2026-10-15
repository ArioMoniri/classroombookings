"""Request bodies of the Phase 19 moderation API (``app/api/v1/moderation.py``); responses are the documented
dicts of ``app/services/moderation.py``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PriorityIn(BaseModel):
    #: an integer within -100..100 (higher wins) or a tier: high / normal / low (yüksek / düşük); ``null`` clears
    #: a request override (the section's priority applies again) or sets a section back to 0
    priority: int | str | None = None
    note: str | None = Field(default=None, max_length=500)


class ResolveIn(BaseModel):
    base_run_id: int
    changed_request_ids: list[int] = Field(default_factory=list, max_length=500)
    mode: Literal["repair", "full"] = "repair"
    #: conflict hops freed around the changed requests (``app.solver.repair.neighbours``)
    radius: int = Field(default=1, ge=0, le=3)
    time_limit_s: float | None = Field(default=None, gt=0)
    #: solve inside the request and answer with the diff (200) instead of 202 + polling
    wait: bool = False


class MatchingActionIn(BaseModel):
    #: the draft child run the edit is written to (never the published run)
    run_id: int
    action: Literal["pin", "prefer", "unlock"]
    #: pin / prefer: the rooms (default: the class's rooms in the base run)
    room_ids: list[int] | None = Field(default=None, max_length=8)
    #: pin: the cell (default: the class's cell in the base run)
    day: int | None = Field(default=None, ge=1, le=7)
    start_period: int | None = Field(default=None, ge=1, le=18)
    #: why (a planning administrator's capacity override needs one, Q8)
    reason: str | None = Field(default=None, max_length=500)


__all__ = ["MatchingActionIn", "PriorityIn", "ResolveIn"]
