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
from app.api.v1 import council, presets, studio  # noqa: E402

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

# calendar sync (subscription feeds, Google / Microsoft push connectors) and outgoing webhooks
# (docs/product/calendar-sync-api.md)
from app.api.v1 import calendar_sync, webhooks  # noqa: E402

api_router.include_router(calendar_sync.router)
api_router.include_router(webhooks.router)
# Ingestion Council (universal onboarding)
api_router.include_router(council.router)

# P19-C1/C2 from-scratch programme creation: faculty/programme/course/instructor/section writes, weekly patterns
from app.api.v1 import catalog_admin  # noqa: E402

api_router.include_router(catalog_admin.router)

# Phase 18 part 3 (P18-LEGACY): upgrade a legacy classroombookings database
from app.api.v1 import crbs_upgrade  # noqa: E402

api_router.include_router(crbs_upgrade.router)

# no-placeholder audit m6 (b): the API schema for planning administrators (production has no public docs)
from app.api.v1 import admin_docs  # noqa: E402

api_router.include_router(admin_docs.router)

# Phase 19 P19-L2..L4: learned suggestions (suggest only), memory reset / undo / purge, KVKK erasure
from app.api.v1 import learning  # noqa: E402

api_router.include_router(learning.router)

# Phase 19 P19-M1..M3: moderation tab (people, history, matchings, priorities, re-solve with diff, draft edits)
from app.api.v1 import moderation  # noqa: E402

api_router.include_router(moderation.router)

from app.api.v1 import sso  # noqa: E402  (Entra ID sign-in, /auth/sso; app/services/sso.py)

api_router.include_router(sso.router)

# notification channels (Apprise + pywebpush; docs/product/2026-10-15-integrations-options.md)
from app.api.v1 import channels as notify_channels  # noqa: E402

api_router.include_router(notify_channels.router)

# planning analytics: scenario comparison and utilisation heatmaps (read-only; app/services/scenario_compare.py,
# app/services/utilisation.py)
from app.api.v1 import analytics  # noqa: E402

api_router.include_router(analytics.router)

# booking enhancements wave 2 (ROADMAP Phase 17): P8 booking policies + exam-period mode
from app.api.v1 import booking_policies as booking_policies_api  # noqa: E402

api_router.include_router(booking_policies_api.router)

# booking enhancements wave 2: P2 conflict resolver after publishing (/bookings/conflicts/{run_id}/...)
from app.api.v1 import booking_conflicts as booking_conflicts_api  # noqa: E402

api_router.include_router(booking_conflicts_api.router)

# booking enhancements wave 2: V2 public read-only day view (no sign-in; off until an admin signs off KVKK)
from app.api.v1 import public_schedule as public_schedule_api  # noqa: E402

api_router.include_router(public_schedule_api.router)
api_router.include_router(public_schedule_api.admin_router)

# invigilator assignment for exam runs (pool, plans, duties; app/services/invigilation.py, app/solver/invigilation.py)
from app.api.v1 import invigilation as invigilation_api  # noqa: E402

api_router.include_router(invigilation_api.router)

# booking enhancements wave 2: A4 KVKK (retention + daily purge, notices, consents, export / erase requests)
from app.api.v1 import kvkk as kvkk_api  # noqa: E402

api_router.include_router(kvkk_api.me_router)
api_router.include_router(kvkk_api.public_router)
api_router.include_router(kvkk_api.admin_router)

# wave 3 W3-OPS: operations panel (service status, error groups, log tail, Grafana forward-auth; app/api/v1/ops.py)
from app.api.v1 import ops as ops_api  # noqa: E402

api_router.include_router(ops_api.router)

# wave 3 W3-AI: AI gateway administration (providers, models, usage, limits, guardrails) and GET /ai/me/usage
from app.api.v1 import ai_admin  # noqa: E402

api_router.include_router(ai_admin.router)

# wave 3b W3-HUB: integrations gallery status (read-only aggregator over the areas' own status; /admin/integrations)
from app.api.v1 import integrations as integrations_api  # noqa: E402

api_router.include_router(integrations_api.router)

# wave 3b W3-MAIL: SMTP setup (presets, test with transcript, SPF/DKIM/DMARC), themed e-mail templates (/admin/email)
from app.api.v1 import mail_admin  # noqa: E402

api_router.include_router(mail_admin.router)
