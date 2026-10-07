"""``no_cohort_overlap``: events sharing a cohort key (``PROG:Psikoloji:Y1``) never overlap in a
week they share.  Always hard.  Extra params: ``{"keys": [...]}`` restricts the keys checked
(default: every key).  Assumption guard per key: ``cohort:<key>``."""

from __future__ import annotations

from app.solver.constraints import _overlap
from app.solver.constraints._common import str_list
from app.solver.context import ModelContext
from app.solver.domains import Domains, cohort_groups
from app.solver.evaluate import Evaluation
from app.solver.model import Constraint, SolverInput


def _groups(inp: SolverInput, c: Constraint) -> dict[str, list[int]]:
    groups = cohort_groups(inp)
    keys = str_list(c.params, "keys")
    if keys:
        groups = {k: v for k, v in groups.items() if k in keys}
    return groups


def prune(doms: Domains, c: Constraint) -> None:
    _overlap.prune_keys(doms, _groups(doms.inp, c), "no_cohort_overlap", "cohort")


def apply(ctx: ModelContext, c: Constraint) -> None:
    _overlap.apply_keys(ctx, _groups(ctx.inp, c), "no_cohort_overlap", "cohort")


def score(ev: Evaluation, c: Constraint) -> None:
    _overlap.score_keys(ev, _groups(ev.inp, c), "no_cohort_overlap", "cohort")


__all__ = ["apply", "prune", "score"]
