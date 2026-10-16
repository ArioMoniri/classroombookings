"""One source of truth for a run's verdict and counts (round-1 R1-M-04 / R1-M-05).

The Studio run card said "691/713 ders yerleşti · hiçbir kural bozulmadı" while the report next to it listed 303
clashing and 78 over-capacity classes and also said "Yerleşen her ders bütün kurallara uyuyor"; the card, the report
and the API counted differently (the grid's per-row flags counted the members of one joint lecture as clashing with
each other, and the planner's accepted exceptions as rule breaks).

:func:`run_truth` is the only place that decides what the product says about a finished run. It reads the
planner-level check (``planner_check``, the independent validator of the stored rows) and the publish integrity
(``publish_guard.integrity``: violations and manual breaks, explained by a recorded override or not):

* ``placed`` / ``total`` / ``unplaced``: the solver's classes (``stats.placed`` / ``events_total``; a joint lecture
  is one class), the same numbers on the card, the report and the API;
* ``broken``: every hard rule the stored timetable breaks right now (``publish_guard.broken_rules``) - a forced move
  with its reason is listed, never hidden; ``hard_score`` is the integrity score;
* ``exceptions``: the accepted exceptions the run reports, by cause, each with its planner-facing label and the
  number of classes (the planner's own too-small room, two classes the planner fixed at the same time, rooms outside
  the pool ...). They are not "no rule broken": the verdict names them;
* ``verdict``: ``broken`` (a hard rule is broken), ``exceptions`` (every hard rule held except the listed accepted
  exceptions), ``clean`` (nothing to list), ``none`` (no timetable);
* ``headline``: the one TR / EN sentence every surface shows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScheduleRun

#: statuses with a stored timetable the verdict talks about
WITH_TIMETABLE = frozenset({"OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL", "TIMEOUT"})
#: accepted-exception causes shown in the verdict (``D3`` = unplaced is its own count; ``manual`` breaks are
#: ``broken``; a fallback size for a missing enrolment is a data note, listed but not a rule exception)
CAUSE_LABELS: dict[str, dict[str, str]] = {
    "D1": {
        "tr": "planlayıcının kilitlediği derslik sınıfa küçük ya da özelliği eksik "
        "(planlama listesindeki seçim korundu)",
        "en": "the planner's locked room is too small or lacks a feature (kept as the planning list says)",
    },
    "D2": {
        "tr": "planlama listesinde aynı saate sabitlenmiş iki dersin çakışması (ikisi de saatini korur)",
        "en": "two classes the planning list fixes at the same time clash (both keep their times)",
    },
    "week_split": {
        "tr": "kilitli ders, dersliğinin kapalı olduğu haftalarda başka derslikte",
        "en": "a locked class uses another room in the weeks its room is blocked",
    },
    "outside_pool": {
        "tr": "derslik havuzu dışındaki dersliklerde çakışma (kapasitesi bilinmiyor)",
        "en": "overlaps in rooms outside the room pool (capacity unknown)",
    },
    "manual": {
        "tr": "elle taşınan ders: planlama listesindeki dersliği ya da saati planlayıcı değiştirdi",
        "en": "moved by hand: the planner changed the room or time of the planning list",
    },
    "missing_enrolment": {
        "tr": "öğrenci sayısı verilmemiş; tahmini sayı kullanıldı",
        "en": "no enrolment given; a fallback size was used",
    },
}
RULE_EXCEPTIONS: tuple[str, ...] = ("D1", "D2", "week_split", "outside_pool", "manual")


def _n(v: int, lang: str) -> str:
    s = f"{v:,}"
    return s.replace(",", ".") if lang == "tr" else s


def headline(truth: dict[str, Any]) -> dict[str, str]:
    """The run's one sentence from its truth (card, report, summary, run list)."""
    verdict = truth["verdict"]
    placed, total = truth.get("placed"), truth.get("total")
    if verdict == "none":
        return {"tr": "Bu çalıştırmanın çizelgesi yok.", "en": "This run has no timetable."}
    if total and placed is not None and placed < total:
        lead = {
            "tr": f"{_n(placed, 'tr')}/{_n(total, 'tr')} ders yerleşti",
            "en": f"{_n(placed, 'en')} of {_n(total, 'en')} classes placed",
        }
    else:
        n = total or placed or 0
        lead = {"tr": f"Bütün dersler yerleşti ({_n(n, 'tr')})", "en": f"Every class placed ({_n(n, 'en')})"}
    if verdict == "broken":
        b = truth["broken_count"]
        forced = sum(1 for x in truth["broken"] if x.get("explained"))
        tail_tr = f"{_n(b, 'tr')} kesin kural bozuk" + (
            f" ({_n(forced, 'tr')} gerekçeli zorunlu taşıma)" if forced else ""
        )
        tail_en = f"{_n(b, 'en')} hard rule(s) broken" + (
            f" ({_n(forced, 'en')} forced with a reason)" if forced else ""
        )
        return {"tr": f"{lead['tr']} · {tail_tr}", "en": f"{lead['en']} · {tail_en}"}
    if verdict == "exceptions":
        k = truth["exceptions_total"]
        return {
            "tr": f"{lead['tr']} · kesin kurallar korundu; {_n(k, 'tr')} kabul edilmiş istisna listelendi",
            "en": f"{lead['en']} · hard rules held; {_n(k, 'en')} accepted exception(s) listed",
        }
    return {"tr": f"{lead['tr']} · hiçbir kural bozulmadı", "en": f"{lead['en']} · no rule broken"}


