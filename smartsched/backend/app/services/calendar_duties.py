"""CAL-13 "Sınav görevlerim": a person's invigilation duties and own exams on the calendar engine
(``calendar_classes``; docs/research/2026-10-17-calendar-export.md §3, ROADMAP CAL-13).

What it holds, per exam term:

* the **duties** of the term's active invigilation plan (``invigilation_plans.is_active``): one event per post (a
  room at one time of one date) with the instructors on it (``invigilation_duties.instructor_id``). When the term
  has a published EXAM run, only the plan of that run counts (a plan of a replaced exam timetable never reaches a
  calendar);
* the person's **own exams** in the active EXAM run: the exam list's instructor cell matched to instructor records
  with the invigilation service's own rules (:func:`app.services.invigilation.match_exam_people`: exact canonical
  name, folded Turkish letters / titles, initials, a middle name left out; two candidates are never guessed).
  An own exam that the person also invigilates in the same room and time is shown once, as the duty.

Who sees what: ``Instructor.user_id`` -> the linked instructor ids (P19-L1), the same rule as ``my_classes``.

Stable identity: ``exam-<sha1(term | key | date | ordinal)[:20]>@smartsched`` with ``key`` = ``p:<post key>``
for a duty (``<date>|<room>|<start>-<end>``, stable across re-solves while the exams stay put) or
``e:<exam request ids>`` for an own exam (a room change keeps it). The rows live in ``calendar_class_revisions``
with the term id, apart from the class rows by the ``exam-`` prefix, so SEQUENCE, LAST-MODIFIED and the
CANCELLED tombstones work as for classes (a duty that leaves the published plan is sent once as cancelled).

Fields (KVKK Art. 4, minimisation): course code(s), room, time, department and, as the administrator allows, the
course title and a SmartSched link. Never the other invigilators' names, students, counts or notes.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import (
    Assignment,
    CalendarClassRevision,
    Course,
    ExamRequest,
    Instructor,
    InvigilationDuty,
    InvigilationPlan,
    Program,
    Room,
    ScheduleRun,
    Term,
)
from app.services import calendar_classes as cc
from app.services.bookings_export import IcsEvent

DUTY_LABEL = "Gözetmenlik"
EXAM_LABEL = "Sınav"
#: at most this many course codes in a title ("BME 419, PSY 262, PSY 263 +2")
MAX_CODES = 3


def exam_uid(term_id: int, key: str, day: date, ordinal: int) -> str:
    raw = f"{term_id}|{key}|{day.isoformat()}|{ordinal}"
    return f"{cc.EXAM_UID_PREFIX}{hashlib.sha1(raw.encode()).hexdigest()[:20]}@{cc.UID_HOST}"  # noqa: S324 - an id


def _codes_text(codes: tuple[str, ...]) -> str:
    shown = ", ".join(codes[:MAX_CODES])
    return shown + (f" +{len(codes) - MAX_CODES}" if len(codes) > MAX_CODES else "")


def _clock(sp: int, ep: int) -> tuple[time, time]:
    """The invigilation screen's clock (``calendar_views.clock``: the period grid)."""
    from app.services.calendar_views import clock

    return (
        datetime.strptime(clock(sp), "%H:%M").time(),
        datetime.strptime(clock(ep, True), "%H:%M").time(),
    )


# --------------------------------------------------------------------------------------------------
# What is published
# --------------------------------------------------------------------------------------------------


async def published(session: AsyncSession) -> list[tuple[int, ScheduleRun | None, InvigilationPlan | None]]:
    """``(term id, active EXAM run, active invigilation plan)`` per term with either, plus the terms that still have
    live exam rows (so a withdrawn plan ends them). The plan of a term with a published EXAM run must belong to that
    run."""
    runs = {
        r.term_id: r
        for r in (
            await session.execute(
                select(ScheduleRun)
                .where(ScheduleRun.is_active.is_(True), ScheduleRun.kind == "EXAM")
                .order_by(ScheduleRun.id)
            )
        ).scalars()
    }
    plans: dict[int, InvigilationPlan] = {}
    for p in (
        await session.execute(
            select(InvigilationPlan).where(InvigilationPlan.is_active.is_(True)).order_by(InvigilationPlan.id)
        )
    ).scalars():
        run = runs.get(p.term_id)
        if run is not None and p.exam_run_id != run.id:
            continue
        plans[p.term_id] = p
    live = {
        int(t)
        for t in (
            await session.execute(
                select(CalendarClassRevision.term_id)
                .where(CalendarClassRevision.uid.like(cc.EXAM_UID_PREFIX + "%"), CalendarClassRevision.ended_at.is_(None))
                .distinct()
            )
        ).scalars()
    }
    return [(t, runs.get(t), plans.get(t)) for t in sorted(set(runs) | set(plans) | live)]


