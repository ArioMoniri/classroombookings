"""Structured suggestion options: every ``Diagnosis`` carries ``params["options"]`` — one dict per
suggestion string (same index) with the action and its arguments, so consumers (run-report fixes,
studio pre-check, the AI layer) never parse the wording.  The patterns below are the solver's *own*
phrasings (diagnose.py) and live next to their producer.

Actions: ``move`` (``event_id, room_code, room_codes, day, start_period, end_period``; ``room_code`` is the
set joined by ``+`` — ``A101+A106`` — and ``room_codes`` lists it), ``release_room`` (+
``holder_event_ids``), ``unlock`` (``event_ids``), ``relax`` (``kind, event_ids``), ``split``
(``event_ids, max_rooms``), ``manual`` (no arguments: needs a human).
"""

from __future__ import annotations

import re
from typing import Any

# "use A101 at day 1 P4-P6"
_USE = re.compile(r"^use (?P<room>\S+) at day (?P<day>[1-7]) P(?P<start>\d+)-P(?P<end>\d+)$")
# "alternative periods on the same day: P5-P7 in A101, P8-P10 in B201"
_ALT = re.compile(r"^alternative periods on the same day: P(?P<start>\d+)-P(?P<end>\d+) in (?P<room>[^,\s]+)")
# "release A101 (58) at day 1 P4-P6 held by PSI 155 (#12), MAT 112 (#14)"
_RELEASE = re.compile(
    r"^release (?P<room>\S+) \((?P<cap>\d+)\) at day (?P<day>[1-7]) P(?P<start>\d+)-P(?P<end>\d+) held by (?P<who>.+)$"
)
_UNLOCK = re.compile(r"^unlock\b")
_RELAX = re.compile(r"^make the (?P<kind>[a-z_]+) rule soft")
_SPLIT = re.compile(r"allow split(?:ting)?", re.IGNORECASE)
_HOLDER = re.compile(r"\(#(?P<id>\d+)\)")
_DAY_IN_MSG = re.compile(r"\bday (?P<day>[1-7]) P\d+")


def classify(index: int, text: str, message: str, event_ids: list[int]) -> dict[str, Any]:
    t = " ".join(str(text).split())
    target = event_ids[0] if event_ids else None
    base: dict[str, Any] = {"index": index}
    if m := _USE.match(t):
        return {
            **base,
            "action": "move",
            "event_id": target,
            "room_code": m["room"],
            "room_codes": m["room"].split("+"),
            "day": int(m["day"]),
            "start_period": int(m["start"]),
            "end_period": int(m["end"]),
        }
    if m := _ALT.match(t):
        day = _DAY_IN_MSG.search(message or "")
        return {
            **base,
            "action": "move",
            "event_id": target,
            "room_code": m["room"],
            "room_codes": m["room"].split("+"),
            "day": int(day["day"]) if day else None,
            "start_period": int(m["start"]),
            "end_period": int(m["end"]),
        }
    if m := _RELEASE.match(t):
        return {
            **base,
            "action": "release_room",
            "event_id": target,
            "room_code": m["room"],
            "room_codes": [m["room"]],
            "day": int(m["day"]),
            "start_period": int(m["start"]),
            "end_period": int(m["end"]),
            "holder_event_ids": [int(h["id"]) for h in _HOLDER.finditer(m["who"])],
        }
    if _UNLOCK.match(t):
        return {**base, "action": "unlock", "event_ids": list(event_ids)}
    if m := _RELAX.match(t):
        return {**base, "action": "relax", "kind": m["kind"], "event_ids": list(event_ids)}
    if _SPLIT.search(t):
        return {**base, "action": "split", "event_ids": list(event_ids), "max_rooms": 3}
    return {**base, "action": "manual"}


def options_for(suggestions: list[str], message: str, event_ids: list[int]) -> list[dict[str, Any]]:
    return [classify(i, s, message, event_ids) for i, s in enumerate(suggestions)]


__all__ = ["classify", "options_for"]
