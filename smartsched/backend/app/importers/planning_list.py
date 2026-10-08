"""Importer for shape A: course planning request lists (`… Derslik Planlama Listesi.xlsx`, sheet Sayfa1)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_files import open_workbook, run_isolated
from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.importers.report import ImportReport
from app.importers.xlsx import iter_sheet_rows, map_headers, row_dict
from app.models import MeetingRequest, Section, SectionInstructor

HEADER_SPEC: dict[str, list[str]] = {
    "faculty": ["fakülte"],
    "program": ["bölüm/program", "program"],
    "class_year": ["=sınıf", "sınıf"],
    "semester": ["yarıyıl"],
    "code": ["ders kodu"],
    "name": ["ders adı"],
    "label": ["şube"],
    "t": ["=t"],
    "u": ["=u"],
    "l": ["=l"],
    "k": ["=k"],
    "ects": ["akts"],
    "enrolment": ["öğrenci sayısı"],
    "day": ["dersin günü", "günü"],
    "start": ["başlangıç"],
    "end": ["bitiş"],
    "request": ["derslik talebi"],
    "definitive": ["kesinleşen"],
    "ins1": ["1. öğretim elemanı"],
    "ins2": ["2. öğretim elemanı"],
    "mode": ["öğretim şekli"],
    "notes": ["özel açıklama", "açıklama"],
    "whole_term": ["dönemin tamamı"],
    "weeks": ["kullanılacağı haftalar", "haftalar"],
    "remote_pct": ["yüzdesi"],
}


@dataclass
class PlanningRow:
    row: int
    raw: dict[str, Any]
    course_code: str | None
    course_name: str | None
    faculty: str | None
    program: str | None
    class_years: list[int]
    semester: int | None
    label: str | None
    t: int | None
    u: int | None
    l: int | None
    credits: float | None
    ects: float | None
    enrolment: int | None
    day: n.DayParse
    start_time: time | None
    end_time: time | None
    periods: n.PeriodRange
    venue: n.VenueRequest
    definitive: n.DefinitiveParse
    instructors: list[str]
    secondary_instructors: list[str]
    mode: n.ModeParse
    notes: str | None
    whole_term: bool | None
    weeks: n.WeeksParse
    remote_pct: int | None
    needs_room: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def has_day_and_time(self) -> bool:
        return bool(self.day.days) and self.start_time is not None and self.end_time is not None

    @property
    def fingerprint(self) -> str:
        parts = [
            self.course_code or "",
            n.tr_casefold(self.program or ""),
            self.label or "",
            ",".join(map(str, self.day.days)),
            str(self.start_time),
            str(self.end_time),
            n.tr_casefold(self.venue.raw or ""),
            n.tr_casefold(self.definitive.raw or ""),
            ",".join(self.instructors),
            ",".join(map(str, self.class_years)),
        ]
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class CapacityEntry:
    """One room of a capacity bucket in the list's summary sheet (Bahar ``Sayfa2``)."""

    code: str
    capacity: int | None
    bucket: int  # column index of the bucket's DERSLİK column
    raw: str
    pc_lab: bool = False  # the bucket is the computer-lab bucket


@dataclass
class ParsedPlanningList:
    rows: list[PlanningRow]
    rows_total: int
    skipped: list[tuple[int, str, str | None]]
    headers: list[str | None]
    capacities: list[CapacityEntry] = field(default_factory=list)


