"""TOTP (RFC 6238) and recovery codes for two-step sign-in (AU-B; docs/research/2026-10-18-auth-backend.md §2, §4).

* HMAC-SHA-1, 6 digits, 30 s steps (what every authenticator app reads from the ``otpauth://`` URI);
* a 160-bit secret from :mod:`secrets` (RFC 4226 R6), shown as unpadded Base32;
* :func:`match` accepts the current step and one step either way (clock drift), and only a step *after* the last one
  the account used (replay resistance, NIST SP 800-63B-4 §3.2.7, ASVS 6.5.1);
* recovery codes: 10 × 16 Crockford Base32 characters (80 bits, ≥ the 64 bits of 800-63B-4 §4.2.1.1), grouped
  ``XXXX-XXXX-XXXX-XXXX``; typed input ignores case, spaces and dashes and maps O→0, I/L→1.

Stdlib only (no pyotp): the replay rule needs the matched step, which is the whole algorithm anyway.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote

PERIOD = 30
DIGITS = 6
DRIFT_STEPS = 1
SECRET_BYTES = 20
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RECOVERY_COUNT = 10
RECOVERY_LEN = 16


def now() -> float:
    """The server clock (the trusted time source, ASVS 6.5.8); tests replace it."""
    return time.time()


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, at: float, *, digits: int = DIGITS) -> str:
    """The code of the step containing unix time ``at`` (RFC 6238 §4, RFC 4226 §5.3 dynamic truncation)."""
    return _hotp(_key(secret), int(at // PERIOD), digits)


def _hotp(key: bytes, counter: int, digits: int) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[off : off + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


_CODE_RX = re.compile(r"^\d{6}$")


def match(secret: str, code: str | None, *, now: float | None = None, last_step: int | None = None) -> int | None:
    """The step a typed ``code`` belongs to (current ±1), or ``None``. A step at or before ``last_step`` (the one the
    account used last) never matches, so a code works once."""
    typed = re.sub(r"\s+", "", code or "")
    if not _CODE_RX.match(typed):
        return None
    t = globals()["now"]() if now is None else now
    key = _key(secret)
    current = int(t // PERIOD)
    found: int | None = None
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        if hmac.compare_digest(_hotp(key, step, DIGITS), typed):  # every step is computed: no timing hint
            found = step
    if found is None or (last_step is not None and found <= last_step):
        return None
    return found


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """``otpauth://totp/Issuer:account?secret=…&issuer=…`` (Google Authenticator Key Uri Format)."""
    label = f"{quote(issuer, safe='')}:{quote(account, safe='')}"
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"
    )


def new_recovery_codes(count: int = RECOVERY_COUNT) -> list[str]:
    out: set[str] = set()
    while len(out) < count:
        raw = "".join(secrets.choice(CROCKFORD) for _ in range(RECOVERY_LEN))
        out.add("-".join(raw[i : i + 4] for i in range(0, RECOVERY_LEN, 4)))
    return sorted(out)


_TYPO = str.maketrans({"O": "0", "I": "1", "L": "1"})


def normalise_recovery(typed: str | None) -> str | None:
    """The canonical 16 characters of a typed recovery code, or ``None`` when it cannot be one."""
    s = re.sub(r"[\s\-]+", "", (typed or "")).upper().translate(_TYPO)
    if len(s) != RECOVERY_LEN or any(ch not in CROCKFORD for ch in s):
        return None
    return s


__all__ = [
    "CROCKFORD",
    "DIGITS",
    "PERIOD",
    "code_at",
    "match",
    "new_recovery_codes",
    "new_secret",
    "normalise_recovery",
    "now",
    "provisioning_uri",
]
