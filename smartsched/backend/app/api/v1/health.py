from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.deps import DB
from app.core.config import get_settings
from app.models import Assignment, MeetingRequest, Room, ScheduleRun, Term
from app.services.solver_bridge import solver_name

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health(db: DB) -> dict[str, Any]:
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "solver": solver_name(),
        "app": get_settings().app_name,
        "version": "0.1.0",
    }


@router.get("/metrics")
async def metrics(db: DB) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, model in (
        ("terms", Term),
        ("rooms", Room),
        ("meeting_requests", MeetingRequest),
        ("schedule_runs", ScheduleRun),
        ("assignments", Assignment),
    ):
        out[name] = (await db.execute(select(func.count()).select_from(model))).scalar_one()
    out["runs_by_status"] = {
        k: v for k, v in (await db.execute(select(ScheduleRun.status, func.count()).group_by(ScheduleRun.status))).all()
    }
    return out
