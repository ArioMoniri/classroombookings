"""The SMTP sender, shared by every administrator (wave 3b W3-MAIL; docs/deploy/email.md).

* Settings: the organisation's ``smtp.*`` rows (``app.services.bookings_settings.SMTP_SPECS``): one set for the whole
  organisation, secrets (password, OAuth2 client secret and refresh token) Fernet-encrypted at rest, write-only in the
  API, every change audited by the settings flush hook (``audit_events`` entity ``settings``), shown as
  "Son değişiklik: <ad>, <zaman>" (:func:`last_change`).
* Sign-in: ``password`` (``AUTH PLAIN/LOGIN``), ``xoauth2`` (Google / Microsoft 365 access token,
  :mod:`app.services.mail_oauth`) or ``none`` (an internal relay).
* Messages: ``multipart/alternative`` (plain text first, themed HTML second, the logo as an inline CID image) built by
  :func:`build_message` from :func:`render_for` (the organisation's overrides and brand over :func:`app.emails.render`).
* :func:`send_test`: a themed test message with an SMTP transcript excerpt (``C:`` / ``S:`` lines, credentials and the
  message body never included) and a plain Turkish hint for the usual failures.
"""

from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import socket
import ssl
import time
from collections.abc import Mapping
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import emails
from app.models import AuditEvent, NotificationOutbox, User
from app.models.base import utcnow
from app.services import mail_oauth
from app.services.bookings_settings import get_group, get_value

log = logging.getLogger(__name__)

TEST_KIND = "smtp_test"
TRANSCRIPT_MAX = 80
#: the settings keys an administrator edits on the e-mail screen (the "Son değişiklik" history)
SETTINGS_KEYS = (
    "host",
    "port",
    "security",
    "username",
    "password",
    "from_address",
    "from_name",
    "timeout_s",
    "provider",
    "auth_mode",
    "oauth_provider",
    "oauth_tenant",
    "oauth_client_id",
    "oauth_client_secret",
    "oauth_refresh_token",
    "reply_to",
    "dkim_selector",
)


class MailMessage(EmailMessage):
    """An e-mail whose :meth:`get_content` reads the plain-text part of a multipart message (what a reader of the
    text sees), so code written for the former text-only messages keeps working."""

    def get_content(self, *args: Any, **kw: Any) -> Any:
        if self.is_multipart():
            part = self.get_body(preferencelist=("plain",))
            if part is not None:
                return part.get_content(*args, **kw)
        return super().get_content(*args, **kw)


# --------------------------------------------------------------------------------------------------
# Rendering with the organisation's overrides and brand
# --------------------------------------------------------------------------------------------------


async def brand(session: AsyncSession) -> emails.Brand:
    from app.services.calendar_feeds import public_base

    base, _ = await public_base(session)
    org = str(await get_value(session, "org", "name") or "")
    reply_to = str(await get_value(session, "smtp", "reply_to") or "") or None
    return emails.Brand(org_name=org, base_url=base, reply_to=reply_to)


async def overrides(session: AsyncSession, locale: str) -> dict[str, str]:
    from app.services import bookings_i18n

    return dict((await bookings_i18n.overrides(session, locale)).get("email", {}))


async def render_for(session: AsyncSession, kind: str, locale: str | None = None, **ctx: Any) -> emails.Rendered:
    """:func:`app.emails.render` with the organisation's overrides (translation set ``email``) and brand."""
    lang = await resolve_locale(session, locale)
    return emails.render(kind, lang, strings=await overrides(session, lang), brand=await brand(session), **ctx)


async def resolve_locale(session: AsyncSession, locale: str | None = None, user: User | None = None) -> str:
    from app.services import bookings_i18n

    if locale:
        return bookings_i18n.display_language(locale)
    if user is not None:
        from app.services.bookings_notify import _language

        return bookings_i18n.display_language(await _language(session, user))
    return bookings_i18n.display_language(str(await get_value(session, "org", "default_language") or "tr"))


# --------------------------------------------------------------------------------------------------
# Building and sending
# --------------------------------------------------------------------------------------------------


_THREAD = re.compile(r"[?&](request|series)=(\d+)")


def thread_id(link: str | None, domain: str) -> str | None:
    """``<request-128@uni.edu.tr>`` for every e-mail about one request (or series), so clients thread them
    (emails.md §6); ``None`` for anything else (security mails never thread)."""
    m = _THREAD.search(link or "")
    return f"<{m.group(1)}-{m.group(2)}@{domain}>" if m and domain else None


