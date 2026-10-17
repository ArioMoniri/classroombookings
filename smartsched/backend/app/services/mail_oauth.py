"""OAuth2 access tokens for SMTP XOAUTH2 (Google, Microsoft 365) (wave 3b W3-MAIL).

* Google: ``refresh_token`` grant at ``https://oauth2.googleapis.com/token`` (scope ``https://mail.google.com/``,
  granted when the refresh token was issued).
* Microsoft 365: ``client_credentials`` grant (scope ``https://outlook.office365.com/.default``, application
  permission ``SMTP.SendAsApp`` + an Exchange service principal with rights on the mailbox) or, when a refresh token
  is stored, the delegated ``refresh_token`` grant (scope ``https://outlook.office.com/SMTP.Send offline_access``).

Runs inside the SMTP worker thread (sync ``httpx``). Tokens are cached in-process until a minute before they expire.
Errors never echo the secret; the provider's ``error`` / ``error_description`` are passed on (they carry none).
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from typing import Any

import httpx

GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
MS_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
MS_APP_SCOPE = "https://outlook.office365.com/.default"
MS_DELEGATED_SCOPE = "https://outlook.office.com/SMTP.Send offline_access"
_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,99}$")

_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


class OAuthError(Exception):
    def __init__(self, message: str, message_tr: str) -> None:
        super().__init__(message)
        self.message, self.message_tr = message, message_tr


def _post(url: str, data: dict[str, str], timeout: float) -> dict[str, Any]:
    """POST the token request (tests replace this function)."""
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, data=data, headers={"Accept": "application/json"})
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code >= 400 or "access_token" not in body:
        code = str(body.get("error") or r.status_code)
        desc = str(body.get("error_description") or "").split("\r\n")[0][:200]
        raise OAuthError(
            f"token endpoint refused: {code} {desc}".strip(),
            f"Erişim jetonu alınamadı: {code} {desc}".strip(),
        )
    return dict(body)


def _request(smtp: dict[str, Any]) -> tuple[str, dict[str, str]]:
    provider = str(smtp.get("oauth_provider") or "").lower()
    client_id = str(smtp.get("oauth_client_id") or "").strip()
    secret = str(smtp.get("oauth_client_secret") or "")
    refresh = str(smtp.get("oauth_refresh_token") or "")
    if not client_id or not secret:
        raise OAuthError(
            "OAuth2 needs a client ID and a client secret", "OAuth2 için istemci kimliği ve gizli anahtar gerekir"
        )
    if provider == "google":
        if not refresh:
            raise OAuthError("Google OAuth2 needs a refresh token", "Google OAuth2 için yenileme jetonu gerekir")
        return GOOGLE_TOKEN, {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": secret,
            "refresh_token": refresh,
        }
    if provider == "microsoft":
        tenant = str(smtp.get("oauth_tenant") or "").strip()
        if not _TENANT.match(tenant):
            raise OAuthError(
                "Microsoft OAuth2 needs the directory (tenant) ID",
                "Microsoft OAuth2 için dizin (kiracı) kimliği gerekir",
            )
        url = MS_TOKEN.format(tenant=tenant)
        if refresh:
            return url, {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": secret,
                "refresh_token": refresh,
                "scope": MS_DELEGATED_SCOPE,
            }
        return url, {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": MS_APP_SCOPE,
        }
    raise OAuthError("choose Google or Microsoft for OAuth2", "OAuth2 için Google ya da Microsoft seçin")


def access_token(smtp: dict[str, Any], *, timeout: float = 15.0) -> str:
    url, data = _request(smtp)
    key = hashlib.sha256(repr(sorted(data.items())).encode()).hexdigest()
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[1] > now + 60:
            return hit[0]
    body = _post(url, data, timeout)
    token = str(body["access_token"])
    ttl = float(body.get("expires_in") or 3600)
    with _lock:
        _cache[key] = (token, now + ttl)
    return token


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def xoauth2_string(user: str, token: str) -> str:
    """The SASL XOAUTH2 initial response (before base64): ``user=<u>^Aauth=Bearer <t>^A^A``."""
    return f"user={user}\x01auth=Bearer {token}\x01\x01"
