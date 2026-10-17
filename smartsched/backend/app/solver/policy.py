"""Relaxation policy: who loses when not every request can be placed (user decision 2026-10-15).

A best-effort run (``SolverInput.best_effort``) whose request set has no complete timetable keeps the
placement that is lexicographically best under ``SolverInput.relaxation_policy``:

* ``lock_first`` (default): (1) the planner's trusted locks (``Event.locked`` with ``lock_trusted``) are kept
  — a lock is never moved, it is either placed where the planner put it or reported unplaced; (2) then the
  coordinator-set ``Event.priority`` (higher first: one more request of a higher priority beats any number of
  lower ones); (3) then the most requests placed, (4) then the requests placed in the *previous* timetable
  (``SolverInput.previous``: a re-solve never trades a published class for a newcomer of equal priority — round-2
  T-R2-34), (5) the most event-weeks, (6) tool-made locks.
* ``most_classes_first``: (1) the most requests placed, (2) the previous timetable's requests, (3) the most
  event-weeks, (4) priority, (5) locks.

A *request* is one event, or every week segment of one request (``weeksplit``: placed only when all its
segments are).  Ties left after every tier are broken by class size and a fixed id rank (never by the input
order or submission time: policy default Q3).

The tiers are linear counts over ``placed[e]`` (relaxation mode of the CP-SAT model).  Tiers whose combined
coefficient range fits :data:`SINGLE_OBJECTIVE_LIMIT` are folded into one weighted objective; otherwise the
groups are solved in stages (solve, fix ``group <= value``, solve the next group): :func:`objective_groups`.
:func:`cost` evaluates the same tiers in pure Python for a set of placed events, so every placement the solver
compares (greedy fallback, week-split rounds) is ranked by the same order.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.solver.model import Event, SolverInput

Policy = Literal["lock_first", "most_classes_first"]
POLICIES: tuple[Policy, ...] = ("lock_first", "most_classes_first")
DEFAULT_POLICY: Policy = "lock_first"
PRIORITY_MIN, PRIORITY_MAX = -100, 100
#: largest coefficient range ``Π (ub_k + 1)`` of one weighted objective (the relaxation multiplies it once more
#: by the warm-start room tier); beyond it the tiers are solved in stages
SINGLE_OBJECTIVE_LIMIT = 2**42


def policy_name(value: Any) -> Policy:
    """A valid policy name; anything else (``None``, a typo stored in a setting) is the default."""
    if value == "most_classes_first":
        return "most_classes_first"
    return DEFAULT_POLICY


def clamp_priority(value: Any) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    return max(PRIORITY_MIN, min(PRIORITY_MAX, v))


def trusted_locked(e: Event) -> bool:
    """The planner's own lock (a LOCKED planning-list row): never moved, kept first under ``lock_first``."""
    return e.locked is not None and e.lock_trusted


def previously_placed(inp: SolverInput) -> frozenset[int]:
    """Events placed in the previous timetable (``SolverInput.previous``; rooms given when the event needs one)."""
    by_id = {e.id: e for e in inp.events}
    return frozenset(
        a.event_id for a in inp.previous if a.event_id in by_id and (a.room_ids or not by_id[a.event_id].needs_room)
    )


def segment_groups(inp: SolverInput) -> list[list[int]]:
    """Events that are week segments of one request (``weeksplit.split_blocked_weeks`` marks their
    ``same_room_across_weeks`` group with ``week_segments``)."""
    ids = {e.id for e in inp.events}
    out: list[list[int]] = []
    for c in inp.constraints:
        if c.kind == "same_room_across_weeks" and c.params.get("week_segments"):
            for g in c.params.get("groups") or []:
                members = [int(i) for i in g if int(i) in ids]
                if len(members) > 1:
                    out.append(members)
    return out


@dataclass(frozen=True)
class Unit:
    """One request as the relaxation counts it: an event, or all week segments of one request."""

    ids: tuple[int, ...]
    priority: int

    @property
    def grouped(self) -> bool:
        return len(self.ids) > 1


