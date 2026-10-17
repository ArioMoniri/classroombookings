"""Organisation, LDAP and SMTP settings (CRBS ``settings`` groups ``crbs``, ``dates``, ``lang``, ``features``
and ``auth``), stored in the ``settings`` table under prefixed keys. Secret values (SMTP password) are
encrypted with APP_SECRET and only ever returned masked."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models import Setting


@dataclass(frozen=True)
class Spec:
    key: str
    kind: str = "str"  # str | int | bool | json
    default: Any = None
    secret: bool = False


ORG_SPECS: dict[str, Spec] = {
    s.key: s
    for s in (
        Spec("name", default=""),
        Spec("website", default=""),
        Spec("logo_url", default=None),
        Spec("displaytype", default="day"),  # day | room
        Spec("d_columns", default="periods"),  # periods | rooms | days
        Spec("login_message_enabled", "bool", False),
        Spec("login_message_text", default=""),
        Spec("maintenance_mode", "bool", False),
        Spec("maintenance_mode_message", default=""),
        Spec("use_room_groups", "bool", True),
        Spec("pattern_long", default="EEEE d MMMM yyyy"),
        Spec("pattern_weekday", default="EEE d MMM"),
        Spec("pattern_time", default="HH:mm"),
        Spec("default_language", default="tr"),
        Spec("languages", "json", ["tr", "en"]),
        # CRBS settings/General "grid_highlight": coloured highlight of the mouse-focused grid slot
        Spec("grid_highlight", "bool", False),
    )
}
LDAP_SPECS: dict[str, Spec] = {
    s.key: s
    for s in (
        # defaults are the ones CRBS's installer writes (Installer::get_settings, group "auth")
        Spec("enabled", "bool", False),
        Spec("create_users", "bool", True),
        Spec("server", default=""),
        Spec("port", "int", 389),
        Spec("version", "int", 3),
        Spec("use_tls", "bool", False),
        # CRBS's installer writes 1 (certificates never checked); SmartSched checks them unless the admin
        # explicitly switches this on (docs/review/2026-10-08-crbs-parity-audit.md, deliberate differences)
        Spec("ignore_cert", "bool", False),
        Spec("bind_dn_format", default="uid=:user,dc=example,dc=com"),
        Spec("base_dn", default="dc=example,dc=com"),
        Spec("search_filter", default="(&(uid=:user)(objectClass=person))"),
        Spec("attr_firstname", default=""),
        Spec("attr_lastname", default=""),
        Spec("attr_displayname", default="cn"),
        Spec("attr_email", default="mail"),
        Spec("default_role_id", "int", None),
        Spec("default_department_id", "int", None),
    )
}
SMTP_SPECS: dict[str, Spec] = {
    s.key: s
    for s in (
        Spec("host", default=""),
        Spec("port", "int", 587),
        Spec("security", default="starttls"),  # starttls | ssl | none
        Spec("username", default=""),
        Spec("password", default="", secret=True),
        Spec("from_address", default=""),
        Spec("from_name", default="SmartSched"),
        Spec("timeout_s", "int", 15),
        # wave 3b W3-MAIL (app/services/mail.py, docs/deploy/email.md): guided setup shared by every admin
        Spec("provider", default=""),  # a preset id of app/services/mail_presets.py, "" = custom
        Spec("auth_mode", default="password"),  # password | xoauth2 | none
        Spec("oauth_provider", default=""),  # google | microsoft (XOAUTH2)
        Spec("oauth_tenant", default=""),  # Microsoft Entra tenant id (client credentials)
        Spec("oauth_client_id", default=""),
        Spec("oauth_client_secret", default="", secret=True),
        Spec("oauth_refresh_token", default="", secret=True),
        Spec("reply_to", default=""),
        Spec("dkim_selector", default=""),  # the selector the provider console shows (DNS check)
        # KVKK md. 9 acknowledgement for a provider abroad: {"by", "by_user_id", "at", "provider"} (W3-MAIL)
        Spec("abroad_ack", "json", None),
    )
}
BOOKINGS_SPECS: dict[str, Spec] = {
    s.key: s
    for s in (
        # CRBS hides rooms that belong to no room group from the booking grid (Rooms_model::get_bookable_rooms);
        # an administrator may show them (as an "ungrouped" tab) instead.
        Spec("show_ungrouped_rooms", "bool", False),
        # --- deliberate differences (docs/review/2026-10-08-crbs-parity-audit.md). Behaviour switches default
        # to what CRBS does; security switches default to the safer SmartSched rule.
        # (a) CRBS checks max_active_bookings in the grid (Slot) and in multi-booking, not when a single booking
        #     is posted (SingleAgent); True also refuses POST /bookings past the limit.
        Spec("enforce_max_active_on_create", "bool", False),
        # (f) CRBS counts only "book" instances against recur_max_instances; True also counts "replace".
        Spec("recur_max_counts_replacements", "bool", False),
        # (g) CRBS's maintenance gate is the Bookings controller only; True also closes the dashboard,
        #     "my bookings", owned rooms and the calendar feeds.
        Spec("maintenance_gates_lists", "bool", False),
        # (i) CRBS computes the current session from its dates (Sessions_model::auto_set_current);
        #     True keeps the manual terms.is_active flag instead.
        Spec("manual_current_term", "bool", False),
        # (j) CRBS's export joins room_groups (INNER): bookings of ungrouped rooms are left out; True includes them.
        Spec("export_ungrouped_rooms", "bool", False),
        # (b) CRBS's multi-booking recurring step lets book_recur.create choose the department
        #     (MultiAgent::process_recurring_defaults); True requires book_recur.set_department.
        Spec("recurring_department_needs_set_department", "bool", False),
        # (c) security: unauthorised user/department choices answer 403; True restores CRBS (silently book
        #     for yourself / your own department).
        Spec("ignore_unauthorised_user_department", "bool", False),
        # security: scope=all cancels this and future instances only (past instances stay as history);
        #     True restores CRBS (Bookings_model::cancel_all cancels every instance).
        Spec("cancel_all_includes_past", "bool", False),
        # MISSING 3 (Bookings_model::check_session_dates): when a term's dates shrink, bookings outside them are
        #     "cancel" = cancelled with a reason at once (CRBS deletes them), "confirm" = the change is refused
        #     with the list until it is repeated with ?confirm=true.
        Spec("term_date_change", default="cancel"),
        # P7 (beyond CRBS): a booking create / move / cancel can be undone within this many hours (or until the
        #     booking starts), as long as nothing changed it since (POST /audit/{id}/undo).
        Spec("audit_undo_hours", "int", 24),
        # approval-first bookings (owner requirement 2026-10-15): "rules" = only rooms / room groups / room types
        #     with an approval rule need approval (CRBS + P1, the default of empty and universal installs);
        #     "all" = every booking request goes to the approvers first, except for users holding
        #     approvals.decide, planning.admin or bookings.skip_approval (app/services/approvals.py need_for).
        #     The institution install sets it once: PUT /api/v1/org/settings {"approval_mode": "all"}.
        Spec("approval_mode", default="rules"),
    )
}
APPROVAL_MODES = ("rules", "all")
#: KVKK sign-off (admin persona 2026-10-15 M-18): never shipped as a default. It exists only after a named
#: administrator switched calendar sync on through ``PUT /calendar/admin/settings`` (who, user id, when);
#: until then ``calendar_sync_enabled`` reads as off whatever is stored (:func:`kvkk_signed`). alembic
#: 0022_kvkk_signoff_unseed marks copies of the former pre-seeded 2026-10-08 record as not signed.
SIGNOFF_GATED = ("integrations", "calendar_sync_enabled", "calendar_sync_signoff")


def kvkk_signed(record: Any) -> bool:
    """A real sign-off: enabled, by a named administrator (``by`` + integer ``by_user_id``) at an ISO date."""
    if not isinstance(record, dict) or record.get("enabled") is not True or record.get("signed") is False:
        return False
    uid, by, at = record.get("by_user_id"), record.get("by"), record.get("at")
    if not isinstance(uid, int) or isinstance(uid, bool) or not isinstance(by, str) or not by.strip():
        return False
    try:
        date.fromisoformat(str(at)[:10])
    except ValueError:
        return False
    return True


# Calendar sync, push connectors and webhooks (docs/product/calendar-sync-api.md). Client secrets are stored
# encrypted with APP_SECRET; no client id ships with the product (connectors report configured: false).
INTEGRATIONS_SPECS: dict[str, Spec] = {
    s.key: s
    for s in (
        Spec("calendar_sync_enabled", "bool", False),  # off until an administrator signs off (kvkk_signed)
        Spec("calendar_sync_signoff", "json", None),
        Spec("webhooks_enabled", "bool", False),
        Spec("public_url", default=""),
        Spec("feed_past_days", "int", 90),
        Spec("feed_cancelled_grace_days", "int", 14),
        Spec("google_client_id", default=""),
        Spec("google_client_secret", default="", secret=True),
        Spec("microsoft_client_id", default=""),
        Spec("microsoft_client_secret", default="", secret=True),
        Spec("microsoft_tenant", default="organizations"),
    )
}
# P8 exam-period mode (docs/product/booking-enhancements.md §P8; app/services/booking_policies.py). Off by default:
# an administrator switches it on for the institution (PUT /booking-policies/exam-period).
#   exam_period_mode: "off" | "request" (bookings of exam rooms in exam weeks become approval requests) |
#                     "closed" (refused)
#   exam_period_rooms: {"from_exam_timetable": true, "room_ids": [...]}: the rooms the term's exam timetable uses
#                      and / or a list chosen by the administrator
POLICY_SPECS: dict[str, Spec] = {
    s.key: s
    for s in (
        Spec("exam_period_mode", default="off"),
        Spec("exam_period_rooms", "json", None),
    )
}
# V2 public read-only day view (docs/product/booking-enhancements.md §V2; app/services/public_schedule.py). Off by
# default; it counts as on only with a KVKK sign-off recorded when an administrator switches it on
# (PUT /public-schedule/admin/settings), like calendar sync. The pages never show personal data.
PUBLIC_SPECS: dict[str, Spec] = {
    s.key: s
    for s in (
        Spec("schedule_enabled", "bool", False),
        Spec("schedule_signoff", "json", None),
        # bookings appear as "Rezerve / Reserved" blocks ("busy") or not at all ("hidden"); never with a name or note
        Spec("show_bookings", default="busy"),
    )
}
GROUPS = {
    "policies": POLICY_SPECS,
    "public": PUBLIC_SPECS,
    "org": ORG_SPECS,
    "ldap": LDAP_SPECS,
    "smtp": SMTP_SPECS,
    "bookings": BOOKINGS_SPECS,
    "integrations": INTEGRATIONS_SPECS,
}


def _decode(spec: Spec, raw: str | None) -> Any:
    if raw is None:
        return spec.default
    try:
        if spec.kind == "int":
            return int(raw)
        if spec.kind == "bool":
            return raw.lower() in {"1", "true", "yes", "on"}
        if spec.kind == "json":
            return json.loads(raw)
    except (TypeError, ValueError):
        return spec.default
    return raw


def _encode(spec: Spec, value: Any) -> str | None:
    if value is None:
        return None
    if spec.kind == "bool":
        return "1" if value else "0"
    if spec.kind == "json":
        return json.dumps(value, ensure_ascii=False)
    return str(value)


async def get_group(session: AsyncSession, group: str, *, reveal: bool = False) -> dict[str, Any]:
    specs = GROUPS[group]
    rows = {r.key: r for r in (await session.execute(select(Setting).where(Setting.key.like(f"{group}.%")))).scalars()}
    out: dict[str, Any] = {}
    for key, spec in specs.items():
        row = rows.get(f"{group}.{key}")
        raw = row.value if row is not None else None
        if spec.secret:
            plain = None
            if raw:
                try:
                    plain = decrypt_secret(raw)
                except ValueError:
                    plain = None
            out[key] = plain if reveal else {"set": bool(plain), "masked": mask_secret(plain)}
        else:
            out[key] = _decode(spec, raw)
    if group == SIGNOFF_GATED[0]:
        out[SIGNOFF_GATED[1]] = bool(out[SIGNOFF_GATED[1]]) and kvkk_signed(out[SIGNOFF_GATED[2]])
    return out


async def set_group(session: AsyncSession, group: str, values: dict[str, Any]) -> None:
    specs = GROUPS[group]
    for key, value in values.items():
        spec = specs.get(key)
        if spec is None:
            raise KeyError(key)
        full = f"{group}.{key}"
        row = await session.get(Setting, full)
        if spec.secret:
            stored = encrypt_secret(str(value)) if value not in (None, "") else None
        else:
            stored = _encode(spec, value)
        if row is None:
            session.add(Setting(key=full, value=stored, is_secret=spec.secret))
        else:
            row.value = stored
            row.is_secret = spec.secret
    await session.flush()


async def get_value(session: AsyncSession, group: str, key: str) -> Any:
    if (group, key) == SIGNOFF_GATED[:2]:  # the KVKK switch counts only with a real sign-off (M-18)
        on = await _stored_value(session, group, key)
        return bool(on) and kvkk_signed(await _stored_value(session, group, SIGNOFF_GATED[2]))
    return await _stored_value(session, group, key)


async def _stored_value(session: AsyncSession, group: str, key: str) -> Any:
    spec = GROUPS[group][key]
    row = await session.get(Setting, f"{group}.{key}")
    if row is None:
        return spec.default
    if spec.secret:
        return decrypt_secret(row.value) if row.value else None
    return _decode(spec, row.value)


async def smtp_configured(session: AsyncSession) -> bool:
    smtp = await get_group(session, "smtp", reveal=True)
    return bool(smtp["host"] and smtp["from_address"])


# per-user values (CRBS settings group ``user.N``)
async def get_user_value(session: AsyncSession, user_id: int, key: str) -> str | None:
    row = await session.get(Setting, f"user.{user_id}.{key}")
    return row.value if row is not None else None


async def set_user_value(session: AsyncSession, user_id: int, key: str, value: str | None) -> None:
    full = f"user.{user_id}.{key}"
    row = await session.get(Setting, full)
    if row is None:
        session.add(Setting(key=full, value=value, is_secret=False))
    else:
        row.value = value
    await session.flush()
