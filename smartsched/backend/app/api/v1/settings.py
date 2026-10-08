from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.ai.client import DEFAULT_MODEL, test_connection
from app.api.deps import DB, Admin
from app.core.security import redact_keys, validate_api_key
from app.schemas.settings import SettingsUpdate, TestAiIn, TestAiOut
from app.services import settings_service as ss

router = APIRouter(prefix="/settings", tags=["settings"])
log = logging.getLogger(__name__)


@router.get("")
async def get_settings_view(db: DB, _: Admin) -> dict[str, Any]:
    return await ss.get_all_masked(db)


@router.put("")
async def update_settings(body: SettingsUpdate, db: DB, _: Admin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    if data.get("anthropic_api_key"):
        try:
            data["anthropic_api_key"] = validate_api_key(data["anthropic_api_key"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    extra = data.pop("extra", None) or {}
    for key, value in {**data, **extra}.items():
        if key == "solver_weights" and isinstance(value, dict):
            import json

            value = json.dumps(value)
        await ss.set_value(db, key, value)
    return await ss.get_all_masked(db)


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
