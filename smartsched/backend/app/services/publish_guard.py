"""Hard-rule integrity of a run before and while it is the published timetable ("100/100 or explained"; review
2026-10-15 D4 and the admin persona test M-02 / M-04).

* **Forced overrides.** A planning administrator may force a manual move that breaks a hard rule (room clash,
  capacity, block ...), only with a written reason. Every such move is recorded on the run
  (``stats.forced_overrides``: assignments, requests, rules, the conflicts, reason, who, when, audit id) and
  stays listed in the run report.
* **Integrity** (:func:`integrity`) re-reads the planner-level check (:mod:`app.services.planner_check`): its
  violations and the "manual" exceptions (a planner's edit that breaks a rule) count against the hard score; a
  manual finding is *explained* when a recorded override names one of its requests. Unplaced requests do not
  block (a best-effort partial timetable can be published); the other accepted exceptions (the planner's own
  rooms, fixed-time clashes, ...) stay accepted as the run reports them.
* **Publishing** refuses a run with an unexplained finding, and a run that covers fewer weeks than the published
  one unless the caller confirms the reduction (:func:`scope_reduction`).

Imported board rows carry no request ids, so the planner-level check cannot see a clash between them; the
override registry is what makes such forced edits visible (they always need a reason).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScheduleRun, Term, User, Week

#: findings that never block publishing (a partial timetable is publishable; fallback sizes are reported)
NON_BLOCKING_RULES = frozenset({"unplaced", "missing_enrolment"})
REASON_MIN = 3


def overrides(run: ScheduleRun) -> list[dict[str, Any]]:
    return list((run.stats or {}).get("forced_overrides") or [])


def record_override(
    run: ScheduleRun,
    *,
    assignment_ids: list[int],
    request_ids: list[int],
    rules: list[str],
    conflicts: list[str],
    reason: str,
    actor: User | None,
    audit_id: int | None = None,
) -> dict[str, Any]:
    item = {
        "assignment_ids": sorted(set(assignment_ids)),
        "request_ids": sorted({int(r) for r in request_ids if r}),
        "rules": sorted(set(rules)),
        "conflicts": conflicts[:20],
        "reason": reason.strip(),
        "by": actor.id if actor is not None else None,
        "by_name": (actor.full_name or actor.username or actor.email) if actor is not None else None,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "audit_id": audit_id,
    }
    run.stats = {**(run.stats or {}), "forced_overrides": [*overrides(run), item]}
    return item


def _score(bad: int, placed: int) -> int:
    if not bad:
        return 100
    return max(0, min(99, int(100 * (1 - bad / max(1, placed)))))


def integrity(check: Any, run: ScheduleRun) -> dict[str, Any]:
    """Hard score and the findings that block publishing, from a :class:`planner_check.PlannerCheck`."""
    ovs = overrides(run)
    explained_reqs = {int(r) for o in ovs for r in o.get("request_ids") or []}
    blocking: list[Any] = []
    explained: list[Any] = []
    for f in check.findings:
        if f.rule in NON_BLOCKING_RULES:
            continue
        manual = f.cause == "manual"
        if not (f.violation or manual):
            continue  # an accepted, reported exception (D1, D2, week_split, outside_pool ...)
        if manual and explained_reqs & set(f.request_ids):
            explained.append(f)
        else:
            blocking.append(f)
    # every recorded override is a hard rule broken on purpose, seen by the planner-level check or not (board rows
    # carry no request id there): it counts against the hard score, explained or not
    bad_reqs = {r for f in [*blocking, *explained] for r in f.request_ids} | explained_reqs
    board_only = {a for o in ovs if not o.get("request_ids") for a in o.get("assignment_ids") or []}
    hard = _score(len(bad_reqs) + len(board_only), check.requests_placed or check.rows)
    return {
        "hard_score": hard,
        "blocking": [f.as_dict() for f in blocking],
        "explained": [f.as_dict() for f in explained],
        "overrides": len(ovs),
    }


async def run_weeks(session: AsyncSession, run: ScheduleRun) -> list[int]:
    """The weeks a run publishes: its horizon's weeks, every week of the term for a TERM run."""
    hp = run.horizon_params or {}
    if (run.horizon or "TERM") != "TERM":
        weeks = hp.get("weeks") or ([hp["week"]] if hp.get("week") else [])
        if weeks:
            return sorted({int(w) for w in weeks})
    idx = list((await session.execute(select(Week.index).where(Week.term_id == run.term_id))).scalars())
    if idx:
        return sorted({int(i) for i in idx})
    term = await session.get(Term, run.term_id)
    return list(range(1, int(term.week_count or 14) + 1)) if term is not None else []


async def scope_reduction(session: AsyncSession, run: ScheduleRun, active: ScheduleRun | None) -> dict[str, Any] | None:
    """``None`` when ``run`` covers every week the published ``active`` run covers; else what would be lost."""
    if active is None or active.id == run.id:
        return None
    new, old = await run_weeks(session, run), await run_weeks(session, active)
    lost = sorted(set(old) - set(new))
    if not lost:
        return None
    return {
        "code": "scope_reduction",
        "message": f"run {run.id} covers weeks {new} only; publishing it removes weeks {lost} of run {active.id} "
        "from the published timetable (send confirm_scope_reduction: true to do it anyway)",
        "message_tr": f"#{run.id} yalnız {', '.join(map(str, new))}. haftaları kapsıyor; yayımlanırsa #{active.id} "
        f"programının {len(lost)} haftası yayından kalkar",
        "active": {"run_id": active.id, "horizon": active.horizon, "weeks": old, "label": active.label},
        "new": {"run_id": run.id, "horizon": run.horizon, "weeks": new, "label": run.label},
        "weeks_lost": lost,
        "confirm_field": "confirm_scope_reduction",
    }


def valid_reason(reason: str | None) -> bool:
    return len((reason or "").strip()) >= REASON_MIN


__all__ = [
    "integrity",
    "overrides",
    "record_override",
    "run_weeks",
    "scope_reduction",
    "valid_reason",
]
