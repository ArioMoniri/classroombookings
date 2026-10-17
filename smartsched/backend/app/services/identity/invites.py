"""Invitations per provider (wave 3b W3-IDP): the invite e-mail, resend, bulk invite from CSV and the local-password
invite (the invited person sets a password from the link).

The invite rows, renew and revoke stay in app/services/sso.py (T-R1-35: revoking disables the unused placeholder
account). The e-mail goes through W3-MAIL's themed renderer (kind ``invitation`` of app/emails) by way of
:func:`app.services.bookings_notify.notify` with the template context passed in memory: the outbox keeps a record
of the e-mail but never the live invite link (the body is scrubbed after sending, like password-reset codes).
"""

from __future__ import annotations

import csv
import io
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, hash_password
from app.models import User
from app.models.base import utcnow
from app.models.sso import SsoInvite
from app.services import audit, sso
from app.services.bookings_settings import get_value
from app.services.calendar_feeds import public_base

MAX_ROWS = 200
#: CSV header aliases (Turkish and English, folded: lower case, dotless, no spaces / punctuation)
HEADERS = {
    "email": ("email", "eposta", "mail", "epostaadresi", "upn", "kullaniciadi"),
    "full_name": ("fullname", "name", "ad", "adsoyad", "adisoyadi", "isim", "adsoyadi"),
    "role": ("role", "rol", "yetki"),
    "provider": ("provider", "saglayici", "girisyontemi", "yontem"),
    "days": ("days", "gun", "sure", "gecerlilik"),
}
_TR_FOLD = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ş": "s",
        "ş": "s",
        "Ğ": "g",
        "ğ": "g",
        "Ü": "u",
        "ü": "u",
        "Ö": "o",
        "ö": "o",
        "Ç": "c",
        "ç": "c",
    }
)


def _fold_header(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).replace("﻿", "").replace("\xa0", " ").translate(_TR_FOLD).lower()
    return "".join(ch for ch in text if ch.isalnum())


def _months(locale: str) -> tuple[str, ...]:
    if locale == "en":
        return (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        )
    return (
        "Ocak",
        "Şubat",
        "Mart",
        "Nisan",
        "Mayıs",
        "Haziran",
        "Temmuz",
        "Ağustos",
        "Eylül",
        "Ekim",
        "Kasım",
        "Aralık",
    )


def human_date(dt: datetime, locale: str) -> str:
    """``16 Kasım 2026`` / ``16 November 2026`` (Europe/Istanbul is UTC+3 all year)."""
    from datetime import timedelta

    local = dt + timedelta(hours=3)
    return f"{local.day} {_months(locale)[local.month - 1]} {local.year}"


async def invite_link(db: AsyncSession, inv: SsoInvite) -> str | None:
    base, _ = await public_base(db)
    try:
        token = decrypt_secret(inv.token_enc)
    except ValueError:
        return None
    return f"{base}/login?{urlencode({'invite': token})}" if base else None


async def send_invite_email(db: AsyncSession, actor: User, inv: SsoInvite, locale: str | None = None) -> dict[str, Any]:
    """E-mail the invite now; ``{sent, status, error}`` (``UNSENT`` without SMTP: the administrator copies the link)."""
    from app.services.bookings_notify import notify

    target = await db.get(User, inv.user_id)
    link = await invite_link(db, inv)
    lang = locale if locale in ("tr", "en") else str(await get_value(db, "org", "default_language") or "tr")
    lang = "en" if lang.startswith("en") else "tr"
    org = str(await get_value(db, "org", "name") or "SmartSched")
    prov = None if inv.provider == sso.LOCAL else await sso.get_provider(db, slug=inv.provider)
    provider_name = sso.provider_label(prov, lang) if prov is not None else sso.LOCAL_LABEL[lang]
    inviter = audit.user_label(actor) or ""
    expires = human_date(inv.expires_at, lang)
    name = (target.full_name if target is not None else None) or ""
    subject_tr = f"{org}: SmartSched daveti"
    subject_en = f"{org}: SmartSched invitation"
    body = (
        f"Merhaba {name},\n\n{inviter} sizi {org} SmartSched paneline davet etti. Giriş yöntemi: {provider_name}.\n"
        f"Daveti kabul etmek için: {link}\nDavet {expires} tarihine kadar geçerlidir.\n\n"
        f"Hello {name},\n\n{inviter} invited you to the {org} SmartSched panel. Sign-in method: {provider_name}.\n"
        f"Accept the invitation: {link}\nThe invitation is valid until {expires}.\n"
    )
    row = await notify(
        db,
        kind="invitation",
        to_email=inv.email,
        subject=subject_en if lang == "en" else subject_tr,
        body=body,
        user_id=inv.user_id,
        deliver_now=True,
        link="/login",
        locale=lang,
        ctx={
            "name": name,
            "org": org,
            "inviter": inviter,
            "provider": provider_name,
            "provider_kind": prov.kind if prov is not None else sso.LOCAL,
            "expires": expires,
            "cta_url": link,
        },
    )
    status, error = row.status, row.error
    # the outbox keeps the fact, never the live link
    row.body = "(invitation e-mail; the link is not stored)"
    await db.flush()
    await audit.record(
        db,
        "user.invite_emailed",
        "user",
        inv.user_id,
        after={"provider": inv.provider, "status": status, "invite_id": inv.id},
        actor=actor,
    )
    return {"sent": status == "SENT", "status": status, "error": error}


