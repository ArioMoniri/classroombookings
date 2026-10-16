"""Messages of the external channels, in the recipient's language (Turkish or English).

External messages never reuse the notice's ``title`` / ``body``: those name the approver or the requester. They are
built from the structured ``Notice.data`` instead and carry only what docs/product/2026-10-15-integrations-options.md
§6 allows: room, dates, periods, the decision and the reason (never booking notes, never other people's names or
e-mail addresses).

``link_only`` (per channel, KVKK's strictest reading) carries no personal detail at all: "SmartSched'de yeni
bildirim" and the deep link. In that mode the outbox row itself keeps only the event, the language and the link.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.notify_dispatch import Notice

TITLE = "SmartSched"
LINK_ONLY: dict[str, tuple[str, str]] = {
    # (with a link, without one)
    "tr": (
        "SmartSched'de yeni bildirim var. Ayrıntılar: {link}",
        "SmartSched'de yeni bildirim var. Ayrıntılar için SmartSched'i açın.",
    ),
    "en": (
        "New notification in SmartSched. Details: {link}",
        "New notification in SmartSched. Open SmartSched for the details.",
    ),
}
FULL: dict[str, dict[str, str]] = {
    "approval.requested": {"tr": "Onay bekleyen oda talebi: {what}", "en": "Room request awaiting approval: {what}"},
    "approval.approved": {"tr": "Oda talebiniz onaylandı: {what}", "en": "Your room request was approved: {what}"},
    "approval.rejected": {
        "tr": "Oda talebiniz reddedildi: {what}\nGerekçe: {reason}",
        "en": "Your room request was declined: {what}\nReason: {reason}",
    },
    "approval.withdrawn": {
        "tr": "Oda talebinizi geri çektiniz: {what}",
        "en": "You withdrew your room request: {what}",
    },
    "approval.expired": {"tr": "Oda talebinizin süresi doldu: {what}", "en": "Your room request expired: {what}"},
}
GENERIC = {"tr": "SmartSched bildirimi", "en": "SmartSched notification"}
VERIFY = {
    "tr": (
        "SmartSched doğrulama kodunuz: {code}. Kod 10 dakika geçerlidir. Bu isteği siz yapmadıysanız mesajı yok sayın."
    ),
    "en": (
        "Your SmartSched verification code: {code}. It is valid for 10 minutes. Ignore this message if you did not ask."
    ),
}
TEST = {
    "tr": "SmartSched test bildirimi: bu kanal çalışıyor.",
    "en": "SmartSched test notification: this channel works.",
}
LINKED = {
    "tr": "Bağlandı ✓ SmartSched bildirimleri artık bu sohbete gelecek. Kaldırmak için Profil > Bildirim kanalları.",
    "en": (
        "Linked ✓ SmartSched notifications will arrive in this chat. Remove it under Profile > Notification channels."
    ),
}
INVALID_CODE = {
    "tr": "Bağlantı kodu geçersiz ya da süresi dolmuş. SmartSched Profil sayfasından yeni bir bağlantı oluşturun.",
    "en": "The link code is invalid or expired. Create a new link on your SmartSched Profile page.",
}
STOPPED = {
    "tr": "SmartSched bildirimleri bu sohbete artık gönderilmeyecek.",
    "en": "SmartSched notifications will no longer be sent to this chat.",
}

#: payload keys a full-mode outbox row may keep (the allow-list of §6; no names, notes or e-mail addresses)
FULL_KEYS = ("room", "dates", "periods", "decision", "reason_code", "reason_note")


def lang_of(lang: str | None) -> str:
    return "tr" if (lang or "tr").lower().startswith(("tr", "türk", "turk")) else "en"


def both(table: dict[str, str], lang: str, **fmt: Any) -> str:
    return table[lang_of(lang)].format(**fmt)


def absolute(base: str, link: str | None) -> str | None:
    if not link or not base:
        return None
    if link.startswith(("https://", "http://")):
        return link
    return f"{base.rstrip('/')}/{link.lstrip('/')}"


def notice_payload(notice: Notice, lang: str, mode: str, base: str) -> dict[str, Any]:
    """What the outbox row keeps for one notice."""
    out: dict[str, Any] = {
        "event": notice.event,
        "lang": lang_of(lang),
        "mode": mode,
        "link": absolute(base, notice.link),
    }
    if mode == "link_only":
        return out
    data = dict(notice.data or {})
    if notice.event == "approval.rejected":
        out["reason_code"] = data.get("reason_code")
        out["reason_note"] = data.get("note") if data.get("reason_code") not in (None, "") or data.get("note") else None
    for key in ("room", "dates", "periods", "decision"):
        if key in data:
            out[key] = data[key]
    return {k: v for k, v in out.items() if k in (*FULL_KEYS, "event", "lang", "mode", "link")}


def _what(payload: dict[str, Any]) -> str:
    """``A 102, 19.02.2026 P1 08:30-09:10`` from the structured facts (the same shape approvals.summary builds)."""
    dates: list[date] = []
    for raw in payload.get("dates") or []:
        try:
            dates.append(date.fromisoformat(str(raw)))
        except ValueError:
            continue
    dates.sort()
    periods = [p for p in payload.get("periods") or [] if isinstance(p, dict)]

    def one(p: dict[str, Any]) -> str:
        times = f"{p.get('start') or ''}-{p.get('end') or ''}".strip("-")
        return f"{p.get('name') or ''} {times}".strip()

    if len(periods) == 1:
        span = one(periods[0])
    elif periods and all(
        int(b.get("start_period") or 0) == int(a.get("end_period") or 0) + 1
        for a, b in zip(periods, periods[1:], strict=False)
    ):
        first, last = periods[0], periods[-1]
        span = f"{first.get('name')}-{last.get('name')} {first.get('start') or ''}-{last.get('end') or ''}".strip()
    else:
        span = ", ".join(one(p) for p in periods)
    if len(dates) == 1:
        when = f"{dates[0]:%d.%m.%Y}"
    elif dates:
        when = f"{dates[0]:%d.%m.%Y} - {dates[-1]:%d.%m.%Y} ({len(dates)})"
    else:
        when = ""
    room = str(payload.get("room") or "").strip()
    return ", ".join(x for x in (room, f"{when} {span}".strip()) if x)


def render(payload: dict[str, Any]) -> tuple[str, str]:
    """(title, body) of an outbox row; the verification code is passed in decrypted by the caller."""
    lang = lang_of(payload.get("lang"))
    event = str(payload.get("event") or "")
    link = payload.get("link")
    if event == "channel.verify":
        return TITLE, both(VERIFY, lang, code=payload.get("code", ""))
    if event == "channel.test":
        return TITLE, both(TEST, lang)
    if payload.get("mode") != "full" or event not in FULL:
        with_link, without = LINK_ONLY[lang]
        return TITLE, with_link.format(link=link) if link else without
    reason = "-"
    if event == "approval.rejected":
        from app.services.approvals import reason_text

        reason = reason_text(payload.get("reason_code"), payload.get("reason_note"), lang)
    body = FULL[event][lang].format(what=_what(payload), reason=reason)
    if link:
        body = f"{body}\n{link}"
    return TITLE, body
