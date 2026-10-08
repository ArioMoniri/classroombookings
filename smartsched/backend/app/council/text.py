"""Locale-independent value parsing for the Ingestion Council (TR, EN, DE, FR, ES, IT, PT).

The university-specific parsers live in :mod:`app.importers.normalize` (Turkish days, the 18-period
grid, buildings A-D). The council needs versions that make no assumption about the institution:
day and month names in several languages, AM/PM times, dashed/dotted room codes, ISO and day-first
dates. Everything here is pure and DB-free.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Any

from app.importers import normalize as n

_WS = re.compile(r"\s+")


def fold(value: Any) -> str:
    """Casefold for matching: Turkish dotted/dotless i, diacritics stripped, whitespace collapsed."""
    if value is None:
        return ""
    s = str(value).replace("\xa0", " ").replace("İ", "i").replace("I", "ı")
    s = s.casefold().replace("ı", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ß", "ss")
    return _WS.sub(" ", s).strip()


def cell_text(value: Any) -> str:
    """Workbook/CSV value -> display text (times ``HH:MM``, dates ISO, integral floats as ints)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if (value.hour, value.minute) == (0, 0):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) // 60
        return f"{total // 60 % 24:02d}:{total % 60:02d}"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("\xa0", " ").replace("\r", "").strip()


def is_blank(value: Any) -> bool:
    return n.clean_text(value) is None


# ---------------------------------------------------------------------------
# Days and months
# ---------------------------------------------------------------------------

#: folded day name -> ISO weekday (1 = Monday)
DAY_WORDS: dict[str, int] = {}
for _num, _names in {
    1: ["pazartesi", "monday", "montag", "lundi", "lunes", "lunedi", "segunda", "segunda-feira", "maandag"],
    2: ["sali", "tuesday", "dienstag", "mardi", "martes", "martedi", "terca", "terca-feira", "dinsdag"],
    3: [
        "carsamba",
        "wednesday",
        "mittwoch",
        "mercredi",
        "miercoles",
        "mercoledi",
        "quarta",
        "quarta-feira",
        "woensdag",
    ],
    4: ["persembe", "thursday", "donnerstag", "jeudi", "jueves", "giovedi", "quinta", "quinta-feira", "donderdag"],
    5: ["cuma", "friday", "freitag", "vendredi", "viernes", "venerdi", "sexta", "sexta-feira", "vrijdag"],
    6: ["cumartesi", "saturday", "samstag", "samedi", "sabado", "sabato", "zaterdag"],
    7: ["pazar", "sunday", "sonntag", "dimanche", "domingo", "domenica", "zondag"],
}.items():
    for _name in _names:
        DAY_WORDS[_name] = _num

#: abbreviations accepted only as whole tokens (they collide with other words in running text)
DAY_ABBREV: dict[str, int] = {
    "pzt": 1,
    "mon": 1,
    "mo": 1,
    "lun": 1,
    "seg": 1,
    "sal": 2,
    "tue": 2,
    "tues": 2,
    "di": 2,
    "mar": 2,
    "ter": 2,
    "car": 3,
    "crs": 3,
    "wed": 3,
    "mi": 3,
    "mer": 3,
    "mie": 3,
    "qua": 3,
    "per": 4,
    "prs": 4,
    "thu": 4,
    "thur": 4,
    "thurs": 4,
    "do": 4,
    "jeu": 4,
    "jue": 4,
    "gio": 4,
    "qui": 4,
    "cum": 5,
    "fri": 5,
    "fr": 5,
    "ven": 5,
    "vie": 5,
    "sex": 5,
    "cmt": 6,
    "sat": 6,
    "sa": 6,
    "sam": 6,
    "sab": 6,
    "paz": 7,
    "sun": 7,
    "so": 7,
    "dim": 7,
    "dom": 7,
}

_DAY_RX = re.compile(r"\b(" + "|".join(sorted(map(re.escape, DAY_WORDS), key=len, reverse=True)) + r")\b")
_TOKEN_RX = re.compile(r"[a-z]+")

