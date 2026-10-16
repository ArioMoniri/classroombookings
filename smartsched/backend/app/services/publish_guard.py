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
    findings: list[dict[str, Any]] | None = None,
    rows: list[Any] | None = None,
) -> dict[str, Any]:
    item = {
        # where the forced move put the rows: the override stops counting once none of them sits there any more
        # (the move was undone or the class moved on; round-1 R1-M-05)
        "placements": [_placement(a) for a in rows or []],
        "assignment_ids": sorted(set(assignment_ids)),
        "request_ids": sorted({int(r) for r in request_ids if r}),
        "rules": sorted(set(rules)),
        "conflicts": conflicts[:20],
        # the planner-level hard findings this forced move adds (``move_guard``): explained by this override
        "findings": [
            {"rule": str(f["rule"]), "request_ids": sorted(int(r) for r in f["request_ids"])}
            for f in (findings or [])[:50]
        ],
        "reason": reason.strip(),
        "by": actor.id if actor is not None else None,
        "by_name": (actor.full_name or actor.username or actor.email) if actor is not None else None,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "audit_id": audit_id,
    }
    run.stats = {**(run.stats or {}), "forced_overrides": [*overrides(run), item]}
    return item


def _placement(a: Any) -> dict[str, Any]:
    return {
        "id": int(a.id),
        "day": int(a.day),
        "start": int(a.start_period),
        "end": int(a.end_period),
        "rooms": sorted(int(r) for r in a.room_ids or []),
        "weeks": sorted(int(w) for w in (a.weeks or ([a.week] if a.week else []))),
    }


def active_overrides(run: ScheduleRun) -> list[dict[str, Any]]:
    """Recorded overrides whose forced placement still exists (see :func:`refresh_overrides`)."""
    return [o for o in overrides(run) if not o.get("undone_at")]


async def refresh_overrides(session: AsyncSession, run: ScheduleRun) -> int:
    """Mark the overrides whose forced placement is gone (``undone_at``): none of their rows sits where the forced
    move put it. Returns how many were marked. Overrides recorded before placements were kept stay active."""
    from app.models import Assignment

    ovs = overrides(run)
    ids = {int(p["id"]) for o in ovs if not o.get("undone_at") for p in o.get("placements") or []}
    if not ids:
        return 0
    rows = {
        a.id: _placement(a)
        for a in (
            await session.execute(select(Assignment).where(Assignment.id.in_(ids), Assignment.archived.is_(False)))
        ).scalars()
    }
    changed = 0
    out = []
    for o in ovs:
        places = o.get("placements") or []
        if places and not o.get("undone_at") and not any(rows.get(int(p["id"])) == p for p in places):
            o = {**o, "undone_at": datetime.now(UTC).isoformat(timespec="seconds")}
            changed += 1
        out.append(o)
    if changed:
        run.stats = {**(run.stats or {}), "forced_overrides": out}
    return changed


#: a planner's own decision changed by a manual move (the LOCKED row's room, a fixed time): the move re-decides it,
#: listed as a manual edit, never a broken hard rule (round-1 R1-M-05: moving a class "from week 4" stays a planner
#: task); capacity, tags, clashes, blocks and weeks broken by a manual move still count
MANUAL_DECISIONS = frozenset({"locked_room", "time"})


def _score(bad: int, placed: int) -> int:
    if not bad:
        return 100
    return max(0, min(99, int(100 * (1 - bad / max(1, placed)))))


