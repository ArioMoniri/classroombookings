"""Published class occurrences for calendar export (CAL-01…CAL-05; docs/research/2026-10-17-calendar-export.md §3).

One engine feeds every channel: the subscription links (``/calendar/feeds/{token}/classes.ics``, the department,
room and room-group feeds), the one-off ``.ics`` files and the push connectors. It reads the **published** (active)
COURSE run of a term only, never a draft or a what-if.

Stable identity (§3.3). A class occurrence's UID is ``class-<sha1(term | key | week | ordinal)[:20]>@smartsched``:
``key`` is the meeting request (``r:<id>``) or, for an imported board row without one, its course code(s)
(``c:PSY262``); ``week`` is the teaching week of the date; ``ordinal`` tells two meetings of the same key in one
week apart (by date, start period, row). It contains no run id, assignment id or room, so a re-publish, a room move
or a move to another day of the same week keeps it.

Revisions (``calendar_class_revisions``): the fingerprint covers date, start, end, rooms, codes, section, title,
departments, teachers and status; a change bumps SEQUENCE and LAST-MODIFIED. An occurrence that leaves the published
plan gets ``ended_at`` (+1 SEQUENCE) and is sent as ``STATUS:CANCELLED`` for ``feed_cancelled_grace_days``; a scope
the occurrence left (another room, another teacher) gets the same tombstone, from the ``seen`` sets. The first
refresh of a term also stores the pre-0039 UIDs (``class-{assignment}-{room}-{date}@smartsched``) as cancelled
``legacy`` rows, so a room or department feed subscribed before tells its calendar once to drop them.

Fields (KVKK Art. 4, minimisation): course code, section, room, start / end and department; the course title, the
other teachers' names and a SmartSched link only as the administrator allows (``integrations.export_field_*``;
co-teachers off by default). Never students, counts, notes or the board text.

Who may export a department (owner decision 2026-10-17): the person's own department (``users.department_id``),
a department of a section they teach, or holders of ``calendar.department_feed``.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import (
    Assignment,
    BookingPeriod,
    CalendarClassRevision,
    Course,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
    Term,
    User,
)
from app.models.base import utcnow
from app.services.bookings_export import IcsEvent

#: published classes are listed up to this far ahead (the rest of a term; research §3.8: to term end, max 200 days)
CLASS_HORIZON_DAYS = 200
UID_HOST = "smartsched"

SCOPE_MY_CLASSES = "my_classes"
SCOPE_DEPARTMENT = "department_classes"
SCOPE_MY_BOOKINGS = "my_bookings"
SCOPE_ROOM = "room"
SCOPE_ROOM_GROUP = "room_group"
SCOPE_KINDS = (SCOPE_MY_CLASSES, SCOPE_DEPARTMENT, SCOPE_MY_BOOKINGS, SCOPE_ROOM, SCOPE_ROOM_GROUP)
#: scopes that need an id (``scope_id``)
SCOPES_WITH_ID = frozenset({SCOPE_DEPARTMENT, SCOPE_ROOM, SCOPE_ROOM_GROUP})
#: the new permission (bookings_perms; "Bölüm ders takvimini dışa aktarma")
DEPARTMENT_PERMISSION = "calendar.department_feed"

SCOPE_LABELS: dict[str, tuple[str, str]] = {
    SCOPE_MY_CLASSES: ("Derslerim", "My classes"),
    SCOPE_DEPARTMENT: ("Bölümümün dersleri", "My department's classes"),
    SCOPE_MY_BOOKINGS: ("Rezervasyonlarım", "My bookings"),
    SCOPE_ROOM: ("Derslik takvimi", "Room calendar"),
    SCOPE_ROOM_GROUP: ("Derslik grubu takvimi", "Room group calendar"),
}

#: what an event may carry (research §2.5); the administrator turns the optional ones on or off
FIELD_KEYS = ("course_code", "section", "room", "time", "department", "course_title", "co_instructors", "link")
FIELD_LABELS: dict[str, tuple[str, str]] = {
    "course_code": ("Ders kodu", "Course code"),
    "section": ("Şube", "Section"),
    "room": ("Derslik", "Room"),
    "time": ("Gün ve saat", "Day and time"),
    "department": ("Bölüm adı", "Department name"),
    "course_title": ("Ders adı", "Course title"),
    "co_instructors": ("Diğer öğretim elemanlarının adları", "Other instructors' names"),
    "link": ("SmartSched bağlantısı", "SmartSched link"),
}


class ScopeError(Exception):
    """A refused export: ``status``, ``code``, English and Turkish text (``as_detail`` for the API)."""

    def __init__(self, status: int, code: str, en: str, tr: str, **extra: Any) -> None:
        super().__init__(en)
        self.status, self.code, self.en, self.tr, self.extra = status, code, en, tr, extra

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.en, "message_en": self.en, "message_tr": self.tr, **self.extra}


def not_linked_error() -> ScopeError:
    return ScopeError(
        409,
        "not_linked",
        "Your account is not linked to an instructor record; ask the planning office.",
        "Hesabınız bir öğretim elemanı kaydına bağlı değil; planlama ofisine başvurun.",
    )


def department_not_allowed_error(program_id: int, name: str | None = None) -> ScopeError:
    what = name or f"#{program_id}"
    return ScopeError(
        403,
        "department_not_allowed",
        f"You may not export the classes of {what}. Ask your head of department.",
        "Bu bölümün derslerini dışa aktarma yetkiniz yok. Bölüm başkanınızdan isteyin.",
        department_id=program_id,
        permission=DEPARTMENT_PERMISSION,
    )


# --------------------------------------------------------------------------------------------------
# Occurrences
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassOccurrence:
    """One meeting of a class on one date in the published plan (viewer-independent)."""

    uid: str
    term_id: int
    run_id: int
    assignment_id: int
    week: int | None
    start: datetime  # local, naive
    end: datetime
    room_ids: tuple[int, ...]
    rooms: tuple[str, ...]
    codes: tuple[str, ...]
    section: str | None
    title: str | None
    program_ids: tuple[int, ...]
    departments: tuple[str, ...]
    instructor_ids: tuple[int, ...]
    fingerprint: str
    legacy_uids: tuple[tuple[int, str], ...] = ()  # (room id, pre-0039 UID) per room

    @property
    def location(self) -> str:
        return ", ".join(self.rooms)

    def summary(self) -> str:
        what = " / ".join(self.codes) or "Ders"
        return f"{what} · Şube {self.section}" if self.section else what


def class_uid(term_id: int, key: str, week: int | str, ordinal: int) -> str:
    digest = hashlib.sha1(f"{term_id}|{key}|{week}|{ordinal}".encode()).hexdigest()[:20]  # noqa: S324 - an id
    return f"class-{digest}@{UID_HOST}"


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


async def course_runs(session: AsyncSession, term_ids: set[int] | None = None) -> list[ScheduleRun]:
    """The published COURSE runs (one per term at most)."""
    q = select(ScheduleRun).where(ScheduleRun.is_active.is_(True), ScheduleRun.kind == "COURSE")
    if term_ids is not None:
        q = q.where(ScheduleRun.term_id.in_(sorted(term_ids)))
    return list((await session.execute(q.order_by(ScheduleRun.term_id, ScheduleRun.id))).scalars())


async def _period_clock(session: AsyncSession, term_id: int) -> Any:
    """``(start_period, end_period) -> (time_start, time_end)`` from the term's booking periods, else the grid."""
    from app.services.bookings_calendar import term_info
    from app.services.calendar import period_times

    term = await session.get(Term, term_id)
    info = await term_info(session, term) if term is not None else None
    starts: dict[int, time] = {}
    ends: dict[int, time] = {}
    if info is not None and info.default_schedule_id:
        for p in (
            await session.execute(select(BookingPeriod).where(BookingPeriod.schedule_id == info.default_schedule_id))
        ).scalars():
            starts.setdefault(p.start_period, p.time_start)
            ends.setdefault(p.end_period, p.time_end)

    def clock(sp: int, ep: int) -> tuple[time, time]:
        if sp in starts and ep in ends:
            return starts[sp], ends[ep]
        s_txt, e_txt = period_times(sp, ep)
        return datetime.strptime(s_txt, "%H:%M").time(), datetime.strptime(e_txt, "%H:%M").time()

    return clock