async def resend(db: AsyncSession, actor: User, invite_id: int, locale: str | None = None) -> dict[str, Any]:
    """The same link again by e-mail (the validity is not extended: "Yenile" does that)."""
    from app.services.bookings_perms import may_manage_user

    inv = await db.get(SsoInvite, invite_id)
    if inv is None:
        raise sso.SsoAdminError(404, "not_found", "invite not found", "Davet bulunamadı")
    target = await db.get(User, inv.user_id)
    if target is not None and not await may_manage_user(db, actor, target):
        raise sso._no_escalation()  # noqa: SLF001
    if inv.expires_at < utcnow():
        raise sso.SsoAdminError(
            409, "invite_expired", "the invite has expired: renew it first", "Davetin süresi dolmuş: önce yenileyin"
        )
    return await send_invite_email(db, actor, inv, locale)


# --------------------------------------------------------------------------------------------------
# bulk CSV
# --------------------------------------------------------------------------------------------------


def parse_csv(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(rows, errors). Excel exports from Turkish locales use ``;`` and a BOM; NBSP and zero-width characters are
    removed; a file without a header is read as ``email[,name[,role]]``."""
    clean = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in clean.split("\n") if ln.strip()]
    if not lines:
        return [], [{"line": 0, "code": "empty", "tr": "Dosya boş.", "en": "The file is empty."}]
    first = lines[0]
    delim = ";" if first.count(";") >= first.count(",") and ";" in first else ("\t" if "\t" in first else ",")
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
    table = [[sso._plain(c) for c in r] for r in reader]  # noqa: SLF001 - NBSP / zero-width / NFKC
    head = [_fold_header(c) for c in table[0]]
    cols: dict[str, int] = {}
    for key, aliases in HEADERS.items():
        for i, h in enumerate(head):
            if h in aliases and key not in cols:
                cols[key] = i
    start = 1
    if "email" not in cols:
        if any("@" in c for c in table[0]):
            cols, start = {"email": 0, "full_name": 1, "role": 2}, 0
        else:
            return [], [
                {"line": 1, "code": "no_email_column", "tr": "E-posta sütunu bulunamadı.", "en": "No e-mail column."}
            ]
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for n, rec in enumerate(table[start:], start=start + 1):

        def cell(key: str, rec: list[str] = rec) -> str:
            i = cols.get(key)
            return rec[i].strip() if i is not None and i < len(rec) else ""

        row: dict[str, Any] = {"line": n, "email": cell("email"), "full_name": cell("full_name") or None}
        if cell("role"):
            row["role"] = cell("role")
        if cell("provider"):
            row["provider"] = cell("provider")
        days = cell("days")
        if days:
            if not days.isdigit() or not 1 <= int(days) <= 365:
                errors.append(
                    {
                        "line": n,
                        "email": row["email"],
                        "code": "invalid_days",
                        "tr": "Gün 1-365 olmalı.",
                        "en": "Days must be 1-365.",
                    }
                )
                continue
            row["days"] = int(days)
        rows.append(row)
    if len(rows) > MAX_ROWS:
        errors.append(
            {"line": 0, "code": "too_many", "tr": f"En çok {MAX_ROWS} satır.", "en": f"At most {MAX_ROWS} rows."}
        )
        rows = rows[:MAX_ROWS]
    return rows, errors


async def _role_id(db: AsyncSession, value: str) -> int | None:
    from app.models import Role

    text = sso._plain(value)  # noqa: SLF001
    folded = _fold_header(text)
    for r in (await db.execute(select(Role))).scalars():
        if (r.code and r.code.lower() == folded) or _fold_header(r.name) == folded:
            return r.id
    aliases = {
        "ogretmen": "TEACHER",
        "ogretimelemani": "TEACHER",
        "izleyici": "VIEWER",
        "planlamaci": "PLANNER",
        "yonetici": "ADMIN",
    }
    code = aliases.get(folded)
    if code:
        found = (await db.execute(select(Role.id).where(Role.code == code))).scalar_one_or_none()
        return found
    return None


async def bulk(db: AsyncSession, actor: User, body: dict[str, Any]) -> dict[str, Any]:
    """Create one invite per CSV row (each in its own savepoint: a refused row never undoes the others), optionally
    e-mail them. ``provider`` / ``role_id`` / ``days`` of the request are the defaults of the rows."""
    rows, errors = parse_csv(str(body.get("csv") or ""))
    created: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        payload: dict[str, Any] = {
            "email": row["email"],
            "full_name": row.get("full_name"),
            "provider": row.get("provider") or body.get("provider"),
            "role_id": body.get("role_id"),
            "days": row.get("days") or body.get("days"),
        }
        if row.get("role"):
            rid = await _role_id(db, row["role"])
            if rid is None:
                errors.append(
                    {
                        "line": row["line"],
                        "email": row["email"],
                        "code": "unknown_role",
                        "tr": f"Bilinmeyen rol: {row['role']}",
                        "en": f"Unknown role: {row['role']}",
                    }
                )
                continue
            payload["role_id"] = rid
        key = (sso._fold_email(row["email"]) or row["email"]).lower()  # noqa: SLF001
        if key in seen:
            errors.append(
                {
                    "line": row["line"],
                    "email": row["email"],
                    "code": "duplicate",
                    "tr": "Bu adres dosyada birden çok kez var.",
                    "en": "This address appears more than once.",
                }
            )
            continue
        seen.add(key)
        try:
            async with db.begin_nested():
                out = await sso.create_invite(db, actor, payload)
        except sso.SsoAdminError as exc:
            errors.append({"line": row["line"], "email": row["email"], "code": exc.code, "tr": exc.tr, "en": exc.en})
            continue
        if body.get("send_email"):
            inv = await db.get(SsoInvite, out["id"])
            if inv is not None:
                out["email_status"] = (await send_invite_email(db, actor, inv, body.get("locale")))["status"]
        out["line"] = row["line"]
        out.pop("link", None)  # links of a bulk run are e-mailed or copied one by one, never listed in bulk
        created.append(out)
    await audit.record(
        db,
        "user.invites_bulk",
        "user",
        None,
        after={"created": len(created), "refused": len(errors), "provider": body.get("provider")},
        actor=actor,
    )
    errors.sort(key=lambda e: e.get("line", 0))
    return {"created": created, "errors": errors}


# --------------------------------------------------------------------------------------------------
# local-password invites
# --------------------------------------------------------------------------------------------------


async def accept_local(db: AsyncSession, token: str, password: str) -> User | None:
    """The invited person sets a password from ``/login?invite=<token>`` (local invites only). ``None``: unknown,
    used, expired, not a local invite or the account was disabled. Audited ``user.invite_accepted``."""
    inv = await sso._invite_by_token(db, token)  # noqa: SLF001
    if inv is None or inv.provider != sso.LOCAL or inv.kind != "invite" or inv.expires_at < utcnow():
        return None
    user = await db.get(User, inv.user_id)
    if user is None or not user.is_active:
        return None
    user.password_hash = hash_password(password)
    user.auth_source = "local"
    user.force_password_reset = False
    facts = {"kind": inv.kind, "email": inv.email, "invite_id": inv.id, "provider": sso.LOCAL}
    await db.delete(inv)
    await db.flush()
    await audit.record(db, "user.invite_accepted", "user", user.id, after=facts, actor=user)
    return user
