"""Stable identity of imported planning-list meetings and the planner-edit bookkeeping shared by the
importer and the studio (review M4).

A meeting's identity is **section key + day(s) + occurrence index** (``PL:<term>:id:<digest>#<n>``):
the section key is ``course|programme canonical|şube``, the occurrence orders that section's rows on the
same day(s) by start time, then file row. Free-text columns that the planning office fills in later
(definitive room, requested venue) are *not* part of it, so filling the definitive rooms no longer gives
every row a new id (and detaches draft exclusions, pins and rule ``event_ids``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import time
from typing import Any

MEETING_FIELDS = (
    "day",
    "days",
    "flexible_day",
    "start_period",
    "end_period",
    "weeks",
    "requested_room_ids",
    "requested_building",
    "requested_tags",
    "definitive_room_ids",
    "needs_room",
    "status",
)
SECTION_FIELDS = ("enrolment", "mode")
#: fields that only make sense together: one planner edit (revert and import-diff unit)
COUPLED: tuple[frozenset[str], ...] = (
    frozenset({"day", "days", "flexible_day"}),
    frozenset({"start_period", "end_period"}),
    frozenset({"status", "definitive_room_ids"}),
    frozenset({"mode", "needs_room"}),
)
#: meeting columns derived from the time group (stored in the snapshot as ``_start_time`` / ``_end_time``)
TIME_SHADOW = {"start_time": "_start_time", "end_time": "_end_time"}

_LEGACY = re.compile(r"^PL:(?P<term>.+):[0-9a-f]{16}#\d+$")


def plain(v: Any) -> Any:
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, list | tuple):
        return [plain(x) for x in v]
    return v


def fingerprint(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def section_snapshot_fp(source_row: Any, source_key: str | None) -> str:
    return fingerprint(source_row, source_key)


def meeting_snapshot_fp(section_source_row: Any, source_key: str | None, source_row_index: int | None) -> str:
    return fingerprint(section_source_row, source_key, source_row_index)


def expand_coupled(fields: Iterable[str]) -> set[str]:
    out = set(fields)
    for group in COUPLED:
        if out & group:
            out |= group
    return out


def meeting_identity(term_code: str, section_key: str, days: Sequence[int], occurrence: int) -> str:
    day_part = ",".join(str(int(d)) for d in sorted(set(days))) or "-"
    digest = hashlib.sha1(f"{section_key}|D{day_part}".encode()).hexdigest()[:20]
    return f"PL:{term_code}:id:{digest}#{occurrence}"


def is_legacy_key(term_code: str, key: str | None) -> bool:
    m = _LEGACY.match(key or "")
    return bool(m and m.group("term") == term_code)


def occurrences(items: Sequence[tuple[str, tuple[int, ...], tuple[Any, ...]]]) -> list[int]:
    """Occurrence index of every ``(section_key, days, sort_key)`` within its (section, days) group."""
    groups: dict[tuple[str, tuple[int, ...]], list[int]] = defaultdict(list)
    for i, (sk, days, _sort) in enumerate(items):
        groups[(sk, tuple(sorted(set(days))))].append(i)
    out = [0] * len(items)
    for idxs in groups.values():
        for occ, i in enumerate(sorted(idxs, key=lambda j: (items[j][2], j))):
            out[i] = occ
    return out


def time_sort_key(t: time | str | None, row: int | None) -> tuple[Any, ...]:
    if isinstance(t, time):
        t = t.strftime("%H:%M")
    return (t or "99:99", row or 0)


__all__ = [
    "COUPLED",
    "MEETING_FIELDS",
    "SECTION_FIELDS",
    "expand_coupled",
    "is_legacy_key",
    "meeting_identity",
    "occurrences",
]
