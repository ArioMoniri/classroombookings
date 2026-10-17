"""The AI gateway's client: one provider-neutral facade over the provider adapters (``app/ai/providers``; the
official ``anthropic`` SDK is the default adapter).

Wave 3 W3-AI: :func:`get_client` resolves the feature's route (provider + model + effort + caps + fallback,
``app/ai/gateway.py``), binds a :class:`~app.ai.pipeline.GatewayContext` and every call then runs the pipeline of
``app/ai/pipeline.py`` (transfer basis, rate / concurrency, input guard, limits, caps, output guard, one ``ai_usage``
row per outcome). An ``AIClient`` built directly (tests, the live smoke test) talks to Anthropic exactly as before,
without metering.

* The key comes from the encrypted settings table (``anthropic_api_key``) or from a transient key
  passed by the caller (settings "test connection"); it is never logged.
* The model comes from settings (``anthropic_model``) with :data:`DEFAULT_MODEL` as fallback; callers
  may override per request.
* Every call is accounted for (tokens + estimated USD) in :class:`UsageTracker`; the chat layer stores
  the totals on the ``ChatMessage`` row it writes.
* Retries/timeouts are the SDK's (``max_retries``, ``timeout`` seconds); refusals raise
  :class:`AIRefusal`; a missing key raises :class:`AIConfigError` (the API maps it to HTTP 409).

Prompts and model outputs are only ever logged at DEBUG level and only as lengths.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.personal import Redactor, load_redactor
from app.ai.pipeline import AIGuardError, GatewayContext
from app.ai.providers import PROVIDERS, ProviderAdapter
from app.ai.providers.anthropic_adapter import EAGER_FIELD as _EAGER
from app.ai.providers.anthropic_adapter import FALLBACK_BETA as _FALLBACK_BETA
from app.ai.providers.anthropic_adapter import FALLBACK_MODELS as _FALLBACK_MODELS
from app.ai.providers.anthropic_adapter import AnthropicAdapter
from app.ai.providers.base import ProviderError
from app.core.security import redact_keys
from app.services import settings_service as ss

log = logging.getLogger(__name__)


class _RedactKeys(logging.Filter):
    """Never let an API key reach a log line (SDK / httpx DEBUG output included; review MINOR 3)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        clean = redact_keys(msg)
        if clean != msg:
            record.msg, record.args = clean, ()
        return True


for _name in ("anthropic", "httpx", "httpcore", __name__, "app.ai.providers", "app.ai.pipeline"):
    logging.getLogger(_name).addFilter(_RedactKeys())

#: Default per the ``claude-api`` skill (the stored setting ``anthropic_model`` wins when set).
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MAX_RETRIES = 3

#: version of :data:`PRICING_USD_PER_MTOK` (the claude-api skill's model table, cached 2026-10-06); stored on every
#: ``ai_usage`` row (``synced`` = the provider's own published price, ``unpriced`` = no price known)
PRICE_TABLE_VERSION = "2026-10-06"

#: USD per 1M tokens (input, output) - from the claude-api skill's model table; cache reads are
#: charged at 10 % of input, cache writes at 125 %. Unknown models fall back to the Opus rate.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}

#: Models on which the server-side refusal fallback beta is accepted (claude-api skill).
FALLBACK_MODELS = _FALLBACK_MODELS
FALLBACK_BETA = _FALLBACK_BETA

#: Models that accept ``output_config.effort`` (it errors on Sonnet 4.5 / Haiku 4.5 and older).
EFFORT_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-haiku-5-5",
    }
)


class AIError(RuntimeError):
    """Base class for errors raised by the AI layer."""


class AIConfigError(AIError):
    """No API key configured (HTTP 409 at the API)."""


class AIRefusal(AIError):
    """The model declined the request (``stop_reason == "refusal"``)."""

    def __init__(self, category: str | None, explanation: str | None) -> None:
        super().__init__(f"model refused the request ({category or 'unspecified'})")
        self.category = category
        self.explanation = explanation


class AIUpstreamError(AIError):
    """The SDK raised an error (auth, rate limit, server error) that we do not retry further."""


class AIOutputRejected(AIUpstreamError):
    """The output guard refused the model's answer (an unexpected tool call, a structured answer that does not match
    its schema): nothing is applied, the caller treats it like a provider failure."""

    def __init__(self, code: str, message_tr: str, message_en: str) -> None:
        super().__init__(f"{message_tr} / {message_en}")
        self.code, self.message_tr, self.message_en = code, message_tr, message_en


class AIStreamJSONError(AIError):
    """A streamed tool input could not be parsed at all (eager input streaming): the turn has no ``tool_use_id``
    to answer, so the caller re-issues it (bounded)."""


EventSink = Callable[[dict[str, Any]], Awaitable[None]]
EAGER_FIELD = _EAGER