#: folded month name -> month number
MONTH_WORDS: dict[str, int] = {}
for _num, _names in {
    1: ["ocak", "january", "jan", "januar", "janvier", "enero", "gennaio", "janeiro"],
    2: ["subat", "february", "feb", "februar", "fevrier", "febrero", "febbraio", "fevereiro"],
    3: ["mart", "march", "marz", "mars", "marzo", "marco"],
    4: ["nisan", "april", "apr", "avril", "abril", "aprile"],
    5: ["mayis", "may", "mai", "mayo", "maggio", "maio"],
    6: ["haziran", "june", "jun", "juni", "juin", "junio", "giugno", "junho"],
    7: ["temmuz", "july", "jul", "juli", "juillet", "julio", "luglio", "julho"],
    8: ["agustos", "august", "aug", "aout", "agosto"],
    9: ["eylul", "september", "sep", "sept", "septembre", "septiembre", "settembre", "setembro"],
    10: ["ekim", "october", "oct", "oktober", "octobre", "octubre", "ottobre", "outubro"],
    11: ["kasim", "november", "nov", "novembre", "noviembre", "novembro"],
    12: ["aralik", "december", "dec", "dezember", "decembre", "diciembre", "dicembre", "dezembro"],
}.items():
    for _name in _names:
        MONTH_WORDS[_name] = _num
_MONTH_RX = re.compile(r"\b(" + "|".join(sorted(map(re.escape, MONTH_WORDS), key=len, reverse=True)) + r")\b")


def parse_days(value: Any, *, allow_abbrev: bool = True) -> list[int]:
    """All weekdays named in a cell (``"Salı / Cuma"`` -> [2, 5], ``"Mon"`` -> [1])."""
    text = fold(value)
    if not text:
        return []
    days = [DAY_WORDS[m.group(1)] for m in _DAY_RX.finditer(text)]
    if not days and allow_abbrev:
        tokens = _TOKEN_RX.findall(text)
        if tokens and len(tokens) <= 4:
            days = [DAY_ABBREV[t] for t in tokens if t in DAY_ABBREV]
    return list(dict.fromkeys(days))


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------

_AMPM_RX = re.compile(r"(\d{1,2})(?:\s*[.:h]\s*(\d{2}))?\s*([ap])\.?\s*m\.?\b", re.I)
_CLOCK_RX = re.compile(r"(?<!\d)(\d{1,2})\s*[.:hH]\s*(\d{2})(?!\d)")
_RANGE_SEP = r"\s*(?:-|–|—|~|to|bis|a|à|ile|until)\s*"
_RANGE_RX = re.compile(
    r"(?<!\d)(\d{1,2}\s*[.:hH]\s*\d{2}(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?)"
    + _RANGE_SEP
    + r"(\d{1,2}\s*[.:hH\-]\s*\d{2}(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?)",
    re.I,
)


def _ampm(text: str) -> time | None:
    m = _AMPM_RX.search(text)
    if not m:
        return None
    h, mi, half = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if not (1 <= h <= 12 and 0 <= mi < 60):
        return None
    if half == "p" and h != 12:
        h += 12
    if half == "a" and h == 12:
        h = 0
    return time(h, mi)


def parse_clock(value: Any) -> time | None:
    """One clock time: ``13:30``, ``09.00``, ``9h30``, ``1:30 PM``, Excel time/fraction values."""
    if isinstance(value, str):
        t = _ampm(value)
        if t is not None:
            return t
        m = _CLOCK_RX.search(value)
        if m and len(value.strip()) <= 12:
            h, mi = int(m.group(1)), int(m.group(2))
            return time(h % 24, mi) if 0 <= h <= 24 and mi < 60 else None
    return n.parse_time(value)


def parse_time_range(value: Any) -> tuple[time, time] | None:
    """``08:30-09:10``, ``22.10-22-50`` (typo), ``8:30 – 10:20``, ``1 PM to 3 PM`` -> (start, end)."""
    text = cell_text(value)
    if not text:
        return None
    m = _RANGE_RX.search(text)
    if not m:
        return None
    a = parse_clock(m.group(1))
    b = parse_clock(m.group(2).replace("-", ":"))
    if a is None or b is None:
        return None
    return a, b


def minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t is not None else None


def from_hhmm(s: str | None) -> time | None:
    if not s:
        return None
    try:
        h, m = s.split(":", 1)
        return time(int(h), int(m))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_ISO_RX = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_DMY_RX = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{2,4})(?!\d)")
