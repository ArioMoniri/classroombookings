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
        SettingSpec("solver_default_time_limit", default=60.0, kind="float"),
        SettingSpec("solver_workers", default=8, kind="int"),
        SettingSpec("solver_weights", default="{}"),
        SettingSpec("ui_language", default="tr"),
        SettingSpec("timezone", default="Europe/Istanbul"),
    )
}


def _env_default(key: str) -> Any:
    s = get_settings()
    return {
        "anthropic_api_key": s.anthropic_api_key,
        "anthropic_model": s.anthropic_model,
        "solver_default_time_limit": s.solver_default_time_limit,
        "solver_workers": s.solver_workers,
    }.get(key, SPECS[key].default if key in SPECS else None)


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
