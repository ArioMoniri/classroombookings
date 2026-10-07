from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, constraints, health, imports, reference, requests, rooms, runs, settings, terms

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
):
    api_router.include_router(r)
