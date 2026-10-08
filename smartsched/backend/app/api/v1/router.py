from __future__ import annotations

from fastapi import APIRouter, Depends

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
from app.api.v1.audit import audit_context  # noqa: E402
from app.api.v1.room_features import facets_router  # noqa: E402

# P7: every /api/v1 request names its actor, request id and hashed network for the audit log
api_router = APIRouter(dependencies=[Depends(audit_context)])
for r in (
    health.router,
    facets_router,  # GET /rooms/facets before GET /rooms/{room_id}
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

# calendar v2 + all-classes read models, scoped/bulk moves, explain, saved views (docs/design/v2/calendar.md)
from app.api.v1 import calendar as calendar_v2  # noqa: E402

api_router.include_router(calendar_v2.router)

# booking enhancements wave 1 (ROADMAP Phase 17, docs/product/wave1-api.md): typed room features (P10), find a
# room (T1), audit log + undo (P7), approval workflows (P1)
from app.api.v1 import approvals, audit, find_room, room_features  # noqa: E402

for r in (
    room_features.router,
    find_room.router,
    audit.router,
    approvals.router,
    approvals.rules_router,
    approvals.me_router,
):
    api_router.include_router(r)
