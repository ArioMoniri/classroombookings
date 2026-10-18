"""Exams vs the class plan (adaptive scheduling AS-12; docs/research/2026-10-17-adaptive-scheduling.md §3.5).

An exam run used to see its own term's blocks and the confirmed bookings, but not the class plan: an exam dated
inside the lecture weeks of a term (a midterm, an "early final") could take a room a class holds then.

* :func:`course_blocks` (exam runs): the published (active) COURSE run of the same term, on the weeks and weekdays
  that carry an exam, becomes solver blocks.  Exam weeks (kind EXAM / MAKEUP) are not in a course run's horizon
  (AS-02), so a final in its own weeks is unaffected; a term without a published course run gives no block and
  says so in the stats.
* :func:`exam_overlaps` (course side, the reverse warning): course assignments that share a room and a time with a
  dated exam of the term's published exam run, as data-issue items (TR/EN).

Nothing here changes a stored row; the blocks only exist in the solver input.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, Room, ScheduleRun, Term, Week
from app.services.calendar import week_index_for_date
from app.services.conflicts import active_run_for_term
from app.services.exam_load import day_label
from app.services.grid import assignment_weeks
from app.solver import model as sm

STATS_KEY = "class_plan"


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


async def _rows(session: AsyncSession, run: ScheduleRun) -> list[Assignment]:
    return list(
        (
            await session.execute(
                select(Assignment)
                .where(Assignment.run_id == run.id, Assignment.archived.is_(False))
                .order_by(Assignment.id)
            )
        ).scalars()
    )


def _run_weeks(run: ScheduleRun, term: Term) -> set[int]:
    from app.services.solver_bridge import horizon_weeks

    return set(horizon_weeks(run, term))


def blocks_from_rows(rows: Iterable[Any], wanted: set[tuple[int, int]], all_weeks: set[int]) -> list[sm.Block]:
    """Blocks of course assignment rows on the wanted (week, weekday) pairs (pure; rows need ``day``,
    ``start_period``, ``end_period``, ``room_ids``, ``weeks`` / ``week``).  A row without weeks covers
    ``all_weeks`` (the run's horizon)."""
    out: set[tuple[int, int, int, int, int]] = set()
    for a in rows:
        ws = assignment_weeks(a) or all_weeks
        for w in ws:
            if (w, int(a.day)) not in wanted:
                continue
            for rid in a.room_ids or []:
                out.add((int(rid), int(w), int(a.day), int(a.start_period), int(a.end_period)))
    return [sm.Block(r, w, d, s, e) for r, w, d, s, e in sorted(out)]


async def course_blocks(
    session: AsyncSession, term: Term, weeks_rows: Sequence[Week], events: Iterable[sm.Event]
) -> tuple[list[sm.Block], dict[str, Any]]:
    """Blocks for an exam run: the class plan of ``term`` on the (week, weekday) of every dated exam event.

    Returns ``(blocks, stats)``; ``stats`` (stored as ``run.stats["class_plan"]``) names the course run, the exam
    dates checked and the number of blocks, or ``status: "not_published"`` when the term has no published course
    run while exams fall in its lecture weeks."""
    wanted: dict[tuple[int, int], set[date]] = defaultdict(set)
    for e in events:
        if e.kind != "exam" or e.fixed_date is None:
            continue
        for w in e.weeks:
            wanted[(int(w), e.fixed_date.isoweekday())].add(e.fixed_date)
    if not wanted:
        return [], {}
    course = await active_run_for_term(session, term.id, "COURSE")
    if course is None:
        return [], {"status": "not_published", "exam_dates": len({d for v in wanted.values() for d in v})}
    horizon = _run_weeks(course, term)
    pairs = {k for k in wanted if k[0] in horizon}
    if not pairs:
        return [], {"status": "no_lecture_dates", "course_run_id": course.id}
    blocks = blocks_from_rows(await _rows(session, course), pairs, horizon)
    dates = sorted({d for k in pairs for d in wanted[k]})
    return blocks, {
        "status": "applied",
        "course_run_id": course.id,
        "dates": [d.isoformat() for d in dates],
        "blocks": len(blocks),
    }


# ------------------------------------------------------------------------------------------------ course side


def overlaps(
    course_rows: Iterable[Any],
    exam_rows: Iterable[Any],
    week_of: Any,
    all_weeks: set[int],
) -> list[tuple[Any, Any, int]]:
    """(course row, exam row, week) pairs sharing a room and overlapping periods on an exam's date (pure).
    ``week_of(date) -> week | None``."""
    by_slot: dict[tuple[int, int, int], list[Any]] = defaultdict(list)  # (room, week, day) -> exam rows
    for x in exam_rows:
        if x.date is None:
            continue
        w = week_of(x.date)
        if w is None:
            continue
        for rid in x.room_ids or []:
            by_slot[(int(rid), int(w), x.date.isoweekday())].append(x)
    out: list[tuple[Any, Any, int]] = []
    if not by_slot:
        return out
    for a in course_rows:
        for w in sorted(assignment_weeks(a) or all_weeks):
            for rid in a.room_ids or []:
                for x in by_slot.get((int(rid), int(w), int(a.day)), []):
                    if a.start_period <= x.end_period and x.start_period <= a.end_period:
                        out.append((a, x, int(w)))
    return out


async def exam_overlaps(session: AsyncSession, run: ScheduleRun) -> list[dict[str, Any]]:
    """Reverse warning for a COURSE run: its classes that sit in a room a dated exam of the term's published exam
    run uses at the same time (data-issue items, group ``exam_overlap``)."""
    if (run.kind or "COURSE") != "COURSE":
        return []
    term = await session.get(Term, run.term_id)
    if term is None:
        return []
    exam_run = await active_run_for_term(session, term.id, "EXAM")
    if exam_run is None:
        return []
    weeks_rows = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
    horizon = _run_weeks(run, term)
    pairs = overlaps(
        await _rows(session, run),
        await _rows(session, exam_run),
        lambda d: week_index_for_date(term, d, weeks_rows),
        horizon,
    )
    if not pairs:
        return []
    codes = {int(i): str(c) for i, c in (await session.execute(select(Room.id, Room.code))).all()}
    items: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    for a, x, w in pairs:
        key = (a.id, x.id, w)
        if key in seen:
            continue
        seen.add(key)
        room = ", ".join(codes.get(int(r), str(r)) for r in sorted(set(a.room_ids or []) & set(x.room_ids or [])))
        lab = day_label(x.date)
        cls, ex = a.label or f"#{a.meeting_request_id}", x.label or f"#{x.exam_request_id}"
        items.append(
            {
                "code": "exam_overlap",
                "severity": "warning",
                "message_tr": (
                    f"{cls} ({room}, {a.start_period}.–{a.end_period}. ders) {w}. hafta {lab['tr']}: aynı saatte "
                    f"{ex} sınavı bu derslikte"
                ),
                "message": (
                    f"{cls} ({room}, periods {a.start_period}–{a.end_period}) week {w} {lab['en']}: the exam {ex} "
                    "uses this room at the same time"
                ),
                "suggestions": ["move the class or the exam for that date (advice only)"],
                "request_ids": [r for r in (a.meeting_request_id, x.exam_request_id) if r is not None],
                "params": {
                    "week": w,
                    "date": x.date.isoformat(),
                    "room": room,
                    "class_period": [a.start_period, a.end_period],
                    "exam_period": [x.start_period, x.end_period],
                    "exam_run_id": exam_run.id,
                    "assignment_id": a.id,
                    "exam_assignment_id": x.id,
                },
            }
        )
    return items


__all__ = ["STATS_KEY", "blocks_from_rows", "course_blocks", "exam_overlaps", "overlaps"]
