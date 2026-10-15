"""Weekly-pattern expander (P19-C2): pure functions, no DB, no HTTP.

A coordinator creating a programme from scratch describes a section's week as a pattern instead of writing
planning-list rows:

```
{"theory": 3, "practice": 2, "lab": 0,          # periods per week (default: the course's T/U/L)
 "block_size": [2, 1],                           # how the theory hours split into consecutive blocks
 "practice_blocks": [2], "lab_blocks": [...],    # optional splits of U and L (default: one block each)
 "days": "TUE|THU",                              # candidate days of every block (one day = fixed)
 "start": "11.00" | 4 | ["11.00", "13:30", ...], # start time / period of every block, or one per block
 "slots": [{"day": "Salı", "start": "11:00"}],   # instead of days + start: one fixed slot per block
 "weeks": "1-14" | [1, 2, 3] | "Tüm haftalar" | "İlk 7 hafta",
 "room_needs": {"tags": ["PC"], "building": "A", "preferred_room": "A 105", "capacity": 60},
 "room_needs_by_kind": {"lab": {...}}}           # per kind (theory / practice / lab), merged over room_needs
```

:func:`build_spec` validates such a mapping into a :class:`PatternSpec` and :func:`expand` turns it into one
:class:`MeetingSpec` per block, in the shape the planning-list importer writes (``app/importers/planning_list``:
``day`` set only for a single day, ``days`` = the candidate days, ``flexible_day`` when there are several,
start/end periods on the 18-period grid with the grid's clock times, ``weeks`` as a sorted list), so the solver
bridge treats a hand-made meeting exactly like an imported one: the solver chooses the room and, among
``days``, the day; the time is the department's.

Blocks follow the design (docs/design/v2/phase19-program-wizard.md §4.6): theory, practice and lab are separate
meetings with their own room needs; a split whose total differs from the hours is an error ("3 saatlik ders için
yalnızca 2 saat yerleştirildi"). ``block_size`` is either the explicit theory split (``[2, 1]``) or the largest
block (``2``: every kind is split greedily, 3 -> 2 + 1).

Turkish text is normalised like the importers do: NBSP and newlines collapse, day names match with or without
Turkish letters (``SALI``, ``PERSEMBE``, ``Çarşamba``), dotted times (``09.20``) parse, and off-grid start times are
refused rather than snapped (the importer snaps with a warning because a file cannot be asked; the API can).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from app.importers import normalize as n

__all__ = [
    "KINDS",
    "PERIOD_STARTS",
    "MeetingSpec",
    "PatternError",
    "PatternSpec",
    "RoomNeeds",
    "blocks_for",
    "build_spec",
    "expand",
    "fold",
    "parse_days",
    "parse_room_needs",
    "parse_start",
    "parse_weeks_spec",
    "split_hours",
]


class PatternError(ValueError):
    """An invalid pattern (422 at the API, with this message)."""


#: block kinds in output order: (key in the request, short code stored on the meeting, Turkish label)
KINDS: tuple[tuple[str, str, str], ...] = (
    ("theory", "T", "Teorik"),
    ("practice", "U", "Uygulama"),
    ("lab", "L", "Lab"),
)
#: clock starts of the 18 periods ("08:30", "09:20", ...): the only start times a pattern accepts
PERIOD_STARTS: tuple[str, ...] = tuple(f"{p.start:%H:%M}" for p in n.PERIODS)
_START_BY_MINUTE = {p.start.hour * 60 + p.start.minute: p.index for p in n.PERIODS}

_ALLOWED_KEYS = frozenset(
    {
        "theory",
        "practice",
        "lab",
        "block_size",
        "practice_blocks",
        "lab_blocks",
        "days",
        "start",
        "slots",
        "weeks",
        "room_needs",
        "room_needs_by_kind",
    }
)

# --------------------------------------------------------------------------- text


_FOLD = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})


def fold(value: Any) -> str:
    """Matching form: NBSP/whitespace collapsed, Turkish casefold (``İ`` -> ``i``, ``I`` -> ``ı``), then the
    Turkish letters folded to ASCII so ``SALI``, ``Salı`` and ``sali`` are one word. Never for display."""
    text = n.clean_text(value) or ""
    return n.tr_casefold(text).translate(_FOLD)


#: day words in :func:`fold` form -> ISO weekday (1 = Monday): Turkish names and abbreviations, English
_DAY_WORDS: dict[str, int] = {
    **{fold(k): v for k, v in n.DAY_NAMES.items()},
    **{"pzt": 1, "pts": 1, "sal": 2, "car": 3, "crs": 3, "per": 4, "prs": 4, "cum": 5, "cmt": 6, "paz": 7},
    **{"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7},
    **{"monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6, "sunday": 7},
}
_DAY_SPLIT = re.compile(r"\s*(?:[|/,;+&]|\s-\s|\bveya\b|\bve\b|\bya da\b|\bor\b|\band\b)\s*|\s+")


def _one_day(value: Any) -> int:
    if isinstance(value, bool):
        raise PatternError(f"unknown day {value!r}")
    if isinstance(value, int):
        if 1 <= value <= 7:
            return value
        raise PatternError(f"day {value} is not 1 (Monday) .. 7 (Sunday)")
    word = fold(value)
    if word.isdigit():
        return _one_day(int(word))
    day = _DAY_WORDS.get(word)
    if day is None:
        raise PatternError(f"unknown day {n.clean_text(value)!r} (Pazartesi..Pazar, MON..SUN or 1..7)")
    return day


def parse_days(value: Any) -> tuple[int, ...]:
    """``"TUE|THU"``, ``"Salı / Perşembe"``, ``"SALI,PERSEMBE"``, ``[2, 4]``, ``6`` -> sorted unique weekdays."""
    if isinstance(value, Sequence) and not isinstance(value, str):
        tokens: list[Any] = list(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        tokens = [value]
    else:
        text = fold(value)
        tokens = [t for t in _DAY_SPLIT.split(text) if t]
    days = sorted({_one_day(t) for t in tokens})
    if not days:
        raise PatternError("no day given (Pazartesi..Pazar, MON..SUN or 1..7)")
    return tuple(days)


def parse_start(value: Any) -> int:
    """A start period (1..18) from ``4``, ``"P4"``, ``"11:00"``, ``"11.00"`` or a ``time``; off-grid times are
    refused with the grid's start times in the message."""
    if isinstance(value, bool) or value is None:
        raise PatternError(f"start {value!r} is not a time or period")
    if isinstance(value, int):
        if 1 <= value <= n.PERIODS_PER_DAY:
            return value
        raise PatternError(f"start period {value} is not 1..{n.PERIODS_PER_DAY}")
    if isinstance(value, time):
        t: time | None = value
    else:
        text = n.clean_text(value) or ""
        m = re.fullmatch(r"[pP]\s*(\d{1,2})", text)
        if m:
            return parse_start(int(m.group(1)))
        if text.isdigit():
            return parse_start(int(text))
        t = n.parse_time(text) if re.search(r"\d\s*[.:,hH]\s*\d{2}", text) else None
    if t is None:
        raise PatternError(f"start {value!r} is not a time (e.g. 09.20) or period (e.g. P2)")
    period = _START_BY_MINUTE.get(t.hour * 60 + t.minute)
    if period is None:
        raise PatternError(f"start {t:%H:%M} is not on the period grid; use one of {', '.join(PERIOD_STARTS)}")
    return period


