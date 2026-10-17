"""Google Cloud Speech-to-Text v2 with Chirp 3 (``POST https://{location}-speech.googleapis.com/v2/projects/{project}/
locations/{location}/recognizers/_:recognize``; docs.cloud.google.com/speech-to-text/docs/models/chirp-3, read
2026-10-17: ``tr-TR`` GA, the ``eu`` and ``us`` multi-regions GA).

Synchronous recognition of one short clip (the clips are ≤ 120 s): ``config`` with ``autoDecodingConfig``,
``languageCodes`` ``["tr-TR"]``, ``model`` ``chirp_3`` and an inline phrase set for the vocabulary (Chirp 3 model
adaptation); ``content`` is the clip in base64. Authentication is an API key restricted to the Speech-to-Text API
(header ``x-goog-api-key``): the backend has no Google auth library, and a key keeps the encrypted write-only key
pattern of the other providers. The location is part of the host name, so it must be a plain region name.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Sequence
from typing import Any

import httpx
from app.ai.providers.base import ModelInfo, ProviderError
from app.ai.voice.speech import HttpSpeechAdapter, Transcript, clean_terms, locale

DEFAULT_LOCATION = "eu"
MODELS = (ModelInfo(id="chirp_3", display_name="Chirp 3"),)
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")


def _seconds(value: Any) -> float | None:
    """``"5.160s"`` (a protobuf Duration in JSON) -> 5.16."""
    if isinstance(value, str) and value.endswith("s"):
        try:
            return float(value[:-1])
        except ValueError:
            return None
    return None


class GoogleSTTAdapter(HttpSpeechAdapter):
    name = "google_stt"
    label = "Google Speech-to-Text"

    def __init__(
        self,
        *,
        api_key: str,
        project_id: str | None,
        location: str | None = None,
        timeout_s: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("no API key configured for Google Speech-to-Text")
        loc = (location or DEFAULT_LOCATION).strip().lower()
        project = (project_id or "").strip()
        if not _NAME.match(loc):
            raise ProviderError("the Google Speech-to-Text location must be a region name such as eu or us")
        if not project or not re.match(r"^[a-z][a-z0-9-]{0,62}$", project):
            raise ProviderError("Google Speech-to-Text needs the Google Cloud project id")
        host = "https://speech.googleapis.com" if loc == "global" else f"https://{loc}-speech.googleapis.com"
        super().__init__(base_url=host, timeout_s=timeout_s, transport=transport)
        self._key = api_key
        self.project, self.location = project, loc

    async def transcribe(
        self, audio: bytes, mime: str, *, model: str, language: str, vocabulary: Sequence[str] = ()
    ) -> Transcript:
        config: dict[str, Any] = {
            "autoDecodingConfig": {},
            "languageCodes": [locale(language)],
            "model": model or "chirp_3",
        }
        terms = clean_terms(vocabulary, limit=200)
        if terms:
            config["adaptation"] = {"phraseSets": [{"inlinePhraseSet": {"phrases": [{"value": t} for t in terms]}}]}
        body = await self._send(
            "POST",
            f"{self.base_url}/v2/projects/{self.project}/locations/{self.location}/recognizers/_:recognize",
            headers={"x-goog-api-key": self._key},
            json={"config": config, "content": base64.b64encode(audio).decode("ascii")},
        )
        results = [r for r in body.get("results") or [] if isinstance(r, dict)]
        texts = [str(((r.get("alternatives") or [{}])[0] or {}).get("transcript") or "").strip() for r in results]
        ends = [s for s in (_seconds(r.get("resultEndOffset")) for r in results) if s is not None]
        meta = body.get("metadata") or {}
        duration = max(ends) if ends else _seconds(meta.get("totalBilledDuration"))
        lang = next((str(r["languageCode"]) for r in results if r.get("languageCode")), None)
        return Transcript(
            text=" ".join(t for t in texts if t),
            duration_s=duration,
            language=lang,
            request_id=str(meta["requestId"]) if meta.get("requestId") else None,
        )

    async def list_models(self) -> list[ModelInfo]:
        return list(MODELS)


__all__ = ["DEFAULT_LOCATION", "GoogleSTTAdapter"]
