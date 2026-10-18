"""AI gateway administration (wave 3 W3-AI): providers and keys, synced models, per-feature routes, usage, limits,
guardrails, recent refusals, the red-team self-test; plus every user's own usage (``GET /ai/me/usage``).

Voice (VO-04): the sync tags every model with its modalities (``text`` / ``stt`` / ``tts``) and lists the
speech-only providers' fixed models; the test call of a speech model transcribes the bundled 5 s Turkish clip
(``app/ai/voice/assets``); routes accept only speech models for ``voice_stt`` and only text models elsewhere;
``GET / PUT /ai/admin/voice`` hold the voice settings (audited ``ai.voice``); limits take audio seconds.

Who: administrators with ``planning.admin`` or ``setup.settings`` manage everything under ``/ai/admin``; any
signed-in user reads only their own usage. Keys are write-only: answers carry ``{"set", "masked"}`` and never the
value; every change writes an audit event (values of secrets never reach the audit log either).
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.ai import gateway as gw
from app.ai.context import FEATURE_LABELS, FEATURES
from app.ai.providers import PROVIDERS, UnsafeBaseURL, check_base_url, has_credentials, make_adapter
from app.ai.providers.base import ProviderError
from app.ai.redteam import GUARD_CASES_PATH, load_cases, score_guard_cases, summarize_guard
from app.ai.voice import registry as speech
from app.api.deps import DB, CurrentUser, require_permission
from app.core.security import redact_keys, validate_api_key
from app.models import User
from app.services import ai_usage as meter
from app.services import audit

router = APIRouter(tags=["ai-admin"])
AIAdmin = Annotated[User, Depends(require_permission("planning.admin", "setup.settings"))]


def _err(status: int, code: str, tr: str, en: str, **extra: Any) -> HTTPException:
    return HTTPException(status, {"code": code, "message": en, "message_en": en, "message_tr": tr, **extra})


def _provider(p: str) -> str:
    if p not in PROVIDERS:
        raise _err(404, "unknown_provider", "Bilinmeyen sağlayıcı.", "Unknown provider.")
    return p


# ---------------------------------------------------------------------------------------------- schemas


class TransferIn(BaseModel):
    region: str | None = Field(default=None, max_length=64)
    retention: str | None = Field(default=None, max_length=200)
    kvkk_mechanism: str | None = None
    contract_date: str | None = Field(default=None, max_length=20)
    notification_date: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    #: voice (VO-04): this provider receives recordings, and what it does with them (from the agreement)
    processes_voice: bool | None = None
    audio_retention: str | None = Field(default=None, max_length=200)


class ProviderIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    aws_access_key_id: str | None = Field(default=None, max_length=200)
    aws_secret_access_key: str | None = Field(default=None, max_length=500)
    #: secret names to delete
    clear: list[str] = []
    base_url: str | None = Field(default=None, max_length=500)
    region: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    #: openai_compatible only: the explicit opt-in for a local server (Ollama, vLLM) on loopback / a private network
    allow_local: bool | None = None
    transfer: TransferIn | None = None


class TestIn(BaseModel):
    model: str | None = Field(default=None, max_length=128)


class CapabilitiesIn(BaseModel):
    """An admin override of one model's capabilities (HB-12); ``null`` clears a field back to sync / probe."""

    model: str = Field(min_length=1, max_length=128)
    capabilities: dict[str, bool | int | None]


class RoutesIn(BaseModel):
    default: dict[str, Any] | None = None
    features: dict[str, dict[str, Any] | None] = {}


class LimitsIn(BaseModel):
    org_monthly_tokens: int | None = Field(default=None, ge=0)
    org_monthly_cost_usd: float | None = Field(default=None, ge=0)
    user_daily_tokens: int | None = Field(default=None, ge=0)
    user_monthly_tokens: int | None = Field(default=None, ge=0)
    roles: dict[str, dict[str, int]] | None = None
    users: dict[str, dict[str, int]] | None = None
    soft_pct: int | None = Field(default=None, ge=1, le=99)
    alert_recipients: list[int] | None = None
    requests_per_minute: int | None = Field(default=None, ge=0, le=600)
    max_concurrent: int | None = Field(default=None, ge=0, le=20)
    #: voice, in seconds of audio (0 = no limit)
    user_daily_audio_s: int | None = Field(default=None, ge=0, le=86400)
    user_monthly_audio_s: int | None = Field(default=None, ge=0, le=2678400)
    org_monthly_audio_s: int | None = Field(default=None, ge=0, le=100_000_000)