def parse_weeks_spec(value: Any, max_week: int) -> tuple[int, ...]:
    """Weeks of the term: ``None`` = all, a list of week numbers, or the planning-list text forms (``"1-14"``,
    ``"1-7, 9-14"``, ``"Tüm haftalar"``, ``"İlk 7 hafta"``, ``"son 7 hafta"``). Anything ambiguous, empty or
    outside ``1..max_week`` is refused."""
    if value is None:
        return tuple(range(1, max_week + 1))
    if isinstance(value, Sequence) and not isinstance(value, str):
        weeks: list[int] = []
        for w in value:
            if isinstance(w, bool) or not isinstance(w, int):
                raise PatternError(f"week {w!r} is not a number")
            weeks.append(w)
    else:
        text = n.clean_text(value)
        if text is None:
            return tuple(range(1, max_week + 1))
        low = fold(text)
        nums = [int(x) for x in re.findall(r"\d+", low)]
        if any(x > max_week for x in nums):
            raise PatternError(f"weeks {text!r}: the term has {max_week} weeks")
        parsed = n.parse_weeks(text, max_week=max_week)
        if parsed.warnings or parsed.needs_room is False or not parsed.weeks:
            raise PatternError(f"weeks {text!r} is not a week list (e.g. 1-14, 1-7, 9-14, Tüm haftalar)")
        weeks = list(parsed.weeks)
    bad = [w for w in weeks if not 1 <= w <= max_week]
    if bad or not weeks:
        raise PatternError(f"weeks must be within 1..{max_week}" + (f" (got {bad})" if bad else ""))
    return tuple(sorted(set(weeks)))