def build_message(
    smtp: Mapping[str, Any],
    *,
    to: str,
    rendered: emails.Rendered | None,
    subject: str,
    text: str,
    link: str | None = None,
) -> MailMessage:
    msg = MailMessage()
    from_address = str(smtp["from_address"])
    msg["Subject"] = emails.clean(subject).replace("\n", " ")
    msg["From"] = formataddr((str(smtp.get("from_name") or ""), from_address))
    msg["To"] = to
    if smtp.get("reply_to"):
        msg["Reply-To"] = str(smtp["reply_to"])
    msg["Date"] = formatdate(usegmt=True)
    msg["Message-ID"] = make_msgid(domain=from_address.rsplit("@", 1)[-1] or None)
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    thread = thread_id(link, from_address.rsplit("@", 1)[-1])
    if thread:
        msg["In-Reply-To"] = thread
        msg["References"] = thread
    if rendered is not None:
        msg["Content-Language"] = rendered.locale
    msg.set_content(text)
    if rendered is not None:
        msg.add_alternative(rendered.html, subtype="html")
        if rendered.uses_cid_logo:
            html_part = msg.get_payload()[1]
            html_part.add_related(
                emails.logo_png(),
                maintype="image",
                subtype="png",
                cid=f"<{emails.LOGO_CID}>",
                filename="smartsched.png",
                disposition="inline",
            )
    return msg


