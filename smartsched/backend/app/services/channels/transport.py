"""The network boundary of the notification channels. Only the integrations worker and two administrator actions
(Telegram setup, the WhatsApp Web bridge QR) reach this module; request handlers of ordinary users never call out.

* :func:`apprise_send`: Telegram (``tgram://``), WhatsApp Business Cloud (``whatsapp://``), SMS (``twilio://``,
  ``vonage://``), Teams Workflows and Slack incoming webhooks (their native URLs) through Apprise (BSD-2-Clause).
  Apprise uses its own HTTP stack, so the callers check the URL (vendor allowlist + the M-41 DNS check) right
  before the send.
* :func:`webpush_send`: the payload is encrypted with pywebpush (RFC 8291, aes128gcm) and signed with a VAPID JWT
  (RFC 8292); the POST goes through :func:`http_client`, the webhook client with the SSRF-guarded network backend.
* :func:`telegram_api`: getMe / setWebhook / deleteWebhook / getUpdates on ``api.telegram.org``.
* :func:`bridge_api`: the WhatsApp Web bridge (wuzapi) at the operator-set ``WHATSAPP_BRIDGE_URL``.

Secrets never reach a log line or a stored error: :func:`redact` removes every credential of the send (also
URL-encoded, and both halves of a Telegram bot token) and :class:`_AppriseRedactor` filters Apprise's own logger.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

log = logging.getLogger(__name__)

TIMEOUT_S = 15.0
_active_secrets: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar("channel_secrets", default=())


def _variants(secret: str) -> set[str]:
    out = {secret, quote(secret, safe=""), quote(secret)}
    if ":" in secret:  # a Telegram bot token "<bot id>:<key>": the key alone is the secret part
        out |= {part for part in secret.split(":") if len(part) >= 8}
    return {v for v in out if len(v) >= 6}


def redact(text: str | None, secrets: Iterable[str]) -> str:
    out = text or ""
    for s in sorted({v for sec in secrets if sec for v in _variants(sec)}, key=len, reverse=True):
        out = out.replace(s, "***")
    return out


class _AppriseRedactor(logging.Filter):
    """Apprise logs to the ``apprise`` logger, sometimes with the notification URL; the URL carries the bot token."""

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = _active_secrets.get()
        if secrets:
            try:
                msg = record.getMessage()
            except Exception:  # noqa: BLE001 - a broken format string must not break the send
                msg = str(record.msg)
            record.msg, record.args = redact(msg, secrets), ()
        return True


_REDACTOR = _AppriseRedactor()


def _install_redactor() -> None:
    lg = logging.getLogger("apprise")
    if _REDACTOR not in lg.filters:
        lg.addFilter(_REDACTOR)


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error: str | None = None
    #: the address is gone for good (push subscription expired): delete it
    gone: bool = False
    #: the recipient blocked the sender (Telegram 403): stop sending
    blocked: bool = False


def http_client(**_kw: Any) -> httpx.AsyncClient:
    """Outbound client with the M-41 SSRF guard (resolve, refuse private / metadata, connect to the checked address);
    tests replace this function."""
    from app.services import webhooks

    return webhooks.http_client()


def bridge_client(**_kw: Any) -> httpx.AsyncClient:
    """Client for the in-pod WhatsApp Web bridge (operator-set URL, a private address by design)."""
    return httpx.AsyncClient(timeout=TIMEOUT_S, trust_env=False, follow_redirects=False)


# --------------------------------------------------------------------------------------------------
# Apprise
# --------------------------------------------------------------------------------------------------


def apprise_url_ok(url: str, plugin: str | None = None) -> bool:
    """Apprise can parse ``url`` (and, with ``plugin``, maps it to that notifier class, e.g. ``NotifySlack``)."""
    import apprise

    ap = apprise.Apprise()
    if not ap.add(url):
        return False
    return plugin is None or type(ap[0]).__name__ == plugin


async def apprise_send(url: str, title: str, body: str, secrets: Iterable[str]) -> SendResult:
    secret_list = tuple(s for s in secrets if s)
    _install_redactor()

    def run() -> SendResult:
        import apprise

        token = _active_secrets.set(secret_list)
        try:
            ap = apprise.Apprise()
            if not ap.add(url):
                return SendResult(False, "the sender URL is not valid for Apprise (check the channel settings)")
            with apprise.LogCapture(level=logging.INFO) as captured:
                ok = bool(ap.notify(body=body, title=title))
                text = captured.getvalue() if hasattr(captured, "getvalue") else ""
            if ok:
                return SendResult(True)
            detail = redact(text, secret_list).strip().splitlines()
            message = (detail[-1] if detail else "the provider refused the message")[:400]
            lowered = text.lower()
            blocked = "403" in lowered and ("blocked" in lowered or "forbidden" in lowered)
            return SendResult(False, message, blocked=blocked)
        except Exception as exc:  # noqa: BLE001 - recorded on the delivery row, never raised into a request
            return SendResult(False, redact(f"{type(exc).__name__}: {exc}", secret_list)[:400])
        finally:
            _active_secrets.reset(token)

    return await asyncio.to_thread(run)


# --------------------------------------------------------------------------------------------------
# Web Push (pywebpush + py_vapid, HTTP through the guarded client)
# --------------------------------------------------------------------------------------------------


def _vapid_headers(pem: str, contact: str, endpoint: str) -> dict[str, str]:
    from py_vapid import Vapid02

    parts = urlsplit(endpoint)
    claims: dict[str, str | int] = {
        "sub": contact,
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int(time.time()) + 12 * 3600,
    }
    signed = Vapid02.from_pem(pem.encode("ascii")).sign(claims)
    return {str(k): str(v) for k, v in signed.items()}


async def webpush_send(subscription: dict[str, Any], payload: bytes, pem: str, contact: str, ttl: int) -> SendResult:
    from pywebpush import WebPusher

    endpoint = str(subscription["endpoint"])
    try:
        encoded = WebPusher(subscription).encode(payload, "aes128gcm")
        headers = {
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(ttl),
            "Urgency": "normal",
            **_vapid_headers(pem, contact, endpoint),
        }
    except Exception as exc:  # noqa: BLE001 - a malformed subscription
        return SendResult(False, f"cannot encrypt for this subscription: {type(exc).__name__}", gone=True)
    try:
        async with http_client() as client:
            resp = await client.post(endpoint, content=encoded["body"], headers=headers)
    except httpx.HTTPError as exc:
        return SendResult(False, f"{type(exc).__name__}: {str(exc)[:200]}")
    if resp.status_code in (200, 201, 202):
        return SendResult(True)
    if resp.status_code in (404, 410):
        return SendResult(False, f"push service answered {resp.status_code}: subscription expired", gone=True)
    return SendResult(False, f"push service answered HTTP {resp.status_code}")


# --------------------------------------------------------------------------------------------------
# Telegram Bot API (setup, long poll) and the WhatsApp Web bridge
# --------------------------------------------------------------------------------------------------


class ProviderCallError(Exception):
    """A provider call failed; the message is redacted and safe to show to an administrator."""


async def telegram_api(token: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        async with http_client() as client:
            resp = await client.post(url, json=payload or {})
    except httpx.HTTPError as exc:
        raise ProviderCallError(redact(f"Telegram {method}: {type(exc).__name__}: {exc}", [token])[:300]) from None
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("ok", resp.status_code == 200)
    data["http_status"] = resp.status_code
    if "description" in data:
        data["description"] = redact(str(data["description"]), [token])[:300]
    return data


async def bridge_api(method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.services.channels.config import bridge_url

    base = bridge_url()
    if not base:
        raise ProviderCallError("WHATSAPP_BRIDGE_URL is not set on the backend")
    try:
        async with bridge_client() as client:
            resp = await client.request(method, f"{base}{path}", json=payload, headers={"Token": token})
    except httpx.HTTPError as exc:
        raise ProviderCallError(redact(f"bridge {path}: {type(exc).__name__}: {exc}", [token])[:300]) from None
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["http_status"] = resp.status_code
    return data
