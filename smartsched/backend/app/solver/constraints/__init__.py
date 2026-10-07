"""Constraint-kind registry.

Every kind lives in its own module exposing

* ``prune(doms, c)``  (optional) — tighten candidate domains for a *hard* constraint before any
  CP-SAT variable exists;
* ``apply(ctx, c)``   — add hard clauses (guarded by assumption literals in ``assume`` mode) or
  soft penalty terms to the :class:`~app.solver.context.ModelContext`;
* ``score(ev, c)``    — evaluate the same rule on a finished set of assignments, recording hard
  violations and weighted soft penalties on the :class:`~app.solver.evaluate.Evaluation`.

``IMPLICIT`` kinds are always active, derived from ``Event`` fields (capacity, pins, overlaps ...).
An explicit ``Constraint`` of an implicit kind either *configures* the default (no event selector:
e.g. ``Constraint("capacity", {}, hard=False)`` makes capacity a soft rule) or *adds* a targeted
rule (``{"event_ids": [...], ...}``).  Overlap kinds can never be softened: a request to do so is
ignored and reported in ``stats["warnings"]``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.solver.constraints import (
    _common,
    building_preference,
    capacity,
    day_window,
    evening_programs_in_buildings,
    exam_gap,
    fixed_time,
    max_exams_per_day,
    min_capacity_waste,
    no_cohort_overlap,
    no_instructor_overlap,
    no_room_overlap,
    room_closed,
    room_forbid,
    room_pin,
    room_preference,
    room_tags,
    same_room_across_weeks,
    same_room_group,
    stability,
)
from app.solver.context import ModelContext
from app.solver.domains import Domains
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, SolverInput


@dataclass(frozen=True)
class Handler:
    kind: str
    apply: Callable[[ModelContext, Constraint], None]
    score: Callable[[Evaluation, Constraint], None]
    prune: Callable[[Domains, Constraint], None] | None = None
    implicit: bool = False  # always active even without an explicit Constraint
    may_soften: bool = True  # hard=False accepted
    default_hard: bool = True  # hardness of the implicit default


HANDLERS: dict[str, Handler] = {
    h.kind: h
    for h in (
        Handler("capacity", capacity.apply, capacity.score, capacity.prune, implicit=True),
        Handler("no_room_overlap", no_room_overlap.apply, no_room_overlap.score, implicit=True, may_soften=False),
        Handler(
            "no_cohort_overlap",
            no_cohort_overlap.apply,
            no_cohort_overlap.score,
            no_cohort_overlap.prune,
            implicit=True,
            may_soften=False,
        ),
        Handler(
            "no_instructor_overlap",
            no_instructor_overlap.apply,
            no_instructor_overlap.score,
            no_instructor_overlap.prune,
            implicit=True,
            may_soften=False,
        ),
        Handler("fixed_time", fixed_time.apply, fixed_time.score, fixed_time.prune, implicit=True),
        Handler("room_tags", room_tags.apply, room_tags.score, room_tags.prune, implicit=True),
        Handler("room_pin", room_pin.apply, room_pin.score, room_pin.prune, implicit=True),
        Handler("room_forbid", room_forbid.apply, room_forbid.score, room_forbid.prune, implicit=True),
        Handler(
            "building_preference",
            building_preference.apply,
            building_preference.score,
            building_preference.prune,
            implicit=True,
            default_hard=False,
        ),
        Handler(
            "room_preference",
            room_preference.apply,
            room_preference.score,
            room_preference.prune,
            implicit=True,
            default_hard=False,
        ),
        Handler(
            "same_room_across_weeks",
            same_room_across_weeks.apply,
            same_room_across_weeks.score,
            implicit=True,
            default_hard=False,
        ),
        Handler("same_room_group", same_room_group.apply, same_room_group.score, implicit=True, default_hard=False),
        Handler(
            "min_capacity_waste", min_capacity_waste.apply, min_capacity_waste.score, implicit=True, default_hard=False
        ),
        Handler("exam_gap", exam_gap.apply, exam_gap.score),
        Handler("max_exams_per_day", max_exams_per_day.apply, max_exams_per_day.score),
        Handler("stability", stability.apply, stability.score, implicit=True, default_hard=False),
        Handler("room_closed", room_closed.apply, room_closed.score, room_closed.prune),
        Handler("day_window", day_window.apply, day_window.score, day_window.prune),
        Handler(
            "evening_programs_in_buildings",
            evening_programs_in_buildings.apply,
            evening_programs_in_buildings.score,
            evening_programs_in_buildings.prune,
        ),
    )
}

#: structural kinds whose implicit hard version is enforced by domain pruning
STRUCTURAL = frozenset({"capacity", "room_tags", "room_pin", "room_forbid", "fixed_time"})


def effective_constraints(inp: SolverInput) -> tuple[list[Constraint], list[str], frozenset[str]]:
    """Explicit constraints + implicit defaults.

    Returns ``(constraints, warnings, soft_structural)`` where ``soft_structural`` lists the
    structural kinds whose implicit default was switched to soft by an explicit constraint."""
    warnings: list[str] = []
    out: list[Constraint] = []
    configured: dict[str, Constraint] = {}
    for c in inp.constraints:
        h = HANDLERS.get(c.kind)
        if h is None:
            warnings.append(f"unknown constraint kind '{c.kind}' (id={c.id}) ignored")
            continue
        if not c.hard and not h.may_soften:
            warnings.append(f"constraint kind '{c.kind}' (id={c.id}) cannot be soft; kept hard")
            c = Constraint(c.kind, c.params, True, c.weight, c.id)
        if h.implicit and not _common.is_targeted(c):
            if c.kind in configured:
                warnings.append(f"duplicate default configuration for '{c.kind}' (id={c.id}); last one wins")
            configured[c.kind] = c
            continue
        out.append(c)
    for kind, h in HANDLERS.items():
        if not h.implicit:
            continue
        default = configured.get(kind)
        out.append(default if default is not None else Constraint(kind, {}, hard=h.default_hard, weight=1, id=None))
    soft_structural = frozenset(
        c.kind for c in out if c.kind in STRUCTURAL and not c.hard and not _common.is_targeted(c)
    )
    return out, warnings, soft_structural


def handler(kind: str) -> Handler:
    return HANDLERS[kind]


__all__ = ["HANDLERS", "STRUCTURAL", "Handler", "effective_constraints", "handler"]