class VoiceIn(BaseModel):
    enabled: bool | None = None
    language: str | None = None
    max_seconds: int | None = Field(default=None, ge=5, le=gw.VOICE_MAX_SECONDS)
    vocabulary: str | None = None
    live_captions: str | None = None
    #: USD per audio minute by ``provider:model``
    prices_per_min: dict[str, float] | None = None


class TopupIn(BaseModel):
    tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    reason: str = Field(min_length=3, max_length=300)


class GuardrailsIn(BaseModel):
    scope_check: bool | None = None
    injection_check: bool | None = None
    model_scope_check: bool | None = None
    upload_neutralize: bool | None = None
    output_check: bool | None = None
    rate_limit: bool | None = None


# ---------------------------------------------------------------------------------------------- providers


async def _provider_out(db: DB, p: str) -> dict[str, Any]:
    spec = PROVIDERS[p]
    secrets = await gw.provider_secrets(db, p)
    cfg = await gw.provider_config(db, p)
    synced = await gw.synced_models(db, p)
    transfer = await gw.transfer_record(db, p)
    allow_local = p == "openai_compatible" and cfg.get("allow_local") is True
    # "local" from the resolved addresses (HB-13), resolved off the event loop
    local = p == "openai_compatible" and await asyncio.to_thread(gw.is_local_url, cfg.get("base_url"))
    return {
        **spec.to_dict(),
        "keys": {name: gw.masked(secrets.get(name)) for name in spec.secrets},
        "config": {k: cfg.get(k) for k in (*spec.config, "enabled") if k in cfg},
        "config_fields": list(spec.config),
        "has_credentials": has_credentials(p, secrets),
        "usable": await gw.provider_usable(db, p),
        "models": synced.get("models") or [],
        "fetched_at": synced.get("fetched_at"),
        "sync_error": synced.get("error"),
        "last_test": await gw.get_json(db, f"ai.provider.{p}.test", {}),
        "transfer": transfer,
        "transfer_ok": gw.transfer_ok(p, cfg, transfer, local=local),
        "local": local,
        "allow_local": allow_local,
        "warnings": [LOCAL_WARNING] if allow_local else [],
    }


#: shown on the provider card while the local-server opt-in is on (docs/SECURITY.md R12)
LOCAL_WARNING = {
    "code": "local_url_opt_in",
    "message_tr": "Yerel sunucuya izin verildi: bu sağlayıcı kurum içi ağdaki ya da bu makinedeki bir adrese "
    "istek gönderebilir. Yalnızca güvendiğiniz bir Ollama / vLLM sunucusu için açık tutun.",
    "message_en": "A local server is allowed: this provider may send requests to an address on the internal network "
    "or this machine. Keep it on only for an Ollama / vLLM server you trust.",
}


@router.get("/ai/admin/providers")
async def list_providers(db: DB, _: AIAdmin) -> dict[str, Any]:
    return {
        "providers": [await _provider_out(db, p) for p in PROVIDERS],
        "kvkk_mechanisms": list(gw.KVKK_MECHANISMS),
    }


