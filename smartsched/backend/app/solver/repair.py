"""LNS-style repair and CP-SAT-independent validation.

* :func:`repair` — after a chat/manual edit or a moderation edit: keep every assignment except the changed events'
  neighbours (events that share a room slot, a cohort key or an instructor key at an overlapping time), re-solve
  the small residual model with the stability objective and hints.  The repair works on **week segments**
  (:mod:`app.solver.weeksplit`): a term run keeps a class in its room in the weeks that room is free and moves
  only the blocked weeks, so its stored placement has several rows; the repair reads them as the segments they
  are instead of flattening them to one room (round-2 T-R2-34: that flattening freed 16 planner-locked classes
  and dropped 17 of them on the Güz term).
* :func:`segment_view` / :func:`violating_events` — the segmented picture of a stored timetable and the segments
  whose published cell breaks a hard rule under the current rules (a booking or block added since, a draft rule).
* :func:`minimal_change` — a placed event outside the edit's scope goes back to its published cell when that cell
  (alone, or together with the chain of moved events that took it) still keeps every hard rule.
* :func:`validate` — pure-Python check of every hard rule (and the soft score) over any set of
  assignments; used by the API after AI/manual edits.  Same objective definitions as the solver.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from app.solver.cpsat import solve
from app.solver.domains import TimeOption, normalize_input, weeks_intersect
from app.solver.evaluate import Violation, index_assignments
from app.solver.model import Assignment, Event, SolverInput, SolverResult
from app.solver.scoring import evaluate
from app.solver.weeksplit import WeekSplit, split_blocked_weeks, split_by_rows, to_original

#: largest chain of moved events :func:`minimal_change` puts back together (a swap cycle is 2; the Güz room
#: rotations of a re-solve were 3-4 long)
MAX_REVERT_CLUSTER = 8


def _touches(a: Assignment, ea: Event, b: Assignment, eb: Event) -> bool:
    ta = TimeOption(a.day, a.start, a.end - a.start + 1)
    tb = TimeOption(b.day, b.start, b.end - b.start + 1)
    if not ta.overlaps(tb) or not weeks_intersect(ea.weeks, eb.weeks):
        return False
    return bool(
        set(a.room_ids) & set(b.room_ids) or ea.cohort_keys & eb.cohort_keys or ea.instructor_keys & eb.instructor_keys
    )


def neighbourhood(
    inp: SolverInput, assignments: Iterable[Assignment], seeds: Iterable[int], radius: int = 1
) -> dict[int, int | None]:
    """Events within ``radius`` conflict hops of the seed events -> the seed they were reached from (``None`` for
    a seed itself).  Deterministic: seeds and candidates are visited in id order."""
    by_id = index_assignments(list(assignments))
    events = {e.id: e for e in inp.events}
    frontier = sorted({s for s in seeds if s in events})
    reached: dict[int, int | None] = dict.fromkeys(frontier)
    for _ in range(max(0, radius)):
        nxt: dict[int, int] = {}
        for s in frontier:
            a = by_id.get(s)
            if a is None:
                continue
            origin = reached.get(s)
            seed = s if origin is None else origin
            for other_id in sorted(by_id):
                if other_id in reached or other_id in nxt or other_id not in events:
                    continue
                if _touches(a, events[s], by_id[other_id], events[other_id]):
                    nxt[other_id] = seed
        reached.update(nxt)
        frontier = sorted(nxt)
    return reached


def neighbours(inp: SolverInput, assignments: Iterable[Assignment], seeds: Iterable[int], radius: int = 1) -> set[int]:
    """Events within ``radius`` conflict hops of the seed events (seeds included)."""
    return set(neighbourhood(inp, assignments, seeds, radius))


# ------------------------------------------------------------------------------------------------ week segments


@dataclass
class SegmentView:
    """A stored timetable read as week segments: ``split.inp`` is the segmented input (its ``previous`` = ``current``),
    ``current`` holds one assignment per placed segment event (segment ids; ``split.origin_of`` maps them back)."""

    split: WeekSplit
    current: list[Assignment]

    @property
    def inp(self) -> SolverInput:
        return self.split.inp

    def root_of(self, event_id: int) -> int:
        return self.split.origin_of(event_id)

    def segments_of(self, root: int) -> list[int]:
        return list(self.split.segments.get(root, [root]))

    def roots(self, ids: Iterable[int]) -> set[int]:
        return {self.root_of(int(i)) for i in ids}

    def expand(self, ids: Iterable[int]) -> set[int]:
        """Original event ids -> all their segment ids; a segment id (or an unknown id) passes through."""
        out: set[int] = set()
        for i in ids:
            i = int(i)
            out.update(self.split.segments.get(i, [i]))
        return out


def _rows_by_event(inp: SolverInput, assignments: Iterable[Assignment]) -> dict[int, list[Assignment]]:
    known = {e.id for e in inp.events}
    out: dict[int, list[Assignment]] = defaultdict(list)
    for a in assignments:
        if a.event_id in known and a not in out[a.event_id]:
            out[a.event_id].append(a)
    return out


def _segment_rows(split: WeekSplit, rows_by_root: dict[int, list[Assignment]]) -> list[Assignment]:
    """One assignment per segment event: the stored row covering most of the segment's weeks, re-keyed to it."""
    out: list[Assignment] = []
    for e in split.inp.events:
        rows = rows_by_root.get(split.origin_of(e.id))
        if not rows:
            continue
        best = max(rows, key=lambda a: (len(a.weeks & e.weeks) if a.weeks else len(e.weeks), -rows.index(a)))
        if best.weeks and not best.weeks & e.weeks:
            continue  # the stored row covers none of this segment's weeks: the segment is not placed
        out.append(Assignment(e.id, best.day, best.start, best.end, best.room_ids, e.weeks, best.date))
    return out


