# Voice provider response fixtures

Shaped after each provider's API reference (read 2026-10-17), not captured from a live account. The transcript is
the bundled test clip's speech (`app/ai/voice/assets/tr-test.ogg`).

| File | Provider / endpoint | Reference |
|---|---|---|
| openai_gpt_transcribe.json | OpenAI `POST /v1/audio/transcriptions`, `gpt-transcribe` (`languages`, duration usage) | developers.openai.com/api/docs/guides/speech-to-text, API reference "Create transcription" |
| openai_gpt_4o_mini_transcribe.json | same, `gpt-4o-mini-transcribe` (token usage) | same |
| azure_fast.json | Azure AI Speech fast transcription `transcriptions:transcribe?api-version=2025-10-15` | learn.microsoft.com/azure/ai-services/speech-service/fast-transcription-create |
| gemini.json | Gemini API `models/{m}:generateContent` with inline audio and a JSON response schema | ai.google.dev/gemini-api/docs/audio |
| google_chirp3.json | Cloud Speech-to-Text v2 `recognizers/_:recognize`, model `chirp_3`, location `eu` | docs.cloud.google.com/speech-to-text/docs/models/chirp-3 |
| deepgram.json | Deepgram `POST /v1/listen` (EU endpoint `api.eu.deepgram.com`), Nova-3 | developers.deepgram.com/reference/speech-to-text/listen-pre-recorded |
