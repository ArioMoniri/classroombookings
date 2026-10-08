"""Login identifiers: Turkish-aware normalisation of usernames and e-mails.

Usernames are matched without regard to case **and** to the Turkish dotted/dotless I (``İ``, ``I``,
``ı`` and ``i`` all fold to ``i``), so ``İLKER.ŞAHİN``, ``ILKER.ŞAHİN`` and ``ılker.şahin`` are one account.
NBSP / zero-width characters and compatibility forms (NFKC) are removed before matching.
"""

from __future__ import annotations

import re
import unicodedata

_USERNAME_RX = re.compile(r"^[\w.@+-]{1,255}$")
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍﻿"), None)


def _clean(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).translate(_INVISIBLE).replace("\xa0", " ")
    return text.strip()


def fold_username(value: str) -> str:
    """Canonical (stored and compared) form of a username; raises ``ValueError`` when invalid."""
    text = _clean(value)
    text = text.replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    if not _USERNAME_RX.match(text):
        raise ValueError("username may contain letters, digits and . _ - @ + only (no spaces)")
    return text


def clean_email(value: str) -> str:
    text = _clean(value)
    text = text.replace("İ", "i").replace("I", "i").lower()
    if "@" not in text or len(text) < 3 or " " in text:
        raise ValueError("invalid email")
    return text