def parse_capacity_buckets(path: str | Path, skip_sheet: int = 0) -> list[CapacityEntry]:
    """Room capacity buckets from the summary sheet(s): every ``DERSLİK`` header cell followed by a
    ``KAPASİTE`` cell starts a bucket (two columns, rooms listed downwards).  A bucket that contains a
    computer-lab nickname (``B BİLGİ LAB``) is the computer-lab bucket: all its rooms are PC labs (Bahar:
    A 103 / A 104 / A 105 / B 207, matching the summary count "Bilgisayar 4")."""
    wb = open_workbook(path, read_only=True, data_only=True, max_rows=200, max_cols=60)
    out: list[CapacityEntry] = []
    try:
        for idx, ws in enumerate(wb.worksheets):
            if idx == skip_sheet:
                continue
            grid = [list(r) for r in ws.iter_rows(min_row=1, max_row=200, max_col=60, values_only=True)]
            for r, row in enumerate(grid):
                for c in range(len(row) - 1):
                    if n.tr_casefold(n.clean_text(row[c]) or "") != "derslik":
                        continue
                    if not n.tr_casefold(n.clean_text(row[c + 1]) or "").startswith("kapasite"):
                        continue
                    bucket: list[CapacityEntry] = []
                    for below in grid[r + 1 :]:
                        raw = n.clean_text(below[c]) if c < len(below) else None
                        if raw is None:
                            break
                        codes = n.parse_room_codes(raw)
                        if len(codes) != 1:
                            continue
                        cap = n.parse_int_loose(below[c + 1]) if c + 1 < len(below) else None
                        bucket.append(CapacityEntry(codes[0], cap or None, c, raw))
                    if any(n.is_pc_lab_text(e.raw) for e in bucket):
                        for e in bucket:
                            e.pc_lab = True
                    out.extend(bucket)
    finally:
        wb.close()
    return out


def _get(values: tuple[Any, ...], mapping: dict[str, int], key: str) -> Any:
    idx = mapping.get(key)
    if idx is None or idx >= len(values):
        return None
    return values[idx]


def parse_planning_row(
    row: int, values: tuple[Any, ...], mapping: dict[str, int], headers: list[str | None], max_week: int = 14
) -> PlanningRow | tuple[str, str | None]:
    """Return a PlanningRow or (skip_reason, detail)."""

    def g(k: str) -> Any:
        return _get(values, mapping, k)

    code, code_warning = n.canon_course_code_loose(g("code"), g("name"))
    if code is None:
        raw_code = n.clean_text(g("code"))
        return ("no course code", raw_code)
    day = n.parse_day(g("day"))
    start = n.parse_time(g("start"))
    end = n.parse_time(g("end"))
    warnings: list[str] = list(day.warnings)
    if code_warning:
        warnings.append(code_warning)
    periods = n.time_range_to_periods(start, end) if (start and end) else n.PeriodRange(None, None)
    if start and end:
        warnings.extend(periods.warnings)
    elif (g("start") is not None and n.clean_text(g("start")) and start is None) and day.days:
        warnings.append(f"unparseable start time {g('start')!r}")
    venue = n.parse_venue_request(g("request"))
    definitive = n.parse_definitive_rooms(g("definitive"))
    mode = n.parse_mode(g("mode"))
    weeks = n.parse_weeks(g("weeks"), max_week=max_week)
    warnings.extend(weeks.warnings)
    whole_term = n.parse_bool_loose(g("whole_term"))
    needs_room = mode.needs_room
    if day.needs_room is False or weeks.needs_room is False or venue.needs_room is False:
        needs_room = False
    if definitive.status in {"NO_ROOM", "CANCELLED"}:
        needs_room = False
    if definitive.status == "ROOMS":
        needs_room = True
    enrol = n.parse_int_loose(g("enrolment"))
    if g("enrolment") is not None and enrol is None and n.clean_text(g("enrolment")):
        warnings.append(f"unparseable enrolment {g('enrolment')!r}")
    return PlanningRow(
        row=row,
        raw=row_dict(headers, values),
        course_code=code,
        course_name=n.clean_text(g("name")),
        faculty=n.clean_text(g("faculty")),
        program=n.clean_text(g("program")),
        class_years=n.parse_class_year(g("class_year")),
        semester=n.parse_semester(g("semester")),
        label=n.parse_section_label(g("label")),
        t=n.parse_int_loose(g("t")),
        u=n.parse_int_loose(g("u")),
        l=n.parse_int_loose(g("l")),
        credits=n.parse_float_loose(g("k")),
        ects=n.parse_float_loose(g("ects")),
        enrolment=enrol,
        day=day,
        start_time=start,
        end_time=end,
        periods=periods,
        venue=venue,
        definitive=definitive,
        instructors=n.split_person_names(g("ins1")),
        secondary_instructors=n.split_person_names(g("ins2")),
        mode=mode,
        notes=n.clean_text(g("notes")),
        whole_term=whole_term,
        weeks=weeks,
        remote_pct=n.parse_pct(g("remote_pct")),
        needs_room=needs_room,
        warnings=warnings,
    )


