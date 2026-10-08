"""Importer for shape B: exam planning request lists (`… Final Planlama Listesi.xlsx`)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date as date_
from datetime import time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.importers.catalog import Catalog
from app.importers.report import ImportReport
from app.importers.xlsx import iter_sheet_rows, map_headers, row_dict
from app.models import ExamRequest

HEADER_SPEC: dict[str, list[str]] = {
    "faculty": ["fakülte"],
    "program": ["bölüm/program", "program"],
    "class_year": ["=sınıf", "sınıf"],
    "code": ["ders kodu"],
    "name": ["ders adı"],
    "enrolment": ["öğr. sayısı", "öğrenci sayısı"],
    "instructor": ["öğretim elemanı"],
    "date": ["sınav tarihi", "tarih"],
    "start": ["başlangıç"],
    "end": ["bitiş"],
    "venue": ["yapılacağı yer", "talep"],
    "definitive": ["kesinleşen"],
    "on_campus": ["kampüste"],
    "no_exam": ["yapılmayacak"],
}


@dataclass
class ExamRow:
    row: int
    raw: dict[str, Any]
    course_code: str | None
    course_name: str | None
    faculty: str | None
    program: str | None
    class_years: list[int]
    enrolment: int | None
    instructor: str | None
    date: date_ | None
    date_end: date_ | None
    start_time: time | None
    end_time: time | None
    periods: n.PeriodRange
    venue: n.VenueRequest
    definitive: n.DefinitiveParse
    on_campus_written: bool
    no_exam: bool
    needs_room: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def merge_key(self) -> str | None:
        if not self.course_code or self.date is None or self.start_time is None:
            return None
        return f"{self.course_code}:{self.date.isoformat()}:{self.start_time:%H%M}"

    @property
    def fingerprint(self) -> str:
        parts = [
            self.course_code or "",
            n.tr_casefold(self.program or ""),
            ",".join(map(str, self.class_years)),
            str(self.date),
            str(self.start_time),
            str(self.end_time),
            n.tr_casefold(self.instructor or ""),
        ]
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class ParsedExamList:
    rows: list[ExamRow]
    rows_total: int
    skipped: list[tuple[int, str, str | None]]


def parse_exam_row(
    row: int, values: tuple[Any, ...], mapping: dict[str, int], headers: list[str | None]
) -> ExamRow | tuple[str, str | None]:
    def g(k: str) -> Any:
        idx = mapping.get(k)
        return values[idx] if idx is not None and idx < len(values) else None

    code, code_warning = n.canon_course_code_loose(g("code"), g("name"))
    if code is None:
        return ("no course code", n.clean_text(g("code")))
    warnings: list[str] = [code_warning] if code_warning else []
    d, d_end = n.parse_date_range(g("date"))
    start = n.parse_time(g("start"))
    end = n.parse_time(g("end"))
    periods = n.time_range_to_periods(start, end) if (start and end) else n.PeriodRange(None, None)
    if start and end:
        warnings.extend(periods.warnings)
    raw_date = n.clean_text(g("date"))
    if raw_date and d is None:
        warnings.append(f"unparseable exam date {raw_date!r}")
    if d_end:
        warnings.append(f"exam date range {d}..{d_end}; using first day")
    venue = n.parse_venue_request(g("venue"))
    definitive = n.parse_definitive_rooms(g("definitive"))
    no_exam = n.clean_text(g("no_exam")) is not None
    on_campus = n.clean_text(g("on_campus")) is not None
    needs_room = not no_exam
    if definitive.status in {"NO_ROOM", "CANCELLED"} or venue.needs_room is False:
        needs_room = False
    if definitive.status == "ROOMS":
        needs_room = True
    if raw_date and n.tr_casefold(raw_date) in {"uzem", "yok", "online"}:
        needs_room = False
    return ExamRow(
        row=row,
        raw=row_dict(headers, values),
        course_code=code,
        course_name=n.clean_text(g("name")),
        faculty=n.clean_text(g("faculty")),
        program=n.clean_text(g("program")),
        class_years=n.parse_class_year(g("class_year")),
        enrolment=n.parse_int_loose(g("enrolment")),
        instructor=n.clean_text(g("instructor")),
        date=d,
        date_end=d_end,
        start_time=start,
        end_time=end,
        periods=periods,
        venue=venue,
        definitive=definitive,
        on_campus_written=on_campus,
        no_exam=no_exam,
        needs_room=needs_room,
        warnings=warnings,
    )


def parse_exam_list(path: str | Path, sheet: str | int = 0) -> ParsedExamList:
    headers, rows = iter_sheet_rows(path, sheet)
    mapping = map_headers(headers, HEADER_SPEC)
    missing = [k for k in ("code", "date", "start") if k not in mapping]
    if missing:
        raise ValueError(f"exam list is missing columns: {missing}; headers={headers}")
    parsed: list[ExamRow] = []
    skipped: list[tuple[int, str, str | None]] = []
    total = 0
    for row, values in rows:
        total += 1
        res = parse_exam_row(row, values, mapping, headers)
        if isinstance(res, tuple):
            skipped.append((row, res[0], res[1]))
        else:
            parsed.append(res)
    return ParsedExamList(parsed, total, skipped)


async def import_exam_list(
    session: AsyncSession,
    path: str | Path,
    term_code: str,
    *,
    filename: str | None = None,
    term_name: str | None = None,
    term_kind: str = "FINAL",
) -> ImportReport:
    report = ImportReport(kind="exam-list", filename=filename or Path(path).name, term_code=term_code)
    parsed = parse_exam_list(path)
    report.rows_total = parsed.rows_total
    for row, reason, detail in parsed.skipped:
        report.skip(row, reason, detail)
    cat = Catalog(session, report)
    term = await cat.term(term_code, name=term_name, kind=term_kind, week_count=3)
    existing = {
        e.source_key: e
        for e in (await session.execute(select(ExamRequest).where(ExamRequest.term_id == term.id))).scalars()
    }
    seen_fp: dict[str, int] = {}
    seen_keys: set[str] = set()
    merge_groups: dict[str, int] = {}
    for r in parsed.rows:
        for w in r.warnings:
            report.warn(w, r.row)
        faculty = await cat.faculty(r.faculty)
        program = await cat.program(r.program, faculty)
        await cat.course(r.course_code or "", name=r.course_name)
        occ = seen_fp.get(r.fingerprint, 0)
        seen_fp[r.fingerprint] = occ + 1
        key = f"EX:{term_code}:{r.fingerprint}#{occ}"
        seen_keys.add(key)
        mk = f"{term_code}:{r.merge_key}" if r.merge_key else None
        if mk:
            merge_groups[mk] = merge_groups.get(mk, 0) + 1
        status = "PARSED"
        if r.definitive.status == "ROOMS":
            status = "LOCKED"
        elif r.needs_room and (r.date is None or r.periods.start_period is None):
            status = "NEEDS_REVIEW"
        fields: dict[str, Any] = dict(
            term_id=term.id,
            course_code=r.course_code,
            course_name=r.course_name,
            program_id=program.id if program else None,
            faculty_text=r.faculty,
            class_year=r.class_years[0] if r.class_years else None,
            class_years=r.class_years,
            enrolment=r.enrolment,
            instructor_text=r.instructor,
            date=r.date,
            date_end=r.date_end,
            start_time=r.start_time,
            end_time=r.end_time,
            start_period=r.periods.start_period,
            end_period=r.periods.end_period,
            requested_venue_text=r.venue.raw,
            requested_room_ids=await cat.room_ids(r.venue.room_codes, create=False),
            requested_building=r.venue.building,
            requested_room_count=r.venue.room_count,
            requested_min_capacity=r.venue.min_capacity,
            requested_tags=r.venue.tags,
            invigilators_requested=r.venue.invigilators,
            on_campus_written=r.on_campus_written,
            no_exam=r.no_exam,
            needs_room=r.needs_room,
            definitive_room_text=r.definitive.raw,
            definitive_room_ids=await cat.room_ids(r.definitive.room_codes, create=True),
            merge_key=mk,
            status=status,
            parse_warnings=r.warnings,
            notes=r.venue.notes,
            source_row=r.raw,
            source_key=key,
            source_row_index=r.row,
            archived=False,
        )
        ex = existing.get(key)
        if ex is None:
            ex = ExamRequest(**fields)
            session.add(ex)
            existing[key] = ex
            report.created["exam_requests"] += 1
        else:
            if ex.status == "LOCKED" and status != "LOCKED":
                fields.pop("status")
            for k, v in fields.items():
                setattr(ex, k, v)
            report.updated["exam_requests"] += 1
        report.rows_imported += 1
    for skey, ex in existing.items():
        if skey and skey not in seen_keys and not ex.archived:
            ex.archived = True
            report.updated["exam_requests_archived"] += 1
    await cat.finalize_rooms(lecture_side=False)
    report.extra["merge_groups"] = len(merge_groups)
    report.extra["merged_rows"] = sum(c for c in merge_groups.values() if c > 1)
    await session.commit()
    return report