@router.put("/ai/admin/providers/{provider}")
async def put_provider(provider: str, body: ProviderIn, db: DB, user: AIAdmin) -> dict[str, Any]:
    p = _provider(provider)
    spec = PROVIDERS[p]
    before = await _provider_out(db, p)
    changed: list[str] = []
    for name in ("api_key", "aws_access_key_id", "aws_secret_access_key"):
        value = getattr(body, name)
        if value is None or not value.strip():
            continue
        if name not in spec.secrets:
            raise _err(
                422,
                "unknown_secret",
                "Bu sağlayıcıda böyle bir anahtar yok.",
                "This provider has no such key.",
                field=name,
            )
        try:
            clean = validate_api_key(value) if name == "api_key" else value.strip()
        except ValueError as exc:
            raise _err(422, "invalid_key", "Anahtar geçersiz karakterler içeriyor.", str(exc), field=name) from exc
        await gw.set_provider_secret(db, p, name, clean)
        changed.append(f"set:{name}")
    for name in body.clear:
        if name in spec.secrets:
            await gw.set_provider_secret(db, p, name, None)
            changed.append(f"clear:{name}")
    cfg = await gw.get_json(db, f"ai.provider.{p}.config", {})
    if body.allow_local is not None:
        if p != "openai_compatible":
            raise _err(
                422,
                "unknown_field",
                "Bu sağlayıcıda bu alan yok.",
                "This provider has no such field.",
                field="allow_local",
            )
        cfg["allow_local"] = bool(body.allow_local)
        changed.append("allow_local")
    for fld in ("base_url", "region", "project_id"):
        value = getattr(body, fld)
        if value is None:
            continue
        if fld not in spec.config:
            raise _err(
                422, "unknown_field", "Bu sağlayıcıda bu alan yok.", "This provider has no such field.", field=fld
            )
        value = value.strip()
        if fld == "base_url" and value and not value.startswith(("http://", "https://")):
            raise _err(
                422,
                "invalid_url",
                "Adres http:// ya da https:// ile başlamalı.",
                "The URL must start with http:// or https://.",
                field=fld,
            )
        if fld == "region" and p == "google_stt" and value and not re.match(r"^[a-z0-9][a-z0-9-]{0,30}$", value):
            raise _err(
                422,
                "invalid_region",
                "Konum bir bölge adı olmalı (ör. eu, us).",
                "The location must be a region name (e.g. eu, us).",
                field=fld,
            )
        cfg[fld] = value or None
        changed.append(fld)
    if ("base_url" in changed or "allow_local" in changed) and cfg.get("base_url"):
        # SSRF guard (app/ai/providers/url_guard.py): https, no metadata / link-local, local only with the opt-in.
        # No DNS here; every request checks the resolved address again.
        try:
            check_base_url(
                str(cfg["base_url"]),
                allow_local=p == "openai_compatible" and cfg.get("allow_local") is True,
                resolve=False,
            )
        except UnsafeBaseURL as exc:
            raise _err(422, "unsafe_url", exc.message_tr, exc.message_en, field="base_url", reason=exc.code) from exc
    if body.enabled is not None:
        cfg["enabled"] = bool(body.enabled)
        changed.append("enabled")
    await gw.put_json(db, f"ai.provider.{p}.config", {k: v for k, v in cfg.items() if v is not None})
    if body.transfer is not None:
        t = body.transfer.model_dump()
        if t.get("kvkk_mechanism") not in (None, "", "none", *gw.KVKK_MECHANISMS):
            raise _err(
                422,
                "invalid_mechanism",
                "Geçersiz KVKK aktarım dayanağı.",
                "Invalid KVKK transfer mechanism.",
                field="kvkk_mechanism",
            )
        t.update(recorded_by=user.id, recorded_at=datetime.now(UTC).isoformat(timespec="seconds"))
        await gw.put_json(db, f"ai.provider.{p}.transfer", {k: v for k, v in t.items() if v not in (None, "")})
        changed.append("transfer")
    after = await _provider_out(db, p)
    await audit.record(
        db,
        "ai.provider",
        "setting",
        f"ai.provider.{p}",
        before={
            "keys_set": {k: v["set"] for k, v in before["keys"].items()},
            "config": before["config"],
            "transfer": before["transfer"],
        },
        after={
            "keys_set": {k: v["set"] for k, v in after["keys"].items()},
            "config": after["config"],
            "transfer": after["transfer"],
            "changed": changed,
        },
        actor=user,
    )
    await db.commit()
    return after


async def _adapter_for(db: DB, p: str, model: str = "") -> Any:
    secrets = await gw.provider_secrets(db, p)
    if not has_credentials(p, secrets):
        raise _err(
            409, "no_credentials", "Bu sağlayıcı için anahtar girilmedi.", "No credentials are set for this provider."
        )
    from app.ai.pipeline import TEST_TRANSPORT

    try:
        return make_adapter(
            p,
            model=model,
            secrets=secrets,
            config=await gw.provider_config(db, p),
            timeout_s=30.0,
            max_retries=1,
            use_fallbacks=False,
            transport=TEST_TRANSPORT[0],
        )
    except ProviderError as exc:
        raise _err(409, "provider_config", "Sağlayıcı ayarları eksik.", str(exc)) from exc


