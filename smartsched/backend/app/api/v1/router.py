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

# Generator Studio (phase 8)
from app.api.v1 import presets, studio  # noqa: E402

api_router.include_router(studio.router)
api_router.include_router(presets.router)

# CRBS parity: users, roles, rooms and bookings (docs/CRBS_PARITY.md)
from app.api.v1 import booking_admin, bookings, departments, holidays, org, roles, room_admin  # noqa: E402

for r in (
    roles.router,
    departments.router,
    holidays.router,
    room_admin.router,
    booking_admin.router,
    bookings.router,
    bookings.ics_router,
    org.router,
    org.auth_router,
):
    api_router.include_router(r)

# planner-facing data-conflict report of a run (GET /runs/{id}/data-issues)
from app.api.v1 import data_issues  # noqa: E402

api_router.include_router(data_issues.router)
