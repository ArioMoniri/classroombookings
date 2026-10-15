"""Schedule map -> baseline IMPORT run (P19-I5).

The course entries of every schedule map in a commit (a weekly board read by the fast path, an ICS feed, an
``intake.v1`` timetable, a general-path timetable) become assignments of one run per term,
``Baseline: imported schedule`` (``params.source = "COUNCIL_BASELINE"``, ``origin = "IMPORT"``). Each entry is
matched to a meeting request by ``(course key, section, day, start period)``, generalising the board importer's
link (``app/importers/weekly_grid.py``, request linking index): the course key is ASCII-folded
(``normalize.course_key``), the section is used when the entry names one, and a request whose weeks hold the
entry's week is preferred. The run is then the ``parent_run_id`` of a new solve, which keeps placements stable.

Weeks: the record's week (board sheet), else its date counted from the term's first Monday; entries outside
the term's dates are clipped (counted, not written). Exam sheets are skipped (exam boards link exam requests).

Deduplication across jobs: an assignment is keyed on its natural key (term, room, week, day, start period,
course codes), never on the job, so the same board uploaded again (in any job, any format) updates the same
rows; the run lists each source file once by its sha256 (``params.sources``).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.council import critic
from app.council.reconcile import room_key
from app.importers import normalize as n
from app.models import Assignment, Course, MeetingRequest, Room, ScheduleRun, Section, Term, Week
from app.models.base import utcnow

LABEL = "Baseline: imported schedule"
SOURCE = "COUNCIL_BASELINE"


def natural_key(term_id: int, room_id: int, week: int, day: int, start: int, codes: list[str]) -> str:
    raw = f"{room_id}|{week}|{day}|{start}|{','.join(sorted(codes))}"
    return f"CB:{term_id}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


async def _term_monday(session: AsyncSession, term: Term) -> date | None:
    from app.services.calendar import term_monday

    weeks = list((await session.execute(select(Week).where(Week.term_id == term.id))).scalars())
    return term_monday(term, weeks)


async def _baseline_run(session: AsyncSession, term: Term) -> tuple[ScheduleRun, bool]:
    run = (
        (
            await session.execute(
                select(ScheduleRun).where(
                    ScheduleRun.term_id == term.id, ScheduleRun.kind == "COURSE", ScheduleRun.label == LABEL
                )
            )
        )
        .scalars()
        .first()
    )
    if run is not None:
        return run, False
    run = ScheduleRun(
        term_id=term.id,
        kind="COURSE",
        horizon="TERM",
        status="FEASIBLE",
        label=LABEL,
        params={"source": SOURCE, "sources": []},
        hard_score=100,
        soft_score=100,
        stats={"progress": 100, "phase": "imported"},
        finished_at=utcnow(),
    )
    session.add(run)
    await session.flush()
    return run, True


async def _request_index(
    session: AsyncSession, term: Term
) -> dict[tuple[str, int, int], list[tuple[int, str, set[int]]]]:
    """(course key, day, start period) -> [(meeting request id, section label, weeks)] of the term."""
    rows = await session.execute(
        select(
            MeetingRequest.id,
            MeetingRequest.day,
            MeetingRequest.days,
            MeetingRequest.start_period,
            MeetingRequest.weeks,
            Section.label,
            Course.code,
        )  # fmt: skip
        .join(Section, Section.id == MeetingRequest.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Section.term_id == term.id, MeetingRequest.archived.is_(False))
        .order_by(MeetingRequest.id)
    )
    index: dict[tuple[str, int, int], list[tuple[int, str, set[int]]]] = {}
    for mid, day, days, sp, weeks, label, code in rows:
        if sp is None:
            continue
        for d in [day] if day else list(days or []):
            index.setdefault((n.course_key(code), int(d), int(sp)), []).append(
                (mid, str(label or ""), {int(w) for w in weeks or []})
            )
    return index


def _pick(cands: list[tuple[int, str, set[int]]], section: str | None, week: int) -> int:
    if section:
        same = [c for c in cands if c[1] == section]
        cands = same or cands
    in_week = [c for c in cands if not c[2] or week in c[2]]
    return (in_week or cands)[0][0]


async def as_baseline_run(
    session: AsyncSession,
    term: Term,
    entries: list[tuple[dict[str, Any], dict[str, Any]]],
    periods: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """``entries``: ``(booking record, {"sha256", "file", "job"})`` of the commit's schedule maps. Writes the
    baseline run (flush only; the caller commits) and returns its counts, or None when no entry is a course."""
    course = [(r, src) for r, src in entries if r.get("course_codes")]
    if not course:
        return None
    run, created = await _baseline_run(session, term)
    counts: Counter[str] = Counter()
    monday = await _term_monday(session, term)
    last = monday + timedelta(weeks=int(term.week_count or 14), days=-1) if monday else None
    if term.end_date and last:
        last = max(last, term.end_date)
    index = await _request_index(session, term)
    rooms = {r.code: r for r in (await session.execute(select(Room))).scalars()}
    existing = {
        a.source_key: a
        for a in (await session.execute(select(Assignment).where(Assignment.run_id == run.id))).scalars()
        if a.source_key
    }
    seen: set[str] = set()
    for r, _src in course:
        if str(r.get("sheet_kind") or "").upper() in ("EXAM", "MAKEUP"):
            counts["exam_entries_skipped"] += 1
            continue
        when = date.fromisoformat(r["date"]) if r.get("date") else None
        if when is not None and monday is not None and (when < monday or (last is not None and when > last)):
            counts["clipped_outside_term"] += 1
            continue
        week = r.get("week_index")
        if not week and when is not None and monday is not None:
            week = (when - monday).days // 7 + 1
        day = r.get("day") or (when.isoweekday() if when else None)
        sp = r.get("slot_start") or critic.period_index(periods, r.get("start"), "start")
        ep = r.get("slot_end") or critic.period_index(periods, r.get("end"), "end")
        room = rooms.get(room_key(r.get("room_code") or ""))
        if not week or not day or sp is None or ep is None or room is None:
            counts["entries_unplaceable"] += 1
            continue
        codes = [n.course_key(c) for c in r["course_codes"]]
        key = natural_key(term.id, room.id, int(week), int(day), int(sp), codes)
        if key in seen:
            counts["duplicates_in_commit"] += 1
            continue
        seen.add(key)
        mr_id = None
        for code in codes:
            cands = index.get((code, int(day), int(sp)))
            if cands:
                mr_id = _pick(cands, r.get("section"), int(week))
                break
        counts["linked" if mr_id else "unlinked"] += 1
        fields: dict[str, Any] = dict(
            run_id=run.id,
            meeting_request_id=mr_id,
            week=int(week),
            weeks=[int(week)],
            day=int(day),
            date=when,
            start_period=int(sp),
            end_period=max(int(ep), int(sp)),
            room_ids=[room.id],
            label=str(r.get("text") or "")[:255],
            course_codes=codes,
            tags=[],
            notes=None,
            origin="IMPORT",
            is_locked=False,
            source_key=key,
            archived=False,
        )
        a = existing.get(key)
        if a is None:
            session.add(Assignment(**fields))
            counts["created"] += 1
        else:
            changed = False
            for k, v in fields.items():
                if getattr(a, k) != v:
                    setattr(a, k, v)
                    changed = True
            counts["updated" if changed else "unchanged"] += 1
    sources = list((run.params or {}).get("sources") or [])
    known = {s.get("sha256") for s in sources}
    for _r, src in course:
        if src.get("sha256") and src["sha256"] not in known:
            known.add(src["sha256"])
            sources.append(src)
    run.params = {**(run.params or {}), "source": SOURCE, "sources": sources}
    run.stats = {**(run.stats or {}), "baseline": dict(counts)}
    await session.flush()
    return {"run_id": run.id, "run_created": created, **dict(counts)}


__all__ = ["LABEL", "SOURCE", "as_baseline_run", "natural_key"]