@router.post("/ai/admin/providers/{provider}/sync")
async def sync_provider(provider: str, db: DB, user: AIAdmin) -> dict[str, Any]:
    """List the provider's models through its API and store them with ``fetched_at`` (the UI offers only these)."""
    p = _provider(provider)
    text_capable = "text" in PROVIDERS[p].capabilities
    adapter = await _adapter_for(db, p) if text_capable else await _speech_adapter_for(db, p)
    error: str | None = None
    models: list[dict[str, Any]] = []
    server_kind: str | None = None
    try:
        listed = await adapter.list_models()
        if text_capable:  # capability facts of a local server (HB-12): safe reads, through url_guard
            server_kind = await adapter.sniff(listed)
        for m in listed:
            m.modalities = speech.model_modalities(p, m.id)
            models.append(m.to_dict())
    except Exception as exc:  # noqa: BLE001 - surfaced as a short text, never with the key or the upstream body
        mapped = adapter.translate_error(exc, "") if text_capable else exc
        error = redact_keys(
            str(mapped) if isinstance(mapped, ProviderError) else f"sync failed ({type(exc).__name__})"
        )[:300]
    record = await gw.store_synced_models(db, p, models, error)
    await audit.record(
        db,
        "ai.provider.sync",
        "setting",
        f"ai.provider.{p}.models",
        after={"models": len(record["models"]), "error": error, "server_kind": server_kind},
        actor=user,
    )
    await db.commit()
    return {"ok": error is None, **record, "server_kind": server_kind}


@router.post("/ai/admin/providers/{provider}/test")
async def test_provider(
    provider: str, body: TestIn, db: DB, user: AIAdmin, probe: bool = Query(False)
) -> dict[str, Any]:
    """A tiny real call (a few output tokens, no tools) with the stored credentials; metered as ``test``. With
    ``probe=true`` (HB-12) three tiny calls find out what the model can do (forced tool, JSON schema, a 32×32
    image; under 1000 tokens, one ``test`` row) and the result is stored as the model's ``probe`` capabilities."""
    p = _provider(provider)
    stored = (await gw.synced_models(db, p)).get("models") or []
    synced = [m.get("id") for m in stored]
    model = (body.model or "").strip() or (synced[0] if synced else "")
    if p == "anthropic" and not model:
        model = await gw.legacy_model(db)
    if not model:
        raise _err(409, "sync_first", "Önce modelleri eşitleyin.", "Sync the models first.")
    if model in speech.speech_model_ids(stored) or "text" not in PROVIDERS[p].capabilities:
        return await _test_speech(db, p, model, user)
    adapter = await _adapter_for(db, p, model)
    if probe:
        return await _probe(db, p, model, adapter, user)
    started = time.monotonic()
    ok, detail, usage = False, "", None
    req: dict[str, Any] = {
        "model": model,
        "max_tokens": 16,
        "system": "Reply with OK.",
        "messages": [{"role": "user", "content": "ping"}],
    }
    try:
        msg = await adapter.create(req)
        usage = getattr(msg, "usage", None)
        ok = True
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        detail = f"ok ({getattr(msg, 'model', model)}, {tokens_in} in / {tokens_out} out)"
    except Exception as exc:  # noqa: BLE001
        mapped = adapter.translate_error(exc, model)
        detail = (
            str(mapped)
            if isinstance(mapped, ProviderError)
            else f"could not complete the test call ({type(exc).__name__})"
        )
    detail = redact_keys(detail)[:300]
    await meter.record(
        user_id=user.id,
        feature="test",
        provider=p,
        model=model,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        latency_ms=int((time.monotonic() - started) * 1000),
        outcome="ok" if ok else "provider_error",
        reason_code=None if ok else "provider_error",
        detail=None if ok else detail,
        guard_verdict="skipped",
    )
    result = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ok": ok,
        "detail": detail,
        "model": model,
        "kind": "text",
    }
    await gw.put_json(db, f"ai.provider.{p}.test", result)
    await db.commit()
    return result


async def _probe(db: DB, p: str, model: str, adapter: Any, user: User) -> dict[str, Any]:
    from app.ai import capabilities as caps

    started = time.monotonic()
    found, usage = await caps.probe(adapter, model)
    ok = usage.calls > 0
    detail = (
        f"probe ({model}): "
        + ", ".join(f"{k}={'yes' if found[k] else 'no'}" for k in caps.BOOL_KEYS if found[k] is not None)
    )[:300]
    await meter.record(
        user_id=user.id,
        feature="test",
        provider=p,
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        latency_ms=int((time.monotonic() - started) * 1000),
        outcome="ok" if ok else "provider_error",
        reason_code=None if ok else "provider_error",
        detail="probe" if ok else "probe failed",
        guard_verdict="skipped",
    )
    probes = await gw.get_json(db, f"ai.provider.{p}.probe", {})
    probes[model] = found
    await gw.put_json(db, f"ai.provider.{p}.probe", probes)
    result = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ok": ok,
        "detail": detail,
        "model": model,
        "kind": "probe",
        "capabilities": found,
    }
    await gw.put_json(db, f"ai.provider.{p}.test", result)
    await audit.record(
        db, "ai.provider.probe", "setting", f"ai.provider.{p}.probe", after={"model": model, **found}, actor=user
    )
    await db.commit()
    return {**result, "effective": (await gw.model_capabilities(db, p)).get(model)}


