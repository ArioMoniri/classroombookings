"""The speech adapter contract (VO-01): one clip in, one :class:`Transcript` out.

Every cloud speech provider (OpenAI / Azure OpenAI ``audio/transcriptions``, Azure AI Speech fast transcription,
Gemini audio input, Google Cloud Speech-to-Text v2 Chirp 3, Deepgram) implements :class:`SpeechAdapter`. The REST
adapters share :class:`HttpSpeechAdapter`: plain ``httpx`` (no provider SDK), the SSRF guard on the resolved address
before every real request (``app/ai/providers/url_guard.py``), and errors reduced to a short
:class:`~app.ai.providers.base.ProviderError` that never carries the upstream body (it can echo the audio's words)
or the key.

The audio bytes live only in the caller's memory: adapters send them and keep nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from app.ai.providers.base import ModelInfo, ProviderError
from app.ai.providers.openai_compat import _status_error
from app.ai.providers.url_guard import ensure_safe

#: ISO-639-1 -> the locale the locale-based providers (Azure, Google) expect
LOCALES = {"tr": "tr-TR", "en": "en-US"}
#: the file extension each accepted container is sent with
EXTENSIONS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav"}


@dataclass
class Transcript:
    """What a provider heard. ``duration_s`` is the provider's own audio length when it reports one."""

    text: str
    duration_s: float | None = None
    language: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    request_id: str | None = None


def locale(language: str) -> str:
    return LOCALES.get(language, language)


def clean_terms(vocabulary: Sequence[str], *, limit: int, max_len: int = 48) -> list[str]:
    """Vocabulary hints a provider accepts: one line each, no ``<`` / ``>`` (OpenAI rejects them), de-duplicated."""
    out: list[str] = []
    for term in vocabulary:
        t = " ".join(str(term).replace("<", " ").replace(">", " ").split())[:max_len]
        if t and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


class SpeechAdapter(ABC):
    """One speech-to-text provider."""

    name: str = ""

    @abstractmethod
    async def transcribe(
        self, audio: bytes, mime: str, *, model: str, language: str, vocabulary: Sequence[str] = ()
    ) -> Transcript: ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...


class HttpSpeechAdapter(SpeechAdapter):
    """Shared REST plumbing: SSRF guard, timeout, status -> short error, JSON body."""

    label = "the speech provider"

    def __init__(
        self, *, base_url: str, timeout_s: float = 60.0, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._transport = transport

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self.base_url!r})"

    async def _send(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if self._transport is None:  # a real socket: SSRF guard after DNS resolution (docs/SECURITY.md R12)
            await ensure_safe(url, allow_local=False)
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                resp = await http.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.label} did not answer in time") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"could not reach {self.label} ({type(exc).__name__})") from exc
        if resp.status_code >= 400:
            raise _status_error(resp.status_code, self.label)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"{self.label} answered something that is not JSON") from exc
        if not isinstance(data, dict):
            raise ProviderError(f"{self.label} answered something that is not a JSON object")
        return data


__all__ = ["EXTENSIONS", "LOCALES", "HttpSpeechAdapter", "SpeechAdapter", "Transcript", "clean_terms", "locale"]
