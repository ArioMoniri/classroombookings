"""OpenAPI-walking audit coverage (ROADMAP Phase 17 follow-up "OpenAPI-walking audit coverage test"; review D5).

Every mutating route (POST / PUT / PATCH / DELETE under ``/api/v1``) has a recorded audit decision:

* ``event``   -- writes an explicit ``audit_events`` action (``publish_event`` / ``audit.record``), in the handler or
  in the named service;
* ``tracked`` -- writes administration tables the audit flush hook records (``app.services.audit.TRACKED``);
* ``job``     -- the change is recorded in its own job / run table (import jobs, schedule runs, chat messages,
  council jobs, AI proposal decisions);
* ``none``    -- no shared state changes: previews, probes, personal settings and links;
* ``gap``     -- a planning write not in ``audit_events`` yet (owner and follow-up named). The gap list is frozen:
  it may only shrink.

A new route without a decision fails this test; so does a route that disappeared. For ``event`` rows the named
module must actually contain an audit call, and a sample of ``tracked`` / ``event`` routes is exercised on the
real Bahar data.
"""

from __future__ import annotations

import importlib
import inspect
import re

from app.core import db as dbmod
from app.main import app
from app.models import AuditEvent
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401

AUDIT_CALL = re.compile(r"publish_event|audit(?:_log)?\.record|record_assignments|record_many|record_override|_audit\(")