async def term_occurrences(session: AsyncSession, term: Term, run: ScheduleRun) -> list[ClassOccurrence]:
    """Every published class meeting of ``term`` (``run`` = its active COURSE run), dates from the shared
    occupancy engine (``bookings.timetable_occupancy``: weeks, dated rows), one occurrence per row and date."""
    from app.services import bookings as booking_svc
    from app.services.bookings_calendar import term_info
    from app.services.calendar import week_index_for_date

    info = await term_info(session, term)
    if info is None:
        return []
    occ = await booking_svc.timetable_occupancy(session, None, info.start, info.end)
    grouped: dict[tuple[int, date], dict[str, Any]] = {}
    for helds in occ.values():
        for h in helds:
            if h.kind != "timetable" or h.run_id != run.id:
                continue
            g = grouped.setdefault((h.ref_id, h.date), {"rooms": set(), "start": h.start, "end": h.end})
            g["rooms"].add(h.room_id)
    if not grouped:
        return []
    assigns = {
        a.id: a
        for a in (
            await session.execute(
                select(Assignment).where(Assignment.run_id == run.id, Assignment.archived.is_(False))
            )
        ).scalars()
    }
    # sections of the term (course, label, department) and their teachers
    sections: dict[int, dict[str, Any]] = {}
    by_course: dict[str, list[int]] = defaultdict(list)
    for sid, label, program_id, code, disp, cname in (
        await session.execute(
            select(Section.id, Section.label, Section.program_id, Course.code, Course.display_code, Course.name)
            .join(Course, Course.id == Section.course_id)
            .where(Section.term_id == term.id, Section.archived.is_(False))
        )
    ).all():
        key = n.course_key(code)
        sections[sid] = {"label": label, "program_id": program_id, "key": key, "display": disp, "name": cname}
        by_course[key].append(sid)
    teachers: dict[int, set[int]] = defaultdict(set)
    for sid, iid in (
        await session.execute(
            select(SectionInstructor.section_id, SectionInstructor.instructor_id)
            .join(Section, Section.id == SectionInstructor.section_id)
            .where(Section.term_id == term.id)
        )
    ).all():
        teachers[sid].add(int(iid))
    mr_section = dict(
        (
            await session.execute(
                select(MeetingRequest.id, MeetingRequest.section_id)
                .join(Section, Section.id == MeetingRequest.section_id)
                .where(Section.term_id == term.id)
            )
        ).all()
    )
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
    clock = await _period_clock(session, term.id)

    raw: list[dict[str, Any]] = []
    for (aid, d), g in grouped.items():
        a = assigns.get(aid)
        if a is None:
            continue
        order = [int(r) for r in (a.room_ids or [])]
        rids = tuple([r for r in order if r in g["rooms"]] + sorted(g["rooms"] - set(order)))
        sec_ids: list[int] = []
        if a.meeting_request_id and a.meeting_request_id in mr_section:
            key = f"r:{a.meeting_request_id}"
            sec_ids = [int(mr_section[a.meeting_request_id])]
            course_keys = [sections[sec_ids[0]]["key"]] if sec_ids[0] in sections else []
        else:
            course_keys = list(dict.fromkeys(n.course_key(c) for c in (a.course_codes or []) if c))
            key = "c:" + "+".join(sorted(course_keys)) if course_keys else "l:" + (n.clean_text(a.label) or str(aid))
            sec_ids = [s for k in course_keys for s in by_course.get(k, [])]
        secs = [sections[s] for s in sec_ids if s in sections]
        codes = tuple(dict.fromkeys(display.get(k, k) for k in course_keys)) or (
            (n.clean_text(a.label),) if a.label else ()
        )
        labels = {s["label"] for s in secs if s["label"]}
        section = next(iter(labels)) if len(secs) == 1 and len(labels) == 1 else None
        titles = {names[k] for k in course_keys if k in names}
        title = next(iter(titles)) if len(titles) == 1 else None
        pids = tuple(sorted({int(s["program_id"]) for s in secs if s["program_id"]}))
        iids = tuple(sorted({i for s in sec_ids for i in teachers.get(s, set())}))
        t0, t1 = clock(g["start"], g["end"])
        start, end = datetime.combine(d, t0), datetime.combine(d, t1)
        if end <= start:
            end = start + timedelta(minutes=40)
        week = week_index_for_date(term, d, info.weeks)
        raw.append(
            {
                "key": key,
                "week": week if week is not None else d.isoformat(),
                "sort": (d, g["start"], aid),
                "a": a,
                "date": d,
                "start": start,
                "end": end,
                "room_ids": rids,
                "rooms": tuple(room_names.get(r, f"#{r}") for r in rids),
                "codes": codes,
                "section": section,
                "title": title,
                "program_ids": pids,
                "departments": tuple(programs[p] for p in pids if p in programs),
                "instructor_ids": iids,
            }
        )
    ordinal: dict[tuple[str, Any], int] = defaultdict(int)
    out: list[ClassOccurrence] = []
    for item in sorted(raw, key=lambda x: (x["key"], str(x["week"]), x["sort"])):
        slot = (item["key"], item["week"])
        idx = ordinal[slot]
        ordinal[slot] += 1
        fp = _fingerprint(
            {
                "date": item["date"].isoformat(),
                "start": item["start"].isoformat(),
                "end": item["end"].isoformat(),
                "rooms": list(item["rooms"]),
                "room_ids": list(item["room_ids"]),
                "codes": list(item["codes"]),
                "section": item["section"],
                "title": item["title"],
                "departments": list(item["departments"]),
                "program_ids": list(item["program_ids"]),
                "instructor_ids": list(item["instructor_ids"]),
                "status": "CONFIRMED",
            }
        )
        a = item["a"]
        out.append(
            ClassOccurrence(
                uid=class_uid(term.id, item["key"], item["week"], idx),
                term_id=term.id,
                run_id=run.id,
                assignment_id=a.id,
                week=item["week"] if isinstance(item["week"], int) else None,
                start=item["start"],
                end=item["end"],
                room_ids=item["room_ids"],
                rooms=item["rooms"],
                codes=item["codes"],
                section=item["section"],
                title=item["title"],
                program_ids=item["program_ids"],
                departments=item["departments"],
                instructor_ids=item["instructor_ids"],
                fingerprint=fp,
                legacy_uids=tuple((r, f"class-{a.id}-{r}-{item['date']:%Y%m%d}@{UID_HOST}") for r in item["room_ids"]),
            )
        )
    out.sort(key=lambda o: (o.start, o.uid))
    return out


