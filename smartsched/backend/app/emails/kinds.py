"""The catalogue of e-mail kinds: one entry per message the system sends (or can send).

``kind`` is the outbox ``kind`` (``notification_outbox.kind``): a ``notify_dispatch`` event with ``_`` for ``.``
(``approval.rejected`` -> ``approval_rejected``) or the name a direct sender uses (``password_reset``, ``smtp_test``,
``kvkk_request``). ``sender`` tells the admin screen who sends it today: ``wired`` (a send path in this repository
renders it), ``template`` (the template ships; the lane named in ``owner`` wires its send path).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KindSpec:
    kind: str
    label_tr: str
    label_en: str
    #: who receives it (shown in the template list)
    audience_tr: str
    audience_en: str
    tone: str = "info"  # info | success | danger | warning | neutral
    #: shipped string keys (set "email"); ``None`` = derived ``<kind>.<part>``
    subject_key: str | None = None
    intro_key: str | None = None
    #: enum fields whose value is shown through ``<kind>.<field>.<value>``
    enums: tuple[str, ...] = ()
    #: placeholders an admin override may use (shown in the editor)
    placeholders: tuple[str, ...] = ("name", "org")
    #: the panel path of the button when the sender gives only a relative link or none
    path: str | None = None
    sender: str = "wired"
    owner: str = "W3-MAIL"
    #: the subject / intro of a wired send already passed through the translations (``bookings_i18n.text``), so the
    #: renderer must not apply the override twice
    caller_applies_overrides: bool = False

    @property
    def keys(self) -> dict[str, str]:
        return {
            "subject": self.subject_key or f"{self.kind}.subject",
            "heading": f"{self.kind}.heading",
            "intro": self.intro_key or f"{self.kind}.intro",
            "cta": f"{self.kind}.cta",
            "preheader": f"{self.kind}.preheader",
            "note": f"{self.kind}.note",
        }


_K = KindSpec
KINDS: dict[str, KindSpec] = {
    s.kind: s
    for s in (
        _K(
            "password_reset",
            "Parola sıfırlama",
            "Password reset",
            "Parolasını unutan kişi",
            "The person who forgot their password",
            placeholders=("name", "org", "valid_hours"),
            path="/reset-password",
        ),
        _K(
            "invitation",
            "Davet (yerel ve kimlik sağlayıcı)",
            "Invitation (local and identity provider)",
            "Davet edilen kişi",
            "The invited person",
            enums=("provider",),
            placeholders=("name", "org", "inviter", "provider", "expires"),
            path="/login",
            sender="template",
            owner="W3-IDP",
        ),
        _K(
            "account_created",
            "Hesap açıldı / hoş geldiniz",
            "Account created / welcome",
            "Yeni kullanıcı",
            "The new user",
            tone="success",
            placeholders=("name", "org", "username"),
            path="/login",
            sender="template",
            owner="W3-IDP",
        ),
        _K(
            "new_device_sign_in",
            "Yeni cihazdan giriş",
            "Sign-in from a new device",
            "Hesabın sahibi",
            "The account owner",
            tone="warning",
            placeholders=("name", "org", "when", "device"),
            path="/profile#security",
            sender="template",
            owner="W3-SEC",
        ),
        _K(
            "booking_created",
            "Rezervasyon yapıldı",
            "Booking confirmed",
            "Adına rezervasyon yapılan kişi",
            "The person a booking was made for",
            tone="success",
            intro_key="booking_created.body",
            placeholders=("actor", "count", "items"),
            path="/bookings/mine",
            caller_applies_overrides=True,
        ),
        _K(
            "room_owner_booking",
            "Sorumlu olunan odaya rezervasyon",
            "Booking in a room you look after",
            "Derslik sorumlusu",
            "The room owner",
            subject_key="room_owner.subject",
            intro_key="room_owner.body",
            placeholders=("actor", "room", "series", "items"),
            path="/bookings",
            caller_applies_overrides=True,
        ),
        _K(
            "approval_submitted",
            "Talep alındı (talep edene)",
            "Request submitted (to the requester)",
            "Talep eden",
            "The requester",
            placeholders=("name", "org", "what"),
            path="/bookings/mine",
            sender="template",
        ),
        _K(
            "approval_requested",
            "Yeni talep (onaylayana)",
            "New request (to the approver)",
            "Onaylayıcılar",
            "Approvers",
            tone="warning",
            placeholders=("who", "what"),
            path="/approvals",
        ),
        _K(
            "approval_approved",
            "Talep onaylandı",
            "Request approved",
            "Talep eden",
            "The requester",
            tone="success",
            placeholders=("name", "who", "what"),
            path="/bookings/mine",
        ),
        _K(
            "approval_rejected",
            "Talep reddedildi (gerekçe ve öneriler)",
            "Request declined (reason and suggestions)",
            "Talep eden",
            "The requester",
            tone="danger",
            placeholders=("name", "who", "what", "reason", "alt"),
            path="/find-room",
        ),
        _K(
            "approval_withdrawn",
            "Talep geri çekildi",
            "Request withdrawn",
            "Talep eden ve onaylayıcılar",
            "The requester and the approvers",
            tone="neutral",
            placeholders=("who", "what"),
            path="/approvals",
        ),
        _K(
            "approval_expired",
            "Talebin süresi doldu",
            "Request expired",
            "Talep eden",
            "The requester",
            tone="neutral",
            placeholders=("what",),
            path="/reserve",
        ),
        _K(
            "booking_cancelled",
            "Rezervasyon iptal edildi",
            "Booking cancelled",
            "Rezervasyon sahibi",
            "The booking's owner",
            tone="danger",
            intro_key="booking_cancelled.body",
            placeholders=("actor", "count", "items", "reason"),
            path="/find-room",
            caller_applies_overrides=True,
        ),
        _K(
            "booking_reminder",
            "Rezervasyon hatırlatması",
            "Booking reminder",
            "Rezervasyon sahibi",
            "The booking's owner",
            placeholders=("name", "when", "what"),
            path="/bookings/mine",
            sender="template",
        ),
        _K(
            "series_created",
            "Yinelenen rezervasyon oluşturuldu",
            "Recurring booking created",
            "Seri sahibi",
            "The series' owner",
            tone="success",
            placeholders=("who", "room", "pattern", "count", "series_id", "items"),
            path="/bookings/mine",
            sender="template",
        ),
        _K(
            "series_changed",
            "Yinelenen rezervasyon değişti",
            "Recurring booking changed",
            "Seri sahibi",
            "The series' owner",
            tone="warning",
            placeholders=("who", "room", "series_id", "change", "items"),
            path="/bookings/mine",
            sender="template",
        ),
        _K(
            "calendar_consent",
            "Takvim eşitleme izni",
            "Calendar sync consent",
            "İzni veren kişi",
            "The person who consented",
            tone="neutral",
            enums=("state", "provider"),
            placeholders=("name", "provider", "state"),
            path="/profile#privacy",
            sender="template",
        ),
        _K(
            "kvkk_request",
            "KVKK veri talebi güncellemesi",
            "KVKK data request update",
            "Talep eden kişi",
            "The data subject",
            tone="neutral",
            enums=("request_kind", "status"),
            placeholders=("request_kind", "status", "detail"),
            path="/profile#privacy",
        ),
        _K(
            "ai_usage_alert",
            "Yapay zekâ kullanım uyarısı",
            "AI usage alert",
            "Uyarı alıcıları (yöneticiler)",
            "Alert recipients (administrators)",
            tone="warning",
            placeholders=("who", "percent", "used", "limit"),
            path="/admin/ai",
            owner="W3-AI",
        ),
        _K(
            "ops_alert",
            "Operasyon uyarısı",
            "Operations alert",
            "Yöneticiler",
            "Administrators",
            tone="danger",
            enums=("severity",),
            placeholders=("service", "title", "severity", "detail", "first_seen", "count"),
            path="/admin/ops",
            sender="template",
            owner="W3-OPS",
        ),
        _K(
            "timetable_published",
            "Yayınlanan programda değişiklik",
            "Changes in a published timetable",
            "Dersi değişen akademisyen",
            "Academicians whose classes changed",
            placeholders=("term", "items"),
            path="/timetable",
        ),
        _K(
            "booking_conflict_resolved",
            "Çakışma çözüldü",
            "Conflict resolved",
            "Rezervasyonu değişen kişi",
            "The person whose booking changed",
            tone="warning",
            placeholders=("items",),
            path="/bookings/mine",
        ),
        _K(
            "preference_accepted",
            "Ders tercihi kabul edildi",
            "Class preference accepted",
            "Akademisyen",
            "The academician",
            tone="success",
            placeholders=("who", "course", "what"),
            path="/moderation/me",
        ),
        _K(
            "preference_rejected",
            "Ders tercihi kabul edilmedi",
            "Class preference declined",
            "Akademisyen",
            "The academician",
            tone="danger",
            placeholders=("who", "course", "what", "reason"),
            path="/moderation/me",
        ),
        _K(
            "smtp_test",
            "Deneme iletisi",
            "Test message",
            "Denemeyi isteyen yönetici",
            "The administrator who asked for it",
            tone="success",
            placeholders=("org", "host"),
        ),
    )
}

#: an outbox kind without an entry (a future sender) still gets the themed layout with its own subject and body
GENERIC = KindSpec("generic", "Bildirim", "Notification", "-", "-", tone="info", placeholders=())


def spec(kind: str) -> KindSpec:
    return KINDS.get(kind) or GENERIC