E, T, J, N, G = "event", "tracked", "job", "none", "gap"
DECISIONS: dict[str, tuple[str, str]] = {
    # approvals (P1)
    "POST /api/v1/approvals/groups/{group_id}/decide": (E, "app.services.approvals"),
    "POST /api/v1/approvals/sweep": (E, "app.services.approvals"),
    "PUT /api/v1/approvals/approvers/{user_id}": (E, "app.services.approvals"),
    "POST /api/v1/approvals/{request_id}/decide": (E, "app.services.approvals"),
    "POST /api/v1/approvals/{request_id}/withdraw": (E, "app.services.approvals"),
    "POST /api/v1/approval-rules": (E, "app.api.v1.approvals"),
    "PUT /api/v1/approval-rules/{rule_id}": (E, "app.api.v1.approvals"),
    "DELETE /api/v1/approval-rules/{rule_id}": (E, "app.api.v1.approvals"),
    "POST /api/v1/me/notifications/read": (N, "the user's own in-app notifications"),
    "PUT /api/v1/me/notification-preferences": (T, "Setting (user.<id>.notification_prefs)"),
    # audit (P7)
    "POST /api/v1/audit/{event_id}/undo": (E, "app.services.bookings_undo"),
    # auth
    "POST /api/v1/auth/login": (N, "sign-in; failures are throttled, the user keeps last_login_at"),
    "POST /api/v1/auth/logout": (N, "revokes the caller's own tokens (token_version)"),
    "PUT /api/v1/auth/profile": (T, "User"),
    "POST /api/v1/auth/change-password": (T, "User (password hash redacted)"),
    "POST /api/v1/auth/password-reset/request": (N, "a one-time code row + outbox; no account data changes"),
    "POST /api/v1/auth/password-reset/confirm": (T, "User (password hash redacted)"),
    # Microsoft Entra ID sign-in (app/services/sso.py; the callback is a GET and audits auth.login / auth.login_refused)
    "POST /api/v1/auth/sso/exchange": (N, "redeems the one-time ticket; the sign-in is audited at the callback"),
    "POST /api/v1/auth/sso/entra/link": (N, "single-use state row; the link is audited at the callback"),
    "DELETE /api/v1/auth/sso/entra/link": (E, "app.services.sso"),
    "PUT /api/v1/auth/sso/admin/entra": (E, "app.services.sso"),
    "POST /api/v1/auth/sso/admin/entra/mappings": (E, "app.services.sso"),
    "DELETE /api/v1/auth/sso/admin/entra/mappings/{mapping_id}": (E, "app.services.sso"),
    "POST /api/v1/auth/sso/admin/invites": (E, "app.services.sso"),
    "POST /api/v1/auth/sso/admin/invites/{invite_id}/renew": (E, "app.services.sso"),
    "DELETE /api/v1/auth/sso/admin/invites/{invite_id}": (E, "app.services.sso"),
    "POST /api/v1/auth/sso/admin/users/{user_id}/bind": (E, "app.services.sso"),
    "DELETE /api/v1/auth/sso/admin/users/{user_id}/identity": (E, "app.services.sso"),
    "PUT /api/v1/auth/sso/admin/users/{user_id}/instructor": (E, "app.services.sso"),
    # wave 3b W3-IDP: several identity providers (app/services/identity/**)
    "POST /api/v1/auth/sso/admin/providers": (E, "app.services.identity.providers"),
    "PUT /api/v1/auth/sso/admin/providers/order": (E, "app.services.identity.providers"),
    "PUT /api/v1/auth/sso/admin/providers/{provider_id}": (E, "app.services.identity.providers"),
    "DELETE /api/v1/auth/sso/admin/providers/{provider_id}": (E, "app.services.identity.providers"),
    "POST /api/v1/auth/sso/admin/providers/{provider_id}/discover": (E, "app.services.identity.providers"),
    "POST /api/v1/auth/sso/admin/providers/{provider_id}/test": (
        N,
        "single-use state rows; the test login's outcome is audited (sso.test_login) at the callback",
    ),
    "POST /api/v1/auth/sso/admin/providers/{provider_id}/mappings": (E, "app.services.sso"),
    "DELETE /api/v1/auth/sso/admin/providers/{provider_id}/mappings/{mapping_id}": (E, "app.services.sso"),
    "POST /api/v1/auth/sso/admin/invites/bulk": (E, "app.services.identity.invites"),
    "POST /api/v1/auth/sso/admin/invites/{invite_id}/resend": (E, "app.services.identity.invites"),
    "POST /api/v1/auth/sso/invites/{token}/password": (E, "app.services.identity.invites"),
    "POST /api/v1/auth/sso/{slug}/acs": (E, "app.services.sso"),
    # Profil › Güvenlik links of the Google / OIDC / SAML providers (idp-2026-10-18, app/services/identity/links.py)
    "POST /api/v1/auth/sso/{slug}/link": (
        N,
        "single-use state row after re-authentication; the link is audited (auth.identity_bound) at the callback / ACS",
    ),
    "POST /api/v1/auth/sso/{slug}/unlink": (E, "app.services.identity.links"),
    # AU-B two-step sign-in, passkeys, trusted devices, admin resets (app/services/mfa.py audits every event)
    "POST /api/v1/auth/mfa/totp/start": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/totp/confirm": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/disable": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/recovery-codes": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/verify": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/passkey/options": (N, "stores the WebAuthn challenge on the caller's own sign-in step"),
    "POST /api/v1/auth/mfa/passkey/verify": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/setup/totp/start": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/setup/totp/confirm": (E, "app.services.mfa"),
    "POST /api/v1/auth/mfa/setup/passkey/options": (N, "stores the WebAuthn challenge on the caller's own setup step"),
    "POST /api/v1/auth/mfa/setup/passkey/verify": (E, "app.services.mfa"),
    "POST /api/v1/auth/passkeys/register/options": (N, "a single-use registration challenge row of the caller"),
    "POST /api/v1/auth/passkeys/register/verify": (E, "app.services.mfa"),
    "PATCH /api/v1/auth/passkeys/{passkey_id}": (E, "app.services.mfa"),
    "POST /api/v1/auth/passkeys/{passkey_id}/remove": (E, "app.services.mfa"),
    "POST /api/v1/auth/passkey/options": (N, "an anonymous single-use passkey sign-in challenge"),
    "POST /api/v1/auth/passkey/verify": (E, "app.services.mfa"),
    "DELETE /api/v1/auth/trusted-devices/{device_id}": (E, "app.services.mfa"),
    "DELETE /api/v1/auth/trusted-devices": (E, "app.services.mfa"),
    "PUT /api/v1/admin/auth/mfa-policy": (E, "app.services.mfa"),
    "POST /api/v1/admin/users/{user_id}/mfa/reset": (E, "app.services.mfa"),
    "POST /api/v1/admin/users/{user_id}/password-reset-link": (E, "app.services.mfa"),
    # AU-15 server-side sessions (app/services/sessions.py)
    "DELETE /api/v1/auth/sessions/{session_id}": (E, "app.services.sessions"),
    "POST /api/v1/auth/sessions/revoke-others": (E, "app.services.sessions"),
    "POST /api/v1/admin/users/{user_id}/sessions/revoke": (E, "app.services.sessions"),
    # AU-16 "IdP MFA'yı zorunlu tut" per provider
    "PUT /api/v1/admin/auth/providers/{provider_id}/idp-mfa": (E, "app.services.mfa"),
    # booking administration (CRBS setup)
    "PUT /api/v1/booking-admin/sessions/{term_id}": (T, "TermBookingSettings"),
    "PUT /api/v1/booking-admin/sessions/{term_id}/schedules": (T, "TermSchedule"),
    "PUT /api/v1/booking-admin/sessions/{term_id}/dates": (T, "TimetableWeek / term dates"),
    "POST /api/v1/booking-admin/sessions/{term_id}/apply-week": (T, "term dates"),
    "POST /api/v1/booking-admin/schedules": (T, "BookingSchedule"),
    "PUT /api/v1/booking-admin/schedules/{sid}": (T, "BookingSchedule"),
    "DELETE /api/v1/booking-admin/schedules/{sid}": (T, "BookingSchedule"),
    "POST /api/v1/booking-admin/schedules/{sid}/periods": (T, "BookingPeriod"),
    "POST /api/v1/booking-admin/schedules/{sid}/periods/from-grid": (T, "BookingPeriod"),
    "PUT /api/v1/booking-admin/periods/{pid}": (T, "BookingPeriod"),
    "DELETE /api/v1/booking-admin/periods/{pid}": (T, "BookingPeriod"),
    "POST /api/v1/booking-admin/weeks": (T, "TimetableWeek"),
    "PUT /api/v1/booking-admin/weeks/{wid}": (T, "TimetableWeek"),
    "DELETE /api/v1/booking-admin/weeks/{wid}": (T, "TimetableWeek"),
    "POST /api/v1/booking-admin/outbox/{oid}/retry": (N, "re-sends an outbox e-mail (the outbox row is the record)"),
    # bookings
    "POST /api/v1/bookings": (E, "app.services.bookings"),
    "POST /api/v1/bookings/recurring/preview": (N, "dry run"),
    "POST /api/v1/bookings/recurring": (E, "app.services.bookings"),
    "POST /api/v1/bookings/multi": (N, "the caller's selection draft"),
    "DELETE /api/v1/bookings/multi/{mb_id}": (N, "the caller's selection draft"),
    "POST /api/v1/bookings/multi/{mb_id}/create": (E, "app.services.bookings"),
    "POST /api/v1/bookings/feed/token": (N, "the caller's own calendar link (stored hashed)"),
    "PUT /api/v1/bookings/{booking_id}": (E, "app.services.bookings"),
    "POST /api/v1/bookings/{booking_id}/cancel": (E, "app.services.bookings"),
    "POST /api/v1/bookings/cancel-multi": (E, "app.services.bookings"),
    "POST /api/v1/buildings": (T, "Building"),
    # notification channels (app/api/v1/channels.py): admin sender config, KVKK sign-off, user link / unlink
    "PUT /api/v1/channels/admin/{kind}": (E, "app.services.channels.config"),
    "POST /api/v1/channels/admin/webpush/vapid": (E, "app.services.channels.config"),
    "POST /api/v1/channels/admin/telegram/setup": (E, "app.api.v1.channels"),
    "PUT /api/v1/channels/admin/{kind}/departments/{department_id}": (E, "app.services.channels.targets"),
    "DELETE /api/v1/channels/admin/{kind}/departments/{department_id}": (E, "app.services.channels.targets"),
    "POST /api/v1/channels/admin/whatsapp_web/connect": (E, "app.services.channels.bridge"),
    "POST /api/v1/channels/admin/whatsapp_web/logout": (E, "app.services.channels.bridge"),
    "POST /api/v1/channels/telegram/webhook": (E, "app.services.channels.links"),
    "POST /api/v1/me/channels/telegram/link": (N, "a one-time nonce (stored as an HMAC); nothing is linked yet"),
    "POST /api/v1/me/channels/telegram/check": (E, "app.services.channels.links"),
    "POST /api/v1/me/channels/webpush": (E, "app.services.channels.links"),
    "POST /api/v1/me/channels/{kind}/link": (N, "a one-time code row + its outbox message; nothing is linked yet"),
    "POST /api/v1/me/channels/{kind}/verify": (E, "app.services.channels.links"),
    "POST /api/v1/me/channels/{channel_id}/test": (N, "queues a test message to the caller's own address"),
    "DELETE /api/v1/me/channels/{channel_id}": (E, "app.services.channels.links"),
    # calendar sync
    "POST /api/v1/calendar/feeds/tokens": (N, "the caller's own calendar link (stored hashed)"),
    "POST /api/v1/calendar/feeds/reset": (N, "the caller's own calendar links"),
    "DELETE /api/v1/calendar/feeds/tokens/{token_id}": (N, "the caller's own calendar link"),
    "POST /api/v1/calendar/connectors/{provider}/connect": (N, "the caller's own OAuth grant"),
    "PUT /api/v1/calendar/connectors/{provider}": (N, "the caller's own calendar choice"),
    "DELETE /api/v1/calendar/connectors/{provider}": (E, "app.api.v1.calendar_sync"),  # calendar.push_disconnect
    "POST /api/v1/calendar/connectors/{provider}/resync": (N, "re-queues the caller's own push jobs"),
    "PUT /api/v1/calendar/admin/settings": (E, "app.api.v1.calendar_sync"),
    # calendar export for academicians (CAL-03 / CAL-06 / CAL-07; cal-b-2026-10-17)
    "POST /api/v1/calendar/subscriptions": (E, "app.api.v1.calendar_sync"),
    "DELETE /api/v1/calendar/subscriptions/{sub_id}": (E, "app.api.v1.calendar_sync"),
    "POST /api/v1/calendar/subscriptions/{sub_id}/rotate": (E, "app.api.v1.calendar_sync"),
    "PUT /api/v1/calendar/connectors/{provider}/scopes": (E, "app.api.v1.calendar_sync"),
    "PUT /api/v1/calendar/admin/export-settings": (E, "app.api.v1.calendar_sync"),
    # constraints (D1)
    "POST /api/v1/constraints": (E, "app.api.v1.constraints"),
    "PUT /api/v1/constraints/{cid}": (E, "app.api.v1.constraints"),
    "DELETE /api/v1/constraints/{cid}": (E, "app.api.v1.constraints"),
    # council (multi-format intake)
    "POST /api/v1/council/jobs": (J, "council job tables"),
    "POST /api/v1/council/jobs/{job_id}/review": (J, "council job tables"),
    "POST /api/v1/council/jobs/{job_id}/commit": (E, "app.council.commit"),
    "POST /api/v1/council/jobs/{job_id}/rerun": (J, "council job tables"),
    "POST /api/v1/council/jobs/{job_id}/rows/decisions": (E, "app.council.airows"),  # council.review
    "DELETE /api/v1/council/memory/{row_id}": (E, "app.council.memory_admin"),  # council.memory.forget
    "DELETE /api/v1/council/memory": (E, "app.council.memory_admin"),  # council.memory.forget
    # catalogue (P19-C1/C2)
    **{
        f"{m} /api/v1/{res}{suffix}": (E, "app.services.catalog_admin")
        for res, key in (
            ("faculties", "faculty_id"),
            ("programs", "program_id"),
            ("courses", "course_id"),
            ("instructors", "instructor_id"),
            ("sections", "section_id"),
        )
        for m, suffix in (("POST", ""), ("PUT", f"/{{{key}}}"), ("DELETE", f"/{{{key}}}"))
    },
    "POST /api/v1/sections/{section_id}/pattern": (E, "app.services.catalog_admin"),
    "POST /api/v1/requests/meetings": (E, "app.services.catalog_admin"),
    "DELETE /api/v1/requests/meetings/{meeting_id}": (E, "app.services.catalog_admin"),
    "POST /api/v1/requests/exams": (E, "app.services.catalog_admin"),
    "DELETE /api/v1/requests/exams/{exam_id}": (E, "app.services.catalog_admin"),
    # CRBS upgrade, departments, holidays, imports
    "POST /api/v1/crbs-upgrade": (T, "Role / User / Room / Term ... through the importer"),
    "POST /api/v1/departments": (T, "Program"),
    "PUT /api/v1/departments/{dep_id}": (T, "Program"),
    "DELETE /api/v1/departments/{dep_id}": (T, "Program"),
    "POST /api/v1/holidays": (T, "Holiday"),
    "PUT /api/v1/holidays/{holiday_id}": (T, "Holiday"),
    "DELETE /api/v1/holidays/{holiday_id}": (T, "Holiday"),
    "POST /api/v1/imports/planning-list": (J, "import_jobs (file, kind, summary) under the term write lock"),
    "POST /api/v1/imports/exam-list": (J, "import_jobs"),
    "POST /api/v1/imports/weekly-grid": (J, "import_jobs"),
    "POST /api/v1/imports/room-master": (J, "import_jobs"),
    "POST /api/v1/imports/crbs": (J, "import_jobs"),
    # RF-06: apply a previewed import (dry_run); the job records who, the finished import writes import.run
    "POST /api/v1/imports/{job_id}/apply": (J, "import_jobs (created_by, preview_of) + import.run"),
    # RF-09: the period grid (clock times of P1-P18)
    "PUT /api/v1/period-grid": (E, "app.services.period_grid"),
    "DELETE /api/v1/period-grid": (E, "app.services.period_grid"),
    # learned suggestions (P19-L2..L4)
    "POST /api/v1/learning/refresh": (E, "app.api.v1.learning"),  # learning.refresh (actor, term, counts)
    "POST /api/v1/learning/suggestions/{prior_id}/accept": (E, "app.services.learning"),
    "POST /api/v1/learning/suggestions/{prior_id}/reject": (E, "app.services.learning"),
    "POST /api/v1/learning/suggestions/{prior_id}/snooze": (E, "app.services.learning"),
    "POST /api/v1/learning/suggestions/{prior_id}/restore": (E, "app.services.learning"),
    "POST /api/v1/learning/reset": (E, "app.services.learning"),
    "POST /api/v1/learning/resets/{reset_id}/undo": (E, "app.services.learning"),
    "POST /api/v1/learning/purge": (E, "app.api.v1.learning"),  # learning.purge_run + one learning.purge per reset
    "POST /api/v1/learning/erase": (E, "app.services.learning"),
    # moderation (P19-M1..M3)
    "PUT /api/v1/moderation/sections/{section_id}/priority": (E, "app.services.moderation"),
    "PUT /api/v1/moderation/requests/{request_id}/priority": (E, "app.services.moderation"),
    "POST /api/v1/terms/{term_id}/moderation/resolve": (E, "app.services.moderation"),
    "PUT /api/v1/moderation/matchings/{request_id}": (E, "app.services.moderation"),
    # P19 backend gaps: person / programme priority (person.priority, program.priority with the term)
    "PUT /api/v1/moderation/people/{instructor_id}/priority": (E, "app.services.moderation"),
    "PUT /api/v1/moderation/programs/{program_id}/priority": (E, "app.services.moderation"),
    # P19-T2 "Tercih ekle": an academician's own wish, the coordinator's decision (preference.* audit actions)
    "POST /api/v1/moderation/me/preferences": (E, "app.services.teacher_preferences"),
    "DELETE /api/v1/moderation/me/preferences/{constraint_id}": (E, "app.services.teacher_preferences"),
    "POST /api/v1/moderation/preferences/{constraint_id}/decide": (E, "app.services.teacher_preferences"),
    # program wizard drafts (P19-W): the draft is wizard state, nothing live changes until the commit
    "POST /api/v1/program-drafts": (N, "a wizard draft; nothing in the term changes until commit"),
    "PATCH /api/v1/program-drafts/{draft_id}": (N, "autosave of a wizard draft (versioned on the draft row)"),
    "DELETE /api/v1/program-drafts/{draft_id}": (N, "an uncommitted wizard draft; committed drafts are kept"),
    "POST /api/v1/program-drafts/{draft_id}/validate": (N, "validation only"),
    "POST /api/v1/program-drafts/{draft_id}/precheck": (N, "pre-check in a rolled-back session"),
    "POST /api/v1/program-drafts/{draft_id}/paste": (N, "TSV preview, nothing stored"),
    "POST /api/v1/program-drafts/{draft_id}/commit": (E, "app.services.program_drafts"),
    "POST /api/v1/program-drafts/{draft_id}/undo": (E, "app.services.program_drafts"),
    # organisation
    "POST /api/v1/org/setup": (T, "User / Setting"),
    "PUT /api/v1/org/settings": (T, "Setting / Role"),
    "POST /api/v1/org/logo": (T, "Setting"),
    "DELETE /api/v1/org/logo": (T, "Setting"),
    "PUT /api/v1/org/auth/ldap": (T, "Setting (secrets redacted)"),
    "POST /api/v1/org/auth/ldap/test": (N, "probe"),
    "PUT /api/v1/org/smtp": (T, "Setting (secrets redacted)"),
    "POST /api/v1/org/smtp/test": (N, "probe (the outbox row is the record)"),
    "PUT /api/v1/org/translations": (T, "Translation"),
    "DELETE /api/v1/org/translations/{tid}": (T, "Translation"),
    "POST /api/v1/org/changelog/seen": (N, "the caller's own preference"),
    # presets, requests
    "POST /api/v1/presets": (E, "app.api.v1.presets"),
    "PUT /api/v1/presets/{preset_id}": (E, "app.api.v1.presets"),
    "DELETE /api/v1/presets/{preset_id}": (E, "app.api.v1.presets"),
    "POST /api/v1/presets/{preset_id}/apply": (E, "app.api.v1.presets"),
    "PUT /api/v1/requests/meetings/{mr_id}": (E, "app.api.v1.requests"),
    "POST /api/v1/requests/meetings/{mr_id}/check-room": (N, "read-only check"),
    "PUT /api/v1/requests/exams/{ex_id}": (E, "app.api.v1.requests"),
    # roles, rooms
    "POST /api/v1/roles": (T, "Role"),
    "PUT /api/v1/roles/{role_id}": (T, "Role"),
    "DELETE /api/v1/roles/{role_id}": (T, "Role"),
    **{
        k: (T, "RoomGroup / Room / RoomCustomField / RoomAcl")
        for k in (
            "POST /api/v1/room-admin/groups",
            "POST /api/v1/room-admin/groups/from-buildings",
            "PUT /api/v1/room-admin/groups/order",
            "PUT /api/v1/room-admin/groups/{gid}",
            "DELETE /api/v1/room-admin/groups/{gid}",
            "PUT /api/v1/room-admin/rooms/order",
            "PUT /api/v1/room-admin/rooms/{room_id}",
            "POST /api/v1/room-admin/rooms/{room_id}/photo",
            "DELETE /api/v1/room-admin/rooms/{room_id}/photo",
            "POST /api/v1/room-admin/fields",
            "PUT /api/v1/room-admin/fields/{fid}",
            "DELETE /api/v1/room-admin/fields/{fid}",
            "PUT /api/v1/room-admin/rooms/{room_id}/fields",
            "POST /api/v1/room-admin/acl",
            "PUT /api/v1/room-admin/acl/{acl_id}",
            "DELETE /api/v1/room-admin/acl/{acl_id}",
        )
    },
    **{
        k: (E, "app.services.rooms_features")
        for k in (
            "POST /api/v1/room-admin/features",
            "POST /api/v1/room-admin/features/adopt-tags",
            "POST /api/v1/room-admin/features/template",
            "POST /api/v1/room-admin/features/bulk-values",
            "PUT /api/v1/room-admin/features/{fid}",
            "DELETE /api/v1/room-admin/features/{fid}",
            "PUT /api/v1/room-admin/rooms/{room_id}/features",
        )
    },
    "POST /api/v1/rooms": (T, "Room"),
    "PUT /api/v1/rooms/{room_id}": (T, "Room"),
    "DELETE /api/v1/rooms/{room_id}": (T, "Room"),
    "POST /api/v1/rooms/{room_id}/photo": (T, "Room"),
    "POST /api/v1/rooms/find": (N, "search (the caller's recent searches)"),
    # runs, timetable edits (D4 / D5)
    "POST /api/v1/runs": (J, "schedule_runs (created_by, params)"),
    "DELETE /api/v1/runs/{run_id}": (E, "app.api.v1.runs"),
    "POST /api/v1/runs/{run_id}/cancel": (J, "schedule_runs (status CANCELLED, error names who)"),
    "POST /api/v1/runs/{run_id}/activate": (E, "app.api.v1.runs"),
    "POST /api/v1/runs/{run_id}/assignments/{aid}/move": (E, "app.api.v1.runs"),
    "POST /api/v1/runs/{run_id}/assignments/{aid}/lock": (E, "app.services.planning_audit"),
    "POST /api/v1/runs/{run_id}/diagnoses/{idx}/apply": (E, "app.api.v1.runs"),
    "POST /api/v1/runs/{run_id}/chat": (J, "chat_messages; changes become a child run (AI agent)"),
    "POST /api/v1/runs/{run_id}/chat/stream": (J, "chat_messages (AI agent)"),
    "POST /api/v1/runs/{run_id}/chat/apply": (J, "child run stats.ai (diff, verifier, user) (AI agent)"),
    "POST /api/v1/runs/{run_id}/explain": (N, "AI explanation text"),
    "POST /api/v1/runs/{run_id}/assignments/bulk-move": (E, "app.services.planning_audit"),
    "POST /api/v1/runs/{run_id}/assignments/{aid}/move-preview": (N, "dry run"),
    "POST /api/v1/runs/{run_id}/assignments/restore": (E, "app.services.planning_audit"),
    "POST /api/v1/runs/{run_id}/assignments/bulk-lock": (E, "app.services.planning_audit"),
    "POST /api/v1/runs/{run_id}/assignments/{aid}/explain": (N, "explanation text"),
    # settings, studio (importer agent), terms
    "PUT /api/v1/settings": (T, "Setting (secrets redacted)"),
    "PUT /api/v1/admin/security-contact": (E, "app.api.v1.security_contact"),
    "POST /api/v1/settings/test-ai": (N, "probe"),
    "PUT /api/v1/studio/meetings/bulk": (E, "app.api.v1.studio"),
    "POST /api/v1/studio/meetings/{mr_id}/revert": (E, "app.api.v1.studio"),
    "POST /api/v1/studio/meetings/revert": (E, "app.api.v1.studio"),
    "POST /api/v1/studio/constraints/preview": (N, "dry run"),
    "POST /api/v1/studio/constraints/copy": (E, "app.api.v1.studio"),
    "POST /api/v1/terms": (T, "Term"),
    "PUT /api/v1/terms/{term_id}": (T, "Term"),
    "DELETE /api/v1/terms/{term_id}": (T, "Term"),
    "PUT /api/v1/terms/{term_id}/weeks": (T, "Week"),
    "PATCH /api/v1/terms/{term_id}/weeks/{index}": (T, "Week"),  # RF-09: one week, marked edited
    "PUT /api/v1/terms/{term_id}/relaxation-policy": (E, "app.api.v1.terms"),  # term.relaxation_policy
    "POST /api/v1/terms/{term_id}/elicit": (N, "AI proposals, nothing written"),
    "POST /api/v1/terms/{term_id}/elicit/accept": (J, "ai_proposal_decisions + constraints.source_ref (AI agent)"),
    "POST /api/v1/terms/{term_id}/preferences/upload": (N, "AI proposals, nothing written"),
    "PUT /api/v1/ai/policy": (E, "app.ai.policy"),
    "PUT /api/v1/terms/{term_id}/studio": (E, "app.api.v1.studio"),
    "POST /api/v1/terms/{term_id}/studio/precheck": (N, "computes the pre-check"),
    "POST /api/v1/terms/{term_id}/studio/precheck/fix": (E, "app.api.v1.studio"),
    "POST /api/v1/terms/{term_id}/studio/proposals/accept": (E, "app.api.v1.studio"),
    "POST /api/v1/terms/{term_id}/studio/preferences/mapping": (
        N,
        "returns proposals only; they are written (and audited) by proposals/accept",
    ),
    "POST /api/v1/terms/{term_id}/studio/generate": (J, "schedule_runs"),
    # users
    "POST /api/v1/users": (T, "User"),
    "PUT /api/v1/users/{user_id}": (T, "User"),
    "DELETE /api/v1/users/{user_id}": (T, "User"),
    "POST /api/v1/users/{user_id}/password": (T, "User (password hash redacted)"),
    "PUT /api/v1/users/{user_id}/constraints": (T, "UserConstraint"),
    "POST /api/v1/users/import": (T, "User"),
    "POST /api/v1/users/{user_id}/reset-token": (E, "app.services.bookings_users"),
    # saved views, webhooks
    "POST /api/v1/views": (N, "the caller's own saved view"),
    "PUT /api/v1/views/{view_id}": (N, "the caller's own saved view"),
    "DELETE /api/v1/views/{view_id}": (N, "the caller's own saved view"),
    "POST /api/v1/webhooks": (E, "app.api.v1.webhooks"),
    "PUT /api/v1/webhooks/{webhook_id}": (E, "app.api.v1.webhooks"),
    "DELETE /api/v1/webhooks/{webhook_id}": (E, "app.api.v1.webhooks"),
    "POST /api/v1/webhooks/{webhook_id}/secret": (E, "app.api.v1.webhooks"),
    "POST /api/v1/webhooks/{webhook_id}/test": (N, "ping (webhook_deliveries is the record)"),
    "POST /api/v1/webhooks/deliveries/{delivery_id}/redeliver": (E, "app.api.v1.webhooks"),
    # booking enhancements wave 2: P8 booking policies + exam-period mode (booking_policy.* audit actions)
    "POST /api/v1/booking-policies": (E, "app.api.v1.booking_policies"),
    "PUT /api/v1/booking-policies/{policy_id}": (E, "app.api.v1.booking_policies"),
    "DELETE /api/v1/booking-policies/{policy_id}": (E, "app.api.v1.booking_policies"),
    "PUT /api/v1/booking-policies/exam-period": (E, "app.api.v1.booking_policies"),
    # P2 conflict resolver after publishing (booking.move / booking.cancel / approval.reject + booking_conflict.*)
    "POST /api/v1/bookings/conflicts/{run_id}/apply": (E, "app.services.booking_conflicts"),
    "POST /api/v1/bookings/conflicts/{run_id}/auto": (N, "a dry-run suggestion; nothing changes"),
    "POST /api/v1/bookings/conflicts/{run_id}/detect": (E, "app.services.booking_conflicts"),
    # V2 public day view: the switch records the KVKK sign-off (public_schedule.settings)
    "PUT /api/v1/public-schedule/admin/settings": (E, "app.services.public_schedule"),
    # A4 KVKK: notices, consents, data-subject requests, retention (kvkk.* audit actions)
    "POST /api/v1/me/privacy/ack": (E, "app.services.kvkk"),
    "POST /api/v1/me/consents/{purpose}": (E, "app.services.kvkk"),
    "DELETE /api/v1/me/consents/{purpose}": (E, "app.services.kvkk"),
    "POST /api/v1/me/data-requests": (E, "app.services.kvkk"),
    "POST /api/v1/admin/dsr/{request_id}/complete": (E, "app.services.kvkk"),
    "POST /api/v1/admin/dsr/{request_id}/refuse": (E, "app.services.kvkk"),
    "PUT /api/v1/admin/retention/{data_class}": (E, "app.services.kvkk"),
    "POST /api/v1/admin/retention/run": (E, "app.services.kvkk"),
    "POST /api/v1/admin/privacy-notices": (E, "app.api.v1.kvkk"),
    "PUT /api/v1/admin/privacy-notices/{notice_id}": (E, "app.api.v1.kvkk"),
    "POST /api/v1/admin/privacy-notices/{notice_id}/publish": (E, "app.api.v1.kvkk"),
    "DELETE /api/v1/admin/privacy-notices/{notice_id}": (E, "app.api.v1.kvkk"),
    # invigilator assignment (invigilator.* / invigilation.* audit actions; app/services/invigilation.py)
    "POST /api/v1/invigilation/pool": (E, "app.services.invigilation"),
    "PUT /api/v1/invigilation/pool/{member_id}": (E, "app.services.invigilation"),
    "DELETE /api/v1/invigilation/pool/{member_id}": (E, "app.services.invigilation"),
    "POST /api/v1/invigilation/plans": (E, "app.services.invigilation"),
    "POST /api/v1/invigilation/plans/{plan_id}/rerun": (E, "app.services.invigilation"),
    "POST /api/v1/invigilation/plans/{plan_id}/activate": (E, "app.services.invigilation"),
    "DELETE /api/v1/invigilation/plans/{plan_id}": (E, "app.services.invigilation"),
    "POST /api/v1/invigilation/plans/{plan_id}/duties/{duty_id}/lock": (E, "app.services.invigilation"),
    "PUT /api/v1/invigilation/plans/{plan_id}/duties/{duty_id}": (E, "app.services.invigilation"),
    "POST /api/v1/invigilation/plans/{plan_id}/duties": (E, "app.services.invigilation"),
    # W3-AI provider gateway, limits, guardrails (ai.* audit actions; secrets never reach the log)
    "PUT /api/v1/ai/admin/providers/{provider}": (E, "app.api.v1.ai_admin"),
    "POST /api/v1/ai/admin/providers/{provider}/sync": (E, "app.api.v1.ai_admin"),
    "POST /api/v1/ai/admin/providers/{provider}/test": (T, "ai_usage + setting ai.provider.<p>.test"),
    "PUT /api/v1/ai/admin/providers/{provider}/capabilities": (E, "app.api.v1.ai_admin"),
    "PUT /api/v1/ai/faculty/allocations": (E, "app.api.v1.ai_faculty"),
    "PUT /api/v1/ai/admin/routes": (E, "app.api.v1.ai_admin"),
    "PUT /api/v1/ai/admin/limits": (E, "app.api.v1.ai_admin"),
    "POST /api/v1/ai/admin/limits/topup": (E, "app.api.v1.ai_admin"),
    "PUT /api/v1/ai/admin/guardrails": (E, "app.api.v1.ai_admin"),
    "POST /api/v1/ai/admin/guardrails/check": (N, "dry run: the deterministic guard's verdict, no model call"),
    "POST /api/v1/ai/admin/redteam": (N, "dry run: the shipped guard corpus, no model call"),
    # voice VO-03 / VO-04: the transcription writes only its metering row (audio and transcript are never stored)
    "POST /api/v1/ai/voice/transcribe": (J, "ai_usage row (voice_stt, audio_in); no audio, no transcript"),
    "PUT /api/v1/ai/admin/voice": (E, "app.api.v1.ai_admin"),
    # W3-OPS error tracking: reports are rows of their own table; the triage is an audit event
    "POST /api/v1/ops/errors": (J, "error_events (grouped, scrubbed client report)"),
    "POST /api/v1/ops/client-errors": (J, "error_events (alias of POST /ops/errors)"),
    "POST /api/v1/ops/errors/{error_id}/status": (E, "app.api.v1.ops"),
    # W3-MAIL SMTP setup + themed e-mails
    "PUT /api/v1/mail/settings": (T, "settings group smtp (bookings_settings.set_group)"),
    "POST /api/v1/mail/outbox/requeue": (E, "app.services.mail"),
    "POST /api/v1/mail/test": (E, "app.services.mail"),
    "POST /api/v1/mail/dns-check": (N, "DNS lookup of SPF / DKIM / DMARC"),
    "POST /api/v1/mail/templates/{kind}/preview": (N, "render only"),
    "PUT /api/v1/mail/templates/{kind}": (T, "translations set email"),
    "POST /api/v1/mail/templates/{kind}/test": (E, "app.services.mail"),
    # welcome guide per role WG-01..03: the person's own guide state; the admin switches / texts / reshow are audited
    "POST /api/v1/welcome/events": (N, "the caller's own welcome_progress (shown / snoozed / step / item_done)"),
    "POST /api/v1/welcome/restart": (N, "the caller's own welcome_progress (Help › Turu yeniden başlat)"),
    "PUT /api/v1/welcome/settings": (E, "app.services.welcome"),
    "PUT /api/v1/welcome/content/{audience}": (E, "app.services.welcome"),
    "POST /api/v1/welcome/content/{audience}/reshow": (E, "app.services.welcome"),
    # adaptive scheduling AS-03 / AS-10: season profiles (season_profile.*), admin period segments, what-if runs
    "POST /api/v1/seasons/profiles": (E, "app.services.seasons"),
    "PUT /api/v1/seasons/profiles/{profile_id}": (E, "app.services.seasons"),
    "POST /api/v1/seasons/profiles/{profile_id}/activate": (E, "app.services.seasons"),
    "POST /api/v1/seasons/profiles/{profile_id}/revert": (E, "app.services.seasons"),
    "DELETE /api/v1/seasons/profiles/{profile_id}": (E, "app.services.seasons"),
    "POST /api/v1/seasons/terms/{term_id}/segments": (E, "app.api.v1.seasons"),
    "PUT /api/v1/seasons/segments/{segment_id}": (E, "app.api.v1.seasons"),
    "DELETE /api/v1/seasons/segments/{segment_id}": (E, "app.api.v1.seasons"),
    "POST /api/v1/analytics/forecast/what-if": (E, "app.services.forecast"),
    # FIX-F AS20-F04: "Uygula" on an exam advisor move (one exam_request.update row per moved row)
    "POST /api/v1/analytics/forecast/exams/advice/apply": (E, "app.services.exam_advisor"),
    # AS-13 / RF-07: learning versions, calibration, per-habit controls, nightly switch
    "POST /api/v1/learning/versions/{version_id}/revert": (E, "app.services.learning_versions"),
    "POST /api/v1/learning/calibration/apply": (E, "app.services.learning_versions"),
    "PUT /api/v1/learning/priors/{prior_id}/habit": (E, "app.services.learning_versions"),
    "PUT /api/v1/learning/settings": (E, "app.api.v1.learning"),
    # AS-14: a learned-weights draft profile goes through seasons.create_profile / update_profile (season_profile.*)
    "POST /api/v1/learning/weights/propose": (E, "app.services.seasons"),
    # AI helper (app/ai/helper; app/api/v1/helper.py): action cards are reads or dry-run previews
    "POST /api/v1/helper/actions/{name}/card": (N, "a read, or a write's dry-run preview with a signed token"),
    "POST /api/v1/helper/actions/confirm": (E, "app.ai.helper.confirm"),
    "POST /api/v1/helper/turn": (N, "reads and write previews, metered in ai_usage; writes need /confirm"),
    # HB-23b helper file router: classify writes no row (the bytes are staged encrypted for 10 minutes, KVKK note
    # docs/kvkk/helper-file-stage.md); the card's button writes helper.file.handoff; the target import audits itself
    "POST /api/v1/helper/files/classify": (N, "reads a file's header area; no row, no job; encrypted 10-min stage"),
    "POST /api/v1/helper/files/route": (N, "a card from the staged signals; nothing written"),
    "POST /api/v1/helper/files/handoff": (E, "app.api.v1.helper_files"),
    "DELETE /api/v1/helper/files/{sid}": (N, "deletes the person's own encrypted file stage"),
    "POST /api/v1/helper/actions/undo": (E, "app.ai.helper.confirm"),
    "PUT /api/v1/helper/memory": (T, "Setting (user.<id>.helper_memory)"),
    "POST /api/v1/helper/notes": (N, "the person's own helper note (Bunu hatırla)"),
    "DELETE /api/v1/helper/notes/{note_id}": (N, "the person's own helper note"),
    "DELETE /api/v1/helper/notes": (N, "the person's own helper notes and history"),
    "DELETE /api/v1/helper/threads": (E, "app.ai.helper.memory"),
    "PUT /api/v1/helper/admin/settings": (E, "app.api.v1.helper"),
    # helper telemetry (HB-14): aggregate product events of the person, no content; settings (HB-15) audited
    "POST /api/v1/helper/feedback": (N, "the person's own thumbs / note on an answer (helper_events, aggregates)"),
    "POST /api/v1/helper/events": (N, "client telemetry (nav_click / form_open / cancel), aggregates only"),
    "PUT /api/v1/ai/admin/helper": (E, "app.api.v1.ai_admin"),
}
#: frozen: may only shrink (a closed gap moves to event / tracked)
KNOWN_GAPS = frozenset(k for k, (cat, _) in DECISIONS.items() if cat == G)
GAP_CEILING = 0  # studio / presets closed 2026-10-15 (studio_audit)


