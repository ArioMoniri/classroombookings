"""Planner-level validation of a stored run: the persisted ``Assignment`` rows against the raw request rows.

The solver proves "hard 100" for the problem the bridge hands it (``SolverInput``).  The bridge rewrites
the planner's problem on the way (joint lectures merged, fallback sizes for missing enrolments, the
planner's locks trusted, term runs split into week segments), so this module checks the *planner's*
problem directly from the DB, without any ``app.solver`` code (port of the strict review's independent
checker ``check_db.py``):

* every row: the request's day / periods / date, weeks inside the request's weeks, the planner's locked
  room kept (``definitive_rooms="lock"``);
* every room (inside and outside the bookable pool), week, day and period: one class at a time (exams:
  the students of all exams in a room fit its exam seats — one max-flow per period over the rooms used);
* blocks of the grid and confirmed bookings; capacity (sum of the enrolments of the requests seated
  together vs. the seats of their rooms); PC / TIP room tags; one class at a time per cohort (programme +
  class year) and per instructor;
* every request in the run's scope is placed in all of its weeks, or the run names it in an error.

Each finding is either a **violation** or an **accepted exception** with its cause, and an exception
counts only when the run reports it (a diagnosis naming the request):

* ``D1`` — the planner's own room is kept although it is too small / lacks a tag (``trust_locked_rooms``);
* ``D2`` — two requests clash at the times the planner fixed for both (``fixed_conflicts_as_warnings``);
* ``D3`` — a request is not placed (best effort);
* ``week_split`` — a locked request changes room in the weeks its room is blocked;
* ``outside_pool`` — rooms outside the bookable pool (no capacity known) are kept as the planner set them;
* ``manual`` — a planner's manual move / fix-button placement (the row says so, or the bridge reports
  the carried-over lock);
* ``missing_enrolment`` — no enrolment in the data; the bridge used a reported fallback size.

``hard_score`` counts the placed requests with a violation; ``strict_score`` also counts the accepted
exceptions (the score with no waivers).  ``tools/validate_planner.py`` runs this on the real workbooks.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.importers.normalize import non_person_reason
from app.models import (
    Assignment,
    Block,
    ExamRequest,
    Instructor,
    MeetingRequest,
    Room,
    ScheduleRun,
    Section,
    Term,
    Week,
)

#: causes of accepted exceptions and the diagnosis codes that report them (``D3``: any error)
CAUSE_CODES: dict[str, frozenset[str]] = {
    "D1": frozenset({"trusted_lock_capacity", "trusted_lock_tags", "trusted_hint_capacity", "joint_lecture_clipped"}),
    "D2": frozenset({"input_conflict"}),
    "week_split": frozenset({"week_split"}),
    "outside_pool": frozenset({"outside_room_pool", "outside_pool_overlap"}),
    "manual": frozenset({"manual_lock"}),
    "missing_enrolment": frozenset({"missing_enrolment"}),
}
CAUSES: tuple[str, ...] = ("D1", "D2", "D3", "week_split", "outside_pool", "manual", "missing_enrolment")
MANUAL_ORIGINS = frozenset({"MANUAL", "AI_EDIT"})


@dataclass(frozen=True)
class Req:
    """One request (meeting or exam row) in the run's scope, as the planner wrote it."""

    id: int
    label: str
    day: int | None  # fixed day (exams: weekday of the date)
    days: frozenset[int]  # allowed days of a flexible meeting
    start: int
    end: int
    date: date | None
    weeks: frozenset[int]  # the request's weeks inside the run's horizon
    size: int | None  # enrolment (courses: or the requested capacity); None = missing
    locked: bool  # status LOCKED
    definitive: frozenset[int]  # the planner's definitive rooms (all, pooled or not)
    tags: frozenset[str]
    cohort: frozenset[str]
    instructors: frozenset[str]

    @property
    def fixed(self) -> bool:
        return self.day is not None


@dataclass(frozen=True)
class Row:
    """One persisted assignment row."""

    id: int
    req: int
    day: int
    start: int
    end: int
    date: date | None
    weeks: frozenset[int]
    rooms: tuple[int, ...]
    origin: str
    is_locked: bool


