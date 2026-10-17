"""RFC 9116 security.txt, set per institution (security follow-up wave3-sec2, docs/SECURITY.md §3 "security.txt").

Settings (``app.services.settings_service.SPECS``): ``security.contact_email`` (required once set), ``security.
contact_url`` and ``security.policy_url`` (optional, https), ``security.preferred_languages`` (default "tr, en").
Administrators write them through ``PUT /api/v1/admin/security-contact`` (audited ``security.contact``); the backend
serves the file at ``/.well-known/security.txt`` and ``/security.txt`` (nginx proxies both). Expires is one year
ahead of the request, so the file never goes stale. While no contact is set the file names ``security@<host>`` and
the admin card warns.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent
from app.services import settings_service as ss

EMAIL_KEY = "security.contact_email"
URL_KEY = "security.contact_url"
POLICY_KEY = "security.policy_url"
LANG_KEY = "security.preferred_languages"
KEYS = {"contact_email": EMAIL_KEY, "contact_url": URL_KEY, "policy_url": POLICY_KEY, "preferred_languages": LANG_KEY}
DEFAULT_LANGUAGES = "tr, en"
AUDIT_ACTION = "security.contact"

UNSET_WARNING = {
    "code": "security_contact_unset",
    "message_tr": "Güvenlik iletişim adresi ayarlanmadı",
    "message_en": "The security contact address is not set",
}

_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+$")
_URL = re.compile(r"^https://[A-Za-z0-9.-]+(?::\d{1,5})?(?:/[^\s]*)?$")
_LANG = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$")
_HOST = re.compile(r"^(?:[A-Za-z0-9-]{1,63}\.)*[A-Za-z0-9-]{1,63}(?::\d{1,5})?$|^\[[0-9A-Fa-f:.]+\](?::\d{1,5})?$")

_TEXTS = {
    "contact_email": ("Geçerli bir güvenlik iletişim e-postası girin.", "Enter a valid security contact e-mail."),
    "contact_url": ("İletişim sayfası https:// ile başlayan bir adres olmalı.", "The contact page must be an https:// URL."),
    "policy_url": ("Politika sayfası https:// ile başlayan bir adres olmalı.", "The policy page must be an https:// URL."),
    "preferred_languages": (
        "Diller virgülle ayrılmış dil kodları olmalı (ör. tr, en).",
        "Languages must be comma-separated language tags (e.g. tr, en).",
    ),
}


class InvalidContact(ValueError):
    def __init__(self, field: str) -> None:
        self.field = field
        self.message_tr, self.message_en = _TEXTS[field]
        super().__init__(self.message_en)


def validate(values: dict[str, Any]) -> dict[str, str | None]:
    """Normalised values for the four keys (``None`` = clear an optional one); raises :class:`InvalidContact`."""
    email = str(values.get("contact_email") or "").strip()
    if len(email) > 254 or not _EMAIL.match(email):
        raise InvalidContact("contact_email")
    out: dict[str, str | None] = {"contact_email": email}
    for name in ("contact_url", "policy_url"):
        url = str(values.get(name) or "").strip()
        if url and (len(url) > 500 or not _URL.match(url)):
            raise InvalidContact(name)
        out[name] = url or None
    langs = str(values.get("preferred_languages") or "").strip() or DEFAULT_LANGUAGES
    tags = [t.strip() for t in langs.split(",")]
    if not tags or len(tags) > 10 or not all(_LANG.match(t) for t in tags):
        raise InvalidContact("preferred_languages")
    out["preferred_languages"] = ", ".join(tags)
    return out


async def current(session: AsyncSession) -> dict[str, Any]:
    vals = {name: await ss.get_value(session, key) for name, key in KEYS.items()}
    vals["preferred_languages"] = vals["preferred_languages"] or DEFAULT_LANGUAGES
    vals["configured"] = bool(vals["contact_email"])
    return vals


async def save(session: AsyncSession, values: dict[str, str | None]) -> None:
    for name, key in KEYS.items():
        await ss.set_value(session, key, values.get(name))


async def last_change(session: AsyncSession) -> dict[str, Any] | None:
    ev = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.action == AUDIT_ACTION)
            .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ev is None:
        return None
    return {"actor": ev.actor_label, "at": ev.ts.replace(tzinfo=UTC).isoformat(timespec="seconds") if ev.ts else None}


def safe_host(host: str | None) -> str:
    h = (host or "").strip()
    return h if h and len(h) <= 255 and _HOST.match(h) else "localhost"


def build(values: dict[str, Any], *, host: str, scheme: str, now: datetime | None = None) -> str:
    host = safe_host(host)
    scheme = "https" if scheme == "https" else "http"
    expires = (now or datetime.now(UTC)) + timedelta(days=365)
    bare = host.rsplit(":", 1)[0] if not host.startswith("[") else "localhost"
    lines = [f"Contact: mailto:{values.get('contact_email') or f'security@{bare}'}"]
    if values.get("contact_url"):
        lines.append(f"Contact: {values['contact_url']}")
    lines.append(f"Expires: {expires.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
    lines.append(f"Preferred-Languages: {values.get('preferred_languages') or DEFAULT_LANGUAGES}")
    lines.append(f"Canonical: {scheme}://{host}/.well-known/security.txt")
    if values.get("policy_url"):
        lines.append(f"Policy: {values['policy_url']}")
    return "\n".join(lines) + "\n"


__all__ = [
    "AUDIT_ACTION",
    "DEFAULT_LANGUAGES",
    "KEYS",
    "UNSET_WARNING",
    "InvalidContact",
    "build",
    "current",
    "last_change",
    "safe_host",
    "save",
    "validate",
]
