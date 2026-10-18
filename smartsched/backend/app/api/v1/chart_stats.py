"""Read-only chart aggregates (CH-07, CH-10, CH-11; docs/design/v3/charts.md "CH-07 … CH-11 notes"; logic in
``app/services/chart_stats.py``). GET only: no audit rows, no writes.

* ``GET /bookings/stats/weekly?term_id=`` -- ``system.export_bookings``: bookings and booking request outcomes per
  term week, exam weeks and the partial (current / cut-off) week flagged.
* ``GET /audit/stats/daily?days=30`` -- ``audit.view``: audit events per Europe/Istanbul day, zero-filled, under the
  audit list's own scope rule.
* ``GET /me/load?term_id=`` -- signed in: the caller's own linked instructor record only (no parameter selects
  anyone else), class periods per weekday on the term's published course run.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import DB, CurrentAccess, require_permission
from app.services import bookings as bsvc
from app.services import chart_stats as svc

router = APIRouter(tags=["stats"])


def _err(exc: svc.StatsError) -> HTTPException:
    return HTTPException(exc.status, exc.detail())


@router.get("/bookings/stats/weekly", dependencies=[Depends(require_permission("system.export_bookings"))])
async def bookings_weekly(db: DB, term_id: int) -> dict[str, Any]:
    try:
        return await svc.weekly_bookings(db, term_id, await bsvc.today(db))
    except svc.StatsError as exc:
        raise _err(exc) from exc


@router.get("/audit/stats/daily", dependencies=[Depends(require_permission("audit.view"))])
async def audit_daily(db: DB, access: CurrentAccess, days: int = Query(default=30, ge=1, le=svc.DAYS_MAX)) -> Any:
    from app.api.v1.audit import _own_scope  # the list's scope: one rule for the list and its chart

    scope = None if access.can("audit.view") else await _own_scope(db, access)
    return await svc.daily_audit(db, days, scope)


@router.get("/me/load")
async def my_load(db: DB, access: CurrentAccess, term_id: int | None = None) -> dict[str, Any]:
    try:
        return await svc.my_load(db, access.user_id, term_id, await bsvc.today(db))
    except svc.StatsError as exc:
        raise _err(exc) from exc
