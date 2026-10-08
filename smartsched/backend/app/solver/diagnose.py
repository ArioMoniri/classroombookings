"""Infeasibility explanation.

Three rungs, cheapest first (see README "Diagnosis"):

1. **Static checker** (:func:`static_check`) — pure Python over the pruned domains: events with
   no eligible room (size > every room, tags nobody has, pins to unknown rooms), fixed times
   outside the grid, overlapping locked assignments, fixed-vs-fixed cohort/instructor clashes and
   pigeonhole overloads (more fixed-time events in a slot than rooms).  Reported *before* the big
   model is built.
2. **Assumption core** (:func:`core_diagnosis`) — a satisfaction-only copy of the model with one
   assumption literal per event ("placed") and per actionable constraint group (room, cohort,
   instructor, locked event, explicit constraint).  ``SufficientAssumptionsForInfeasibility`` gives
   a (non-minimal) core which is shrunk by deletion-based probing under a per-probe time limit.
3. **Slack relaxation** (:func:`relaxation_diagnosis`) — the same model with ``placed[e]`` free,
   minimising the number of unplaced events.  Every unplaced event is then explained by probing
   its options against the placed ones (:func:`explain_event`): rooms that fit but are busy (and by
   whom), rooms excluded by capacity/tags/pins, cohort/instructor clashes, alternative periods.
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from ortools.sat.python import cp_model  # type: ignore[import-untyped]

from app.solver.build import Prepared, build_model, hint_assignments, make_solver, stable_rank
from app.solver.constraints import HANDLERS
from app.solver.context import ModelContext
from app.solver.domains import (
    EventDomain,
    TimeOption,
    effective_capacity,
    room_fits_alone,
    shares_room,
    sharing_capacity,
    trusted_lock,
    weeks_intersect,
)
from app.solver.model import Assignment, Diagnosis, Event, Room
from app.solver.seats import seat_conflicts

# --------------------------------------------------------------------------- helpers


def _label(e: Event) -> str:
    return f"{e.label} (#{e.id})"


def _time_str(t: TimeOption | Assignment) -> str:
    return f"day {t.day} P{t.start}-P{t.end}"


def _top(counter: Counter[str], n: int = 3) -> str:
    return "; ".join(f"{k} ×{v}" if v > 1 else k for k, v in counter.most_common(n))


def reason_category(reason: str) -> str:
    """Planner-level category of a pruning reason string (so "not in the pinned room set (room_pin #6)"
    ×9 collapses into one ``pin`` line): ``locked``, ``pin``, ``forbid``, ``tags``, ``capacity``,
    ``blocked``, ``cohort``, ``instructor`` or the constraint kind named in the reason."""
    r = reason.casefold()
    if r.startswith("locked to another room"):
        return "locked"
    if "room_pin" in r or "pinned room" in r:
        return "pin"
    if "room_forbid" in r:
        return "forbid"
    if "tag" in r:
        return "tags"
    if "capacity" in r:
        return "capacity"
    if "blocked" in r or "room_closed" in r:
        return "blocked"
    if r.startswith("cohort "):
        return "cohort"
    if r.startswith("instructor "):
        return "instructor"
    m = _KIND_RE.search(reason)
    return m.group(1) if m else "other"


def reason_categories(reasons: Iterable[str]) -> dict[str, int]:
    out: Counter[str] = Counter(reason_category(r) for r in reasons)
    return dict(out.most_common())


_KIND_RE = re.compile(r"\(([a-z_]+)(?: #[^)]*)?\)")
_REASON_KINDS = {"block": "no_room_overlap", "cohort": "no_cohort_overlap", "instructor": "no_instructor_overlap"}


def kinds_in_reasons(reasons: Iterable[str]) -> list[str]:
    """Constraint kinds named in domain-pruning reason strings (``"... (capacity)"``)."""
    found: Counter[str] = Counter()
    for r in reasons:
        for m in _KIND_RE.findall(r):
            kind = _REASON_KINDS.get(m, m)
            if kind in HANDLERS:
                found[kind] += 1
        if r.startswith("cohort "):
            found["no_cohort_overlap"] += 1
        elif r.startswith("instructor "):
            found["no_instructor_overlap"] += 1
    return [k for k, _ in found.most_common()]


# --------------------------------------------------------------------------- static checker


def static_check(prep: Prepared) -> list[Diagnosis]:
    inp = prep.inp
    doms = prep.doms
    out: list[Diagnosis] = []
    all_tags: set[str] = set()
    for r in inp.rooms:
        all_tags |= set(r.tags)
    room_ids = {r.id for r in inp.rooms}
    for e in inp.events:
        dom = doms.domain(e.id)
        if e.fixed_day is not None and e.fixed_day not in inp.days:
            out.append(
                Diagnosis(
                    [e.id],
                    ["fixed_time"],
                    f"{_label(e)} is fixed on day {e.fixed_day}, which is not in the grid {list(inp.days)}",
                    ["correct the day of the request", "add the day to the term grid"],
                    "error",
                    "bad_time",
                    {"day": e.fixed_day},
                )
            )
            continue
        if e.fixed_start is not None and (
            e.fixed_start < 1 or e.fixed_start + max(1, e.duration) - 1 > inp.periods_per_day
        ):
            out.append(
                Diagnosis(
                    [e.id],
                    ["fixed_time"],
                    f"{_label(e)} is fixed at P{e.fixed_start} for {e.duration} "
                    f"periods, outside the {inp.periods_per_day}-period grid",
                    ["shorten the request", "move it earlier"],
                    "error",
                    "bad_time",
                    {"start": e.fixed_start, "duration": e.duration},
                )
            )
            continue
        if e.weeks and not weeks_intersect(e.weeks, frozenset(inp.weeks)):
            out.append(
                Diagnosis(
                    [e.id],
                    [],
                    f"{_label(e)} has no week inside the horizon "
                    f"{min(inp.weeks)}..{max(inp.weeks)}; it is scheduled but never occupies a room",
                    [],
                    "info",
                    "out_of_horizon",
                    {"weeks": sorted(e.weeks)},
                )
            )
        if not dom.times:
            reasons = Counter(dom.time_reasons.values())
            out.append(
                Diagnosis(
                    [e.id],
                    kinds_in_reasons(reasons) or ["fixed_time"],
                    f"{_label(e)} has no feasible time: {_top(reasons) or 'empty window'}",
                    ["widen the day/period window", "move the conflicting fixed-time event"],
                    "error",
                    "no_time",
                    {"reasons": dict(reasons.most_common(5))},
                )
            )
            continue
        if e.needs_room and not dom.rooms:
            out.append(_no_room_diagnosis(e, dom, inp.rooms, all_tags, room_ids))
            continue
        if e.needs_room and dom.option_count() == 0:
            reasons = Counter(dom.pair_reasons.values())
            out.append(
                Diagnosis(
                    [e.id],
                    kinds_in_reasons(reasons) or ["no_room_overlap"],
                    f"{_label(e)} — every eligible room is blocked at its time(s): {_top(reasons)}",
                    ["release one of the blocks", "move the event to another time"],
                    "error",
                    "all_blocked",
                    {"reasons": dict(reasons.most_common(5))},
                )
            )
    for kind, key, a, b in doms.static_conflicts:
        ea, eb = doms.events_by_id[a], doms.events_by_id[b]
        noun = "cohort" if kind == "no_cohort_overlap" else "instructor"
        out.append(
            Diagnosis(
                [a, b],
                [kind],
                f"{noun} '{key}': {_label(ea)} ({_time_str(doms.domain(a).times[0])}) and {_label(eb)} "
                f"({_time_str(doms.domain(b).times[0])}) are both fixed at overlapping times in shared weeks",
                [
                    f"move {ea.label} or {eb.label} to another period",
                    f"split the {noun} key if the two groups are really different",
                ],
                "error",
                "fixed_conflict",
                {
                    "noun": noun,
                    "key": key,
                    "kind": kind,
                    "keys": [[kind, key]],
                    "day": doms.domain(a).times[0].day,
                    "start": doms.domain(a).times[0].start,
                },
            )
        )
    out.extend(_input_conflicts(prep))
    out.extend(_trusted_lock_warnings(prep))
    out.extend(_locked_conflicts(prep))
    out.extend(_locked_seat_budget(prep))
    out.extend(_pigeonhole(prep))
    return out


def _input_conflicts(prep: Prepared) -> list[Diagnosis]:
    """``fixed_conflicts_as_warnings``: one warning per clashing pair of fixed requests (both named,
    with the shared key and a concrete fix); the pair keeps its times, everything else stays hard."""
    doms = prep.doms
    by_pair: dict[tuple[int, int], list[tuple[str, str]]] = defaultdict(list)
    for kind, key, a, b in doms.waived_conflicts:
        by_pair[(min(a, b), max(a, b))].append((kind, key))
    out: list[Diagnosis] = []
    for (a, b), keys in sorted(by_pair.items()):
        ea, eb = doms.events_by_id[a], doms.events_by_id[b]
        ta, tb = doms.domain(a).times[0], doms.domain(b).times[0]
        kinds = sorted({k for k, _ in keys})
        what = "; ".join(
            f"{'same instructor' if k == 'no_instructor_overlap' else 'same cohort'} '{key}'" for k, key in keys[:3]
        )
        sugg = [f"move {ea.label} or {eb.label} to another period"]
        if "no_instructor_overlap" in kinds:
            sugg.append("check the instructor name of both requests (a typo or a shared placeholder merges two people)")
        if "no_cohort_overlap" in kinds:
            sugg.append("check the programme / class year of both requests (electives of one cohort may overlap)")
        out.append(
            Diagnosis(
                [a, b],
                kinds,
                f"input conflict: {_label(ea)} ({_time_str(ta)}) and {_label(eb)} ({_time_str(tb)}) are both "
                f"fixed at overlapping times ({what}); no room choice can resolve this — both keep their times",
                sugg,
                "warning",
                "input_conflict",
                {
                    "keys": [[k, key] for k, key in keys],
                    "noun": "instructor" if "no_instructor_overlap" in kinds else "cohort",
                    "key": keys[0][1],
                    "day": ta.day,
                    "start": ta.start,
                },
            )
        )
    return out


def _trusted_lock_warnings(prep: Prepared) -> list[Diagnosis]:
    """``trust_locked_rooms``: a locked room set smaller than the expected size (or lacking a required
    tag) is kept and reported, e.g. "ACU 132 expects 122 students but is locked to A 207 (55 exam /
    120 lecture seats)"."""
    inp = prep.inp
    out: list[Diagnosis] = []
    for e in inp.events:
        if not trusted_lock(inp, e) or e.locked is None or not e.needs_room:
            continue
        rooms = [prep.doms.rooms_by_id[r] for r in e.locked.room_ids if r in prep.doms.rooms_by_id]
        if not rooms:
            continue
        codes = " + ".join(r.code for r in rooms)
        seats = sum(effective_capacity(r, e) for r in rooms)
        if seats < e.size:
            lecture = sum(r.capacity for r in rooms)
            exam = sum(r.exam_capacity for r in rooms)
            bigger = sorted(
                (r for r in inp.rooms if effective_capacity(r, e) >= e.size and not (e.required_tags - r.tags)),
                key=lambda r: (effective_capacity(r, e), r.code),
            )[:2]
            sugg = ["check the enrolment estimate (planning-list sizes are expected numbers)"]
            if bigger:
                sugg.append("or move it to " + " / ".join(f"{r.code} ({effective_capacity(r, e)})" for r in bigger))
            out.append(
                Diagnosis(
                    [e.id],
                    ["capacity"],
                    f"{e.label} expects {e.size} students but is locked to {codes} ({exam} exam / {lecture} lecture "
                    f"seats); the planner's room is kept",
                    sugg,
                    "warning",
                    "trusted_lock_capacity",
                    {
                        "rooms": [r.id for r in rooms],
                        "room_codes": [r.code for r in rooms],
                        "seats": seats,
                        "size": e.size,
                        "fitting_rooms": [r.code for r in bigger],
                    },
                )
            )
        missing = sorted({t for r in rooms for t in e.required_tags - r.tags})
        clash = sorted({t for r in rooms for t in e.forbidden_tags & r.tags})
        if missing or clash:
            parts = ([f"lacks {missing}"] if missing else []) + ([f"carries {clash}"] if clash else [])
            out.append(
                Diagnosis(
                    [e.id],
                    ["room_tags"],
                    f"{e.label} is locked to {codes}, which {' and '.join(parts)}; the planner's room is kept",
                    ["check the room requirement of the request or the room's tags (room master)"],
                    "warning",
                    "trusted_lock_tags",
                    {"rooms": [r.id for r in rooms], "missing_tags": missing, "forbidden_tags": clash},
                )
            )
    return out


