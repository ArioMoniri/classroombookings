"""``GET /dashboard`` payload: KPI tiles, request counts, last runs, utilisation matrices."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.catalog import TermOut
from app.schemas.runs import RunOut


class BuildingUtilisation(BaseModel):
    building: str
    utilisation: float  # 0..1 over the bookable rooms of the building, Mon-Fri x 18 periods
    rooms: int


class BuildingDayCell(BaseModel):
    building: str
    day: int
    utilisation: float


class BuildingPeriodCell(BaseModel):
    building: str
    period: int
    utilisation: float  # Mon-Fri average


class PeakCell(BaseModel):
    day: int
    period: int
    occupancy: float  # share of bookable rooms occupied


class DashboardOut(BaseModel):
    term: TermOut
    current_week: int
    utilisation_week: int
    rooms_total: int
    rooms_bookable: int
    sections_total: int
    requests_total: int
    meetings_total: int
    exams_total: int
    requests_needs_review: int
    requests_pending: int  # not yet LOCKED (NEW / PARSED / NEEDS_REVIEW)
    requests_locked: int
    meetings_by_status: dict[str, int]
    exams_by_status: dict[str, int]
    active_run_id: int | None
    utilisation_run_id: int | None
    utilisation: float
    utilisation_by_building: list[BuildingUtilisation]
    utilisation_building_day: list[BuildingDayCell]
    utilisation_building_period: list[BuildingPeriodCell]
    peak_hours: list[PeakCell]
    blocks_week: int
    conflicts: int
    last_runs: list[RunOut]