# --------------------------------------------------------------------------------------------------
# Revisions
# --------------------------------------------------------------------------------------------------


@dataclass
class TermSnapshot:
    term_id: int
    occurrences: list[ClassOccurrence]
    #: uid -> revision (live and ended; legacy rows are not loaded here)
    revisions: dict[str, CalendarClassRevision] = field(default_factory=dict)


def _seen(prev: dict[str, Any] | None, o: ClassOccurrence) -> dict[str, list[int]]:
    prev = prev or {}
    return {
        "rooms": sorted({int(x) for x in prev.get("rooms") or []} | set(o.room_ids)),
        "programs": sorted({int(x) for x in prev.get("programs") or []} | set(o.program_ids)),
        "instructors": sorted({int(x) for x in prev.get("instructors") or []} | set(o.instructor_ids)),
    }


def _row_values(o: ClassOccurrence) -> dict[str, Any]:
    return {
        "fingerprint": o.fingerprint,
        "program_id": o.program_ids[0] if o.program_ids else None,
        "program_ids": list(o.program_ids),
        "instructor_ids": list(o.instructor_ids),
        "room_ids": list(o.room_ids),
        "starts_at": o.start,
        "ends_at": o.end,
        "summary": o.summary()[:255],
        "location": o.location[:255],
    }


