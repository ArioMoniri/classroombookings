"""Which provider and model can transcribe, and the factory of speech adapters (VO-01 / VO-10).

* :func:`model_modalities` tags each synced model (``POST /ai/admin/providers/{p}/sync``): OpenAI-style ids with
  ``transcribe`` or ``whisper`` are ``stt`` (the speaker-labelling ``*-diarize`` model needs another answer format
  and is left out), ``tts`` ids are ``tts``; Gemini chat models accept audio input, so they are ``text`` + ``stt``;
  the speech-only providers list only speech models.
* :func:`make_speech_adapter` builds the adapter of a provider whose spec has the ``stt`` capability, with the
  stored secrets and config (keys are passed in, never read here and never logged).
"""

from __future__ import annotations

from typing import Any

import httpx
from app.ai.providers import PROVIDERS
from app.ai.providers.base import ProviderError
from app.ai.voice.speech import SpeechAdapter

_GEMINI_NOT_AUDIO = ("embedding", "imagen", "image", "-tts", "aqa", "live", "veo", "learnlm")


def speech_capable(provider: str) -> bool:
    spec = PROVIDERS.get(provider)
    return spec is not None and "stt" in spec.capabilities


def model_modalities(provider: str, model_id: str) -> list[str]:
    spec = PROVIDERS.get(provider)
    if spec is None or not spec.capabilities:
        return ["text"]
    if spec.capabilities == frozenset({"stt"}):
        return ["stt"]
    m = model_id.lower().rsplit("/", 1)[-1]
    if provider in ("openai", "azure_openai"):
        if ("transcribe" in m and "diarize" not in m) or m.startswith("whisper"):
            return ["stt"]
        if "tts" in m:
            return ["tts"]
        return ["text"]
    if provider == "gemini":
        if m.endswith("-tts") or "-tts-" in m:
            return ["tts"]
        if m.startswith("gemini-") and not any(x in m for x in _GEMINI_NOT_AUDIO):
            return ["text", "stt"]
        return ["text"]
    return ["text"]


def speech_model_ids(models: list[dict[str, Any]]) -> set[str]:
    """Ids of synced models (stored dicts) whose modalities include ``stt``."""
    return {str(m.get("id")) for m in models if "stt" in (m.get("modalities") or [])}


def make_speech_adapter(
    provider: str,
    *,
    secrets: dict[str, str],
    config: dict[str, Any] | None = None,
    timeout_s: float = 60.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SpeechAdapter:
    """The speech adapter of ``provider`` (raises :class:`ProviderError` for a provider without speech or with a
    missing key / endpoint)."""
    cfg = config or {}
    if not speech_capable(provider):
        raise ProviderError(f"{provider} cannot transcribe speech")
    key = secrets.get("api_key", "")
    base = str(cfg.get("base_url") or "") or None
    if provider in ("openai", "azure_openai"):
        from app.ai.voice.openai_audio import OpenAIAudioAdapter

        return OpenAIAudioAdapter(provider, api_key=key, base_url=base, timeout_s=timeout_s, transport=transport)
    if provider == "gemini":
        from app.ai.voice.gemini_audio import GeminiAudioAdapter

        return GeminiAudioAdapter(api_key=key, base_url=base, timeout_s=timeout_s, transport=transport)
    if provider == "azure_speech":
        from app.ai.voice.azure_speech import AzureSpeechAdapter

        return AzureSpeechAdapter(api_key=key, base_url=base, timeout_s=timeout_s, transport=transport)
    if provider == "google_stt":
        from app.ai.voice.google_stt import GoogleSTTAdapter

        return GoogleSTTAdapter(
            api_key=key,
            project_id=cfg.get("project_id"),
            location=cfg.get("region"),
            timeout_s=timeout_s,
            transport=transport,
        )
    from app.ai.voice.deepgram import DeepgramAdapter

    return DeepgramAdapter(api_key=key, base_url=base, timeout_s=timeout_s, transport=transport)


__all__ = ["make_speech_adapter", "model_modalities", "speech_capable", "speech_model_ids"]
