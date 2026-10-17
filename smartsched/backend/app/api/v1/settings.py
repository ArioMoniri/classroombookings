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


# --- slot display (W3-SLOT, docs/design/v3/slot-display.md §3 / SD-13): refuse what no surface can draw -----------

_SLOT_LABELS_TR = {
    "unit": "Birim",
    "block_minutes": "Blok süresi",
    "label": "Etiket",
    "period_name": "Ders adı",
    "time_format": "Saat biçimi",
    "density": "Yoğunluk",
    "first_period": "İlk görünen ders",
    "last_period": "Son görünen ders",
    "hide_short": "Kısa dersleri gizle",
    "hide_weekend": "Hafta sonunu gizle",
    "default_view_desktop": "Masaüstü açılış görünümü",
    "default_view_phone": "Telefon açılış görünümü",
    "min_length": "En kısa süre",
    "quick_span": "Hızlı rezervasyon süresi",
}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _slot_display_problem(extra: dict[str, Any]) -> HTTPException | None:
    """422 for the first ``booking.slot_display.*`` value outside its allowed set (``""`` / null resets a key)."""
    from app.api.v1 import bookings as b

    def refuse(name: str, allowed: str, allowed_en: str) -> HTTPException:
        label = _SLOT_LABELS_TR.get(name, name)
        return HTTPException(
            422,
            {
                "code": "invalid_slot_display",
                "field": f"{b.SLOT_DISPLAY_PREFIX}{name}",
                "message": f"{name}: {allowed_en}",
                "message_en": f"Slot display {name}: {allowed_en}",
                "message_tr": f"Dilim görünümü › {label}: {allowed}",
            },
        )

    ints: dict[str, int] = {}
    for key, value in extra.items():
        if not key.startswith(b.SLOT_DISPLAY_PREFIX):
            continue
        name = key[len(b.SLOT_DISPLAY_PREFIX) :]
        if key not in ss.SPECS:
            return refuse(name, "bilinmeyen ayar.", "unknown setting.")
        if value is None or value == "":
            continue
        if name in b._SLOT_CHOICES:
            choices = b._SLOT_CHOICES[name]
            if value not in choices:
                return refuse(
                    name, "şunlardan biri olmalı: " + ", ".join(choices) + ".", "one of " + ", ".join(choices) + "."
                )
        elif name == "default_view_desktop":
            if value not in b._DESKTOP_VIEWS:
                views = ", ".join(b._DESKTOP_VIEWS)
                return refuse(
                    name, f"boş (kurumun görünümü) ya da şunlardan biri: {views}.", f"empty or one of {views}."
                )
        elif name == "block_minutes":
            if _as_int(value) not in b._BLOCK_MINUTES:
                return refuse(name, "15, 30 ya da 60 dakika olmalı.", "15, 30 or 60 minutes.")
        elif name in ("first_period", "last_period"):
            n = _as_int(value)
            if n is None or not 0 <= n <= b._PERIOD_MAX:
                return refuse(
                    name,
                    f"0 (hepsi) ile {b._PERIOD_MAX} arasında bir ders numarası olmalı.",
                    f"a period number from 0 (all) to {b._PERIOD_MAX}.",
                )
            ints[name] = n
        elif name in ("min_length", "quick_span"):
            n = _as_int(value)
            if n is None or not 1 <= n <= b._LENGTH_MAX:
                return refuse(name, f"1 ile {b._LENGTH_MAX} arasında olmalı.", f"from 1 to {b._LENGTH_MAX}.")
            ints[name] = n
        elif name in ("hide_short", "hide_weekend"):
            if not isinstance(value, bool) and str(value).lower() not in ("true", "false"):
                return refuse(name, "açık ya da kapalı olmalı.", "true or false.")
    first, last = ints.get("first_period", 0), ints.get("last_period", 0)
    if first and last and first > last:
        return refuse(
            "first_period",
            "ilk görünen ders son görünen dersten sonra olamaz.",
            "the first visible period comes after the last.",
        )
    return None


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
    problem = _slot_display_problem(data.get("extra") or {})
    if problem is not None:  # before any write: a refused request stores nothing
        raise problem
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
    if any(str(k).startswith("security.") for k in extra):
        # the security.txt contact has one validated, audited path (PUT /admin/security-contact)
        from app.api.v1.security_contact import refusal
        from app.services import security_txt as st

        current = await st.current(db)
        merged = {name: extra.get(key, current.get(name)) for name, key in st.KEYS.items()}
        try:
            values = st.validate(merged)
        except st.InvalidContact as exc:
            raise refusal(exc) from exc
        for name, key in st.KEYS.items():
            if key in extra:
                extra[key] = values[name]
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
