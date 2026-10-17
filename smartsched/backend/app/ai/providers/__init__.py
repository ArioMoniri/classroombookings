"""Provider registry of the AI gateway (wave 3 W3-AI).

Each provider has an id, TR/EN labels, the secret fields an admin can set (stored encrypted in ``settings``; the
Anthropic key keeps its historic row ``anthropic_api_key``), the plain config fields and a factory. Only the
``anthropic`` SDK is required; the other adapters talk REST through ``httpx`` (OpenAI-compatible, Gemini) or use the
``anthropic`` SDK's Bedrock client (Bedrock; listing models may use ``boto3`` when installed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.providers.anthropic_adapter import AnthropicAdapter, BedrockAdapter, VertexAdapter
from app.ai.providers.base import (
    GBlock,
    GMessage,
    GUsage,
    ModelInfo,
    ProviderAdapter,
    ProviderError,
    ProviderUnsupported,
)
from app.ai.providers.gemini import GeminiAdapter
from app.ai.providers.openai_compat import DEFAULT_BASE_URLS, OpenAICompatAdapter
from app.ai.providers.url_guard import UnsafeBaseURL, check_base_url


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label_tr: str
    label_en: str
    #: secret field names (``api_key``, ``aws_secret_access_key`` ...)
    secrets: tuple[str, ...]
    #: plain config field names (``base_url``, ``region``)
    config: tuple[str, ...]
    #: True when the provider can run without any secret (a local Ollama / vLLM)
    keyless: bool = False
    default_base_url: str = ""
    #: whether Claude model ids (and the claude-api pricing table) apply
    claude: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label_tr": self.label_tr,
            "label_en": self.label_en,
            "secrets": list(self.secrets),
            "config": list(self.config),
            "keyless": self.keyless,
            "default_base_url": self.default_base_url,
        }


PROVIDERS: dict[str, ProviderSpec] = {
    p.id: p
    for p in (
        ProviderSpec("anthropic", "Anthropic (Claude)", "Anthropic (Claude)", ("api_key",), (), claude=True),
        ProviderSpec(
            "openai", "OpenAI", "OpenAI", ("api_key",), ("base_url",), default_base_url=DEFAULT_BASE_URLS["openai"]
        ),
        ProviderSpec("azure_openai", "Azure OpenAI", "Azure OpenAI", ("api_key",), ("base_url",)),
        ProviderSpec(
            "openrouter",
            "OpenRouter",
            "OpenRouter",
            ("api_key",),
            ("base_url",),
            default_base_url=DEFAULT_BASE_URLS["openrouter"],
        ),
        ProviderSpec(
            "openai_compatible",
            "OpenAI uyumlu sunucu (Ollama, vLLM)",
            "OpenAI-compatible server (Ollama, vLLM)",
            ("api_key",),
            ("base_url",),
            keyless=True,
            default_base_url=DEFAULT_BASE_URLS["openai_compatible"],
        ),
        ProviderSpec("gemini", "Google Gemini", "Google Gemini", ("api_key",), ("base_url",)),
        ProviderSpec(
            "bedrock",
            "AWS Bedrock (Claude)",
            "AWS Bedrock (Claude)",
            ("api_key", "aws_access_key_id", "aws_secret_access_key"),
            ("region",),
            claude=True,
        ),
        ProviderSpec(
            "vertex",
            "Google Vertex AI (Claude)",
            "Google Vertex AI (Claude)",
            (),
            ("project_id", "region"),
            keyless=True,
            claude=True,
        ),
    )
}


def has_credentials(provider: str, secrets: dict[str, str]) -> bool:
    spec = PROVIDERS[provider]
    if spec.keyless:
        return True  # a local server; Vertex authenticates with the server's Google credentials
    if provider == "bedrock":
        return bool(
            secrets.get("api_key") or (secrets.get("aws_access_key_id") and secrets.get("aws_secret_access_key"))
        )
    return bool(secrets.get("api_key"))


def make_adapter(
    provider: str,
    *,
    model: str,
    secrets: dict[str, str],
    config: dict[str, Any] | None = None,
    timeout_s: float = 120.0,
    max_retries: int = 3,
    temperature: float | None = None,
    use_fallbacks: bool = True,
    raw: Any | None = None,
    transport: Any | None = None,
) -> ProviderAdapter:
    """An adapter for ``provider`` (raises :class:`ProviderError` when a required credential or URL is missing)."""
    cfg = config or {}
    if provider not in PROVIDERS:
        raise ProviderError(f"unknown AI provider {provider!r}")
    if provider == "anthropic":
        if not secrets.get("api_key") and raw is None:
            raise ProviderError("no Anthropic API key configured")
        return AnthropicAdapter(
            secrets.get("api_key", ""),
            model,
            timeout_s=timeout_s,
            max_retries=max_retries,
            use_fallbacks=use_fallbacks,
            raw=raw,
        )
    if provider == "bedrock":
        if not has_credentials("bedrock", secrets) and raw is None:
            raise ProviderError("no Bedrock credentials configured")
        return BedrockAdapter(
            region=str(cfg.get("region") or ""),
            api_key=secrets.get("api_key") or None,
            aws_access_key=secrets.get("aws_access_key_id") or None,
            aws_secret_key=secrets.get("aws_secret_access_key") or None,
            timeout_s=timeout_s,
            max_retries=max_retries,
            raw=raw,
        )
    if provider == "vertex":
        return VertexAdapter(
            project_id=str(cfg.get("project_id") or ""),
            region=str(cfg.get("region") or "global"),
            timeout_s=timeout_s,
            max_retries=max_retries,
            raw=raw,
        )
    if provider == "gemini":
        return GeminiAdapter(
            api_key=secrets.get("api_key", ""),
            base_url=cfg.get("base_url") or None,
            timeout_s=timeout_s,
            temperature=temperature,
            transport=transport,
        )
    return OpenAICompatAdapter(
        provider,
        api_key=secrets.get("api_key") or None,
        base_url=cfg.get("base_url") or None,
        timeout_s=timeout_s,
        temperature=temperature,
        transport=transport,
        # the administrator's explicit opt-in for a local server (Ollama, vLLM); url_guard.py refuses it otherwise
        allow_local=provider == "openai_compatible" and cfg.get("allow_local") is True,
    )


__all__ = [
    "PROVIDERS",
    "AnthropicAdapter",
    "BedrockAdapter",
    "GBlock",
    "GMessage",
    "GUsage",
    "GeminiAdapter",
    "ModelInfo",
    "OpenAICompatAdapter",
    "ProviderAdapter",
    "ProviderError",
    "ProviderSpec",
    "ProviderUnsupported",
    "UnsafeBaseURL",
    "VertexAdapter",
    "check_base_url",
    "has_credentials",
    "make_adapter",
]