async def _owners(session: AsyncSession, exams: dict[int, ExamRequest]) -> dict[str, int]:
    """Canonical exam-list name -> instructor id (the invigilation service's matching tiers)."""
    from app.services import invigilation as inv_svc

    owners = {k: k for er in exams.values() for k, _ in inv_svc.person_keys(er.instructor_text)}
    if not owners:
        return {}
    instructors = list((await session.execute(select(Instructor).where(Instructor.archived.is_(False)))).scalars())
    found = inv_svc.match_exam_people(owners, instructors)
    return {key: iid for iid, key in found.key_of.items()}


def _fp(item: dict[str, Any], kind: str) -> str:
    return cc._fingerprint(
        {
            "kind": kind,
            "date": item["start"].date().isoformat(),
            "start": item["start"].isoformat(),
            "end": item["end"].isoformat(),
            "rooms": list(item["rooms"]),
            "room_ids": list(item["room_ids"]),
            "codes": list(item["codes"]),
            "title": item["title"],
            "departments": list(item["departments"]),
            "program_ids": list(item["program_ids"]),
            "instructor_ids": list(item["instructor_ids"]),
            "status": "CONFIRMED",
        }
    )


async def term_occurrences(
    session: AsyncSession, term_id: int, run: ScheduleRun | None, plan: InvigilationPlan | None
) -> list[cc.ClassOccurrence]:
    """The duty posts of ``plan`` and the owned exams of ``run`` (both may be ``None``) as viewer-independent
    occurrences."""
    from app.services import invigilation as inv_svc
    from app.services.calendar_views import ints

    if run is None and plan is None:
        return []
    exams = {er.id: er for er in (await session.execute(select(ExamRequest).where(ExamRequest.term_id == term_id))).scalars()}
    display: dict[str, str] = {}
    names: dict[str, str] = {}
    for code, disp, cname in (await session.execute(select(Course.code, Course.display_code, Course.name))).all():
        k = n.course_key(code)
        if disp:
            display.setdefault(k, disp)
        if cname:
            names.setdefault(k, cname)
    programs = dict((await session.execute(select(Program.id, Program.name))).all())
    room_names = dict((await session.execute(select(Room.id, Room.display_name))).all())

    def describe(eids: list[int]) -> dict[str, Any]:
        ers = [exams[e] for e in eids if e in exams]
        keys = sorted({n.course_key(er.course_code) for er in ers if er.course_code})
        codes = tuple(display.get(k, n.clean_text(k) or k) for k in keys)
        titles = {n.clean_text(er.course_name) or names.get(n.course_key(er.course_code), "") for er in ers} - {""}
        pids = tuple(sorted({int(er.program_id) for er in ers if er.program_id}))
        return {
            "codes": codes,
            "title": next(iter(titles)) if len(titles) == 1 else None,
            "program_ids": pids,
            "departments": tuple(programs[p] for p in pids if p in programs),
        }

    raw: list[dict[str, Any]] = []
    if plan is not None:
        posts: dict[str, dict[str, Any]] = {}
        for d in (
            await session.execute(
                select(InvigilationDuty).where(InvigilationDuty.plan_id == plan.id).order_by(InvigilationDuty.id)
            )
        ).scalars():
            g = posts.setdefault(
                d.post_key,
                {"date": d.date, "sp": d.start_period, "ep": d.end_period, "room": d.room_id, "eids": set(), "ins": set()},
            )
            g["eids"] |= set(ints(d.exam_request_ids))
            if d.instructor_id is not None:
                g["ins"].add(int(d.instructor_id))
        for post_key, g in posts.items():
            if not g["ins"]:
                continue  # staff only: nobody with an account to show it to
            t0, t1 = _clock(g["sp"], g["ep"])
            rids = (int(g["room"]),) if g["room"] else ()
            info = describe(sorted(g["eids"]))
            raw.append(
                {
                    "kind": "duty",
                    "key": f"p:{post_key}",
                    "start": datetime.combine(g["date"], t0),
                    "end": datetime.combine(g["date"], t1),
                    "room_ids": rids,
                    "rooms": tuple(room_names.get(r, f"#{r}") for r in rids),
                    "instructor_ids": tuple(sorted(g["ins"])),
                    **info,
                }
            )
    if run is not None:
        owner_of = await _owners(session, exams)
        groups: dict[tuple[date, int, int, str], dict[str, Any]] = {}
        for a in (
            await session.execute(
                select(Assignment)
                .where(Assignment.run_id == run.id, Assignment.archived.is_(False), Assignment.exam_request_id.is_not(None))
                .order_by(Assignment.id)
            )
        ).scalars():
            er = exams.get(int(a.exam_request_id or 0))
            day = (a.date or er.date) if er is not None else None
            if er is None or day is None:
                continue
            g = groups.setdefault(
                (day, a.start_period, a.end_period, n.course_key(er.course_code)), {"eids": set(), "rooms": []}
            )
            g["eids"].add(er.id)
            g["rooms"] += [int(r) for r in ints(a.room_ids) if int(r) not in g["rooms"]]
        for (day, sp, ep, _ck), g in groups.items():
            ins = {owner_of[k] for e in g["eids"] for k, _ in inv_svc.person_keys(exams[e].instructor_text) if k in owner_of}
            if not ins:
                continue
            t0, t1 = _clock(sp, ep)
            rids = tuple(g["rooms"])
            raw.append(
                {
                    "kind": "exam",
                    "key": "e:" + "+".join(str(e) for e in sorted(g["eids"])),
                    "start": datetime.combine(day, t0),
                    "end": datetime.combine(day, t1),
                    "room_ids": rids,
                    "rooms": tuple(room_names.get(r, f"#{r}") for r in rids),
                    "instructor_ids": tuple(sorted(ins)),
                    **describe(sorted(g["eids"])),
                }
            )
    ordinal: dict[tuple[str, date], int] = defaultdict(int)
    out: list[cc.ClassOccurrence] = []
    for item in sorted(raw, key=lambda x: (x["key"], x["start"], x["room_ids"])):
        if item["end"] <= item["start"]:
            item["end"] = item["start"] + timedelta(minutes=40)
        day = item["start"].date()
        idx = ordinal[(item["key"], day)]
        ordinal[(item["key"], day)] += 1
        word = DUTY_LABEL if item["kind"] == "duty" else EXAM_LABEL
        out.append(
            cc.ClassOccurrence(
                uid=exam_uid(term_id, item["key"], day, idx),
                term_id=term_id,
                run_id=run.id if run is not None else (plan.exam_run_id if plan is not None else 0),
                assignment_id=0,
                week=None,
                start=item["start"],
                end=item["end"],
                room_ids=item["room_ids"],
                rooms=item["rooms"],
                codes=item["codes"],
                section=None,
                title=item["title"],
                program_ids=item["program_ids"],
                departments=item["departments"],
                instructor_ids=item["instructor_ids"],
                fingerprint=_fp(item, item["kind"]),
                label=f"{word} · {_codes_text(item['codes'])}" if item["codes"] else word,
            )
        )
    out.sort(key=lambda o: (o.start, o.uid))
    return out