def segment_view(
    inp: SolverInput,
    assignments: Iterable[Assignment],
    *,
    split_weeks: bool = True,
    unlocked_forbidden_tags: Mapping[int, frozenset[str]] | None = None,
) -> SegmentView:
    """The segmented picture of ``assignments`` (several rows per event allowed: one per room set and week range).

    The input is split like the term run splits it (locked rooms blocked in some weeks, fixed-time events with no
    common free room; ``unlocked_forbidden_tags`` = the tags an event may not use without its lock, as the bridge
    passes them to ``solve_segmented`` — a locked class's moved week never lands in a medicine room); an event whose
    stored rows change room between weeks without such a split is split along those rows
    (:func:`weeksplit.split_by_rows`).  Every segment then has exactly one current placement."""
    current = list(assignments)
    rows_by_root = _rows_by_event(inp, current)
    base = replace(inp, previous=tuple(a for rows in rows_by_root.values() for a in rows))
    split = (
        split_blocked_weeks(base, unlocked_forbidden_tags=unlocked_forbidden_tags)
        if split_weeks
        else WeekSplit(inp=normalize_input(base))
    )
    if split_weeks:
        multi = {
            root: rows
            for root, rows in rows_by_root.items()
            if len({(a.day, a.start, a.end, tuple(sorted(a.room_ids))) for a in rows}) > 1
        }
        if multi:
            split = split_by_rows(split, multi)
    seg_current = _segment_rows(split, rows_by_root)
    split = replace(split, inp=replace(split.inp, previous=tuple(seg_current)))
    return SegmentView(split, seg_current)


def violating_events(view: SegmentView) -> set[int]:
    """Segments of the stored timetable whose cell breaks a hard rule under ``view.inp``'s rules now (a booking or a
    block added since, a rule written on the draft, a request edited).  Judged segment by segment: a locked class
    whose blocked week sits in another room is not a violation."""
    placed = {a.event_id for a in view.current}
    sub = replace(view.inp, events=tuple(e for e in view.inp.events if e.id in placed), best_effort=False)
    return {int(i) for v in evaluate(sub, view.current).violations if v.hard for i in v.event_ids}