_DAY_MONTH_RX = re.compile(r"(?<!\d)(\d{1,2})\.?\s+([a-z]+)\.?(?:\s+(\d{4}))?")
_MONTH_DAY_RX = re.compile(r"\b([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?")


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(value: Any, year_hint: int | None = None) -> date | None:
    """ISO, day-first ``13.05.2026`` / ``13/05/2026``, ``13 May 2026``, ``May 13, 2026``,
    ``1 Haziran Pazartesi`` (no year: ``year_hint``)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = fold(cell_text(value))
    if not text:
        return None
    m = _ISO_RX.search(text)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DMY_RX.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        if mo > 12 and d <= 12:  # US month-first
            d, mo = mo, d
        return _mk(y, mo, d)
    m = _DAY_MONTH_RX.search(text)
    if m and m.group(2) in MONTH_WORDS:
        yy = int(m.group(3)) if m.group(3) else year_hint
        return _mk(yy, MONTH_WORDS[m.group(2)], int(m.group(1))) if yy else None
    m = _MONTH_DAY_RX.search(text)
    if m and m.group(1) in MONTH_WORDS:
        yy = int(m.group(3)) if m.group(3) else year_hint
        return _mk(yy, MONTH_WORDS[m.group(1)], int(m.group(2))) if yy else None
    return None


_YEAR_RX = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def years_in(text: str) -> list[int]:
    return [int(y) for y in _YEAR_RX.findall(text or "")]


def month_in(text: str) -> int | None:
    m = _MONTH_RX.search(fold(text))
    return MONTH_WORDS[m.group(1)] if m else None


# ---------------------------------------------------------------------------
# Numbers, codes, people
# ---------------------------------------------------------------------------


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    return n.parse_int_loose(value)


_COURSE_GENERIC_RX = re.compile(r"(?<![A-Za-zÀ-ÿ0-9])([A-ZÇĞİÖŞÜÄÖÜ]{2,6})[\s\-./]?(\d{2,4}[A-Z]?)(?![0-9])")


def course_codes(value: Any) -> list[str]:
    """Canonical course codes in a cell (``MAT 112``, ``INF-101``, ``ING 101 /105``)."""
    codes = n.extract_course_codes(value)
    if codes:
        return codes
    text = n.clean_text(value)
    if not text:
        return []
    up = n.tr_upper(text)
    return list(dict.fromkeys(f"{m.group(1)}{m.group(2)}" for m in _COURSE_GENERIC_RX.finditer(up)))


def course_code(value: Any) -> str | None:
    codes = course_codes(value)
    return codes[0] if codes else None


def display_course(code: str) -> str:
    return n.display_course_code(code)


#: words that name "a room" without saying which one
_GENERIC_ROOM_WORDS = {
    "derslik",
    "room",
    "classroom",
    "sinif",
    "salon",
    "raum",
    "salle",
    "aula",
    "sala",
    "tbd",
    "tba",
    "yok",
    "none",
    "any",
    "herhangi",
    "online",
    "uzem",
    "lab",
    "laboratuvar",
    "amfi",
}
_ROOM_TOKEN_RX = re.compile(r"^([A-Za-zÇĞİÖŞÜçğıöşü]{0,8})[\s\-_.]?([zZ]?\d{1,4}(?:[.\-]\d{1,3})?[A-Za-z]?)$")
_ROOM_SPLIT_RX = re.compile(r"\s*(?:/|,|;|\+|\n|&|\s-\s|\s–\s|\bve\b|\band\b|\bund\b|\bet\b|\by\b)\s*", re.I)


def canon_room(text: str) -> str:
    """Display label -> canonical room code (``A 101`` -> ``A101``, ``Room 1.12`` -> ``ROOM1.12``)."""
    s = n.tr_upper(n.clean_text(text) or "")
    s = re.sub(r"[\s_]+", "", s)
    return s.strip("-.")[:32]


def room_tokens(value: Any) -> list[str]:
    """Room codes named in a cell, any institution (``A 101 / A 106``, ``HS 3, HS 4``, ``B-207``).

    The A-D university aliases of :func:`app.importers.normalize.parse_room_codes` are tried first so
    the universal path agrees with the university path on its own files."""
    text = n.clean_text(value)
    if not text:
        return []
    known = n.parse_room_codes(text)
    if known:
        return known
    out: list[str] = []
    for part in _ROOM_SPLIT_RX.split(text):
        part = part.strip(" ()[]")
        if not part or fold(part) in _GENERIC_ROOM_WORDS:
            continue
        m = _ROOM_TOKEN_RX.match(part)
        if m and len(part) <= 14:
            out.append(canon_room(part))
    return list(dict.fromkeys(out))


_TITLE_WORDS = re.compile(
    r"\b(prof|doc|doç|dr|ogr|öğr|gor|gör|uyesi|üyesi|ars|arş|uzm|mr|mrs|ms|miss|phd|msc|herr|frau|mme|m|sr|sra)\b\.?",
    re.I,
)


def person_key(value: Any) -> str:
    """Canonical person key: folded, academic titles removed (``Prof. Dr. ATA AKIN`` -> ``ata akin``)."""
    parsed = n.canon_person_name(value)
    base = parsed.canonical if parsed else (n.clean_text(value) or "")
    key = _TITLE_WORDS.sub(" ", fold(base))
    return _WS.sub(" ", re.sub(r"[^\w\s]", " ", key)).strip()


def looks_like_person(value: Any) -> bool:
    text = n.clean_text(value)
    if not text or any(ch.isdigit() for ch in text) or len(text) > 80:
        return False
    words = [w for w in re.split(r"[\s.]+", text) if w]
    return 2 <= len(words) <= 8


# ---------------------------------------------------------------------------
# Delivery mode
# ---------------------------------------------------------------------------

_MODE_WORDS: tuple[tuple[str, str], ...] = (
    ("asenkron", "ASYNC"),
    ("asynchron", "ASYNC"),
    ("asynchronous", "ASYNC"),
    ("hibrit", "HYBRID"),
    ("hybrid", "HYBRID"),
    ("hybride", "HYBRID"),
    ("hibrido", "HYBRID"),
    ("ibrido", "HYBRID"),
    ("uzem", "UZEM"),
    ("distance education", "UZEM"),
    ("online", "ONLINE"),
    ("cevrimici", "ONLINE"),
    ("uzaktan", "ONLINE"),
    ("remote", "ONLINE"),
    ("en ligne", "ONLINE"),
    ("a distanza", "ONLINE"),
    ("virtual", "ONLINE"),
    ("hastane", "HOSPITAL"),
    ("hospital", "HOSPITAL"),
    ("klinik", "HOSPITAL"),
    ("simulasyon", "SIMULATION"),
    ("simulation", "SIMULATION"),
    ("yuz yuze", "F2F"),
    ("face to face", "F2F"),
    ("face-to-face", "F2F"),
    ("in person", "F2F"),
    ("in-person", "F2F"),
    ("prasenz", "F2F"),
    ("presentiel", "F2F"),
    ("presencial", "F2F"),
    ("in presenza", "F2F"),
    ("classroom", "F2F"),
    ("derslik", "F2F"),
)
ROOMLESS_MODES = frozenset({"ONLINE", "ASYNC", "UZEM", "HOSPITAL"})


def parse_mode(value: Any) -> str | None:
    text = fold(value)
    if not text:
        return None
    for word, mode in _MODE_WORDS:
        if word in text:
            return mode
    return "OTHER"


# ---------------------------------------------------------------------------
# Language identification (headers and cells are short; stop words + script hints are enough)
# ---------------------------------------------------------------------------

_LANG_WORDS: dict[str, frozenset[str]] = {
    "tr": frozenset(
        "ve ile icin bir bu ders gun saat derslik sinif ogrenci sayisi bolum fakulte sinav tarihi baslangic "
        "bitis haftalar aciklama kodu adi sube yapilacak olarak".split()
    ),
    "en": frozenset(
        "the and of for to in room course day time start end students lecturer section department weeks "
        "remarks title code exam date building capacity seats".split()
    ),
    "de": frozenset(
        "und der die das fur mit raum kurs tag uhrzeit beginn ende studierende dozent gruppe woche "
        "bemerkung prufung datum gebaude platze".split()
    ),
    "fr": frozenset(
        "et le la les des pour salle cours jour heure debut fin etudiants enseignant groupe semaine "
        "remarque examen date batiment places".split()
    ),
    "es": frozenset(
        "y el la los las para aula curso dia hora inicio fin alumnos profesor grupo semana "
        "observaciones examen fecha edificio capacidad".split()
    ),
    "it": frozenset(
        "e il la gli per aula corso giorno ora inizio fine studenti docente gruppo settimana note esame "
        "data edificio posti".split()
    ),
    "pt": frozenset(
        "e o a os as para sala curso dia hora inicio fim alunos professor turma semana observacoes exame "
        "data edificio lugares".split()
    ),
}
_SCRIPT_HINTS = {"tr": "ğşı", "de": "äöüß", "fr": "éèêàç", "es": "ñ¿¡", "pt": "ãõç", "it": "àèìòù"}


def detect_language(texts: list[str]) -> tuple[str, float]:
    """(ISO 639-1 code, confidence 0..1) over a sample of cells/headers; ``("und", 0)`` if unknown."""
    raw = " ".join(t for t in texts if t)[:20000]
    if not raw.strip():
        return "und", 0.0
    words = [w for w in re.findall(r"[a-z]+", fold(raw)) if len(w) >= 2]
    scores = {lang: sum(1 for w in words if w in vocab) for lang, vocab in _LANG_WORDS.items()}
    low = raw.lower()
    for lang, chars in _SCRIPT_HINTS.items():
        scores[lang] += sum(low.count(ch) for ch in chars) // 2
    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    if scores[best] == 0:
        return "und", 0.0
    return best, round(scores[best] / total, 2)
