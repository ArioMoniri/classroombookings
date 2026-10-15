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


def dative(text: str) -> str:
    """``text`` + the dative suffix with an apostrophe (proper names, codes): -'a / -'e / -'ya / -'ye."""
    word = _spoken_tail(text)
    vowels = [c for c in word if c in _BACK or c in _FRONT]
    front = bool(vowels) and vowels[-1] in _FRONT
    suffix = "e" if front else "a"
    if word and (word[-1] in _BACK or word[-1] in _FRONT):
        suffix = "y" + suffix
    return f"{text.rstrip()}'{suffix}"


__all__ = ["dative"]
