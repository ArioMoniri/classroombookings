"""VO-01 speech core: the ``voice_stt`` feature, provider capabilities and declared regions / retention notes, model
modalities at sync, routes that accept only speech models, no fallback to the text default, the OpenAI-style
transcription request (multipart, ``language`` / ``languages``) and the SSRF guard on speech base URLs."""

from __future__ import annotations

import httpx
import pytest
from app.ai import gateway as gw
from app.ai import pipeline
from app.ai.context import FEATURE_LABELS, FEATURES
from app.ai.providers import PROVIDERS, ProviderUnsupported, UnsafeBaseURL, make_adapter
from app.ai.voice.openai_audio import OpenAIAudioAdapter
from app.ai.voice.registry import make_speech_adapter, model_modalities
from app.services import ai_usage as meter

from tests.ai.voice_support import KEY, clip, openai_stub, response
from tests.api_fixtures import login


@pytest.fixture(autouse=True)
def _reset():
    pipeline.reset_state()
    meter.reset_state()
    yield
    pipeline.TEST_TRANSPORT[0] = None
    pipeline.reset_state()
    meter.reset_state()


def test_voice_feature_is_personal_and_capped():
    assert "voice_stt" in FEATURES
    assert FEATURE_LABELS["voice_stt"] == ("Sesle yazma", "Voice input")
    assert "voice_stt" in gw.PERSONAL_FEATURES
    assert gw.DEFAULT_CAPS["voice_stt"] == {"timeout_s": 60, "max_audio_s": 120, "max_bytes": 5_000_000}


def test_capabilities_regions_and_retention_per_provider():
    caps = {p: set(s.capabilities) for p, s in PROVIDERS.items()}
    assert caps["anthropic"] == caps["bedrock"] == caps["vertex"] == {"text"}
    assert caps["openai"] == caps["azure_openai"] == caps["gemini"] == {"text", "stt"}
    assert caps["openrouter"] == caps["openai_compatible"] == {"text"}  # no on-prem / local speech (owner 2026-10-18)
    assert caps["azure_speech"] == caps["google_stt"] == caps["deepgram"] == {"stt"}
    for p in ("openai", "azure_openai", "gemini", "azure_speech", "google_stt", "deepgram"):
        spec = PROVIDERS[p].to_dict()
        assert spec["capabilities"] and spec["regions"], p
        assert spec["retention_tr"] and spec["retention_en"], p
    assert "eu" in PROVIDERS["deepgram"].regions and "eu" in PROVIDERS["google_stt"].regions


def test_model_modalities():
    for m in ("gpt-transcribe", "gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"):
        assert model_modalities("openai", m) == ["stt"], m
    assert model_modalities("openai", "gpt-5") == ["text"]
    assert model_modalities("openai", "gpt-4o-mini-tts") == ["tts"]
    assert model_modalities("azure_openai", "gpt-4o-mini-transcribe") == ["stt"]
    assert model_modalities("gemini", "gemini-2.5-flash") == ["text", "stt"]
    assert model_modalities("gemini", "gemini-embedding-001") == ["text"]
    assert model_modalities("deepgram", "nova-3") == ["stt"]
    assert model_modalities("anthropic", "claude-opus-5-5") == ["text"]


def test_text_adapter_refuses_a_speech_only_provider():
    with pytest.raises(ProviderUnsupported):
        make_adapter("deepgram", model="nova-3", secrets={"api_key": KEY})


