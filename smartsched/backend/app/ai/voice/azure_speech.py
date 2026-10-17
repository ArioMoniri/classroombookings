"""Azure AI Speech fast transcription (``POST {endpoint}/speechtotext/transcriptions:transcribe?api-version=
2025-10-15``; learn.microsoft.com/azure/ai-services/speech-service/fast-transcription-create, read 2026-10-17).

Multipart ``audio`` + ``definition`` (JSON: ``locales`` ``["tr-TR"]`` and, from API version 2025-10-15, a
``phraseList``), header ``Ocp-Apim-Subscription-Key``. The answer has ``durationMilliseconds`` and
``combinedPhrases[].text``. The base URL is the Speech resource's endpoint
(``https://<resource>.cognitiveservices.azure.com``); create the resource in an EU region. There is no model list:
the one model is ``fast``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import httpx

from app.ai.providers.base import ModelInfo, ProviderError
from app.ai.voice.speech import EXTENSIONS, HttpSpeechAdapter, Transcript, clean_terms, locale

API_VERSION = "2025-10-15"
MODELS = (ModelInfo(id="fast", display_name="Fast transcription"),)


class AzureSpeechAdapter(HttpSpeechAdapter):
    name = "azure_speech"
    label = "Azure AI Speech"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        timeout_s: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("no API key configured for Azure AI Speech")
        if not base_url:
            raise ProviderError(
                "Azure AI Speech needs the resource endpoint (https://<resource>.cognitiveservices.azure.com)"
            )
        super().__init__(base_url=base_url, timeout_s=timeout_s, transport=transport)
        self._key = api_key

    async def transcribe(
        self, audio: bytes, mime: str, *, model: str, language: str, vocabulary: Sequence[str] = ()
    ) -> Transcript:
        definition: dict[str, object] = {"locales": [locale(language)]}
        terms = clean_terms(vocabulary, limit=100)
        if terms:
            definition["phraseList"] = {"phrases": terms}
        body = await self._send(
            "POST",
            f"{self.base_url}/speechtotext/transcriptions:transcribe",
            params={"api-version": API_VERSION},
            headers={"Ocp-Apim-Subscription-Key": self._key},
            data={"definition": json.dumps(definition, ensure_ascii=False)},
            files={"audio": (f"audio.{EXTENSIONS.get(mime, 'webm')}", audio, mime)},
        )
        phrases = body.get("combinedPhrases") or []
        if not isinstance(phrases, list):
            raise ProviderError("Azure AI Speech answered without a transcript")
        text = " ".join(str(p.get("text") or "") for p in phrases if isinstance(p, dict)).strip()
        ms = body.get("durationMilliseconds")
        return Transcript(text=text, duration_s=ms / 1000.0 if isinstance(ms, int | float) else None)

    async def list_models(self) -> list[ModelInfo]:
        return list(MODELS)


__all__ = ["API_VERSION", "AzureSpeechAdapter"]
