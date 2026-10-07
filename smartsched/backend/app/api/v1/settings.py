from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.api.deps import DB, Admin
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
    extra = data.pop("extra", None) or {}
    for key, value in {**data, **extra}.items():
        if key == "solver_weights" and isinstance(value, dict):
            import json

            value = json.dumps(value)
        await ss.set_value(db, key, value)
    return await ss.get_all_masked(db)


async def _probe_ai(api_key: str, model: str) -> tuple[bool, str]:
    """1-token call to verify the key. Replaced in tests."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return False, "anthropic SDK not installed"
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(model=model, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        return True, f"ok ({resp.model})"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


@router.post("/test-ai", response_model=TestAiOut)
async def test_ai(body: TestAiIn, db: DB, _: Admin) -> TestAiOut:
    """Verify a Claude key: the transient ``api_key`` in the body (not saved) or the stored key."""
    used = "none"
    key = (body.api_key or "").strip()
    if key:
        used = "transient"
    else:
        key = await ss.get_value(db, "anthropic_api_key") or ""
        if key:
            used = "stored"
    model = body.model or await ss.get_value(db, "anthropic_model")
    if not key:
        return TestAiOut(ok=False, model=model, detail="no API key configured", used_key=used)
    ok, detail = await _probe_ai(key, model)
    return TestAiOut(ok=ok, model=model, detail=detail, used_key=used)
