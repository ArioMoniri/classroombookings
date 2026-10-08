"""Get-or-create helpers for reference entities, with per-import caches and created/updated counters."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.importers.report import ImportReport
from app.models import Building, Course, Faculty, Instructor, Program, Room, Term

BUILDING_NAMES = {"A": "A Blok", "B": "B Blok", "C": "C Blok", "D": "D Blok"}


class Catalog:
    def __init__(self, session: AsyncSession, report: ImportReport):
        self.s = session
        self.report = report
        self._faculties: dict[str, Faculty] = {}
        self._programs: dict[str, Program] = {}
        self._courses: dict[str, Course] = {}
        self._course_keys: dict[str, Course] | None = None
        self._instructors: dict[str, Instructor] = {}
        self._rooms: dict[str, Room] = {}
        self._buildings: dict[str, Building] = {}
        self.touched_rooms: set[str] = set()
        self.preexisting_rooms: set[str] = set()  # found in the DB (created by an earlier import)

    async def term(
        self,
        code: str,
        *,
        name: str | None = None,
        kind: str = "REGULAR",
        week_count: int = 14,
    ) -> Term:
        term = (await self.s.execute(select(Term).where(Term.code == code))).scalar_one_or_none()
        if term is None:
            term = Term(code=code, name=name or code, kind=kind, week_count=week_count)
            self.s.add(term)
            await self.s.flush()
            self.report.created["terms"] += 1
        return term

    async def building(self, letter: str) -> Building:
        letter = letter.upper()
        if letter in self._buildings:
            return self._buildings[letter]
        b = (await self.s.execute(select(Building).where(Building.code == letter))).scalar_one_or_none()
        if b is None:
            b = Building(code=letter, name=BUILDING_NAMES.get(letter, f"{letter} Blok"))
            self.s.add(b)
            await self.s.flush()
            self.report.created["buildings"] += 1
        self._buildings[letter] = b
        return b

    async def room(
        self,
        code: str,
        *,
        display_name: str | None = None,
        capacity: int | None = None,
        exam_capacity: int | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
        create: bool = True,
        source: str | None = None,
    ) -> Room | None:
        """Get or create a room.  Capacities/tags given here update the room, except that values set by
        the planner's room master CSV (``custom_fields.master``) are authoritative: a workbook never
        overwrites them (a differing value is reported as a warning)."""
        room = self._rooms.get(code)
        if room is None:
            room = (await self.s.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
            if room is not None:
                self.preexisting_rooms.add(code)
        if room is None:
            if not create:
                return None
            building = await self.building(code[0]) if code[:1].isalpha() else None
            room = Room(
                code=code,
                display_name=display_name or n.display_room_code(code),
                building_id=building.id if building else None,
                floor=_floor_of(code),
                capacity=capacity or 0,
                exam_capacity=exam_capacity or 0,
                tags=list(tags or []),
                notes=notes,
                custom_fields=_sources({}, source, capacity=capacity, exam_capacity=exam_capacity),
            )
            self.s.add(room)
            await self.s.flush()
            self.report.created["rooms"] += 1
        else:
            changed = False
            fields = dict(room.custom_fields or {})
            master = set(fields.get("master") or [])
            for attr, value in (("capacity", capacity), ("exam_capacity", exam_capacity)):
                if not value or getattr(room, attr) == value:
                    continue
                if attr in master:
                    kept = getattr(room, attr)
                    self.report.warn(f"room {code}: {source or 'import'} says {attr} {value}, room master keeps {kept}")
                    continue
                setattr(room, attr, value)
                fields = _sources(fields, source, **{attr: value})
                changed = True
            if tags:
                merged = list(dict.fromkeys([*room.tags, *tags]))
                if merged != room.tags:
                    room.tags = merged
                    changed = True
            if notes and notes != room.notes:
                room.notes = notes
                changed = True
            if changed:
                room.custom_fields = fields
                self.report.updated["rooms"] += 1
        self._rooms[code] = room
        self.touched_rooms.add(code)
        return room

    async def finalize_rooms(self, *, lecture_side: bool) -> None:
        """Reconcile the rooms this import touched (see DATA_ANALYSIS "Room master").

        * A room without a lecture capacity but with an exam-sheet capacity takes that number as its
          lecture capacity, flagged in a warning and in ``custom_fields.capacity_source`` (best available
          source; the room master CSV corrects it) — in ``lecture_side`` imports (term grid, planning
          list), and in exam imports for rooms an earlier lecture import already knew (B 207: the Bahar
          workbooks name it without a number, the Final workbook seats 60).  Rooms first seen in an exam
          workbook keep lecture capacity 0 (their exam seating says nothing about lectures).
        * A room with no capacity in any source is reported and set ``is_bookable=False`` (flag
          ``custom_fields.auto_unbookable``), never dropped silently; it becomes bookable again as soon
          as a later import or the room master gives it a capacity.
        """
        no_capacity: list[str] = []
        for code in sorted(self.touched_rooms):
            room = self._rooms[code]
            fields = dict(room.custom_fields or {})
            if (lecture_side or code in self.preexisting_rooms) and not room.capacity and room.exam_capacity:
                room.capacity = room.exam_capacity
                fields["capacity_source"] = "exam-sheet capacity (flagged: no lecture capacity found)"
                self.report.warn(
                    f"room {code}: no lecture capacity in any source; using its exam-sheet capacity "
                    f"{room.exam_capacity} (flagged, correct it in the room master)"
                )
            if (room.capacity or room.exam_capacity) and fields.get("auto_unbookable"):
                fields.pop("auto_unbookable")
                room.is_bookable = True
            elif not room.capacity and not room.exam_capacity:
                if room.is_bookable and "master" not in fields:
                    room.is_bookable = False
                    fields["auto_unbookable"] = True
                no_capacity.append(code)
            if fields != (room.custom_fields or {}):
                room.custom_fields = fields
        if no_capacity:
            self.report.warn(
                f"{len(no_capacity)} room(s) have no capacity in any source and are not bookable: "
                + ", ".join(no_capacity)
                + " (fix them with `python -m app.cli import room-master <csv>`)"
            )
            self.report.extra["rooms_without_capacity"] = no_capacity

    async def faculty(self, text: Any) -> Faculty | None:
        parsed = n.canon_faculty(text)
        if parsed is None:
            return None
        if parsed.canonical in self._faculties:
            return self._faculties[parsed.canonical]
        f = (
            await self.s.execute(select(Faculty).where(Faculty.canonical_name == parsed.canonical))
        ).scalar_one_or_none()
        if f is None:
            f = Faculty(name=parsed.name, canonical_name=parsed.canonical)
            self.s.add(f)
            await self.s.flush()
            self.report.created["faculties"] += 1
        self._faculties[parsed.canonical] = f
        return f

    async def program(self, text: Any, faculty: Faculty | None = None) -> Program | None:
        parsed = n.canon_program(text)
        if parsed is None:
            return None
        if parsed.canonical in self._programs:
            return self._programs[parsed.canonical]
        p = (
            await self.s.execute(select(Program).where(Program.canonical_name == parsed.canonical))
        ).scalar_one_or_none()
        if p is None:
            p = Program(
                name=parsed.name,
                canonical_name=parsed.canonical,
                is_evening=parsed.is_evening,
                faculty_id=faculty.id if faculty else None,
            )
            self.s.add(p)
            await self.s.flush()
            self.report.created["programs"] += 1
        elif p.faculty_id is None and faculty is not None:
            p.faculty_id = faculty.id
        self._programs[parsed.canonical] = p
        return p

    async def course(
        self,
        code: str,
        *,
        name: str | None = None,
        t: int | None = None,
        u: int | None = None,
        l: int | None = None,
        credits: float | None = None,
        ects: float | None = None,
    ) -> Course:
        c = self._courses.get(code)
        if c is None:
            c = (await self.s.execute(select(Course).where(Course.code == code))).scalar_one_or_none()
        if c is None:
            # one course per code key: ``SYS 18`` and ``SYS 018`` are the same lecture (comparison R1); the
            # course keeps the spelling it was first imported with (``display_code``)
            c = (await self._course_by_key()).get(n.course_key(code))
        if c is None:
            c = Course(
                code=code,
                display_code=n.display_course_code(code),
                name=name,
                t_hours=t,
                u_hours=u,
                l_hours=l,
                credits=credits,
                ects=ects,
            )
            self.s.add(c)
            await self.s.flush()
            self.report.created["courses"] += 1
            (await self._course_by_key()).setdefault(n.course_key(code), c)
        else:
            if name and not c.name:
                c.name = name
            if c.t_hours is None and t is not None:
                c.t_hours, c.u_hours, c.l_hours = t, u, l
            if c.credits is None and credits is not None:
                c.credits = credits
            if c.ects is None and ects is not None:
                c.ects = ects
        self._courses[code] = c
        return c

    async def _course_by_key(self) -> dict[str, Course]:
        """Course code key (:func:`normalize.course_key`) -> course, loaded once per import."""
        if self._course_keys is None:
            self._course_keys = {}
            for c in (await self.s.execute(select(Course).order_by(Course.id))).scalars():
                self._course_keys.setdefault(n.course_key(c.code), c)
        return self._course_keys

    async def instructor(self, text: Any) -> Instructor | None:
        parsed = n.canon_person_name(text)
        if parsed is None:
            return None
        if parsed.canonical in self._instructors:
            return self._instructors[parsed.canonical]
        i = (
            await self.s.execute(select(Instructor).where(Instructor.canonical_name == parsed.canonical))
        ).scalar_one_or_none()
        if i is None:
            i = Instructor(full_name=parsed.full_name, canonical_name=parsed.canonical, title=parsed.title)
            self.s.add(i)
            await self.s.flush()
            self.report.created["instructors"] += 1
        self._instructors[parsed.canonical] = i
        return i

    async def room_ids(self, codes: list[str], create: bool = True) -> list[int]:
        ids: list[int] = []
        for code in codes:
            r = await self.room(code, create=create)
            if r is not None:
                ids.append(r.id)
        return ids


def _sources(fields: dict[str, Any], source: str | None, **values: int | None) -> dict[str, Any]:
    """Record which import set a capacity (``custom_fields.sources = {"capacity": "...", ...}``)."""
    if not source:
        return fields
    out = dict(fields)
    src = dict(out.get("sources") or {})
    for k, v in values.items():
        if v:
            src[k] = source
    if src:
        out["sources"] = src
    return out


def _floor_of(code: str) -> str | None:
    digits = code[1:]
    if not digits:
        return None
    if digits[:1].upper() == "Z":
        return "0"
    return digits[0] if digits[0].isdigit() else None