@dataclass(frozen=True)
class RoomInfo:
    id: int
    code: str
    seats: int  # lecture capacity (courses) / exam capacity (exams)
    tags: frozenset[str]
    pooled: bool  # inside the solver's room pool (bookable with a capacity)


@dataclass(frozen=True)
class BlockInfo:
    room: int
    week: int | None  # None = every week
    day: int
    start: int
    end: int
    label: str


@dataclass
class CheckData:
    """Everything :func:`check` needs (plain data, no DB)."""

    run_id: int | None
    exam: bool
    reqs: dict[int, Req]
    rows: list[Row]
    rooms: dict[int, RoomInfo]
    blocks: list[BlockInfo]
    #: solver event id -> request ids (joint lectures, exam cohorts); requests not listed are their own event
    members: dict[int, list[int]]
    diagnoses: list[dict[str, Any]]
    #: request id -> fallback size used by the bridge for a missing enrolment
    fallbacks: dict[int, int] = field(default_factory=dict)
    #: request id -> origin of a parent-run lock carried into this run (``manual_lock``)
    carried: dict[int, str] = field(default_factory=dict)
    lock_mode: bool = True  # definitive_rooms == "lock"
    trust: bool = True  # trust_locked_rooms (D1)
    fixed_waiver: bool = True  # fixed_conflicts_as_warnings (D2)


@dataclass
class Finding:
    rule: str
    request_ids: list[int]
    message: str
    #: ``None`` = violation; else the cause of an accepted exception (see :data:`CAUSES`)
    cause: str | None = None
    #: an exception counts only when a diagnosis of the run names it
    reported: bool = False

    @property
    def violation(self) -> bool:
        return self.cause is None or not self.reported

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "request_ids": self.request_ids,
            "message": self.message,
            "cause": self.cause,
            "reported": self.reported,
        }