async def refresh_term(session: AsyncSession, term: Term, run: ScheduleRun) -> TermSnapshot:
    """Compare the published plan of ``term`` with its stored revisions and persist the differences (new rows at
    SEQUENCE 0, changed fingerprints +1, vanished occurrences ended +1, returning ones re-opened +1). Commits when
    something changed; a concurrent refresh that stored the same rows first wins (the refresh then runs again)."""
    for attempt in (1, 2):
        try:
            return await _refresh_term(session, term, run)
        except IntegrityError:
            await session.rollback()
            if attempt == 2:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


async def _refresh_term(session: AsyncSession, term: Term, run: ScheduleRun) -> TermSnapshot:
    now = utcnow().replace(microsecond=0)
    occs = await term_occurrences(session, term, run)
    rows = {
        r.uid: r
        for r in (
            await session.execute(
                select(CalendarClassRevision).where(
                    CalendarClassRevision.term_id == term.id, CalendarClassRevision.legacy.is_(False)
                )
            )
        ).scalars()
    }
    first_time = (
        not rows
        and (
            await session.execute(
                select(CalendarClassRevision.uid).where(CalendarClassRevision.term_id == term.id).limit(1)
            )
        ).first()
        is None
    )
    new_rows: list[dict[str, Any]] = []
    present: set[str] = set()
    dirty = False
    snap = TermSnapshot(term.id, occs)
    for o in occs:
        present.add(o.uid)
        r = rows.get(o.uid)
        if r is None:
            values = {
                "uid": o.uid,
                "term_id": term.id,
                "sequence": 0,
                "last_modified": now,
                "ended_at": None,
                "seen": _seen(None, o),
                "legacy": False,
                **_row_values(o),
            }
            new_rows.append(values)
            snap.revisions[o.uid] = CalendarClassRevision(**values)  # transient: inserted below in bulk
            continue
        if r.fingerprint != o.fingerprint or r.ended_at is not None:
            for k, v in _row_values(o).items():
                setattr(r, k, v)
            r.seen = _seen(r.seen, o)
            r.sequence, r.last_modified, r.ended_at = r.sequence + 1, now, None
            dirty = True
        snap.revisions[o.uid] = r
    for uid, r in rows.items():
        if uid in present:
            continue
        if r.ended_at is None:
            r.ended_at, r.sequence, r.last_modified = now, r.sequence + 1, now
            dirty = True
        snap.revisions[uid] = r
    legacy_rows: list[dict[str, Any]] = []
    if first_time:
        for o in occs:
            for room_id, old in o.legacy_uids:
                legacy_rows.append(
                    {
                        "uid": old,
                        "term_id": term.id,
                        "sequence": 1,
                        "last_modified": now,
                        "ended_at": now,
                        "seen": {"rooms": [room_id], "programs": list(o.program_ids), "instructors": []},
                        "legacy": True,
                        **_row_values(o),
                        "room_ids": [room_id],
                        "instructor_ids": [],
                    }
                )
    for chunk_rows in (new_rows, legacy_rows):
        for i in range(0, len(chunk_rows), 500):
            await session.execute(insert(CalendarClassRevision), chunk_rows[i : i + 500])
            dirty = True
    if dirty:
        await session.commit()
    return snap