# ------------------------------------------------------------------------------------------------------ repair


def repair(
    inp: SolverInput,
    assignments: Iterable[Assignment],
    changed_event_ids: Iterable[int],
    time_limit_s: float = 5.0,
    *,
    keep_changed: bool = True,
    radius: int = 1,
    scope: Iterable[int] | None = None,
    free: Iterable[int] | Mapping[int, int | None] | None = None,
    view: SegmentView | None = None,
    split_weeks: bool = True,
    unlocked_forbidden_tags: Mapping[int, frozenset[str]] | None = None,
) -> SolverResult:
    """Re-solve only the neighbourhood of the changed events.

    ``keep_changed=True`` (chat-edit flow): the changed events are locked to their edited
    assignment (that *is* the user's intent) and their neighbours are freed; ``False``: the changed
    events are freed too.  Every other event is locked to its current assignment, so the residual
    model is tiny and the stability objective keeps the freed events where they were if possible.
    If the edit is impossible the result is INFEASIBLE with a diagnosis — never a silent relaxation.

    ``free``: further events (or segments) to free, e.g. those whose published cell breaks a rule now
    (:func:`violating_events`); they seed the neighbourhood too.  As a mapping, the value names the changed event
    an entry is freed for (it holds the cell that event asks for; ``None`` = its own cell breaks a rule now).
    ``scope``: the requests the user edited —
    after the solve every moved or dropped event outside it goes back to its published cell when that keeps every
    hard rule (:func:`minimal_change`).  ``view``: a prepared :func:`segment_view` (else built here).

    ``stats["repair"]``: ``changed`` / ``freed`` (original event ids), ``freed_by`` (why each freed event outside
    the changed set was freed: ``{"cause": "neighbour", "of": <seed>}`` or ``{"cause": "base_conflict"}``),
    ``moved`` (:func:`moved_diff`), ``dropped``, ``reverted``, ``hard_violations``; with ``inp.workers == 1`` the
    solve runs in deterministic time, so the same input gives the same child.
    """
    current = list(assignments)
    if view is None:
        view = segment_view(inp, current, split_weeks=split_weeks, unlocked_forbidden_tags=unlocked_forbidden_tags)
    sinp = view.inp
    seg_cur = index_assignments(view.current)
    changed = view.expand(int(i) for i in changed_event_ids)
    free_for: dict[int, int | None] = dict(free.items()) if isinstance(free, Mapping) else dict.fromkeys(free or ())
    extra = view.expand(free_for) - changed
    reached = neighbourhood(sinp, view.current, changed | extra, radius)
    free_set = set(reached)
    if keep_changed:
        free_set -= changed
    else:
        free_set |= changed
    events: list[Event] = []
    for e in sinp.events:
        if e.id in free_set:
            events.append(e)  # keeps an original lock if the event had one
        elif e.id in seg_cur and (e.locked is None or e.id in changed):
            events.append(replace(e, locked=seg_cur[e.id]))
        else:
            events.append(e)
    new_inp = replace(sinp, events=tuple(events), previous=tuple(view.current), time_limit_s=time_limit_s)
    result = solve(new_inp)
    reverted: list[int] = []
    if scope is not None and result.assignments and result.status != "ERROR":
        reverted = minimal_change(view, result, scope)
    hard_violations = _hard_count(new_inp, result.assignments)
    freed_by: dict[int, dict[str, Any]] = {}
    for seg in sorted(reached):
        if seg in changed:
            continue
        root = view.root_of(seg)
        if root in freed_by:
            continue
        seed = reached[seg]
        if seg in extra:
            held_for = free_for.get(seg, free_for.get(root))
            if held_for is None:
                freed_by[root] = {"cause": "base_conflict"}
            else:
                freed_by[root] = {"cause": "neighbour", "of": view.root_of(int(held_for))}
        elif seed is not None:
            freed_by[root] = {"cause": "neighbour", "of": view.root_of(seed)}
    final = to_original(view.split, result)
    moved = moved_diff(current, final.assignments)
    final.stats["repair"] = {
        "changed": sorted(view.roots(changed)),
        "freed": sorted(view.roots(free_set)),
        "freed_by": freed_by,
        "locked": sum(1 for e in events if e.locked is not None),
        "radius": radius,
        "keep_changed": keep_changed,
        # P19-S2: what the repair moved, event by event (the changed events' own edit included)
        "moved": moved,
        "moved_count": sum(1 for m in moved if m["to"] is not None and m["from"] is not None),
        "dropped": [m["event_id"] for m in moved if m["to"] is None],
        "reverted": reverted,
        "segments": len([i for i in sinp.events if view.root_of(i.id) != i.id]),
        # the solver re-evaluated the result (cpsat.solve): a traded hard rule is an ``internal`` error there
        "hard_violations": hard_violations,
    }
    return final


