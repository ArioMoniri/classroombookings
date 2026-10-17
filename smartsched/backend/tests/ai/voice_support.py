"""Shared helpers for the voice tests (VO-01…VO-10): a scriptable fake speech provider (tests only, injected by
monkeypatching :func:`app.ai.voice.registry.make_speech_adapter`; it is never registered), in-memory clips, and
the admin set-up steps (provider key, synced speech models, the voice route, a KVKK transfer record, consent)."""

from __future__ import annotations

import io
import json
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from app.ai import pipeline
from app.ai.voice.speech import SpeechAdapter, Transcript
from app.core.db import get_session_factory
from app.core.security import hash_password
from app.models import User

from tests.api_fixtures import login

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "voice"
RESPONSES = FIXTURES / "responses"
KEY = "sk-voice-test-key-1234567890"


def response(name: str) -> dict[str, Any]:
    return json.loads((RESPONSES / f"{name}.json").read_text(encoding="utf-8"))


def wav(seconds: float, rate: int = 8000) -> bytes:
    """A silent mono 8-bit WAV of ``seconds`` (the header carries the exact duration)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(b"\x80" * int(seconds * rate))
    return buf.getvalue()


def _vint(n: int) -> bytes:
    """An EBML size of 8 bytes (always valid)."""
    return bytes([0x01]) + n.to_bytes(7, "big")


def _el(id_bytes: bytes, payload: bytes) -> bytes:
    return id_bytes + _vint(len(payload)) + payload


def webm(seconds: float, *, with_duration: bool = True) -> bytes:
    """A minimal WebM: EBML header, Segment > Info (TimecodeScale 1 ms, optional Duration) > one Cluster per second
    with one SimpleBlock (what MediaRecorder writes; it usually omits Duration)."""
    header = _el(b"\x1a\x45\xdf\xa3", _el(b"\x42\x82", b"webm"))
    info_payload = _el(b"\x2a\xd7\xb1", (1_000_000).to_bytes(3, "big"))
    if with_duration:
        info_payload += _el(b"\x44\x89", struct.pack(">d", seconds * 1000.0))
    body = _el(b"\x15\x49\xa9\x66", info_payload)
    t = 0
    while t <= int(seconds * 1000) - 1000:
        block = b"\x81" + struct.pack(">h", 980) + b"\x80" + b"\x00" * 40
        body += _el(b"\x1f\x43\xb6\x75", _el(b"\xe7", t.to_bytes(4, "big")) + _el(b"\xa3", block))
        t += 1000
    # Segment of unknown size (0x01FFFFFFFFFFFFFF), like a live recording
    return header + b"\x18\x53\x80\x67" + b"\x01\xff\xff\xff\xff\xff\xff\xff" + body


def clip() -> bytes:
    """The bundled 5 s Turkish clip (Ogg Opus) the admin test call sends."""
    from app.ai.voice.assets import test_clip

    return test_clip()


@dataclass
class FakeSpeech(SpeechAdapter):
    """Scripted speech provider: answers queued :class:`Transcript` objects (or raises queued exceptions) and
    records every call (audio length, mime, model, language, vocabulary)."""

    name: str = "fake"
    script: list[Any] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def transcribe(self, audio, mime, *, model, language, vocabulary=()):  # type: ignore[no-untyped-def]
        self.calls.append(
            {"bytes": len(audio), "mime": mime, "model": model, "language": language, "vocabulary": list(vocabulary)}
        )
        nxt = self.script.pop(0) if self.script else Transcript(text="B 204 numaralı salonda", duration_s=3.0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    async def list_models(self):  # type: ignore[no-untyped-def]
        return []


def install_fake(monkeypatch, *answers: Any) -> FakeSpeech:
    from app.ai.voice import registry

    fake = FakeSpeech(script=list(answers))
    made: list[str] = []

    def _make(provider, **_kw):  # type: ignore[no-untyped-def]
        made.append(provider)
        fake.name = provider
        return fake

    monkeypatch.setattr(registry, "make_speech_adapter", _make)
    fake.made = made  # type: ignore[attr-defined]
    return fake


def openai_stub(models: tuple[str, ...] = ("gpt-transcribe", "gpt-4o-mini-transcribe", "whisper-1", "gpt-5")):
    """An OpenAI-shaped HTTP stub (``/models``, ``/audio/transcriptions``, ``/chat/completions``)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        if path.endswith("/audio/transcriptions"):
            return httpx.Response(200, json=response("openai_gpt_4o_mini_transcribe"))
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 1},
            },
        )

    pipeline.TEST_TRANSPORT[0] = httpx.MockTransport(handler)
    return seen


async def add_user(email: str, role: str) -> dict[str, str]:
    async with get_session_factory()() as s:
        s.add(User(email=email, password_hash=hash_password("parola-1234"), role=role, full_name=email.split("@")[0]))
        await s.commit()
    return {"email": email}


async def configure(
    client,
    *,
    provider: str = "openai",
    model: str = "gpt-4o-mini-transcribe",
    transfer: bool = True,
    enable: bool = True,
    fallback: tuple[str, str] | None = None,
    consent: bool = True,
) -> dict[str, str]:
    """Admin: key + sync (OpenAI stub) + voice route + transfer record + voice on; the admin's own consent."""
    h = await login(client)
    providers = [provider] + ([fallback[0]] if fallback else [])
    for p in providers:
        body: dict[str, Any] = {"api_key": KEY}
        if p == "azure_openai":
            body["base_url"] = "https://contoso.openai.azure.com/openai/v1"
        if transfer:
            body["transfer"] = {"region": "eu", "kvkk_mechanism": "standard_contract", "processes_voice": True}
        r = await client.put(f"/api/v1/ai/admin/providers/{p}", json=body, headers=h)
        assert r.status_code == 200, r.text
        r = await client.post(f"/api/v1/ai/admin/providers/{p}/sync", headers=h)
        assert r.status_code == 200 and r.json()["ok"], r.text
    route: dict[str, Any] = {"provider": provider, "model": model}
    if fallback:
        route.update(fallback_provider=fallback[0], fallback_model=fallback[1])
    r = await client.put("/api/v1/ai/admin/routes", json={"features": {"voice_stt": route}}, headers=h)
    assert r.status_code == 200, r.text
    if enable:
        r = await client.put("/api/v1/ai/admin/voice", json={"enabled": True}, headers=h)
        assert r.status_code == 200, r.text
    if consent:
        r = await client.post("/api/v1/me/consents/voice", headers=h)
        assert r.status_code == 200, r.text
    return h


async def transcribe(client, headers, audio: bytes, mime: str = "audio/wav", *, feature: str = "chat", lang="tr"):
    return await client.post(
        f"/api/v1/ai/voice/transcribe?feature={feature}&lang={lang}",
        content=audio,
        headers={**headers, "Content-Type": mime},
    )
