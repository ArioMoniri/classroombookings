"""Sample data for previews, "test gönder" and the renderer tests: rooms, periods and people of the real Bahar 2026
fixtures (A 201 is the TIP room of the weekly grid, BME 419 the 102-seat cohort of docs/DATA_ANALYSIS.md; the
18-period grid starts 08:30, P3 10:10-11:00)."""

from __future__ import annotations

from typing import Any

BASE = "https://plan.uni.edu.tr"

_WHAT = "A 201, 18.02.2026 P3-P5 10:10-12:30"
_ITEMS = {
    "tr": ["A 201, 18 Şubat 2026 Çarşamba P3 10:10-11:00", "A 201, 25 Şubat 2026 Çarşamba P3 10:10-11:00"],
    "en": ["A 201, Wednesday, 18 February 2026 P3 10:10-11:00", "A 201, Wednesday, 25 February 2026 P3 10:10-11:00"],
}

_COMMON: dict[str, Any] = {"name": "Ayşe Yılmaz", "org": "Örnek Üniversitesi", "base_url": BASE}

_BY_KIND: dict[str, dict[str, dict[str, Any] | Any]] = {
    "password_reset": {"*": {"code": "Kq7Zp2Lm9Xw4Rt8Vb3Nc", "valid_hours": 24, "cta_url": f"{BASE}/reset-password"}},
    "invitation": {
        "*": {
            "inviter": "Fatih Demir",
            "provider": "microsoft",
            "provider_name": "Kampüs girişi",
            "cta_url": f"{BASE}/login?invite=ornek",
        },
        "tr": {"expires": "16 Kasım 2026", "role": "Öğretim elemanı"},
        "en": {"expires": "16 November 2026", "role": "Teacher"},
    },
    "account_created": {
        "*": {"username": "ayse.yilmaz", "actor": "Fatih Demir", "method": "local", "valid_hours": 24, "cta_url": f"{BASE}/login"},
        "tr": {"role": "Öğretim elemanı"},
        "en": {"role": "Teacher"},
    },
    "new_device_sign_in": {
        "*": {"cta_url": f"{BASE}/profile#security"},
        "tr": {"when": "17 Ekim 2026 20:41", "device": "Safari, iPhone (İstanbul)"},
        "en": {"when": "17 October 2026 20:41", "device": "Safari, iPhone (Istanbul)"},
    },
    "booking_created": {"*": {"actor": "Fatih Demir", "count": 2, "cta_url": f"{BASE}/bookings/mine"}, "items": True},
    "room_owner_booking": {
        "*": {"actor": "Fatih Demir", "room": "A 201", "series": "", "cta_url": f"{BASE}/bookings"},
        "items": True,
    },
    "approval_submitted": {"*": {"what": _WHAT, "cta_url": f"{BASE}/bookings/mine?request=7"}},
    "approval_requested": {"*": {"who": "Ayşe Yılmaz", "what": _WHAT, "cta_url": f"{BASE}/approvals?request=7"}},
    "approval_approved": {"*": {"who": "Gözde Ayrancıgil", "what": _WHAT, "cta_url": f"{BASE}/bookings/mine?request=7"}},
    "approval_rejected": {
        "*": {
            "who": "Gözde Ayrancıgil",
            "what": _WHAT,
            "suggestions": ["A 101", "B 207"],
            "cta_url": f"{BASE}/find-room",
        },
        "tr": {"reason": "Kapasite yetersiz: 102 kişilik BME 419 için küçük"},
        "en": {"reason": "Not enough seats: too small for the 102-seat BME 419"},
    },
    "approval_withdrawn": {"*": {"who": "Ayşe Yılmaz", "what": _WHAT, "cta_url": f"{BASE}/approvals"}},
    "approval_expired": {"*": {"what": _WHAT, "cta_url": f"{BASE}/reserve"}},
    "booking_cancelled": {
        "*": {"actor": "Fatih Demir", "count": 2, "reason": "replaced_by_series:8", "cta_url": f"{BASE}/find-room"},
        "items": True,
    },
    "booking_reminder": {
        "*": {"room": "A 201", "period": "P3 10:10-11:00", "when": "day_before", "cta_url": f"{BASE}/bookings/mine"},
        "tr": {"date": "18 Şubat 2026 Çarşamba"},
        "en": {"date": "Wednesday, 18 February 2026"},
    },
    "series_created": {
        "*": {"who": "Fatih Demir", "room": "A 201", "count": 14, "series_id": 8, "cta_url": f"{BASE}/bookings/mine"},
        "tr": {"pattern": "her Çarşamba P3"},
        "en": {"pattern": "every Wednesday P3"},
        "items": True,
    },
    "series_changed": {
        "*": {"who": "Fatih Demir", "room": "A 201", "series_id": 8, "cta_url": f"{BASE}/bookings/mine"},
        "tr": {"change": "saat P3 yerine P4 (11:00-11:50)"},
        "en": {"change": "time P4 (11:00-11:50) instead of P3"},
        "items": True,
    },
    "calendar_consent": {"*": {"state": "on", "provider": "google", "cta_url": f"{BASE}/profile#privacy"}},
    "kvkk_request": {
        "*": {"request_kind": "info", "status": "done", "cta_url": f"{BASE}/profile#privacy"},
        "tr": {"detail": "Verilerinizin kopyası Profil > Gizlilik bölümünde 7 gün indirilebilir."},
        "en": {"detail": "A copy of your data can be downloaded under Profile > Privacy for 7 days."},
    },
    "ai_usage_alert": {
        "*": {"who": "Fatih Demir", "percent": 80, "used": "400.000", "limit": "500.000", "cta_url": f"{BASE}/admin/ai"},
        "tr": {"reset_date": "1 Kasım 2026"},
        "en": {"reset_date": "1 November 2026"},
    },
    "ops_alert": {
        "*": {"severity": "critical", "count": 12, "cta_url": f"{BASE}/admin/ops"},
        "tr": {
            "service": "Çözücü",
            "title": "çözücü işleri zaman aşımına uğruyor",
            "detail": "Son 15 dakikada 12 iş 900 sn sınırını aştı.",
            "first_seen": "17 Ekim 2026 20:05",
        },
        "en": {
            "service": "Solver",
            "title": "solver jobs time out",
            "detail": "12 jobs passed the 900 s limit in the last 15 minutes.",
            "first_seen": "17 October 2026 20:05",
        },
    },
    "timetable_published": {
        "*": {"term": "2026-BAHAR", "cta_url": f"{BASE}/timetable"},
        "tr": {"items": ["MAT 112 (1. şube): Salı P3 A 204 yerine Perşembe P5 A 101"]},
        "en": {"items": ["MAT 112 (section 1): Thursday P5 A 101 instead of Tuesday P3 A 204"]},
    },
    "booking_conflict_resolved": {
        "*": {"term": "2026-BAHAR", "cta_url": f"{BASE}/bookings/mine"},
        "tr": {"items": ["A 201, 18 Şubat 2026 P3: A 106 dersliğine taşındı"]},
        "en": {"items": ["A 201, 18 February 2026 P3: moved to A 106"]},
    },
    "preference_accepted": {
        "*": {"who": "Fatih Demir", "course": "BME 419", "cta_url": f"{BASE}/moderation/me"},
        "tr": {"what": "Çarşamba sabahları"},
        "en": {"what": "Wednesday mornings"},
    },
    "preference_rejected": {
        "*": {"who": "Fatih Demir", "course": "BME 419", "cta_url": f"{BASE}/moderation/me"},
        "tr": {"what": "Çarşamba sabahları", "reason": "Çarşamba sabahı ortak dersler var"},
        "en": {"what": "Wednesday mornings", "reason": "Shared lectures run on Wednesday mornings"},
    },
    "smtp_test": {"*": {"host": "smtp.uni.edu.tr"}},
}


def sample_context(kind: str, locale: str = "tr") -> dict[str, Any]:
    """Preview data for ``kind`` in ``locale`` (tr / en)."""
    lang = "tr" if locale == "tr" else "en"
    entry = _BY_KIND.get(kind, {})
    out: dict[str, Any] = dict(_COMMON)
    out.update(entry.get("*", {}))  # type: ignore[arg-type]
    out.update(entry.get(lang, {}))  # type: ignore[arg-type]
    if entry.get("items") is True:
        out["items"] = list(_ITEMS[lang])
    return out
