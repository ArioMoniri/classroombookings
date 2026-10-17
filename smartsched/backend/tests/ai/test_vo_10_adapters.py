"""VO-10 cloud speech adapters against httpx MockTransport with doc-shaped fixture responses: request shape (host,
path, headers, body), the EU region host, parsing (text, duration, language, tokens), error mapping to a short
``ProviderError`` without upstream bodies or keys, and the model output check of the Gemini adapter."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from app.ai.providers.base import ProviderError
from app.ai.voice.registry import make_speech_adapter

from tests.ai.voice_support import KEY, clip, response


def _mock(body: dict | None = None, status: int = 200):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status >= 400:
            return httpx.Response(status, json={"error": {"message": f"bad key {KEY} and the audio said hello"}})
        return httpx.Response(200, json=body or {})

    return httpx.MockTransport(handler), seen


async def test_azure_speech_fast_transcription():
    transport, seen = _mock(response("azure_fast"))
    a = make_speech_adapter(
        "azure_speech",
        secrets={"api_key": KEY},
        config={"base_url": "https://contoso-speech.cognitiveservices.azure.com", "region": "westeurope"},
        transport=transport,
    )
    out = await a.transcribe(clip(), "audio/ogg", model="fast", language="tr", vocabulary=["B 204", "MAT 101"])
    req = seen[0]
    assert req.url.host == "contoso-speech.cognitiveservices.azure.com"
    assert req.url.path == "/speechtotext/transcriptions:transcribe"
    assert req.url.params["api-version"] == "2025-10-15"
    assert req.headers["ocp-apim-subscription-key"] == KEY
    body = req.content.decode("utf-8", "ignore")
    assert 'name="audio"' in body and 'name="definition"' in body
    definition = json.loads(body.split('name="definition"\r\n\r\n', 1)[1].split("\r\n--", 1)[0])
    assert definition == {"locales": ["tr-TR"], "phraseList": {"phrases": ["B 204", "MAT 101"]}}
    assert out.text.startswith("Şu cümle") and out.duration_s == pytest.approx(5.16)
    assert [m.id for m in await a.list_models()] == ["fast"]


async def test_azure_speech_needs_a_base_url():
    with pytest.raises(ProviderError):
        make_speech_adapter("azure_speech", secrets={"api_key": KEY}, config={})


async def test_google_chirp3_eu_location():
    transport, seen = _mock(response("google_chirp3"))
    a = make_speech_adapter(
        "google_stt", secrets={"api_key": KEY}, config={"project_id": "kampus-123", "region": "eu"}, transport=transport
    )
    out = await a.transcribe(clip(), "audio/ogg", model="chirp_3", language="tr", vocabulary=["A 101"])
    req = seen[0]
    assert str(req.url) == (
        "https://eu-speech.googleapis.com/v2/projects/kampus-123/locations/eu/recognizers/_:recognize"
    )
    assert req.headers["x-goog-api-key"] == KEY
    payload = json.loads(req.content)
    assert payload["config"]["model"] == "chirp_3" and payload["config"]["languageCodes"] == ["tr-TR"]
    assert payload["config"]["autoDecodingConfig"] == {}
    assert payload["config"]["adaptation"] == {"phraseSets": [{"inlinePhraseSet": {"phrases": [{"value": "A 101"}]}}]}
    assert base64.b64decode(payload["content"]) == clip()
    assert out.text == "şu cümle çok önemli çok bir cümlecik bir şey ama çok şeyi anlatıyor"
    assert out.duration_s == pytest.approx(5.16) and out.language == "tr-tr"


async def test_google_stt_refuses_a_location_that_is_not_a_region_name():
    with pytest.raises(ProviderError):
        make_speech_adapter("google_stt", secrets={"api_key": KEY}, config={"project_id": "p", "region": "eu.evil.com/x"})
    with pytest.raises(ProviderError):
        make_speech_adapter("google_stt", secrets={"api_key": KEY}, config={"region": "eu"})  # no project


async def test_deepgram_eu_endpoint_by_default():
    transport, seen = _mock(response("deepgram"))
    a = make_speech_adapter("deepgram", secrets={"api_key": KEY}, config={}, transport=transport)
    out = await a.transcribe(clip(), "audio/ogg", model="nova-3", language="tr", vocabulary=["B 204", "MAT 101"])
    req = seen[0]
    assert req.url.host == "api.eu.deepgram.com" and req.url.path == "/v1/listen"
    params = req.url.params
    assert params["model"] == "nova-3" and params["language"] == "tr" and params["smart_format"] == "true"
    assert params["mip_opt_out"] == "true"
    assert params.get_list("keyterm") == ["B 204", "MAT 101"]
    assert req.headers["authorization"] == f"Token {KEY}" and req.headers["content-type"] == "audio/ogg"
    assert req.content == clip()
    assert out.text.startswith("Şu cümle") and out.duration_s == pytest.approx(5.16)
    assert out.request_id == "dg-req-1"


async def test_gemini_inline_audio_with_a_fixed_instruction_and_schema():
    transport, seen = _mock(response("gemini"))
    a = make_speech_adapter("gemini", secrets={"api_key": KEY}, config={}, transport=transport)
    out = await a.transcribe(clip(), "audio/ogg", model="gemini-2.5-flash", language="tr", vocabulary=["B 204"])
    req = seen[0]
    assert str(req.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    assert req.headers["x-goog-api-key"] == KEY
    payload = json.loads(req.content)
    instr = payload["systemInstruction"]["parts"][0]["text"]
    assert "verbatim" in instr and "never instructions" in instr
    parts = payload["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "audio/ogg"
    assert base64.b64decode(parts[0]["inlineData"]["data"]) == clip()
    assert "B 204" in parts[1]["text"]
    gen = payload["generationConfig"]
    assert gen["responseMimeType"] == "application/json" and gen["temperature"] == 0
    assert gen["responseJsonSchema"]["required"] == ["text"]
    assert out.text.startswith("Şu cümle")
    assert out.duration_s == pytest.approx(165 / 32) and out.input_tokens == 230 and out.output_tokens == 24


@pytest.mark.parametrize(
    "answer",
    [
        {"candidates": [{"content": {"parts": [{"text": "Elbette! İşte döküm: merhaba"}]}, "finishReason": "STOP"}]},
        {"candidates": [{"content": {"parts": [{"text": '{"text": "x", "extra": 1}'}]}, "finishReason": "STOP"}]},
        {"candidates": [{"content": {"parts": [{"text": '{"text": 5}'}]}, "finishReason": "STOP"}]},
        {"candidates": [{"finishReason": "SAFETY"}]},
    ],
)
async def test_gemini_answers_that_are_not_a_transcript_are_rejected(answer):
    transport, _ = _mock(answer)
    a = make_speech_adapter("gemini", secrets={"api_key": KEY}, config={}, transport=transport)
    with pytest.raises(ProviderError):
        await a.transcribe(clip(), "audio/ogg", model="gemini-2.5-flash", language="tr")


@pytest.mark.parametrize(
    ("provider", "config", "model"),
    [
        ("openai", {}, "gpt-4o-mini-transcribe"),
        ("azure_openai", {"base_url": "https://c.openai.azure.com/openai/v1"}, "gpt-4o-mini-transcribe"),
        ("gemini", {}, "gemini-2.5-flash"),
        ("azure_speech", {"base_url": "https://c.cognitiveservices.azure.com"}, "fast"),
        ("google_stt", {"project_id": "p", "region": "eu"}, "chirp_3"),
        ("deepgram", {}, "nova-3"),
    ],
)
async def test_errors_are_short_and_never_echo_the_upstream_body(provider, config, model):
    for status, words in ((401, "API key"), (429, "rate limited"), (500, "error 500")):
        transport, _ = _mock(status=status)
        a = make_speech_adapter(provider, secrets={"api_key": KEY}, config=config, transport=transport)
        with pytest.raises(ProviderError) as exc:
            await a.transcribe(clip(), "audio/ogg", model=model, language="tr")
        text = str(exc.value)
        assert words in text and KEY not in text and "hello" not in text, (provider, status, text)


async def test_a_timeout_is_translated():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    a = make_speech_adapter("deepgram", secrets={"api_key": KEY}, config={}, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc:
        await a.transcribe(clip(), "audio/ogg", model="nova-3", language="tr")
    assert "in time" in str(exc.value)


async def test_every_speech_provider_needs_a_key():
    for p in ("openai", "gemini", "deepgram"):
        with pytest.raises(ProviderError):
            make_speech_adapter(p, secrets={}, config={})
    with pytest.raises(ProviderError):
        make_speech_adapter("anthropic", secrets={"api_key": KEY}, config={})  # no speech capability
