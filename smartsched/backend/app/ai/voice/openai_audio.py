"""OpenAI and Azure OpenAI speech to text: ``POST {base}/audio/transcriptions`` (multipart; API reference "Create
transcription", read 2026-10-17).

* ``gpt-transcribe`` (the recommended file model since 2026-07-28) takes ``languages[]``, ``keywords[]`` and
  ``prompt``; it must not get the singular ``language``. The older models (``gpt-4o-transcribe``,
  ``gpt-4o-mini-transcribe``, ``whisper-1``) take ``language`` and ``prompt``.
* ``response_format=json``; the answer is ``{"text", "languages"?, "usage"?}`` where ``usage`` is either
  ``{"type": "duration", "seconds"}`` or token counts.
* Azure OpenAI uses the same ``/openai/v1`` path with the ``api-key`` header (the deployment name is the model).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from app.ai.providers.base import ModelInfo, ProviderError
from app.ai.providers.openai_compat import DEFAULT_BASE_URLS
from app.ai.voice.speech import EXTENSIONS, HttpSpeechAdapter, Transcript, clean_terms

_LABELS = {"openai": "OpenAI", "azure_openai": "Azure OpenAI"}


def _uses_languages(model: str) -> bool:
    return model.lower().rsplit("/", 1)[-1].startswith("gpt-transcribe")


class OpenAIAudioAdapter(HttpSpeechAdapter):
    def __init__(
        self,
        flavor: str,
        *,
        api_key: str | None,
        base_url: str | None = None,
        timeout_s: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if flavor not in _LABELS:
            raise ValueError(f"no speech adapter for {flavor!r}")
        base = (base_url or DEFAULT_BASE_URLS[flavor]).strip()
        if not base:
            raise ProviderError("this provider needs a base URL (Azure: https://<resource>.openai.azure.com/openai/v1)")
        if not api_key:
            raise ProviderError("no API key configured for this provider")
        super().__init__(base_url=base, timeout_s=timeout_s, transport=transport)
        self.name = flavor
        self.label = _LABELS[flavor]
        self._key = api_key

    def _headers(self) -> dict[str, str]:
        return {"api-key": self._key} if self.name == "azure_openai" else {"Authorization": f"Bearer {self._key}"}

    async def transcribe(
        self, audio: bytes, mime: str, *, model: str, language: str, vocabulary: Sequence[str] = ()
    ) -> Transcript:
        data: dict[str, Any] = {"model": model, "response_format": "json"}
        terms = clean_terms(vocabulary, limit=40)
        if _uses_languages(model):
            data["languages[]"] = [language]
            if terms:
                data["keywords[]"] = terms
        else:
            data["language"] = language
            if terms:
                data["prompt"] = ("Sözlük: " if language == "tr" else "Vocabulary: ") + ", ".join(terms)
        files = {"file": (f"audio.{EXTENSIONS.get(mime, 'webm')}", audio, mime)}
        body = await self._send(
            "POST", f"{self.base_url}/audio/transcriptions", headers=self._headers(), data=data, files=files
        )
        return parse_transcription(body)

    async def list_models(self) -> list[ModelInfo]:
        body = await self._send("GET", f"{self.base_url}/models", headers=self._headers())
        return [
            ModelInfo(id=str(m["id"]), display_name=str(m.get("name") or m["id"]))
            for m in body.get("data") or []
            if isinstance(m, dict) and m.get("id")
        ]


def parse_transcription(body: dict[str, Any]) -> Transcript:
    text = body.get("text")
    if not isinstance(text, str):
        raise ProviderError("the provider answered without a transcript")
    raw_usage = body.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    duration = usage.get("seconds") if usage.get("type") == "duration" else body.get("duration")
    langs = body.get("languages") or []
    language = langs[0].get("code") if langs and isinstance(langs[0], dict) else body.get("language")
    return Transcript(
        text=text,
        duration_s=float(duration) if isinstance(duration, int | float) else None,
        language=str(language) if language else None,
        input_tokens=int(usage.get("input_tokens") or 0) if usage.get("type") == "tokens" else 0,
        output_tokens=int(usage.get("output_tokens") or 0) if usage.get("type") == "tokens" else 0,
    )


__all__ = ["OpenAIAudioAdapter", "parse_transcription"]
