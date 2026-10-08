"""Thin wrapper over the official ``anthropic`` SDK.

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
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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


for _name in ("anthropic", "httpx", "httpcore", __name__):
    logging.getLogger(_name).addFilter(_RedactKeys())

#: Default per the ``claude-api`` skill (the stored setting ``anthropic_model`` wins when set).
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MAX_RETRIES = 3

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
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"

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


def estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0
) -> float:
    base = model.split("@")[0]
    rate_in, rate_out = PRICING_USD_PER_MTOK.get(base, PRICING_USD_PER_MTOK["claude-opus-5-5"])
    cost = input_tokens * rate_in + output_tokens * rate_out + cache_read * rate_in * 0.1 + cache_write * rate_in * 1.25
    return round(cost / 1_000_000, 6)


@dataclass
class UsageTracker:
    model: str
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
    """Async client bound to one key + one model. Create it with :func:`get_client`."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        use_fallbacks: bool = True,
        raw: Any | None = None,
    ) -> None:
        if not api_key:
            raise AIConfigError("no Anthropic API key configured")
        self.model = model or DEFAULT_MODEL
        self.use_fallbacks = use_fallbacks and self.model in FALLBACK_MODELS
        self.usage = UsageTracker(self.model)
        self._key_fingerprint = f"...{api_key[-4:]}" if len(api_key) >= 8 else "***"
        if raw is not None:
            self._raw = raw
        else:
            import anthropic

            self._raw = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=max_retries)

    def __repr__(self) -> str:  # never shows the key
        return f"AIClient(model={self.model!r}, key={self._key_fingerprint})"

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
        """One ``POST /v1/messages``. Returns the SDK ``Message``; raises :class:`AIRefusal` on refusal."""
        import anthropic

        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": disable_parallel_tool_use}
        output_config: dict[str, Any] = {}
        if output_format:
            output_config["format"] = output_format
        if effort and kwargs["model"].split("@")[0].removeprefix("anthropic.") in EFFORT_MODELS:
            output_config["effort"] = effort
        if output_config:
            kwargs["output_config"] = output_config
        log.debug(
            "ai request model=%s system_chars=%d messages=%d tools=%d",
            kwargs["model"],
            len(str(system)),
            len(messages),
            len(tools or []),
        )
        try:
            message = await self._send(kwargs)
        except anthropic.AuthenticationError as exc:
            raise AIUpstreamError("Anthropic rejected the API key (authentication error)") from exc
        except anthropic.PermissionDeniedError as exc:
            raise AIUpstreamError("the API key lacks permission for this model") from exc
        except anthropic.NotFoundError as exc:
            raise AIUpstreamError(f"model {kwargs['model']!r} not found") from exc
        except anthropic.RateLimitError as exc:
            raise AIUpstreamError("rate limited by Anthropic; retry later") from exc
        except anthropic.BadRequestError as exc:  # the upstream text may echo input: log it, return a generic one
            log.warning("ai bad request: %s", redact_keys(str(exc.message)[:500]))
            raise AIUpstreamError("the AI service rejected the request (bad request)") from exc
        except anthropic.APIStatusError as exc:
            raise AIUpstreamError(f"Anthropic API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIUpstreamError("could not reach the Anthropic API") from exc
        self.usage.add(message)
        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            raise AIRefusal(getattr(details, "category", None), getattr(details, "explanation", None))
        log.debug("ai response stop=%s blocks=%d", getattr(message, "stop_reason", None), len(message.content))
        return message

    async def _send(self, kwargs: dict[str, Any]) -> Any:
        """Beta endpoint with server-side refusal fallbacks when the model supports it, else the
        stable endpoint. If the beta is rejected by the deployment we retry once without it."""
        import anthropic

        if self.use_fallbacks:
            try:
                return await self._raw.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except anthropic.BadRequestError as exc:
                if "fallback" not in exc.message.lower() and "beta" not in exc.message.lower():
                    raise
                log.debug("server-side fallbacks rejected by the API; retrying without")
                self.use_fallbacks = False
        return await self._raw.messages.create(**kwargs)


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
    session: AsyncSession, *, api_key: str | None = None, model: str | None = None, **kwargs: Any
) -> AIClient:
    """Client from the stored (decrypted) key or a transient one. Raises :class:`AIConfigError`."""
    key, chosen, _ = await resolve_key_and_model(session, api_key=api_key, model=model)
    if not key:
        raise AIConfigError("no Anthropic API key configured; set it under Settings > AI")
    return AIClient(key, chosen, **kwargs)


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