class Transcript:
    """Collects smtplib's debug lines as ``C:`` / ``S:``; AUTH exchanges and the message body are never kept."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._in_auth = False

    def add(self, line: str) -> None:
        if len(self.lines) < TRANSCRIPT_MAX:
            self.lines.append(line[:300])

    @staticmethod
    def _plain(raw: Any) -> str:
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes | bytearray) else str(raw)
        if text[:2] in ("b'", 'b"') and text[-1:] in ("'", '"'):
            text = text[2:-1]  # smtplib logs repr(bytes)
        elif text[:1] in ("'", '"') and text[-1:] == text[:1]:
            text = text[1:-1]
        return text.replace("\\r\\n", "\n").replace("\\n", "\n").strip()

    def hook(self, *args: Any) -> None:
        if not args:
            return
        head, rest = str(args[0]), args[1:]
        if head == "send:" and rest:
            text = self._plain(rest[0])
            if text.upper().startswith("AUTH"):
                self._in_auth = True
                words = text.split()
                self.add(f"C: AUTH {words[1] if len(words) > 1 else ''} ********".replace("  ", " "))
            elif self._in_auth:
                self.add("C: ********")
            elif len(text) > 200 or "\n" in text:
                self.add(f"C: <ileti / message, {len(text)} B>")
            else:
                self.add(f"C: {text}")
        elif head == "reply:" and rest:
            text = self._plain(rest[0])
            if text[:3] == "334":
                self.add("S: 334 ********")
                return
            self._in_auth = False  # any other answer ends an AUTH exchange
            self.add(f"S: {text}")


def _open(smtp: Mapping[str, Any], transcript: Transcript | None) -> smtplib.SMTP:
    timeout = int(smtp.get("timeout_s") or 15)
    host, port = str(smtp["host"]), int(smtp.get("port") or 587)
    security = str(smtp.get("security") or "starttls").lower()
    ctx = ssl.create_default_context()
    if transcript is None:
        # the plain path (the queue): smtplib connects in the constructor (tests replace smtplib.SMTP)
        if security == "ssl":
            return smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx)
        return smtplib.SMTP(host, port, timeout=timeout)
    server: smtplib.SMTP
    server = smtplib.SMTP_SSL(timeout=timeout, context=ctx) if security == "ssl" else smtplib.SMTP(timeout=timeout)
    server._print_debug = transcript.hook  # type: ignore[method-assign]
    server.set_debuglevel(1)
    transcript.add(f"* {host}:{port} ({'SSL/TLS' if security == 'ssl' else security.upper()})")
    server.connect(host, port)
    return server


def transmit(smtp: Mapping[str, Any], msg: EmailMessage, transcript: Transcript | None = None) -> None:
    """Connect, secure, sign in and send ``msg`` (blocking; run in a thread)."""
    security = str(smtp.get("security") or "starttls").lower()
    server = _open(smtp, transcript)
    try:
        if security == "starttls":
            server.starttls(context=ssl.create_default_context())
            if transcript is not None:
                sock = getattr(server, "sock", None)
                version = sock.version() if isinstance(sock, ssl.SSLSocket) else "?"
                transcript.add(f"* TLS {version}")
        mode = str(smtp.get("auth_mode") or "password").lower()
        user = str(smtp.get("username") or "")
        if mode == "xoauth2":
            token = mail_oauth.access_token(dict(smtp))
            auth_user = user or str(smtp["from_address"])
            server.ehlo_or_helo_if_needed()
            server.auth(
                "XOAUTH2",
                lambda challenge=None: mail_oauth.xoauth2_string(auth_user, token) if challenge is None else "",
                initial_response_ok=True,
            )
        elif mode != "none" and user:
            server.login(user, str(smtp.get("password") or ""))
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except (smtplib.SMTPException, OSError):
            server.close()


def explain(exc: BaseException, smtp: Mapping[str, Any]) -> tuple[str, str]:
    """A plain Turkish / English hint for the usual SMTP failures (never echoes a secret)."""
    provider = str(smtp.get("provider") or "")
    if isinstance(exc, mail_oauth.OAuthError):
        return exc.message_tr, exc.message
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        tr = "Kullanıcı adı ya da parola kabul edilmedi."
        en = "The username or password was not accepted."
        if provider.startswith("google"):
            tr += " Gmail için 2 Adımlı Doğrulama açık bir hesapta oluşturulmuş uygulama şifresi gerekir."
            en += " Gmail needs an app password created on an account with 2-Step Verification."
        if provider.startswith("microsoft") or "office365" in str(smtp.get("host") or ""):
            tr += " Microsoft 365'te parola ile SMTP kapatıldı: OAuth2 ön ayarını kullanın."
            en += " Microsoft 365 retired password SMTP: use the OAuth2 preset."
        return tr, en
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            "Sunucu gönderen adresini kabul etmedi: gönderen adresi oturum açan hesapla aynı olmalı ya da hesaba bu "
            "adresten gönderme izni verilmeli.",
            "The server refused the from-address: it must match the signed-in account, or the account needs "
            "permission to send as it.",
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return ("Sunucu alıcı adresini kabul etmedi.", "The server refused the recipient address.")
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return (
            "Sunucu istenen özelliği desteklemiyor (STARTTLS ya da oturum açma yöntemi): güvenlik ve oturum açma "
            "yöntemini kontrol edin.",
            "The server does not support the requested feature (STARTTLS or the sign-in method): check the security "
            "and sign-in settings.",
        )
    if isinstance(exc, smtplib.SMTPResponseException) and exc.smtp_code == 530:
        return (
            "Sunucu önce şifreli bağlantı ya da oturum açma istiyor: güvenlik için STARTTLS seçin ve kullanıcı bilgilerini girin.",
            "The server wants encryption or a sign-in first: choose STARTTLS and enter the credentials.",
        )
    if isinstance(exc, ssl.SSLError):
        return (
            "TLS bağlantısı kurulamadı: 465 için SSL/TLS, 587 için STARTTLS seçin; sunucunun sertifikası geçerli olmalı.",
            "The TLS handshake failed: use SSL/TLS for 465 and STARTTLS for 587; the server certificate must be valid.",
        )
    if isinstance(exc, socket.gaierror):
        return ("Sunucu adı çözülemedi: ana bilgisayar adını kontrol edin.", "The host name did not resolve: check the host.")
    if isinstance(exc, TimeoutError | socket.timeout):
        return (
            "Sunucuya ulaşılamadı (zaman aşımı): ana bilgisayar adı ve bağlantı noktası doğru mu, güvenlik duvarı "
            "çıkışa izin veriyor mu?",
            "The server did not answer (timeout): are the host and port right, and does the firewall allow outbound "
            "connections?",
        )
    if isinstance(exc, ConnectionRefusedError):
        return (
            "Bağlantı reddedildi: bağlantı noktası yanlış olabilir (587 STARTTLS, 465 SSL/TLS).",
            "The connection was refused: the port may be wrong (587 STARTTLS, 465 SSL/TLS).",
        )
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "Sunucu bağlantıyı kapattı: güvenlik türü bağlantı noktasıyla uyuşmuyor olabilir.",
            "The server closed the connection: the security type may not match the port.",
        )
    return ("İleti gönderilemedi.", "The message could not be sent.")


def configured(smtp: Mapping[str, Any]) -> bool:
    return bool(smtp.get("host") and smtp.get("from_address"))


async def send_test(
    session: AsyncSession,
    to: str,
    actor: User,
    *,
    kind: str = TEST_KIND,
    locale: str | None = None,
    draft: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Send a themed test e-mail now and answer the outcome with the transcript excerpt. ``kind`` other than
    ``smtp_test`` sends that template with its sample data ("test gönder" of the template screen); ``draft`` are
    unsaved overrides to try. The outbox keeps the row (kind ``smtp_test``) as the last check."""
    from app.services import audit

    smtp = await get_group(session, "smtp", reveal=True)
    lang = await resolve_locale(session, locale)
    ctx = emails.sample_context(kind, lang) if kind != TEST_KIND else {"host": smtp.get("host") or "-"}
    ctx.pop("base_url", None)
    strings = {**(await overrides(session, lang)), **dict(draft or {})}
    b = await brand(session)
    if kind != TEST_KIND:
        ctx.setdefault("org", b.org_name or ctx.get("org"))
    rendered = emails.render(kind, lang, strings=strings, brand=b, **ctx)
    subject = rendered.subject if kind == TEST_KIND else f"[Deneme / Test] {rendered.subject}"
    row = NotificationOutbox(
        kind=TEST_KIND,
        to_email=to,
        subject=subject[:255],
        body=rendered.text,
        user_id=actor.id,
        locale=lang,
    )
    session.add(row)
    await session.flush()
    out: dict[str, Any] = {"outbox_id": row.id, "to": to, "kind": kind, "locale": lang}
    if not configured(smtp):
        row.status, row.error = "UNSENT", "SMTP is not configured"
        out.update(
            ok=False,
            status="UNSENT",
            error=row.error,
            hint_tr="Önce SMTP sunucusunu ve gönderen adresini kaydedin.",
            hint_en="Save the SMTP server and the from-address first.",
            transcript=[],
            duration_ms=0,
        )
        return out
    msg = build_message(smtp, to=to, rendered=rendered, subject=subject, text=rendered.text)
    transcript = Transcript()
    started = time.monotonic()
    row.attempts = 1
    try:
        await asyncio.to_thread(transmit, smtp, msg, transcript)
    except (OSError, smtplib.SMTPException, mail_oauth.OAuthError, ValueError) as exc:
        hint_tr, hint_en = explain(exc, smtp)
        detail = f"{type(exc).__name__}: {exc}"
        for secret in (smtp.get("password"), smtp.get("oauth_client_secret"), smtp.get("oauth_refresh_token")):
            if secret:
                detail = detail.replace(str(secret), "********")
        row.status, row.error = "FAILED", detail[:500]
        out.update(ok=False, status="FAILED", error=row.error, hint_tr=hint_tr, hint_en=hint_en)
    else:
        row.status, row.error, row.sent_at = "SENT", None, utcnow()
        out.update(ok=True, status="SENT", error=None, hint_tr=None, hint_en=None)
    out["transcript"] = transcript.lines
    out["duration_ms"] = int((time.monotonic() - started) * 1000)
    await audit.record(
        session,
        "mail.test",
        "settings",
        "smtp",
        after={"to_domain": to.rsplit("@", 1)[-1], "status": row.status, "kind": kind, "locale": lang},
        actor=actor,
    )
    await session.flush()
    return out