#: an indicator "is missing": ``("event", id)`` = 1 - placed[id]; ``("unit", index)`` = the unit is not placed
#: completely (for a single-event unit the same as its event)
Indicator = tuple[str, int]


@dataclass(frozen=True)
class Tier:
    name: str
    terms: tuple[tuple[int, Indicator], ...]

    @property
    def ub(self) -> int:
        return sum(c for c, _ in self.terms)


def units(inp: SolverInput) -> list[Unit]:
    by_id = {e.id: e for e in inp.events}
    seen: set[int] = set()
    out: list[Unit] = []
    for g in segment_groups(inp):
        g = [i for i in g if i not in seen]
        if len(g) < 2:
            continue
        seen.update(g)
        out.append(Unit(tuple(g), max(clamp_priority(by_id[i].priority) for i in g)))
    for e in inp.events:
        if e.id not in seen:
            out.append(Unit((e.id,), clamp_priority(e.priority)))
    return out


def tiers(inp: SolverInput, unit_list: list[Unit] | None = None) -> list[Tier]:
    """The policy's tiers, most significant first; empty tiers are dropped."""
    us = unit_list if unit_list is not None else units(inp)
    weeks = {e.id: max(1, len(e.weeks)) for e in inp.events}
    trusted = [e.id for e in inp.events if trusted_locked(e)]
    tool = [e.id for e in inp.events if e.locked is not None and not e.lock_trusted]
    levels = sorted({u.priority for u in us}, reverse=True)
    requests = Tier("requests", tuple((1, ("unit", i)) for i in range(len(us))))
    by_level = [
        Tier(f"priority:{p}", tuple((1, ("unit", i)) for i, u in enumerate(us) if u.priority == p)) for p in levels
    ]
    event_weeks = Tier("weeks", tuple((weeks[e.id], ("event", e.id)) for e in inp.events))
    locks = Tier("locks", tuple((1, ("event", i)) for i in trusted))
    # the requests of the previous timetable (a published run under a moderation re-solve): kept ahead of a
    # newcomer at equal priority and count, so a soft change never costs a placed class (round-2 T-R2-34)
    had = previously_placed(inp)
    previous = Tier("previous", tuple((1, ("unit", i)) for i, u in enumerate(us) if any(x in had for x in u.ids)))
    policy = policy_name(inp.relaxation_policy)
    out: list[Tier]
    if policy == "lock_first":
        # with several priority levels the level counts add up to the request count: no separate request tier
        prio = by_level if len(levels) > 1 else [requests]
        out = [locks, *prio, previous, event_weeks, Tier("tool_locks", tuple((1, ("event", i)) for i in tool))]
    else:
        out = [
            requests,
            previous,
            event_weeks,
            *(by_level if len(levels) > 1 else []),
            Tier("locks", tuple((1, ("event", i)) for i in trusted + tool)),
        ]
    return [t for t in out if t.ub > 0]


def cost(inp: SolverInput, placed: Iterable[int]) -> tuple[int, ...]:
    """The policy's tier values for the events ``placed`` (smaller is better, compare as tuples)."""
    have = set(placed)
    us = units(inp)

    def missing(ind: Indicator) -> int:
        kind, key = ind
        if kind == "event":
            return int(key not in have)
        return int(not all(i in have for i in us[key].ids))

    return tuple(sum(c * missing(ind) for c, ind in t.terms) for t in tiers(inp, us))


def better(inp: SolverInput, a: Iterable[int], b: Iterable[int]) -> bool:
    """Is placement ``a`` strictly better than ``b`` under the policy?"""
    return cost(inp, a) < cost(inp, b)


def objective_groups(tier_list: list[Tier]) -> list[list[tuple[Tier, int]]]:
    """Fold tiers into weighted groups (``Σ weight·tier``, lexicographic within a group) whose coefficient range
    fits :data:`SINGLE_OBJECTIVE_LIMIT`; groups are most significant first and solved in stages."""
    groups: list[list[tuple[Tier, int]]] = []
    current: list[tuple[Tier, int]] = []
    mult = 1
    for t in reversed(tier_list):
        if current and mult * (t.ub + 1) > SINGLE_OBJECTIVE_LIMIT:
            groups.append(current)
            current, mult = [], 1
        current.insert(0, (t, mult))
        mult *= t.ub + 1
    if current:
        groups.append(current)
    groups.reverse()
    return groups


