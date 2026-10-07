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
        self._instructors: dict[str, Instructor] = {}
        self._rooms: dict[str, Room] = {}
        self._buildings: dict[str, Building] = {}

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
    ) -> Room | None:
        room = self._rooms.get(code)
        if room is None:
            room = (await self.s.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
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
            )
            self.s.add(room)
            await self.s.flush()
            self.report.created["rooms"] += 1
        else:
            changed = False
            if capacity and room.capacity != capacity:
                room.capacity = capacity
                changed = True
            if exam_capacity and room.exam_capacity != exam_capacity:
                room.exam_capacity = exam_capacity
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
                self.report.updated["rooms"] += 1
        self._rooms[code] = room
        return room

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


def _floor_of(code: str) -> str | None:
    digits = code[1:]
    if not digits:
        return None
    if digits[:1].upper() == "Z":
        return "0"
    return digits[0] if digits[0].isdigit() else None
