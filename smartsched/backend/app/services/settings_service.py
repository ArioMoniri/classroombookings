"""Runtime settings stored in the DB (secrets encrypted with APP_SECRET), with env fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models import Setting


@dataclass(frozen=True)
class SettingSpec:
    key: str
    is_secret: bool = False
    default: Any = None
    kind: str = "str"  # str | int | float | bool


SPECS: dict[str, SettingSpec] = {
    s.key: s
    for s in (
        SettingSpec("anthropic_api_key", is_secret=True),
        SettingSpec("anthropic_model", default="claude-opus-5-5"),
        # KVKK: the Ingestion Council sends uploaded file content to Claude only after an administrator opts in
        SettingSpec("council_ai_enabled", default=False, kind="bool"),
        SettingSpec("solver_default_time_limit", default=60.0, kind="float"),
        SettingSpec("solver_workers", default=8, kind="int"),
        SettingSpec("solver_weights", default="{}"),
        SettingSpec("ui_language", default="tr"),
        SettingSpec("timezone", default="Europe/Istanbul"),
        # review D16: hosts a live CRBS MySQL DSN may name (app/services/crbs_dsn.py); empty = none
        SettingSpec("crbs_dsn_allowed_hosts", default=""),
        # KVKK ai_personal (consent gates 2026-10-16; app.services.kvkk.ai_personal_default): "included" = only an
        # explicit withdrawal keeps a person out of AI requests, "excluded" = not granted is excluded
        SettingSpec("kvkk.ai_personal_default", default="included"),
        # wave 3 W3-SLOT (docs/design/v3/slot-display.md §3): how a slot is shown wherever bookings appear (grid,
        # free slots, /reserve, find-room, kiosk). Written by ADMIN through PUT /settings ``extra``; read (sanitised)
        # by every signed-in user: GET /bookings/context ``slot_display``, GET /bookings/slot-display (bookings.py).
        # unit: periods (equal rows) | blocks (size follows minutes, 15/30/60-minute blocks drawn onto the periods)
        SettingSpec("booking.slot_display.unit", default="periods"),
        SettingSpec("booking.slot_display.block_minutes", default=30, kind="int"),
        # both | period ("P3" / "3. ders") | time ("10:30-11:20")
        SettingSpec("booking.slot_display.label", default="both"),
        # schedule (the schedule's own period name, as before wave 3) | ordinal ("3. ders")
        SettingSpec("booking.slot_display.period_name", default="schedule"),
        # range ("10:30-11:20") | start ("10:30")
        SettingSpec("booking.slot_display.time_format", default="range"),
        # compact (32 px rows) | standard (44) | comfortable (56); phones always keep >= 44 px
        SettingSpec("booking.slot_display.density", default="standard"),
        # first / last visible period number (0 = the first / the last): evening periods are hidden this way
        SettingSpec("booking.slot_display.first_period", default=0, kind="int"),
        SettingSpec("booking.slot_display.last_period", default=0, kind="int"),
        # hide periods shorter than 35 minutes (transition slots)
        SettingSpec("booking.slot_display.hide_short", default=False, kind="bool"),
        SettingSpec("booking.slot_display.hide_weekend", default=False, kind="bool"),
        # what /bookings opens on: "" = the organisation's CRBS display type | grid_day | grid_room_week |
        # free_slots | free_week | quick (desktop); free_slots | free_week | quick (phone)
        SettingSpec("booking.slot_display.default_view_desktop", default=""),
        SettingSpec("booking.slot_display.default_view_phone", default="free_slots"),
        # quick reserve lengths, counted in the unit (periods or blocks): from min_length up to quick_span (1..8)
        SettingSpec("booking.slot_display.min_length", default=1, kind="int"),
        SettingSpec("booking.slot_display.quick_span", default=1, kind="int"),
    )
}


def _env_default(key: str) -> Any:
    s = get_settings()
    spec_default = SPECS[key].default if key in SPECS else None
    value = {
        "anthropic_api_key": s.anthropic_api_key,
        "anthropic_model": s.anthropic_model,
        "solver_default_time_limit": s.solver_default_time_limit,
        "solver_workers": s.solver_workers,
    }.get(key, spec_default)
    # an environment variable left empty (ANTHROPIC_MODEL= in a copied .env) is "not set", not a model named ""
    if key != "anthropic_api_key" and isinstance(value, str) and not value.strip():
        return spec_default
    return value


def _coerce(spec: SettingSpec | None, value: Any) -> Any:
    if value is None or spec is None:
        return value
    try:
        if spec.kind == "int":
            return int(value)
        if spec.kind == "float":
            return float(value)
        if spec.kind == "bool":
            return str(value).lower() in {"1", "true", "yes"}
    except (TypeError, ValueError):
        return spec.default
    return value


async def get_value(session: AsyncSession, key: str) -> Any:
    row = await session.get(Setting, key)
    spec = SPECS.get(key)
    if row is None or row.value is None:
        return _coerce(spec, _env_default(key))
    if row.is_secret:
        try:
            return decrypt_secret(row.value)
        except ValueError:
            return None
    return _coerce(spec, row.value)


async def set_value(session: AsyncSession, key: str, value: Any) -> None:
    spec = SPECS.get(key)
    is_secret = spec.is_secret if spec else False
    row = await session.get(Setting, key)
    stored: str | None
    if value is None or value == "":
        stored = None
    else:
        stored = encrypt_secret(str(value)) if is_secret else str(value)
    if row is None:
        session.add(Setting(key=key, value=stored, is_secret=is_secret))
    else:
        row.value = stored
        row.is_secret = is_secret
    await session.commit()


async def get_all_masked(session: AsyncSession) -> dict[str, Any]:
    rows = {r.key: r for r in (await session.execute(select(Setting))).scalars()}
    out: dict[str, Any] = {}
    for key, spec in SPECS.items():
        value = await get_value(session, key)
        if spec.is_secret:
            out[key] = {
                "set": bool(value),
                "masked": mask_secret(value),
                "source": "db" if key in rows and rows[key].value else ("env" if value else None),
            }
            if key == "anthropic_api_key":
                out[key].update(await key_status(session, value))
        else:
            out[key] = value
    for key, row in rows.items():
        if "." in key:  # org.* / ldap.* / smtp.* / user.N.* belong to /org (app/services/bookings_settings.py)
            continue
        if key not in out:
            out[key] = (
                {"set": bool(row.value), "masked": mask_secret(await get_value(session, key))}
                if row.is_secret
                else row.value
            )
    return out


KEY_STATUS = "ai.key_status"  # dotted: internal, not listed by GET /settings


async def record_key_test(session: AsyncSession, key: str, ok: bool, detail: str) -> None:
    """Remember the outcome of the last real probe of ``key`` (by fingerprint, never the key)."""
    import json
    from datetime import UTC, datetime

    from app.core.security import key_fingerprint

    payload = {"fp": key_fingerprint(key), "ok": ok, "detail": detail[:300], "at": datetime.now(UTC).isoformat()}
    row = await session.get(Setting, KEY_STATUS)
    if row is None:
        session.add(Setting(key=KEY_STATUS, value=json.dumps(payload), is_secret=False))
    else:
        row.value = json.dumps(payload)
    await session.commit()


async def key_status(session: AsyncSession, key: str | None) -> dict[str, Any]:
    """``status``: ``none`` (no key), ``unverified`` (saved, never tested - or changed since), ``ok`` /
    ``failed`` (last real probe of exactly this key). A saved key is never reported as connected
    until a probe succeeded (usability U4)."""
    import json

    from app.core.security import key_fingerprint

    if not key:
        return {"status": "none", "checked_at": None, "detail": None}
    row = await session.get(Setting, KEY_STATUS)
    try:
        data = json.loads(row.value) if row is not None and row.value else {}
    except ValueError:
        data = {}
    if data.get("fp") != key_fingerprint(key):
        return {"status": "unverified", "checked_at": None, "detail": None}
    return {"status": "ok" if data.get("ok") else "failed", "checked_at": data.get("at"), "detail": data.get("detail")}