@router.put("/ai/admin/providers/{provider}/capabilities")
async def put_capabilities(provider: str, body: CapabilitiesIn, db: DB, user: AIAdmin) -> dict[str, Any]:
    """The admin's override of a synced model's capabilities (HB-12), for servers that hide them; audited."""
    from app.ai import capabilities as caps

    p = _provider(provider)
    synced = {str(m.get("id")) for m in (await gw.synced_models(db, p)).get("models") or []}
    if body.model not in synced:
        raise _err(
            422,
            "model_not_synced",
            "Bu model sağlayıcıdan eşitlenmedi; önce Eşitle'ye basın.",
            "This model was not synced from the provider; press Sync first.",
        )
    unknown = [k for k in body.capabilities if k not in caps.CAP_KEYS]
    window = body.capabilities.get("context_window")
    if unknown or (window is not None and (isinstance(window, bool) or not 0 < int(window) <= 10_000_000)):
        raise _err(
            422,
            "invalid_capabilities",
            "Bilinmeyen ya da geçersiz yetenek alanı.",
            "Unknown or invalid capability field.",
            fields=unknown,
        )
    stored = await gw.get_json(db, f"ai.provider.{p}.cap_overrides", {})
    before = dict(stored.get(body.model) or {})
    layer = {k: v for k, v in {**before, **body.capabilities}.items() if k in caps.CAP_KEYS and v is not None}
    if layer:
        stored[body.model] = {**layer, "source": "admin", "checked_at": caps.now_iso()}
    else:
        stored.pop(body.model, None)
    await gw.put_json(db, f"ai.provider.{p}.cap_overrides", stored)
    await audit.record(
        db,
        "ai.provider.capabilities",
        "setting",
        f"ai.provider.{p}.cap_overrides",
        before={"model": body.model, **before},
        after={"model": body.model, **(stored.get(body.model) or {})},
        actor=user,
    )
    await db.commit()
    return {"model": body.model, "capabilities": (await gw.model_capabilities(db, p)).get(body.model)}


async def _speech_adapter_for(db: DB, p: str) -> Any:
    secrets = await gw.provider_secrets(db, p)
    if not has_credentials(p, secrets):
        raise _err(
            409, "no_credentials", "Bu sağlayıcı için anahtar girilmedi.", "No credentials are set for this provider."
        )
    from app.ai.pipeline import TEST_TRANSPORT

    try:
        return speech.make_speech_adapter(
            p, secrets=secrets, config=await gw.provider_config(db, p), timeout_s=30.0, transport=TEST_TRANSPORT[0]
        )
    except ProviderError as exc:
        raise _err(409, "provider_config", "Sağlayıcı ayarları eksik.", str(exc)) from exc


async def _test_speech(db: DB, p: str, model: str, user: User) -> dict[str, Any]:
    """The speech test call: the bundled 5 s Turkish clip, metered as ``test`` with its audio length; the result
    keeps the first 60 characters of the transcript so the admin can judge the Turkish."""
    from app.ai.client import estimate_stt_cost
    from app.ai.voice.assets import CLIP_MIME, test_clip

    adapter = await _speech_adapter_for(db, p)
    started = time.monotonic()
    ok, detail, preview, seconds, tokens = False, "", "", 0.0, (0, 0)
    try:
        out = await adapter.transcribe(test_clip(), CLIP_MIME, model=model, language="tr")
        ok, preview = True, " ".join(out.text.split())[:60]
        seconds = out.duration_s if out.duration_s is not None else 5.15
        tokens = (out.input_tokens, out.output_tokens)
        detail = f"ok ({model}, {seconds:.1f} s)"
    except ProviderError as exc:
        detail = str(exc)
    except Exception as exc:  # noqa: BLE001
        detail = f"could not complete the test call ({type(exc).__name__})"
    detail = redact_keys(detail)[:300]
    prices = (await gw.get_voice(db)).get("prices_per_min") or {}
    cost, version = estimate_stt_cost(p, model, seconds, prices=prices)
    await meter.record(
        user_id=user.id,
        feature="test",
        provider=p,
        model=model,
        modality="audio_in",
        audio_ms=int(round(seconds * 1000)),
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        cost_usd=cost,
        price_version=version,
        latency_ms=int((time.monotonic() - started) * 1000),
        outcome="ok" if ok else "provider_error",
        reason_code=None if ok else "provider_error",
        detail=None if ok else detail,
        guard_verdict="skipped",
    )
    result = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ok": ok,
        "detail": detail,
        "model": model,
        "kind": "stt",
        "transcript_preview": preview,
    }
    await gw.put_json(db, f"ai.provider.{p}.test", result)
    await db.commit()
    return result