def _hard_count(inp: SolverInput, assignments: list[Assignment]) -> int:
    """Hard violations of the placed events (a partial result's unplaced events are reported separately)."""
    placed = {a.event_id for a in assignments}
    sub = replace(inp, events=tuple(e for e in inp.events if e.id in placed), best_effort=False)
    return sum(1 for v in validate(sub, assignments) if v.hard)


def _cluster(
    start: int,
    before: dict[int, Assignment],
    after: dict[int, Assignment],
    events: dict[int, Event],
    blocked: set[int],
) -> set[int] | None:
    """The moved events that would have to go back together with ``start``: those whose new cell takes ``start``'s
    old cell, transitively.  ``None`` when the chain reaches an event that cannot go back (in scope, newly placed,
    not moved) or grows past :data:`MAX_REVERT_CLUSTER`."""
    cluster = {start}
    frontier = [start]
    while frontier:
        x = frontier.pop(0)
        old = before[x]
        for y in sorted(after):
            if y in cluster or y == x:
                continue
            if not _touches(old, events[x], after[y], events[y]):
                continue
            if y in blocked or y not in before or after[y] == before[y]:
                return None
            cluster.add(y)
            frontier.append(y)
            if len(cluster) > MAX_REVERT_CLUSTER:
                return None
    return cluster