async def snapshots(session: AsyncSession, d_from: date, d_to: date) -> list[TermSnapshot]:
    """Refreshed snapshots of the terms with a published COURSE run that overlap ``d_from``…``d_to``."""
    from app.services.bookings_calendar import term_info

    out: list[TermSnapshot] = []
    for run in await course_runs(session):
        term = await session.get(Term, run.term_id)
        if term is None:
            continue
        info = await term_info(session, term)
        if info is None or info.end < d_from or info.start > d_to:
            continue
        out.append(await refresh_term(session, term, run))
    return out


async def refresh_all(session: AsyncSession) -> int:
    """Refresh every term with a published run (the integrations worker after a publish / move); the number of
    occurrences."""
    total = 0
    for run in await course_runs(session):
        term = await session.get(Term, run.term_id)
        if term is not None:
            total += len((await refresh_term(session, term, run)).occurrences)
    return total


# --------------------------------------------------------------------------------------------------
# Scopes
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeFilter:
    """Which occurrences a feed shows: by teacher (``my_classes``), department, or rooms (room / room-group feeds).
    ``visible_room``: rooms the viewer may see (``None`` = no room check)."""

    instructor_ids: frozenset[int] | None = None
    program_id: int | None = None
    room_ids: frozenset[int] | None = None
    include_legacy: bool = False

    def live(self, o: ClassOccurrence) -> bool:
        if self.instructor_ids is not None and not (set(o.instructor_ids) & self.instructor_ids):
            return False
        if self.program_id is not None and self.program_id not in o.program_ids:
            return False
        return not (self.room_ids is not None and not (set(o.room_ids) & self.room_ids))

    def current(self, r: CalendarClassRevision) -> bool:
        if self.instructor_ids is not None and not ({int(x) for x in r.instructor_ids or []} & self.instructor_ids):
            return False
        if self.program_id is not None and self.program_id not in {int(x) for x in r.program_ids or []}:
            return False
        return not (self.room_ids is not None and not ({int(x) for x in r.room_ids or []} & self.room_ids))

    def seen(self, r: CalendarClassRevision) -> bool:
        s = r.seen or {}
        if self.instructor_ids is not None and not ({int(x) for x in s.get("instructors") or []} & self.instructor_ids):
            return False
        if self.program_id is not None and self.program_id not in {int(x) for x in s.get("programs") or []}:
            return False
        return not (self.room_ids is not None and not ({int(x) for x in s.get("rooms") or []} & self.room_ids))


