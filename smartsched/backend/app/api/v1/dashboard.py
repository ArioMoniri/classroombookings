from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DB, Viewer
from app.api.v1.runs import runs_out
from app.schemas.catalog import TermOut
from app.schemas.dashboard import DashboardOut
from app.services.dashboard import build_dashboard, pick_term

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    week: int | None = Query(None, ge=1, le=60, description="utilisation week (default: current or run's first)"),
) -> DashboardOut:
    """KPI tiles for one term (default: the active term, else the newest)."""
    term = await pick_term(db, term_id)
    if term is None:
        raise HTTPException(404, "term not found" if term_id else "no terms yet: import a workbook first")
    data = await build_dashboard(db, term, week=week)
    data["term"] = TermOut.model_validate(term)
    data["last_runs"] = await runs_out(db, data["last_runs"])
    return DashboardOut.model_validate(data)