def _locked_seat_budget(prep: Prepared) -> list[Diagnosis]:
    """Locked room-sharing events (single- or multi-room exams) whose seats cannot be allotted."""
    inp = prep.inp
    locked = {e.id: e.locked for e in inp.events if e.locked is not None and shares_room(e)}
    if len(locked) < 2:
        return []
    out: list[Diagnosis] = []
    for ids, room_ids, day, period, week in seat_conflicts(inp, prep.doms.events_by_id, prep.doms.rooms_by_id, locked):
        events = [prep.doms.events_by_id[i] for i in ids]
        codes = " + ".join(prep.doms.rooms_by_id[r].code for r in room_ids)
        cap = sum(sharing_capacity(prep.doms.rooms_by_id[r], events) for r in room_ids)
        need = sum(e.size for e in events)
        if all(trusted_lock(inp, e) for e in events):
            out.append(
                Diagnosis(
                    list(ids),
                    ["capacity"],
                    f"locked exams share {codes} on day {day} P{period} (week {week}): {need} students for {cap} "
                    "seats (" + ", ".join(f"{e.label} ({e.size})" for e in events[:6]) + "); the planner's rooms "
                    "are kept and nobody else is seated there",
                    ["check the enrolment estimates or the rooms' exam capacity (room master)", "add a room"],
                    "warning",
                    "trusted_lock_capacity",
                    {
                        "rooms": list(room_ids),
                        "room_codes": [prep.doms.rooms_by_id[r].code for r in room_ids],
                        "seats": cap,
                        "size": need,
                        "shared": True,
                        "day": day,
                        "period": period,
                        "week": week,
                    },
                )
            )
            continue
        out.append(
            Diagnosis(
                list(ids),
                ["no_room_overlap", "fixed_time"],
                f"locked exams share {codes} on day {day} P{period} (week {week}) but need {need} seats and the "
                f"rooms seat {cap}: " + ", ".join(f"{e.label} ({e.size})" for e in events[:6]),
                [f"unlock one of {', '.join(e.label for e in events[:3])}", "add a room to one of the exams"],
                "error",
                "locked_overlap",
                {
                    "rooms": list(room_ids),
                    "room_codes": [prep.doms.rooms_by_id[r].code for r in room_ids],
                    "day": day,
                    "period": period,
                    "week": week,
                    "need": need,
                    "seats": cap,
                    "shared": True,
                },
            )
        )
    return out