def minimal_change(view: SegmentView, result: SolverResult, scope: Iterable[int]) -> list[int]:
    """Academician needs Q9: a published class outside the changed requests keeps its cell unless moving it was
    needed.  Every moved or dropped segment outside ``scope`` whose old cell is still free (reverting it keeps every
    hard rule) is put back; then every chain of moved segments that took each other's old cells (a swap, a room
    rotation) is put back as a whole when that keeps every hard rule.  Deterministic (sorted order, repeated until
    nothing changes).  Returns the reverted original event ids and rewrites ``result`` in place (assignments,
    scores, placement stats and the diagnoses of the classes placed again)."""
    sinp = view.inp
    events = {e.id: e for e in sinp.events}
    before = index_assignments(view.current)
    after = index_assignments(result.assignments)
    scope_ids = view.expand(int(i) for i in scope)
    viol0 = _hard_count(sinp, list(after.values()))
    reverted: list[int] = []

    def candidates() -> list[int]:
        return [
            eid
            for eid in sorted(before)
            if eid not in scope_ids and eid not in reverted and after.get(eid) != before[eid]
        ]

    changed = True
    while changed:
        changed = False
        for eid in candidates():
            trial = dict(after)
            trial[eid] = before[eid]
            if _hard_count(sinp, list(trial.values())) <= viol0:
                after = trial
                reverted.append(eid)
                changed = True
    changed = True
    while changed:
        changed = False
        for eid in candidates():
            cluster = _cluster(eid, before, after, events, scope_ids | set(reverted))
            if cluster is None or len(cluster) < 2:
                continue
            trial = dict(after)
            for x in cluster:
                trial[x] = before[x]
            if _hard_count(sinp, list(trial.values())) <= viol0:
                after = trial
                reverted.extend(sorted(cluster))
                changed = True
    if not reverted:
        return []
    final = [after[k] for k in sorted(after)]
    hard, soft, breakdown = score(
        replace(sinp, events=tuple(e for e in sinp.events if e.id in after), best_effort=False), final
    )
    restored = {eid for eid in reverted if eid not in {a.event_id for a in result.assignments}}
    if restored:
        # classes put back in their published cell are placed again: their "cannot be placed" lines go
        result.diagnoses = [
            d
            for d in result.diagnoses
            if not (len(d.event_ids) == 1 and d.event_ids[0] in restored and d.severity == "error")
        ]
        for d in result.diagnoses:
            if d.code == "unplaced_summary":
                d.event_ids = [i for i in d.event_ids if i not in restored]
        total = int(result.stats.get("events_total") or len(sinp.events))
        result.stats["placed"] = len(final)
        result.stats["unplaced"] = max(0, total - len(final))
        if isinstance(result.stats.get("unplaced_ids"), list):
            result.stats["unplaced_ids"] = [i for i in result.stats["unplaced_ids"] if i not in restored]
        result.stats["restored_to_published"] = sorted(view.roots(restored))
    result.assignments = final
    result.hard_score, result.soft_score = hard, soft
    result.objective_breakdown = breakdown
    return sorted(view.roots(reverted))


# ------------------------------------------------------------------------------- the published timetable is kept


def _rows_clash(a: Assignment, ea: Event, b: Assignment, eb: Event) -> bool:
    """Two placement rows compete: overlapping time in a shared week and a shared room, cohort or instructor."""
    if a.day != b.day or a.start > b.end or b.start > a.end:
        return False
    if not (a.weeks or ea.weeks) & (b.weeks or eb.weeks):
        return False
    if set(a.room_ids) & set(b.room_ids) and not (ea.share_room and eb.share_room):
        return True
    return bool(ea.cohort_keys & eb.cohort_keys or ea.instructor_keys & eb.instructor_keys)


def _cells(rows: list[Assignment]) -> frozenset[tuple[int, int, int, tuple[int, ...], frozenset[int]]]:
    return frozenset((a.day, a.start, a.end, tuple(sorted(a.room_ids)), a.weeks) for a in rows)


def _rank(e: Event) -> tuple[int, int]:
    """Who keeps a contested cell under ``lock_first``: the planner's trusted lock, then the coordinator priority."""
    from app.solver.policy import clamp_priority, trusted_locked

    return (1 if trusted_locked(e) else 0, clamp_priority(e.priority))