@dataclass
class PlannerCheck:
    run_id: int | None
    findings: list[Finding]
    requests_total: int
    requests_placed: int  # placed in every week of the run's scope
    rows: int

    @property
    def violations(self) -> list[Finding]:
        """Unwaived findings and exceptions nobody reported."""
        return [f for f in self.findings if f.violation]

    @property
    def exceptions(self) -> list[Finding]:
        return [f for f in self.findings if not f.violation]

    def exceptions_by_cause(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.exceptions:
            assert f.cause is not None
            out[f.cause] = out.get(f.cause, 0) + 1
        return {c: out[c] for c in CAUSES if c in out}

    def _score(self, findings: Iterable[Finding]) -> int:
        bad = {r for f in findings if f.rule not in ("unplaced", "missing_enrolment") for r in f.request_ids}
        placed = max(1, self.requests_placed)
        if not bad:
            return 100
        return max(0, min(99, int(100 * (1 - len(bad) / placed))))

    @property
    def hard_score(self) -> int:
        """100 = no placed request breaks a rule outside the reported exceptions."""
        return self._score(self.violations)

    @property
    def strict_score(self) -> int:
        """The same score with no waivers: every exception counts as a violation."""
        return self._score(self.findings)

    @property
    def placed_pct(self) -> float:
        return round(100.0 * self.requests_placed / max(1, self.requests_total), 1)

    def summary(self) -> dict[str, Any]:
        by_rule: dict[str, int] = {}
        for f in self.violations:
            by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
        return {
            "run_id": self.run_id,
            "rows": self.rows,
            "requests_total": self.requests_total,
            "requests_placed": self.requests_placed,
            "placed_pct": self.placed_pct,
            "hard_score": self.hard_score,
            "strict_score": self.strict_score,
            "violations": len(self.violations),
            "violations_by_rule": by_rule,
            "exceptions_by_cause": self.exceptions_by_cause(),
        }


# --------------------------------------------------------------------------- pure check


def _overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 <= b1 and b0 <= a1


def _max_flow_ok(groups: dict[int, tuple[int, frozenset[int]]], seats: dict[int, int]) -> bool:
    """Can every group seat its students in its rooms (any split over its rooms) within the rooms' seats?
    ``groups``: group -> (size, rooms).  Augmenting paths on the bipartite group -> room network."""
    need = {g: s for g, (s, _r) in groups.items() if s > 0}
    if sum(need.values()) <= 0:
        return True
    left = dict(seats)
    flow: dict[tuple[int, int], int] = defaultdict(int)
    for g in sorted(need):
        while need[g] > 0:
            # BFS from g over residual edges: group -> room (unbounded), room -> group (if flow), room -> sink
            parent: dict[tuple[str, int], tuple[str, int] | None] = {("g", g): None}
            queue: list[tuple[str, int]] = [("g", g)]
            sink: tuple[str, int] | None = None
            while queue and sink is None:
                kind, x = queue.pop(0)
                if kind == "g":
                    for r in sorted(groups[x][1]):
                        if ("r", r) not in parent:
                            parent[("r", r)] = (kind, x)
                            if left.get(r, 0) > 0:
                                sink = ("r", r)
                                break
                            queue.append(("r", r))
                else:
                    for (g2, r2), f in flow.items():
                        if r2 == x and f > 0 and ("g", g2) not in parent:
                            parent[("g", g2)] = (kind, x)
                            queue.append(("g", g2))
            if sink is None:
                return False
            path: list[tuple[str, int]] = []
            node: tuple[str, int] | None = sink
            while node is not None:
                path.append(node)
                node = parent[node]
            path.reverse()  # g ... r(sink)
            amount = min(need[g], left[sink[1]])
            for i in range(len(path) - 1):
                a, b = path[i], path[i + 1]
                if a[0] == "r" and b[0] == "g":
                    amount = min(amount, flow[(b[1], a[1])])
            for i in range(len(path) - 1):
                a, b = path[i], path[i + 1]
                if a[0] == "g":
                    flow[(a[1], b[1])] += amount
                else:
                    flow[(b[1], a[1])] -= amount
            left[sink[1]] -= amount
            need[g] -= amount
    return True


def check(data: CheckData) -> PlannerCheck:
    reqs, rooms = data.reqs, data.rooms
    head_of: dict[int, int] = {m: h for h, ms in data.members.items() for m in ms}

    def head(rid: int) -> int:
        return head_of.get(rid, rid)

    def group(h: int) -> list[int]:
        return data.members.get(h, [h])

    # who reports what: cause -> request ids named by a diagnosis of that cause; error-named requests
    named: dict[str, set[int]] = defaultdict(set)
    errors: set[int] = set()
    pair_diags: list[set[int]] = []
    for d in data.diagnoses:
        ids = [int(i) for i in d.get("event_ids") or [] if str(i).lstrip("-").isdigit()]
        req_ids = {m for i in ids for m in group(i)}
        dcode = str(d.get("code") or "")
        if d.get("severity") == "error":
            errors |= req_ids
        for cz, codes in CAUSE_CODES.items():
            if dcode in codes:
                named[cz] |= req_ids
        if dcode == "input_conflict":
            pair_diags.append(set(ids))
    named["manual"] |= set(data.carried)

    findings: list[Finding] = []

    def add(rule: str, rids: Iterable[int], msg: str, cause: str | None = None, reported: bool | None = None) -> None:
        ids = sorted(set(rids))
        if reported is None:
            reported = cause is not None and all(r in named.get(cause, set()) for r in ids)
        findings.append(Finding(rule, ids, msg, cause, reported))

    def label(rid: int) -> str:
        r = reqs.get(rid)
        return r.label if r else f"#{rid}"

    def code(room: int) -> str:
        info = rooms.get(room)
        return info.code if info else f"#{room}"

    def pooled(rs: Iterable[int]) -> list[int]:
        return [r for r in rs if r in rooms and rooms[r].pooled]

    rows = [a for a in data.rows if a.req in reqs]
    manual_rows = {a.id for a in rows if a.origin in MANUAL_ORIGINS}
    by_req: dict[int, list[Row]] = defaultdict(list)
    for a in rows:
        by_req[a.req].append(a)

    def manual(a: Row) -> bool:
        return a.id in manual_rows or a.req in data.carried

    def manual_cause(a: Row) -> tuple[str | None, bool | None]:
        if a.id in manual_rows:
            return "manual", True  # the row itself records the planner's edit
        if a.req in data.carried:
            return "manual", None
        return None, None

    # ---- missing enrolments: every one must carry a reported fallback size
    for rid, r in sorted(reqs.items()):
        if r.size is None:
            fb = data.fallbacks.get(rid)
            add(
                "missing_enrolment",
                [rid],
                f"{r.label}: no enrolment in the data"
                + (f"; checked with the fallback size {fb}" if fb else "; no fallback size reported"),
                "missing_enrolment" if fb else None,
            )

    def size_of(rid: int) -> int:
        r = reqs[rid]
        return r.size if r.size is not None else data.fallbacks.get(rid, 0)

    # ---- per row: time, weeks, the planner's lock
    for a in rows:
        r = reqs[a.req]
        if not a.weeks:
            add("weeks", [a.req], f"{r.label}: assignment row without weeks")
        if not a.weeks <= r.weeks:
            add("weeks", [a.req], f"{r.label}: weeks {sorted(a.weeks)} outside its weeks {sorted(r.weeks)}")
        if data.exam:
            wrong = a.date != r.date or (a.start, a.end) != (r.start, r.end)
        elif r.fixed:
            wrong = (a.day, a.start, a.end) != (r.day, r.start, r.end)
        else:
            wrong = a.day not in r.days or a.end - a.start != r.end - r.start
        if wrong:
            why, rep = manual_cause(a)
            add(
                "time",
                [a.req],
                f"{r.label}: requested {r.date or r.day} P{r.start}-P{r.end}, placed {a.date or a.day} "
                f"P{a.start}-P{a.end}",
                why,
                rep,
            )
        planner_pooled = frozenset(pooled(r.definitive))
        if data.lock_mode and r.locked and planner_pooled and r.fixed and frozenset(pooled(a.rooms)) != planner_pooled:
            why, rep = manual_cause(a)
            add(
                "locked_room",
                [a.req],
                f"{r.label}: locked to {', '.join(code(x) for x in sorted(planner_pooled))}, placed in "
                f"{', '.join(code(x) for x in a.rooms) or 'no room'} in week(s) {sorted(a.weeks)}",
                why or "week_split",
                rep,
            )

    # ---- occupancy of every room (pooled or not) per (room, week, day, period)
    occ: dict[tuple[int, int, int, int], list[Row]] = defaultdict(list)
    for a in rows:
        for room in dict.fromkeys(a.rooms):
            for w in a.weeks:
                for p in range(a.start, a.end + 1):
                    occ[(room, w, a.day, p)].append(a)
    seen_pairs: set[tuple[int, tuple[int, ...]]] = set()
    if not data.exam:
        for (room, w, day, p), items in sorted(occ.items()):
            heads = sorted({head(a.req) for a in items})
            if len(heads) < 2:
                continue
            pkey = (room, tuple(heads))
            if pkey in seen_pairs:
                continue
            seen_pairs.add(pkey)
            rids = sorted({a.req for a in items})
            msg = f"{code(room)} week {w} day {day} P{p}: {', '.join(label(x) for x in rids)}"
            if room in rooms and rooms[room].pooled:
                add("room_double_booking", rids, msg)
            else:
                add("room_double_booking", rids, msg + " (room outside the pool)", "outside_pool")

    # ---- blocks (grid cells, confirmed bookings)
    blocks_by_room: dict[int, list[BlockInfo]] = defaultdict(list)
    for blk in data.blocks:
        blocks_by_room[blk.room].append(blk)
    seen_blocks: set[tuple[int, int]] = set()
    for a in rows:
        for room in dict.fromkeys(a.rooms):
            for blk in blocks_by_room.get(room, []):
                if blk.day != a.day or not _overlap(a.start, a.end, blk.start, blk.end):
                    continue
                hit = sorted(a.weeks if blk.week is None else a.weeks & {blk.week})
                if not hit or (a.id, room) in seen_blocks:
                    continue
                seen_blocks.add((a.id, room))
                msg = (
                    f"{label(a.req)} in {code(room)} week(s) {hit} day {a.day} P{a.start}-P{a.end} "
                    f"vs block '{blk.label}'"
                )
                if room in rooms and rooms[room].pooled:
                    why, rep = manual_cause(a)
                    add("blocked", [a.req], msg, why, rep)
                else:
                    add("blocked", [a.req], msg + " (room outside the pool)", "outside_pool")

    # ---- capacity and seats
    def trusted_rooms(group_ids: list[int], used: frozenset[int]) -> bool:
        """The group sits exactly in its planner's (LOCKED, definitive) pooled rooms."""
        if not data.trust:
            return False
        locked = [m for m in group_ids if m in reqs and reqs[m].locked]
        if not locked or (not data.exam and len(locked) != len(group_ids)):
            return False
        planner = frozenset(x for m in locked for x in pooled(reqs[m].definitive))
        return bool(planner) and used == planner

    if data.exam:
        # every (week, day, period): the exams sitting in pooled rooms must fit the rooms' exam seats
        cells: dict[tuple[int, int, int], dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        cell_members: dict[tuple[int, int, int], dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        for a in rows:
            prs = pooled(a.rooms)
            if not prs:
                continue
            for w in a.weeks:
                for p in range(a.start, a.end + 1):
                    cells[(w, a.day, p)][head(a.req)].update(prs)
                    cell_members[(w, a.day, p)][head(a.req)].add(a.req)
        seen_sets: set[tuple[int, ...]] = set()
        seen_trusted: set[tuple[int, frozenset[int]]] = set()
        for cell, by_head in sorted(cells.items()):
            # connected components over shared rooms
            comps: list[set[int]] = []
            for h, rs in sorted(by_head.items()):
                touching = {i for i, c in enumerate(comps) if any(rs & by_head[x] for x in c)}
                merged = {h}.union(*(comps[i] for i in touching)) if touching else {h}
                comps = [c for i, c in enumerate(comps) if i not in touching] + [merged]
            for comp in comps:
                groups: dict[int, tuple[int, frozenset[int]]] = {}
                for h in sorted(comp):
                    need_h = sum(size_of(m) for m in cell_members[cell][h])
                    rooms_h = frozenset(by_head[h])
                    seats_h = sum(rooms[r].seats for r in rooms_h)
                    if need_h > seats_h and trusted_rooms(group(h), rooms_h):
                        # the planner's own (too small) rooms: the group fills them (D1, reported by the run),
                        # like the solver's seat target min(size, seats); the others must still fit
                        ckey_h = (h, rooms_h)
                        if ckey_h not in seen_trusted:
                            seen_trusted.add(ckey_h)
                            rids_h = sorted(cell_members[cell][h])
                            add(
                                "capacity",
                                rids_h,
                                f"{', '.join(label(x) for x in rids_h[:4])}: {need_h} students in the planner's "
                                f"{', '.join(code(r) for r in sorted(rooms_h))} ({seats_h} exam seats)",
                                "D1",
                            )
                        need_h = seats_h
                    groups[h] = (need_h, rooms_h)
                used_rooms = set().union(*(rs for _s, rs in groups.values()))
                room_seats = {r: rooms[r].seats for r in used_rooms}
                if _max_flow_ok(groups, room_seats):
                    continue
                ckey = tuple(sorted(comp))
                if ckey in seen_sets:
                    continue
                seen_sets.add(ckey)
                rids = sorted({m for h in comp for m in cell_members[cell][h]})
                need = sum(s for s, _r in groups.values())
                msg = (
                    f"{', '.join(code(r) for r in sorted(used_rooms))} week {cell[0]} day {cell[1]} P{cell[2]}: "
                    f"{need} students for {sum(room_seats.values())} exam seats "
                    f"({', '.join(label(x) for x in rids[:6])})"
                )
                ok = all(trusted_rooms(group(h), frozenset(groups[h][1])) for h in comp)
                add("capacity", rids, msg, "D1" if ok else None)
    else:
        seen_cap: set[tuple[int, frozenset[int], frozenset[int]]] = set()
        present: dict[tuple[int, int, int, int], list[Row]] = defaultdict(list)
        for a in rows:
            for w in a.weeks:
                for p in range(a.start, a.end + 1):
                    present[(head(a.req), w, a.day, p)].append(a)
        for (h, w, _day, _p), items in present.items():
            present_ids = frozenset(a.req for a in items)
            used = frozenset(x for a in items for x in pooled(a.rooms))
            if not used or (h, present_ids, used) in seen_cap:
                continue
            seen_cap.add((h, present_ids, used))
            need = sum(size_of(m) for m in present_ids)
            seats = sum(rooms[x].seats for x in used)
            if need <= seats:
                continue
            msg = (
                f"{' + '.join(label(m) for m in sorted(present_ids))}: {need} students in "
                f"{', '.join(code(x) for x in sorted(used))} ({seats} seats), week {w}"
            )
            if trusted_rooms(sorted(present_ids), used):
                add("capacity", sorted(present_ids), msg, "D1")
            else:
                ca, rep = next((manual_cause(a) for a in items if manual(a)), (None, None))
                add("capacity", sorted(present_ids), msg, ca, rep)

    # ---- room tags (PC required, TIP rooms only for TIP requests or the planner's own TIP room)
    seen_tags: set[tuple[int, int, str]] = set()
    for a in rows:
        h = head(a.req)
        group_ids = [m for m in group(h) if m in reqs]
        wants: frozenset[str] = frozenset().union(*(reqs[m].tags for m in group_ids)) if group_ids else frozenset()
        planner = frozenset(x for m in group_ids if reqs[m].locked for x in reqs[m].definitive)
        for room in a.rooms:
            info = rooms.get(room)
            if info is None:
                continue
            if "PC" in wants and "PC" not in info.tags and (h, room, "PC") not in seen_tags:
                seen_tags.add((h, room, "PC"))
                if data.trust and room in planner:
                    add("tags", [a.req], f"{label(a.req)} needs a PC room, placed in {info.code}", "D1")
                else:
                    ca, rep = manual_cause(a)
                    add("tags", [a.req], f"{label(a.req)} needs a PC room, placed in {info.code}", ca, rep)
            if "TIP" in info.tags and "TIP" not in wants and room not in planner and (h, room, "TIP") not in seen_tags:
                seen_tags.add((h, room, "TIP"))
                why, rep = manual_cause(a)
                add("tags", [a.req], f"{label(a.req)} placed in the medicine (TIP) room {info.code}", why, rep)

    # ---- one class at a time per cohort and per instructor
    by_key: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for a in rows:
        r = reqs[a.req]
        for k in r.cohort:
            by_key[("cohort", k)].append(a)
        for k in r.instructors:
            by_key[("instructor", k)].append(a)
    seen_keys: set[tuple[str, int, int]] = set()
    for (kind, k), items in sorted(by_key.items()):
        if len(items) < 2:
            continue
        items.sort(key=lambda x: (x.day, x.start, x.id))
        for a, b in combinations(items, 2):
            ha, hb = head(a.req), head(b.req)
            if ha == hb or a.day != b.day or not _overlap(a.start, a.end, b.start, b.end):
                continue
            if data.exam and a.date != b.date:
                continue
            if not a.weeks & b.weeks:
                continue
            pk = (kind, min(ha, hb), max(ha, hb))
            if pk in seen_keys:
                continue
            seen_keys.add(pk)
            ra, rb = reqs[a.req], reqs[b.req]
            at_fixed = all(
                r.fixed and (x.day, x.start, x.end) == (r.day, r.start, r.end) and (not data.exam or x.date == r.date)
                for x, r in ((a, ra), (b, rb))
            )
            msg = (
                f"{kind} '{k}': {ra.label} day {a.day} P{a.start}-P{a.end} vs {rb.label} day {b.day} "
                f"P{b.start}-P{b.end}"
            )
            if at_fixed and data.fixed_waiver and not (manual(a) or manual(b)):
                rep = any({ha, hb} <= ids for ids in pair_diags)
                add(kind, [a.req, b.req], msg, "D2", rep)
            else:
                add(kind, [a.req, b.req], msg)

    # ---- placement: every request in all of its weeks, or named by an error of the run
    placed = 0
    for rid, r in sorted(reqs.items()):
        covered: set[int] = set()
        for a in by_req.get(rid, []):
            covered |= a.weeks
        missing = r.weeks - covered
        if not missing:
            placed += 1
            continue
        what = "not placed" if not covered else f"not placed in week(s) {sorted(missing)}"
        add("unplaced", [rid], f"{r.label}: {what}", "D3", rid in errors)

    return PlannerCheck(data.run_id, findings, len(reqs), placed, len(rows))


# --------------------------------------------------------------------------- loading from the DB


def _weeks_of(a: Assignment) -> frozenset[int]:
    ws = [int(w) for w in (a.weeks or []) if w is not None]
    if not ws and a.week is not None:
        ws = [int(a.week)]
    return frozenset(ws)


def _int_ids(values: Iterable[Any] | None) -> frozenset[int]:
    out: set[int] = set()
    for v in values or []:
        try:
            out.add(int(v))
        except (TypeError, ValueError):
            continue
    return frozenset(out)


def _cohorts(program: str | None, years: Iterable[Any]) -> frozenset[str]:
    if not program:
        return frozenset()
    out = set()
    for y in years:
        try:
            yi = int(y)
        except (TypeError, ValueError):
            continue
        if yi > 0:
            out.add(f"{program}:Y{yi}")
    return frozenset(out)


async def load(session: AsyncSession, run: ScheduleRun, assignments: list[Assignment] | None = None) -> CheckData:
    """The run's rows, the requests in its scope (the bridge's filters), rooms, blocks and diagnoses."""
    from app.services.bookings_solver import booking_blocks
    from app.services.calendar import week_index_for_date
    from app.services.solver_bridge import horizon_weeks, run_mode

    term = await session.get(Term, run.term_id)
    assert term is not None
    weeks_rows = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
    horizon = horizon_weeks(run, term)
    week_set = set(horizon)
    params = run.params or {}
    exam = run.kind == "EXAM"
    room_rows = list((await session.execute(select(Room))).scalars())
    rooms = {
        r.id: RoomInfo(
            r.id,
            r.code,
            int((r.exam_capacity if exam else r.capacity) or 0),
            frozenset(str(t) for t in (r.tags or [])),
            bool(r.is_bookable) and bool((r.exam_capacity or r.capacity) if exam else r.capacity),
        )
        for r in room_rows
    }
    reqs: dict[int, Req] = {}
    if exam:
        q = (
            select(ExamRequest)
            .where(ExamRequest.term_id == term.id, ExamRequest.archived.is_(False), ExamRequest.needs_room.is_(True))
            .options(selectinload(ExamRequest.program))
        )
        for ex in (await session.execute(q)).scalars():
            if ex.date is None or ex.start_period is None or ex.end_period is None:
                continue
            week = week_index_for_date(term, ex.date, weeks_rows)
            if week is None:
                week = horizon[0]
            if week not in week_set and run.horizon != "TERM" and params.get("strict_horizon", True):
                continue
            prog = ex.program.canonical_name if ex.program else None
            reqs[ex.id] = Req(
                id=ex.id,
                label=ex.course_code,
                day=ex.date.isoweekday(),
                days=frozenset({ex.date.isoweekday()}),
                start=ex.start_period,
                end=ex.end_period,
                date=ex.date,
                weeks=frozenset({week}),
                size=int(ex.enrolment) if ex.enrolment else None,
                locked=ex.status == "LOCKED",
                definitive=_int_ids(ex.definitive_room_ids),
                tags=frozenset(str(t) for t in ex.requested_tags or []),
                cohort=_cohorts(prog, ex.class_years or [ex.class_year]),
                # a value that names no person ("UZEM", a department) is no instructor (the bridge drops it too)
                instructors=frozenset({ex.instructor_text})
                if ex.instructor_text and non_person_reason(ex.instructor_text) is None
                else frozenset(),
            )
    else:
        not_person = {
            int(i)
            for i, name in (await session.execute(select(Instructor.id, Instructor.full_name))).all()
            if non_person_reason(name) is not None
        }
        qm = (
            select(MeetingRequest)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == term.id, MeetingRequest.archived.is_(False), MeetingRequest.needs_room.is_(True))
            .options(
                selectinload(MeetingRequest.section).selectinload(Section.course),
                selectinload(MeetingRequest.section).selectinload(Section.program),
                selectinload(MeetingRequest.section).selectinload(Section.instructors),
            )
        )
        for mr in (await session.execute(qm)).scalars():
            if mr.start_period is None or mr.end_period is None:
                continue
            weeks = frozenset(int(w) for w in (mr.weeks or horizon) if int(w) in week_set)
            if not weeks:
                continue
            sec = mr.section
            days = [int(d) for d in (mr.days or [])] or ([mr.day] if mr.day else [])
            day = mr.day if mr.day else (days[0] if len(days) == 1 else None)
            size = int(sec.enrolment or mr.requested_capacity or 0)
            prog = sec.program.canonical_name if sec.program else None
            reqs[mr.id] = Req(
                id=mr.id,
                label=f"{sec.course.display_code}{' §' + sec.label if sec.label else ''}",
                day=day,
                days=frozenset(days or [1, 2, 3, 4, 5]),
                start=mr.start_period,
                end=mr.end_period,
                date=None,
                weeks=weeks,
                size=size or None,
                locked=mr.status == "LOCKED",
                definitive=_int_ids(mr.definitive_room_ids),
                tags=frozenset(str(t) for t in mr.requested_tags or []),
                cohort=_cohorts(prog, sec.class_years or [sec.class_year]),
                instructors=frozenset(
                    str(si.instructor_id) for si in sec.instructors if si.instructor_id not in not_person
                ),
            )
    if assignments is None:
        assignments = list(
            (
                await session.execute(
                    select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
                )
            ).scalars()
        )
    rows = []
    for a in assignments:
        if a.archived:
            continue
        rid = a.exam_request_id if exam else a.meeting_request_id
        if rid is None:
            continue
        rows.append(
            Row(
                id=int(a.id or 0),
                req=int(rid),
                day=int(a.day),
                start=int(a.start_period),
                end=int(a.end_period),
                date=a.date,
                weeks=_weeks_of(a),
                rooms=tuple(int(x) for x in a.room_ids or []),
                origin=str(a.origin or "SOLVER"),
                is_locked=bool(a.is_locked),
            )
        )
    blocks: list[BlockInfo] = []
    for b in (
        await session.execute(select(Block).where(Block.term_id == term.id, Block.archived.is_(False)))
    ).scalars():
        day = b.day or (b.date.isoweekday() if b.date else None)
        if day is None:
            continue
        bweeks: list[int | None] = [int(x) for x in b.weeks or []] or [None]
        for w in bweeks:
            if w is None or w in week_set:
                blocks.append(BlockInfo(b.room_id, w, day, b.start_period, b.end_period, b.label))
    for sb in await booking_blocks(session, term, weeks_rows, week_set):
        blocks.append(BlockInfo(sb.room_id, sb.week, sb.day, sb.start, sb.end, "booking"))
    stats = run.stats or {}
    members = {int(k): [int(x) for x in v] for k, v in (stats.get("event_members") or {}).items()}
    fallbacks = {int(k): int(v.get("size", 0)) for k, v in (stats.get("enrolment_fallbacks") or {}).items()}
    carried = {int(k): str(v) for k, v in (stats.get("carried_locks") or {}).items()}
    return CheckData(
        run_id=run.id,
        exam=exam,
        reqs=reqs,
        rows=rows,
        rooms=rooms,
        blocks=blocks,
        members=members,
        diagnoses=[d for d in (run.diagnosis or []) if isinstance(d, dict)],
        fallbacks=fallbacks,
        carried=carried,
        lock_mode=run_mode(params, "definitive_rooms") == "lock",
        trust=bool(run_mode(params, "trust_locked_rooms")),
        fixed_waiver=bool(run_mode(params, "fixed_conflicts_as_warnings")),
    )


async def check_run(
    session: AsyncSession, run: ScheduleRun, assignments: list[Assignment] | None = None
) -> PlannerCheck:
    """Planner-level check of ``run`` (optionally of an edited set of its rows)."""
    return check(await load(session, run, assignments))


__all__ = [
    "CAUSES",
    "CheckData",
    "Finding",
    "PlannerCheck",
    "Req",
    "Row",
    "check",
    "check_run",
    "load",
]