def parse_planning_list(path: str | Path, sheet: str | int = 0, max_week: int = 14) -> ParsedPlanningList:
    headers, rows = iter_sheet_rows(path, sheet)
    mapping = map_headers(headers, HEADER_SPEC)
    missing = [k for k in ("code", "day", "start", "end") if k not in mapping]
    if missing:
        raise ValueError(f"planning list is missing columns: {missing}; headers={headers}")
    parsed: list[PlanningRow] = []
    skipped: list[tuple[int, str, str | None]] = []
    total = 0
    for row, values in rows:
        total += 1
        res = parse_planning_row(row, values, mapping, headers, max_week)
        if isinstance(res, tuple):
            skipped.append((row, res[0], res[1]))
        else:
            parsed.append(res)
    capacities = parse_capacity_buckets(path, skip_sheet=sheet if isinstance(sheet, int) else 0)
    return ParsedPlanningList(parsed, total, skipped, headers, capacities)


async def import_planning_list(
    session: AsyncSession,
    path: str | Path,
    term_code: str,
    *,
    filename: str | None = None,
    term_name: str | None = None,
    week_count: int = 14,
) -> ImportReport:
    report = ImportReport(kind="planning-list", filename=filename or Path(path).name, term_code=term_code)
    parsed = await run_isolated(parse_planning_list, path, max_week=week_count)  # off the loop, rlimit
    report.rows_total = parsed.rows_total
    for row, reason, detail in parsed.skipped:
        report.skip(row, reason, detail)
    cat = Catalog(session, report)
    term = await cat.term(term_code, name=term_name, week_count=week_count)
    # room master facts from the summary sheet: lecture capacities + the computer-lab bucket
    for e in parsed.capacities:
        await cat.room(
            e.code, capacity=e.capacity, tags=["PC"] if e.pc_lab else None, source=f"planning-list:{report.filename}"
        )
    report.extra["capacity_buckets"] = len({e.bucket for e in parsed.capacities})
    report.extra["pc_labs"] = sorted({e.code for e in parsed.capacities if e.pc_lab})
    pc_from_text: set[str] = set()

    existing_sections = {
        s.source_key: s for s in (await session.execute(select(Section).where(Section.term_id == term.id))).scalars()
    }
    existing_meetings = {
        m.source_key: m
        for m in (
            await session.execute(select(MeetingRequest).join(Section).where(Section.term_id == term.id))
        ).scalars()
    }
    seen_fp: dict[str, int] = {}
    seen_meeting_keys: set[str] = set()
    seen_section_keys: set[str] = set()
    with_periods = 0
    with_day_time = 0

    for r in parsed.rows:
        for w in r.warnings:
            report.warn(w, r.row)
        faculty = await cat.faculty(r.faculty)
        program = await cat.program(r.program, faculty)
        course = await cat.course(
            r.course_code or "", name=r.course_name, t=r.t, u=r.u, l=r.l, credits=r.credits, ects=r.ects
        )
        section_key = f"{r.course_code}|{program.canonical_name if program else ''}|{r.label or ''}"
        section = existing_sections.get(section_key)
        class_year = r.class_years[0] if r.class_years else None
        if section is None:
            section = Section(
                term_id=term.id,
                course_id=course.id,
                program_id=program.id if program else None,
                label=r.label,
                class_year=class_year,
                class_years=r.class_years,
                semester_no=r.semester,
                enrolment=r.enrolment,
                mode=r.mode.mode,
                remote_pct=r.remote_pct,
                whole_term_in_room=r.whole_term,
                notes=r.notes,
                source_row=r.raw,
                source_key=section_key,
            )
            session.add(section)
            await session.flush()
            existing_sections[section_key] = section
            report.created["sections"] += 1
        else:
            if section_key not in seen_section_keys:
                section.enrolment = r.enrolment if r.enrolment is not None else section.enrolment
                section.mode = r.mode.mode
                section.remote_pct = r.remote_pct
                section.whole_term_in_room = r.whole_term
                section.notes = r.notes
                section.class_year = class_year
                section.class_years = r.class_years
                section.semester_no = r.semester
                section.source_row = r.raw
                section.archived = False
                report.updated["sections"] += 1
        seen_section_keys.add(section_key)

        # instructors
        for idx, text in enumerate(r.instructors + r.secondary_instructors):
            ins = await cat.instructor(text)
            if ins is None:
                continue
            role = "PRIMARY" if idx < len(r.instructors) else "SECONDARY"
            link = await session.get(SectionInstructor, (section.id, ins.id))
            if link is None:
                session.add(SectionInstructor(section_id=section.id, instructor_id=ins.id, role=role))

        fp = r.fingerprint
        occ = seen_fp.get(fp, 0)
        seen_fp[fp] = occ + 1
        mkey = f"PL:{term_code}:{fp}#{occ}"
        seen_meeting_keys.add(mkey)
        if r.has_day_and_time:
            with_day_time += 1
            if r.periods.start_period is not None:
                with_periods += 1
        requested_ids = await cat.room_ids(r.venue.room_codes, create=False)
        definitive_ids = await cat.room_ids(r.definitive.room_codes, create=True)
        # "C 202 BİLG. LAB. ZORUNLU PLANLANDI", "A 105 nolu bilgi lab": the named room is a computer lab
        for lab_text in (r.definitive.raw, r.venue.raw):
            for code in n.pc_lab_rooms(lab_text):
                room = await cat.room(code, create=False)
                if room is not None and "PC" not in (room.tags or []):
                    await cat.room(code, tags=["PC"])
                    pc_from_text.add(code)
        status = "PARSED"
        if r.definitive.status == "ROOMS":
            status = "LOCKED"
        elif r.needs_room and (not r.has_day_and_time or r.periods.start_period is None):
            status = "NEEDS_REVIEW"
        elif r.warnings:
            status = "NEEDS_REVIEW"
        fields: dict[str, Any] = dict(
            section_id=section.id,
            day=r.day.days[0] if len(r.day.days) == 1 else None,
            days=r.day.days,
            start_period=r.periods.start_period,
            end_period=r.periods.end_period,
            start_time=r.start_time,
            end_time=r.end_time,
            weeks=r.weeks.weeks,
            requested_room_text=r.venue.raw,
            requested_room_ids=requested_ids,
            requested_building=r.venue.building,
            requested_tags=r.venue.tags,
            requested_capacity=r.venue.min_capacity or r.enrolment,
            flexible_day=r.day.flexible or len(r.day.days) > 1,
            needs_room=r.needs_room,
            definitive_room_text=r.definitive.raw,
            definitive_room_ids=definitive_ids,
            status=status,
            parse_warnings=r.warnings,
            notes=_join_notes(r),
            source_key=mkey,
            source_row_index=r.row,
            archived=False,
        )
        mr = existing_meetings.get(mkey)
        if mr is None:
            mr = MeetingRequest(**fields)
            session.add(mr)
            existing_meetings[mkey] = mr
            report.created["meeting_requests"] += 1
        else:
            if mr.status == "LOCKED" and status != "LOCKED":
                fields.pop("status")  # never downgrade a planner lock
            for k, v in fields.items():
                setattr(mr, k, v)
            report.updated["meeting_requests"] += 1
        report.rows_imported += 1

    # rows absent from the new file are archived, never deleted
    for key, mr in existing_meetings.items():
        if key and key.startswith(f"PL:{term_code}:") and key not in seen_meeting_keys and not mr.archived:
            mr.archived = True
            report.updated["meeting_requests_archived"] += 1
    for key, sec in existing_sections.items():
        if key not in seen_section_keys and not sec.archived:
            sec.archived = True
            report.updated["sections_archived"] += 1

    if pc_from_text:
        report.warn(f"rooms tagged PC because a row calls them a computer lab: {', '.join(sorted(pc_from_text))}")
        report.extra["pc_labs"] = sorted({*report.extra["pc_labs"], *pc_from_text})
    await cat.finalize_rooms(lecture_side=True)
    report.extra["rows_with_day_time"] = with_day_time
    report.extra["rows_with_periods"] = with_periods
    report.extra["period_coverage"] = round(with_periods / with_day_time, 4) if with_day_time else None
    await session.commit()
    return report


def _join_notes(r: PlanningRow) -> str | None:
    parts = [p for p in (r.notes, r.day.note, r.weeks.note, r.venue.notes if r.venue.same_room_as else None) if p]
    return " | ".join(dict.fromkeys(parts)) or None
