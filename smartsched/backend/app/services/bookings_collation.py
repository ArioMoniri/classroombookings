"""Turkish alphabetical order for the CRBS name lists (users, departments, room groups, rooms).

CRBS sorts in MySQL with a Unicode collation, so "Çağla" comes before "Dilek" and "İpek" after "Işık"; a plain
code-point sort puts Ç, İ, Ö, Ş, Ü after Z. First used by GET /users/search (CRBS superset gate, 2026-10-08)."""

from __future__ import annotations

from app.importers import normalize as n

#: Turkish alphabet (TDK) with q, w, x where Latin puts them
_TR_ORDER = {ch: i for i, ch in enumerate("abcçdefgğhıijklmnoöpqrsştuüvwxyz")}


def tr_sort_key(value: str | None) -> tuple[tuple[int, int], ...]:
    """Sort key for Turkish names: ``tr_casefold`` (I/ı, İ/i, NBSP, runs of spaces), then letters in Turkish
    order; digits and punctuation sort before letters, other characters after them."""
    return tuple(
        (1, _TR_ORDER[ch]) if ch in _TR_ORDER else (0, ord(ch)) if ord(ch) < 128 else (2, ord(ch))
        for ch in n.tr_casefold(value or "")
    )