# --------------------------------------------------------------------------------------------------
# Status (the "Son değişiklik" line, the integrations hub card)
# --------------------------------------------------------------------------------------------------


def _iso(v: datetime | None) -> str | None:
    if v is None:
        return None
    text = v.isoformat(timespec="seconds")
    return text if v.tzinfo else text + "Z"


async def last_change(session: AsyncSession) -> dict[str, Any] | None:
    keys = [f"smtp.{k}" for k in SETTINGS_KEYS]
    q = (
        select(AuditEvent.actor_label, AuditEvent.ts, AuditEvent.entity_id)
        .where(and_(AuditEvent.entity_type == "settings", AuditEvent.entity_id.in_(keys)))
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    row = (await session.execute(q)).first()
    if row is None:
        return None
    return {"by": row[0], "at": _iso(row[1]), "key": str(row[2]).removeprefix("smtp.")}


async def last_check(session: AsyncSession) -> dict[str, Any] | None:
    q = (
        select(NotificationOutbox)
        .where(NotificationOutbox.kind == TEST_KIND, NotificationOutbox.status.in_(("SENT", "FAILED")))
        .order_by(NotificationOutbox.id.desc())
        .limit(1)
    )
    row = (await session.execute(q)).scalars().first()
    if row is None:
        return None
    return {
        "at": _iso(row.sent_at or row.created_at),
        "ok": row.status == "SENT",
        "error": row.error,
        "outbox_id": row.id,
    }


async def status(session: AsyncSession) -> dict[str, Any]:
    smtp = await get_group(session, "smtp", reveal=True)
    check = await last_check(session)
    if not configured(smtp):
        state = "not_configured"
    elif check is not None and not check["ok"]:
        state = "error"
    else:
        state = "connected"
    return {
        "state": state,
        "configured": configured(smtp),
        "provider": smtp.get("provider") or "",
        "host": smtp.get("host") or "",
        "from_address": smtp.get("from_address") or "",
        "auth_mode": smtp.get("auth_mode") or "password",
        "tested": check is not None,
        "last_check": check,
        "last_change": await last_change(session),
    }