# --------------------------------------------------------------------------- hours -> blocks


def _hours(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= n.PERIODS_PER_DAY * 7:
        raise PatternError(f"{what} must be a whole number of periods per week (got {value!r})")
    return value


def split_hours(hours: int, blocks: Any) -> tuple[int, ...]:
    """Block lengths of ``hours`` periods: ``None`` = one block, an int = the largest block (greedy split), a
    list = the explicit split, which must add up to ``hours``."""
    hours = _hours(hours, "hours")
    if blocks is None:
        return (hours,) if hours else ()
    if isinstance(blocks, int) and not isinstance(blocks, bool):
        if blocks < 1:
            raise PatternError(f"block size must be at least 1 (got {blocks})")
        if not hours:
            return ()
        out = [blocks] * (hours // blocks)
        if hours % blocks:
            out.append(hours % blocks)
        return tuple(out)
    if isinstance(blocks, Sequence) and not isinstance(blocks, str):
        lengths: list[int] = []
        for b in blocks:
            if isinstance(b, bool) or not isinstance(b, int) or b < 1:
                raise PatternError(f"block lengths must be whole numbers >= 1 (got {list(blocks)!r})")
            lengths.append(b)
        if sum(lengths) != hours:
            raise PatternError(f"blocks {lengths} add up to {sum(lengths)} period(s) but the course has {hours}")
        return tuple(lengths)
    raise PatternError(f"block size must be a number or a list of numbers (got {blocks!r})")


def _kind_blocks(raw: Mapping[str, Any], hours: tuple[int, int, int]) -> list[tuple[str, int]]:
    t, u, l = hours
    size = raw.get("block_size")
    greedy = size if isinstance(size, int) and not isinstance(size, bool) else None
    out: list[tuple[str, int]] = []
    out += [("T", b) for b in split_hours(t, size)]
    out += [("U", b) for b in split_hours(u, raw.get("practice_blocks", greedy))]
    out += [("L", b) for b in split_hours(l, raw.get("lab_blocks", greedy))]
    return out


def _course_hours(
    raw: Mapping[str, Any], course_hours: tuple[int | None, int | None, int | None]
) -> tuple[int, int, int]:
    vals = []
    for (key, _code, _label), default in zip(KINDS, course_hours, strict=True):
        v = raw.get(key)
        vals.append(_hours(v if v is not None else (default or 0), key))
    return vals[0], vals[1], vals[2]


def blocks_for(raw: Mapping[str, Any], hours: tuple[int, int, int]) -> list[tuple[str, int]] | None:
    """The (kind, length) blocks ``raw`` asks for, or ``None`` when its hours/splits are invalid (test helper)."""
    try:
        return _kind_blocks(raw, _course_hours(raw, hours))
    except PatternError:
        return None


# --------------------------------------------------------------------------- room needs


ROOM_TAGS = ("TIP", "PC", "LAB", "AMPHI")
_TAG_WORDS: dict[str, str] = {
    "tip": "TIP",
    "pc": "PC",
    "bilgisayar": "PC",
    "lab": "LAB",
    "laboratuvar": "LAB",
    "laboratuar": "LAB",
    "amfi": "AMPHI",
    "amphi": "AMPHI",
    "amfi tiyatro": "AMPHI",
}


@dataclass(frozen=True)
class RoomNeeds:
    tags: tuple[str, ...] = ()
    building: str | None = None
    preferred_room: str | None = None  # canonical room code (``A105``)
    room_text: str | None = None  # display form (``A 105``), stored as ``requested_room_text``
    capacity: int | None = None

    def merged(self, other: RoomNeeds) -> RoomNeeds:
        """``other`` over ``self``: tags are united, single values replaced when ``other`` sets them."""
        return RoomNeeds(
            tags=tuple(dict.fromkeys([*self.tags, *other.tags])),
            building=other.building or self.building,
            preferred_room=other.preferred_room or self.preferred_room,
            room_text=other.room_text or self.room_text,
            capacity=other.capacity if other.capacity is not None else self.capacity,
        )


def _tag(value: Any) -> str:
    text = n.clean_text(value)
    if not text:
        raise PatternError("empty room tag")
    if n.is_pc_lab_text(text):
        return "PC"
    word = fold(text).strip(" .")
    if word.upper() in ROOM_TAGS:
        return word.upper()
    tag = _TAG_WORDS.get(word)
    if tag is None:
        raise PatternError(f"unknown room tag {text!r} (one of {', '.join(ROOM_TAGS)})")
    return tag


def parse_room_needs(raw: Mapping[str, Any] | None, buildings: Sequence[str] = ("A", "B", "C", "D")) -> RoomNeeds:
    if not raw:
        return RoomNeeds()
    unknown = sorted(set(raw) - {"tags", "building", "preferred_room", "capacity"})
    if unknown:
        raise PatternError(f"unknown room_needs keys {unknown}")
    tags_raw = raw.get("tags") or []
    if isinstance(tags_raw, str):
        tags_raw = [t for t in re.split(r"[,;/|+]", tags_raw) if t.strip()]
    tags = tuple(dict.fromkeys(_tag(t) for t in tags_raw))
    building = None
    if raw.get("building") not in (None, ""):
        word = fold(raw["building"])
        m = re.fullmatch(r"([a-z])(?:\s*blok\w*)?", word)
        letter = m.group(1).upper() if m else None
        if letter is None or letter not in {b.upper() for b in buildings}:
            raise PatternError(f"unknown building {n.clean_text(raw['building'])!r} (one of {', '.join(buildings)})")
        building = letter
    room = text = None
    if raw.get("preferred_room") not in (None, ""):
        codes = n.parse_room_codes(raw["preferred_room"])
        if len(codes) != 1:
            raise PatternError(f"preferred_room {n.clean_text(raw['preferred_room'])!r} names no single room")
        room, text = codes[0], n.display_room_code(codes[0])
    cap = raw.get("capacity")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= 2000):
        raise PatternError(f"capacity must be 1..2000 (got {cap!r})")
    return RoomNeeds(tags=tags, building=building, preferred_room=room, room_text=text, capacity=cap)


# --------------------------------------------------------------------------- spec and expansion


@dataclass(frozen=True)
class Block:
    kind: str  # T | U | L
    length: int
    days: tuple[int, ...]
    start: int
    needs: RoomNeeds

    @property
    def end(self) -> int:
        return self.start + self.length - 1


@dataclass(frozen=True)
class PatternSpec:
    blocks: tuple[Block, ...]
    weeks: tuple[int, ...]
    hours: tuple[int, int, int]


@dataclass(frozen=True)
class MeetingSpec:
    """One meeting request to create, field for field what the planning-list importer writes."""

    kind: str
    block_no: int  # 1-based within the section's pattern
    day: int | None
    days: tuple[int, ...]
    start_period: int
    end_period: int
    start_time: time
    end_time: time
    weeks: tuple[int, ...]
    flexible_day: bool
    needs_room: bool
    requested_tags: tuple[str, ...] = ()
    requested_building: str | None = None
    requested_room_code: str | None = None
    requested_room_text: str | None = None
    requested_capacity: int | None = None
    notes: str = ""
    warnings: tuple[str, ...] = field(default=())


def _starts(raw: Mapping[str, Any], count: int) -> list[int]:
    value = raw.get("start")
    if value is None:
        raise PatternError(
            "start is required (a time such as 09.20 or a period such as P2, or one per block, or slots): "
            "the solver chooses the room and the day among `days`, not the time"
        )
    if isinstance(value, Sequence) and not isinstance(value, str):
        if len(value) != count:
            raise PatternError(f"start lists {len(value)} time(s) but the pattern has {count} block(s)")
        return [parse_start(v) for v in value]
    return [parse_start(value)] * count


def _check_fit(blocks: Sequence[Block]) -> None:
    for i, b in enumerate(blocks, 1):
        if b.end > n.PERIODS_PER_DAY:
            last = n.PERIODS[-1]
            raise PatternError(
                f"block {i} ({b.length} period(s) from P{b.start}) runs past P18 ({last.start:%H:%M}-{last.end:%H:%M})"
            )
    # blocks sharing one fixed day must not overlap; blocks with the same candidate days need as many days as
    # blocks overlapping in time (interval graph: max point overlap = days needed)
    for i, a in enumerate(blocks):
        for b in blocks[i + 1 :]:
            if len(a.days) == 1 and a.days == b.days and not (a.end < b.start or b.end < a.start):
                raise PatternError(
                    f"blocks overlap: {n.DAY_LABELS_TR[a.days[0]]} P{a.start}-P{a.end} and P{b.start}-P{b.end}"
                )
    by_days: dict[tuple[int, ...], list[Block]] = {}
    for b in blocks:
        by_days.setdefault(b.days, []).append(b)
    for days, group in by_days.items():
        if len(days) < 2:
            continue
        peak = max(sum(1 for b in group if b.start <= p <= b.end) for p in range(1, n.PERIODS_PER_DAY + 1))
        if peak > len(days):
            raise PatternError(
                f"{peak} blocks share a time but only {len(days)} days are allowed: give more days or other starts"
            )


def build_spec(
    raw: Mapping[str, Any],
    *,
    course_hours: tuple[int | None, int | None, int | None],
    max_week: int,
    buildings: Sequence[str] = ("A", "B", "C", "D"),
) -> PatternSpec:
    """Validate a pattern mapping (see the module docstring) against the course's T/U/L and the term length."""
    unknown = sorted(set(raw) - _ALLOWED_KEYS)
    if unknown:
        raise PatternError(f"unknown pattern keys {unknown}")
    hours = _course_hours(raw, course_hours)
    if not sum(hours):
        raise PatternError("the pattern has no weekly hours: set theory / practice / lab (the course lists 0+0+0)")
    kinds = _kind_blocks(raw, hours)
    base = parse_room_needs(raw.get("room_needs"), buildings)
    by_kind_raw = raw.get("room_needs_by_kind") or {}
    if not isinstance(by_kind_raw, Mapping):
        raise PatternError("room_needs_by_kind must be an object keyed by theory / practice / lab")
    kind_codes = {key: code for key, code, _ in KINDS}
    bad = sorted(set(by_kind_raw) - set(kind_codes))
    if bad:
        raise PatternError(f"unknown room_needs_by_kind keys {bad} (theory, practice, lab)")
    needs = {kind_codes[k]: base.merged(parse_room_needs(v, buildings)) for k, v in by_kind_raw.items()}
    slots = raw.get("slots")
    blocks: list[Block] = []
    if slots is not None:
        if raw.get("days") is not None or raw.get("start") is not None:
            raise PatternError("give either slots or days + start, not both")
        if not isinstance(slots, Sequence) or isinstance(slots, str) or len(slots) != len(kinds):
            got = len(slots) if isinstance(slots, Sequence) and not isinstance(slots, str) else 0
            raise PatternError(f"slots lists {got} slot(s) but the pattern has {len(kinds)} block(s)")
        for (kind, length), slot in zip(kinds, slots, strict=True):
            if (
                not isinstance(slot, Mapping)
                or set(slot) - {"day", "start"}
                or "day" not in slot
                or "start" not in slot
            ):
                raise PatternError("every slot is {day, start}")
            blocks.append(
                Block(kind, length, (_one_day(slot["day"]),), parse_start(slot["start"]), needs.get(kind, base))
            )
    else:
        if raw.get("days") is None:
            raise PatternError("days is required (e.g. TUE|THU, Salı / Perşembe) unless slots are given")
        days = parse_days(raw["days"])
        starts = _starts(raw, len(kinds))
        blocks = [
            Block(kind, length, days, start, needs.get(kind, base))
            for (kind, length), start in zip(kinds, starts, strict=True)
        ]
    _check_fit(blocks)
    return PatternSpec(blocks=tuple(blocks), weeks=parse_weeks_spec(raw.get("weeks"), max_week), hours=hours)


def expand(spec: PatternSpec, *, enrolment: int | None, needs_room: bool) -> list[MeetingSpec]:
    """One meeting per block. ``needs_room`` comes from the section's mode (online / UZEM / hospital: no room);
    the requested capacity is the block's ``room_needs.capacity`` or the enrolment, as the importer does."""
    out: list[MeetingSpec] = []
    labels = {code: label for _key, code, label in KINDS}
    counts = {code: sum(1 for b in spec.blocks if b.kind == code) for _k, code, _l in KINDS}
    seen: dict[str, int] = {}
    for i, b in enumerate(spec.blocks, 1):
        seen[b.kind] = seen.get(b.kind, 0) + 1
        part = f" {seen[b.kind]}/{counts[b.kind]}" if counts[b.kind] > 1 else ""
        out.append(
            MeetingSpec(
                kind=b.kind,
                block_no=i,
                day=b.days[0] if len(b.days) == 1 else None,
                days=b.days,
                start_period=b.start,
                end_period=b.end,
                start_time=n.PERIODS[b.start - 1].start,
                end_time=n.PERIODS[b.end - 1].end,
                weeks=spec.weeks,
                flexible_day=len(b.days) > 1,
                needs_room=needs_room,
                requested_tags=b.needs.tags,
                requested_building=b.needs.building,
                requested_room_code=b.needs.preferred_room,
                requested_room_text=b.needs.room_text,
                requested_capacity=b.needs.capacity if b.needs.capacity is not None else enrolment,
                notes=f"{labels[b.kind]}{part}: {b.length} saat / period(s)",
            )
        )
    return out
