"""Security helpers: password hashing (argon2), JWT tokens (PyJWT), Fernet encryption for secret settings."""

from __future__ import annotations

import base64
import hashlib
import re
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


#: hashes carried over from a CRBS database (``password_hash()`` bcrypt, and the 2018 ``sha1:`` upgrade format)
LEGACY_PREFIXES = ("$2y$", "$2a$", "$2b$", "sha1:")


def _bcrypt_verify(password: str, hashed: str) -> bool:
    import bcrypt

    h = hashed.encode("ascii", errors="ignore")
    if h.startswith(b"$2y$"):  # PHP's bcrypt marker; the same algorithm as $2b$
        h = b"$2b$" + h[4:]
    try:
        return bool(bcrypt.checkpw(password.encode("utf-8")[:72], h))  # PHP uses the first 72 bytes too
    except ValueError:  # malformed hash
        return False


def verify_password(password: str, password_hash: str) -> bool:
    """argon2 (SmartSched), or a legacy CRBS hash exactly as ``Auth_local::verify`` checks it: ``$2y$`` bcrypt
    of the password, or ``sha1:`` + bcrypt of ``sha1(password)`` (hex). Callers rehash legacy hashes to
    argon2 after a successful check (:func:`password_needs_rehash`)."""
    if not password_hash:
        return False
    if password_hash.startswith("sha1:"):
        return _bcrypt_verify(hashlib.sha1(password.encode("utf-8")).hexdigest(), password_hash[5:])
    if password_hash.startswith(LEGACY_PREFIXES):
        return _bcrypt_verify(password, password_hash)
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # malformed hash
        return False


def password_needs_rehash(password_hash: str) -> bool:
    if password_hash.startswith(LEGACY_PREFIXES):
        return True
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
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
    return jwt.encode(payload, settings.signing_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.signing_key, algorithms=[settings.jwt_algorithm])


_KEY_RX = re.compile(r"sk-ant-[A-Za-z0-9_\-]{4,}")


def redact_keys(text: str) -> str:
    """Remove anything that looks like an Anthropic API key from ``text`` (logs, error messages)."""
    return _KEY_RX.sub("sk-ant-***", text)


def validate_api_key(value: str) -> str:
    """A pasted API key: surrounding whitespace dropped; control characters, inner whitespace and absurd
    lengths are refused (they ended up in HTTP headers and error texts; review MINOR 3)."""
    key = (value or "").strip()
    if not key:
        return key
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in key):
        raise ValueError("the API key contains spaces or control characters; paste it again")
    if not 20 <= len(key) <= 300:
        raise ValueError("the API key length is not plausible (20..300 characters)")
    return key


def key_fingerprint(key: str) -> str:
    return hashlib.sha256(("key-fp:" + key).encode("utf-8")).hexdigest()[:16]