def _no_room_diagnosis(
    e: Event, dom: EventDomain, rooms: tuple[Room, ...], all_tags: set[str], room_ids: set[int]
) -> Diagnosis:
    kinds: list[str] = []
    sugg: list[str] = []
    missing_pins = sorted(e.required_room_ids - room_ids)
    if missing_pins:
        kinds.append("room_pin")
        sugg.append(f"pinned room id(s) {missing_pins} do not exist; fix the pin")
    missing_tags = sorted(e.required_tags - all_tags)
    if missing_tags:
        kinds.append("room_tags")
        sugg.append(f"no room carries tag(s) {missing_tags}; tag a room or drop the requirement")
    eligible = [
        r
        for r in rooms
        if (not e.required_room_ids or r.id in e.required_room_ids)
        and r.id not in e.forbidden_room_ids
        and e.required_tags <= r.tags
        and not (e.forbidden_tags & r.tags)
    ]
    if eligible and not any(room_fits_alone(r, e) for r in eligible) and e.max_rooms <= 1:
        kinds.append("capacity")
        best = max(eligible, key=lambda r: effective_capacity(r, e))
        sugg.append(
            f"largest eligible room is {best.code} ({effective_capacity(best, e)} seats) < "
            f"{e.size}; allow splitting (max_rooms>1), reduce the group or raise the room capacity"
        )
        combos = sorted(eligible, key=lambda r: -effective_capacity(r, e))[:3]
        if sum(effective_capacity(r, e) for r in combos) >= e.size:
            sugg.append("split across " + " + ".join(f"{r.code}({effective_capacity(r, e)})" for r in combos))
    params: dict[str, Any] = {"size": e.size, "missing_pins": missing_pins, "missing_tags": missing_tags}
    if "capacity" in kinds:
        params.update(largest_room=best.code, largest_capacity=effective_capacity(best, e))
    by_id = {r.id: r for r in rooms}
    pinned = [by_id[r] for r in sorted(e.required_room_ids) if r in by_id]
    locked_rooms = [by_id[r] for r in (e.locked.room_ids if e.locked is not None else ()) if r in by_id]
    if pinned:
        params["pinned_rooms"] = [{"room": r.code, "capacity": effective_capacity(r, e)} for r in pinned]
        seats = sum(effective_capacity(r, e) for r in pinned[: max(1, e.max_rooms)])
        if "capacity" not in kinds and seats < e.size:
            kinds.insert(0, "capacity")
            sugg.insert(0, f"the pinned room(s) seat {seats} < {e.size}; pin a bigger room or split the group")
            big = max(pinned, key=lambda r: effective_capacity(r, e))
            params.update(largest_room=big.code, largest_capacity=effective_capacity(big, e), pinned_seats=seats)
    if locked_rooms:
        params["locked_rooms"] = [{"room": r.code, "capacity": effective_capacity(r, e)} for r in locked_rooms]
        if pinned and not {r.id for r in pinned} & {r.id for r in locked_rooms}:
            params["pin_vs_lock"] = True
            if "room_pin" not in kinds:
                kinds.append("room_pin")
            sugg.append(
                "the request is locked to "
                + ", ".join(r.code for r in locked_rooms)
                + " but pinned to "
                + ", ".join(r.code for r in pinned)
                + "; keep one of them"
            )
    fitting = sorted(
        (
            r
            for r in rooms
            if e.required_tags <= r.tags
            and not (e.forbidden_tags & r.tags)
            and r.id not in e.forbidden_room_ids
            and effective_capacity(r, e) >= e.size
        ),
        key=lambda r: effective_capacity(r, e),
    )
    params["fitting_rooms"] = [{"room": r.code, "capacity": effective_capacity(r, e)} for r in fitting[:6]]
    params["excluded"] = reason_categories(dom.room_reasons.values())
    if not kinds:
        reasons = Counter(dom.room_reasons.values())
        kinds.extend(kinds_in_reasons(reasons))
        sugg.append("reasons: " + _top(reasons))
        params["reasons"] = dict(reasons.most_common(5))
    params["reason"] = (
        "pin"
        if missing_pins
        else "tags"
        if missing_tags
        else "capacity"
        if "capacity" in kinds
        else "pin_vs_lock"
        if params.get("pin_vs_lock")
        else "rules"
    )
    return Diagnosis(
        [e.id],
        kinds or ["capacity"],
        f"{_label(e)} (size {e.size}) has no eligible room"
        + (f": {sugg[0]}" if params["reason"] in ("capacity", "pin_vs_lock") and sugg else ""),
        sugg,
        "error",
        "no_room",
        params,
    )