async def linked_instructor_ids(session: AsyncSession, user_id: int) -> list[int]:
    """The instructor records linked to the account (P19-L1 ``Instructor.user_id``)."""
    q = select(Instructor.id).where(Instructor.user_id == user_id).order_by(Instructor.id)
    return [int(i) for i in (await session.execute(q)).scalars()]


async def taught_program_ids(session: AsyncSession, instructor_ids: list[int]) -> set[int]:
    if not instructor_ids:
        return set()
    q = (
        select(Section.program_id)
        .join(SectionInstructor, SectionInstructor.section_id == Section.id)
        .where(SectionInstructor.instructor_id.in_(instructor_ids), Section.program_id.is_not(None))
        .distinct()
    )
    return {int(p) for p in (await session.execute(q)).scalars() if p is not None}


async def department_rule(session: AsyncSession, access: Any) -> tuple[bool, set[int]]:
    """``(every department allowed, the allowed ids otherwise)`` for ``access`` (owner decision 2026-10-17).
    ``planning.view`` holders (the planning office) read every published timetable on /timetable already, so they
    pass as well; it exposes nothing new."""
    if access.can(DEPARTMENT_PERMISSION) or access.can("planning.view"):
        return True, set()
    user: User = access.user
    allowed = await taught_program_ids(session, await linked_instructor_ids(session, user.id))
    if user.department_id:
        allowed.add(int(user.department_id))
    return False, allowed


async def department_allowed(session: AsyncSession, access: Any, program_id: int) -> bool:
    everything, ids = await department_rule(session, access)
    return everything or program_id in ids


# --------------------------------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fields:
    """The optional event fields (admin settings ``integrations.export_field_*``)."""

    course_title: bool = True
    department: bool = True
    co_instructors: bool = False
    link: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "course_code": True,
            "section": True,
            "room": True,
            "time": True,
            "department": self.department,
            "course_title": self.course_title,
            "co_instructors": self.co_instructors,
            "link": self.link,
        }


async def fields_setting(session: AsyncSession) -> Fields:
    from app.services.bookings_settings import get_group

    g = await get_group(session, "integrations")
    return Fields(
        course_title=bool(g.get("export_field_course_title", True)),
        department=bool(g.get("export_field_department", True)),
        co_instructors=bool(g.get("export_field_co_instructors", False)),
        link=bool(g.get("export_field_link", True)),
    )


@dataclass
class EventContext:
    fields: Fields = field(default_factory=Fields)
    #: the viewer's own instructor ids (left out of the co-teacher list)
    own_instructor_ids: frozenset[int] = frozenset()
    #: the panel URL for the DESCRIPTION link ("" = none)
    base_url: str = ""
    names: dict[int, str] = field(default_factory=dict)


def description(o: ClassOccurrence, ctx: EventContext) -> str | None:
    lines: list[str] = []
    if ctx.fields.course_title and o.title:
        lines.append(o.title)
    if ctx.fields.department and o.departments:
        lines.append("Bölüm: " + ", ".join(o.departments))
    if ctx.fields.co_instructors:
        others = [ctx.names[i] for i in o.instructor_ids if i not in ctx.own_instructor_ids and i in ctx.names]
        if others:
            lines.append("Öğretim elemanları: " + ", ".join(others))
    if ctx.fields.link and ctx.base_url:
        lines.append(f"SmartSched: {ctx.base_url}/profile")
    return "\n".join(lines) or None


def occurrence_event(o: ClassOccurrence, rev: CalendarClassRevision | None, ctx: EventContext) -> IcsEvent:
    seq = rev.sequence if rev is not None else 0
    stamp = (rev.last_modified if rev is not None else utcnow()).replace(microsecond=0)
    return IcsEvent(
        uid=o.uid,
        start=o.start,
        end=o.end,
        summary=o.summary(),
        location=o.location,
        description=description(o, ctx),
        status="CONFIRMED",
        sequence=seq,
        last_modified=stamp,
    )


def tombstone_event(r: CalendarClassRevision) -> IcsEvent:
    return IcsEvent(
        uid=r.uid,
        start=r.starts_at,
        end=r.ends_at,
        summary=r.summary,
        location=r.location,
        description=None,
        status="CANCELLED",
        sequence=r.sequence,
        last_modified=r.last_modified.replace(microsecond=0),
    )