def keep_published(
    inp: SolverInput,
    current: Iterable[Assignment],
    result: SolverResult,
    scope: Iterable[int],
    *,
    unlocked_forbidden_tags: Mapping[int, frozenset[str]] | None = None,
) -> dict[str, list[int]]:
    """Round-3 R3-M-01: a re-solve never gives a published class (``current``) outside the edited ``scope`` away for a
    class that was not placed before at equal (or lower) lock / priority rank, and never moves one whose published
    cell is still free.  Works on the result in original event ids (several rows per event allowed), after the
    solve (repair or full), so the guarantee holds by construction — not only when the search proves the
    relaxation's ``previous`` tier optimal within its time limit.

    * a moved published class whose published rows clash with nothing placed goes back (hard rules re-checked);
    * a dropped published class goes back to its published rows when everything in their way is a newcomer of no
      higher rank (evicted) or a published class that moved (put back too, transitively, up to
      :data:`MAX_REVERT_CLUSTER`); a class of the scope or an unmoved published class in the way keeps the loss.
      Accepted only when no hard violation is added and the relaxation policy's cost does not get worse; an
      evicted newcomer that fits after all is placed again.
    * every evicted newcomer gets an ``unplaced`` diagnosis with ``policy.reason = "published_kept"`` naming the
      published classes that kept the cell.

    Rewrites ``result`` in place (assignments, diagnoses, placement stats, soft score) and returns
    ``{"reverted", "restored", "evicted"}`` (original event ids, sorted)."""
    from app.solver import policy as pol
    from app.solver.model import Diagnosis

    events = {e.id: e for e in inp.events}
    scope_ids = {int(i) for i in scope}
    base: dict[int, list[Assignment]] = _rows_by_event(inp, current)
    after: dict[int, list[Assignment]] = _rows_by_event(inp, result.assignments)
    cost_inp = replace(inp, previous=tuple(a for rows in base.values() for a in rows))

    def flat(rows: dict[int, list[Assignment]]) -> list[Assignment]:
        return [a for k in sorted(rows) for a in rows[k]]

    def violations(rows: dict[int, list[Assignment]]) -> int:
        view = segment_view(inp, flat(rows), unlocked_forbidden_tags=unlocked_forbidden_tags)
        return _hard_count(view.inp, view.current)

    def pair_clash(x: int, mine: list[Assignment], y: int, theirs: list[Assignment]) -> bool:
        return any(_rows_clash(a, events[x], b, events[y]) for a in mine for b in theirs)

    def clashing(rows: dict[int, list[Assignment]], eid: int, mine: list[Assignment]) -> list[int]:
        """The events in the way of ``eid`` at ``mine``; an unmoved published class that already shared the cell with it
        in the published timetable (a fixed-time clash accepted as a warning, a joint lecture) is no obstacle: the hard
        check judges it."""
        return [
            y
            for y in sorted(rows)
            if y != eid
            and pair_clash(eid, mine, y, rows[y])
            and not (
                eid in base
                and y in base
                and _cells(rows[y]) == _cells(base[y])
                and pair_clash(eid, base[eid], y, base[y])
            )
        ]

    after_before = dict(after)  # the solve's own rows (an evicted newcomer's cell, for its diagnosis)
    v_now = violations(after)
    cost_now = pol.cost(cost_inp, after)
    reverted: list[int] = []
    restored: list[int] = []
    evicted: dict[int, list[int]] = {}  # newcomer -> the published classes that took its cell back
    changed = True
    while changed:
        changed = False
        # 1) a published class that moved although its published cell is free goes back
        for eid in sorted(base):
            if eid in scope_ids or eid not in after or _cells(after[eid]) == _cells(base[eid]):
                continue
            if clashing(after, eid, base[eid]):
                continue
            trial = {**after, eid: base[eid]}
            v = violations(trial)
            if v <= v_now:
                after, v_now = trial, v
                reverted.append(eid)
                changed = True
        # 2) a published class that was dropped: put back, evicting newcomers of no higher rank
        lost = sorted(
            (x for x in base if x not in after and x not in scope_ids),
            key=lambda x: (*(-r for r in _rank(events[x])), x),
        )
        for eid in lost:
            trial = {**after, eid: base[eid]}
            out_now: list[int] = []
            back: list[int] = []
            queue = [eid]
            ok = True
            while queue and ok:
                x = queue.pop(0)
                for y in clashing(trial, x, trial[x]):
                    if y in scope_ids:
                        ok = False
                    elif y not in base:
                        if _rank(events[y]) > _rank(events[eid]):
                            ok = False
                        else:
                            del trial[y]
                            out_now.append(y)
                    elif _cells(trial[y]) != _cells(base[y]) and y not in back:
                        trial[y] = base[y]
                        back.append(y)
                        queue.append(y)
                        ok = len(back) < MAX_REVERT_CLUSTER
                    else:
                        ok = False  # an unmoved published class (or one put back already) holds it
                    if not ok:
                        break
            if not ok:
                continue
            v = violations(trial)
            if v > v_now or pol.cost(cost_inp, trial) > cost_now:
                continue
            for y in list(out_now):  # an evicted newcomer that fits after all stays
                if not clashing(trial, y, after[y]):
                    t2 = {**trial, y: after[y]}
                    v2 = violations(t2)
                    if v2 <= v:
                        trial, v = t2, v2
                        out_now.remove(y)
            after, v_now, cost_now = trial, v, pol.cost(cost_inp, trial)
            restored.append(eid)
            reverted.extend(back)
            for y in out_now:
                evicted.setdefault(y, []).append(eid)
            changed = True
    if not (reverted or restored or evicted):
        return {"reverted": [], "restored": [], "evicted": []}
    final = flat(after)
    gone = set(evicted)
    back_in = set(restored)
    result.assignments = final
    # the solver's hard score stands (no hard violation was added); the soft score follows the new placement
    view = segment_view(inp, final, unlocked_forbidden_tags=unlocked_forbidden_tags)
    placed = {a.event_id for a in view.current}
    sub = replace(view.inp, events=tuple(e for e in view.inp.events if e.id in placed), best_effort=False)
    _hard, soft, breakdown = score(sub, view.current)
    result.soft_score, result.objective_breakdown = soft, breakdown
    diags = [
        d
        for d in result.diagnoses
        if not (len(d.event_ids) == 1 and d.event_ids[0] in back_in and d.severity == "error")
    ]
    for d in diags:
        if d.code == "unplaced_summary":
            d.event_ids = [i for i in d.event_ids if i not in back_in] + sorted(gone)
    labels = {e.id: e.label for e in inp.events}
    rooms = {r.id: r for r in inp.rooms}
    for y in sorted(gone):
        e, winners = events[y], sorted(set(evicted[y]))
        names = ", ".join(labels.get(w, f"#{w}") for w in winners)
        mine = after_before[y]
        busy: dict[int, dict[str, Any]] = {}
        clashes: list[dict[str, Any]] = []
        for w in winners:
            for a in mine:
                for b in base[w]:
                    if not _rows_clash(a, e, b, events[w]):
                        continue
                    for r in sorted(set(a.room_ids) & set(b.room_ids)):
                        if r in rooms:
                            held = busy.setdefault(
                                r,
                                {
                                    "room": rooms[r].code,
                                    "capacity": rooms[r].capacity,
                                    "day": b.day,
                                    "start": b.start,
                                    "end": b.end,
                                    "holders": [],
                                },
                            )
                            if w not in held["holders"]:
                                held["holders"].append(w)
                    for k in sorted(
                        (e.cohort_keys & events[w].cohort_keys) | (e.instructor_keys & events[w].instructor_keys)
                    ):
                        clashes.append(
                            {
                                "kind": "cohort" if k in e.cohort_keys & events[w].cohort_keys else "instructor",
                                "key": k,
                                "day": b.day,
                                "start": b.start,
                                "end": b.end,
                                "holders": [w],
                            }
                        )
        when = mine[0] if mine else None
        diags.append(
            Diagnosis(
                [y],
                ["stability"],
                f"{e.label} cannot be placed: {names} of the published timetable keeps the cell at equal or higher "
                "priority (a re-solve never displaces a published class for a new one)",
                [f"raise the priority of {e.label} to place it before {names}", "move it to another time or room"],
                "error",
                "unplaced",
                {
                    "day": when.day if when else e.fixed_day,
                    "start": when.start if when else e.fixed_start,
                    "end": when.end if when else None,
                    # the run report's text: the rooms (or the cohort / instructor) the published class holds
                    "problem": "rooms_busy" if busy else "clash" if clashes else "published_kept",
                    "busy": list(busy.values()),
                    "clashes": clashes[:3],
                    "policy": {
                        "policy": pol.policy_name(inp.relaxation_policy),
                        "priority": pol.clamp_priority(e.priority),
                        "reason": "published_kept",
                        "winners": winners,
                    },
                },
            )
        )
    result.diagnoses = diags
    st = result.stats
    have = {a.event_id for a in final}
    if isinstance(st.get("placed"), int):
        st["placed"] = int(st["placed"]) + len(back_in) - len(gone)
        total = int(st.get("events_total") or len(inp.events))
        st["unplaced"] = max(0, total - int(st["placed"]))
    if isinstance(st.get("unplaced_ids"), list):
        st["unplaced_ids"] = [i for i in st["unplaced_ids"] if i not in have] + sorted(gone - set(st["unplaced_ids"]))
    if back_in:
        st["restored_to_published"] = sorted(set(st.get("restored_to_published") or []) | back_in)
    st["published_kept"] = {"reverted": sorted(reverted), "restored": sorted(restored), "evicted": sorted(gone)}
    st["policy_cost"] = list(cost_now)
    return {"reverted": sorted(reverted), "restored": sorted(restored), "evicted": sorted(gone)}


