"""Pure normalisation functions for Turkish planning spreadsheets (see docs/DATA_ANALYSIS.md).

Everything here is side-effect free and DB-agnostic so it can be unit-tested on raw cell values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Text basics
# ---------------------------------------------------------------------------

_WS_RX = re.compile(r"\s+")
_EMPTY_TOKENS = {"", "-", "--", "---", "–", "—", "nan", "none", "null"}


def clean_text(value: Any) -> str | None:
    """Collapse whitespace (incl. NBSP/newlines), strip; return None for empty or dash-only cells."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).replace("\xa0", " ").replace("​", "")
    text = _WS_RX.sub(" ", text).strip()
    if text.lower() in _EMPTY_TOKENS:
        return None
    return text


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def tr_casefold(s: str) -> str:
    return _WS_RX.sub(" ", tr_lower(s.replace("\xa0", " "))).strip()


def _tr_title(s: str) -> str:
    return " ".join(w[:1].upper() + w[1:] if w else w for w in s.split(" "))


# ---------------------------------------------------------------------------
# Course codes
# ---------------------------------------------------------------------------

_TR_LETTERS = "A-ZÇĞİÖŞÜ"
_COURSE_RX = re.compile(
    rf"(?<![{_TR_LETTERS}])([{_TR_LETTERS}]{{2,5}})\s?(\d{{2,4}})(?!\d)([A-Z](?![{_TR_LETTERS}a-z]))?"
)
_BARE_NUMBER_RX = re.compile(r"(?<![A-Za-z0-9.])(\d{2,4})(?![0-9.])")
_COURSE_FULL_RX = re.compile(rf"^([{_TR_LETTERS}]{{2,5}})(\d{{2,4}})([A-Z]?)$")


def extract_course_codes(value: Any) -> list[str]:
    """All canonical course codes in a cell; bare numbers after a code inherit its prefix (`ING 101 /105`)."""
    text = clean_text(value)
    if not text:
        return []
    up = tr_upper(text)
    codes: list[str] = []
    pos = 0
    last_prefix: str | None = None
    while pos < len(up):
        m = _COURSE_RX.search(up, pos)
        if not m:
            break
        # bare numbers between the previous code and this one inherit the previous prefix
        if last_prefix:
            for b in _BARE_NUMBER_RX.finditer(up, pos, m.start()):
                codes.append(f"{last_prefix}{b.group(1)}")
        last_prefix = m.group(1)
        codes.append(f"{m.group(1)}{m.group(2)}{m.group(3) or ''}")
        pos = m.end()
    if last_prefix:
        for b in _BARE_NUMBER_RX.finditer(up, pos):
            codes.append(f"{last_prefix}{b.group(1)}")
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def canon_course_code(value: Any) -> str | None:
    codes = extract_course_codes(value)
    return codes[0] if codes else None


_LOOSE_CODE_RX = re.compile(rf"([{_TR_LETTERS}]{{2,5}})\s?(\d[\dO ]{{1,4}}\d|[\dO]{{2,4}})(?![{_TR_LETTERS}])")
_PREFIX_ONLY_RX = re.compile(rf"^([{_TR_LETTERS}]{{2,5}})(?:\s*X{{2,4}})?$")


def canon_course_code_loose(value: Any, name: Any = None) -> tuple[str | None, str | None]:
    """Strict parse first; then repair typos (`BES 3O6`, `ING1 11`, `GT' 251`) or synthesise a placeholder
    for bare department codes (`ACU`, `MBG XXX`) from the course name. Returns (code, warning)."""
    strict = canon_course_code(value)
    if strict:
        return strict, None
    text = clean_text(value)
    if not text:
        return None, None
    up = tr_upper(text).replace("'", "").replace("’", "")
    m = _LOOSE_CODE_RX.search(up)
    if m and any(ch.isdigit() for ch in m.group(2)):
        digits = m.group(2).replace("O", "0").replace(" ", "")
        code = f"{m.group(1)}{digits}"
        return code, f"course code {text!r} repaired to {code}"
    m = _PREFIX_ONLY_RX.match(up.strip())
    if m:
        cname = clean_text(name)
        if cname:
            digest = __import__("hashlib").sha1(tr_casefold(cname).encode("utf-8")).hexdigest()[:4].upper()
            code = f"{m.group(1)}-{digest}"
            return code, f"course code {text!r} has no number; placeholder {code} derived from name {cname!r}"
        return None, f"course code {text!r} has no number and no name"
    return None, f"unrecognised course code {text!r}"


def display_course_code(code: str) -> str:
    m = _COURSE_FULL_RX.match(code)
    if not m:
        return code.replace("-", " ") if "-" in code else code
    return f"{m.group(1)} {m.group(2)}{m.group(3)}"


# ---------------------------------------------------------------------------
# Days
# ---------------------------------------------------------------------------

