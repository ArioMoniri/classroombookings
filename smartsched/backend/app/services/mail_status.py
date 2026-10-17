"""The E-posta card of the integrations hub (wave 3b W3-HUB contract ``integration_status``; W3-MAIL)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import mail, mail_presets

_DETAIL = {
    "connected": ("SMTP sunucusu ayarlı.", "The SMTP server is set up."),
    "not_configured": (
        "Sunucu ve gönderen adresi girilmedi: e-postalar gönderilmez, giden kutusunda bekler.",
        "No server or from-address yet: e-mails are not sent; they wait in the outbox.",
    ),
    "error": ("Son deneme iletisi gönderilemedi.", "The last test message failed."),
}


async def integration_status(session: AsyncSession) -> list[dict[str, Any]]:
    st = await mail.status(session)
    preset = mail_presets.get(st["provider"])
    tr, en = _DETAIL[st["state"]]
    if st["state"] == "connected":
        via = preset.label if preset else st["host"]
        tr, en = f"{via} üzerinden {st['from_address']} adresiyle gönderir.", f"Sends as {st['from_address']} via {via}."
        if not st["tested"]:
            tr += " Henüz deneme iletisi gönderilmedi."
            en += " No test message was sent yet."
    check = st["last_check"] or {}
    change = st["last_change"] or {}
    return [
        {
            "key": "email.smtp",
            "name_tr": "E-posta (SMTP)",
            "name_en": "E-mail (SMTP)",
            "status": st["state"],
            "enabled": st["configured"],
            "detail_tr": tr,
            "detail_en": en,
            "last_check_at": check.get("at"),
            "last_check_ok": check.get("ok"),
            "changed_by": change.get("by"),
            "changed_at": change.get("at"),
            "setup_href": "/admin/integrations?tab=email&setup=email.smtp",
        }
    ]
