"""E-mail administration (wave 3b W3-MAIL; ``/admin/email`` and the E-posta card of ``/admin/integrations``).

Every route needs ``setup.settings``. Everything is organisation-wide (database rows shared by every administrator).

* ``GET /mail/presets`` -- provider presets (host / port / TLS / sign-in, console steps with values to copy).
* ``GET /mail/settings`` / ``PUT /mail/settings`` -- the SMTP settings; secrets are write-only (``null`` keeps,
  ``""`` clears) and answered masked; every change is audited; ``last_change`` = "Son değişiklik".
* ``POST /mail/test`` -- a themed test e-mail now, with the SMTP transcript excerpt (no secrets) and a hint.
* ``POST /mail/dns-check`` -- SPF / DKIM / DMARC of the from-domain with plain Turkish guidance.
* ``GET /mail/templates``, ``POST /mail/templates/{kind}/preview``, ``PUT /mail/templates/{kind}``,
  ``POST /mail/templates/{kind}/test`` -- the e-mail catalogue, previews with sample data, subject / intro
  overrides per language (rows of ``translations``, set ``email``: the CRBS override mechanism) and "test gönder".
* ``GET /mail/status`` -- the state the integrations hub shows (also ``app.services.mail_status``).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app import emails
from app.api.deps import DB, require_permission
from app.core.identity import clean_email
from app.models import Translation, User
from app.services import mail, mail_dns, mail_presets
from app.services.bookings_settings import get_group, set_group

router = APIRouter(prefix="/mail", tags=["mail"])
MailAdmin = Annotated[User, Depends(require_permission("setup.settings"))]

SECRET_KEYS = ("password", "oauth_client_secret", "oauth_refresh_token")
_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,252})$|^\[[0-9A-Fa-f:.]+\]$")
_SELECTOR = re.compile(r"^[A-Za-z0-9._-]{1,63}$")


def resolver() -> mail_dns.Resolver:
    """The DNS resolver of the from-domain check (tests replace it with a fake)."""
    return mail_dns.UdpResolver()


def _err(status: int, code: str, en: str, tr: str, **extra: Any) -> HTTPException:
    return HTTPException(status, {"code": code, "message": en, "message_en": en, "message_tr": tr, **extra})


def _clean(v: str | None) -> str | None:
    return None if v is None else " ".join(v.replace("\xa0", " ").split())


# --------------------------------------------------------------------------------------------------- settings


class MailSettingsIn(BaseModel):
    provider: str | None = None
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"] | None = None
    auth_mode: Literal["password", "xoauth2", "none"] | None = None
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)
    oauth_provider: Literal["", "google", "microsoft"] | None = None
    oauth_tenant: str | None = Field(default=None, max_length=100)
    oauth_client_id: str | None = Field(default=None, max_length=255)
    oauth_client_secret: str | None = Field(default=None, max_length=2048)
    oauth_refresh_token: str | None = Field(default=None, max_length=4096)
    from_address: str | None = Field(default=None, max_length=255)
    from_name: str | None = Field(default=None, max_length=120)
    reply_to: str | None = Field(default=None, max_length=255)
    timeout_s: int | None = Field(default=None, ge=1, le=120)
    dkim_selector: str | None = Field(default=None, max_length=63)
    #: "Bildirimi okudum; kurum adına onaylıyorum." (KVKK md. 9, providers abroad; integrations.md §7.1)
    abroad_ack: bool | None = None

    @field_validator("host", "username", "oauth_tenant", "oauth_client_id", "from_name", "dkim_selector", "provider")
    @classmethod
    def _text(cls, v: str | None) -> str | None:
        return _clean(v)


async def _settings_out(db: Any) -> dict[str, Any]:
    out = await get_group(db, "smtp")
    st = await mail.status(db)
    out["configured"] = st["configured"]
    out["status"] = st["state"]
    out["last_check"] = st["last_check"]
    out["last_change"] = st["last_change"]
    out["unsent"] = await mail.unsent_count(db)
    return out


@router.get("/settings")
async def get_settings(db: DB, _: MailAdmin) -> dict[str, Any]:
    return await _settings_out(db)


@router.put("/settings")
async def put_settings(body: MailSettingsIn, db: DB, me: MailAdmin) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    for key in SECRET_KEYS:
        if key in data and data[key] is None:
            data.pop(key)  # null = keep the stored secret; "" clears it
    if data.get("provider") and mail_presets.get(data["provider"]) is None:
        raise _err(422, "unknown_preset", "unknown provider preset", "bilinmeyen sağlayıcı ön ayarı")
    if data.get("host") and not _HOST.match(data["host"]):
        raise _err(
            422, "bad_host", "the host must be a server name or IP", "sunucu adı bir ana bilgisayar adı ya da IP olmalı"
        )
    for key in ("from_address", "reply_to"):
        if data.get(key):
            try:
                data[key] = clean_email(data[key])
            except ValueError as exc:
                raise _err(
                    422, f"bad_{key}", f"{key} must be an e-mail address", "geçerli bir e-posta adresi girin", field=key
                ) from exc
        elif key in data:
            data[key] = ""
    if data.get("dkim_selector") and not _SELECTOR.match(data["dkim_selector"]):
        raise _err(
            422,
            "bad_selector",
            "a DKIM selector is letters, digits, '.', '-', '_'",
            "DKIM seçici harf, rakam, '.', '-', '_' içerir",
        )
    stored = await get_group(db, "smtp", reveal=True)
    merged = {**stored, **data}
    if (
        str(merged.get("security")) == "none"
        and str(merged.get("auth_mode") or "password") != "none"
        and (merged.get("username") or merged.get("password"))
    ):
        raise _err(
            422,
            "plaintext_auth",
            "credentials are never sent over an unencrypted connection: choose STARTTLS or SSL/TLS",
            "Parola şifrelenmemiş bağlantıyla gönderilmez: güvenlik için STARTTLS ya da SSL/TLS seçin.",
        )
    if (
        str(merged.get("auth_mode")) == "xoauth2"
        and data.get("auth_mode") == "xoauth2"
        and not merged.get("oauth_provider")
    ):
        raise _err(
            422, "oauth_provider", "choose Google or Microsoft for OAuth2", "OAuth2 için Google ya da Microsoft seçin"
        )
    ack = data.pop("abroad_ack", None)
    preset = mail_presets.get(str(merged.get("provider") or ""))
    if preset is not None and preset.abroad:
        stored_ack = merged.get("abroad_ack") if isinstance(merged.get("abroad_ack"), dict) else None
        if ack:
            from app.models.base import utcnow
            from app.services.audit import user_label

            data["abroad_ack"] = {
                "by": user_label(me),
                "by_user_id": me.id,
                "at": utcnow().isoformat(timespec="seconds") + "Z",
                "provider": preset.id,
            }
        elif not (stored_ack and stored_ack.get("provider") == preset.id):
            raise _err(
                422,
                "abroad_ack_required",
                f"{preset.label} servers are abroad: confirm the KVKK art. 9 notice first",
                f"{preset.label} sunucuları yurt dışında: bildirim e-postaları (alıcı adı, adresi, rezervasyon "
                "bilgileri) yurt dışına aktarılır (KVKK md. 9). Önce bildirimi onaylayın.",
                field="abroad_ack",
            )
    await set_group(db, "smtp", data)
    await db.commit()
    return await _settings_out(db)


class RequeueIn(BaseModel):
    #: "Bekleyenleri de gönder": UNSENT rows younger than 7 days are queued again (integrations.md §7.2 step 6)
    days: int = Field(default=7, ge=1, le=7)


@router.post("/outbox/requeue")
async def requeue(body: RequeueIn, db: DB, me: MailAdmin) -> dict[str, Any]:
    n = await mail.requeue_unsent(db, me, days=body.days)
    await db.commit()
    return {"queued": n, "unsent": await mail.unsent_count(db)}


@router.get("/presets")
async def get_presets(_: MailAdmin) -> list[dict[str, Any]]:
    return mail_presets.presets_out()


@router.get("/status")
async def get_status(db: DB, _: MailAdmin) -> dict[str, Any]:
    return await mail.status(db)


# --------------------------------------------------------------------------------------------------- test + DNS


class TestIn(BaseModel):
    to: str
    locale: Literal["tr", "en"] | None = None


@router.post("/test")
async def send_test(body: TestIn, db: DB, me: MailAdmin) -> dict[str, Any]:
    to = _to(body.to)
    out = await mail.send_test(db, to, me, locale=body.locale)
    await db.commit()
    return out


def _to(value: str) -> str:
    try:
        return clean_email(value)
    except ValueError as exc:
        raise _err(422, "bad_to", "enter an e-mail address", "geçerli bir e-posta adresi girin") from exc


class DnsIn(BaseModel):
    domain: str | None = Field(default=None, max_length=253)
    selector: str | None = Field(default=None, max_length=63)


@router.post("/dns-check")
async def dns_check(body: DnsIn, db: DB, _: MailAdmin) -> dict[str, Any]:
    smtp = await get_group(db, "smtp")
    domain = _clean(body.domain) or str(smtp.get("from_address") or "")
    if not domain:
        raise _err(
            422,
            "no_domain",
            "save a from-address or enter a domain",
            "bir gönderen adresi kaydedin ya da alan adı girin",
        )
    selector = _clean(body.selector) or str(smtp.get("dkim_selector") or "") or None
    if selector and not _SELECTOR.match(selector):
        raise _err(422, "bad_selector", "bad DKIM selector", "geçersiz DKIM seçici")
    try:
        return await mail_dns.check_domain(
            domain, resolver=resolver(), preset_id=str(smtp.get("provider") or ""), selector=selector
        )
    except ValueError as exc:
        raise _err(422, "bad_domain", "not a domain name", "geçerli bir alan adı girin") from exc


# --------------------------------------------------------------------------------------------------- templates


def _kind(kind: str) -> emails.KindSpec:
    spec = emails.KINDS.get(kind)
    if spec is None:
        raise _err(404, "unknown_kind", "unknown e-mail kind", "bilinmeyen e-posta türü")
    return spec


async def _overrides_of(db: Any, spec: emails.KindSpec) -> dict[str, dict[str, str | None]]:
    keys = {spec.keys["subject"]: "subject", spec.keys["intro"]: "intro"}
    q = select(Translation).where(Translation.set == "email", Translation.key.in_(list(keys)))
    out: dict[str, dict[str, str | None]] = {
        "tr": {"subject": None, "intro": None},
        "en": {"subject": None, "intro": None},
    }
    for t in (await db.execute(q)).scalars():
        if t.language in out:
            out[t.language][keys[t.key]] = t.text
    return out


def _shipped_of(spec: emails.KindSpec) -> dict[str, dict[str, str | None]]:
    from app.emails.strings import shipped

    return {
        lang: {"subject": shipped(lang).get(spec.keys["subject"]), "intro": shipped(lang).get(spec.keys["intro"])}
        for lang in ("tr", "en")
    }


@router.get("/templates")
async def list_templates(db: DB, _: MailAdmin) -> list[dict[str, Any]]:
    out = []
    for spec in emails.KINDS.values():
        out.append(
            {
                "kind": spec.kind,
                "label_tr": spec.label_tr,
                "label_en": spec.label_en,
                "audience_tr": spec.audience_tr,
                "audience_en": spec.audience_en,
                "tone": spec.tone,
                "sender": spec.sender,
                "owner": spec.owner,
                "placeholders": sorted({*spec.placeholders, "name", "org"}),
                "shipped": _shipped_of(spec),
                "overrides": await _overrides_of(db, spec),
            }
        )
    return out


class DraftIn(BaseModel):
    locale: Literal["tr", "en"] = "tr"
    subject: str | None = Field(default=None, max_length=255)
    intro: str | None = Field(default=None, max_length=2000)


def _draft(spec: emails.KindSpec, body: DraftIn) -> dict[str, str]:
    allowed = {*spec.placeholders, "name", "org"}
    out: dict[str, str] = {}
    for part, key in (("subject", spec.keys["subject"]), ("intro", spec.keys["intro"])):
        value = getattr(body, part)
        if value is None:
            continue
        text = value.replace("\xa0", " ").replace("\r\n", "\n").strip()
        if part == "subject":
            text = " ".join(text.split())
        unknown = [p for p in emails.placeholders_in(text) if p not in allowed]
        if unknown:
            raise _err(
                422,
                "unknown_placeholder",
                f"unknown placeholders: {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}",
                f"bilinmeyen alanlar: {', '.join(unknown)}; kullanılabilir: {', '.join(sorted(allowed))}",
                field=part,
            )
        if text.count("{") != text.count("}"):
            raise _err(422, "unbalanced_braces", "unbalanced { }", "süslü parantezler eşleşmiyor", field=part)
        out[key] = text
    return out


@router.post("/templates/{kind}/preview")
async def preview(kind: str, body: DraftIn, db: DB, _: MailAdmin) -> dict[str, Any]:
    spec = _kind(kind)
    draft = {k: v for k, v in _draft(spec, body).items() if v}
    strings = {**(await mail.overrides(db, body.locale)), **draft}
    b = await mail.brand(db)
    ctx = emails.sample_context(kind, body.locale)
    if b.org_name:
        ctx["org"] = b.org_name
    r = emails.render(kind, body.locale, strings=strings, brand=b, **ctx)
    return {
        "kind": kind,
        "locale": body.locale,
        "subject": r.subject,
        "html": r.html,
        "text": r.text,
        "preheader": r.preheader,
    }


@router.put("/templates/{kind}")
async def save_template(kind: str, body: DraftIn, db: DB, _: MailAdmin) -> dict[str, Any]:
    """Save the subject / intro overrides of one language; ``""`` removes the override (the shipped text again)."""
    spec = _kind(kind)
    draft = _draft(spec, body)
    for key, text in draft.items():
        row = (
            await db.execute(
                select(Translation).where(
                    Translation.language == body.locale, Translation.set == "email", Translation.key == key
                )
            )
        ).scalar_one_or_none()
        if not text:
            if row is not None:
                await db.delete(row)
        elif row is None:
            db.add(Translation(language=body.locale, set="email", key=key, text=text))
        else:
            row.text = text
    await db.commit()
    return {"kind": kind, "overrides": await _overrides_of(db, spec), "shipped": _shipped_of(spec)}


class TemplateTestIn(DraftIn):
    to: str


@router.post("/templates/{kind}/test")
async def template_test(kind: str, body: TemplateTestIn, db: DB, me: MailAdmin) -> dict[str, Any]:
    spec = _kind(kind)
    draft = {k: v for k, v in _draft(spec, body).items() if v}
    out = await mail.send_test(db, _to(body.to), me, kind=kind, locale=body.locale, draft=draft)
    await db.commit()
    return out
