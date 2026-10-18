"""Voice input for the AI features (VO-01…VO-04, VO-10; docs/research/2026-10-17-voice-ai.md).

Claude has no audio input, so voice is one speech-to-text step in front of the unchanged text pipeline:

1. ``POST /api/v1/ai/voice/transcribe`` takes one clip (≤ 120 s, ≤ 5 MB; WebM / Ogg / MP4 / MP3 / WAV) from a
   person who holds the KVKK consent ``voice``, sends it to the cloud speech model the admins routed
   ``voice_stt`` to (OpenAI, Azure OpenAI, Azure AI Speech, Gemini, Google Cloud STT Chirp 3, Deepgram EU), and
   returns the transcript **to the same person for review**. The audio is never stored (memory only, retention 0)
   and neither audio nor transcript is logged; one ``ai_usage`` row meters the audio seconds and the cost.
2. The person edits the text and sends it through the feature they spoke for (chat, rules, the guard bench):
   that endpoint runs the full text pipeline (input guard, injection check, redaction, limits) exactly as for
   typed text.

Modules: :mod:`.speech` (adapter contract), :mod:`.registry` (capabilities, modalities, factory), one module per
provider, :mod:`.audio` (type / magic bytes / length), :mod:`.vocabulary` (codes, never names), :mod:`.run` (the
transcription flow and the status), :mod:`.errors` (TR/EN refusals). Tests inject a fake adapter by monkeypatching
:func:`.registry.make_speech_adapter`; there is no fake in the app.
"""
