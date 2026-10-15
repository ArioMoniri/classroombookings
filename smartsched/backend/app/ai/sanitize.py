"""Clean uploaded text before it leaves the server (review 2026-10-15: KVKK + prompt injection).

* Zero-width, bidi and other invisible control characters are stripped: they hide instructions from the
  reviewer ("Trojan Source" style) and carry no scheduling meaning.
* E-mail addresses and phone numbers are redacted (``[e-posta]`` / ``[telefon]``): they are personal data
  under KVKK and never needed to map a preference to a rule.
* The ``<document>`` wrapper the prompts put around file text cannot be opened or closed from inside the file.

Scheduling data (course codes, rooms, dates, times, periods, enrolments) is left untouched; the patterns are
deliberately narrow (Turkish numbers with a 0 / +90 / 5xx prefix and international ``+`` numbers).
"""

from __future__ import annotations

import re

#: zero-width / invisible formatting characters
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064\ufeff\u180e"
#: bidi embeddings, overrides, isolates and marks
_BIDI = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f\u061c"
#: C0 controls except tab / newline / carriage return, and DEL
_C0 = "".join(chr(c) for c in range(0x20) if chr(c) not in "\t\n\r") + "\x7f"
_CONTROLS_RE = re.compile(f"[{re.escape(_ZERO_WIDTH + _BIDI + _C0)}]")

_EMAIL_RE = re.compile(r"(?<![\w.%+-])[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}(?![\w-])")
_SEP = r"[ .\-]?"
_PHONE_RES = (
    # international: +90 532 123 45 67, +90 (532) 123-45-67, +44 20 7946 0958
    re.compile(rf"(?<![\w+])\+\d{{1,3}}{_SEP}(?:\(\d{{1,4}}\){_SEP})?\d{{1,4}}(?:{_SEP}\d{{2,4}}){{1,4}}(?![\w])"),
    # Turkish with the trunk 0: 0532 123 45 67, 0(212) 555 12 34, 05321234567, 0212.555.12.34
    re.compile(rf"(?<![\w+])0[ .]?\(?[2-5]\d{{2}}\)?{_SEP}\d{{3}}{_SEP}\d{{2}}{_SEP}\d{{2}}(?![\w])"),
    # Turkish mobile without the 0: 532 123 45 67, (532) 123 45 67
    re.compile(rf"(?<![\w+(])\(?5\d{{2}}\)?{_SEP}\d{{3}}{_SEP}\d{{2}}{_SEP}\d{{2}}(?![\w])"),
)
_MIN_PHONE_DIGITS = 9
_DOC_TAG_RE = re.compile(r"<\s*/?\s*document\b[^>]*>", re.IGNORECASE)

EMAIL_MARK = "[e-posta]"
PHONE_MARK = "[telefon]"
TAG_MARK = "(document)"


def strip_controls(text: str) -> str:
    """``text`` without zero-width, bidi and C0 control characters (newlines and tabs are kept)."""
    return _CONTROLS_RE.sub("", text or "")


def clean_for_model(text: str) -> tuple[str, dict[str, int]]:
    """``(clean text, counts)`` with counts ``controls``, ``emails``, ``phones``, ``tags``."""
    stats = {"controls": 0, "emails": 0, "phones": 0, "tags": 0}
    out, stats["controls"] = _CONTROLS_RE.subn("", text or "")
    out, stats["tags"] = _DOC_TAG_RE.subn(TAG_MARK, out)
    out, stats["emails"] = _EMAIL_RE.subn(EMAIL_MARK, out)

    def phone(m: re.Match[str]) -> str:
        if sum(ch.isdigit() for ch in m.group(0)) < _MIN_PHONE_DIGITS:
            return m.group(0)
        stats["phones"] += 1
        return PHONE_MARK

    for rx in _PHONE_RES:
        out = rx.sub(phone, out)
    return out, stats


__all__ = ["EMAIL_MARK", "PHONE_MARK", "clean_for_model", "strip_controls"]