def _locked_conflicts(prep: Prepared) -> list[Diagnosis]:
    inp = prep.inp
    out: list[Diagnosis] = []
    locked = [(e, e.locked) for e in inp.events if e.locked is not None]
    occ: dict[tuple[int, int, int], list[tuple[Event, Assignment]]] = defaultdict(list)
    for e, a in locked:
        for r in a.room_ids:
            for p in range(a.start, a.end + 1):
                occ[(r, a.day, p)].append((e, a))
    seen: set[tuple[int, int]] = set()
    for (r, day, p), items in sorted(occ.items()):
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ea, eb = items[i][0], items[j][0]
                key = (min(ea.id, eb.id), max(ea.id, eb.id))
                if key in seen or not weeks_intersect(ea.weeks, eb.weeks):
                    continue
                if shares_room(ea) and shares_room(eb):
                    continue  # seat budget of shared rooms is checked by the model / evaluation
                seen.add(key)
                code = prep.doms.rooms_by_id[r].code if r in prep.doms.rooms_by_id else str(r)
                out.append(
                    Diagnosis(
                        [ea.id, eb.id],
                        ["no_room_overlap", "fixed_time"],
                        f"locked assignments overlap: {_label(ea)} and {_label(eb)} both hold {code} on day {day} P{p}",
                        [f"unlock {ea.label} or {eb.label}"],
                        "error",
                        "locked_overlap",
                        {"rooms": [r], "room_codes": [code], "day": day, "period": p, "shared": False},
                    )
                )
    for e, a in locked:
        dom = prep.doms.domain(e.id)
        if not e.needs_room:
            continue
        bad_rooms = [r for r in a.room_ids if r not in dom.rooms]
        if bad_rooms:
            reasons = [dom.room_reasons.get(r, "unknown room") for r in bad_rooms]
            codes = [prep.doms.rooms_by_id[r].code if r in prep.doms.rooms_by_id else str(r) for r in bad_rooms]
            out.append(
                Diagnosis(
                    [e.id],
                    ["fixed_time", "capacity"],
                    f"locked assignment of {_label(e)} uses room(s) {', '.join(codes)} which are not eligible: "
                    + _top(Counter(reasons), 4),  # duplicate reasons collapsed ("... ×3")
                    ["unlock the event", "fix the room (capacity/tags) or the pin"],
                    "error",
                    "locked_ineligible",
                    {
                        "rooms": bad_rooms,
                        "room_codes": codes,
                        "reasons": reasons,
                        "categories": reason_categories(reasons),
                        "day": a.day,
                        "start": a.start,
                        "end": a.end,
                    },
                )
            )
        elif any(not dom.is_pair_allowed(dom.times[0], r) for r in a.room_ids):
            out.append(
                Diagnosis(
                    [e.id],
                    ["room_closed", "no_room_overlap"],
                    f"locked assignment of {_label(e)} sits on a blocked slot ({_time_str(a)})",
                    ["release the block", "unlock the event"],
                    "error",
                    "locked_blocked",
                    {"day": a.day, "start": a.start, "end": a.end, "rooms": list(a.room_ids)},
                )
            )
    return out