def edited(run: ScheduleRun) -> bool:
    """Moved or forced by hand since the solver stored it (the publish guard then re-checks it at planner level)."""
    from app.services import publish_guard

    return bool((run.stats or {}).get("manual_edits")) or bool(publish_guard.overrides(run))


def build(run: ScheduleRun, check: Any, *, status: str | None = None) -> dict[str, Any]:
    """The truth of ``run`` from its planner-level check (pure; see the module docstring). ``status``: the status
    the run is about to get (the worker computes the truth before it commits the result).

    Like the publish guard (``runs.publish_blockers``): a run edited by hand is judged by the integrity check (a
    manual break counts, explained by an override or not); an unedited run by its planner-level violations (a
    manual placement carried from the parent run is an accepted exception the run reports)."""
    from app.services import publish_guard

    status = status or run.status
    stats = run.stats or {}
    placed = stats.get("placed")
    total = stats.get("events_total")
    placed_i = int(placed) if isinstance(placed, int | float) else None
    total_i = int(total) if isinstance(total, int | float) else None
    if status not in WITH_TIMETABLE:
        out: dict[str, Any] = {
            "source": "planner_check",
            "verdict": "none",
            "placed": placed_i,
            "total": total_i,
            "unplaced": None,
            "hard_score": run.hard_score,
            "broken": [],
            "broken_count": 0,
            "exceptions": [],
            "exceptions_total": 0,
        }
        out["headline"] = headline(out)
        return out
    is_edited = edited(run)
    if is_edited:
        integ = publish_guard.integrity(check, run)
        broken = publish_guard.broken_rules(integ, run, limit=200)
        hard = int(integ["hard_score"])
    else:
        broken = [
            {**f.as_dict(), "explained": False, "reason": None, "by_name": None, "at": None}
            for f in check.violations
            if f.rule not in publish_guard.NON_BLOCKING_RULES
        ][:200]
        hard = int(check.hard_score)
    by_cause: dict[str, set[int]] = {}
    findings_by_cause: dict[str, int] = {}
    for f in check.exceptions:
        if f.cause == "D3" or (f.cause == "manual" and is_edited and f.rule not in publish_guard.MANUAL_DECISIONS):
            continue  # unplaced is its own count; a manual break of an edited run is ``broken``
        by_cause.setdefault(str(f.cause), set()).update(int(r) for r in f.request_ids)
        findings_by_cause[str(f.cause)] = findings_by_cause.get(str(f.cause), 0) + 1
    exceptions: list[dict[str, Any]] = [
        {
            "cause": c,
            "classes": len(by_cause[c]),
            "findings": findings_by_cause[c],
            "rule": c in RULE_EXCEPTIONS,
            "label": CAUSE_LABELS.get(c, {"tr": c, "en": c}),
        }
        for c in (*RULE_EXCEPTIONS, "missing_enrolment")
        if c in by_cause
    ]
    rule_exc = sum(int(x["classes"]) for x in exceptions if x["rule"])
    if placed_i is None:
        placed_i = check.requests_placed
        total_i = check.requests_total
    out = {
        "source": "planner_check",
        "placed": placed_i,
        "total": total_i,
        "unplaced": max(0, (total_i or 0) - (placed_i or 0)),
        "requests": {"placed": check.requests_placed, "total": check.requests_total},
        "hard_score": hard,
        "edited": is_edited,
        "broken": broken,
        "broken_count": len(broken),
        "exceptions": exceptions,
        "exceptions_total": rule_exc,
        "forced_overrides": len(publish_guard.overrides(run)),
        "verdict": "broken" if broken else ("exceptions" if rule_exc else "clean"),
    }
    out["headline"] = headline(out)
    return out


async def run_truth(
    session: AsyncSession, run: ScheduleRun, check: Any | None = None, *, status: str | None = None
) -> dict[str, Any]:
    """The truth of ``run`` (computes the planner-level check unless given)."""
    if (status or run.status) not in WITH_TIMETABLE:
        return build(run, None, status=status)
    if check is None:
        from app.services.planner_check import check_run

        check = await check_run(session, run)
    return build(run, check, status=status)


__all__ = ["CAUSE_LABELS", "WITH_TIMETABLE", "build", "edited", "headline", "run_truth"]
