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
from what the solver actually does. The solver's ``is_targeted`` looks at key presence only, while its
``select_events`` reads an empty selector as "every event"; so the guard also requires a non-blank value
(admin persona 2026-10-15 M-47: ``{"match": ""}``, ``{"match": " "}``, ``{"event_ids": []}`` are untargeted).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.importers import normalize as n
from app.solver.constraints import STRUCTURAL
from app.solver.constraints._common import is_targeted
from app.solver.model import Constraint

#: the solver's structural kinds (capacity, room_tags, fixed_time, room_pin, room_forbid)
STRUCTURAL_KINDS: frozenset[str] = frozenset(STRUCTURAL)
#: rule sources that may never carry a waiver, whoever accepts them
UNWAIVABLE_SOURCES: frozenset[str] = frozenset({"AI", "UPLOAD", "LEARNED", "TEACHER"})
REASON_MIN = 3
#: the selector keys of ``app.solver.constraints._common.is_targeted`` / ``select_events``
SELECTOR_KEYS: tuple[str, ...] = (
    "event_ids",
    "cohort",
    "cohorts",
    "program",
    "programs",
    "match",
    "instructor",
    "instructors",
)


def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    # metadata keys (``_source_ref`` ...) are dropped before the solver sees the params
    return {k: v for k, v in dict(params or {}).items() if not str(k).startswith("_")}


def _names_something(value: Any) -> bool:
    """A selector value that names at least one thing: a number, a non-blank text (NBSP, zero-width and other
    spaces are blank) or a list holding one of these."""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        return n.clean_text(value) is not None
    if isinstance(value, list | tuple | set | frozenset):
        return any(_names_something(v) for v in value)
    return False


def is_targeted_params(params: Mapping[str, Any] | None) -> bool:
    """True when the params name specific classes: the solver's ``is_targeted`` *and* a non-blank selector."""
    clean = _clean_params(params)
    if not is_targeted(Constraint("capacity", clean, hard=False)):
        return False
    return any(_names_something(clean.get(k)) for k in SELECTOR_KEYS)


def is_waiver(kind: str, params: Mapping[str, Any] | None, hardness: str | None) -> bool:
    """True when the row would switch a structural hard rule off for the whole term."""
    if kind not in STRUCTURAL_KINDS or (hardness or "soft") != "soft":
        return False
    return not is_targeted_params(params)


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


__all__ = [
    "SELECTOR_KEYS",
    "STRUCTURAL_KINDS",
    "UNWAIVABLE_SOURCES",
    "guard_rule",
    "is_targeted_params",
    "is_waiver",
    "waiver_ref",
    "without_waiver",
]
