"""LNS-style repair and CP-SAT-independent validation.

* :func:`repair` — after a chat/manual edit: keep every assignment except the changed events'
  neighbours (events that share a room slot, a cohort key or an instructor key at an overlapping
  time), re-solve the small residual model with the stability objective and hints.
* :func:`validate` — pure-Python check of every hard rule (and the soft score) over any set of
  assignments; used by the API after AI/manual edits.  Same objective definitions as the solver.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from app.solver.cpsat import solve
from app.solver.domains import TimeOption, weeks_intersect
from app.solver.evaluate import Violation, index_assignments
from app.solver.model import Assignment, Event, SolverInput, SolverResult
from app.solver.scoring import evaluate


def _touches(a: Assignment, ea: Event, b: Assignment, eb: Event) -> bool:
    ta = TimeOption(a.day, a.start, a.end - a.start + 1)
    tb = TimeOption(b.day, b.start, b.end - b.start + 1)
    if not ta.overlaps(tb) or not weeks_intersect(ea.weeks, eb.weeks):
        return False
    return bool(
        set(a.room_ids) & set(b.room_ids) or ea.cohort_keys & eb.cohort_keys or ea.instructor_keys & eb.instructor_keys
    )


def neighbours(inp: SolverInput, assignments: Iterable[Assignment], seeds: Iterable[int], radius: int = 1) -> set[int]:
    """Events within ``radius`` conflict hops of the seed events (seeds included)."""
    by_id = index_assignments(list(assignments))
    events = {e.id: e for e in inp.events}
    frontier = {s for s in seeds if s in events}
    seen = set(frontier)
    for _ in range(max(0, radius)):
        nxt: set[int] = set()
        for s in frontier:
            a = by_id.get(s)
            if a is None:
                continue
            for other_id, b in by_id.items():
                if other_id in seen or other_id not in events:
                    continue
                if _touches(a, events[s], b, events[other_id]):
                    nxt.add(other_id)
        seen |= nxt
        frontier = nxt
    return seen


def repair(
    inp: SolverInput,
    assignments: Iterable[Assignment],
    changed_event_ids: Iterable[int],
    time_limit_s: float = 5.0,
    *,
    keep_changed: bool = True,
    radius: int = 1,
) -> SolverResult:
    """Re-solve only the neighbourhood of the changed events.

    ``keep_changed=True`` (chat-edit flow): the changed events are locked to their edited
    assignment (that *is* the user's intent) and their neighbours are freed; ``False``: the changed
    events are freed too.  Every other event is locked to its current assignment, so the residual
    model is tiny and the stability objective keeps the freed events where they were if possible.
    If the edit is impossible the result is INFEASIBLE with a diagnosis — never a silent relaxation.
    """
    current = list(assignments)
    by_id = index_assignments(current)
    changed = {int(i) for i in changed_event_ids}
    free = neighbours(inp, current, changed, radius)
    if keep_changed:
        free -= changed
    else:
        free |= changed
    events: list[Event] = []
    for e in inp.events:
        if e.id in free:
            events.append(e)  # keeps an original lock if the event had one
        elif e.id in by_id and (e.locked is None or e.id in changed):
            events.append(replace(e, locked=by_id[e.id]))
        else:
            events.append(e)
    new_inp = replace(inp, events=tuple(events), previous=tuple(current), time_limit_s=time_limit_s)
    result = solve(new_inp)
    result.stats["repair"] = {
        "changed": sorted(changed),
        "freed": sorted(free),
        "locked": sum(1 for e in events if e.locked is not None),
        "radius": radius,
        "keep_changed": keep_changed,
    }
    return result


def validate(inp: SolverInput, assignments: Iterable[Assignment]) -> list[Violation]:
    """Every hard violation (``hard=True``) and soft penalty (``hard=False``) of the assignments."""
    return evaluate(inp, list(assignments)).violations


def score(inp: SolverInput, assignments: Iterable[Assignment]) -> tuple[int, int, dict[str, int]]:
    """``(hard_score, soft_score, objective_breakdown)`` with the solver's definitions."""
    ev = evaluate(inp, list(assignments))
    return ev.hard_score(), ev.soft_score(), dict(sorted(ev.penalties.items()))


__all__ = ["Violation", "neighbours", "repair", "score", "validate"]
