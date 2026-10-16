"""P2 conflict resolver after publishing (docs/product/booking-enhancements.md §4.4; service:
:mod:`app.services.booking_conflicts`). Every route needs ``planning.edit``; ``override`` needs ``planning.admin``.

* ``GET  /bookings/conflicts/summary`` -- open conflicts per published run (the banner);
* ``GET  /bookings/conflicts/{run_id}/plan`` -- conflicts grouped by series with ranked options;
* ``POST /bookings/conflicts/{run_id}/apply`` -- ``{items: [{conflict_id, action, option_id?, scope, reason?}],
  dry_run}``: all or nothing, audited, one digest per owner;
* ``POST /bookings/conflicts/{run_id}/auto`` -- the top options as an ``apply`` payload (dry run only);
* ``POST /bookings/conflicts/{run_id}/detect`` -- scan the published run again (after manual timetable edits).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentAccess, Planner
from app.importers import normalize as n
from app.services import booking_conflicts as svc

router = APIRouter(prefix="/bookings/conflicts", tags=["bookings"])


class ApplyItem(BaseModel):
    conflict_id: int
    action: str
    option_id: str | None = None
    scope: str = "one"
    reason: str | None = Field(default=None, max_length=500)


class ApplyIn(BaseModel):
    items: list[ApplyItem] = Field(min_length=1, max_length=2000)
    dry_run: bool = False


def _err(exc: svc.ConflictError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


@router.get("/summary")
async def conflicts_summary(db: DB, _: Planner) -> dict[str, Any]:
    return await svc.summary(db)


@router.get("/{run_id}/plan")
async def conflicts_plan(run_id: int, db: DB, _: Planner, access: CurrentAccess) -> dict[str, Any]:
    try:
        return await svc.plan(db, access, run_id)
    except svc.ConflictError as exc:
        raise _err(exc) from exc


@router.post("/{run_id}/apply")
async def conflicts_apply(run_id: int, body: ApplyIn, db: DB, _: Planner, access: CurrentAccess) -> dict[str, Any]:
    items = [{**i.model_dump(), "reason": n.clean_text(i.reason) if i.reason else None} for i in body.items]
    try:
        return await svc.apply(db, access, run_id, items, dry_run=body.dry_run)
    except svc.ConflictError as exc:
        raise _err(exc) from exc


@router.post("/{run_id}/auto")
async def conflicts_auto(run_id: int, db: DB, _: Planner, access: CurrentAccess) -> dict[str, Any]:
    try:
        return await svc.auto(db, access, run_id)
    except svc.ConflictError as exc:
        raise _err(exc) from exc


@router.post("/{run_id}/detect")
async def conflicts_detect(run_id: int, db: DB, user: Planner) -> dict[str, Any]:
    try:
        run = await svc.active_run(db, run_id)
    except svc.ConflictError as exc:
        raise _err(exc) from exc
    out = await svc.detect(db, run, user)
    await db.commit()
    return {"run_id": run_id, **out}