async def snapshots(session: AsyncSession) -> list[cc.TermSnapshot]:
    """Refreshed exam / invigilation snapshots of every term with a published EXAM run or invigilation plan (and the
    terms whose rows must end). A concurrent refresh that stored the same rows first wins (this one runs again)."""
    out: list[cc.TermSnapshot] = []
    for term_id, run, plan in await published(session):
        for attempt in (1, 2):
            try:
                occs = await term_occurrences(session, term_id, run, plan)
                out.append(await cc.persist_revisions(session, term_id, occs, exam=True))
                break
            except IntegrityError:
                await session.rollback()
                if attempt == 2:
                    raise
    return out


def is_duty(o: cc.ClassOccurrence) -> bool:
    return (o.label or "").startswith(DUTY_LABEL)


def _same_slot(a: cc.ClassOccurrence, b: cc.ClassOccurrence) -> bool:
    return a.start < b.end and b.start < a.end and bool(set(a.room_ids) & set(b.room_ids))


async def select_duties(
    session: AsyncSession,
    instructor_ids: frozenset[int],
    d_from: date,
    d_to: date,
    *,
    grace_days: int,
    snaps: list[cc.TermSnapshot] | None = None,
) -> cc.ClassSelection:
    """The person's duties and own exams between ``d_from`` and ``d_to`` (plus tombstones in the grace period); an
    own exam the person invigilates in the same room and time is left to the duty event."""
    if not instructor_ids:
        return cc.ClassSelection([], [])
    flt = cc.ScopeFilter(instructor_ids=instructor_ids)
    snaps = snaps if snaps is not None else await snapshots(session)
    sel = await cc.select_classes(session, flt, d_from, d_to, grace_days=grace_days, snaps=snaps)
    duties = [o for o, _ in sel.live if is_duty(o)]
    live = [(o, r) for o, r in sel.live if is_duty(o) or not any(_same_slot(o, d) for d in duties)]
    return cc.ClassSelection(live, sel.tombstones)


def duty_context(ctx: cc.EventContext) -> cc.EventContext:
    """Never the other invigilators' or teachers' names, whatever the class field setting says."""
    return replace(ctx, fields=replace(ctx.fields, co_instructors=False))


async def duty_events(
    session: AsyncSession,
    instructor_ids: frozenset[int],
    d_from: date,
    d_to: date,
    *,
    grace_days: int,
    ctx: cc.EventContext | None = None,
) -> list[IcsEvent]:
    ctx = duty_context(ctx or cc.EventContext())
    sel = await select_duties(session, instructor_ids, d_from, d_to, grace_days=grace_days)
    out = [cc.occurrence_event(o, r, ctx) for o, r in sel.live] + [cc.tombstone_event(r) for r in sel.tombstones]
    out.sort(key=lambda e: (e.start, e.uid))
    return out


def horizon(today: date) -> date:
    return today + timedelta(days=cc.CLASS_HORIZON_DAYS)


async def term_slug(session: AsyncSession) -> str:
    """``2026-final`` for the file name: the newest term with a published EXAM run or invigilation plan."""
    terms = [t for t, run, plan in await published(session) if run is not None or plan is not None]
    if not terms:
        return "takvim"
    term = await session.get(Term, terms[-1])
    return cc.ascii_slug(term.code if term is not None else None)
