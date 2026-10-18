"""Anthropic adapter (the official ``anthropic`` SDK; the default provider) and the Bedrock adapter (Claude models on
Amazon Bedrock through the SDK's ``AsyncAnthropicBedrockMantle`` client, the Messages-API Bedrock endpoint).

Behaviour is the one ``AIClient`` had before the gateway (load the ``claude-api`` skill before editing):

* the beta endpoint with server-side refusal fallbacks (``fallbacks="default"``) on the models that accept it, the
  stable endpoint otherwise, and once without the beta when a deployment rejects it;
* streaming with ``eager_input_streaming`` on every tool, retried once without it when a proxy rejects the field;
* typed SDK errors -> short texts, most specific first (the upstream body may echo input and is only logged,
  redacted);
* a forced single tool (``tool_choice`` ``{"type": "tool"}``, HB-13) is sent as ``auto``: current Claude models
  (Opus 5.5, Sonnet 5.5, Fable 5.1) answer a forced ``tool`` / ``any`` choice with a 400, and Claude follows the
  one-tool prompt reliably (claude-api skill, "Forced tool use removed").

Model listing: ``client.models.list()`` (auto-paginating; ``id``, ``display_name``, ``created_at``,
``max_input_tokens``, ``max_tokens``). Bedrock lists through the Mantle client when it answers ``/v1/models`` and
falls back to ``boto3`` ``bedrock.list_foundation_models(byProvider="Anthropic")`` (optional import).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.ai.providers.base import EventSink, ModelInfo, ProviderAdapter, ProviderError
from app.core.security import redact_keys

log = logging.getLogger(__name__)

#: Models on which the server-side refusal fallback beta is accepted (claude-api skill; Claude API only).
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
EAGER_FIELD = "eager_input_streaming"


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    iso = getattr(value, "isoformat", None)
    return str(iso()) if callable(iso) else str(value)


def unforced(kwargs: dict[str, Any]) -> dict[str, Any]:
    """``tool_choice`` ``tool`` / ``any`` -> ``auto`` (keeping ``disable_parallel_tool_use``)."""
    choice = kwargs.get("tool_choice")
    if not isinstance(choice, dict) or choice.get("type") not in {"tool", "any"}:
        return kwargs
    auto: dict[str, Any] = {"type": "auto"}
    if "disable_parallel_tool_use" in choice:
        auto["disable_parallel_tool_use"] = bool(choice["disable_parallel_tool_use"])
    return {**kwargs, "tool_choice": auto}


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 120.0,
        max_retries: int = 3,
        use_fallbacks: bool = True,
        raw: Any | None = None,
        base_url: str | None = None,
    ) -> None:
        self.use_fallbacks = use_fallbacks and model.split("@")[0] in FALLBACK_MODELS
        if raw is not None:
            self._raw = raw
        else:
            import anthropic

            extra: dict[str, Any] = {"base_url": base_url} if base_url else {}
            self._raw = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=max_retries, **extra)

    # ------------------------------------------------------------------ calls

    async def create(self, kwargs: dict[str, Any]) -> Any:
        """Beta endpoint with server-side refusal fallbacks when the model supports it, else the stable endpoint.
        If the beta is rejected by the deployment we retry once without it."""
        import anthropic

        kwargs = unforced(kwargs)
        if self.use_fallbacks:
            try:
                return await self._raw.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except anthropic.BadRequestError as exc:
                if "fallback" not in exc.message.lower() and "beta" not in exc.message.lower():
                    raise
                log.debug("server-side fallbacks rejected by the API; retrying without")
                self.use_fallbacks = False
        return await self._raw.messages.create(**kwargs)

    async def stream(self, kwargs: dict[str, Any], on_event: EventSink | None) -> Any:
        """Streamed request (refusal fallbacks as in :meth:`create`). A deployment that rejects
        ``eager_input_streaming`` (a proxy, an older serving stack) is retried once without it."""
        import anthropic

        kwargs = unforced(kwargs)
        for attempt in range(2):
            try:
                if self.use_fallbacks:
                    try:
                        return await self._consume(
                            self._raw.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **kwargs),
                            on_event,
                        )
                    except anthropic.BadRequestError as exc:
                        if "fallback" not in exc.message.lower() and "beta" not in exc.message.lower():
                            raise
                        log.debug("server-side fallbacks rejected by the API; retrying without")
                        self.use_fallbacks = False
                return await self._consume(self._raw.messages.stream(**kwargs), on_event)
            except anthropic.BadRequestError as exc:
                if attempt or EAGER_FIELD not in exc.message or not kwargs.get("tools"):
                    raise
                log.info("eager_input_streaming rejected by the API; streaming without it")
                kwargs = {
                    **kwargs,
                    "tools": [{k: v for k, v in t.items() if k != EAGER_FIELD} for t in kwargs["tools"]],
                }
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    async def _consume(manager: Any, on_event: EventSink | None) -> Any:
        async with manager as stream:
            async for event in stream:
                if on_event is None:
                    continue
                kind = getattr(event, "type", None)
                if kind == "text":
                    await on_event({"type": "text", "text": event.text})
                elif kind == "content_block_start" and getattr(event.content_block, "type", None) == "tool_use":
                    await on_event({"type": "tool_start", "name": event.content_block.name})
            return await stream.get_final_message()

    # ------------------------------------------------------------------ models

    async def list_models(self) -> list[ModelInfo]:
        out: list[ModelInfo] = []
        async for m in self._raw.models.list():
            created = getattr(m, "created_at", None)
            out.append(
                ModelInfo(
                    id=str(m.id),
                    display_name=str(getattr(m, "display_name", "") or m.id),
                    created_at=_iso(created),
                    context_window=getattr(m, "max_input_tokens", None),
                    max_output=getattr(m, "max_tokens", None),
                )
            )
        return out

    # ------------------------------------------------------------------ errors

    def translate_error(self, exc: Exception, model: str) -> Exception:
        """Typed SDK errors -> our short texts, most specific first. Anything else is returned unchanged."""
        import anthropic

        if isinstance(exc, anthropic.AuthenticationError):
            return ProviderError("Anthropic rejected the API key (authentication error)")
        if isinstance(exc, anthropic.PermissionDeniedError):
            return ProviderError("the API key lacks permission for this model")
        if isinstance(exc, anthropic.NotFoundError):
            return ProviderError(f"model {model!r} not found")
        if isinstance(exc, anthropic.RateLimitError):
            return ProviderError("rate limited by Anthropic; retry later")
        if isinstance(exc, anthropic.BadRequestError):
            log.warning("ai bad request: %s", redact_keys(str(exc.message)[:500]))
            return ProviderError("the AI service rejected the request (bad request)")
        if isinstance(exc, anthropic.APIStatusError):
            return ProviderError(f"Anthropic API error {exc.status_code}")
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderError("could not reach the Anthropic API")
        return exc


def bedrock_model_id(model: str) -> str:
    """Bedrock model ids take the ``anthropic.`` prefix (``anthropic.claude-opus-5-5``); regional inference
    profiles (``us.anthropic.…``, ``eu.anthropic.…``) are kept as they are."""
    m = (model or "").strip()
    if m.startswith("anthropic.") or ".anthropic." in m:
        return m
    return f"anthropic.{m}"


class BedrockAdapter(AnthropicAdapter):
    """Claude on Amazon Bedrock. Credentials: a Bedrock API key, or an access key id + secret (+ session token);
    the region is required. Server-side refusal fallbacks are a Claude API feature, so they are off here."""

    name = "bedrock"

    def __init__(
        self,
        *,
        region: str,
        api_key: str | None = None,
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 3,
        raw: Any | None = None,
        boto_client: Any | None = None,
    ) -> None:
        if not region:
            raise ProviderError("Bedrock needs an AWS region")
        self.region = region
        self._creds = (aws_access_key, aws_secret_key, aws_session_token)
        self._boto = boto_client
        if raw is None:
            from anthropic import AsyncAnthropicBedrockMantle

            kwargs: dict[str, Any] = {"aws_region": region, "timeout": timeout_s, "max_retries": max_retries}
            if api_key:
                kwargs["api_key"] = api_key
            elif aws_access_key and aws_secret_key:
                kwargs.update(aws_access_key=aws_access_key, aws_secret_key=aws_secret_key)
                if aws_session_token:
                    kwargs["aws_session_token"] = aws_session_token
            raw = AsyncAnthropicBedrockMantle(**kwargs)
        super().__init__("", "", raw=raw, use_fallbacks=False)

    async def create(self, kwargs: dict[str, Any]) -> Any:
        return await super().create({**kwargs, "model": bedrock_model_id(kwargs["model"])})

    async def stream(self, kwargs: dict[str, Any], on_event: EventSink | None) -> Any:
        return await super().stream({**kwargs, "model": bedrock_model_id(kwargs["model"])}, on_event)

    async def list_models(self) -> list[ModelInfo]:
        try:
            listed = await super().list_models()
            if listed:
                return listed
        except Exception as exc:  # noqa: BLE001 - the Mantle endpoint may not list models; try boto3
            log.info("bedrock mantle model list unavailable (%s); trying boto3", type(exc).__name__)
        client = self._boto
        if client is None:
            try:
                import boto3  # type: ignore[import-not-found, import-untyped, unused-ignore]
            except ImportError as exc:
                raise ProviderError("listing Bedrock models needs boto3 (pip install boto3)") from exc
            ak, sk, st = self._creds
            client = boto3.client(
                "bedrock",
                region_name=self.region,
                **({"aws_access_key_id": ak, "aws_secret_access_key": sk} if ak and sk else {}),
                **({"aws_session_token": st} if st else {}),
            )
        resp = await asyncio.to_thread(client.list_foundation_models, byProvider="Anthropic")
        out = []
        for m in resp.get("modelSummaries") or []:
            if "TEXT" not in (m.get("outputModalities") or ["TEXT"]):
                continue
            out.append(ModelInfo(id=str(m.get("modelId")), display_name=str(m.get("modelName") or m.get("modelId"))))
        return out

    def translate_error(self, exc: Exception, model: str) -> Exception:
        mapped = super().translate_error(exc, model)
        if isinstance(mapped, ProviderError):
            return ProviderError(str(mapped).replace("Anthropic", "Bedrock"))
        return mapped


class VertexAdapter(AnthropicAdapter):
    """Claude on Google Cloud Vertex AI (``AsyncAnthropicVertex``; needs ``anthropic[vertex]`` / ``google-auth``).
    Auth is Google Application Default Credentials on the server, no key in the database; ``project_id`` and
    ``region`` (``global`` recommended) come from the provider config. Vertex model ids are the bare first-party
    ids. Vertex has no model-list endpoint for partner models, so a sync offers the Claude ids of the price table
    (``source: catalog``); the Test button proves which of them the project can call."""

    name = "vertex"

    def __init__(
        self, *, project_id: str, region: str, timeout_s: float = 120.0, max_retries: int = 3, raw: Any | None = None
    ) -> None:
        if not project_id:
            raise ProviderError("Vertex AI needs a Google Cloud project id")
        self.region = region or "global"
        if raw is None:
            try:
                from anthropic import AsyncAnthropicVertex
            except ImportError as exc:  # pragma: no cover - part of the anthropic SDK
                raise ProviderError("the anthropic SDK has no Vertex client") from exc
            try:
                raw = AsyncAnthropicVertex(
                    project_id=project_id, region=self.region, timeout=timeout_s, max_retries=max_retries
                )
            except Exception as exc:  # noqa: BLE001 - google-auth missing or no default credentials
                raise ProviderError(f"Vertex AI client could not start ({type(exc).__name__})") from exc
        super().__init__("", "", raw=raw, use_fallbacks=False)

    async def list_models(self) -> list[ModelInfo]:
        from app.ai.client import PRICING_USD_PER_MTOK

        return [ModelInfo(id=m, display_name=m, created_at=None) for m in PRICING_USD_PER_MTOK]

    def translate_error(self, exc: Exception, model: str) -> Exception:
        mapped = super().translate_error(exc, model)
        if isinstance(mapped, ProviderError):
            return ProviderError(str(mapped).replace("Anthropic", "Vertex AI"))
        return mapped


__all__ = [
    "VertexAdapter",
    "EAGER_FIELD",
    "FALLBACK_BETA",
    "FALLBACK_MODELS",
    "AnthropicAdapter",
    "BedrockAdapter",
    "bedrock_model_id",
    "unforced",
]