def _pigeonhole(prep: Prepared) -> list[Diagnosis]:
    """More fixed-time room-needing events in a (day, period, week) than rooms they could use."""
    inp = prep.inp
    doms = prep.doms
    cells: dict[tuple[int, int], list[EventDomain]] = defaultdict(list)
    for e in inp.events:
        dom = doms.domain(e.id)
        if not e.needs_room or not dom.fixed_time or e.max_rooms > 1 or shares_room(e):
            continue
        t = dom.times[0]
        for p in t.periods:
            cells[(t.day, p)].append(dom)
    out: list[Diagnosis] = []
    reported: set[tuple[int, ...]] = set()
    for (day, p), ds in sorted(cells.items()):
        for w in inp.weeks:
            group = [d for d in ds if w in d.event.weeks]
            if len(group) < 2:
                continue
            rooms: set[int] = set()
            for d in group:
                rooms.update(r for r in d.rooms if d.is_pair_allowed(d.times[0], r))
            if len(group) > len(rooms):
                ids = tuple(sorted(d.event.id for d in group))
                if ids in reported:
                    continue
                reported.add(ids)
                labels = ", ".join(d.event.label for d in group[:6])
                out.append(
                    Diagnosis(
                        list(ids),
                        ["no_room_overlap", "capacity"],
                        f"{len(group)} fixed-time events need a room on day {day} P{p} in "
                        f"week {w} but only {len(rooms)} eligible room(s) exist: {labels}",
                        [
                            "move one of them to another period",
                            "allow a larger set of rooms (capacity/tags)",
                            "make one of them flexible in time",
                        ],
                        "error",
                        "pigeonhole",
                        {"n": len(group), "day": day, "period": p, "week": w, "rooms": len(rooms)},
                    )
                )
    return out


# --------------------------------------------------------------------------- explanation of one event


class _PlacedIndex:
    def __init__(self, prep: Prepared, placed: dict[int, Assignment]) -> None:
        self.prep = prep
        self.placed = placed
        self.room_occ: dict[tuple[int, int, int], list[int]] = defaultdict(list)
        self.key_occ: dict[tuple[str, int, int], list[int]] = defaultdict(list)
        self.waived = {(key, min(a, b), max(a, b)) for _k, key, a, b in prep.doms.waived_conflicts}
        for eid, a in placed.items():
            e = prep.doms.events_by_id[eid]
            for p in range(a.start, a.end + 1):
                for r in a.room_ids:
                    self.room_occ[(r, a.day, p)].append(eid)
                for k in e.cohort_keys | e.instructor_keys:
                    self.key_occ[(k, a.day, p)].append(eid)

    def room_busy(self, room_id: int, t: TimeOption, weeks: frozenset[int], event: Event | None = None) -> list[int]:
        """Events blocking ``room_id`` at ``t``; a sharing event is only blocked by exclusive
        occupants or when the shared seat budget would overflow."""
        ids: list[int] = []
        for p in t.periods:
            for eid in self.room_occ.get((room_id, t.day, p), []):
                if eid not in ids and weeks_intersect(self.prep.doms.events_by_id[eid].weeks, weeks):
                    ids.append(eid)
        if event is None or not shares_room(event) or not ids:
            return ids
        others = [self.prep.doms.events_by_id[i] for i in ids]
        if any(not shares_room(o) for o in others):
            return ids
        room = self.prep.doms.rooms_by_id[room_id]
        cap = sharing_capacity(room, [*others, event])
        return ids if sum(o.size for o in others) + event.size > cap else []

    def key_busy(self, key: str, t: TimeOption, weeks: frozenset[int], event_id: int | None = None) -> list[int]:
        """Placed events holding ``key`` at ``t``; pairs waived as input conflicts do not count."""
        ids: list[int] = []
        for p in t.periods:
            for eid in self.key_occ.get((key, t.day, p), []):
                if eid in ids or not weeks_intersect(self.prep.doms.events_by_id[eid].weeks, weeks):
                    continue
                if event_id is not None and (key, min(eid, event_id), max(eid, event_id)) in self.waived:
                    continue
                ids.append(eid)
        return ids


