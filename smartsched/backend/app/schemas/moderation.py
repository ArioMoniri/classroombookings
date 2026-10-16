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


class SubjectPriorityIn(PriorityIn):
    """A person's or a programme's priority for one term (P19-P-04); ``null`` / ``normal`` clears it."""

    term_id: int


class ResolveIn(BaseModel):
    base_run_id: int
    changed_request_ids: list[int] = Field(default_factory=list, max_length=500)
    mode: Literal["repair", "full"] = "repair"
    #: conflict hops freed around the changed requests (``app.solver.repair.neighbours``)
    radius: int = Field(default=1, ge=0, le=3)
    time_limit_s: float | None = Field(default=None, gt=0)
    #: solve inside the request and answer with the diff (200) instead of 202 + polling
    wait: bool = False
    #: the preview's baseline (default: the published run that started the chain, even from a draft child)
    compare_to: int | None = None


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


class TeacherPreferenceIn(BaseModel):
    """P19-T2 "Tercih ekle" (``app/services/teacher_preferences.py``): an academician's own wish for their classes.

    ``kind``: ``room_preference`` | ``building_preference`` | ``day_window`` (or ``room`` / ``building`` / ``time``).
    The classes: ``request_ids`` (meeting requests) or ``section_id`` (all its meetings), all taught by the caller.
    A room by id (``room_ids``) or as typed (``rooms``: ``"C 404"``, ``"c\u00a0404"``); a building as typed
    (``buildings``: ``"C"``, ``"C Blok"``); a time window by period (``earliest`` / ``latest``, 1..18) or by clock
    time as the lists write it (``not_before`` / ``not_after``: ``"10.10"``, ``"15:50"``), optional ``days``.
    ``hardness`` / ``weight`` exist only to be refused in Turkish and English: the wish is always soft and ranked
    below the department's request (Q12)."""

    kind: str = Field(max_length=32)
    request_ids: list[int] = Field(default_factory=list, max_length=50)
    section_id: int | None = None
    room_ids: list[int] | None = Field(default=None, max_length=10)
    rooms: list[str] | None = Field(default=None, max_length=10)
    buildings: list[str] | None = Field(default=None, max_length=10)
    earliest: int | None = None
    latest: int | None = None
    not_before: str | None = Field(default=None, max_length=16)
    not_after: str | None = Field(default=None, max_length=16)
    days: list[int | str] | None = Field(default=None, max_length=7)
    note: str | None = Field(default=None, max_length=2000)
    hardness: str | None = Field(default=None, max_length=16)
    weight: int | None = None


class PreferenceDecisionIn(BaseModel):
    decision: Literal["accept", "reject"]
    #: required for a rejection: the academician reads it (notify_dispatch ``preference.rejected``)
    reason: str | None = Field(default=None, max_length=1000)
    reason_code: str | None = Field(default=None, max_length=32)
    #: decide every row of the same "Tercih ekle" submission (one per distinct department ask); default true
    with_submission: bool = True


__all__ = [
    "MatchingActionIn",
    "PreferenceDecisionIn",
    "PriorityIn",
    "ResolveIn",
    "SubjectPriorityIn",
    "TeacherPreferenceIn",
]