def _claude_base(model: str) -> str:
    base = (model or "").split("@")[0]
    for prefix in ("us.", "eu.", "apac.", "global."):
        base = base.removeprefix(prefix)
    return base.removeprefix("anthropic.").removeprefix("anthropic/")


def effort_supported(model: str) -> bool:
    return _claude_base(model) in EFFORT_MODELS


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
    *,
    provider: str | None = None,
    prices: tuple[float | None, float | None] | None = None,
) -> float:
    """Estimated USD. ``prices`` (USD per 1M input / output tokens) is the provider's synced price when it published
    one; Claude models use :data:`PRICING_USD_PER_MTOK` (unknown Claude models: the Opus rate); other models
    without a price cost 0 (``price_version`` says ``unpriced``)."""
    if prices and prices[0] is not None and prices[1] is not None:
        rate_in, rate_out = float(prices[0]), float(prices[1])
    else:
        base = _claude_base(model)
        if base in PRICING_USD_PER_MTOK:
            rate_in, rate_out = PRICING_USD_PER_MTOK[base]
        elif provider in (None, "anthropic", "bedrock") or base.startswith("claude"):
            rate_in, rate_out = PRICING_USD_PER_MTOK["claude-opus-5-5"]
        else:
            return 0.0
    cost = input_tokens * rate_in + output_tokens * rate_out + cache_read * rate_in * 0.1 + cache_write * rate_in * 1.25
    return round(cost / 1_000_000, 6)


def price_version(provider: str, model: str, prices: tuple[float | None, float | None] | None = None) -> str:
    if prices and prices[0] is not None and prices[1] is not None:
        return "synced"
    base = _claude_base(model)
    if base in PRICING_USD_PER_MTOK or provider in ("anthropic", "bedrock") or base.startswith("claude"):
        return PRICE_TABLE_VERSION
    return "unpriced"