def explain_event(
    prep: Prepared, event_id: int, placed: dict[int, Assignment], index: _PlacedIndex | None = None
) -> Diagnosis:
    """Why can't ``event_id`` be placed next to the ``placed`` assignments?  Concrete suggestions."""
    doms = prep.doms
    e = doms.events_by_id[event_id]
    dom = doms.domain(event_id)
    idx = index or _PlacedIndex(prep, placed)
    kinds: Counter[str] = Counter()
    busy_rooms: list[tuple[str, int]] = []  # (text, count)
    busy_params: dict[int, dict[str, Any]] = {}  # room id -> {room, capacity, day, start, end, holders}
    clash_params: list[dict[str, Any]] = []
    free_params: list[dict[str, Any]] = []
    key_clashes: list[str] = []
    suggestions: list[str] = []
    free_options: list[str] = []
    for t in dom.times:
        clashes = [(k, idx.key_busy(k, t, e.weeks, e.id)) for k in sorted(e.cohort_keys | e.instructor_keys)]
        clashes = [(k, ids) for k, ids in clashes if ids]
        if clashes:
            for k, ids in clashes[:2]:
                kinds["no_cohort_overlap" if k in e.cohort_keys else "no_instructor_overlap"] += 1
                names = ", ".join(_label(doms.events_by_id[i]) for i in ids[:3])
                key_clashes.append(
                    f"{_time_str(t)}: {'cohort' if k in e.cohort_keys else 'instructor'} '{k}' busy with {names}"
                )
                if len(clash_params) < 6:
                    clash_params.append(
                        {
                            "kind": "cohort" if k in e.cohort_keys else "instructor",
                            "key": k,
                            "day": t.day,
                            "start": t.start,
                            "end": t.end,
                            "holders": list(ids[:3]),
                        }
                    )
            continue
        if not e.needs_room:
            free_options.append(_time_str(t))
            continue
        for rid in dom.rooms:
            if not dom.is_pair_allowed(t, rid):
                kinds["room_closed"] += 1
                continue
            holders = idx.room_busy(rid, t, e.weeks, e)
            room = doms.rooms_by_id[rid]
            if holders:
                kinds["no_room_overlap"] += 1
                names = ", ".join(_label(doms.events_by_id[i]) for i in holders[:2])
                if shares_room(e) and all(shares_room(doms.events_by_id[i]) for i in holders):
                    names += f" (shared seats exceed {sharing_capacity(room, [e])})"
                busy_rooms.append(
                    (f"{room.code} ({effective_capacity(room, e)}) at {_time_str(t)} held by {names}", len(holders))
                )
                if rid not in busy_params and len(busy_params) < 8:
                    busy_params[rid] = {
                        "room": room.code,
                        "capacity": effective_capacity(room, e),
                        "day": t.day,
                        "start": t.start,
                        "end": t.end,
                        "holders": list(holders[:3]),
                    }
            else:
                free_options.append(f"{room.code} at {_time_str(t)}")
                if len(free_params) < 3:
                    free_params.append({"room": room.code, "day": t.day, "start": t.start, "end": t.end})
    for k in kinds_in_reasons(dom.room_reasons.values()):
        kinds[k] += 1
    pruned = Counter(dom.room_reasons.values())
    parts: list[str] = []
    if busy_rooms:
        parts.append("rooms that fit are busy: " + "; ".join(b for b, _ in busy_rooms[:4]))
        for b, _ in busy_rooms[:3]:
            suggestions.append(f"release {b}")
    if key_clashes:
        parts.append("; ".join(key_clashes[:3]))
        suggestions.append("move the clashing event or correct the cohort/instructor keys")
    if pruned:
        parts.append(f"{len(dom.room_reasons)} room(s) excluded: " + _top(pruned))
    if free_options:
        parts.append("free options exist: " + ", ".join(free_options[:3]) + (" ..." if len(free_options) > 3 else ""))
        suggestions.append("use " + free_options[0])
    if e.needs_room and e.max_rooms <= 1 and e.size > 0:
        fitting = [r for r in prep.inp.rooms if room_fits_alone(r, e)]
        if not fitting:
            suggestions.append("allow splitting across rooms (max_rooms > 1) or raise a room's capacity")
    if dom.fixed_time and e.needs_room:
        alt = _alternative_periods(prep, e, idx)
        if alt:
            suggestions.append("alternative periods on the same day: " + ", ".join(alt[:4]))
    suggestions.extend(_suggest_from_reasons(prep, e, dom))
    if not parts:
        parts.append("no option survives the hard rules")
    if not suggestions:
        suggestions.append("widen the event's day/period window or its room requirements")
    msg = (
        f"{_label(e)} (size {e.size}, {e.duration} period(s), "
        f"{_time_str(dom.times[0]) if dom.fixed_time else f'{len(dom.times)} time options'}) cannot be placed: "
        + " | ".join(parts)
    )
    caps = [effective_capacity(r, e) for r in prep.inp.rooms]
    fits = sum(1 for c in caps if c >= e.size)
    params: dict[str, Any] = {
        "size": e.size,
        "duration": e.duration,
        "time_options": len(dom.times),
        "busy": list(busy_params.values()),
        "clashes": clash_params,
        "free": free_params,
        "excluded": reason_categories(dom.room_reasons.values()),
        "fitting_rooms": fits,
        "largest_capacity": max(caps, default=0),
        "problem": (
            "capacity"
            if e.needs_room and e.max_rooms <= 1 and e.size > 0 and fits == 0
            else "rooms_busy"
            if busy_params
            else "clash"
            if clash_params
            else "excluded"
        ),
    }
    if dom.fixed_time:
        params.update(day=dom.times[0].day, start=dom.times[0].start, end=dom.times[0].end)
    return Diagnosis(
        [event_id], [k for k, _ in kinds.most_common()] or ["capacity"], msg, suggestions, "error", "unplaced", params
    )


def _suggest_from_reasons(prep: Prepared, e: Event, dom: EventDomain) -> list[str]:
    """One concrete suggestion per kind that excluded rooms for this event."""
    out: list[str] = []
    kinds = kinds_in_reasons(dom.room_reasons.values())
    rooms = prep.inp.rooms
    if "capacity" in kinds and e.needs_room:
        biggest = max(rooms, key=lambda r: effective_capacity(r, e), default=None)
        if biggest is not None and effective_capacity(biggest, e) < e.size:
            out.append(
                f"no room seats {e.size}: allow splitting (max_rooms > 1) or reduce the "
                f"group (largest is {biggest.code}, {effective_capacity(biggest, e)})"
            )
        else:
            out.append(f"rooms large enough for {e.size} are excluded by other rules; relax them or reduce the group")
    if "room_tags" in kinds:
        out.append(
            f"relax the tag rules (needs {sorted(e.required_tags)}, "
            f"avoids {sorted(e.forbidden_tags)}) or tag another room"
        )
    if "room_pin" in kinds:
        out.append("widen or remove the room pin")
    if "room_forbid" in kinds:
        out.append("remove the room ban for this event")
    for k in ("building_preference", "evening_programs_in_buildings", "room_preference", "day_window", "room_closed"):
        if k in kinds:
            out.append(f"make the {k} rule soft or exempt this event")
    return out