# ---------------------------------------------------------------------------------------------- routes


def _labels() -> list[dict[str, str]]:
    return [{"id": f, "label_tr": FEATURE_LABELS[f][0], "label_en": FEATURE_LABELS[f][1]} for f in FEATURES]


async def _routes_out(db: DB) -> dict[str, Any]:
    data = await gw.get_routes(db)
    resolved = {f: await gw.resolve_route(db, f) for f in FEATURES}
    return {
        "default": data["default"],
        "features": data["features"],
        "effective": {f: {**r.route.to_dict(), "source": r.source, "caps": r.caps} for f, r in resolved.items()},
        "feature_list": _labels(),
        "efforts": list(gw.EFFORTS),
        "legacy_model": await gw.legacy_model(db),
    }


@router.get("/ai/admin/routes")
async def get_routes(db: DB, _: AIAdmin) -> dict[str, Any]:
    return await _routes_out(db)


@router.put("/ai/admin/routes")
async def put_routes(body: RoutesIn, db: DB, user: AIAdmin) -> dict[str, Any]:
    """Global default + one route per feature (``null`` = follow the default). Only synced models are accepted."""
    stored = {p: (await gw.synced_models(db, p)).get("models") or [] for p in PROVIDERS}
    synced = {p: {str(m.get("id")) for m in models} for p, models in stored.items()}
    speech_ids = {p: speech.speech_model_ids(models) for p, models in stored.items()}
    capabilities = await gw.all_capabilities(db)  # HB-12: a model that lacks what the feature needs is refused
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    clean: dict[str, Any] = {"default": None, "features": {}}

    def prep(raw: dict[str, Any], where: str) -> dict[str, Any] | None:
        r = {k: v for k, v in raw.items() if v not in (None, "")}
        if not r:
            return None
        feature = where if where in FEATURES else "default"
        for e in gw.validate_route(r, synced, feature=feature, speech=speech_ids, capabilities=capabilities):
            errors.append({**e, "route": where})
        for w in gw.route_warnings(r, feature=feature, capabilities=capabilities):
            warnings.append({**w, "route": where})
        route = gw.Route.from_dict(r)
        return route.to_dict() if route else None

    if body.default:
        clean["default"] = prep(body.default, "default")
    for f, raw in body.features.items():
        if f not in FEATURES:
            errors.append(
                {
                    "route": f,
                    "field": "feature",
                    "code": "unknown_feature",
                    "message_tr": "Bilinmeyen özellik.",
                    "message_en": "Unknown feature.",
                }
            )
            continue
        if raw:
            route = prep(raw, f)
            if route:
                clean["features"][f] = route
    if errors:
        raise _err(
            422, "invalid_routes", "Bazı model seçimleri geçersiz.", "Some model choices are invalid.", errors=errors
        )
    before = await gw.get_routes(db)
    await gw.put_json(db, gw.ROUTES_KEY, clean)
    await audit.record(db, "ai.routes", "setting", gw.ROUTES_KEY, before=before, after=clean, actor=user)
    await db.commit()
    return {**await _routes_out(db), "warnings": warnings}


# ---------------------------------------------------------------------------------------------- usage


