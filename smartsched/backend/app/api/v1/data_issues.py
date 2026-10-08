"""``GET /runs/{id}/data-issues``: the planner-facing report of the problems in their own data (grouped
warnings and unplaced reasons with the classes involved); ``?format=xlsx`` gives one sheet per group
with Turkish / English columns.  See ``app/services/data_issues.py``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import DB, Viewer
from app.models import ScheduleRun
from app.schemas.runs import DataIssuesOut
from app.services.data_issues import build_data_issues, to_xlsx

router = APIRouter(prefix="/runs", tags=["runs"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/{run_id}/data-issues", response_model=DataIssuesOut)
async def run_data_issues(
    run_id: int,
    db: DB,
    _: Viewer,
    format: str = Query("json", pattern="^(json|xlsx)$"),
) -> Any:
    run = await db.get(ScheduleRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    report = await build_data_issues(db, run)
    if format == "xlsx":
        return Response(
            to_xlsx(report),
            media_type=XLSX,
            headers={"Content-Disposition": f'attachment; filename="smartsched-run{run.id}-data-issues.xlsx"'},
        )
    return report