def describe(inp: SolverInput) -> dict[str, Any]:
    """Stats of the policy for a run (tier names and the stage split)."""
    ts = tiers(inp)
    return {
        "policy": policy_name(inp.relaxation_policy),
        "tiers": [t.name for t in ts],
        "stages": [[t.name for t, _ in g] for g in objective_groups(ts)],
        "priority_levels": sorted({clamp_priority(e.priority) for e in inp.events}, reverse=True),
    }


# --------------------------------------------------------------------------- loss reasons (run report)

#: reason codes of an unplaced request under the policy (README "Relaxation policy"; TR / EN texts in the bridge)
LOSS_REASONS = (
    "lock_clash_priority",  # two locks hold one room at once: the other lock has the higher priority (Q5)
    "lock_clash_tie",  # two locks, equal priority: more classes / weeks, then the larger class (never row order)
    "lock_clash_more_locks",  # keeping this lock would drop more locked rows (they have a lower priority)
    "locked_row_kept",  # a trusted locked row holds what this request needs (locks are never moved)
    "lower_priority",  # a request of higher coordinator priority holds it
    "published_kept",  # a class of the previous (published) timetable holds it at equal priority (T-R2-34)
    "most_classes",  # placing it would leave at least as many other requests out
    "no_option",  # nothing placed blocks it: no room / time survives the hard rules
)


def loss_reason(inp: SolverInput, e: Event, competitors: Iterable[int], by_id: Mapping[int, Event]) -> dict[str, Any]:
    """Why ``e`` lost under the policy, given the placed events that hold one of its options (a room or a
    cohort / instructor key at one of its times).  ``winners`` are the events named in the run report."""
    policy = policy_name(inp.relaxation_policy)
    comp = sorted({int(i) for i in competitors if int(i) in by_id and int(i) != e.id})
    out: dict[str, Any] = {"policy": policy, "priority": clamp_priority(e.priority)}
    if not comp:
        return {**out, "reason": "no_option", "winners": []}
    events = [by_id[i] for i in comp]
    locks = [x for x in events if trusted_locked(x)]
    higher = [x for x in events if clamp_priority(x.priority) > clamp_priority(e.priority)]

    def ids(xs: list[Event]) -> list[int]:
        return [x.id for x in sorted(xs, key=lambda x: (-clamp_priority(x.priority), -x.size, x.id))][:5]

    if policy == "lock_first":
        if trusted_locked(e) and locks:
            hi = [x for x in locks if clamp_priority(x.priority) > clamp_priority(e.priority)]
            if hi:
                return {**out, "reason": "lock_clash_priority", "winners": ids(hi)}
            eq = [x for x in locks if clamp_priority(x.priority) == clamp_priority(e.priority)]
            if eq:
                return {**out, "reason": "lock_clash_tie", "winners": ids(eq)}
            return {**out, "reason": "lock_clash_more_locks", "winners": ids(locks)}
        if locks and not trusted_locked(e):
            return {**out, "reason": "locked_row_kept", "winners": ids(locks)}
        if higher:
            return {**out, "reason": "lower_priority", "winners": ids(higher)}
    had = previously_placed(inp)
    kept = [x for x in events if x.id in had]
    if kept and e.id not in had:
        return {**out, "reason": "published_kept", "winners": ids(kept)}
    return {**out, "reason": "most_classes", "winners": ids(events)}


__all__ = [
    "DEFAULT_POLICY",
    "LOSS_REASONS",
    "POLICIES",
    "PRIORITY_MAX",
    "PRIORITY_MIN",
    "SINGLE_OBJECTIVE_LIMIT",
    "Tier",
    "Unit",
    "better",
    "clamp_priority",
    "cost",
    "describe",
    "loss_reason",
    "objective_groups",
    "policy_name",
    "previously_placed",
    "segment_groups",
    "tiers",
    "trusted_locked",
    "units",
]