@dataclass
class UsageTracker:
    model: str
    provider: str = "anthropic"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    requests: int = 0
    request_ids: list[str] = field(default_factory=list)

    def add(self, message: Any) -> None:
        usage = getattr(message, "usage", None)
        self.requests += 1
        if usage is None:
            return
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_read_input_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.cache_creation_input_tokens += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        rid = getattr(message, "_request_id", None)
        if rid:
            self.request_ids.append(str(rid))

    @property
    def estimated_cost_usd(self) -> float:
        return estimate_cost_usd(
            self.model,
            self.input_tokens,
            self.output_tokens,
            self.cache_read_input_tokens,
            self.cache_creation_input_tokens,
            provider=self.provider,
        )

    def to_out(self) -> dict[str, Any]:
        """Fields of :class:`app.schemas.ai.UsageOut`."""
        return {k: v for k, v in self.to_dict().items() if k != "type"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "usage",
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "requests": self.requests,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


class AIClient:
    """Async client bound to one key / adapter + one model. Create it with :func:`get_client`."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        use_fallbacks: bool = True,
        raw: Any | None = None,
        adapter: ProviderAdapter | None = None,
        provider: str = "anthropic",
        gateway: GatewayContext | None = None,
    ) -> None:
        if adapter is None and not api_key:
            raise AIConfigError("no Anthropic API key configured")
        self.model = model or DEFAULT_MODEL
        self.provider = provider
        self.usage = UsageTracker(self.model, provider=provider)
        self._key_fingerprint = f"...{api_key[-4:]}" if len(api_key or "") >= 8 else "***"
        #: people who withdrew the ``ai_personal`` consent (``app/ai/personal.py``; set by :func:`get_client`):
        #: their names leave as ``[KİŞİ_n]`` and come back as names in the answer
        self.redactor: Redactor | None = None
        self._adapter: ProviderAdapter = adapter or AnthropicAdapter(
            api_key, self.model, timeout_s=timeout_s, max_retries=max_retries, use_fallbacks=use_fallbacks, raw=raw
        )
        #: the gateway pipeline (routes, guards, limits, metering); ``None`` = a direct client (tests, smoke test)
        self.gateway = gateway

    def __repr__(self) -> str:  # never shows the key
        return f"AIClient(provider={self.provider!r}, model={self.model!r}, key={self._key_fingerprint})"

    @property
    def use_fallbacks(self) -> bool:
        return bool(getattr(self._adapter, "use_fallbacks", False))

    @property
    def _raw(self) -> Any:
        return getattr(self._adapter, "_raw", None)

    async def complete(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        output_format: dict[str, Any] | None = None,
        effort: str | None = None,
        disable_parallel_tool_use: bool = False,
        model: str | None = None,
    ) -> Any:
        """One model call. Returns the message; raises :class:`AIRefusal` on refusal, :class:`AIGuardError` when
        the gateway refused the call, :class:`AIUpstreamError` on provider failures."""
        kwargs = self._kwargs(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            output_format=output_format,
            effort=effort,
            disable_parallel_tool_use=disable_parallel_tool_use,
            model=model,
        )
        return await self._dispatch(kwargs, stream=False, on_event=None, model_override=model)

    async def stream_complete(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        effort: str | None = None,
        disable_parallel_tool_use: bool = False,
        model: str | None = None,
        on_event: EventSink | None = None,
    ) -> Any:
        """Like :meth:`complete`, streamed: ``on_event`` gets ``{"type": "text", "text"}`` deltas and
        ``{"type": "tool_start", "name"}``. Every tool carries ``eager_input_streaming: true``, so the server no
        longer validates tool input: the caller must validate each parsed input before running it, and an input
        the SDK cannot parse at all raises :class:`AIStreamJSONError` (re-issue the turn). Providers without
        streaming answer in one piece, replayed as the same events."""
        kwargs = self._kwargs(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            output_format=None,
            effort=effort,
            disable_parallel_tool_use=disable_parallel_tool_use,
            model=model,
            eager=True,
        )
        return await self._dispatch(kwargs, stream=True, on_event=on_event, model_override=model)

    async def _dispatch(
        self, kwargs: dict[str, Any], *, stream: bool, on_event: Any, model_override: str | None
    ) -> Any:
        try:
            if self.gateway is not None:
                from app.ai.pipeline import run_call

                message = await run_call(self, kwargs, stream=stream, on_event=on_event, model_override=model_override)
            else:
                direct = self._direct_kwargs(kwargs)
                message = await (self._adapter.stream(direct, on_event) if stream else self._send(direct))
        except ValueError as exc:
            if stream and not isinstance(exc, ProviderError):  # the SDK's partial-JSON parser gave up on a tool input
                raise AIStreamJSONError("a streamed tool input could not be parsed") from exc
            raise
        except (AIError, AIGuardError):
            raise
        except ProviderError as exc:
            raise AIUpstreamError(str(exc)) from exc
        except Exception as exc:
            mapped = self._adapter.translate_error(exc, kwargs["model"])
            if mapped is exc:  # not an SDK error: unchanged
                raise
            raise AIUpstreamError(str(mapped)) from exc
        return self._finish(message)

    async def _send(self, kwargs: dict[str, Any]) -> Any:
        """One non-streamed request of a direct client (the seam tests patch, as before the gateway)."""
        return await self._adapter.create(kwargs)

    @staticmethod
    def _direct_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        """The historic request of a direct client: effort only on the models that accept it."""
        out = {k: v for k, v in kwargs.items() if k != "_effort"}
        effort = kwargs.get("_effort")
        if effort and effort_supported(out["model"]):
            out["output_config"] = {**(out.get("output_config") or {}), "effort": effort}
        return out

    def _kwargs(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        output_format: dict[str, Any] | None,
        effort: str | None,
        disable_parallel_tool_use: bool,
        model: str | None,
        eager: bool = False,
    ) -> dict[str, Any]:
        if self.redactor:
            system, messages = self.redactor.payload(system), self.redactor.payload(messages)
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = [{**t, EAGER_FIELD: True} for t in tools] if eager else tools
            kwargs["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": disable_parallel_tool_use}
        if output_format:
            kwargs["output_config"] = {"format": output_format}
        if effort:
            kwargs["_effort"] = effort  # applied per provider / model (see _direct_kwargs and the pipeline)
        log.debug(
            "ai request model=%s system_chars=%d messages=%d tools=%d stream=%s",
            kwargs["model"],
            len(str(system)),
            len(messages),
            len(tools or []),
            eager,
        )
        return kwargs

    def _finish(self, message: Any) -> Any:
        self.usage.add(message)
        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            raise AIRefusal(getattr(details, "category", None), getattr(details, "explanation", None))
        if self.redactor:
            self.redactor.restore_message(message)
        log.debug("ai response stop=%s blocks=%d", getattr(message, "stop_reason", None), len(message.content))
        return message


async def resolve_key_and_model(
    session: AsyncSession, *, api_key: str | None = None, model: str | None = None
) -> tuple[str, str, str]:
    """``(key, model, key_source)`` with ``key_source`` in {"transient", "stored", "none"}."""
    key = (api_key or "").strip()
    source = "transient" if key else "none"
    if not key:
        key = (await ss.get_value(session, "anthropic_api_key") or "").strip()
        source = "stored" if key else "none"
    chosen = (model or "").strip() or (await ss.get_value(session, "anthropic_model") or "").strip() or DEFAULT_MODEL
    return key, chosen, source


async def get_client(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    model: str | None = None,
    feature: str | None = None,
    user_id: int | None = None,
    **kwargs: Any,
) -> AIClient:
    """The gateway client for ``feature`` (declared, or inferred from the caller): the route's provider and model,
    the key from the encrypted settings (or a transient Anthropic key), the pipeline bound. Raises
    :class:`AIConfigError` when the route's provider has no credentials (nothing is sent without a key)."""
    from app.ai import gateway as gw
    from app.ai.context import actor_from_session, current_actor, infer_feature

    if (api_key or "").strip():  # a transient key (settings "test connection"): Anthropic, unmetered, as before
        key, chosen, _ = await resolve_key_and_model(session, api_key=api_key, model=model)
        client = AIClient(key, chosen, **kwargs)
        client.redactor = await load_redactor(session)
        return client
    feat = feature or infer_feature()
    routes = await gw.all_routes(session)
    if feat not in routes:
        routes[feat] = await gw.resolve_route(session, feat)
    rr = routes[feat]
    providers = {r.route.provider for r in routes.values()} | {
        r.route.fallback_provider for r in routes.values() if r.route.fallback_provider
    }
    secrets = {p: await gw.provider_secrets(session, p) for p in providers if p in PROVIDERS}
    configs = {p: await gw.provider_config(session, p) for p in providers if p in PROVIDERS}
    transfer = {p: gw.transfer_ok(p, configs[p], await gw.transfer_record(session, p)) for p in configs}
    prices: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for p in configs:
        synced = await gw.synced_models(session, p)
        prices[p] = {
            str(m.get("id")): (m.get("price_in"), m.get("price_out"))
            for m in synced.get("models") or []
            if m.get("price_in") is not None
        }
    ctx = GatewayContext(
        feature=feat,
        routes=routes,
        secrets=secrets,
        configs=configs,
        transfer=transfer,
        guards=await gw.get_guardrails(session),
        limits=await gw.get_limits(session),
        synced_prices=prices,
        user_id=user_id or current_actor() or actor_from_session(session),
        timeout_s=float(kwargs.get("timeout_s", DEFAULT_TIMEOUT_S)),
        max_retries=int(kwargs.get("max_retries", DEFAULT_MAX_RETRIES)),
    )
    provider = rr.route.provider
    if not ctx.usable(provider):
        if provider == "anthropic":
            raise AIConfigError("no Anthropic API key configured; set it under Settings > AI")
        raise AIConfigError(f"no credentials configured for the AI provider {provider!r}; set them under Admin > AI")
    chosen = (model or "").strip() if (model and PROVIDERS[provider].claude) else rr.route.model
    try:
        adapter = ctx.adapter(provider, chosen, rr.route.temperature)
    except ProviderError as exc:
        raise AIConfigError(str(exc)) from exc
    client = AIClient("", chosen, adapter=adapter, provider=provider, gateway=ctx)
    client._key_fingerprint = f"...{(secrets.get(provider, {}).get('api_key') or '')[-4:]}"
    client.redactor = await load_redactor(session)  # KVKK ai_personal withdrawals (app/ai/personal.py)
    return client


async def test_connection(api_key: str, model: str | None = None) -> tuple[bool, str]:
    """Cheap probe used by ``POST /settings/test-ai``: 1 output token, no tools, no fallbacks."""
    if not (api_key or "").strip():
        return False, "no API key configured"
    try:
        client = AIClient(api_key, model or DEFAULT_MODEL, timeout_s=30.0, max_retries=1, use_fallbacks=False)
        message = await client.complete(
            system="Reply with OK.", messages=[{"role": "user", "content": "ping"}], max_tokens=8, effort="low"
        )
    except AIRefusal:
        return True, "ok (model refused the probe but the key is valid)"
    except AIError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - surfaced to the admin UI, never re-raised with the key
        log.warning("ai key probe failed: %s", redact_keys(f"{type(exc).__name__}: {exc}")[:500])
        return False, f"could not complete the test call ({type(exc).__name__})"
    served = getattr(message, "model", client.model)
    return True, f"ok ({served}, {client.usage.input_tokens} in / {client.usage.output_tokens} out)"


def text_of(message: Any) -> str:
    """Concatenated text blocks of a ``Message``."""
    return "\n".join(b.text for b in message.content if getattr(b, "type", None) == "text").strip()


def tool_uses(message: Any) -> list[Any]:
    return [b for b in message.content if getattr(b, "type", None) == "tool_use"]


def content_params(message: Any) -> list[dict[str, Any]]:
    """Response content as request params (thinking blocks included, unchanged, as the API requires)."""
    out: list[dict[str, Any]] = []
    for b in message.content:
        if hasattr(b, "model_dump"):
            out.append(b.model_dump(exclude_none=True))
        elif isinstance(b, dict):
            out.append(b)
    return out