# -------------------------------------------------------------------------------------------------------- diff


def _place(a: Assignment | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {"day": a.day, "start": a.start, "end": a.end, "room_ids": list(a.room_ids), "weeks": sorted(a.weeks)}


def _place_rows(rows: list[Assignment]) -> dict[str, Any] | None:
    """The placement of one event: its row covering most weeks, plus ``segments`` (every row in week order) when the
    room changes between weeks."""
    if not rows:
        return None
    by_weeks = sorted(rows, key=lambda a: (min(a.weeks) if a.weeks else 0, a.room_ids))
    main = _place(max(by_weeks, key=lambda a: (len(a.weeks), -by_weeks.index(a))))
    assert main is not None
    if len(by_weeks) > 1:
        main["segments"] = [_place(a) for a in by_weeks]
    return main


def moved_diff(before: Iterable[Assignment], after: Iterable[Assignment]) -> list[dict[str, Any]]:
    """Events whose placement differs between ``before`` and ``after`` (time, rooms or weeks), sorted by id:
    ``{"event_id", "from", "to"}`` (``to`` None = no longer placed, ``from`` None = newly placed).  An event placed
    in several rows (a room change between weeks) is one entry: the main row plus ``segments``."""
    b: dict[int, list[Assignment]] = defaultdict(list)
    a: dict[int, list[Assignment]] = defaultdict(list)
    for x in before:
        b[x.event_id].append(x)
    for x in after:
        a[x.event_id].append(x)
    out: list[dict[str, Any]] = []
    for eid in sorted(set(b) | set(a)):
        pb, pa = _place_rows(b.get(eid, [])), _place_rows(a.get(eid, []))
        if pb != pa:
            out.append({"event_id": eid, "from": pb, "to": pa})
    return out


def validate(inp: SolverInput, assignments: Iterable[Assignment]) -> list[Violation]:
    """Every hard violation (``hard=True``) and soft penalty (``hard=False``) of the assignments."""
    return evaluate(inp, list(assignments)).violations


def score(inp: SolverInput, assignments: Iterable[Assignment]) -> tuple[int, int, dict[str, int]]:
    """``(hard_score, soft_score, objective_breakdown)`` with the solver's definitions."""
    ev = evaluate(inp, list(assignments))
    return ev.hard_score(), ev.soft_score(), dict(sorted(ev.penalties.items()))


__all__ = [
    "MAX_REVERT_CLUSTER",
    "SegmentView",
    "Violation",
    "keep_published",
    "minimal_change",
    "moved_diff",
    "neighbourhood",
    "neighbours",
    "repair",
    "score",
    "segment_view",
    "validate",
    "violating_events",
]
