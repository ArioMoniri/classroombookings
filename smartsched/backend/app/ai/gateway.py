"""AI gateway configuration: providers, keys, synced models, per-feature routes, limits, guardrails, transfer records
(wave 3 W3-AI; settings keys ``ai.*``; research R-AI-01…10).

Everything lives in the ``settings`` table, so every call path reads one table:

==============================================  ============================================================
``anthropic_api_key``                           the Anthropic key (historic row, encrypted; env fallback)
``ai.provider.<p>.<secret>``                    other providers' secrets (encrypted, ``is_secret``; never returned)
``ai.provider.<p>.config``                      plain config JSON (``base_url``, ``region``, ``enabled``)
``ai.provider.<p>.models``                      synced models ``{"fetched_at", "models": [...], "error"}``; each
                                                model carries its sync-time ``capabilities`` (HB-12)
``ai.provider.<p>.probe``                       probe results per model (``Test`` with ``probe=true``; HB-12)
``ai.provider.<p>.cap_overrides``               the admin's capability overrides per model (audited; HB-12)
``ai.provider.<p>.test``                        the last test call ``{"at", "ok", "detail", "model"}``
``ai.provider.<p>.transfer``                    the KVKK transfer record (region, retention, mechanism, dates)
``ai.routes``                                   ``{"default": Route, "features": {feature: Route}}``
``ai.limits``                                   org budget, per-user / per-role / per-user-override limits
``ai.guardrails``                               guard switches
``ai.voice``                                    voice input settings (VO-03: on/off, language, clip length,
                                                vocabulary, live captions, per-minute prices)
==============================================  ============================================================

With nothing configured the gateway behaves as before the gateway: provider ``anthropic``, the model from
``anthropic_model`` (``claude-opus-5-5``), no limits; without a key nothing is sent (``AIConfigError``).
Every change is audited by the admin API (``app/api/v1/ai_admin.py``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import FEATURES, VOICE_FEATURES
from app.ai.providers import PROVIDERS, has_credentials
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models import Setting
from app.services import settings_service as ss

DEFAULT_PROVIDER = "anthropic"
ROUTES_KEY = "ai.routes"
LIMITS_KEY = "ai.limits"
GUARD_KEY = "ai.guardrails"
VOICE_KEY = "ai.voice"
EFFORTS = ("low", "medium", "high", "xhigh", "max")

#: features whose requests can carry personal data (names in files, chat about people): a provider abroad needs a
#: KVKK transfer record for them (R-AI-03); the Anthropic intake path keeps its own sign-off (``app/ai/policy.py``)
#: a voice recording is personal data (KVKK; research 2026-10-17-voice-ai.md §2.5), so ``voice_stt`` is one of them
#: the helper reads names and booking data through its actions (HB-06), so it is one of them too
PERSONAL_FEATURES = frozenset({"intake", "vision", "chat", "rules", "booking_nl", "voice_stt", "helper"})
KVKK_MECHANISMS = ("adequacy", "standard_contract", "binding_rules", "explicit_consent", "incidental", "domestic")

#: per-feature caps (OWASP LLM10 unbounded consumption): applied when the route does not set its own
DEFAULT_CAPS: dict[str, dict[str, Any]] = {
    "rules": {"max_tokens": 32000, "max_tool_rounds": 4, "timeout_s": 180},
    "chat": {"max_tokens": 32000, "max_tool_rounds": 12, "timeout_s": 180},
    "intake": {"max_tokens": 64000, "max_tool_rounds": 40, "timeout_s": 300},
    "vision": {"max_tokens": 64000, "max_tool_rounds": 20, "timeout_s": 300},
    "explain": {"max_tokens": 16000, "max_tool_rounds": 4, "timeout_s": 120},
    "booking_nl": {"max_tokens": 8000, "max_tool_rounds": 4, "timeout_s": 60},
    #: the in-app helper (HB-06): short answers, at most 4 model calls per turn, a minute per call
    "helper": {"max_tokens": 4000, "max_tool_rounds": 4, "timeout_s": 60},
    #: one clip: at most 120 s and 5 MB, answered within 60 s
    "voice_stt": {"timeout_s": 60, "max_audio_s": 120, "max_bytes": 5_000_000},
}

DEFAULT_GUARDRAILS: dict[str, Any] = {
    "scope_check": True,
    "injection_check": True,
    "model_scope_check": False,
    "upload_neutralize": True,
    "output_check": True,
    "rate_limit": True,
}

DEFAULT_LIMITS: dict[str, Any] = {
    #: 0 = no budget / no limit
    "org_monthly_tokens": 0,
    "org_monthly_cost_usd": 0.0,
    "user_daily_tokens": 0,
    "user_monthly_tokens": 0,
    #: role code -> {"daily": n, "monthly": n}
    "roles": {},
    #: user id (string) -> {"daily": n, "monthly": n}
    "users": {},
    "soft_pct": 80,
    #: user ids that get the alerts; empty = every active administrator (role ADMIN)
    "alert_recipients": [],
    "requests_per_minute": 30,
    "max_concurrent": 2,
    #: audited one-off additions to this month's org budget: [{"month", "tokens", "cost_usd", "by", "at", "reason"}]
    "topups": [],
    #: voice input (VO-02), in seconds of audio: 10 min a day and 100 min a month per person by default; a role or a
    #: person can be raised with ``audio_daily`` / ``audio_monthly`` in ``roles`` / ``users``; 0 = no limit
    "user_daily_audio_s": 600,
    "user_monthly_audio_s": 6000,
    "org_monthly_audio_s": 0,
    #: the quota chain (HB-10; research §5.9), all monthly and optional: a unit without an entry draws from the org
    #: budget unrestricted. ``faculties``: faculty id -> {monthly_tokens, monthly_cost_usd, managers, show_people};
    #: ``departments``: programme id -> {monthly_tokens, monthly_cost_usd} (their sum fits the faculty's);
    #: ``features``: feature -> cap; ``unassigned``: accounts without a faculty; ``strict``: the faculties may not
    #: allocate more than the org budget (otherwise overbooking is a warning)
    "faculties": {},
    "departments": {},
    "features": {},
    "unassigned": {},
    "strict": False,
}

#: hard ceiling of one clip (owner 2026-10-18); the admin may only lower it
VOICE_MAX_SECONDS = 120
VOICE_LANGUAGES = ("tr", "en")
DEFAULT_VOICE: dict[str, Any] = {
    "enabled": False,
    #: the default spoken language (the UI sends its locale; Turkish first)
    "language": "tr",
    "max_seconds": VOICE_MAX_SECONDS,
    #: ``catalog``: room, building and course codes bias the recogniser; never people's names. ``off``: nothing
    "vocabulary": "catalog",
    #: ``on_device``: the browser may show interim captions only from its on-device recogniser; ``off``: none
    "live_captions": "on_device",
    #: USD per audio minute by ``provider:model`` (overrides ``app.ai.client.STT_PRICE_TABLE``)
    "prices_per_min": {},
}


@dataclass
class Route:
    provider: str = DEFAULT_PROVIDER
    model: str = ""
    effort: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_s: float | None = None
    max_tool_rounds: int | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Route | None:
        if not isinstance(data, dict) or not data.get("provider"):
            return None
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def fallback(self) -> Route | None:
        if not self.fallback_provider or not self.fallback_model:
            return None
        return Route(
            provider=self.fallback_provider,
            model=self.fallback_model,
            effort=self.effort,
            max_tokens=self.max_tokens,
            timeout_s=self.timeout_s,
            max_tool_rounds=self.max_tool_rounds,
        )


@dataclass
class ResolvedRoute:
    feature: str
    route: Route
    #: "feature" | "default" | "legacy" (nothing configured: anthropic + anthropic_model)
    source: str
    caps: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------- raw settings


async def _get_raw(session: AsyncSession, key: str) -> str | None:
    row = await session.get(Setting, key)
    return row.value if row is not None else None


async def _put_raw(session: AsyncSession, key: str, value: str | None, *, secret: bool = False) -> None:
    row = await session.get(Setting, key)
    stored = None if value in (None, "") else (encrypt_secret(str(value)) if secret else str(value))
    if row is None:
        session.add(Setting(key=key, value=stored, is_secret=secret))
    else:
        row.value, row.is_secret = stored, secret
    await session.flush()


async def get_json(session: AsyncSession, key: str, default: Any) -> Any:
    raw = await _get_raw(session, key)
    if not raw:
        return json.loads(json.dumps(default))
    try:
        data = json.loads(raw)
    except ValueError:
        return json.loads(json.dumps(default))
    return data if isinstance(data, type(default)) else json.loads(json.dumps(default))


async def put_json(session: AsyncSession, key: str, value: Any) -> None:
    await _put_raw(session, key, json.dumps(value, ensure_ascii=False, sort_keys=True))


# ---------------------------------------------------------------------------------------------- providers


def _secret_key(provider: str, name: str) -> str:
    if provider == "anthropic" and name == "api_key":
        return "anthropic_api_key"
    return f"ai.provider.{provider}.{name}"


async def provider_secrets(session: AsyncSession, provider: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in PROVIDERS[provider].secrets:
        key = _secret_key(provider, name)
        if key == "anthropic_api_key":
            value = (await ss.get_value(session, key) or "").strip()
        else:
            raw = await _get_raw(session, key)
            try:
                value = decrypt_secret(raw).strip() if raw else ""
            except ValueError:
                value = ""
        if value:
            out[name] = value
    return out


async def set_provider_secret(session: AsyncSession, provider: str, name: str, value: str | None) -> None:
    if name not in PROVIDERS[provider].secrets:
        raise ValueError(f"{provider} has no secret {name!r}")
    key = _secret_key(provider, name)
    if key == "anthropic_api_key":
        spec_row = await session.get(Setting, key)
        stored = encrypt_secret(value) if value else None
        if spec_row is None:
            session.add(Setting(key=key, value=stored, is_secret=True))
        else:
            spec_row.value, spec_row.is_secret = stored, True
        await session.flush()
        return
    await _put_raw(session, key, value or None, secret=True)


async def provider_config(session: AsyncSession, provider: str) -> dict[str, Any]:
    cfg: dict[str, Any] = dict(await get_json(session, f"ai.provider.{provider}.config", {}))
    spec = PROVIDERS[provider]
    if spec.default_base_url and not cfg.get("base_url"):
        cfg["base_url"] = spec.default_base_url
    cfg.setdefault("enabled", provider == DEFAULT_PROVIDER or bool(cfg))
    return cfg


async def synced_models(session: AsyncSession, provider: str) -> dict[str, Any]:
    return dict(await get_json(session, f"ai.provider.{provider}.models", {"fetched_at": None, "models": []}))


async def store_synced_models(
    session: AsyncSession, provider: str, models: list[dict[str, Any]], error: str | None
) -> dict[str, Any]:
    previous = await synced_models(session, provider)
    record = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # a failed sync keeps the last good list (the UI shows the error next to it)
        "models": models if error is None else previous.get("models") or [],
        "error": error,
    }
    await put_json(session, f"ai.provider.{provider}.models", record)
    return record


def is_local_url(url: str | None, *, resolver: Any | None = None) -> bool:
    """Every address the host resolves to is loopback / private: the data does not leave the institution (no transfer
    record needed). Decided from the **resolved addresses**, never from the name (HB-13, the KVKK finding of the
    architecture doc §1.4): ``gpu.local`` resolving to a public address is not local, ``llm.uni.edu.tr`` resolving
    to 10.x is. A name that does not resolve is not local (the record is then required)."""
    from app.ai.providers.url_guard import resolved_local

    return resolved_local(url, resolver=resolver)


async def transfer_record(session: AsyncSession, provider: str) -> dict[str, Any]:
    return dict(await get_json(session, f"ai.provider.{provider}.transfer", {}))


def transfer_ok(provider: str, config: dict[str, Any], record: dict[str, Any], *, local: bool | None = None) -> bool:
    """Whether personal data may go to ``provider``: a local server (by its resolved addresses; ``local`` when the
    caller already resolved it off the event loop), or a transfer record with a KVKK mechanism. The historic
    Anthropic path is governed by the intake sign-off (``app/ai/policy.py``) and stays as it was."""
    if provider == DEFAULT_PROVIDER:
        return True
    if provider == "openai_compatible" and (is_local_url(config.get("base_url")) if local is None else local):
        return True
    return bool(record.get("kvkk_mechanism")) and record.get("kvkk_mechanism") != "none"


# ---------------------------------------------------------------------------------------------- routes


async def get_routes(session: AsyncSession) -> dict[str, Any]:
    data = await get_json(session, ROUTES_KEY, {})
    return {"default": data.get("default") or None, "features": dict(data.get("features") or {})}


async def legacy_model(session: AsyncSession) -> str:
    from app.ai.client import DEFAULT_MODEL

    return (await ss.get_value(session, "anthropic_model") or "").strip() or DEFAULT_MODEL


async def resolve_route(session: AsyncSession, feature: str) -> ResolvedRoute:
    data = await get_routes(session)
    caps = dict(DEFAULT_CAPS.get(feature, DEFAULT_CAPS["chat"]))
    feat = Route.from_dict(data["features"].get(feature)) if feature in FEATURES else None
    if feature in VOICE_FEATURES:  # a speech route of its own; the (Claude) text default cannot transcribe
        if feat is not None and feat.model:
            return ResolvedRoute(feature, feat, "feature", caps)
        return ResolvedRoute(feature, Route(provider="", model=""), "none", caps)
    if feature == "vision" and feat is None:
        feat = Route.from_dict(data["features"].get("intake"))  # scans follow intake unless set
    if feat is not None and feat.model:
        return ResolvedRoute(feature, feat, "feature", caps)
    default = Route.from_dict(data["default"])
    if default is not None and default.model:
        return ResolvedRoute(feature, default, "default", caps)
    return ResolvedRoute(feature, Route(provider=DEFAULT_PROVIDER, model=await legacy_model(session)), "legacy", caps)


async def all_routes(session: AsyncSession) -> dict[str, ResolvedRoute]:
    """The text routes the chat / tools client binds (voice routes are resolved by :mod:`app.ai.voice.run`)."""
    text_features = [f for f in FEATURES if f not in VOICE_FEATURES]
    return {f: await resolve_route(session, f) for f in (*text_features, "other", "guard")}


async def provider_usable(session: AsyncSession, provider: str) -> bool:
    cfg = await provider_config(session, provider)
    if provider != DEFAULT_PROVIDER and not cfg.get("enabled", True):
        return False
    if provider in ("vertex", "google_stt") and not cfg.get("project_id"):
        return False
    return has_credentials(provider, await provider_secrets(session, provider))


_NOT_SPEECH = (
    "Bu model sesi yazıya dökemez; ses için konuşmayı yazıya döken bir model seçin (ör. gpt-transcribe, Chirp 3, "
    "Nova-3).",
    "This model cannot transcribe speech; choose a speech-to-text model (e.g. gpt-transcribe, Chirp 3, Nova-3).",
)


async def model_capabilities(session: AsyncSession, provider: str) -> dict[str, dict[str, Any]]:
    """Effective capabilities per synced model of ``provider``: sync ⊕ probe ⊕ admin override (HB-12)."""
    from app.ai import capabilities as caps

    synced = await synced_models(session, provider)
    probes = await get_json(session, f"ai.provider.{provider}.probe", {})
    overrides = await get_json(session, f"ai.provider.{provider}.cap_overrides", {})
    out: dict[str, dict[str, Any]] = {}
    for m in synced.get("models") or []:
        mid = str(m.get("id") or "")
        if not mid:
            continue
        sync_layer = m.get("capabilities")
        if not isinstance(sync_layer, dict) and m.get("context_window"):
            sync_layer = {"context_window": m.get("context_window"), "source": "provider"}
        if PROVIDERS[provider].claude and not isinstance(sync_layer, dict):
            sync_layer = caps.claude(m.get("context_window"))
        out[mid] = caps.merge(sync_layer, probes.get(mid), overrides.get(mid))
    return out


async def all_capabilities(session: AsyncSession) -> dict[str, dict[str, dict[str, Any]]]:
    return {p: await model_capabilities(session, p) for p in PROVIDERS if "text" in PROVIDERS[p].capabilities}


def _route_models(route: dict[str, Any]) -> list[tuple[str, str, str]]:
    out = []
    for prov_field, model_field in (("provider", "model"), ("fallback_provider", "fallback_model")):
        prov, model = route.get(prov_field), route.get(model_field)
        if prov in PROVIDERS and model:
            out.append((model_field, str(prov), str(model)))
    return out


def route_warnings(
    route: dict[str, Any], *, feature: str | None, capabilities: dict[str, dict[str, dict[str, Any]]] | None
) -> list[dict[str, str]]:
    """Warnings of a route (HB-12): a capability the feature needs is unknown (probe it) or degrades the feature."""
    from app.ai import capabilities as caps

    out: list[dict[str, str]] = []
    if capabilities is None or feature is None:
        return out
    for fld, prov, model in _route_models(route):
        _, warns = caps.route_issues(feature, (capabilities.get(prov) or {}).get(model))
        out.extend({**w, "field": fld} for w in warns)
    return out


def validate_route(
    route: dict[str, Any],
    synced: dict[str, set[str]],
    *,
    feature: str | None = None,
    speech: dict[str, set[str]] | None = None,
    capabilities: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> list[dict[str, str]]:
    """Errors of a route change: unknown provider, a model that was not synced, an invalid effort / cap. With
    ``feature`` and ``speech`` (synced model ids whose modalities include ``stt``, per provider): a voice feature
    accepts only speech models (``model_not_speech``), a text feature no speech model (``model_not_text``). With
    ``capabilities`` (provider -> model -> record, :func:`all_capabilities`; HB-12) a model that lacks what the
    feature needs is refused (``model_lacks_capability``, ``context_too_small``); unknown is only a warning
    (:func:`route_warnings`)."""
    errors: list[dict[str, str]] = []

    def err(fld: str, code: str, tr: str, en: str) -> None:
        errors.append({"field": fld, "code": code, "message_tr": tr, "message_en": en})

    for prov_field, model_field in (("provider", "model"), ("fallback_provider", "fallback_model")):
        prov = route.get(prov_field)
        model = route.get(model_field)
        if not prov and prov_field == "fallback_provider":
            continue
        if prov not in PROVIDERS:
            err(prov_field, "unknown_provider", "Bilinmeyen sağlayıcı.", "Unknown provider.")
            continue
        voice = feature in VOICE_FEATURES
        if not model:
            err(model_field, "model_required", "Model seçin.", "Choose a model.")
        elif speech is not None and voice and "stt" not in PROVIDERS[str(prov)].capabilities:
            err(model_field, "model_not_speech", *_NOT_SPEECH)
        elif model not in synced.get(str(prov), set()):
            err(
                model_field,
                "model_not_synced",
                "Bu model sağlayıcıdan eşitlenmedi; önce Sağlayıcılar sekmesinde Eşitle'ye basın.",
                "This model was not synced from the provider; press Sync on the Providers tab first.",
            )
        elif feature is not None and speech is not None:
            is_speech = model in speech.get(str(prov), set())
            if voice and not is_speech:
                err(model_field, "model_not_speech", *_NOT_SPEECH)
            elif not voice and (is_speech or "text" not in PROVIDERS[str(prov)].capabilities):
                err(
                    model_field,
                    "model_not_text",
                    "Bu bir konuşmayı yazıya dökme modeli; bu özellik için bir metin modeli seçin.",
                    "This is a speech-to-text model; choose a text model for this feature.",
                )
    if route.get("effort") not in (None, "", *EFFORTS):
        err("effort", "invalid_effort", "Geçersiz çaba düzeyi.", "Invalid effort level.")
    temp = route.get("temperature")
    if temp not in (None, "") and not (isinstance(temp, int | float) and 0 <= float(temp) <= 2):
        err(
            "temperature",
            "invalid_temperature",
            "Sıcaklık 0 ile 2 arasında olmalı.",
            "Temperature must be between 0 and 2.",
        )
    for cap, hi in (("max_tokens", 128000), ("timeout_s", 900), ("max_tool_rounds", 100)):
        v = route.get(cap)
        if v not in (None, "") and not (isinstance(v, int | float) and 0 < float(v) <= hi):
            err(cap, f"invalid_{cap}", f"{cap} 1 ile {hi} arasında olmalı.", f"{cap} must be between 1 and {hi}.")
    if capabilities is not None and feature not in (None, *VOICE_FEATURES):
        from app.ai import capabilities as caps

        bad_fields = {e["field"] for e in errors}
        for fld, prov, model in _route_models(route):
            if fld in bad_fields:
                continue
            found, _ = caps.route_issues(feature, (capabilities.get(prov) or {}).get(model))
            errors.extend({**e, "field": fld} for e in found)
    return errors


# ---------------------------------------------------------------------------------------------- limits / guards


async def get_limits(session: AsyncSession) -> dict[str, Any]:
    data = await get_json(session, LIMITS_KEY, {})
    return {**json.loads(json.dumps(DEFAULT_LIMITS)), **data}


async def get_voice(session: AsyncSession) -> dict[str, Any]:
    """The voice settings (``ai.voice``) over the defaults; ``max_seconds`` never above the 120 s ceiling."""
    data = await get_json(session, VOICE_KEY, {})
    out = {**json.loads(json.dumps(DEFAULT_VOICE)), **{k: v for k, v in data.items() if k in DEFAULT_VOICE}}
    try:
        out["max_seconds"] = max(5, min(int(out["max_seconds"]), VOICE_MAX_SECONDS))
    except (TypeError, ValueError):
        out["max_seconds"] = VOICE_MAX_SECONDS
    if out["language"] not in VOICE_LANGUAGES:
        out["language"] = DEFAULT_VOICE["language"]
    if not isinstance(out["prices_per_min"], dict):
        out["prices_per_min"] = {}
    out["enabled"] = bool(out["enabled"])
    return out


async def get_guardrails(session: AsyncSession) -> dict[str, Any]:
    data = await get_json(session, GUARD_KEY, {})
    return {**DEFAULT_GUARDRAILS, **{k: bool(v) for k, v in data.items() if k in DEFAULT_GUARDRAILS}}


def masked(value: str | None) -> dict[str, Any]:
    return {"set": bool(value), "masked": mask_secret(value) if value else None}


__all__ = [
    "DEFAULT_CAPS",
    "DEFAULT_VOICE",
    "DEFAULT_GUARDRAILS",
    "DEFAULT_LIMITS",
    "DEFAULT_PROVIDER",
    "EFFORTS",
    "GUARD_KEY",
    "KVKK_MECHANISMS",
    "LIMITS_KEY",
    "PERSONAL_FEATURES",
    "ROUTES_KEY",
    "VOICE_KEY",
    "VOICE_LANGUAGES",
    "VOICE_MAX_SECONDS",
    "ResolvedRoute",
    "Route",
    "all_capabilities",
    "all_routes",
    "get_guardrails",
    "get_json",
    "get_limits",
    "get_voice",
    "get_routes",
    "is_local_url",
    "legacy_model",
    "masked",
    "model_capabilities",
    "provider_config",
    "provider_secrets",
    "provider_usable",
    "put_json",
    "resolve_route",
    "route_warnings",
    "set_provider_secret",
    "store_synced_models",
    "synced_models",
    "transfer_ok",
    "transfer_record",
    "validate_route",
]