async def test_sync_stores_modalities_and_routes_accept_only_speech_models(client):
    h = await login(client)
    openai_stub()
    assert (await client.put("/api/v1/ai/admin/providers/openai", json={"api_key": KEY}, headers=h)).status_code == 200
    r = await client.post("/api/v1/ai/admin/providers/openai/sync", headers=h)
    assert r.status_code == 200, r.text
    mods = {m["id"]: m["modalities"] for m in r.json()["models"]}
    assert mods == {
        "gpt-transcribe": ["stt"],
        "gpt-4o-mini-transcribe": ["stt"],
        "whisper-1": ["stt"],
        "gpt-5": ["text"],
    }
    # a Claude model cannot transcribe
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"voice_stt": {"provider": "anthropic", "model": "claude-opus-5-5"}}},
        headers=h,
    )
    assert r.status_code == 422
    codes = {e["code"] for e in r.json()["detail"]["errors"]}
    assert "model_not_speech" in codes
    err = next(e for e in r.json()["detail"]["errors"] if e["code"] == "model_not_speech")
    assert err["message_tr"] and err["message_en"]
    # a text model of a speech-capable provider neither
    r = await client.put(
        "/api/v1/ai/admin/routes", json={"features": {"voice_stt": {"provider": "openai", "model": "gpt-5"}}}, headers=h
    )
    assert r.status_code == 422 and r.json()["detail"]["errors"][0]["code"] == "model_not_speech"
    # a speech model on a text feature is refused
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"chat": {"provider": "openai", "model": "gpt-transcribe"}}},
        headers=h,
    )
    assert r.status_code == 422 and r.json()["detail"]["errors"][0]["code"] == "model_not_text"
    r = await client.put(
        "/api/v1/ai/admin/routes",
        json={"features": {"voice_stt": {"provider": "openai", "model": "gpt-transcribe"}}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["effective"]["voice_stt"]["source"] == "feature"


async def test_voice_route_never_follows_the_text_default(session):
    await gw.put_json(session, gw.ROUTES_KEY, {"default": {"provider": "anthropic", "model": "claude-opus-5-5"}})
    rr = await gw.resolve_route(session, "voice_stt")
    assert rr.source == "none" and rr.route.provider == "" and rr.route.model == ""
    assert (await gw.resolve_route(session, "chat")).source == "default"


async def test_openai_compatible_request_is_multipart_with_language():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response("openai_gpt_4o_mini_transcribe"))

    a = OpenAIAudioAdapter("openai", api_key=KEY, transport=httpx.MockTransport(handler))
    out = await a.transcribe(clip(), "audio/ogg", model="gpt-4o-mini-transcribe", language="tr", vocabulary=["B 204"])
    req = seen[0]
    assert req.method == "POST" and str(req.url) == "https://api.openai.com/v1/audio/transcriptions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert req.headers["content-type"].startswith("multipart/form-data")
    body = req.content.decode("latin-1")
    assert 'name="model"\r\n\r\ngpt-4o-mini-transcribe' in body
    assert 'name="language"\r\n\r\ntr' in body
    assert 'name="response_format"\r\n\r\njson' in body
    assert 'name="prompt"' in body and "B 204" in body.encode("latin-1").decode("utf-8", "ignore")
    assert 'name="file"; filename="audio.ogg"' in body and "Content-Type: audio/ogg" in body
    assert out.text.startswith("Şu cümle") and out.input_tokens == 61 and out.output_tokens == 19


async def test_gpt_transcribe_uses_languages_and_keywords():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response("openai_gpt_transcribe"))

    a = OpenAIAudioAdapter("openai", api_key=KEY, transport=httpx.MockTransport(handler))
    out = await a.transcribe(clip(), "audio/ogg", model="gpt-transcribe", language="tr", vocabulary=["MAT 101"])
    body = seen[0].content.decode("utf-8", "ignore")
    assert 'name="languages[]"\r\n\r\ntr' in body and 'name="keywords[]"\r\n\r\nMAT 101' in body
    assert 'name="language"\r\n' not in body
    assert out.duration_s == pytest.approx(5.2) and out.language == "tr"


async def test_azure_openai_sends_the_api_key_header():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response("openai_gpt_4o_mini_transcribe"))

    a = make_speech_adapter(
        "azure_openai",
        secrets={"api_key": KEY},
        config={"base_url": "https://contoso.openai.azure.com/openai/v1"},
        transport=httpx.MockTransport(handler),
    )
    await a.transcribe(clip(), "audio/ogg", model="gpt-4o-mini-transcribe", language="tr")
    assert str(seen[0].url) == "https://contoso.openai.azure.com/openai/v1/audio/transcriptions"
    assert seen[0].headers["api-key"] == KEY and "authorization" not in seen[0].headers


async def test_a_private_speech_base_url_is_refused():
    a = OpenAIAudioAdapter("openai", api_key=KEY, base_url="http://10.1.2.3/v1")
    with pytest.raises(UnsafeBaseURL):
        await a.transcribe(clip(), "audio/ogg", model="whisper-1", language="tr")
    with pytest.raises(UnsafeBaseURL):
        await make_speech_adapter(
            "deepgram", secrets={"api_key": KEY}, config={"base_url": "https://169.254.169.254"}
        ).transcribe(clip(), "audio/ogg", model="nova-3", language="tr")
