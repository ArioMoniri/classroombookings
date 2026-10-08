from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    chat,
    constraints,
    dashboard,
    health,
    imports,
    reference,
    requests,
    rooms,
    runs,
    settings,
    terms,
    users,
)

api_router = APIRouter()
for r in (
    health.router,
    auth.router,
    settings.router,
    terms.router,
    rooms.router,
    reference.router,
    requests.router,
    imports.router,
    constraints.router,
    runs.router,
    dashboard.router,
    users.router,
    chat.router,
):
    api_router.include_router(r)
