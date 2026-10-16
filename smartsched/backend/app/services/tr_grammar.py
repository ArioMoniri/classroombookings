"""Turkish suffixes for generated messages (room codes, numbers): ``dative("B 201") == "B 201'e"``.

Turkish vowel harmony follows the *spoken* last word, so a code ending in digits takes the suffix of how its number
is read: 201 = "iki yüz bir" -> 'e, 606 = "altı yüz altı" -> 'ya, 30 = "otuz" -> 'a, 100 = "yüz" -> 'e. Codes ending
in letters follow their last vowel (``LAB`` -> 'a); a final vowel takes the buffer ``y``.
"""

from __future__ import annotations

_UNITS = {
    "1": "bir",
    "2": "iki",
    "3": "üç",
    "4": "dört",
    "5": "beş",
    "6": "altı",
    "7": "yedi",
    "8": "sekiz",
    "9": "dokuz",
}
_TENS = {
    "1": "on",
    "2": "yirmi",
    "3": "otuz",
    "4": "kırk",
    "5": "elli",
    "6": "altmış",
    "7": "yetmiş",
    "8": "seksen",
    "9": "doksan",
}
_BACK = set("aıouAIOU")
_FRONT = set("eiöüEİÖÜ")


def _spoken_tail(text: str) -> str:
    """The word whose vowels decide the suffix."""
    t = text.rstrip()
    digits = ""
    while t and t[-1].isdigit():
        digits = t[-1] + digits
        t = t[:-1]
    if not digits:
        return t.split()[-1] if t.split() else t
    n = digits.lstrip("0")
    if not n:
        return "sıfır"
    if n[-1] != "0":
        return _UNITS[n[-1]]
    if len(n) >= 2 and n[-2] != "0":
        return _TENS[n[-2]]
    if len(n) >= 3 and n[-3] != "0":
        return "yüz"
    if len(n) >= 4:
        return "bin" if len(n) <= 6 else "milyon"
    return _TENS.get(n[-2], "on") if len(n) >= 2 else _UNITS.get(n, "bir")


_POSSESSIVE_NOUNS = ("dersliği", "salonu", "laboratuvarı", "amfisi", "odası", "sınıfı", "binası", "bloğu", "katı")


def dative(text: str) -> str:
    """``text`` + the dative suffix: with an apostrophe for proper names and codes (``B 201'e``, ``LAB'a``), and
    without one for a room named by a common noun with a possessive (``Test dersliği`` -> ``Test dersliğine``, never
    ``Test dersliği'ye``; round-1 R1-S-24 / T-R1-49): the possessive takes the buffer ``n``."""
    word = _spoken_tail(text)
    vowels = [c for c in word if c in _BACK or c in _FRONT]
    front = bool(vowels) and vowels[-1] in _FRONT
    suffix = "e" if front else "a"
    lowered = word.lower()
    if word and word[0].islower() and any(lowered.endswith(n) for n in _POSSESSIVE_NOUNS):
        return f"{text.rstrip()}n{suffix}"
    if word and (word[-1] in _BACK or word[-1] in _FRONT):
        suffix = "y" + suffix
    return f"{text.rstrip()}'{suffix}"


def _runs(weeks: list[int]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for w in sorted(set(weeks)):
        if out and w == out[-1][1] + 1:
            out[-1][1] = w
        else:
            out.append([w, w])
    return [(a, b) for a, b in out]


def week_list(weeks: list[int], lang: str = "tr") -> str:
    """Weeks in one phrase, singular for one week (round-1 R1-S-23 / R1-M-14; mirrors the frontend's
    ``lib/i18n/turkish.ts`` ``weekList``): ``3. hafta``, ``3. ve 5. haftalar``, ``1.–4. haftalar``,
    ``1.–4. ve 6. haftalar``; English ``week 3``, ``weeks 3 and 5``, ``weeks 1–4``. Empty -> ``""``."""
    parts = _runs(list(weeks))
    if not parts:
        return ""
    tr = lang == "tr"
    if sum(b - a + 1 for a, b in parts) == 1:
        return f"{parts[0][0]}. hafta" if tr else f"week {parts[0][0]}"
    flat: list[str] = []
    for a, b in parts:
        if a == b:
            flat.append(f"{a}." if tr else str(a))
        elif b == a + 1:
            flat += [f"{a}.", f"{b}."] if tr else [str(a), str(b)]
        else:
            flat.append(f"{a}.–{b}." if tr else f"{a}–{b}")
    joined = flat[0] if len(flat) == 1 else f"{', '.join(flat[:-1])} {'ve' if tr else 'and'} {flat[-1]}"
    return f"{joined} haftalar" if tr else f"weeks {joined}"


def pct(value: float, lang: str = "tr", digits: int | None = None) -> str:
    """A percentage of 0..100: Turkish ``%95`` / ``%0,6``, English ``95%`` / ``0.6%``; never ``100 %``."""
    d = digits if digits is not None else (0 if float(value).is_integer() else 1)
    num = f"{value:.{d}f}"
    return f"%{num.replace('.', ',')}" if lang == "tr" else f"{num}%"


__all__ = ["dative", "pct", "week_list"]
