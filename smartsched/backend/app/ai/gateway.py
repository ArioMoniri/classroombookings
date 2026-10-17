"""AI gateway configuration: providers, keys, synced models, per-feature routes, limits, guardrails, transfer records
(wave 3 W3-AI; settings keys ``ai.*``; research R-AI-01…10).

Everything lives in the ``settings`` table, so every call path reads one table:

==============================================  ============================================================
``anthropic_api_key``                           the Anthropic key (historic row, encrypted; env fallback)
``ai.provider.<p>.<secret>``                    other providers' secrets (encrypted, ``is_secret``; never returned)
``ai.provider.<p>.config``                      plain config JSON (``base_url``, ``region``, ``enabled``)
``ai.provider.<p>.models``                      synced models ``{"fetched_at", "models": [...], "error"}``
``ai.provider.<p>.test``                        the last test call ``{"at", "ok", "detail", "model"}``
``ai.provider.<p>.transfer``                    the KVKK transfer record (region, retention, mechanism, dates)
``ai.routes``                                   ``{"default": Route, "features": {feature: Route}}``
``ai.limits``                                   org budget, per-user / per-role / per-user-override limits
``ai.guardrails``                               guard switches
==============================================  ============================================================

With nothing configured the gateway behaves as before the gateway: provider ``anthropic``, the model from
``anthropic_model`` (``claude-opus-5-5``), no limits; without a key nothing is sent (``AIConfigError``).
Every change is audited by the admin API (``app/api/v1/ai_admin.py``).
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import FEATURES
from app.ai.providers import PROVIDERS, has_credentials
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models import Setting
from app.services import settings_service as ss

DEFAULT_PROVIDER = "anthropic"
ROUTES_KEY = "ai.routes"
LIMITS_KEY = "ai.limits"
GUARD_KEY = "ai.guardrails"
EFFORTS = ("low", "medium", "high", "xhigh", "max")

#: features whose requests can carry personal data (names in files, chat about people): a provider abroad needs a
#: KVKK transfer record for them (R-AI-03); the Anthropic intake path keeps its own sign-off (``app/ai/policy.py``)
PERSONAL_FEATURES = frozenset({"intake", "vision", "chat", "rules", "booking_nl"})
KVKK_MECHANISMS = ("adequacy", "standard_contract", "binding_rules", "explicit_consent", "incidental", "domestic")

#: per-feature caps (OWASP LLM10 unbounded consumption): applied when the route does not set its own
DEFAULT_CAPS: dict[str, dict[str, Any]] = {
    "rules": {"max_tokens": 32000, "max_tool_rounds": 4, "timeout_s": 180},
    "chat": {"max_tokens": 32000, "max_tool_rounds": 12, "timeout_s": 180},
    "intake": {"max_tokens": 64000, "max_tool_rounds": 40, "timeout_s": 300},
    "vision": {"max_tokens": 64000, "max_tool_rounds": 20, "timeout_s": 300},
    "explain": {"max_tokens": 16000, "max_tool_rounds": 4, "timeout_s": 120},
    "booking_nl": {"max_tokens": 8000, "max_tool_rounds": 4, "timeout_s": 60},
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
    cfg = await get_json(session, f"ai.provider.{provider}.config", {})
    spec = PROVIDERS[provider]
    if spec.default_base_url and not cfg.get("base_url"):
        cfg["base_url"] = spec.default_base_url
    cfg.setdefault("enabled", provider == DEFAULT_PROVIDER or bool(cfg))
    return cfg


async def synced_models(session: AsyncSession, provider: str) -> dict[str, Any]:
    return await get_json(session, f"ai.provider.{provider}.models", {"fetched_at": None, "models": []})


async def store_synced_models(session: AsyncSession, provider: str, models: list[dict[str, Any]], error: str | None) -> dict[str, Any]:
    previous = await synced_models(session, provider)
    record = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # a failed sync keeps the last good list (the UI shows the error next to it)
        "models": models if error is None else previous.get("models") or [],
        "error": error,
    }
    await put_json(session, f"ai.provider.{provider}.models", record)
    return record


def is_local_url(url: str | None) -> bool:
    """A loopback / private address: the data does not leave the institution (no transfer record needed)."""
    host = urlparse(url or "").hostname or ""
    if host in {"localhost"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


async def transfer_record(session: AsyncSession, provider: str) -> dict[str, Any]:
    return await get_json(session, f"ai.provider.{provider}.transfer", {})


def transfer_ok(provider: str, config: dict[str, Any], record: dict[str, Any]) -> bool:
    """Whether personal data may go to ``provider``: a local server, or a transfer record with a KVKK mechanism.
    The historic Anthropic path is governed by the intake sign-off (``app/ai/policy.py``) and stays as it was."""
    if provider == DEFAULT_PROVIDER:
        return True
    if provider == "openai_compatible" and is_local_url(config.get("base_url")):
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
    if feature == "vision" and feat is None:
        feat = Route.from_dict(data["features"].get("intake"))  # scans follow intake unless set
    if feat is not None and feat.model:
        return ResolvedRoute(feature, feat, "feature", caps)
    default = Route.from_dict(data["default"])
    if default is not None and default.model:
        return ResolvedRoute(feature, default, "default", caps)
    return ResolvedRoute(feature, Route(provider=DEFAULT_PROVIDER, model=await legacy_model(session)), "legacy", caps)


async def all_routes(session: AsyncSession) -> dict[str, ResolvedRoute]:
    return {f: await resolve_route(session, f) for f in (*FEATURES, "other", "guard")}


async def provider_usable(session: AsyncSession, provider: str) -> bool:
    cfg = await provider_config(session, provider)
    if provider != DEFAULT_PROVIDER and not cfg.get("enabled", True):
        return False
    return has_credentials(provider, await provider_secrets(session, provider))


def validate_route(route: dict[str, Any], synced: dict[str, set[str]]) -> list[dict[str, str]]:
    """Errors of a route change: unknown provider, a model that was not synced, an invalid effort / cap."""
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
        if not model:
            err(model_field, "model_required", "Model seçin.", "Choose a model.")
        elif model not in synced.get(str(prov), set()):
            err(
                model_field,
                "model_not_synced",
                "Bu model sağlayıcıdan eşitlenmedi; önce Sağlayıcılar sekmesinde Eşitle'ye basın.",
                "This model was not synced from the provider; press Sync on the Providers tab first.",
            )
    if route.get("effort") not in (None, "", *EFFORTS):
        err("effort", "invalid_effort", "Geçersiz çaba düzeyi.", "Invalid effort level.")
    temp = route.get("temperature")
    if temp not in (None, "") and not (isinstance(temp, int | float) and 0 <= float(temp) <= 2):
        err("temperature", "invalid_temperature", "Sıcaklık 0 ile 2 arasında olmalı.", "Temperature must be between 0 and 2.")
    for cap, hi in (("max_tokens", 128000), ("timeout_s", 900), ("max_tool_rounds", 100)):
        v = route.get(cap)
        if v not in (None, "") and not (isinstance(v, int | float) and 0 < float(v) <= hi):
            err(cap, f"invalid_{cap}", f"{cap} 1 ile {hi} arasında olmalı.", f"{cap} must be between 1 and {hi}.")
    return errors


# ---------------------------------------------------------------------------------------------- limits / guards


async def get_limits(session: AsyncSession) -> dict[str, Any]:
    data = await get_json(session, LIMITS_KEY, {})
    return {**json.loads(json.dumps(DEFAULT_LIMITS)), **data}


async def get_guardrails(session: AsyncSession) -> dict[str, Any]:
    data = await get_json(session, GUARD_KEY, {})
    return {**DEFAULT_GUARDRAILS, **{k: bool(v) for k, v in data.items() if k in DEFAULT_GUARDRAILS}}


def masked(value: str | None) -> dict[str, Any]:
    return {"set": bool(value), "masked": mask_secret(value) if value else None}


__all__ = [
    "DEFAULT_CAPS",
    "DEFAULT_GUARDRAILS",
    "DEFAULT_LIMITS",
    "DEFAULT_PROVIDER",
    "EFFORTS",
    "GUARD_KEY",
    "KVKK_MECHANISMS",
    "LIMITS_KEY",
    "PERSONAL_FEATURES",
    "ROUTES_KEY",
    "ResolvedRoute",
    "Route",
    "all_routes",
    "get_guardrails",
    "get_json",
    "get_limits",
    "get_routes",
    "is_local_url",
    "legacy_model",
    "masked",
    "provider_config",
    "provider_secrets",
    "provider_usable",
    "put_json",
    "resolve_route",
    "set_provider_secret",
    "store_synced_models",
    "synced_models",
    "transfer_ok",
    "transfer_record",
    "validate_route",
]