def mutating_routes() -> set[str]:
    def walk(routes, prefix=""):  # type: ignore[no-untyped-def]
        for r in routes:
            ctx = getattr(r, "include_context", None)
            if ctx is not None and hasattr(r, "original_router"):
                yield from walk(r.original_router.routes, prefix + (ctx.prefix or ""))
            elif getattr(r, "endpoint", None) is not None and getattr(r, "methods", None):
                yield prefix + r.path, r

    out = set()
    for path, r in walk(app.routes):
        for m in set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"}:
            out.add(f"{m} {path}")
    if not out:  # older FastAPI: flat route list
        for r in app.routes:
            for m in set(getattr(r, "methods", None) or ()) & {"POST", "PUT", "PATCH", "DELETE"}:
                out.add(f"{m} {r.path}")
    return out


def test_every_mutating_route_has_an_audit_decision():
    routes = mutating_routes()
    assert len(routes) > 150
    missing = sorted(routes - set(DECISIONS))
    stale = sorted(set(DECISIONS) - routes)
    assert not missing, f"mutating routes without an audit decision (add them to DECISIONS): {missing}"
    assert not stale, f"decisions for routes that no longer exist: {stale}"
    assert {c for c, _ in DECISIONS.values()} <= {E, T, J, N, G}
    assert len(KNOWN_GAPS) <= GAP_CEILING, "audit gaps may only shrink"