DAY_NAMES: dict[str, int] = {
    "pazartesi": 1,
    "salı": 2,
    "çarşamba": 3,
    "perşembe": 4,
    "cuma": 5,
    "cumartesi": 6,
    "pazar": 7,
}
DAY_LABELS_TR: dict[int, str] = {v: _tr_title(k) for k, v in DAY_NAMES.items()}
_DAY_RX = re.compile(r"\b(pazartesi|cumartesi|salı|çarşamba|perşembe|cuma|pazar)\b")

_NO_ROOM_WORDS = (
    "asenkron",
    "uzem",
    "online",
    "çevrimiçi",
    "hastane",
    "yaz dönem",
    "tez dersi",
    "yeterliliğe hazırlık",
    "uzaktan",
)
_FLEX_WORDS = (
    "belirli günü yok",
    "danışman",
    "hergün",
    "her gün",
    "veya",
    "belirlenecek",
    "belirleniyor",
    "belirtilmemiş",
    "verilmemiş",
)


@dataclass
class DayParse:
    days: list[int] = field(default_factory=list)
    flexible: bool = False
    needs_room: bool | None = True
    note: str | None = None
    warnings: list[str] = field(default_factory=list)
    raw: str | None = None


def parse_day(value: Any) -> DayParse:
    if isinstance(value, time | datetime):
        return DayParse(warnings=[f"day cell contains a time value: {value!r}"], needs_room=None, raw=str(value))
    text = clean_text(value)
    if not text:
        return DayParse(needs_room=None)
    low = tr_casefold(text)
    days = [DAY_NAMES[m.group(1)] for m in _DAY_RX.finditer(low)]
    days = list(dict.fromkeys(days))
    note_m = re.search(r"\(([^)]*)\)", text)
    note = note_m.group(1).strip() if note_m else None
    needs_room: bool | None = True
    flexible = False
    if any(w in low for w in _NO_ROOM_WORDS):
        needs_room = False
    if any(w in low for w in _FLEX_WORDS):
        flexible = True
    if "hergün" in low or "her gün" in low:
        days = [1, 2, 3, 4, 5]
    warnings: list[str] = []
    if not days and needs_room and not flexible:
        warnings.append(f"unrecognised day: {text!r}")
    return DayParse(days=days, flexible=flexible, needs_room=needs_room, note=note, warnings=warnings, raw=text)


# ---------------------------------------------------------------------------
# Times & periods
# ---------------------------------------------------------------------------

_TIME_RX = re.compile(r"(\d{1,2})\s*[.:,hH]\s*(\d{2})")
_HOUR_ONLY_RX = re.compile(r"^(\d{1,2})$")


