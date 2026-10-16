"""Manual moves are checked with the same hard-rule evaluation that scores the run (round-1 R1-M-05).

The move dialog's server check (``calendar_views.check_candidate``) looks at the target cell: room clashes, blocks,
bookings, capacity, PC / TIP rooms, cohort and instructor clashes. The run's hard score after an edit comes from the
planner-level check (``planner_check`` + ``publish_guard.integrity``), which also knows the planner's own decisions:
a LOCKED request keeps its definitive room and its fixed time, joint lectures sit together, accepted exceptions are
reported. A move the dialog called "uygun" could therefore drop a published run from hard 100 to 99 with nothing
named (PHAR 240 §1 moved out of its locked A 206).

:func:`planner_issues` runs the planner-level check on the run *as it would be after the moves* and returns, per
moved assignment, every hard finding the moves add (blocking under ``publish_guard.integrity``: a violation or a
manual break no recorded override explains). The callers add them to the move's hard issues, so such a move is
never "uygun": a planner gets the reason, an administrator may force it with a written reason (recorded override,
counted against the hard score and listed on the run).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScheduleRun
from app.schemas.calendar import Issue, Text2

#: planner-level rules -> the move-check codes that already name the same break (no duplicate line)
COVERED: dict[str, frozenset[str]] = {
    "room_double_booking": frozenset({"room_overlap", "batch_overlap", "booking", "seats"}),
    "capacity": frozenset({"capacity", "seats"}),
    "blocked": frozenset({"block", "booking"}),
    "tags": frozenset({"pc", "tip"}),
    "cohort": frozenset({"cohort"}),
    "instructor": frozenset({"instructor"}),
    "time": frozenset({"out_of_range"}),
}
RULE_TR: dict[str, str] = {
    "locked_room": "planlayıcının kilitli dersliği",
    "time": "istenen gün / saat",
    "weeks": "dersin haftaları",
    "room_double_booking": "derslik çakışması",
    "blocked": "dolu derslik",
    "capacity": "kapasite",
    "tags": "derslik özelliği",
    "cohort": "sınıf çakışması",
    "instructor": "öğretim elemanı çakışması",
    "policy_lock_dropped": "kilitli dersin yerleşmesi",
}


@dataclass(frozen=True)
class TrialMove:
    """One moved assignment: its rows and the weeks of each that move, and the target cell."""

    base_id: int
    parts: tuple[tuple[int, tuple[int, ...]], ...]  # (assignment id, weeks moved)
    day: int
    start: int
    end: int
    rooms: tuple[int, ...]


def _key(f: Any) -> tuple[str, tuple[int, ...], str]:
    return (str(f["rule"]), tuple(sorted(int(r) for r in f["request_ids"])), str(f["message"]))


def _text(f: dict[str, Any], labels: dict[int, str]) -> Text2:
    rule = str(f["rule"])
    who = ", ".join(labels.get(int(r), f"#{r}") for r in f["request_ids"][:3])
    msg = str(f["message"])
    if rule == "locked_room":
        tr = (
            f"{who} planlama listesinde kendi dersliğine kilitli; başka dersliğe taşımak planlayıcının kilidini "
            f"bozar (kesin kural)"
        )
        en = f"{who} is locked to its own room in the planning list; moving it breaks the planner's lock (hard rule)"
    elif rule == "time":
        tr = f"{who} planlama listesinde bu gün ve saate sabit; başka saate taşımak kesin kuralı bozar"
        en = f"{who} is fixed at this day and time in the planning list; another time breaks a hard rule"
    else:
        tr = f"Kesin kural bozulur ({RULE_TR.get(rule, rule)}): {msg}"
        en = f"Breaks a hard rule ({rule.replace('_', ' ')}): {msg}"
    return Text2(tr=tr, en=en)


@dataclass
class PlannerVerdict:
    """What the moves add at planner level. ``issues``: per moved assignment id, the hard issues to show (findings
    the move check already names are left out); ``findings``: per moved assignment id, every added finding as
    ``{"rule", "request_ids", "message"}`` (recorded on a forced override, so the publish guard knows it is
    explained)."""

    issues: dict[int, list[Issue]]
    findings: dict[int, list[dict[str, Any]]]

    def for_base(self, base_id: int) -> list[Issue]:
        return self.issues.get(base_id, [])


async def planner_issues(
    session: AsyncSession,
    run: ScheduleRun,
    moves: Iterable[TrialMove],
    *,
    covered: dict[int, set[str]] | None = None,
) -> PlannerVerdict:
    """The planner-level hard findings the ``moves`` add to ``run`` (see :class:`PlannerVerdict`).

    ``covered``: per base assignment id, the codes of the hard issues the move check already reported (a planner
    finding of the same break is not repeated as an issue, but is still listed in ``findings``)."""
    from app.services import planner_check, publish_guard

    moves = list(moves)
    verdict = PlannerVerdict({}, {})
    if not moves:
        return verdict
    data = await planner_check.load(session, run)
    before = {_key(f) for f in publish_guard.integrity(planner_check.check(data), run)["blocking"]}
    rows = {r.id: r for r in data.rows}
    req_of_base: dict[int, int] = {}
    trial = dict(rows)
    fresh = -1
    for m in moves:
        for aid, weeks in m.parts:
            row = rows.get(aid)
            if row is None:
                continue  # an imported board row (no request): the cell checks cover it
            req_of_base[m.base_id] = row.req
            moved = frozenset(int(w) for w in weeks) & row.weeks if weeks else row.weeks
            if not moved:
                continue
            target = replace(
                row, day=m.day, start=m.start, end=m.end, rooms=tuple(m.rooms), origin="MANUAL", is_locked=True
            )
            if moved == row.weeks:
                trial[aid] = target
            else:
                trial[aid] = replace(row, weeks=row.weeks - moved)
                trial[fresh] = replace(target, id=fresh, weeks=moved, date=None)
                fresh -= 1
    after = publish_guard.integrity(planner_check.check(replace(data, rows=list(trial.values()))), run)["blocking"]
    added = [f for f in after if _key(f) not in before]
    if not added:
        return verdict
    labels = {rid: r.label for rid, r in data.reqs.items()}
    base_of_req = {req: base for base, req in req_of_base.items()}
    first = moves[0].base_id
    for f in added:
        reqs = [int(r) for r in f["request_ids"]]
        base = next((base_of_req[r] for r in reqs if r in base_of_req), first)
        rule = str(f["rule"])
        verdict.findings.setdefault(base, []).append(
            {"rule": rule, "request_ids": sorted(reqs), "message": str(f["message"])}
        )
        if covered and COVERED.get(rule, frozenset()) & covered.get(base, set()):
            continue
        verdict.issues.setdefault(base, []).append(
            Issue(code=f"planner:{rule}", severity="hard", text=_text(f, labels))
        )
    return verdict


__all__ = ["COVERED", "PlannerVerdict", "TrialMove", "planner_issues"]
