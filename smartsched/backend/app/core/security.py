"""Security helpers: password hashing (argon2), JWT tokens (PyJWT), Fernet encryption for secret settings."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # malformed hash
        return False


def _fernet(secret: str | None = None) -> Fernet:
    secret = secret or get_settings().app_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain: str, secret: str | None = None) -> str:
    return _fernet(secret).encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str, secret: str | None = None) -> str:
    try:
        return _fernet(secret).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("cannot decrypt secret (APP_SECRET changed?)") from exc


def mask_secret(plain: str | None) -> str | None:
    if not plain:
        return None
    if len(plain) <= 8:
        return "*" * len(plain)
    return f"{plain[:4]}{'*' * 8}{plain[-4:]}"


def create_access_token(subject: str, extra: dict[str, Any] | None = None, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.app_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.app_secret, algorithms=[settings.jwt_algorithm])
