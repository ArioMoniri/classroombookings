"""The university's period grid (RF-09): the clock times of P1-P18, read by everyone signed in, edited by schedule
admins (``setup.schedules``, the /admin/schedules permission). See ``app.services.period_grid``.

GET    /period-grid      the grid in use (``source``: ``default`` | ``setting``) and the default times
PUT    /period-grid      ``{"periods": [{"start": "08:30", "end": "09:10"}, ...]}`` (18 items; ``08.30`` is read)
DELETE /period-grid      back to the default grid
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentUser, require_permission
from app.models import User
from app.schemas.messages import problem
from app.services import period_grid as svc

router = APIRouter(prefix="/period-grid", tags=["period-grid"])
GridAdmin = Annotated[User, Depends(require_permission("setup.schedules"))]


class PeriodTimes(BaseModel):
    start: str = Field(max_length=16)
    end: str = Field(max_length=16)


class PeriodGridIn(BaseModel):
    periods: list[PeriodTimes] = Field(max_length=64)


@router.get("")
async def get_grid(db: DB, _: CurrentUser) -> dict[str, Any]:
    return await svc.describe(db)


@router.put("")
async def put_grid(body: PeriodGridIn, db: DB, user: GridAdmin) -> dict[str, Any]:
    try:
        times = svc.parse([p.model_dump() for p in body.periods])
    except svc.GridError as exc:
        raise problem(exc.status, exc.code, exc.tr, exc.en) from exc
    return await svc.save(db, times, user)


@router.delete("")
async def reset_grid(db: DB, user: GridAdmin) -> dict[str, Any]:
    return await svc.reset(db, user)
