from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.ai.client import DEFAULT_MODEL, test_connection
from app.ai.policy import get_policy, set_policy
from app.api.deps import DB, Admin
from app.core.security import redact_keys, validate_api_key
from app.schemas.settings import SettingsUpdate, TestAiIn, TestAiOut
from app.services import settings_service as ss
from app.services.crbs_dsn import format_allowlist, parse_allowlist
from app.services.kvkk import AI_PERSONAL_DEFAULT_KEY, AI_PERSONAL_DEFAULTS, parse_ai_personal_default

router = APIRouter(prefix="/settings", tags=["settings"])
log = logging.getLogger(__name__)


async def _view(db: DB) -> dict[str, Any]:
    out = await ss.get_all_masked(db)
    # one AI policy (app/ai/policy.py): the council toggle reports the effective intake switch
    policy = await get_policy(db)
    out["council_ai_enabled"] = policy["intake_enabled"]
    out["ai_policy"] = policy
    return out


@router.get("")
async def get_settings_view(db: DB, _: Admin) -> dict[str, Any]:
    return await _view(db)


@router.put("")
async def update_settings(body: SettingsUpdate, db: DB, user: Admin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    if "council_ai_enabled" in data:
        # the council toggle is the AI intake + vision switch; it carries the KVKK text, so switching it on is
        # the administrator's acknowledgement (sign-off record + ai.policy audit event)
        on = bool(data.pop("council_ai_enabled"))
        await set_policy(
            db,
            user,
            intake_enabled=on,
            vision_enabled=on,
            kvkk_ack=on,
            reason="Settings > AI toggle council_ai_enabled",
        )
    if data.get("anthropic_api_key"):
        try:
            data["anthropic_api_key"] = validate_api_key(data["anthropic_api_key"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    extra = data.pop("extra", None) or {}
    if "crbs_dsn_allowed_hosts" in extra:  # one validated path for the SSRF allowlist (review D16)
        data["crbs_dsn_allowed_hosts"] = extra.pop("crbs_dsn_allowed_hosts")
    if data.get("crbs_dsn_allowed_hosts") is not None:
        try:
            data["crbs_dsn_allowed_hosts"] = format_allowlist(parse_allowlist(str(data["crbs_dsn_allowed_hosts"])))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if AI_PERSONAL_DEFAULT_KEY in extra:  # KVKK: what a never-given ai_personal consent means (consent gates)
        raw = extra[AI_PERSONAL_DEFAULT_KEY]
        value = parse_ai_personal_default(raw)
        if value is None:
            raise HTTPException(
                422,
                {
                    "code": "ai_personal_default",
                    "field": AI_PERSONAL_DEFAULT_KEY,
                    "message": "kvkk.ai_personal_default is included (only a withdrawal excludes a person from AI "
                    "requests) or excluded (not granted = excluded)",
                    "message_en": "kvkk.ai_personal_default is included (only a withdrawal excludes a person from AI "
                    "requests) or excluded (not granted = excluded)",
                    "message_tr": "kvkk.ai_personal_default değeri included (yalnızca rızasını geri alan kişi yapay "
                    "zekâ isteklerinin dışında kalır) ya da excluded (rıza vermeyen herkes dışarıda kalır) olabilir",
                    "allowed": list(AI_PERSONAL_DEFAULTS),
                },
            )
        extra[AI_PERSONAL_DEFAULT_KEY] = value
    for key, value in {**data, **extra}.items():
        if key == "solver_weights" and isinstance(value, dict):
            import json

            value = json.dumps(value)
        await ss.set_value(db, key, value)
    return await _view(db)


async def _probe_ai(api_key: str, model: str) -> tuple[bool, str]:
    """Tiny probe via the AI layer (:func:`app.ai.client.test_connection`). Replaced in tests."""
    return await test_connection(api_key, model)


@router.post("/test-ai", response_model=TestAiOut)
async def test_ai(body: TestAiIn, db: DB, _: Admin) -> TestAiOut:
    """Verify a Claude key: the transient ``api_key`` in the body (not saved) or the stored key."""
    used = "none"
    try:
        key = validate_api_key(body.api_key or "")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if key:
        used = "transient"
    else:
        key = await ss.get_value(db, "anthropic_api_key") or ""
        if key:
            used = "stored"
    model = body.model or await ss.get_value(db, "anthropic_model") or DEFAULT_MODEL
    if not key:
        return TestAiOut(ok=False, model=model, detail="no API key configured", used_key=used)
    ok, detail = await _probe_ai(key, model)  # a real 1-token call; ok only when it succeeded
    detail = redact_keys(detail)
    await ss.record_key_test(db, key, ok, detail)
    return TestAiOut(ok=ok, model=model, detail=detail, used_key=used)