def integrity(check: Any, run: ScheduleRun) -> dict[str, Any]:
    """Hard score and the findings that block publishing, from a :class:`planner_check.PlannerCheck`."""
    ovs = active_overrides(run)
    explained_reqs = {int(r) for o in ovs for r in o.get("request_ids") or []}
    # a forced move records the planner-level findings it adds (round-1 R1-M-05): a clash it forced on purpose is
    # explained by its override, whatever the finding's cause
    explained_keys = {
        (str(x.get("rule")), tuple(sorted(int(r) for r in x.get("request_ids") or [])))
        for o in ovs
        for x in o.get("findings") or []
    }
    blocking: list[Any] = []
    explained: list[Any] = []
    for f in check.findings:
        if f.rule in NON_BLOCKING_RULES:
            continue
        manual = f.cause == "manual"
        if not (f.violation or manual):
            continue  # an accepted, reported exception (D1, D2, week_split, outside_pool ...)
        if manual and not f.violation and f.rule in MANUAL_DECISIONS:
            continue  # the planner re-decided its own lock / time by hand (listed as a manual edit)
        key = (f.rule, tuple(sorted(int(r) for r in f.request_ids)))
        if (manual and explained_reqs & set(f.request_ids)) or key in explained_keys:
            explained.append(f)
        else:
            blocking.append(f)
    # every recorded override is a hard rule broken on purpose, seen by the planner-level check or not (board rows
    # carry no request id there): it counts against the hard score, explained or not
    # an override whose break was undone (the class moved back) no longer counts: only findings that exist now do
    # (round-1 R1-M-05 / R1-S-01: the run stayed at 99 with no rule broken after the forced clash was reverted)
    bad_reqs = {r for f in [*blocking, *explained] for r in f.request_ids} | explained_reqs
    board_only = {a for o in ovs if not o.get("request_ids") for a in o.get("assignment_ids") or []}
    hard = _score(len(bad_reqs) + len(board_only), check.requests_placed or check.rows)
    return {
        "hard_score": hard,
        "blocking": [f.as_dict() for f in blocking],
        "explained": [f.as_dict() for f in explained],
        "overrides": len(ovs),
    }


def broken_rules(integ: dict[str, Any], run: ScheduleRun, limit: int = 50) -> list[dict[str, Any]]:
    """The hard rules a run breaks right now, for every surface (run card, report, banner, audit; round-1 R1-M-05):
    each blocking or explained finding with its rule, message, requests and - when a forced move explains it - that
    override's reason, author and time. Active overrides the planner-level check cannot see (imported board rows
    without requests, a break it does not model) are listed too."""
    ovs = active_overrides(run)

    def override_for(f: dict[str, Any]) -> dict[str, Any] | None:
        key = (str(f["rule"]), tuple(sorted(int(r) for r in f["request_ids"])))
        reqs = {int(r) for r in f["request_ids"]}
        for o in reversed(ovs):
            keys = {
                (str(x.get("rule")), tuple(sorted(int(r) for r in x.get("request_ids") or [])))
                for x in o.get("findings") or []
            }
            if key in keys or reqs & {int(r) for r in o.get("request_ids") or []}:
                return dict(o)
        return None

    out: list[dict[str, Any]] = []
    for explained, items in ((False, integ.get("blocking") or []), (True, integ.get("explained") or [])):
        for f in items:
            o = override_for(f) if explained else None
            out.append(
                {
                    "rule": f["rule"],
                    "message": f["message"],
                    "request_ids": list(f["request_ids"]),
                    "explained": explained,
                    "reason": (o or {}).get("reason"),
                    "by_name": (o or {}).get("by_name"),
                    "at": (o or {}).get("at"),
                }
            )
    seen = {r for b in out for r in b["request_ids"]}
    for o in ovs:
        if not o.get("request_ids") or not seen & {int(r) for r in o.get("request_ids") or []}:
            out.append(
                {
                    "rule": ",".join(o.get("rules") or []) or "override",
                    "message": "; ".join(o.get("conflicts") or [])[:500],
                    "request_ids": [],
                    "assignment_ids": list(o.get("assignment_ids") or []),
                    "explained": True,
                    "reason": o.get("reason"),
                    "by_name": o.get("by_name"),
                    "at": o.get("at"),
                }
            )
    return out[:limit]


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
    "active_overrides",
    "broken_rules",
    "integrity",
    "refresh_overrides",
    "overrides",
    "record_override",
    "run_weeks",
    "scope_reduction",
    "valid_reason",
]