def test_event_decisions_name_a_module_that_audits():
    for key, (cat, where) in DECISIONS.items():
        if cat != E:
            continue
        src = inspect.getsource(importlib.import_module(where))
        assert AUDIT_CALL.search(src), f"{key}: {where} contains no audit call"


async def test_sampled_routes_write_audit_rows(env):  # noqa: F811
    """One tracked and one explicit route on the real Bahar data."""
    c = env.client
    r = await c.put(f"/api/v1/rooms/{env.rooms['A101']}", json={"notes": "Akıllı tahta arızalı"}, headers=env.admin)
    assert r.status_code == 200, r.text
    r = await c.post(
        "/api/v1/constraints",
        json={"term_id": env.term_id, "kind": "capacity", "params": {}, "hardness": "hard"},
        headers=env.planner,
    )
    assert r.status_code == 201, r.text
    async with dbmod.get_session_factory()() as s:
        actions = set((await s.execute(select(AuditEvent.action))).scalars())
    assert {"room.update", "constraint.create"} <= actions, actions
    uid, _ = await env.user("sifre.kodu@uni.edu.tr")
    r = await c.post(f"/api/v1/users/{uid}/reset-token", headers=env.admin)
    assert r.status_code in (200, 201), r.text
    async with dbmod.get_session_factory()() as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "user.reset_code"))).scalar_one()
    assert ev.entity_id == str(uid) and r.json()["token"] not in str(ev.after)
