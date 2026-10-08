"""Planner-facing data-conflict report of a run (``GET /runs/{id}/data-issues``).

The run's diagnoses (solver + bridge warnings and the unplaced reasons) are grouped into the problems a
planner fixes in *their own data* — two LOCKED rows in one room at one time, a fixed-time instructor or
cohort clash, a locked room smaller than the expected enrolment, a missing room tag, a room outside the
bookable pool, a request without any free fitting room, a lock on a room the grid blocks — each with the
classes (requests) involved, read from the DB: course, section, programme, class year, enrolment, day /
periods / time, weeks, the planner's room, instructors and the source row.  ``to_xlsx`` writes one sheet
per group with Turkish / English column headers.

Nothing is re-solved and nothing is hidden: diagnoses that fit no named group land in ``other``; the
pure summaries (``partial``, ``unplaced_summary``) are left out because every case they summarise is
listed on its own.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ExamRequest, MeetingRequest, Room, ScheduleRun, Section, SectionInstructor
from app.services.calendar import period_times

DAY_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
DAY_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


@dataclass(frozen=True)
class GroupSpec:
    code: str
    sheet: str  # <= 31 characters, no []:*?/\
    title_tr: str
    title_en: str
    hint_tr: str
    hint_en: str


GROUPS: tuple[GroupSpec, ...] = (
    GroupSpec(
        "locked_room_overlap",
        "Kilitli çakışma - Lock overlap",
        "Kilitli derslik çakışmaları",
        "Locked room overlaps",
        "İki KİLİTLİ satır aynı anda aynı dersliği tutuyor; birinin dersliğini veya saatini değiştirin.",
        "Two LOCKED rows hold the same room at the same time; change the room or time of one of them.",
    ),
    GroupSpec(
        "fixed_instructor_clash",
        "Hoca çakışması - Instructor",
        "Sabit saatli öğretim elemanı çakışmaları",
        "Fixed-time instructor clashes",
        "Aynı öğretim elemanının iki sabit saatli dersi çakışıyor; birini taşıyın veya hoca adını kontrol edin.",
        "One instructor has two fixed-time classes at overlapping times; move one or check the name.",
    ),
    GroupSpec(
        "fixed_cohort_clash",
        "Sınıf çakışması - Cohort",
        "Sabit saatli sınıf (program/yıl) çakışmaları",
        "Fixed-time cohort clashes",
        "Aynı program ve sınıfın iki sabit saatli dersi çakışıyor; birini taşıyın veya seçmeli olduğunu belirtin.",
        "One programme year has two fixed-time classes at overlapping times; move one or mark it elective.",
    ),
    GroupSpec(
        "locked_room_too_small",
        "Küçük derslik - Room too small",
        "Kilitli derslik beklenen öğrenci sayısından küçük",
        "Locked rooms too small",
        "Planlayıcının dersliği beklenen öğrenci sayısından küçük; plan korunur, büyük derslik önerilir.",
        "The planner's room seats fewer than the expected enrolment; kept as planned, bigger rooms suggested.",
    ),
    GroupSpec(
        "missing_tags",
        "Eksik özellik - Missing tags",
        "Eksik derslik özellikleri (PC, TIP ...)",
        "Missing room tags",
        "İstenen özellik (ör. PC) dersliklerde yok veya kilitli derslikte eksik.",
        "A requested tag (e.g. PC) is missing on the locked room or on every room.",
    ),
    GroupSpec(
        "rooms_outside_pool",
        "Havuz dışı - Outside pool",
        "Derslik havuzu dışındaki derslikler",
        "Rooms outside the pool",
        "Derslik kapasitesi bilinmiyor / rezerve edilemez; oda listesine kapasiteyle ekleyin.",
        "The room has no known capacity / is not bookable; add it with a capacity to the room master.",
    ),
    GroupSpec(
        "no_free_room",
        "Boş derslik yok - No room",
        "Sığan boş derslik yok",
        "No free room that fits",
        "Bu saatte sığan her derslik dolu veya kapalı; saati değiştirin, grubu bölün ya da bir kilidi kaldırın.",
        "Every room that fits is busy or closed at that time; move it, split the group or release a lock.",
    ),
    GroupSpec(
        "locked_room_blocked",
        "Kapalı derslik - Room blocked",
        "Takvimde kapalı dersliğe kilitli kayıtlar",
        "Locked to rooms blocked by the grid",
        "Kilitli derslik takvimde (ETKİNLİK, sınav ...) kapalı; dersliği veya takvim kaydını düzeltin.",
        "The locked room is blocked in the grid (event, exam ...); fix the room or the grid cell.",
    ),
    GroupSpec(
        "week_room_changes",
        "Hafta değişikliği - Week moves",
        "Bazı haftalarda derslik değişiyor",
        "Room changes in some weeks",
        "Derslik bazı haftalarda takvimde kapalı; o haftalar aynı saatte başka dersliğe alındı.",
        "The room is blocked in some weeks; those weeks moved to another room at the same time.",
    ),
    GroupSpec(
        "other",
        "Diğer - Other",
        "Diğer uyarılar",
        "Other findings",
        "Yukarıdaki gruplara girmeyen bulgular.",
        "Findings that fit none of the groups above.",
    ),
)
GROUP_BY_CODE = {g.code: g for g in GROUPS}
EXAM_BLOCKED_TITLE = ("Takvimde kapalı dersliğe kilitli sınavlar", "Exams locked to rooms blocked by the grid")

#: summaries whose cases are all listed individually
SKIP_CODES = frozenset({"partial", "unplaced_summary"})


def classify(d: dict[str, Any]) -> list[str]:
    """Group codes of one diagnosis (an input clash on both an instructor and a cohort is in both)."""
    code = str(d.get("code") or "")
    params = d.get("params") or {}
    kinds = set(d.get("constraint_kinds") or [])
    if code in SKIP_CODES:
        return []
    if code == "locked_overlap":
        return ["locked_room_overlap"]
    if code in ("input_conflict", "fixed_conflict"):
        keys = {str(k[0]) for k in params.get("keys") or [] if k}
        if params.get("kind"):
            keys.add(str(params["kind"]))
        keys |= kinds
        out = []
        if "no_instructor_overlap" in keys or params.get("noun") == "instructor":
            out.append("fixed_instructor_clash")
        if "no_cohort_overlap" in keys or params.get("noun") == "cohort":
            out.append("fixed_cohort_clash")
        return out or ["other"]
    if code == "trusted_lock_capacity":
        return ["locked_room_too_small"]
    if code == "trusted_lock_tags" or (code == "no_room" and params.get("reason") == "tags"):
        return ["missing_tags"]
    if code in ("outside_room_pool", "room_without_capacity"):
        return ["rooms_outside_pool"]
    if code in ("unplaced", "no_room", "pigeonhole"):
        return ["no_free_room"]
    if code in ("locked_ineligible", "locked_blocked"):
        return ["locked_room_blocked"]
    if code == "week_split":
        return ["week_room_changes"]
    if d.get("severity") in ("error", "warning"):
        return ["other"]
    return []


def _weeks_text(weeks: Iterable[Any]) -> str:
    ws = sorted({int(w) for w in weeks if w is not None})
    runs: list[list[int]] = []
    for w in ws:
        if runs and runs[-1][1] == w - 1:
            runs[-1][1] = w
        else:
            runs.append([w, w])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


def _rooms_text(ids: Iterable[Any], codes: dict[int, str]) -> str:
    return " / ".join(codes.get(int(r), f"#{r}") for r in ids or [])


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list | tuple) else []


def message_tr(d: dict[str, Any]) -> str:
    """Turkish rendering of the common diagnosis codes from their params (English message otherwise)."""
    code = str(d.get("code") or "")
    p = d.get("params") or {}
    rooms = " / ".join(str(c) for c in _as_list(p.get("room_codes"))) or " / ".join(
        str(r) for r in _as_list(p.get("rooms"))
    )
    day = DAY_TR.get(int(p["day"]), str(p["day"])) if p.get("day") else ""
    if code == "locked_overlap" and rooms:
        return f"İki kilitli kayıt {day} P{p.get('period', '?')} saatinde aynı dersliği ({rooms}) tutuyor."
    if code == "input_conflict":
        who = "aynı öğretim elemanı" if p.get("noun") == "instructor" else "aynı sınıf"
        return f"İki sabit saatli ders {day} P{p.get('start', '?')} civarında çakışıyor ({who}: {p.get('key', '')})."
    if code == "trusted_lock_capacity":
        return f"Beklenen {p.get('size')} öğrenci, kilitli derslik(ler) {rooms} {p.get('seats')} kişilik."
    if code == "trusted_lock_tags":
        return f"Kilitli derslikte istenen özellik yok: {', '.join(map(str, _as_list(p.get('missing_tags'))))}."
    if code == "no_room":
        if p.get("reason") == "tags":
            return f"İstenen özelliğe sahip derslik yok: {', '.join(map(str, _as_list(p.get('missing_tags'))))}."
        return f"{p.get('size')} kişilik grup için uygun derslik yok (en büyük: {p.get('largest_capacity', '?')})."
    if code in ("locked_ineligible", "locked_blocked"):
        return "Kilitli derslik bu saatte takvimde kapalı (veya uygun değil)."
    if code == "week_split":
        moved = _weeks_text(_as_list(p.get("moved_weeks")))
        return f"Derslik {moved}. hafta(lar)da kapalı; o haftalar aynı saatte başka dersliğe alındı."
    if code == "unplaced":
        return "Yerleştirilemedi: bu saatte sığan derslikler dolu veya kapalı (ayrıntı İngilizce açıklamada)."
    if code == "pigeonhole":
        slot = f"{day} P{p.get('period', '?')}, {p.get('week', '?')}. hafta"
        return f"{slot}: sabit saatli ders sayısı uygun derslik sayısını aşıyor."
    if code in ("outside_room_pool", "room_without_capacity"):
        return "Derslik havuz dışında (kapasite bilinmiyor); kayıt dersliğini korur, çözücü kontrol edemez."
    return str(d.get("message") or "")


async def _class_rows(session: AsyncSession, run: ScheduleRun, ids: set[int]) -> dict[int, dict[str, Any]]:
    """Request id -> row facts for the report (course or exam requests of the run's term)."""
    rooms = {int(i): str(c) for i, c in (await session.execute(select(Room.id, Room.code))).all()}
    out: dict[int, dict[str, Any]] = {}
    if not ids:
        return out
    if run.kind == "EXAM":
        q = (
            select(ExamRequest)
            .where(ExamRequest.id.in_(ids), ExamRequest.term_id == run.term_id)
            .options(selectinload(ExamRequest.program))
        )
        for ex in (await session.execute(q)).scalars():
            start, end = period_times(ex.start_period, ex.end_period) if ex.start_period and ex.end_period else ("", "")
            out[ex.id] = {
                "request_id": ex.id,
                "course_code": ex.course_code,
                "course_name": ex.course_name or "",
                "section": "",
                "program": ex.program.name if ex.program else (ex.faculty_text or ""),
                "class_year": ex.class_year,
                "enrolment": ex.enrolment,
                "day": ex.date.isoweekday() if ex.date else None,
                "date": ex.date.isoformat() if ex.date else "",
                "periods": f"P{ex.start_period}-P{ex.end_period}" if ex.start_period else "",
                "time": f"{start}-{end}" if start else "",
                "weeks": "",
                "planner_rooms": _rooms_text(ex.definitive_room_ids, rooms) or (ex.definitive_room_text or ""),
                "instructors": ex.instructor_text or "",
                "status": ex.status,
                "source_row": ex.source_row_index,
            }
        return out
    qm = (
        select(MeetingRequest)
        .where(MeetingRequest.id.in_(ids))
        .options(
            selectinload(MeetingRequest.section).selectinload(Section.course),
            selectinload(MeetingRequest.section).selectinload(Section.program),
            selectinload(MeetingRequest.section)
            .selectinload(Section.instructors)
            .selectinload(SectionInstructor.instructor),
        )
    )
    for mr in (await session.execute(qm)).scalars():
        sec = mr.section
        if sec is None or sec.term_id != run.term_id:
            continue
        start, end = period_times(mr.start_period, mr.end_period) if mr.start_period and mr.end_period else ("", "")
        out[mr.id] = {
            "request_id": mr.id,
            "course_code": sec.course.display_code,
            "course_name": sec.course.name or "",
            "section": sec.label or "",
            "program": sec.program.name if sec.program else "",
            "class_year": sec.class_year,
            "enrolment": sec.enrolment,
            "day": mr.day,
            "date": "",
            "periods": f"P{mr.start_period}-P{mr.end_period}" if mr.start_period else "",
            "time": f"{start}-{end}" if start else "",
            "weeks": _weeks_text(mr.weeks or []),
            "planner_rooms": _rooms_text(mr.definitive_room_ids, rooms) or (mr.definitive_room_text or ""),
            "instructors": ", ".join(si.instructor.full_name for si in sec.instructors if si.instructor),
            "status": mr.status,
            "source_row": mr.source_row_index,
        }
    return out


async def _members(session: AsyncSession, run: ScheduleRun, event_ids: set[int]) -> dict[int, list[int]]:
    """Solver event id -> request ids (joint lectures / exam cohorts stand for several requests)."""
    stored = {int(k): [int(x) for x in v] for k, v in ((run.stats or {}).get("event_members") or {}).items()}
    out = {e: stored.get(e, [e]) for e in event_ids}
    if run.kind == "EXAM":
        missing = [e for e in event_ids if e not in stored]
        if missing:
            heads = {
                int(i): mk
                for i, mk in (
                    await session.execute(
                        select(ExamRequest.id, ExamRequest.merge_key).where(ExamRequest.id.in_(missing))
                    )
                ).all()
                if mk
            }
            if heads:
                rows = (
                    await session.execute(
                        select(ExamRequest.id, ExamRequest.merge_key).where(
                            ExamRequest.term_id == run.term_id,
                            ExamRequest.merge_key.in_(set(heads.values())),
                            ExamRequest.archived.is_(False),
                        )
                    )
                ).all()
                by_key: dict[str, list[int]] = {}
                for i, mk in rows:
                    by_key.setdefault(str(mk), []).append(int(i))
                for e, mk in heads.items():
                    out[e] = sorted(by_key.get(str(mk), [e]))
    return out


async def build_data_issues(session: AsyncSession, run: ScheduleRun) -> dict[str, Any]:
    """The grouped report (JSON shape of ``GET /runs/{id}/data-issues``)."""
    diags = [d for d in (run.diagnosis or []) if isinstance(d, dict)]
    unplaced = {int(i) for i in (run.stats or {}).get("unplaced_ids") or []}
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {g.code: [] for g in GROUPS}
    event_ids: set[int] = set()
    for idx, d in enumerate(diags):
        for code in classify(d):
            grouped[code].append((idx, d))
            event_ids |= {int(i) for i in d.get("event_ids") or []}
    members = await _members(session, run, event_ids)
    rows = await _class_rows(session, run, {r for ms in members.values() for r in ms})
    groups_out: list[dict[str, Any]] = []
    for spec in GROUPS:
        items: list[dict[str, Any]] = []
        for idx, d in grouped[spec.code]:
            req_ids = list(dict.fromkeys(r for e in d.get("event_ids") or [] for r in members.get(int(e), [int(e)])))
            items.append(
                {
                    "diagnosis_index": idx,
                    "code": d.get("code") or "",
                    "severity": d.get("severity") or "",
                    "message": d.get("message") or "",
                    "message_tr": message_tr(d),
                    "suggestions": [
                        s if isinstance(s, str) else str(s.get("text", "")) for s in d.get("suggestions") or []
                    ],
                    "event_ids": [int(e) for e in d.get("event_ids") or []],
                    "request_ids": req_ids,
                    "unplaced": any(int(e) in unplaced for e in d.get("event_ids") or []),
                    "params": {k: v for k, v in (d.get("params") or {}).items() if k != "options"},
                    "classes": [rows[r] for r in req_ids if r in rows],
                }
            )
        title_tr, title_en = spec.title_tr, spec.title_en
        if spec.code == "locked_room_blocked" and run.kind == "EXAM":
            title_tr, title_en = EXAM_BLOCKED_TITLE
        groups_out.append(
            {
                "code": spec.code,
                "title": {"tr": title_tr, "en": title_en},
                "hint": {"tr": spec.hint_tr, "en": spec.hint_en},
                "count": len(items),
                "requests": len({r for it in items for r in it["request_ids"]}),
                "items": items,
            }
        )
    stats = run.stats or {}
    return {
        "run_id": run.id,
        "term_id": run.term_id,
        "kind": run.kind,
        "status": run.status,
        "totals": {
            "issues": sum(g["count"] for g in groups_out),
            "events_total": stats.get("events_total"),
            "placed": stats.get("placed"),
            "unplaced": stats.get("unplaced"),
            "by_group": {g["code"]: g["count"] for g in groups_out},
        },
        "groups": groups_out,
    }


# --------------------------------------------------------------------------- xlsx

ISSUE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("issue_no", "No / No"),
    ("severity", "Önem / Severity"),
    ("message_tr", "Sorun / Issue (TR)"),
    ("message", "Açıklama / Details (EN)"),
    ("suggestion", "Öneri / Suggestion"),
)
CLASS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("request_id", "Kayıt / Request #"),
    ("course_code", "Ders / Course"),
    ("section", "Şube / Section"),
    ("course_name", "Ders adı / Course name"),
    ("program", "Program / Programme"),
    ("class_year", "Sınıf / Year"),
    ("enrolment", "Öğrenci / Enrolment"),
    ("day_label", "Gün / Day"),
    ("date", "Tarih / Date"),
    ("periods", "Ders saati / Periods"),
    ("time", "Saat / Time"),
    ("weeks", "Haftalar / Weeks"),
    ("planner_rooms", "Planlanan derslik / Planner room"),
    ("instructors", "Öğretim elemanı / Instructor"),
    ("status", "Durum / Status"),
    ("source_row", "Kaynak satır / Source row"),
)
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
GROUP_FILL = PatternFill("solid", fgColor="E8EEF6")


