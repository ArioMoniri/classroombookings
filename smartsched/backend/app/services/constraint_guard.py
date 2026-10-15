"""Hard-rule integrity guard (review 2026-10-15 D1 / P19-00a).

The solver enforces five *structural* rules implicitly and hard: room capacity, room tags (PC, TIP ...), fixed
times, room pins and room bans. A constraint row of one of these kinds that is **soft and names no target**
(no ``event_ids``, cohort, programme, match or instructor) does not add a preference: it switches the implicit
hard rule off for every class of the term. 180 students in a 50-seat room then come out OPTIMAL with hard 100.

Every code path that creates or edits a ``ConstraintRow`` calls :func:`guard_rule` before writing it:

* ``POST /constraints`` and ``PUT /constraints/{id}`` (``app/api/v1/constraints.py``);
* AI / upload proposals (``app/ai/elicit.accept_proposals``) with ``may_waive=False``;
* studio copy-from-term and presets (``app/services/studio_rules.py``).

Only a ``planning.admin`` with a written reason may waive a structural rule, and never through a rule whose
source is AI, UPLOAD or LEARNED. The caller stores the waiver on ``source_ref["waiver"]`` (:func:`waiver_ref`)
and audits it (``constraint.waive``). Targeted soft structural rules ("MAT 112 may exceed its room") stay a
normal planner decision: they touch only the classes they name.

The definitions come from the solver (``STRUCTURAL`` and ``is_targeted``), read-only, so the guard cannot drift
from what the solver actually does.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.solver.constraints import STRUCTURAL
from app.solver.constraints._common import is_targeted
from app.solver.model import Constraint

#: the solver's structural kinds (capacity, room_tags, fixed_time, room_pin, room_forbid)
STRUCTURAL_KINDS: frozenset[str] = frozenset(STRUCTURAL)
#: rule sources that may never carry a waiver, whoever accepts them
UNWAIVABLE_SOURCES: frozenset[str] = frozenset({"AI", "UPLOAD", "LEARNED"})
REASON_MIN = 3


def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    # metadata keys (``_source_ref`` ...) are dropped before the solver sees the params
    return {k: v for k, v in dict(params or {}).items() if not str(k).startswith("_")}


def is_waiver(kind: str, params: Mapping[str, Any] | None, hardness: str | None) -> bool:
    """True when the row would switch a structural hard rule off for the whole term."""
    if kind not in STRUCTURAL_KINDS or (hardness or "soft") != "soft":
        return False
    return not is_targeted(Constraint(kind, _clean_params(params), hard=False))


def guard_rule(
    kind: str,
    params: Mapping[str, Any] | None,
    hardness: str | None,
    *,
    source: str | None,
    may_waive: bool,
    reason: str | None,
) -> list[str]:
    """Problems that forbid writing this rule; empty list = allowed.

    ``may_waive``: the actor holds ``planning.admin``. ``reason``: the written justification of a waiver."""
    if not is_waiver(kind, params, hardness):
        return []
    what = (
        f"a soft '{kind}' rule without a target switches the structural hard rule off for every class "
        f"(name the classes with event_ids, cohort, program, match or instructor, or keep it hard)"
    )
    if (source or "").upper() in UNWAIVABLE_SOURCES:
        return [f"{what}; rules from {source} may never waive a structural rule"]
    if not may_waive:
        return [f"{what}; only a planning administrator may waive it, with a reason"]
    if len((reason or "").strip()) < REASON_MIN:
        return [f"{what}; a waiver needs a written reason"]
    return []


def waiver_ref(source_ref: Mapping[str, Any] | None, *, reason: str, actor_id: int | None) -> dict[str, Any]:
    """``source_ref`` with the waiver recorded (who, why, when)."""
    out = dict(source_ref or {})
    out["waiver"] = {"reason": reason.strip(), "by": actor_id, "at": datetime.now(UTC).isoformat(timespec="seconds")}
    return out


def without_waiver(source_ref: Mapping[str, Any] | None) -> dict[str, Any] | None:
    out = {k: v for k, v in dict(source_ref or {}).items() if k != "waiver"}
    return out or None


__all__ = ["STRUCTURAL_KINDS", "UNWAIVABLE_SOURCES", "guard_rule", "is_waiver", "waiver_ref", "without_waiver"]
