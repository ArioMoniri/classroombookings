"""Live voice smoke test against OpenAI: the bundled Turkish clip through the real ``audio/transcriptions`` API.
Skipped unless OPENAI_API_KEY is set (costs well under a cent). Checks what the fixtures cannot: the key works and
the request shape is accepted for the configured model (``SMARTSCHED_LIVE_STT_MODEL``, default
gpt-4o-mini-transcribe)."""

from __future__ import annotations

import os

import pytest
from app.ai.voice.assets import CLIP_MIME, test_clip
from app.ai.voice.registry import make_speech_adapter

pytestmark = pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")


async def test_live_openai_transcribes_the_turkish_clip():
    adapter = make_speech_adapter("openai", secrets={"api_key": os.environ["OPENAI_API_KEY"]}, config={})
    model = os.environ.get("SMARTSCHED_LIVE_STT_MODEL", "gpt-4o-mini-transcribe")
    out = await adapter.transcribe(test_clip(), CLIP_MIME, model=model, language="tr", vocabulary=["B 204"])
    assert "cümle" in out.text.lower(), out.text
