"""The API schema for operators (no-placeholder audit m6, option b): production serves no public docs, so the
OpenAPI document is available to ``planning.admin`` sessions only, uncached."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.deps import Admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/openapi.json", include_in_schema=False)
async def admin_openapi(request: Request, _: Admin) -> Any:
    return JSONResponse(request.app.openapi(), headers={"Cache-Control": "no-store"})
