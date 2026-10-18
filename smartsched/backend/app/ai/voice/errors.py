"""Voice refusals with Turkish and English text (``{code, message, message_tr, message_en, …}``, the gateway's
error shape). The frontend maps ``code`` to its own copy (VO-06 ``voice-errors.ts``)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

MESSAGES: dict[str, tuple[int, str, str]] = {
    "voice_not_configured": (
        409,
        "Sesle yazma açık değil ya da ses için bir model seçilmedi.",
        "Voice input is off or no voice model has been chosen.",
    ),
    "voice_consent_required": (
        403,
        "Sesli giriş için onayınız gerekiyor. Onayı Profil › Gizlilik bölümünden verebilirsiniz.",
        "Voice input needs your consent. You can give it under Profile › Privacy.",
    ),
    "not_permitted": (
        403,
        "Bu alana sesle yazma izniniz yok.",
        "You may not use voice input here.",
    ),
    "unknown_target": (
        422,
        "Sesle yazma bu alanda kullanılamaz.",
        "Voice input is not available for this field.",
    ),
    "unsupported_audio": (
        415,
        "Bu ses biçimi desteklenmiyor (WebM, Ogg, MP4, MP3 ya da WAV gönderin).",
        "This audio format is not supported (send WebM, Ogg, MP4, MP3 or WAV).",
    ),
    "too_large": (413, "Kayıt çok büyük.", "The recording is too large."),
    "too_long": (
        413,
        "Kayıt en fazla {max_seconds} saniye olabilir.",
        "Recordings can be at most {max_seconds} seconds.",
    ),
    "empty_audio": (422, "Ses algılanmadı. Tekrar deneyin.", "No audio was received. Try again."),
    "ai_voice_limit_reached": (
        429,
        "Sesli giriş sınırınıza ulaştınız ({used_min}/{limit_min} dk). Yazarak devam edebilirsiniz.",
        "You have reached your voice input limit ({used_min}/{limit_min} min). You can keep typing.",
    ),
    "ai_budget_exceeded": (
        429,
        "Bu ayın yapay zekâ bütçesi doldu.",
        "This month's AI budget is spent.",
    ),
    "rate_limited": (429, "Çok sık istek gönderildi; biraz bekleyin.", "Too many requests; wait a moment."),
    "too_many_concurrent": (
        429,
        "Önceki kayıt hâlâ yazıya dökülüyor; bitmesini bekleyin.",
        "The previous recording is still being transcribed; wait for it.",
    ),
    "ai_transfer_basis_missing": (
        409,
        "Bu ses hizmeti için KVKK aktarım kaydı yok; yönetici tamamlamalı.",
        "This voice service has no KVKK transfer record; an administrator must add it.",
    ),
    "provider_error": (
        502,
        "Ses yazıya dökülemedi. Tekrar deneyin ya da yazarak devam edin.",
        "The recording could not be transcribed. Try again or type instead.",
    ),
}


class _Fields(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "?"


class VoiceError(HTTPException):
    def __init__(self, code: str, **extra: Any) -> None:
        status, tr, en = MESSAGES[code]
        fields = _Fields({k: v for k, v in extra.items() if isinstance(v, int | float | str)})
        tr, en = tr.format_map(fields), en.format_map(fields)
        super().__init__(status, {"code": code, "message": en, "message_en": en, "message_tr": tr, **extra})
        self.code = code


__all__ = ["MESSAGES", "VoiceError"]
