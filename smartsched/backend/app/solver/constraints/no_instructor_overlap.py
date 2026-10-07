"""``no_instructor_overlap``: events sharing an instructor key never overlap in a shared week.
Always hard.  Assumption guard per key: ``instructor:<key>``."""

from __future__ import annotations

from app.solver.constraints import _overlap
from app.solver.constraints._common import str_list
from app.solver.context import ModelContext
from app.solver.domains import Domains, instructor_groups
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, SolverInput


def _groups(inp: SolverInput, c: Constraint) -> dict[str, list[int]]:
    groups = instructor_groups(inp)
    keys = str_list(c.params, "keys")
    if keys:
        groups = {k: v for k, v in groups.items() if k in keys}
    return groups


def prune(doms: Domains, c: Constraint) -> None:
    _overlap.prune_keys(doms, _groups(doms.inp, c), "no_instructor_overlap", "instructor")


def apply(ctx: ModelContext, c: Constraint) -> None:
    _overlap.apply_keys(ctx, _groups(ctx.inp, c), "no_instructor_overlap", "instructor")


def score(ev: Evaluation, c: Constraint) -> None:
    _overlap.score_keys(ev, _groups(ev.inp, c), "no_instructor_overlap", "instructor")


__all__ = ["apply", "prune", "score"]