def _alternative_periods(prep: Prepared, e: Event, idx: _PlacedIndex) -> list[str]:
    inp = prep.inp
    dom = prep.doms.domain(e.id)
    fixed = dom.times[0]
    out: list[str] = []
    for start in range(1, inp.periods_per_day - max(1, e.duration) + 2):
        if start == fixed.start:
            continue
        t = TimeOption(fixed.day, start, max(1, e.duration))
        if any(idx.key_busy(k, t, e.weeks, e.id) for k in e.cohort_keys | e.instructor_keys):
            continue
        for rid in dom.rooms:
            if not idx.room_busy(rid, t, e.weeks, e) and not any(
                b.day == t.day and b.start <= t.end and t.start <= b.end and (b.week is None or b.week in e.weeks)
                for b in prep.doms.blocks_by_room.get(rid, [])
            ):
                out.append(f"P{t.start}-P{t.end} in {prep.doms.rooms_by_id[rid].code}")
                break
        if len(out) >= 4:
            break
    return out


# --------------------------------------------------------------------------- assumption cores


def _assumption_names(ctx: Any) -> dict[int, str]:
    names: dict[int, str] = {}
    for eid, lit in ctx.placed.items():
        names[lit.Index()] = f"event:{eid}"
    for name, lit in ctx.guards.items():
        names[lit.Index()] = name
    return names


def core_diagnosis(prep: Prepared, budget_s: float) -> tuple[list[Diagnosis], dict[str, Any]]:
    """Assumption core + deletion-based shrinking (single worker, satisfaction only)."""
    t0 = time.perf_counter()
    stats: dict[str, Any] = {"core_probes": 0}
    ctx = build_model(prep, "assume")
    names = _assumption_names(ctx)
    lit_by_name: dict[str, Any] = {f"event:{eid}": lit for eid, lit in ctx.placed.items()}
    lit_by_name.update(ctx.guards)
    all_lits = [ctx.placed[e.id] for e in prep.inp.events] + [ctx.guards[n] for n in ctx.guard_order]
    model = ctx.model
    model.AddAssumptions(all_lits)
    solver = make_solver(prep.inp, max(0.5, budget_s * 0.4), workers=1)
    status = solver.Solve(model)
    stats["core_probes"] += 1
    stats["core_first_status"] = solver.StatusName(status)
    if status != cp_model.INFEASIBLE:
        stats["core_s"] = round(time.perf_counter() - t0, 3)
        return [], stats
    core = [names[i] for i in solver.SufficientAssumptionsForInfeasibility() if i in names]
    stats["core_initial"] = len(core)
    # deletion-based shrinking: drop an assumption; still infeasible -> it was not needed
    remaining = budget_s - (time.perf_counter() - t0)
    per_probe = max(0.3, min(3.0, remaining / max(1, len(core))))
    ordered = sorted(core, key=lambda n: (0 if n.startswith("event:") else 1, n))
    for name in ordered:
        if time.perf_counter() - t0 + per_probe > budget_s or len(core) <= 1:
            break
        trial = [n for n in core if n != name]
        model.ClearAssumptions()
        model.AddAssumptions([lit_by_name[n] for n in trial])
        probe = make_solver(prep.inp, per_probe, workers=1)
        st = probe.Solve(model)
        stats["core_probes"] += 1
        if st == cp_model.INFEASIBLE:
            core = trial
    stats["core_final"] = len(core)
    stats["core_s"] = round(time.perf_counter() - t0, 3)
    event_ids = sorted(int(n.split(":", 1)[1]) for n in core if n.startswith("event:"))
    groups = [n for n in core if not n.startswith("event:")]
    kinds = sorted({_kind_of(n) for n in groups} | {"fixed_time" for n in groups if n.startswith("locked:")})
    if not event_ids and not groups:
        return [], stats
    labels = ", ".join(_label(prep.doms.events_by_id[i]) for i in event_ids[:8])
    group_txt = ", ".join(groups[:8])
    msg = (
        f"minimal conflict set: events [{labels}]"
        + (f" with constraint groups [{group_txt}]" if groups else "")
        + " cannot all be satisfied together"
    )
    sugg = [
        "relax or remove one element of the conflict set",
        *[f"make {g.split(':', 1)[1]} ({_kind_of(g)}) soft or release it" for g in groups[:3]],
    ]
    return [Diagnosis(event_ids, kinds, msg, sugg, "error", "core")], stats


def _kind_of(guard_name: str) -> str:
    prefix = guard_name.split(":", 1)[0]
    return {
        "room": "no_room_overlap",
        "cohort": "no_cohort_overlap",
        "instructor": "no_instructor_overlap",
        "locked": "fixed_time",
    }.get(prefix, prefix)


# --------------------------------------------------------------------------- slack relaxation