def _parse_day(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _err(
            422, "invalid_date", "Tarih YYYY-AA-GG biçiminde olmalı.", "Dates are YYYY-MM-DD.", field=field
        ) from exc
    local = d.replace(tzinfo=meter.TZ) if d.tzinfo is None else d
    return local.astimezone(UTC).replace(tzinfo=None)


@router.get("/ai/admin/usage")
async def usage(
    db: DB,
    _: AIAdmin,
    group: str = Query("day"),
    start: str | None = None,
    end: str | None = None,
    q: str | None = Query(None, max_length=100),
) -> dict[str, Any]:
    if group not in meter.GROUPS:
        raise _err(422, "invalid_group", "Geçersiz gruplama.", "Invalid grouping.", allowed=sorted(meter.GROUPS))
    rows = await meter.report(db, group, start=_parse_day(start, "start"), end=_parse_day(end, "end"), q=q)
    return {"group": group, "rows": rows}


@router.get("/ai/admin/usage/summary")
async def usage_summary(db: DB, _: AIAdmin) -> dict[str, Any]:
    by_feature = await meter.report(db, "feature")
    return {
        "org": await meter.org_state(db),
        "by_feature": by_feature,
        "feature_labels": {f: {"tr": t, "en": e} for f, (t, e) in FEATURE_LABELS.items()},
    }


@router.get("/ai/admin/refusals")
async def refusals(db: DB, _: AIAdmin, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {"rows": await meter.refusals(db, limit=limit)}


# ---------------------------------------------------------------------------------------------- limits


@router.get("/ai/admin/limits")
async def get_limits(db: DB, _: AIAdmin) -> dict[str, Any]:
    return {**await gw.get_limits(db), "org": await meter.org_state(db)}


@router.put("/ai/admin/limits")
async def put_limits(body: LimitsIn, db: DB, user: AIAdmin) -> dict[str, Any]:
    before = await gw.get_limits(db)
    changes = body.model_dump(exclude_none=True)
    for key in ("roles", "users"):
        for k, v in (changes.get(key) or {}).items():
            allowed = {"daily", "monthly", "audio_daily", "audio_monthly"}
            if not isinstance(v, dict) or any(x not in allowed or int(n) < 0 for x, n in v.items()):
                raise _err(
                    422,
                    "invalid_limit",
                    "Sınırlar günlük / aylık (jeton ya da ses saniyesi) ve 0 ya da daha büyük olmalı.",
                    "Limits are daily / monthly (tokens or audio seconds) and >= 0.",
                    field=f"{key}.{k}",
                )
    stored = await gw.get_json(db, gw.LIMITS_KEY, {})
    stored.update(changes)
    await gw.put_json(db, gw.LIMITS_KEY, stored)
    after = await gw.get_limits(db)
    await audit.record(
        db,
        "ai.limits",
        "setting",
        gw.LIMITS_KEY,
        before={k: before[k] for k in changes},
        after={k: after[k] for k in changes},
        actor=user,
    )
    await db.commit()
    return {**after, "org": await meter.org_state(db)}


@router.post("/ai/admin/limits/topup")
async def topup(body: TopupIn, db: DB, user: AIAdmin) -> dict[str, Any]:
    """An audited one-off addition to this month's org budget."""
    if not body.tokens and not body.cost_usd:
        raise _err(422, "empty_topup", "Eklenecek jeton ya da tutar girin.", "Enter tokens or an amount to add.")
    stored = await gw.get_json(db, gw.LIMITS_KEY, {})
    entry = {
        "month": meter.month_key(),
        "tokens": body.tokens,
        "cost_usd": body.cost_usd,
        "by": user.id,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reason": body.reason.strip(),
    }
    stored["topups"] = [*(stored.get("topups") or []), entry][-50:]
    await gw.put_json(db, gw.LIMITS_KEY, stored)
    await audit.record(db, "ai.limits.topup", "setting", gw.LIMITS_KEY, after=entry, actor=user, reason=body.reason)
    await db.commit()
    return {**await gw.get_limits(db), "org": await meter.org_state(db)}


# ---------------------------------------------------------------------------------------------- voice


#: what admins cannot change in v1 (owner 2026-10-18): no stored audio, the transcript is always reviewed
VOICE_FIXED = {
    "retention_days": 0,
    "review_before_send": True,
    "max_seconds_cap": gw.VOICE_MAX_SECONDS,
    "consent": "voice",
}


async def _voice_out(db: DB) -> dict[str, Any]:
    from app.ai.voice.run import load_setup

    rr = await gw.resolve_route(db, "voice_stt")
    setup = await load_setup(db)
    spec = PROVIDERS.get(rr.route.provider)
    return {
        "settings": await gw.get_voice(db),
        "fixed": VOICE_FIXED,
        "route": {
            **rr.route.to_dict(),
            "source": rr.source,
            "label_tr": spec.label_tr if spec else None,
            "label_en": spec.label_en if spec else None,
            "usable": setup.primary is not None,
            "transfer_ok": bool(setup.primary and setup.primary.transfer_ok),
        },
        "providers": [p for p, sp in PROVIDERS.items() if "stt" in sp.capabilities],
        "languages": list(gw.VOICE_LANGUAGES),
        "vocabulary_options": ["catalog", "off"],
        "live_captions_options": ["on_device", "off"],
    }


@router.get("/ai/admin/voice")
async def get_voice(db: DB, _: AIAdmin) -> dict[str, Any]:
    return await _voice_out(db)


@router.put("/ai/admin/voice")
async def put_voice(body: VoiceIn, db: DB, user: AIAdmin) -> dict[str, Any]:
    """Voice settings, shared by every admin (one ``settings`` row ``ai.voice``); audited ``ai.voice``."""
    changes = body.model_dump(exclude_none=True)
    checks = (
        ("language", gw.VOICE_LANGUAGES, "Dil tr ya da en olmalı.", "The language is tr or en."),
        ("vocabulary", ("catalog", "off"), "Sözlük catalog ya da off olmalı.", "Vocabulary is catalog or off."),
        ("live_captions", ("on_device", "off"), "Canlı altyazı on_device ya da off olmalı.", "on_device or off."),
    )
    for fld, allowed, tr, en in checks:
        if fld in changes and changes[fld] not in allowed:
            raise _err(422, f"invalid_{fld}", tr, en, field=fld)
    for key, price in (changes.get("prices_per_min") or {}).items():
        prov = key.split(":", 1)[0]
        if ":" not in key or prov not in PROVIDERS or "stt" not in PROVIDERS[prov].capabilities or not 0 <= price <= 10:
            raise _err(
                422,
                "invalid_price",
                "Fiyat 'sağlayıcı:model' için dakika başına 0–10 USD olmalı.",
                "A price is 0–10 USD per minute for 'provider:model'.",
                field=f"prices_per_min.{key}",
            )
    before = await gw.get_voice(db)
    stored = await gw.get_json(db, gw.VOICE_KEY, {})
    stored.update(changes)
    await gw.put_json(db, gw.VOICE_KEY, stored)
    after = await gw.get_voice(db)
    await audit.record(db, "ai.voice", "setting", gw.VOICE_KEY, before=before, after=after, actor=user)
    await db.commit()
    return await _voice_out(db)


# ---------------------------------------------------------------------------------------------- guardrails


@router.get("/ai/admin/guardrails")
async def get_guardrails(db: DB, _: AIAdmin) -> dict[str, Any]:
    return await gw.get_guardrails(db)


@router.put("/ai/admin/guardrails")
async def put_guardrails(body: GuardrailsIn, db: DB, user: AIAdmin) -> dict[str, Any]:
    before = await gw.get_guardrails(db)
    after = {**before, **body.model_dump(exclude_none=True)}
    await gw.put_json(db, gw.GUARD_KEY, after)
    await audit.record(db, "ai.guardrails", "setting", gw.GUARD_KEY, before=before, after=after, actor=user)
    await db.commit()
    return after


class GuardCheckIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    feature: str = "chat"
    surface: str = "user"


@router.post("/ai/admin/guardrails/check")
async def guard_check(body: GuardCheckIn, _: AIAdmin) -> dict[str, Any]:
    """Test bench: the deterministic guard's verdict on a text (dry run: no model call, no usage row)."""
    from app.ai import guardrails as g

    if body.surface == "upload":
        cleaned, findings = g.neutralize_upload(body.text)
        return {
            "surface": "upload",
            "allowed": True,
            "result": "remove" if g.REMOVED_MARK in cleaned else ("mark" if findings else "keep"),
            "reason_code": findings[0].code if findings else None,
            "rules": [f.rule for f in findings],
            "cleaned": cleaned[:2000],
        }
    v = g.check_user_input(body.text, body.feature if body.feature in FEATURES else "chat")
    tr, en = g.message_for(v.reason_code) if v.reason_code else ("", "")
    return {
        "surface": "user",
        "allowed": v.allowed,
        "result": "allow" if v.allowed else "refuse",
        "reason_code": v.reason_code,
        "rules": [v.rule] if v.rule else [],
        "unclear": v.unclear,
        "message_tr": tr,
        "message_en": en,
    }


@router.post("/ai/admin/redteam")
async def redteam(_: AIAdmin) -> dict[str, Any]:
    """Run the shipped red-team guard corpus (TR + EN) through the deterministic guardrails (no model call)."""
    cases = load_cases(GUARD_CASES_PATH)
    return summarize_guard(score_guard_cases(cases))


# ---------------------------------------------------------------------------------------------- my usage


@router.get("/ai/me/usage")
async def my_usage(db: DB, user: CurrentUser) -> dict[str, Any]:
    """The caller's own usage today / this month, their limits and the banner state (``ok`` / ``soft`` / ``hard`` /
    ``org_soft`` / ``none``)."""
    state = await meter.user_state(db, user)
    return {**state, "user_id": user.id, "by_feature": await meter.report(db, "feature", user_id=user.id)}


__all__ = ["router"]
