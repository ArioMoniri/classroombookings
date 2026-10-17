"""Deepgram pre-recorded transcription (``POST {base}/v1/listen``; developers.deepgram.com/reference/speech-to-text/
listen-pre-recorded, read 2026-10-17). The default base is the EU endpoint ``https://api.eu.deepgram.com`` (GA
2025-12-03).

The clip is the raw request body with its ``Content-Type``; the query carries ``model`` (``nova-3``, Turkish since
2026-07-16), ``language``, ``smart_format`` / ``punctuate``, one ``keyterm`` per vocabulary entry (Nova-3 key-term
prompting) and ``mip_opt_out=true`` (the request is not used by Deepgram's model improvement programme; KVKK).
Header ``Authorization: Token <key>``. The answer: ``results.channels[0].alternatives[0].transcript`` and
``metadata.duration`` (seconds).
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from app.ai.providers import DEEPGRAM_EU
from app.ai.providers.base import ModelInfo, ProviderError
from app.ai.voice.speech import HttpSpeechAdapter, Transcript, clean_terms

MODELS = (ModelInfo(id="nova-3", display_name="Nova-3"), ModelInfo(id="nova-2", display_name="Nova-2"))


class DeepgramAdapter(HttpSpeechAdapter):
    name = "deepgram"
    label = "Deepgram"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_s: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("no API key configured for Deepgram")
        super().__init__(base_url=base_url or DEEPGRAM_EU, timeout_s=timeout_s, transport=transport)
        self._key = api_key

    async def transcribe(
        self, audio: bytes, mime: str, *, model: str, language: str, vocabulary: Sequence[str] = ()
    ) -> Transcript:
        params: list[tuple[str, str]] = [
            ("model", model or "nova-3"),
            ("language", language),
            ("smart_format", "true"),
            ("punctuate", "true"),
            ("mip_opt_out", "true"),
        ]
        if (model or "nova-3").startswith("nova-3"):
            params += [("keyterm", t) for t in clean_terms(vocabulary, limit=50)]
        body = await self._send(
            "POST",
            f"{self.base_url}/v1/listen",
            params=params,
            headers={"Authorization": f"Token {self._key}", "Content-Type": mime},
            content=audio,
        )
        try:
            alt = body["results"]["channels"][0]["alternatives"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Deepgram answered without a transcript") from exc
        meta = body.get("metadata") or {}
        duration = meta.get("duration")
        return Transcript(
            text=str(alt.get("transcript") or ""),
            duration_s=float(duration) if isinstance(duration, int | float) else None,
            request_id=str(meta["request_id"]) if meta.get("request_id") else None,
        )

    async def list_models(self) -> list[ModelInfo]:
        return list(MODELS)


__all__ = ["DeepgramAdapter"]