def relaxation_diagnosis(
    prep: Prepared,
    budget_s: float,
    *,
    hints: list[Assignment] | None = None,
    explained: set[int] | frozenset[int] = frozenset(),
) -> tuple[list[Diagnosis], dict[str, Any], dict[int, Assignment]]:
    """Slack relaxation: maximise the number of placed events (hard rules intact).  ``hints`` (e.g.
    the greedy placement) warm-start the model; unplaced events whose id is in ``explained`` (already
    named by a static single-event error) are not explained twice."""
    t0 = time.perf_counter()
    stats: dict[str, Any] = {}
    ctx = build_model(prep, "relax")
    by_id = {a.event_id: a for a in (hints or [])}
    by_id.update({a.event_id: a for a in hint_assignments(prep.inp)})
    # lowest tier: stay in the warm start's rooms (the greedy hint follows the soft preferences, the
    # relaxation itself has none), so maximising the placement does not scatter the planner's rooms
    devs = []
    for e in prep.inp.events:
        h = by_id.get(e.id)
        if h is None or e.locked is not None or not e.needs_room:
            continue
        for r in h.room_ids:
            lit = ctx.room_use(e.id, r)
            if lit is not None and lit is not True:
                devs.append(1 - lit)
    if devs and ctx.relax_objective is not None:
        ctx.relax_objective = (len(devs) + 1) * ctx.relax_objective + sum(devs)
        ctx.model.Minimize(ctx.relax_objective)
        stats["relax_hint_terms"] = len(devs)
    ctx.add_hints([by_id[e.id] for e in prep.inp.events if e.id in by_id], unplaced_rest=True)
    solver = make_solver(prep.inp, max(0.5, budget_s))
    status = solver.Solve(ctx.model)
    stats["relax_status"] = solver.StatusName(status)
    stats["relax_s"] = round(time.perf_counter() - t0, 3)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return (
            [
                Diagnosis(
                    [],
                    [],
                    "the relaxation model found no partial schedule within the time budget",
                    ["raise the time limit"],
                    "warning",
                    "relax_timeout",
                )
            ],
            stats,
            {},
        )
    stats["relax_optimal"] = status == cp_model.OPTIMAL
    assignments = ctx.extract(solver)
    if status == cp_model.OPTIMAL and ctx.relax_objective is not None:
        remaining = budget_s - (time.perf_counter() - t0)
        canon = _canonical_placement(prep, ctx, solver, assignments, remaining)
        if canon is not None:
            assignments = canon
            stats["relax_canonical"] = True
    placed = {a.event_id: a for a in assignments}
    stats["unplaced"] = len(prep.inp.events) - len(placed)
    return explain_unplaced(prep, placed, explained), stats, placed


def _tie_weight(e: Event) -> int:
    """Tie-break among maximum placements: keep the event with more students; a fixed pseudo-random
    rank of the id separates equal sizes."""
    return min(e.size, 2000) * 1000 + stable_rank(e.id)


def _canonical_placement(
    prep: Prepared, ctx: ModelContext, solver: Any, assignments: list[Assignment], budget_s: float
) -> list[Assignment] | None:
    """CP-SAT's parallel search returns *some* optimal relaxation; when several placements are optimal,
    which events stay unplaced would depend on thread timing.  Fix the optimum and pick the placement
    that keeps the most students (then a fixed id rank), so the same input gives the same partial
    timetable (determinism with ``workers > 1``).  ``None`` if the stage does not prove optimality."""
    if budget_s < 0.5 or len(assignments) == len(prep.inp.events):
        return None
    value = int(round(solver.ObjectiveValue()))
    ctx.model.Add(ctx.relax_objective == value)
    ctx.model.Minimize(sum(_tie_weight(e) * (1 - ctx.placed[e.id]) for e in prep.inp.events if e.id in ctx.placed))
    ctx.model.ClearHints()
    ctx.add_hints(assignments, unplaced_rest=True)
    stage = make_solver(prep.inp, max(0.5, min(budget_s, 30.0)))
    status = stage.Solve(ctx.model)
    if status != cp_model.OPTIMAL:
        return None
    return ctx.extract(stage)  # type: ignore[no-any-return]


def explain_unplaced(
    prep: Prepared, placed: dict[int, Assignment], explained: set[int] | frozenset[int] = frozenset()
) -> list[Diagnosis]:
    """Summary + one explanation per unplaced event (at most 50) next to the ``placed`` ones."""
    unplaced = [e for e in prep.inp.events if e.id not in placed]
    out: list[Diagnosis] = []
    if unplaced:
        out.append(
            Diagnosis(
                [e.id for e in unplaced],
                [],
                f"{len(unplaced)} event(s) cannot be placed even when everything else is scheduled: "
                + ", ".join(_label(e) for e in unplaced[:10])
                + (" ..." if len(unplaced) > 10 else ""),
                ["see the per-event explanations below"],
                "error",
                "unplaced_summary",
            )
        )
        idx = _PlacedIndex(prep, placed)
        for e in [e for e in unplaced if e.id not in explained][:50]:
            out.append(explain_event(prep, e.id, placed, idx))
    return out


def diagnose_with_placement(
    prep: Prepared,
    budget_s: float,
    *,
    core: bool = True,
    hints: list[Assignment] | None = None,
    explained: set[int] | frozenset[int] = frozenset(),
) -> tuple[list[Diagnosis], dict[int, Assignment]]:
    """Assumption core (optional) + slack relaxation; returns the diagnoses and the maximum
    placement found by the relaxation (empty when it timed out).  Never raises."""
    out: list[Diagnosis] = []
    placed: dict[int, Assignment] = {}
    t0 = time.perf_counter()
    if core:
        try:
            core_diags, cstats = core_diagnosis(prep, budget_s * 0.5)
            prep.stats.update(cstats)
            out.extend(core_diags)
        except Exception as exc:  # noqa: BLE001
            prep.stats["core_error"] = f"{type(exc).__name__}: {exc}"
    remaining = max(1.0, budget_s - (time.perf_counter() - t0))
    try:
        relax, rstats, placed = relaxation_diagnosis(prep, remaining, hints=hints, explained=explained)
        prep.stats.update(rstats)
        out.extend(relax)
    except Exception as exc:  # noqa: BLE001
        prep.stats["relax_error"] = f"{type(exc).__name__}: {exc}"
    if not out:
        out.append(
            Diagnosis(
                [],
                [],
                "CP-SAT proved the instance infeasible but no conflict set could be isolated within the budget",
                ["raise the time limit", "solve a smaller horizon"],
                "error",
                "no_core",
            )
        )
    return out, placed


def diagnose(prep: Prepared, budget_s: float) -> list[Diagnosis]:
    """Full diagnosis after CP-SAT proved INFEASIBLE.  Never raises."""
    return diagnose_with_placement(prep, budget_s)[0]


__all__ = [
    "core_diagnosis",
    "diagnose",
    "diagnose_with_placement",
    "explain_event",
    "explain_unplaced",
    "relaxation_diagnosis",
    "static_check",
]