def parse_time(value: Any) -> time | None:
    """time/datetime/float fraction-of-day/`09.00`/`09:00`/`-` -> time or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        t = value.time()
        if t != time(0, 0):
            return t.replace(second=0, microsecond=0)
        if value.year == 1900 and value.month == 1 and 1 <= value.day <= 24:
            return time(value.day, 0)  # Excel serial N rendered as a date: user typed the hour
        return None
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) // 60
        return time(total // 60 % 24, total % 60)
    if isinstance(value, int | float) and not isinstance(value, bool):
        if 0 < value < 1:
            minutes = round(value * 24 * 60)
            return time(minutes // 60 % 24, minutes % 60)
        if 1 <= value <= 24 and float(value).is_integer():
            return time(int(value) % 24, 0)
        return None
    text = clean_text(value)
    if not text:
        return None
    m = _TIME_RX.search(text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 24 and 0 <= mi < 60:
            return time(h % 24, mi)
        return None
    m = _HOUR_ONLY_RX.match(text)
    if m and 0 < int(m.group(1)) <= 24:
        return time(int(m.group(1)) % 24, 0)
    return None


@dataclass(frozen=True)
class Period:
    index: int
    start: time
    end: time

    @property
    def label(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M}"


PERIODS: tuple[Period, ...] = tuple(
    Period(i + 1, time(sh, sm), time(eh, em))
    for i, (sh, sm, eh, em) in enumerate(
        [
            (8, 30, 9, 10),
            (9, 20, 10, 0),
            (10, 10, 10, 50),
            (11, 0, 11, 40),
            (11, 50, 12, 30),
            (12, 40, 13, 20),
            (13, 30, 14, 10),
            (14, 20, 15, 0),
            (15, 10, 15, 50),
            (16, 0, 16, 40),
            (16, 50, 17, 30),
            (17, 30, 18, 0),
            (18, 0, 18, 40),
            (18, 50, 19, 30),
            (19, 40, 20, 20),
            (20, 30, 21, 10),
            (21, 20, 22, 0),
            (22, 10, 22, 50),
        ]
    )
)
PERIODS_PER_DAY = len(PERIODS)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


@dataclass
class PeriodMatch:
    period: int | None
    warning: str | None = None


def time_to_period(t: time, kind: str = "start") -> PeriodMatch:
    """Map a clock time to the 18-period grid.

    start: the period containing ``t`` (or the next one when ``t`` falls in a break); exact only when
    ``t`` equals a period start. end: the last period that starts before ``t``.
    """
    m = _minutes(t)
    if kind == "end":
        candidates = [p for p in PERIODS if _minutes(p.start) < m]
        if not candidates:
            return PeriodMatch(None, f"end time {t:%H:%M} is before the first period")
        p = candidates[-1]
        exact = any(_minutes(q.end) == m or _minutes(q.start) == m for q in PERIODS)
        return PeriodMatch(p.index, None if exact else f"end time {t:%H:%M} snapped to P{p.index} ({p.end:%H:%M})")
    for p in PERIODS:
        if _minutes(p.start) == m:
            return PeriodMatch(p.index)
    if m < _minutes(PERIODS[0].start):
        return PeriodMatch(1, f"start time {t:%H:%M} is before the grid; snapped to P1")
    for p in PERIODS:
        if _minutes(p.start) < m <= _minutes(p.end):
            return PeriodMatch(
                p.index, f"start time {t:%H:%M} not on the grid; snapped to P{p.index} ({p.start:%H:%M})"
            )
    for p in PERIODS:
        if _minutes(p.start) > m:
            return PeriodMatch(p.index, f"start time {t:%H:%M} falls in a break; snapped to P{p.index}")
    return PeriodMatch(None, f"start time {t:%H:%M} is after the last period")


@dataclass
class PeriodRange:
    start_period: int | None
    end_period: int | None
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> int:
        if self.start_period is None or self.end_period is None:
            return 0
        return self.end_period - self.start_period + 1


def time_range_to_periods(start: time | None, end: time | None) -> PeriodRange:
    if start is None or end is None:
        return PeriodRange(None, None, ["missing start or end time"])
    if _minutes(end) <= _minutes(start):
        return PeriodRange(None, None, [f"end time {end:%H:%M} is not after start {start:%H:%M}"])
    s = time_to_period(start, "start")
    e = time_to_period(end, "end")
    warnings = [w for w in (s.warning, e.warning) if w]
    if s.period is None or e.period is None:
        return PeriodRange(None, None, warnings or ["time range outside grid"])
    if e.period < s.period:
        e = PeriodMatch(s.period, f"end time {end:%H:%M} inside start period; using a single period")
        warnings.append(e.warning or "")
    return PeriodRange(s.period, e.period, warnings)


_SLOT_RX = re.compile(r"(\d{1,2})[.:](\d{2})\s*-\s*(\d{1,2})[.:\-](\d{2})")


def parse_time_slot(value: Any) -> tuple[time, time] | None:
    text = clean_text(value)
    if not text:
        return None
    m = _SLOT_RX.search(text)
    if not m:
        return None
    return time(int(m.group(1)), int(m.group(2))), time(int(m.group(3)), int(m.group(4)))


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

_ROOM_RX = re.compile(r"(?<![A-Za-zÇĞİÖŞÜçğıöşü0-9])([A-Da-d])\s?([zZ]?\d{2,3})(?![0-9])")
_ROOM_BLOCK_RX = re.compile(r"([A-Da-d])\s*[Bb][Ll][Oo][Kk]\w*\s*((?:\d{3}\s*[-,/]?\s*)+)")
_BUILDING_RX = re.compile(r"\b([A-Da-d])\s*[Bb][Ll][Oo][Kk]")


def _canon_room(letter: str, num: str) -> str:
    return f"{letter.upper()}{num.upper()}"


def parse_room_codes(value: Any) -> list[str]:
    """`A 101 / A 106`, `A107/ B 207`, `C z01`, `B 207\\nPC`, `a 106`, `C blok 601-602` -> canonical codes."""
    text = clean_text(value)
    if not text:
        return []
    codes = [_canon_room(m.group(1), m.group(2)) for m in _ROOM_RX.finditer(text)]
    for m in _ROOM_BLOCK_RX.finditer(text):
        for num in re.findall(r"\d{3}", m.group(2)):
            codes.append(_canon_room(m.group(1), num))
    return list(dict.fromkeys(codes))


def display_room_code(code: str) -> str:
    if len(code) < 2:
        return code
    rest = code[1:]
    if rest[:1] == "Z":
        rest = "z" + rest[1:]
    return f"{code[0]} {rest}"


@dataclass
class RoomHeader:
    code: str
    display_name: str
    capacity: int | None
    tags: list[str]
    raw: str


_ROOM_HEADER_RX = re.compile(r"^\s*([A-Da-d])\s?([zZ]?\d{2,3})\s*(?:\((\d+)\))?\s*(.*)$", re.S)
_KNOWN_ROOM_TAGS = {"TIP", "PC", "LAB", "AMPHI", "AMFI"}


def parse_room_header(value: Any) -> RoomHeader | None:
    if value is None:
        return None
    raw = str(value)
    m = _ROOM_HEADER_RX.match(raw)
    if not m:
        return None
    rest = m.group(4) or ""
    rest_tokens = [tr_upper(t) for t in re.split(r"[\s,/]+", rest.strip()) if t]
    tags: list[str] = []
    for tok in rest_tokens:
        tok = tok.strip("()")
        if tok == "AMFI":
            tok = "AMPHI"
        if tok in _KNOWN_ROOM_TAGS and tok not in tags:
            tags.append(tok)
        elif tok.startswith("(") or not tok.isalpha():
            continue
        elif tok not in tags and len(rest_tokens) <= 2 and tok.isalpha():
            # unknown single tag word (e.g. "LAB") – keep it
            tags.append(tok)
    code = _canon_room(m.group(1), m.group(2))
    cap = int(m.group(3)) if m.group(3) else None
    return RoomHeader(code=code, display_name=display_room_code(code), capacity=cap, tags=tags, raw=raw)


@dataclass
class DefinitiveParse:
    room_codes: list[str]
    status: str  # ROOMS | NO_ROOM | CANCELLED | UNKNOWN | EMPTY
    raw: str | None = None


_NO_ROOM_PHRASES = (
    "online",
    "derslik talebi yok",
    "talebi yok",
    "hastane",
    "uzem",
    "laboratuvar",
    "laboratuar",
    "lab",
    "kampüs dışı",
    "asenkron",
    "çevrimiçi",
    "spor salonu",
    "toplantı",
)
_CANCELLED_PHRASES = ("iptal", "kapatıl", "kapatılacak")


def parse_definitive_rooms(value: Any) -> DefinitiveParse:
    text = clean_text(value)
    if not text or text.lower() in {"x"}:
        return DefinitiveParse([], "EMPTY", text)
    codes = parse_room_codes(text)
    low = tr_casefold(text)
    if any(p in low for p in _CANCELLED_PHRASES):
        return DefinitiveParse(codes, "CANCELLED", text)
    if codes:
        return DefinitiveParse(codes, "ROOMS", text)
    if any(p in low for p in _NO_ROOM_PHRASES):
        return DefinitiveParse([], "NO_ROOM", text)
    return DefinitiveParse([], "UNKNOWN", text)


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------


@dataclass
class WeeksParse:
    weeks: list[int]
    all_weeks: bool
    needs_room: bool | None = True
    note: str | None = None
    warnings: list[str] = field(default_factory=list)


_ALL_WEEK_WORDS = ("hepsi", "tüm", "her hafta", "dönemin tamamı", "tamamı", "boyunca", "100%")
_WEEK_NO_ROOM_WORDS = ("online", "uzem", "çevrimiçi", "hastane", "laboratuvar", "asenkron", "gerek yok", "istenmiyor")
_ILK_RX = re.compile(r"ilk\s+(\d+)\s*hafta")
_RANGE_RX = re.compile(r"(\d+)\s*\.?\s*(?:-|–|ila|ile)\s*(\d+)")
_NUM_RX = re.compile(r"\d+")
_HAFTA_SEG_RX = re.compile(r"([\d.,\s\-–]+?)\s*hafta\w*\s*([^\d]*)")


def _expand_numbers(spec: str) -> list[int]:
    weeks: list[int] = []
    spec = spec.replace("ila", "-").replace("ile", "-")
    consumed: set[int] = set()
    for m in _RANGE_RX.finditer(spec):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            weeks.extend(range(a, b + 1))
        consumed.update(range(m.start(), m.end()))
    for m in _NUM_RX.finditer(spec):
        if m.start() in consumed:
            continue
        weeks.append(int(m.group()))
    return sorted(set(weeks))


def parse_weeks(value: Any, max_week: int = 14) -> WeeksParse:
    all_weeks = list(range(1, max_week + 1))
    if value is None:
        return WeeksParse(all_weeks, True)
    if isinstance(value, bool):
        return WeeksParse(all_weeks, True, warnings=[f"boolean weeks value {value!r}; assuming all"])
    if isinstance(value, int | float):
        if isinstance(value, float) and not value.is_integer():
            return WeeksParse(all_weeks, True, warnings=[f"fractional weeks value {value!r}; assuming all"])
        n = int(value)
        if n <= 1:
            return WeeksParse(all_weeks, True, warnings=[f"weeks value {n}; assuming all"])
        if n < 10:
            return WeeksParse(
                list(range(1, n + 1)), False, warnings=[f"ambiguous weeks value {n}; assuming first {n} weeks"]
            )
        if n > max_week:
            return WeeksParse(all_weeks, True, warnings=[f"weeks value {n} exceeds term length {max_week}"])
        return WeeksParse(list(range(1, n + 1)), n == max_week)
    text = clean_text(value)
    if not text:
        return WeeksParse(all_weeks, True)
    low = tr_casefold(text)
    low = re.sub(r"\s+ve\s+", ", ", low)
    if low in {"x", "evet", "hayır", "var", "yok", "0", "1"}:
        return WeeksParse(all_weeks, True, warnings=[f"non-week value {text!r}; assuming all"], note=text)
    if re.fullmatch(r"[\d.,]+", low) and not re.fullmatch(r"[\d,]+", low) and "," not in low:
        try:
            f = float(low)
        except ValueError:
            f = None
        if f is not None and not f.is_integer():
            return WeeksParse(all_weeks, True, warnings=[f"fractional weeks value {text!r}; assuming all"])
    if any(w in low for w in _WEEK_NO_ROOM_WORDS) and not any(ch.isdigit() for ch in low):
        return WeeksParse([], False, needs_room=False, note=text)
    if any(w in low for w in _ALL_WEEK_WORDS):
        return WeeksParse(all_weeks, True, note=text if len(text) > 20 else None)
    if "vize" in low:
        return WeeksParse(list(range(1, 8)), False, warnings=["'until midterm' approximated as weeks 1-7"], note=text)
    m = _ILK_RX.search(low)
    if m:
        n = min(int(m.group(1)), max_week)
        return WeeksParse(list(range(1, n + 1)), n == max_week, note=text)
    segments = list(_HAFTA_SEG_RX.finditer(low))
    weeks: list[int] = []
    warnings: list[str] = []
    if segments:
        for seg in segments:
            spec, desc = seg.group(1), seg.group(2)
            if any(w in desc for w in _WEEK_NO_ROOM_WORDS) and "derslik" not in desc:
                continue
            nums = _expand_numbers(spec)
            ordinal = re.search(r"\d+\s*\.", spec) is not None  # "12. hafta" = week 12
            if len(nums) == 1 and not _RANGE_RX.search(spec) and "," not in spec and not ordinal:
                n = nums[0]
                if n >= 10:  # "14 hafta" = count of weeks
                    nums = list(range(1, n + 1))
            weeks.extend(nums)
        if not weeks and any(w in low for w in _WEEK_NO_ROOM_WORDS):
            return WeeksParse([], False, needs_room=False, note=text)
    else:
        weeks = _expand_numbers(low)
        if len(weeks) == 1 and not _RANGE_RX.search(low) and "," not in low:
            n = weeks[0]
            if n <= 1:
                return WeeksParse(all_weeks, True, warnings=[f"weeks value {n}; assuming all"])
            weeks = list(range(1, n + 1))
            if n < 10:
                warnings.append(f"ambiguous weeks value {n}; assuming first {n} weeks")
    if not weeks:
        return WeeksParse(all_weeks, True, warnings=[f"unparsed weeks text {text!r}; assuming all"], note=text)
    over = [w for w in weeks if w > max_week or w < 1]
    if over:
        warnings.append(f"weeks {over} exceed term length {max_week}; capped")
    weeks = sorted({w for w in weeks if 1 <= w <= max_week})
    return WeeksParse(weeks, weeks == all_weeks, note=text if len(text) > 8 else None, warnings=warnings)


# ---------------------------------------------------------------------------
# Mode / pct / class year / ints / semester / bool
# ---------------------------------------------------------------------------

ROOM_MODES = {"F2F", "HYBRID", "SIMULATION"}


@dataclass
class ModeParse:
    mode: str
    needs_room: bool
    raw: str | None = None


def parse_mode(value: Any) -> ModeParse:
    text = clean_text(value)
    if not text:
        return ModeParse("F2F", True, None)
    low = tr_casefold(text)
    has_room_word = "derslik" in low or "sınıf" in low or "yüz yüze" in low or "yüzyüze" in low
    negated = "kullanılmayacak" in low or "gerek yok" in low or "istenmiyor" in low
    if (
        "hibrit" in low
        or "hybrid" in low
        or (("online" in low or "çevrimiçi" in low) and has_room_word and not negated)
    ):
        return ModeParse("HYBRID", True, text)
    if "simülasyon" in low or "simulasyon" in low:
        return ModeParse("SIMULATION", True, text)
    if "uzem" in low:
        return ModeParse("UZEM", False, text)
    if "asenkron" in low:
        return ModeParse("ASYNC", False, text)
    if "online" in low or "çevrimiçi" in low or "zoom" in low or "senkron" in low:
        return ModeParse("ONLINE", False, text)
    if "hastane" in low:
        return ModeParse("HOSPITAL", False, text)
    if negated:
        return ModeParse("OTHER", False, text)
    if "lab" in low:
        return ModeParse("OTHER", False, text)
    if has_room_word:
        return ModeParse("F2F", True, text)
    return ModeParse("OTHER", True, text)


def parse_pct(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if 0 < value <= 1:
            return int(round(value * 100))
        if 0 <= value <= 100:
            return int(round(value))
        return None
    text = clean_text(value)
    if not text:
        return None
    low = tr_casefold(text)
    if low == "uzem":
        return 100
    if low in {"yok", "hayır"}:
        return 0
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%*", low)
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    if "%" in low or num > 1:
        return int(round(num)) if num <= 100 else None
    return int(round(num * 100))


def parse_class_year(value: Any) -> list[int]:
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, float):
        if value.is_integer():
            return [int(value)]
        return [int(ch) for ch in str(value) if ch.isdigit()]
    text = clean_text(value)
    if not text:
        return []
    nums = [int(x) for x in re.findall(r"\d+", text)]
    return list(dict.fromkeys(nums))


def parse_int_loose(value: Any) -> int | None:
    if value is None or isinstance(value, bool | time | datetime | date):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = clean_text(value)
    if not text:
        return None
    m = re.match(r"^\s*(\d+)", text)
    if not m:
        return None
    return int(m.group(1))


def parse_float_loose(value: Any) -> float | None:
    if value is None or isinstance(value, bool | time | datetime | date):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = clean_text(value)
    if not text:
        return None
    text = text.replace(",", ".")
    text = re.sub(r"\.{2,}", ".", text)
    m = re.match(r"^\s*(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def parse_semester(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    text = clean_text(value)
    if not text:
        return None
    low = tr_casefold(text)
    m = re.match(r"^(\d+)\s*\.?\s*(yarıyıl|yy)?", low)
    if m and int(m.group(1)) <= 12:
        return int(m.group(1))
    has_guz = "güz" in low
    has_bahar = "bahar" in low
    if has_guz and has_bahar:
        return None
    if has_guz:
        return 1
    if has_bahar:
        return 2
    return None


def parse_bool_loose(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    text = clean_text(value)
    if not text:
        return None
    low = tr_casefold(text)
    if low in {"evet", "x", "var", "yes", "true", "1", "tamamı derslikte", "tüm haftalar", "yüz yüze"}:
        return True
    if low in {"hayır", "hayir", "no", "false", "0", "yok"}:
        return False
    return None


def parse_section_label(value: Any) -> str | None:
    if isinstance(value, float) and not value.is_integer():
        return ",".join(ch for ch in str(value) if ch.isdigit())
    text = clean_text(value)
    if not text:
        return None
    text = text.strip("() ").strip()
    text = re.sub(r"\s*,\s*", ",", text)
    return text or None


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

_TITLE_TOKENS = {
    "prof": "Prof.",
    "dr": "Dr.",
    "doç": "Doç.",
    "doc": "Doç.",
    "öğr": "Öğr.",
    "ogr": "Öğr.",
    "gör": "Gör.",
    "gor": "Gör.",
    "üyesi": "Üyesi",
    "uyesi": "Üyesi",
    "arş": "Arş.",
    "ars": "Arş.",
    "uzm": "Uzm.",
    "uzman": "Uzman",
    "eğt": "Eğt.",
    "egt": "Eğt.",
    "eğitmen": "Eğitmen",
    "okt": "Okt.",
    "okutman": "Okutman",
    "yrd": "Yrd.",
    "dt": "Dt.",
    "ecz": "Ecz.",
    "msc": "MSc",
    "phd": "PhD",
}


@dataclass
class PersonParse:
    full_name: str
    canonical: str
    title: str | None
    raw: str


def canon_person_name(value: Any) -> PersonParse | None:
    text = clean_text(value)
    if not text:
        return None
    # split "Dr.Öğr.Üyesi" into tokens on dots as well as spaces, keeping dot information
    tokens = [t for t in re.split(r"(?<=\.)\s*|\s+", text) if t]
    title_parts: list[str] = []
    idx = 0
    while idx < len(tokens):
        key = tr_casefold(tokens[idx]).rstrip(".")
        if key in _TITLE_TOKENS:
            title_parts.append(_TITLE_TOKENS[key])
            idx += 1
        else:
            break
    rest = " ".join(tokens[idx:]).strip()
    if not rest:  # the whole string was titles – keep original
        rest = text
        title_parts = []
    canonical = tr_casefold(rest)
    title = " ".join(title_parts) if title_parts else None
    return PersonParse(full_name=rest, canonical=canonical, title=title, raw=text)


def split_person_names(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).replace("\xa0", " ")
    parts = re.split(r"\n|/|;|\s{2,}-\s{2,}", text)
    out = []
    for p in parts:
        c = clean_text(p)
        if c:
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Faculties / programs
# ---------------------------------------------------------------------------


@dataclass
class OrgParse:
    name: str
    canonical: str
    is_evening: bool = False


FACULTY_ALIASES: dict[str, str] = {
    "mdbf": "Mühendislik ve Doğa Bilimleri Fakültesi",
    "mdbf ; mf": "Mühendislik ve Doğa Bilimleri Fakültesi",
    "mf": "Mühendislik ve Doğa Bilimleri Fakültesi",
    "shmyo": "Sağlık Hizmetleri Meslek Yüksekokulu",
    "sbf": "Sağlık Bilimleri Fakültesi",
    "itbf": "İnsan ve Toplum Bilimleri Fakültesi",
    "yabancı diller": "Yabancı Diller Bölümü",
    "ortak dersler başkanlığı": "Ortak Dersler Bölüm Başkanlığı",
    "rektörlük servis": "Rektörlük Servis",
}


def _org_key(text: str) -> str:
    low = tr_casefold(text)
    low = re.sub(r"\s*;\s*", " ; ", low)
    return low.strip(" .;,-")


def canon_faculty(value: Any) -> OrgParse | None:
    text = clean_text(value)
    if not text:
        return None
    key = _org_key(text)
    alias = FACULTY_ALIASES.get(key)
    if alias:
        return OrgParse(alias, _org_key(alias))
    # "ECZACILIK FAKÜLTESİ" vs "Eczacılık Fakültesi": canonical key is casefolded, name is title-cased when ALLCAPS
    name = _tr_title(tr_lower(text)) if text.isupper() else text
    return OrgParse(name, key)


_EVENING_RX = re.compile(r"\(?\s*(i\.?ö\.?|ikinci öğretim|iö)\s*\)?", re.I)


def canon_program(value: Any) -> OrgParse | None:
    text = clean_text(value)
    if not text:
        return None
    low = tr_casefold(text)
    is_evening = bool(re.search(r"\((iö|i\.ö\.?)\)|ikinci öğretim|\biö\b", low))
    name = _tr_title(tr_lower(text)) if text.isupper() else text
    return OrgParse(name, _org_key(text), is_evening)


def split_program_names(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    if re.fullmatch(r"[A-ZÇĞİÖŞÜ]{2,5}(\s*[-+/]\s*[A-ZÇĞİÖŞÜ]{2,5})+", text):
        return [p for p in re.split(r"\s*[-+/]\s*", text) if p]
    return [text]


# ---------------------------------------------------------------------------
# Venue request (free text -> structured preference)
# ---------------------------------------------------------------------------


@dataclass
class VenueRequest:
    room_codes: list[str] = field(default_factory=list)
    building: str | None = None
    min_capacity: int | None = None
    room_count: int | None = None
    tags: list[str] = field(default_factory=list)
    invigilators: int | None = None
    same_room_as: list[str] = field(default_factory=list)
    notes: str | None = None
    confidence: str = "none"  # none | low | medium | high
    needs_room: bool | None = None
    raw: str | None = None


_VENUE_NO_ROOM = (
    "yok",
    "talebi yok",
    "online",
    "uzem",
    "hastane",
    "asenkron",
    "çevrimiçi",
    "zoom",
    "gerek yok",
    "istenmiyor",
    "ihtiyaç bulunmuyor",
    "kampüs dışı",
    "senkron",
    "kurumda",
)
_CAP_RX = re.compile(r"(\d+)(?:\s*-\s*(\d+))?\s*kişilik")
_COUNT_RX = re.compile(r"(?<!\d)(\d+)\s*(?:adet\b|(?:büyük\s*|küçük\s*)?(?:derslik|sınıf|amfi|anfi|lab|salon))")
_INVIG_RX = re.compile(r"(\d+)\s*gözetmen")
_SAME_ROOM_RX = re.compile(r"(.+?)\s*(?:dersi\s*)?ile\s*aynı\s*derslik")


def parse_venue_request(value: Any) -> VenueRequest:
    text = clean_text(value)
    if not text or text.lower() in {"x", "i"}:
        return VenueRequest(raw=text)
    low = tr_casefold(text)
    v = VenueRequest(raw=text)
    same = _SAME_ROOM_RX.search(low)
    if same:
        v.same_room_as = extract_course_codes(same.group(1))
    v.room_codes = parse_room_codes(text)
    v.room_codes = [c for c in v.room_codes if c not in {x[:4] for x in v.same_room_as}]
    bm = _BUILDING_RX.search(text)
    if bm:
        v.building = bm.group(1).upper()
    elif v.room_codes:
        v.building = v.room_codes[0][0]
    cm = _CAP_RX.search(low)
    if cm:
        v.min_capacity = int(cm.group(1))
    cnt = _COUNT_RX.search(low)
    if cnt:
        v.room_count = int(cnt.group(1))
    im = _INVIG_RX.search(low)
    if im:
        v.invigilators = int(im.group(1))
    tags: list[str] = []
    if "bilg" in low or "pc" in low.split() or "bilgisayar" in low:
        tags.append("PC")
    if ("lab" in low or "multidisiplin" in low) and "PC" not in tags:
        tags.append("LAB")
    if "amfi" in low or "anfi" in low or "büyük" in low:
        tags.append("AMPHI")
    if "toplantı" in low:
        tags.append("MEETING")
    if "tip" in low.split():
        tags.append("TIP")
    v.tags = tags
    has_room_word = any(w in low for w in ("derslik", "sınıf", "amfi", "anfi", "dersik", "derslk", "derlisk"))
    no_room = any(w in low for w in _VENUE_NO_ROOM)
    explicit_no = any(
        w in low
        for w in ("talebi yok", "gerek yok", "istenmiyor", "ihtiyaç bulunmuyor", "kullanılmayacak", "talebimiz yok")
    )
    if explicit_no and not v.room_codes:
        v.confidence = "medium"
        v.needs_room = False
    elif v.room_codes:
        v.confidence = "high"
        v.needs_room = True
    elif "PC" in tags and ("lab" in low or "bilgisayar" in low):
        v.confidence = "medium"
        v.needs_room = True
    elif no_room and not has_room_word:
        v.confidence = "medium"
        v.needs_room = False
    elif "LAB" in tags and not has_room_word:
        v.confidence = "medium"
        v.needs_room = False  # specialised lab, not a plannable classroom
    elif v.building or v.min_capacity or v.room_count or tags:
        v.confidence = "medium"
        v.needs_room = True
    elif has_room_word or low in {"evet", "var", "yüz yüze", "talep edilmektedir.", "1", "2"}:
        v.confidence = "low"
        v.needs_room = True
    else:
        v.confidence = "low"
        v.needs_room = None
    if v.confidence != "high" or len(text) > 12 or v.same_room_as:
        v.notes = text
    return v


# ---------------------------------------------------------------------------
# Dates / grid helpers
# ---------------------------------------------------------------------------

_DATE_RX = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
MONTHS_TR = {
    "ocak": 1,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "eylül": 9,
    "ekim": 10,
    "kasım": 11,
    "aralık": 12,
}


def parse_date_range(value: Any) -> tuple[date | None, date | None]:
    if isinstance(value, datetime):
        return value.date(), None
    if isinstance(value, date):
        return value, None
    text = clean_text(value)
    if not text:
        return None, None
    found = [date(int(m.group(3)), int(m.group(2)), int(m.group(1))) for m in _DATE_RX.finditer(text)]
    if not found:
        return None, None
    return found[0], (found[1] if len(found) > 1 else None)


def parse_day_header(value: Any, year: int) -> tuple[int | None, date | None]:
    text = clean_text(value)
    if not text:
        return None, None
    low = tr_casefold(text)
    m = _DAY_RX.search(low)
    day = DAY_NAMES[m.group(1)] if m else None
    dm = re.search(r"(\d{1,2})\s+([a-zçğıöşü]+)", low)
    d: date | None = None
    if dm and dm.group(2) in MONTHS_TR:
        try:
            d = date(year, MONTHS_TR[dm.group(2)], int(dm.group(1)))
        except ValueError:
            d = None
    return day, d


@dataclass
class GridCell:
    kind: str  # COURSE | BLOCK
    codes: list[str]
    label: str
    section_label: str | None = None
    raw: str = ""


_BLOCK_LABELS = {"hazırlık": "HAZIRLIK", "hazirlik": "HAZIRLIK", "uzem": "UZEM", "etkinlik": "ETKİNLİK"}
_SECTION_RX = re.compile(r"(?<![A-Z0-9])([A-Z]\d\+?(?:\s*INT\s*[A-Z]?)?|Alttan)(?![A-Za-z0-9])")


def parse_grid_cell(value: Any) -> GridCell | None:
    text = clean_text(value)
    if not text:
        return None
    codes = extract_course_codes(text)
    low = tr_casefold(text)
    if codes and not any(low.startswith(k) for k in _BLOCK_LABELS):
        rest = tr_upper(text)
        for c in codes:
            rest = rest.replace(display_course_code(c), " ").replace(c, " ")
        sm = _SECTION_RX.search(rest)
        return GridCell("COURSE", codes, text, sm.group(1) if sm else None, text)
    label = _BLOCK_LABELS.get(low, text)
    return GridCell("BLOCK", [], label, None, text)


_FILL_TAGS = {
    "FFFF00": "YELLOW",
    "FFC000": "ORANGE",
    "7030A0": "PURPLE",
    "00B0F0": "BLUE",
    "0070C0": "BLUE",
    "92D050": "GREEN",
    "00B050": "GREEN",
    "FF0000": "RED",
}


def fill_to_tag(fill: str | None) -> str | None:
    if not fill:
        return None
    if fill.startswith("theme:"):
        idx = fill.split(":", 1)[1]
        return None if idx in {"0", "1"} else f"THEME{idx}"
    if fill.startswith("indexed:"):
        return f"INDEXED{fill.split(':', 1)[1]}"
    rgb = fill[-6:].upper()
    if rgb in {"FFFFFF", "000000"}:
        return None
    return _FILL_TAGS.get(rgb, f"#{rgb}")
