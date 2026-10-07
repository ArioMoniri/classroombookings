"""Helpers shared by the constraint-kind modules."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, TypeVar

from app.solver.model import Constraint, Event, SolverInput

T = TypeVar("T")


def week_classes(items: Sequence[tuple[T, frozenset[int]]]) -> list[list[T]]:
    """Group items by week so that two items end up in a common group iff their week sets
    intersect.  Returns only the *maximal* groups (a group that is a subset of another is implied
    by it), in a deterministic order.  Groups of size < 2 are dropped."""
    by_week: dict[int, set[int]] = defaultdict(set)
    for idx, (_, weeks) in enumerate(items):
        for w in weeks:
            by_week[w].add(idx)
    distinct: set[frozenset[int]] = {frozenset(s) for s in by_week.values() if len(s) >= 2}
    maximal = [s for s in distinct if not any(s < other for other in distinct)]
    maximal.sort(key=lambda s: (len(s), sorted(s)))
    return [[items[i][0] for i in sorted(s)] for s in maximal]


def week_runs(weeks: frozenset[int]) -> list[tuple[int, int]]:
    """Contiguous runs of a week set as inclusive ``(first, last)`` pairs."""
    out: list[tuple[int, int]] = []
    for w in sorted(weeks):
        if out and out[-1][1] == w - 1:
            out[-1] = (out[-1][0], w)
        else:
            out.append((w, w))
    return out


def int_list(params: Mapping[str, Any], key: str) -> list[int]:
    value = params.get(key)
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    return [int(v) for v in value]


def str_list(params: Mapping[str, Any], key: str) -> list[str]:
    value = params.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def select_events(inp: SolverInput, params: Mapping[str, Any]) -> list[Event]:
    """Events targeted by a constraint's params.

    Selectors (union): ``event_ids``, ``cohort``/``cohorts`` (exact cohort keys), ``program``
    (cohort keys starting with ``PROG:<program>``), ``match`` (case-insensitive substring of a cohort
    key or the label), ``instructor``/``instructors`` (instructor keys).  Optional ``kinds`` filter
    (``["exam"]``).  No selector = every event."""
    ids = set(int_list(params, "event_ids"))
    cohorts = set(str_list(params, "cohort") + str_list(params, "cohorts"))
    programs = str_list(params, "program") + str_list(params, "programs")
    instructors = set(str_list(params, "instructor") + str_list(params, "instructors"))
    match = params.get("match")
    matches = [str(m).casefold() for m in (match if isinstance(match, list) else [match]) if m]
    kinds = set(str_list(params, "kinds") + str_list(params, "kind"))
    has_selector = bool(ids or cohorts or programs or instructors or matches)
    out: list[Event] = []
    for e in inp.events:
        if kinds and e.kind not in kinds:
            continue
        if not has_selector:
            out.append(e)
            continue
        if e.id in ids or (e.cohort_keys & cohorts) or (e.instructor_keys & instructors):
            out.append(e)
            continue
        if any(k.startswith(f"PROG:{p}") for p in programs for k in e.cohort_keys):
            out.append(e)
            continue
        hay = [k.casefold() for k in e.cohort_keys] + [e.label.casefold()]
        if any(m in h for m in matches for h in hay):
            out.append(e)
    return out


def is_targeted(c: Constraint) -> bool:
    """True when the constraint names specific events/cohorts (additive) rather than configuring
    the kind's implicit default."""
    keys = ("event_ids", "cohort", "cohorts", "program", "programs", "match", "instructor", "instructors")
    return any(k in c.params for k in keys)


def label_of(inp_events: Mapping[int, Event], eid: int) -> str:
    e = inp_events.get(eid)
    return f"{e.label} (#{eid})" if e is not None else f"#{eid}"


def pairs(seq: Iterable[T]) -> list[tuple[T, T]]:
    items = list(seq)
    return [(items[i], items[j]) for i in range(len(items)) for j in range(i + 1, len(items))]
