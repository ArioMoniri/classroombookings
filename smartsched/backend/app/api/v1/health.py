from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select, text

from app.api.deps import DB, bearer, get_current_user
from app.core.config import app_version, get_settings
from app.models import Assignment, MeetingRequest, Room, ScheduleRun, Term
from app.services.bookings_perms import load_access

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health(db: DB) -> dict[str, Any]:
    """Public liveness/readiness probe: no solver backend or other internals (no-placeholder audit m7)."""
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "app": get_settings().app_name,
        "version": app_version(),
    }


async def _metrics_access(
    request: Request, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: DB
) -> None:
    """``/metrics`` is not anonymous (review MINOR 5): ``Authorization: Bearer <METRICS_TOKEN>`` for
    scrapers, otherwise an ADMIN (``planning.admin``) session."""
    token = get_settings().metrics_token
    if token and creds is not None and hmac.compare_digest(creds.credentials, token):
        return
    user = await get_current_user(request, creds, db)
    access = await load_access(db, user)
    if "planning.admin" not in access.perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires permission planning.admin")


@router.get("/metrics", dependencies=[Depends(_metrics_access)])
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