async def _instructor_names(session: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    q = select(Instructor.id, Instructor.full_name).where(Instructor.id.in_(sorted(ids)))
    return {int(i): str(nm) for i, nm in (await session.execute(q)).all()}


@dataclass
class ClassSelection:
    """What a scope shows: the live occurrences (with their revision) and the tombstones."""

    live: list[tuple[ClassOccurrence, CalendarClassRevision | None]]
    tombstones: list[CalendarClassRevision]

    @property
    def newest(self) -> datetime | None:
        stamps = [r.last_modified for _, r in self.live if r is not None] + [r.last_modified for r in self.tombstones]
        return max(stamps) if stamps else None


async def select_classes(
    session: AsyncSession,
    flt: ScopeFilter,
    d_from: date,
    d_to: date,
    *,
    grace_days: int,
    room_visible: Any = None,
) -> ClassSelection:
    """The occurrences of ``flt`` between ``d_from`` and ``d_to`` plus the tombstones still within the grace
    period; ``room_visible(room_id) -> bool`` drops occurrences in rooms the viewer may not see."""
    cutoff = utcnow() - timedelta(days=max(0, grace_days))
    lo, hi = datetime.combine(d_from, time.min), datetime.combine(d_to, time.max)
    live: list[tuple[ClassOccurrence, CalendarClassRevision | None]] = []
    tombs: list[CalendarClassRevision] = []
    for snap in await snapshots(session, d_from, d_to):
        for o in snap.occurrences:
            if not (lo <= o.start <= hi) or not flt.live(o):
                continue
            if room_visible is not None and not any(room_visible(r) for r in o.room_ids):
                continue
            live.append((o, snap.revisions.get(o.uid)))
        for r in snap.revisions.values():
            if r.last_modified < cutoff or not (lo <= r.starts_at <= hi):
                continue
            if (r.ended_at is not None or not flt.current(r)) and (flt.seen(r) or flt.current(r)):
                tombs.append(r)
        if flt.include_legacy:
            q = select(CalendarClassRevision).where(
                CalendarClassRevision.term_id == snap.term_id,
                CalendarClassRevision.legacy.is_(True),
                CalendarClassRevision.last_modified >= cutoff,
                CalendarClassRevision.starts_at.between(lo, hi),
            )
            tombs += [r for r in (await session.execute(q)).scalars() if flt.seen(r)]
    return ClassSelection(live, tombs)


async def class_events(
    session: AsyncSession,
    flt: ScopeFilter,
    d_from: date,
    d_to: date,
    *,
    grace_days: int,
    ctx: EventContext | None = None,
    room_visible: Any = None,
) -> list[IcsEvent]:
    ctx = ctx or EventContext()
    sel = await select_classes(session, flt, d_from, d_to, grace_days=grace_days, room_visible=room_visible)
    if ctx.fields.co_instructors and not ctx.names:
        ctx.names = await _instructor_names(session, {i for o, _ in sel.live for i in o.instructor_ids})
    out = [occurrence_event(o, r, ctx) for o, r in sel.live] + [tombstone_event(r) for r in sel.tombstones]
    out.sort(key=lambda e: (e.start, e.uid))
    return out


async def horizon_end(session: AsyncSession, today: date) -> date:
    """To the end of the published terms, at most :data:`CLASS_HORIZON_DAYS` ahead (research §3.8)."""
    from app.services.bookings_calendar import term_info

    cap = today + timedelta(days=CLASS_HORIZON_DAYS)
    ends: list[date] = []
    for run in await course_runs(session):
        term = await session.get(Term, run.term_id)
        info = await term_info(session, term) if term is not None else None
        if info is not None and info.end >= today:
            ends.append(info.end)
    return min(cap, max(ends)) if ends else cap


def ascii_slug(text: str | None) -> str:
    """``2026-BAHAR`` -> ``2026-bahar``; Turkish letters folded (İ/ı -> i, ş -> s, ğ -> g, ü -> u, ö -> o, ç -> c)."""
    raw = n.clean_text(text) or ""
    table = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g", "Ü": "u", "ü": "u",
                           "Ö": "o", "ö": "o", "Ç": "c", "ç": "c"})  # fmt: skip
    folded = raw.translate(table).lower()
    out = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in folded)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "takvim"