def to_xlsx(report: dict[str, Any]) -> bytes:
    """One sheet per group (header row TR / EN, one row per class involved, issue columns repeated) plus
    an ``Özet / Summary`` sheet with the counts."""
    wb = Workbook()
    summary = wb.active
    assert summary is not None
    summary.title = "Özet - Summary"
    summary.append(["Grup", "Group", "Sorun / Issues", "Kayıt / Requests", "Açıklama", "Hint"])
    for c in summary[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
    for g in report["groups"]:
        summary.append(
            [g["title"]["tr"], g["title"]["en"], g["count"], g["requests"], g["hint"]["tr"], g["hint"]["en"]]
        )
    summary.append([])
    t = report["totals"]
    summary.append(["Toplam olay", "Events total", t.get("events_total")])
    summary.append(["Yerleşen", "Placed", t.get("placed")])
    summary.append(["Yerleşemeyen", "Unplaced", t.get("unplaced")])
    for col, width in zip("ABCDEF", (44, 40, 14, 16, 70, 70), strict=True):
        summary.column_dimensions[col].width = width
    headers = [h for _k, h in ISSUE_COLUMNS] + [h for _k, h in CLASS_COLUMNS]
    for g in report["groups"]:
        ws = wb.create_sheet(GROUP_BY_CODE[g["code"]].sheet[:31])
        ws.append([f"{g['title']['tr']} / {g['title']['en']}"])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([g["hint"]["tr"]])
        ws.append([g["hint"]["en"]])
        ws.append(headers)
        for c in ws[4]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = HEADER_FILL
            c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A5"
        for n, it in enumerate(g["items"], start=1):
            issue = {
                "issue_no": n,
                "severity": it["severity"],
                "message_tr": it["message_tr"],
                "message": it["message"],
                "suggestion": "; ".join(it["suggestions"][:3]),
            }
            classes = it["classes"] or [{}]
            for k, cls in enumerate(classes):
                row = {
                    **cls,
                    "day_label": f"{DAY_TR.get(cls['day'], '')} / {DAY_EN.get(cls['day'], '')}"
                    if cls.get("day")
                    else "",
                }
                values = [issue[key] if k == 0 else (n if key == "issue_no" else "") for key, _h in ISSUE_COLUMNS]
                values += [row.get(key, "") if row.get(key) is not None else "" for key, _h in CLASS_COLUMNS]
                ws.append(values)
                if k == 0 and n % 2 == 0:
                    for c in ws[ws.max_row]:
                        c.fill = GROUP_FILL
        widths = [6, 10, 60, 60, 50] + [10, 12, 8, 30, 30, 8, 10, 22, 12, 10, 12, 10, 22, 30, 12, 10]
        for i, w in enumerate(widths[: len(headers)], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["GROUPS", "build_data_issues", "classify", "message_tr", "to_xlsx"]
