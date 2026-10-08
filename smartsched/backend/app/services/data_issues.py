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
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.export_safety import neutralize_workbook
from app.models import (
    Assignment,
    ExamRequest,
    Instructor,
    MeetingRequest,
    Program,
    Room,
    ScheduleRun,
    Section,
    SectionInstructor,
)
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


#: report order: unplaced classes first, then the planner's data errors, clashes, warnings
GROUPS: tuple[GroupSpec, ...] = (
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
        "locked_room_overlap",
        "Kilitli çakışma - Lock overlap",
        "Kilitli derslik çakışmaları",
        "Locked room overlaps",
        "İki KİLİTLİ satır aynı anda aynı dersliği tutuyor; birinin dersliğini veya saatini değiştirin.",
        "Two LOCKED rows hold the same room at the same time; change the room or time of one of them.",
    ),
    GroupSpec(
        "shared_room_overflow",
        "Ortak salon taşıyor - Overflow",
        "Ortak sınav salonu kapasiteyi aşıyor",
        "Shared exam rooms over capacity",
        "Planlayıcının kilitlediği sınavlar bir salonda sınav koltuğundan fazla öğrenci topluyor; plan korunur.",
        "The planner's locked exams put more students into one room than it has exam seats; kept as planned.",
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
        "same_lecture_twice",
        "İki kez yazılmış - Listed twice",
        "Listede iki kez yazılmış dersler",
        "Lectures listed twice",
        "Aynı ders ve şube aynı saatte iki satırda var; birini silin veya birleştirin.",
        "The same course and section appear on two rows at the same time; delete or merge one.",
    ),
    GroupSpec(
        "board_vs_list",
        "Liste ile pano farklı - Board",
        "Planlama listesi ile yayınlanan pano farklı",
        "Board vs planning list",
        "Planlama listesindeki kesin derslik ile yayınlanan haftalık panodaki derslik aynı saatte farklı.",
        "The planning list's definitive room and the published weekly board disagree at the same time.",
    ),
    GroupSpec(
        "board_capacity",
        "Pano kapasite - Board capacity",
        "Panoda derse küçük gelen derslikler",
        "Board rooms too small for their class",
        "Yayınlanan panoda bir ders tek başına öğrenci sayısından küçük bir derslikte; panoyu veya öğrenci "
        "sayısını düzeltin.",
        "On the published board a class sits alone in a room with fewer seats than its enrolment; fix the "
        "board cell or the enrolment.",
    ),
    GroupSpec(
        "board_instructor_clash",
        "Pano hoca - Board instructor",
        "Pano saatlerinden doğan öğretim elemanı çakışmaları",
        "Instructor clashes caused by board times",
        "Panoda aynı öğretim elemanının iki dersi aynı saatte; planlama listesinde saatler çakışmıyor, pano "
        "hücresinin saatini düzeltin.",
        "The board puts two classes of one instructor at the same time although the list times do not "
        "overlap; fix the time of the board cell.",
    ),
    GroupSpec(
        "board_two_classes",
        "Hücrede iki ders - Two in cell",
        "Panoda bir hücrede iki ders",
        "Two classes in one board cell",
        "Bir pano hücresinde iki farklı ders var ve listede ortak ders değiller (öğretim elemanları farklı); "
        "birini başka dersliğe alın.",
        "One board cell holds two different courses that the list does not give as a joint lecture "
        "(different instructors); move one of them.",
    ),
    GroupSpec(
        "board_unknown_code",
        "Panoda bilinmeyen - Board code",
        "Panoda olup listede olmayan ders kodları",
        "Board course codes unknown to the list",
        "Panodaki ders kodu planlama listesinde yok; kodu düzeltin veya dersi listeye ekleyin.",
        "The board cell's course code is not in the planning list; fix the code or add the class to the list.",
    ),
    GroupSpec(
        "board_time_not_in_list",
        "Pano saati - Board time",
        "Listede olmayan saatlerdeki pano hücreleri",
        "Board cells at times the list does not have",
        "Ders listede var ama bu gün ve saatte değil; pano hücresinin veya listenin saatini düzeltin.",
        "The course is in the list, but not on this day and time; fix the board cell or the list time.",
    ),
    GroupSpec(
        "board_missing_week",
        "Pano haftası yok - No board wk",
        "Panosu olmayan haftalar",
        "Weeks without a board sheet",
        "Çalışmanın bu haftaları için panoda sayfa yok; kapalı derslikler ve etkinlikler bilinmiyor. Hafta "
        "sayfasını yayınlayın.",
        "The board has no sheet for these weeks of the run, so closed rooms and events are unknown; publish "
        "the week sheet.",
    ),
    GroupSpec(
        "locked_room_too_small",
        "Küçük derslik - Room too small",
        "Planlanan derslik öğrenci sayısından küçük",
        "Planned rooms too small",
        "Planlayıcının (kesin ya da istenen) dersliği öğrenci sayısından küçük; kilitli plan korunur.",
        "The planner's (definitive or requested) room seats fewer than the enrolment; locks are kept.",
    ),
    GroupSpec(
        "missing_enrolment",
        "Öğrenci sayısı yok - Enrolment",
        "Öğrenci sayısı girilmemiş dersler",
        "Classes without an enrolment",
        "Listede öğrenci sayısı yok; çözücü tahmini bir sayı kullandı (aynı dersin diğer şubeleri, sınıfın "
        "ortancası veya dönemin ortancası). Gerçek sayıyı girin.",
        "The list has no enrolment; the solver used an estimate (the course's other sections, the programme "
        "year's median or the term's median). Enter the real number.",
    ),
    GroupSpec(
        "instructor_not_person",
        "Hoca adı değil - Not a person",
        "Öğretim elemanı sütununda kişi olmayan değerler",
        "Instructor values that name no person",
        "Öğretim elemanı sütununda kişi adı yok (Yüz yüze, UZEM, bölüm adı, not ...); hoca çakışması "
        "denetlenemiyor. Öğretim elemanının adını yazın.",
        "The instructor column names no person (face to face, UZEM, a department, a note ...); instructor "
        "clashes cannot be checked. Enter the instructor's name.",
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
    if code in ("locked_overlap", "outside_pool_overlap"):
        return ["locked_room_overlap"]
    if code == "missing_enrolment":
        return ["missing_enrolment"]
    if code == "instructor_not_person":
        return ["instructor_not_person"]
    if code == "joint_lecture_clipped":  # prefer mode: a joint lecture's planner rooms seat fewer
        return ["locked_room_too_small"]
    if code == "input_conflict" and params.get("same_lecture"):
        return ["same_lecture_twice"]
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
        if params.get("shared") and len(d.get("event_ids") or []) >= 2:
            return ["shared_room_overflow"]
        return ["locked_room_too_small"]
    if code == "trusted_hint_capacity":  # prefer mode: the planner's room as a hint seats fewer
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


# --------------------------------------------------------------------------- planner texts (TR / EN)


@dataclass
class TextContext:
    """What the planner-facing texts need besides the diagnosis: names instead of ids and keys."""

    labels: dict[int, str] = field(default_factory=dict)  # solver event id -> "MAT 112 §1 + HEM 236"
    times: dict[int, tuple[int, int, int]] = field(default_factory=dict)  # event id -> (day, start, end)
    instructors: dict[int, str] = field(default_factory=dict)  # instructor id -> full name
    programs: dict[str, str] = field(default_factory=dict)  # canonical programme -> display name
    stats: dict[str, Any] = field(default_factory=dict)  # run stats (placed / events_total ...)
    exam: bool = False
    rooms: dict[int, str] = field(default_factory=dict)  # room id -> code (params with ids only)


_ID_RX = re.compile(r" ?\(#-?\d+\)")
_INS_RX = re.compile(r"'?INS:(\d+)(?: \(([^)]*)\))?'?")
_PROG_RX = re.compile(r"'?PROG:([^:']+):Y(\d+)'?")
_SLOT_RX = re.compile(r"day (\d) P(\d+)-P(\d+)")


def _clock(start: Any, end: Any) -> str:
    try:
        s, e = period_times(int(start), int(end))
    except (TypeError, ValueError, IndexError):
        return ""
    return f"{s}–{e}"


def _slot(lang: str, day: Any, start: Any, end: Any | None = None) -> str:
    """ "Perşembe 13:30–16:00" / "Thursday 13:30–16:00" (no period numbers, no internal day index)."""
    try:
        d = int(day)
    except (TypeError, ValueError):
        return ""
    name = (DAY_TR if lang == "tr" else DAY_EN).get(d, str(d))
    clock = _clock(start, end if end is not None else start) if start is not None else ""
    return f"{name} {clock}".strip()


def _key_text(lang: str, key: str, ctx: TextContext) -> str:
    m = re.fullmatch(r"INS:(\d+)", key)
    if m:
        name = ctx.instructors.get(int(m.group(1)))
        return name or ("öğretim elemanı" if lang == "tr" else "the instructor")
    m = re.fullmatch(r"PROG:([^:]+):Y(\d+)", key)
    if m:
        prog = ctx.programs.get(m.group(1), m.group(1).title())
        return f"{prog} {m.group(2)}. sınıf" if lang == "tr" else f"{prog} year {m.group(2)}"
    if key.startswith("INS:"):
        return key[4:]
    return key


def humanize(text: str, ctx: TextContext, lang: str = "en") -> str:
    """Fallback for codes without a template: drop ``(#123)`` ids, name instructors and programmes,
    and write ``day 4 P7-P9`` as "Thursday 13:30–16:00"."""
    out = _ID_RX.sub("", text)
    out = _INS_RX.sub(lambda m: m.group(2) or _key_text(lang, f"INS:{m.group(1)}", ctx), out)
    out = _PROG_RX.sub(lambda m: _key_text(lang, f"PROG:{m.group(1)}:Y{m.group(2)}", ctx), out)
    return _SLOT_RX.sub(lambda m: _slot(lang, m.group(1), m.group(2), m.group(3)), out)


_EXCLUDED = {
    "capacity": ("kapasite yetmiyor", "too small"),
    "locked": ("başka dersliğe kilitli", "locked to another room"),
    "pin": ("sabitlenen derslik değil", "not the pinned room"),
    "forbid": ("yasaklı", "banned"),
    "tags": ("özellik (PC, TIP ...) uymuyor", "tags (PC, TIP ...) do not match"),
    "blocked": ("takvimde kapalı", "blocked in the grid"),
}


#: why a class lost every possible time (``no_time`` params.categories, diagnose.reason_category)
_TIME_EXCLUDED = {
    "cohort": ("sınıfın başka dersi var", "the class year has another class"),
    "instructor": ("öğretim elemanının başka dersi var", "the instructor has another class"),
    "day_window": ("izin verilen saatlerin dışında", "outside the allowed hours"),
    "blocked": ("takvimde kapalı", "blocked in the grid"),
    "fixed_time": ("sabit saate uymuyor", "not the fixed time"),
    "room_closed": ("derslikler kapalı", "the rooms are closed"),
}


def _time_excluded_text(lang: str, categories: Any) -> str:
    if not isinstance(categories, dict) or not categories:
        return ""
    parts = []
    for cat, n in list(categories.items())[:4]:
        tr, en = _TIME_EXCLUDED.get(str(cat), ("başka bir kural", "another rule"))
        parts.append(f"{n} saat: {tr}" if lang == "tr" else f"{n} time(s): {en}")
    return "; ".join(parts)


def _excluded_text(lang: str, excluded: Any) -> str:
    if not isinstance(excluded, dict) or not excluded:
        return ""
    parts = []
    for cat, n in list(excluded.items())[:4]:
        tr, en = _EXCLUDED.get(str(cat), (str(cat), str(cat)))
        parts.append(f"{n} derslik {tr}" if lang == "tr" else f"{n} room(s) {en}")
    return ", ".join(parts)


def _rooms_list(items: Any, lang: str, n: int = 5) -> str:
    out = []
    for x in _as_list(items)[:n]:
        if isinstance(x, dict):
            seats = "kişilik" if lang == "tr" else "seats"
            out.append(f"{x.get('room')} ({x.get('capacity')} {seats})")
        else:
            out.append(str(x))
    return ", ".join(out)


def planner_text(d: dict[str, Any], ctx: TextContext | None = None) -> dict[str, str]:
    """Planner-facing ``{"tr": ..., "en": ...}`` of one stored diagnosis, rendered from ``code`` +
    ``params``: course codes, room names, Turkish day names, clock times, week ranges — never
    internal ids, rule kinds or keys.  Unknown codes fall back to the humanised English message."""
    ctx = ctx or TextContext()
    code = str(d.get("code") or "")
    p = d.get("params") or {}
    ids = [int(i) for i in d.get("event_ids") or []]

    def lab(i: int) -> str:
        return ctx.labels.get(i) or "?"

    def when(i: int, lang: str) -> str:
        t = ctx.times.get(i)
        return _slot(lang, *t) if t else ""

    first = lab(ids[0]) if ids else ""
    rooms = " / ".join(str(c) for c in _as_list(p.get("room_codes"))) or " / ".join(
        ctx.rooms.get(int(r), "") for r in _as_list(p.get("rooms")) if isinstance(r, int) and int(r) in ctx.rooms
    )
    size = p.get("size")
    out: dict[str, str] | None = None
    if code == "partial":
        st = ctx.stats
        placed, total = st.get("placed"), st.get("events_total")
        un = st.get("unplaced")
        exc = {str(k): int(v) for k, v in (p.get("exceptions") or st.get("accepted_exceptions") or {}).items()}
        kept_exc = {k: v for k, v in exc.items() if k != "D3" and v}
        n_exc = sum(kept_exc.values())
        if p.get("reason") == "timeout":
            out = {
                "tr": f"Süre içinde tam bir çizelge bulunamadı; {placed}/{total} ders yerleşti ve hepsi kurallara "
                "uyuyor. Kalanların yerleşemeyeceği kanıtlanmadı: süreyi uzatın.",
                "en": f"No complete timetable within the time limit; {placed} of {total} classes placed, all keep "
                "every rule. The rest is not proven impossible: raise the time limit.",
            }
        elif not n_exc:
            out = {
                "tr": f"{placed}/{total} ders yerleşti, {un} ders yerleşemedi. Yerleşen derslerin hepsi kurallara "
                "uyuyor; yerleşemeyenlerin nedeni aşağıda.",
                "en": f"{placed} of {total} classes placed, {un} could not be placed. Every placed class keeps every "
                "rule; the reasons for the rest are below.",
            }
        else:
            out = {
                "tr": f"{placed}/{total} ders yerleşti, {un} ders yerleşemedi. Yerleşen dersler, listelenen {n_exc} "
                "kabul edilmiş istisna dışında her kurala uyuyor ("
                + "; ".join(f"{_CAUSE_TR.get(k, k)}: {v}" for k, v in kept_exc.items())
                + "); yerleşemeyenlerin nedeni aşağıda.",
                "en": f"{placed} of {total} classes placed, {un} could not be placed. The placed classes keep every "
                f"rule except {n_exc} accepted exceptions (listed: "
                + "; ".join(f"{_CAUSE_EN.get(k, k)}: {v}" for k, v in kept_exc.items())
                + "); the reasons for the rest are below.",
            }
    elif code == "unplaced":
        slot_tr = _slot("tr", p.get("day"), p.get("start"), p.get("end")) or when(ids[0], "tr") if ids else ""
        slot_en = _slot("en", p.get("day"), p.get("start"), p.get("end")) or when(ids[0], "en") if ids else ""
        head_tr = f"{first} ({size} öğrenci{', ' + slot_tr if slot_tr else ''}) yerleşemedi"
        head_en = f"{first} ({size} students{', ' + slot_en if slot_en else ''}) could not be placed"
        problem = p.get("problem")
        if problem == "capacity":
            big = p.get("largest_capacity")
            out = {
                "tr": f"{head_tr}: kapasite sorunu — hiçbir derslik {size} kişilik değil (en büyüğü {big} kişilik). "
                "Grubu bölün veya daha büyük bir derslik ekleyin.",
                "en": f"{head_en}: a capacity problem — no room seats {size} (the largest has {big}). "
                "Split the group or add a bigger room.",
            }
        elif problem == "rooms_busy":
            busy = _as_list(p.get("busy"))

            def held(lang: str) -> str:
                parts = []
                for b in busy[:4]:
                    who = " + ".join(lab(int(h)) for h in _as_list(b.get("holders"))[:2]) or "?"
                    seats = "kişilik" if lang == "tr" else "seats"
                    parts.append(f"{b.get('room')} ({b.get('capacity')} {seats}: {who})")
                return "; ".join(parts)

            free = _as_list(p.get("free"))
            alt_tr = alt_en = ""
            if free:
                f0 = free[0]
                alt_tr = f" Boş seçenek: {f0.get('room')} {_slot('tr', f0.get('day'), f0.get('start'), f0.get('end'))}."
                alt_en = f" Free option: {f0.get('room')} {_slot('en', f0.get('day'), f0.get('start'), f0.get('end'))}."
            out = {
                "tr": f"{head_tr}: sığan derslikler o saatte dolu — {held('tr')}.{alt_tr}",
                "en": f"{head_en}: every room that fits is taken at that time — {held('en')}.{alt_en}",
            }
        elif problem == "clash":
            c = _as_list(p.get("clashes"))[0]
            who_tr = _key_text("tr", str(c.get("key", "")), ctx)
            who_en = _key_text("en", str(c.get("key", "")), ctx)
            other = " + ".join(lab(int(h)) for h in _as_list(c.get("holders"))[:2])
            if c.get("kind") == "instructor":
                out = {
                    "tr": f"{head_tr}: öğretim elemanı {who_tr} o saatte {other} dersinde.",
                    "en": f"{head_en}: the instructor {who_en} teaches {other} at that time.",
                }
            else:
                out = {
                    "tr": f"{head_tr}: {who_tr} öğrencilerinin o saatte {other} dersi var.",
                    "en": f"{head_en}: {who_en} has {other} at that time.",
                }
        else:
            out = {
                "tr": f"{head_tr}: kurallara uyan derslik kalmadı ({_excluded_text('tr', p.get('excluded'))}).",
                "en": f"{head_en}: no room is left that the rules allow ({_excluded_text('en', p.get('excluded'))}).",
            }
    elif code == "no_room":
        reason = p.get("reason")
        fit_tr, fit_en = _rooms_list(p.get("fitting_rooms"), "tr"), _rooms_list(p.get("fitting_rooms"), "en")
        if reason == "capacity":
            best, cap = p.get("largest_room"), p.get("largest_capacity")
            pinned = bool(p.get("pinned_rooms"))
            out = {
                "tr": f"{first}: kapasite sorunu — {size} öğrenci var, "
                + (
                    f"sabitlenen derslik {best} {cap} kişilik"
                    if pinned
                    else f"kullanılabilecek en büyük derslik {best} ({cap} kişilik)"
                )
                + "."
                + (f" Sığan derslikler: {fit_tr}." if fit_tr else " Hiçbir derslik bu grubu almıyor; grubu bölün."),
                "en": f"{first}: a capacity problem — {size} students, "
                + (
                    f"the pinned room {best} seats {cap}"
                    if pinned
                    else f"the largest room it may use is {best} ({cap} seats)"
                )
                + "."
                + (f" Rooms that fit: {fit_en}." if fit_en else " No room seats this group; split it."),
            }
        elif reason == "tags":
            tags = ", ".join(map(str, _as_list(p.get("missing_tags"))))
            out = {
                "tr": f"{first} {tags} özellikli bir derslik istiyor ama hiçbir derslikte bu özellik yok.",
                "en": f"{first} needs a room tagged {tags}, but no room has that tag.",
            }
        elif reason == "pin":
            out = {
                "tr": f"{first} olmayan bir dersliğe sabitlenmiş.",
                "en": f"{first} is pinned to a room that does not exist.",
            }
        else:
            out = {
                "tr": f"{first} ({size} öğrenci) için kurallara uyan derslik yok: "
                f"{_excluded_text('tr', p.get('excluded'))}.",
                "en": f"{first} ({size} students) has no room the rules allow: "
                f"{_excluded_text('en', p.get('excluded'))}.",
            }
        if p.get("pin_vs_lock") and out is not None:
            locked = ", ".join(str(x.get("room")) for x in _as_list(p.get("locked_rooms")) if isinstance(x, dict))
            pinned_r = ", ".join(str(x.get("room")) for x in _as_list(p.get("pinned_rooms")) if isinstance(x, dict))
            out["tr"] += (
                f" Ayrıca planlama listesinde {locked} dersliğine kilitli ama {pinned_r} dersliğine "
                "sabitlenmiş; birini seçin."
            )
            out["en"] += (
                f" It is also locked to {locked} in the planning list but pinned to {pinned_r}; keep one of them."
            )
    elif code == "locked_overlap" and len(ids) >= 2:
        slot_tr = _slot("tr", p.get("day"), p.get("period"))
        slot_en = _slot("en", p.get("day"), p.get("period"))
        if p.get("shared"):
            out = {
                "tr": f"Kilitli sınavlar {rooms} salonunu {slot_tr} paylaşıyor ama {p.get('need')} öğrenciye "
                f"{p.get('seats')} koltuk var: " + ", ".join(lab(i) for i in ids[:4]) + ".",
                "en": f"Locked exams share {rooms} on {slot_en} but need {p.get('need')} seats for "
                f"{p.get('seats')}: " + ", ".join(lab(i) for i in ids[:4]) + ".",
            }
        else:
            out = {
                "tr": f"{lab(ids[0])} ve {lab(ids[1])} {slot_tr} saatinde aynı dersliğe ({rooms}) kilitli. "
                "Birinin dersliğini veya saatini değiştirin.",
                "en": f"{lab(ids[0])} and {lab(ids[1])} are both locked to {rooms} on {slot_en}. "
                "Change the room or time of one of them.",
            }
    elif code == "input_conflict" and p.get("same_lecture") and len(ids) >= 2:
        slot_tr = when(ids[0], "tr")
        slot_en = when(ids[0], "en")
        out = {
            "tr": f"{lab(ids[0])} listede iki kez yazılmış ({slot_tr}): aynı ders, aynı şube, aynı saat. Satırlardan "
            "birini silin veya ikisini tek satırda birleştirin.",
            "en": f"{lab(ids[0])} is listed twice ({slot_en}): the same course, section and time. Delete one row or "
            "merge them into one.",
        }
    elif code in ("input_conflict", "fixed_conflict") and ids:
        keys = [k for k in _as_list(p.get("keys")) if isinstance(k, list | tuple) and len(k) == 2]
        if not keys and p.get("key"):
            keys = [
                [
                    p.get("kind")
                    or ("no_instructor_overlap" if p.get("noun") == "instructor" else "no_cohort_overlap"),
                    p["key"],
                ]
            ]
        whats_tr, whats_en = [], []
        for kind, key in keys[:2]:
            if kind == "no_instructor_overlap":
                whats_tr.append(f"aynı öğretim elemanı ({_key_text('tr', str(key), ctx)})")
                whats_en.append(f"the same instructor ({_key_text('en', str(key), ctx)})")
            else:
                whats_tr.append(f"aynı sınıf ({_key_text('tr', str(key), ctx)})")
                whats_en.append(f"the same class ({_key_text('en', str(key), ctx)})")
        pair = ids[:2]
        a_tr = " ve ".join(f"{lab(i)} ({when(i, 'tr')})" if when(i, "tr") else lab(i) for i in pair)
        a_en = " and ".join(f"{lab(i)} ({when(i, 'en')})" if when(i, "en") else lab(i) for i in pair)
        out = {
            "tr": f"{a_tr} sabit saatlerde çakışıyor: {', '.join(whats_tr) or 'ortak anahtar'}. "
            "Birini başka saate alın veya Excel'deki hoca / sınıf bilgisini düzeltin.",
            "en": f"{a_en} overlap at their fixed times: {', '.join(whats_en) or 'a shared key'}. "
            "Move one of them or correct the instructor / class in the Excel file.",
        }
    elif code == "trusted_lock_capacity":
        if p.get("shared") and len(ids) >= 2:
            slot_tr = _slot("tr", p.get("day"), p.get("period"))
            slot_en = _slot("en", p.get("day"), p.get("period"))
            who = ", ".join(lab(i) for i in ids[:4])
            out = {
                "tr": f"Ortak sınav salonu taşıyor: {rooms} ({p.get('seats')} sınav koltuğu) {slot_tr} saatinde "
                f"{size} öğrenciye ayrılmış ({who}). Planlayıcının kararı korunuyor; öğrenci sayısını veya "
                "salonu kontrol edin.",
                "en": f"Shared exam room overflows: {rooms} ({p.get('seats')} exam seats) holds {size} students on "
                f"{slot_en} ({who}). The planner's decision is kept; check the enrolments or the rooms.",
            }
        else:
            out = {
                "tr": f"{first}: beklenen {size} öğrenci, kilitli derslik {rooms} {p.get('seats')} kişilik. "
                "Planlayıcının dersliği korunuyor."
                + (
                    f" Sığan derslikler: {', '.join(map(str, _as_list(p.get('fitting_rooms'))[:4]))}."
                    if p.get("fitting_rooms")
                    else ""
                ),
                "en": f"{first} expects {size} students but is locked to {rooms} ({p.get('seats')} seats). "
                "The planner's room is kept."
                + (
                    f" Rooms that fit: {', '.join(map(str, _as_list(p.get('fitting_rooms'))[:4]))}."
                    if p.get("fitting_rooms")
                    else ""
                ),
            }
    elif code == "trusted_lock_tags":
        tags = ", ".join(map(str, _as_list(p.get("missing_tags"))))
        bad = ", ".join(map(str, _as_list(p.get("forbidden_tags"))))
        where_tr = rooms or "planlayıcının dersliği"
        where_en = rooms or "the planner's room"
        why_tr = " ve ".join(
            x for x in (f"{tags} özelliğine sahip değil" if tags else "", f"{bad} dersliği" if bad else "") if x
        )
        why_en = " and ".join(x for x in (f"lacks {tags}" if tags else "", f"is a {bad} room" if bad else "") if x)
        out = {
            "tr": f"{first} kilitli dersliği {where_tr} {why_tr or 'istenen özelliklere uymuyor'}; plan korunuyor.",
            "en": f"{first} is locked to {where_en}, which {why_en or 'does not match the requested tags'}; "
            "kept as planned.",
        }
    elif code in ("locked_ineligible", "locked_blocked"):
        slot_tr = _slot("tr", p.get("day"), p.get("start"), p.get("end")) or (when(ids[0], "tr") if ids else "")
        slot_en = _slot("en", p.get("day"), p.get("start"), p.get("end")) or (when(ids[0], "en") if ids else "")
        why_tr = _excluded_text("tr", p.get("categories")) or "takvimde kapalı"
        why_en = _excluded_text("en", p.get("categories")) or "blocked in the grid"
        out = {
            "tr": f"{first} {rooms + ' ' if rooms else ''}dersliğine kilitli ama bu derslik {slot_tr} "
            f"kullanılamıyor ({why_tr}).",
            "en": f"{first} is locked to {rooms + ' ' if rooms else 'a room '}that cannot be used on {slot_en} "
            f"({why_en}).",
        }
    elif code == "pigeonhole":
        out = {
            "tr": f"{_slot('tr', p.get('day'), p.get('period'))}, {p.get('week')}. hafta: "
            f"{p.get('n')} sabit saatli ders "
            f"derslik istiyor ama yalnızca {p.get('rooms')} uygun derslik var.",
            "en": f"{_slot('en', p.get('day'), p.get('period'))}, week {p.get('week')}: "
            f"{p.get('n')} fixed-time classes "
            f"need a room but only {p.get('rooms')} rooms fit.",
        }
    elif code == "week_split":
        moved = _weeks_text(_as_list(p.get("moved_weeks")))
        kept = _weeks_text(_as_list(p.get("kept_weeks")))
        hit = rooms or "derslik"
        out = {
            "tr": f"{first}: {hit} {moved}. hafta(lar)da kullanılamıyor; o haftalar aynı saatte başka dersliğe alındı, "
            f"{kept}. haftalarda {rooms or 'aynı derslikte'} kalıyor.",
            "en": f"{first}: {rooms or 'the room'} cannot be used in week(s) {moved}; those weeks move to "
            "another room at "
            f"the same time, week(s) {kept} stay{' in ' + rooms if rooms else ''}.",
        }
    elif code == "unplaced_summary":
        out = {
            "tr": f"{len(ids)} ders yerleştirilemedi (nedenleri tek tek listelendi).",
            "en": f"{len(ids)} classes cannot be placed (each reason is listed).",
        }
    elif code == "missing_enrolment":
        src = [str(x) for x in _as_list(p.get("sources"))]
        out = {
            "tr": f"{first}: listede öğrenci sayısı yok; {size} öğrenci varsayıldı ("
            + ", ".join(_FALLBACK_TR.get(x, x) for x in src)
            + "). Gerçek öğrenci sayısını girin.",
            "en": f"{first}: the list has no enrolment; planned with {size} students ("
            + ", ".join(_FALLBACK_EN.get(x, x) for x in src)
            + "). Enter the real enrolment.",
        }
    elif code == "instructor_not_person":
        names = ", ".join(f"'{x}'" for x in _as_list(p.get("names"))[:8])
        n_req = len(_as_list(p.get("request_ids"))) or len(ids)
        out = {
            "tr": f"{n_req} kayıtta öğretim elemanı yerine kişi olmayan bir değer yazılmış ({names}); bu değerler "
            "hoca çakışmasında kullanılmadı. Öğretim elemanının adını yazın.",
            "en": f"{n_req} request(s) name no person as instructor ({names}); these values are not used for "
            "instructor clashes. Enter the instructor's name.",
        }
    elif code == "joint_lecture_clipped":
        out = {
            "tr": f"{first} (ortak ders): beklenen {size} öğrenci, planlayıcının dersliği {rooms} {p.get('seats')} "
            f"kişilik. Grup bu derslikte {p.get('seats')} öğrenci sayıldı; başka bir derslik tüm grubu almalı.",
            "en": f"{first} (joint lecture) expects {size} students; the planner's room {rooms} has {p.get('seats')} "
            f"seats. The group counts as {p.get('seats')} in that room only; any other room must seat everyone.",
        }
    elif code == "outside_pool_overlap" and len(ids) >= 2:
        slot_tr = str(p.get("date") or _slot("tr", p.get("day"), p.get("start"), p.get("end")))
        slot_en = str(p.get("date") or _slot("en", p.get("day"), p.get("start"), p.get("end")))
        out = {
            "tr": f"{lab(ids[0])} ve {lab(ids[1])} aynı anda havuz dışındaki {rooms} dersliğine kilitli ({slot_tr}). "
            "Çözücü bu dersliği denetleyemez; birinin dersliğini veya saatini değiştirin.",
            "en": f"{lab(ids[0])} and {lab(ids[1])} are both locked to {rooms}, outside the room pool, on {slot_en}. "
            "The solver cannot check that room; change the room or time of one of them.",
        }
    elif code == "manual_lock":
        out = {
            "tr": f"{first} önceki çalışmada elle (veya bir düzeltmeyle) yerleştirildiği yerde kalıyor; kapasite ve "
            "derslik özellikleri denetlendi.",
            "en": f"{first} stays where it was placed by hand (or by a fix) in the parent run; capacity and room "
            "tags are checked.",
        }
    elif code == "joint_lecture_rejected":
        out = {
            "tr": f"{first}: aynı saatteki satırlar farklı dersliklere kilitli; ayrı dersler olarak planlandı.",
            "en": f"{first}: rows at the same time are locked to different rooms; planned as separate classes.",
        }
    elif code == "trusted_hint_capacity":
        seats_tr = "sınav koltuğu" if ctx.exam else "kişilik"
        seats_en = "exam seats" if ctx.exam else "seats"
        out = {
            "tr": f"{first}: beklenen {size} öğrenci, planlayıcının dersliği {rooms} {p.get('seats')} {seats_tr}. "
            f"Derslik ipucu olarak kullanıldı ve grup {p.get('seats')} öğrenci sayıldı; öğrenci tahminini "
            "kontrol edin.",
            "en": f"{first} expects {size} students; the planner's room {rooms} has {p.get('seats')} {seats_en}. "
            f"The room is used as a hint and the group counted as {p.get('seats')}; check the enrolment estimate.",
        }
    elif code == "no_time":
        why_tr = _time_excluded_text("tr", p.get("categories"))
        why_en = _time_excluded_text("en", p.get("categories"))
        out = {
            "tr": f"{first} için uygun saat kalmadı{' (' + why_tr + ')' if why_tr else ''}. Gün / saat aralığını "
            "genişletin veya çakışan sabit saatli dersi taşıyın.",
            "en": f"{first} has no possible time left{' (' + why_en + ')' if why_en else ''}. Widen its day / time "
            "window or move the clashing fixed-time class.",
        }
    elif code == "bad_time":
        if p.get("day") is not None:
            day = int(p["day"])
            out = {
                "tr": f"{first} {DAY_TR.get(day, str(day))} gününe sabit ama bu gün dönem takviminde yok. Talebin "
                "gününü düzeltin veya günü takvime ekleyin.",
                "en": f"{first} is fixed on {DAY_EN.get(day, str(day))}, which is not a day of the term grid. "
                "Correct the request's day or add the day to the grid.",
            }
        else:
            out = {
                "tr": f"{first} {p.get('start')}. ders saatinde {p.get('duration')} saat olarak sabit ve günün son "
                "ders saatini aşıyor. Süreyi kısaltın veya daha erken başlatın.",
                "en": f"{first} starts at period {p.get('start')} for {p.get('duration')} periods, past the last "
                "period of the day. Shorten it or start it earlier.",
            }
    elif code == "out_of_horizon":
        weeks = _weeks_text(_as_list(p.get("weeks")))
        out = {
            "tr": f"{first} bu çalışmanın haftalarında yok ({weeks}. hafta); derslik kullanmıyor.",
            "en": f"{first} has no week in this run (week(s) {weeks}); it takes no room.",
        }
    elif code == "core":
        names = ", ".join(lab(i) for i in ids[:6]) + (" ..." if len(ids) > 6 else "")
        out = {
            "tr": f"Bu dersler birlikte yerleştirilemiyor: {names}. Birinin saatini, dersliğini veya kilidini "
            "değiştirin.",
            "en": f"These classes cannot all be placed together: {names}. Change the time, room or lock of one "
            "of them.",
        }
    elif code == "no_core":
        out = {
            "tr": "Çizelge çıkmıyor ve çakışan dersler süre içinde ayrıştırılamadı. Süreyi uzatın veya daha kısa "
            "bir dönemi (tek hafta) çözün.",
            "en": "No timetable exists and the clashing classes could not be isolated in time. Raise the time "
            "limit or solve a shorter horizon (one week).",
        }
    elif code == "relax_timeout":
        out = {
            "tr": "Süre içinde kısmi bir çizelge bulunamadı. Süreyi uzatın veya hafta hafta çözün.",
            "en": "No partial timetable was found within the time limit. Raise the time limit or solve week by week.",
        }
    elif code == "timeout":
        out = {
            "tr": "Süre içinde çizelge bulunamadı. Süreyi uzatın, hafta hafta çözün veya daha fazla dersi kilitleyin.",
            "en": "No timetable was found within the time limit. Raise the time limit, solve week by week or lock "
            "more classes.",
        }
    elif code == "internal":
        out = {
            "tr": "Çözücü iç hatası: sonuç kurallara göre doğrulanamadı. Bu çalışmayı destek ekibine bildirin "
            "(ayrıntı aşağıda).",
            "en": "Internal solver error: the result could not be validated against the rules. Please report "
            "this run (details below).",
        }
    elif code in ("outside_room_pool", "room_without_capacity"):
        names = ", ".join(lab(i) for i in ids[:6]) or humanize(str(d.get("message") or "").split(":", 1)[-1], ctx)
        out = {
            "tr": f"Havuz dışı / kapasitesi bilinmeyen derslikler: {names}. Derslik listesine kapasiteyle ekleyin.",
            "en": f"Rooms outside the pool / without a capacity: {names}. Add them with a capacity to the room master.",
        }
    if out is None:
        text = humanize(str(d.get("message") or ""), ctx, "en")
        out = {"tr": humanize(str(d.get("message") or ""), ctx, "tr"), "en": text}
    return out


_CAUSE_TR = {
    "D1": "planlayıcının küçük / özelliği eksik dersliği korundu",
    "D2": "aynı saate sabitlenmiş derslerin çakışması",
    "week_split": "kapalı haftalarda derslik değişikliği",
    "outside_pool": "havuz dışı derslik çakışması",
    "missing_enrolment": "öğrenci sayısı tahmini",
    "manual": "elle yerleştirme",
}
_CAUSE_EN = {
    "D1": "planner's room kept although too small / missing a tag",
    "D2": "clashes of classes fixed at the same time",
    "week_split": "room changes in blocked weeks",
    "outside_pool": "overlaps in rooms outside the pool",
    "missing_enrolment": "estimated enrolments",
    "manual": "manual placements",
}
_FALLBACK_TR = {
    "course_sections": "aynı dersin diğer şubelerinin ortancası",
    "cohort_median": "programın o sınıfının ortancası",
    "term_median": "dönemin ortancası",
    "none": "hiç öğrenci sayısı yok",
}
_FALLBACK_EN = {
    "course_sections": "median of the course's other sections",
    "cohort_median": "median of the programme year",
    "term_median": "median of the term",
    "none": "no enrolment anywhere",
}

#: report order: unplaced classes first, then the planner's data errors, input clashes, warnings, info
_ORDER = {
    "partial": 0,
    "unplaced": 1,
    "no_room": 1,
    "no_time": 1,
    "bad_time": 1,
    "locked_ineligible": 1,
    "locked_blocked": 1,
    "unplaced_summary": 2,
    "locked_overlap": 3,
    "outside_pool_overlap": 3,
    "pigeonhole": 3,
    "fixed_conflict": 3,
    "core": 3,
    "input_conflict": 4,
}


def report_rank(d: dict[str, Any]) -> tuple[int, int]:
    code = str(d.get("code") or "")
    if code in _ORDER:
        return (_ORDER[code], 0)
    sev = str(d.get("severity") or "")
    if code == "trusted_lock_capacity" and (d.get("params") or {}).get("shared"):
        return (3, 1)  # shared exam rooms over capacity: a prominent planner data issue
    return (5 if sev == "error" else 6 if sev == "warning" else 7, 0)


def order_for_report(diags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable sort: unplaced classes, input data errors, fixed-time clashes, warnings, info."""
    return [d for _r, d in sorted(enumerate(diags), key=lambda x: (report_rank(x[1]), x[0]))]


async def text_context(
    session: AsyncSession, run: ScheduleRun, diags: list[dict[str, Any]], members: dict[int, list[int]] | None = None
) -> TextContext:
    """Labels / times of the events named in ``diags`` (and in their params), instructor and programme
    names, read from the DB."""
    ids: set[int] = set()
    keys: set[str] = set()
    for d in diags:
        ids |= {int(i) for i in d.get("event_ids") or []}
        p = d.get("params") or {}
        for key in ("busy", "clashes"):
            for x in _as_list(p.get(key)):
                if isinstance(x, dict):
                    ids |= {int(h) for h in _as_list(x.get("holders"))}
                    if x.get("key"):
                        keys.add(str(x["key"]))
        for k in _as_list(p.get("keys")):
            if isinstance(k, list | tuple) and len(k) == 2:
                keys.add(str(k[1]))
        if p.get("key"):
            keys.add(str(p["key"]))
        keys |= {f"INS:{m[0]}" for m in _INS_RX.findall(str(d.get("message") or ""))}
    mem = members if members is not None else await _members(session, run, ids)
    rows = await _class_rows(session, run, {r for e in ids for r in mem.get(e, [e])})
    ctx = TextContext(stats=dict(run.stats or {}), exam=run.kind == "EXAM")
    ctx.rooms = {int(i): str(c) for i, c in (await session.execute(select(Room.id, Room.code))).all()}
    for e in ids:
        reqs = [rows[r] for r in mem.get(e, [e]) if r in rows]
        if not reqs:
            continue
        names = list(dict.fromkeys(f"{r['course_code']}{' §' + r['section'] if r['section'] else ''}" for r in reqs))
        ctx.labels[e] = " + ".join(names[:3]) + (f" + {len(names) - 3}" if len(names) > 3 else "")
        r0 = reqs[0]
        if r0.get("day") and r0.get("start_period"):
            ctx.times[e] = (int(r0["day"]), int(r0["start_period"]), int(r0["end_period"]))
    ins_ids = {int(k[4:]) for k in keys if re.fullmatch(r"INS:\d+", k)}
    if ins_ids:
        ctx.instructors = {
            int(i): str(n)
            for i, n in (
                await session.execute(select(Instructor.id, Instructor.full_name).where(Instructor.id.in_(ins_ids)))
            ).all()
        }
    progs = {m.group(1) for k in keys if (m := re.fullmatch(r"PROG:([^:]+):Y\d+", k))}
    if progs:
        ctx.programs = {
            str(c): str(n)
            for c, n in (
                await session.execute(
                    select(Program.canonical_name, Program.name).where(Program.canonical_name.in_(progs))
                )
            ).all()
        }
    return ctx


def message_tr(d: dict[str, Any], ctx: TextContext | None = None) -> str:
    """Turkish planner text of one diagnosis (see :func:`planner_text`)."""
    return planner_text(d, ctx)["tr"]


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
                "start_period": ex.start_period,
                "end_period": ex.end_period,
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
            "start_period": mr.start_period,
            "end_period": mr.end_period,
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


def _norm_code(code: str) -> str:
    """Course code key: no spaces, ``İ`` folded, no leading zeros (``SYS 018`` = ``SYS18``)."""
    from app.importers.normalize import course_key

    return course_key(code)


def _weeks_of_row(a: Assignment) -> set[int]:
    return {int(w) for w in a.weeks or ([a.week] if a.week else [])}


async def _run_weeks(session: AsyncSession, run: ScheduleRun) -> set[int] | None:
    """The run's horizon weeks (``None`` = no limit: a run without a term)."""
    from app.models import Term
    from app.services.solver_bridge import horizon_weeks

    if run.term_id is None:
        return None
    term = await session.get(Term, run.term_id)
    if term is None:
        return None
    weeks = set(horizon_weeks(run, term))
    if run.kind == "EXAM" and run.horizon == "TERM":
        return None  # exams of a term run may sit outside the lecture weeks (early finals)
    return weeks


async def board_vs_list(session: AsyncSession, run: ScheduleRun) -> list[dict[str, Any]]:
    """LOCKED requests whose definitive room disagrees with the published weekly board (the grid
    import's run) at the same course, day and periods — per week, e.g. "PHAR 240 §1: list A 206, board
    D 106 in weeks 1-3"."""
    board = await _board_run(session, run)
    if board is None:
        return []
    exam = run.kind == "EXAM"
    cells: dict[tuple[str, Any], list[Assignment]] = {}
    for a in (
        await session.execute(select(Assignment).where(Assignment.run_id == board.id, Assignment.archived.is_(False)))
    ).scalars():
        for c in a.course_codes or []:
            cells.setdefault((_norm_code(str(c)), a.date if exam else a.day), []).append(a)
    if not cells:
        return []
    room_codes = {int(i): str(c) for i, c in (await session.execute(select(Room.id, Room.code))).all()}
    found: list[tuple[int, list[int], list[int], list[int]]] = []  # request, list rooms, board rooms, weeks
    run_weeks = await _run_weeks(session, run)
    if exam:
        qe = select(ExamRequest).where(
            ExamRequest.term_id == run.term_id, ExamRequest.status == "LOCKED", ExamRequest.archived.is_(False)
        )
        for ex in (await session.execute(qe)).scalars():
            rooms = {int(r) for r in ex.definitive_room_ids or []}
            if not rooms or ex.date is None or ex.start_period is None or ex.end_period is None:
                continue
            hits = [
                a
                for a in cells.get((_norm_code(ex.course_code), ex.date), [])
                if a.start_period <= ex.end_period
                and ex.start_period <= a.end_period
                and (run_weeks is None or not _weeks_of_row(a) or _weeks_of_row(a) & run_weeks)
            ]
            if hits and not any(rooms & {int(r) for r in a.room_ids or []} for a in hits):
                board_rooms = sorted({int(r) for a in hits for r in a.room_ids or []})
                found.append((ex.id, sorted(rooms), board_rooms, []))
    else:
        qm = (
            select(MeetingRequest)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(
                Section.term_id == run.term_id, MeetingRequest.status == "LOCKED", MeetingRequest.archived.is_(False)
            )
            .options(selectinload(MeetingRequest.section).selectinload(Section.course))
        )
        for mr in (await session.execute(qm)).scalars():
            rooms = {int(r) for r in mr.definitive_room_ids or []}
            if not rooms or mr.day is None or mr.start_period is None or mr.end_period is None:
                continue
            hits = [
                a
                for a in cells.get((_norm_code(mr.section.course.code), mr.day), [])
                if a.start_period <= mr.end_period and mr.start_period <= a.end_period
            ]
            if not hits:
                continue
            req_weeks = {int(w) for w in mr.weeks or []}
            by_week: dict[int, set[int]] = {}
            for a in hits:
                for w in a.weeks or ([a.week] if a.week else []):
                    if run_weeks is not None and int(w) not in run_weeks:
                        continue  # the board's other weeks are not this run's business (MINOR)
                    if not req_weeks or int(w) in req_weeks:
                        by_week.setdefault(int(w), set()).update(int(r) for r in a.room_ids or [])
            bad = sorted(w for w, rs in by_week.items() if not rs & rooms)
            if bad:
                board_rooms = sorted({r for w in bad for r in by_week[w]})
                found.append((mr.id, sorted(rooms), board_rooms, bad))
    if not found:
        return []
    rows = await _class_rows(session, run, {f[0] for f in found})
    out: list[dict[str, Any]] = []
    for rid, list_rooms, board_rooms, weeks in found:
        row = rows.get(rid)
        if row is None:
            continue
        name = f"{row['course_code']}{' §' + row['section'] if row['section'] else ''}"
        lr = " / ".join(room_codes.get(r, str(r)) for r in list_rooms)
        br = " / ".join(room_codes.get(r, str(r)) for r in board_rooms)
        slot_tr = row.get("date") or _slot("tr", row.get("day"), row.get("start_period"), row.get("end_period"))
        slot_en = row.get("date") or _slot("en", row.get("day"), row.get("start_period"), row.get("end_period"))
        wk = _weeks_text(weeks)
        out.append(
            {
                "diagnosis_index": -1,
                "code": "board_vs_list",
                "severity": "warning",
                "message": f"{name} ({slot_en}): the planning list says {lr}, the published board has {br}"
                + (f" in week(s) {wk}" if wk else "")
                + ".",
                "message_tr": f"{name} ({slot_tr}): planlama listesinde {lr}, yayınlanan panoda {br}"
                + (f" ({wk}. hafta)" if wk else "")
                + ".",
                "detail": "",
                "suggestions": [f"correct the definitive room in the planning list or the board cell ({br} → {lr})"],
                "event_ids": [],
                "request_ids": [rid],
                "unplaced": False,
                "params": {"list_rooms": lr, "board_rooms": br, "weeks": weeks},
                "classes": [{**row, "board_rooms": br}],
            }
        )
    return out


async def _board_run(session: AsyncSession, run: ScheduleRun) -> ScheduleRun | None:
    """The published weekly board of the run's term and kind (the grid import's run)."""
    rows = (
        (
            await session.execute(
                select(ScheduleRun)
                .where(ScheduleRun.term_id == run.term_id, ScheduleRun.kind == run.kind, ScheduleRun.id != run.id)
                .order_by(ScheduleRun.id)
            )
        )
        .scalars()
        .all()
    )
    return next((r for r in rows if (r.params or {}).get("source") == "GRID_IMPORT"), None)


@dataclass
class _BoardReq:
    """A request as the board checks see it."""

    id: int
    key: str
    days: tuple[int, ...]
    when: Any  # exam date (None for courses)
    start: int
    end: int
    weeks: frozenset[int]
    size: int
    instructors: frozenset[int]
    definitive: frozenset[int]
    group: str  # exams: merge key (one exam of several cohorts); courses: the request id


@dataclass
class _BoardBlock:
    """One class on the board: one room (set), one label, consecutive periods of one day and week."""

    week: int
    day: int
    date: Any
    start: int
    end: int
    rooms: tuple[int, ...]
    label: str
    keys: tuple[str, ...]
    refs: list[str]


@dataclass
class _BoardCase:
    group: str
    weeks: set[int] = field(default_factory=set)
    cells: set[str] = field(default_factory=set)
    rooms: set[int] = field(default_factory=set)
    slots: set[tuple[Any, Any, int, int]] = field(default_factory=set)
    request_ids: list[int] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


def _cell_ref(source_key: str | None, sheets: dict[int, str]) -> str:
    """``GRID:term:file:3:CT9:98`` -> ``"'16 - 22 Şubat'!CT9"`` (the Excel cell the planner opens)."""
    parts = (source_key or "").split(":")
    if len(parts) < 5 or not parts[-3].isdigit():
        return ""
    return f"'{sheets.get(int(parts[-3]), parts[-3])}'!{parts[-2]}"


async def board_checks(session: AsyncSession, run: ScheduleRun) -> dict[str, list[dict[str, Any]]]:
    """Checks of the published weekly board alone (comparison §7.3, §7.5), in the run's weeks:

    * ``board_capacity`` - a class alone in one board room with more students than seats (the planner's
      definitive room of that class is checked by the list checks already);
    * ``board_instructor_clash`` - two board cells of one instructor overlap although the list times of the
      two classes do not (a clash the board's times create; list clashes are ``fixed_instructor_clash``);
    * ``board_two_classes`` - one board cell holds two courses that the list gives different instructors;
    * ``board_unknown_code`` - a board course code the list does not have;
    * ``board_time_not_in_list`` - a board cell of a listed course on a day / time the list does not have;
    * ``board_missing_week`` - weeks of the run the board has no sheet for.

    A pattern repeated every week is one item with its weeks.  Group code -> items."""
    from app.importers.normalize import course_key, non_person_reason
    from app.models import Block, Term, Week

    out: dict[str, list[dict[str, Any]]] = {
        k: []
        for k in (
            "board_capacity",
            "board_instructor_clash",
            "board_two_classes",
            "board_unknown_code",
            "board_time_not_in_list",
            "board_missing_week",
        )
    }
    board = await _board_run(session, run)
    if board is None or run.term_id is None:
        return out
    exam = run.kind == "EXAM"
    run_weeks = await _run_weeks(session, run)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    sheets = {
        int(w.index): str(w.label or w.index)
        for w in (await session.execute(select(Week).where(Week.term_id == run.term_id))).scalars()
    }
    cells = list(
        (
            await session.execute(
                select(Assignment).where(Assignment.run_id == board.id, Assignment.archived.is_(False))
            )
        ).scalars()
    )

    # --- weeks without a sheet ----------------------------------------------------------------------
    covered = {w for a in cells for w in _weeks_of_row(a)}
    for blk in (
        await session.execute(
            select(Block).where(Block.term_id == run.term_id, Block.source == "GRID_IMPORT", Block.archived.is_(False))
        )
    ).scalars():
        if blk.weeks:
            covered.add(int(blk.weeks[0]))  # the sheet's own week (later weeks: carried forward by a setting)
    if covered and not exam:
        term = await session.get(Term, run.term_id)
        horizon = (
            set(run_weeks)
            if run_weeks is not None
            else set(range(1, int(term.week_count or 14) + 1))
            if term
            else set()
        )
        missing = sorted(horizon - covered)
        if missing:
            wk = _weeks_text(missing)
            have = _weeks_text(covered)
            out["board_missing_week"].append(
                {
                    **_list_item(
                        "board_missing_week",
                        (
                            f"Pano yalnızca {len(covered)} haftayı kapsıyor ({have}. hafta); {wk}. hafta(lar) için "
                            "sayfa yok, bu haftalarda kapalı derslikler ve etkinlikler bilinmiyor.",
                            f"The board covers only {len(covered)} week(s) ({have}); it has no sheet for week(s) "
                            f"{wk}, so closed rooms and events of those weeks are unknown.",
                        ),
                        [],
                        {},
                        {"weeks": missing, "board_weeks": sorted(covered)},
                    ),
                    "suggestions": ["publish the week sheet, or set IMPORT_GRID_CARRY_FORWARD=1 and re-import"],
                }
            )

    # --- the list's requests by course key ---------------------------------------------------------
    by_key: dict[str, list[_BoardReq]] = {}
    names: dict[int, str] = {}
    if exam:
        qe = select(ExamRequest).where(ExamRequest.term_id == run.term_id, ExamRequest.archived.is_(False))
        for ex in (await session.execute(qe)).scalars():
            if ex.start_period is None or ex.end_period is None or ex.date is None:
                key = course_key(ex.course_code)
                by_key.setdefault(key, [])
                continue
            r = _BoardReq(
                ex.id,
                course_key(ex.course_code),
                (ex.date.isoweekday(),),
                ex.date,
                int(ex.start_period),
                int(ex.end_period),
                frozenset(),
                int(ex.enrolment or 0),
                frozenset(),
                frozenset(int(x) for x in ex.definitive_room_ids or []),
                str(ex.merge_key or f"single:{ex.id}"),
            )
            by_key.setdefault(r.key, []).append(r)
    else:
        names = {
            int(i): str(n)
            for i, n in (await session.execute(select(Instructor.id, Instructor.full_name))).all()
            if non_person_reason(n) is None
        }
        qm = (
            select(MeetingRequest)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == run.term_id, MeetingRequest.archived.is_(False))
            .options(
                selectinload(MeetingRequest.section).selectinload(Section.course),
                selectinload(MeetingRequest.section).selectinload(Section.instructors),
            )
        )
        for mr in (await session.execute(qm)).scalars():
            key = course_key(mr.section.course.code)
            days = tuple(int(d) for d in (mr.days or ([mr.day] if mr.day else [])))
            if mr.start_period is None or mr.end_period is None or not days:
                by_key.setdefault(key, [])
                continue
            r = _BoardReq(
                mr.id,
                key,
                days,
                None,
                int(mr.start_period),
                int(mr.end_period),
                frozenset(int(w) for w in mr.weeks or []),
                int(mr.section.enrolment or 0),
                frozenset(int(si.instructor_id) for si in mr.section.instructors if int(si.instructor_id) in names),
                frozenset(int(x) for x in mr.definitive_room_ids or []),
                str(mr.id),
            )
            by_key.setdefault(key, []).append(r)

    def matches(b: _BoardBlock, w: int, key: str) -> list[_BoardReq]:
        out_: list[_BoardReq] = []
        for r in by_key.get(key, []):
            if exam:
                if r.when != b.date:
                    continue
            elif b.day not in r.days or (r.weeks and w not in r.weeks):
                continue
            if r.start <= b.end and b.start <= r.end:
                out_.append(r)
        return out_

    # --- board cells -> blocks: one class in one room on consecutive periods (the board writes one cell per
    # period row), per week -------------------------------------------------------------------------------
    raw: dict[tuple[Any, ...], list[Assignment]] = {}
    for a in cells:
        keys = tuple(dict.fromkeys(course_key(str(c)) for c in a.course_codes or [] if c))
        if not keys:
            continue
        for w in sorted(_weeks_of_row(a)):
            if run_weeks is not None and w not in run_weeks:
                continue
            day = a.date if exam else a.day
            raw.setdefault((w, day, tuple(sorted(int(x) for x in a.room_ids or [])), a.label or "", keys), []).append(a)
    by_week: dict[int, list[_BoardBlock]] = {}
    for (w, _day, room_ids, label, keys), xs in raw.items():
        xs.sort(key=lambda a: (a.start_period, a.end_period))
        cur: _BoardBlock | None = None
        for a in xs:
            ref = _cell_ref(a.source_key, sheets)
            if cur is not None and a.start_period <= cur.end + 1:
                cur.end = max(cur.end, a.end_period)
                if ref:
                    cur.refs.append(ref)
                continue
            cur = _BoardBlock(
                w, a.day, a.date, a.start_period, a.end_period, room_ids, label, keys, [ref] if ref else []
            )
            by_week.setdefault(w, []).append(cur)

    cases: dict[tuple[Any, ...], _BoardCase] = {}

    def case(group: str, sig: tuple[Any, ...], b: _BoardBlock | None = None) -> _BoardCase:
        c = cases.setdefault((group, *sig), _BoardCase(group))
        if b is not None:
            c.weeks.add(b.week)
            c.rooms.update(b.rooms)
            c.cells.update(b.refs[:1])  # the first cell of the block is the one to open
            c.slots.add((b.day, b.date, b.start, b.end))
        return c

    for w, blocks in sorted(by_week.items()):
        # rooms of a course on a day (a class spread over several board rooms is no single-room class)
        spread: dict[tuple[Any, str], list[_BoardBlock]] = {}
        for b in blocks:
            for k in b.keys:
                spread.setdefault((b.date if exam else b.day, k), []).append(b)
        matched_of: dict[int, dict[str, list[_BoardReq]]] = {}
        for b in blocks:
            matched = {k: matches(b, w, k) for k in b.keys}
            matched_of[id(b)] = matched
            known = [k for k in b.keys if k in by_key]
            if not known:
                case("board_unknown_code", (b.label,), b)
                continue
            if not any(matched[k] for k in known):
                c = case("board_time_not_in_list", (b.label, b.date if exam else b.day, b.start, b.end), b)
                c.request_ids = list(dict.fromkeys([*c.request_ids, *(r.id for k in known for r in by_key[k][:3])]))
                continue
            # one class alone in one room: capacity
            if len(known) == 1 and len(b.rooms) == 1 and b.rooms[0] in rooms:
                k = known[0]
                room = rooms[b.rooms[0]]
                seats = int(((room.exam_capacity or room.capacity) if exam else room.capacity) or 0)
                elsewhere = any(
                    o is not b and o.rooms != b.rooms and o.start <= b.end and b.start <= o.end
                    for o in spread.get((b.date if exam else b.day, k), [])
                )
                reqs = [r for r in matched[k] if b.rooms[0] not in r.definitive]
                if exam:
                    sizes: dict[str, int] = {}
                    for r in matched[k]:
                        sizes[r.group] = sizes.get(r.group, 0) + r.size
                    size = max(sizes.values(), default=0)
                else:
                    size = max((r.size for r in reqs), default=0)
                if seats and size > seats and reqs and not elsewhere:
                    c = case("board_capacity", (b.label, b.date if exam else b.day, b.start, b.end, b.rooms[0]), b)
                    c.request_ids = list(dict.fromkeys([*c.request_ids, *(r.id for r in reqs)]))
                    c.params = {"seats": seats, "size": size}
            # two courses in one cell that the list does not give as one lecture
            if not exam and len(known) >= 2:
                for i, ka in enumerate(known):
                    for kb in known[i + 1 :]:
                        ra, rb = matched[ka], matched[kb]
                        if not ra or not rb:
                            continue
                        ia = frozenset().union(*(r.instructors for r in ra))
                        ib = frozenset().union(*(r.instructors for r in rb))
                        same_lock = any(x.definitive and x.definitive == y.definitive for x in ra for y in rb)
                        if ia & ib or same_lock or not ia or not ib:
                            continue
                        c = case("board_two_classes", (b.label, b.day, b.start, b.end, ka, kb), b)
                        c.request_ids = list(dict.fromkeys([*c.request_ids, ra[0].id, rb[0].id]))
        # instructor clashes the board times create
        if not exam:
            per_ins: dict[tuple[int, int], list[tuple[_BoardBlock, str, _BoardReq]]] = {}
            for b in blocks:
                for k, rs in matched_of[id(b)].items():
                    for r in rs:
                        for ins in r.instructors:
                            per_ins.setdefault((ins, b.day), []).append((b, k, r))
            for (ins, day), pairs_of in per_ins.items():
                for i, (p1, ka, qa) in enumerate(pairs_of):
                    for p2, kb, qb in pairs_of[i + 1 :]:
                        if ka == kb or set(p1.rooms) & set(p2.rooms) or p1.start > p2.end or p2.start > p1.end:
                            continue
                        if set(qa.days) & set(qb.days) and qa.start <= qb.end and qb.start <= qa.end:
                            continue  # the list itself clashes: fixed_instructor_clash reports it
                        pair = tuple(sorted([(ka, p1.start, p1.end), (kb, p2.start, p2.end)]))
                        c = case("board_instructor_clash", (day, ins, pair))
                        for x in (p1, p2):
                            c.weeks.add(x.week)
                            c.rooms.update(x.rooms)
                            c.cells.update(x.refs[:1])
                        c.request_ids = list(dict.fromkeys([*c.request_ids, qa.id, qb.id]))
                        first, second = sorted((p1, p2), key=lambda x: (x.start, x.label))
                        c.params = {
                            "instructor": names.get(ins, str(ins)),
                            "labels": [first.label, second.label],
                            "slots": [[first.start, first.end], [second.start, second.end]],
                        }

    if not cases:
        return out
    rows = await _class_rows(session, run, {r for c in cases.values() for r in c.request_ids})

    def slots_text(c: _BoardCase, lang: str) -> str:
        parts = []
        for day, d, start, end in sorted(c.slots, key=lambda x: (str(x[1]), x[0], x[2])):
            if exam:
                parts.append(f"{d.isoformat() if d else ''} {_clock(start, end)}".strip())
            else:
                parts.append(_slot(lang, day, start, end))
        return "; ".join(parts[:4]) + (" ..." if len(parts) > 4 else "")

    for sig, c in sorted(cases.items(), key=lambda kv: (kv[0][0], sorted(kv[1].weeks), str(kv[0][1:]))):
        group = c.group
        wk = _weeks_text(sorted(c.weeks))
        rooms_txt = " / ".join(sorted(rooms[r].code for r in c.rooms if r in rooms))
        cells_txt = ", ".join(sorted(c.cells)[:4]) + (" ..." if len(c.cells) > 4 else "")
        label = str(sig[1]) if group != "board_instructor_clash" else ""
        when_tr, when_en = slots_text(c, "tr"), slots_text(c, "en")
        if group == "board_instructor_clash":
            day = sig[1]
            labels = list(c.params.get("labels") or [])
            span = [_clock(a, b) for a, b in c.params.get("slots") or []]
            who = c.params.get("instructor")
            msg = (
                f"{who}: panoda {' ve '.join(labels)} aynı anda ({DAY_TR.get(day, day)} {' / '.join(span)}, "
                f"{rooms_txt}; {wk}. hafta); listede saatleri çakışmıyor. Hücreler: {cells_txt}.",
                f"{who}: the board has {' and '.join(labels)} at the same time ({DAY_EN.get(day, day)} "
                f"{' / '.join(span)}, {rooms_txt}; week(s) {wk}); their list times do not overlap. Cells: {cells_txt}.",
            )
        elif group == "board_capacity":
            msg = (
                f"Panoda {label} ({when_tr}, {wk}. hafta) tek başına {rooms_txt} dersliğinde: {c.params['seats']} "
                f"{'sınav koltuğu' if exam else 'kişilik'}, derste {c.params['size']} öğrenci var. Hücre: {cells_txt}.",
                f"The board puts {label} ({when_en}, week(s) {wk}) alone in {rooms_txt}: {c.params['seats']} "
                f"{'exam ' if exam else ''}seats for {c.params['size']} students. Cell: {cells_txt}.",
            )
        elif group == "board_two_classes":
            msg = (
                f"Panoda bir hücrede iki ders: {label} ({when_tr}, {rooms_txt}; {wk}. hafta); listede öğretim "
                f"elemanları farklı. Hücre: {cells_txt}.",
                f"One board cell holds two courses: {label} ({when_en}, {rooms_txt}; week(s) {wk}); the list gives "
                f"them different instructors. Cell: {cells_txt}.",
            )
        elif group == "board_unknown_code":
            msg = (
                f"Panodaki {label} planlama listesinde yok ({when_tr}; {rooms_txt}; {wk}. hafta). Hücre: {cells_txt}.",
                f"The board's {label} is not in the planning list ({when_en}; {rooms_txt}; week(s) {wk}). "
                f"Cell: {cells_txt}.",
            )
        else:
            msg = (
                f"Panoda {label} {when_tr} ({rooms_txt}; {wk}. hafta); listede bu ders bu gün ve saatte yok. "
                f"Hücre: {cells_txt}.",
                f"The board has {label} on {when_en} ({rooms_txt}; week(s) {wk}); the list has no such day and time "
                f"for it. Cell: {cells_txt}.",
            )
        params = {
            **c.params,
            "weeks": sorted(c.weeks),
            "room_codes": sorted(rooms[r].code for r in c.rooms if r in rooms),
            "cells": sorted(c.cells),
        }
        item = _list_item(group, msg, c.request_ids, rows, params)
        item["classes"] = [{**cls, "board_rooms": rooms_txt} for cls in item["classes"]]
        out[group].append(item)
    return out
    rows = await _class_rows(session, run, {r for c in cases.values() for r in c.request_ids})
    for sig, c in sorted(cases.items(), key=lambda kv: (kv[0][0], sorted(kv[1].weeks), str(kv[0][1:]))):
        group = c.group
        wk = _weeks_text(sorted(c.weeks))
        rooms_txt = " / ".join(sorted(rooms[r].code for r in c.rooms if r in rooms))
        cells_txt = ", ".join(sorted(c.cells)[:4]) + (" ..." if len(c.cells) > 4 else "")
        if group == "board_instructor_clash":
            day = sig[1]
            labels = " ve ".join(str(x) for x in c.params.get("labels") or [])
            labels_en = " and ".join(str(x) for x in c.params.get("labels") or [])
            who = c.params.get("instructor")
            msg = (
                f"{who}: panoda {labels} aynı anda ({DAY_TR.get(day, day)}, {rooms_txt}; {wk}. hafta); listede "
                f"saatleri çakışmıyor. Hücreler: {cells_txt}.",
                f"{who}: the board has {labels_en} at the same time ({DAY_EN.get(day, day)}, {rooms_txt}; week(s) "
                f"{wk}); their list times do not overlap. Cells: {cells_txt}.",
            )
        else:
            day, start, end, label = sig[1], sig[2], sig[3], sig[4]
            if exam:
                when_tr = when_en = f"{day.isoformat() if day else ''} {_clock(start, end)}".strip()
            else:
                when_tr, when_en = _slot("tr", day, start, end), _slot("en", day, start, end)
            if group == "board_capacity":
                msg = (
                    f"Panoda {label} ({when_tr}, {wk}. hafta) tek başına {rooms_txt} dersliğinde: "
                    f"{c.params['seats']} kişilik, derste {c.params['size']} öğrenci var. Hücre: {cells_txt}.",
                    f"The board puts {label} ({when_en}, week(s) {wk}) alone in {rooms_txt}: {c.params['seats']} "
                    f"seats for {c.params['size']} students. Cell: {cells_txt}.",
                )
            elif group == "board_two_classes":
                msg = (
                    f"Panoda bir hücrede iki ders: {label} ({when_tr}, {rooms_txt}; {wk}. hafta); listede "
                    f"öğretim elemanları farklı. Hücre: {cells_txt}.",
                    f"One board cell holds two courses: {label} ({when_en}, {rooms_txt}; week(s) {wk}); the list "
                    f"gives them different instructors. Cell: {cells_txt}.",
                )
            elif group == "board_unknown_code":
                msg = (
                    f"Panodaki {label} ({when_tr}, {rooms_txt}; {wk}. hafta) planlama listesinde yok. "
                    f"Hücre: {cells_txt}.",
                    f"The board's {label} ({when_en}, {rooms_txt}; week(s) {wk}) is not in the planning list. "
                    f"Cell: {cells_txt}.",
                )
            else:
                msg = (
                    f"Panoda {label} {when_tr} ({rooms_txt}; {wk}. hafta); listede bu ders bu gün ve saatte yok. "
                    f"Hücre: {cells_txt}.",
                    f"The board has {label} on {when_en} ({rooms_txt}; week(s) {wk}); the list has no such day "
                    f"and time for it. Cell: {cells_txt}.",
                )
        params = {
            **c.params,
            "weeks": sorted(c.weeks),
            "room_codes": sorted(rooms[r].code for r in c.rooms if r in rooms),
            "cells": sorted(c.cells),
        }
        item = _list_item(group, msg, c.request_ids, rows, params)
        for cls in item["classes"]:
            cls.setdefault("board_rooms", rooms_txt)
        item["classes"] = [{**cls, "board_rooms": rooms_txt} for cls in item["classes"]]
        out[group].append(item)
    return out


def _list_item(
    code: str, group_msg: tuple[str, str], rids: list[int], rows: dict[int, dict[str, Any]], params: dict[str, Any]
) -> dict[str, Any]:
    return {
        "diagnosis_index": -1,
        "code": code,
        "severity": "warning",
        "message": group_msg[1],
        "message_tr": group_msg[0],
        "detail": "",
        "suggestions": [],
        "event_ids": [],
        "request_ids": rids,
        "unplaced": False,
        "params": params,
        "classes": [rows[r] for r in rids if r in rows],
    }


async def list_checks(session: AsyncSession, run: ScheduleRun) -> dict[str, list[dict[str, Any]]]:
    """The planner's list checked from the data alone — two LOCKED rows in one room at one time, a locked
    room without the requested PC tag, a locked room blocked by the grid — for runs whose solver did not
    lock the definitive rooms (``definitive_rooms`` prefer / ignore), so the report lists them in every mode
    (in lock mode the solver's diagnoses already do).  Group code -> items."""
    from app.models import Block

    out: dict[str, list[dict[str, Any]]] = {"locked_room_overlap": [], "missing_tags": [], "locked_room_blocked": []}
    if run.kind == "EXAM":
        return out  # exams share rooms by design; their seat checks belong to the solver
    run_weeks = await _run_weeks(session, run)
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    q = (
        select(MeetingRequest)
        .join(Section, Section.id == MeetingRequest.section_id)
        .where(
            Section.term_id == run.term_id,
            MeetingRequest.status == "LOCKED",
            MeetingRequest.archived.is_(False),
            MeetingRequest.needs_room.is_(True),
        )
        .options(selectinload(MeetingRequest.section).selectinload(Section.course))
    )
    locked = []
    for mr in (await session.execute(q)).scalars():
        ids = [int(r) for r in mr.definitive_room_ids or [] if int(r) in rooms]
        if not ids or mr.day is None or mr.start_period is None or mr.end_period is None:
            continue
        weeks = {int(w) for w in mr.weeks or []} or set(run_weeks or range(1, 15))
        if run_weeks is not None:
            weeks &= run_weeks
        if weeks:
            locked.append((mr, ids, weeks))
    found: dict[str, list[tuple[list[int], dict[str, Any]]]] = {k: [] for k in out}
    by_room: dict[tuple[int, int], list[tuple[MeetingRequest, set[int]]]] = {}
    for mr, ids, weeks in locked:
        for r in ids:
            by_room.setdefault((r, int(mr.day or 0)), []).append((mr, weeks))
    for (room_id, _day), items in sorted(by_room.items()):
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, wa = items[i]
                b, wb = items[j]
                assert a.start_period is not None and a.end_period is not None
                assert b.start_period is not None and b.end_period is not None
                if a.start_period > b.end_period or b.start_period > a.end_period or not wa & wb:
                    continue
                if _norm_code(a.section.course.code) == _norm_code(b.section.course.code):
                    continue  # one lecture listed twice (merged by the bridge, reported as such)
                found["locked_room_overlap"].append(
                    ([a.id, b.id], {"room_codes": [rooms[room_id].code], "weeks": sorted(wa & wb)})
                )
        if "PC" not in (rooms[room_id].tags or []):
            for mr, _w in items:
                if "PC" in (mr.requested_tags or []):
                    found["missing_tags"].append(
                        ([mr.id], {"room_codes": [rooms[room_id].code], "missing_tags": ["PC"]})
                    )
    blocks = list(
        (await session.execute(select(Block).where(Block.term_id == run.term_id, Block.archived.is_(False)))).scalars()
    )
    for row, ids, weeks in locked:
        for blk in blocks:
            bday = blk.day or (blk.date.isoweekday() if blk.date else None)
            if blk.room_id not in ids or bday != row.day:
                continue
            r0, r1 = int(row.start_period or 0), int(row.end_period or 0)
            if blk.start_period > r1 or r0 > blk.end_period:
                continue
            hit = sorted(weeks & {int(w) for w in blk.weeks}) if blk.weeks else sorted(weeks)
            if hit:
                found["locked_room_blocked"].append(
                    ([row.id], {"room_codes": [rooms[blk.room_id].code], "weeks": hit, "block": blk.label})
                )
                break
    rows = await _class_rows(session, run, {r for cases in found.values() for rids, _p in cases for r in rids})
    for code, cases in found.items():
        for rids, params in cases:
            names = [
                f"{rows[r]['course_code']}{' §' + rows[r]['section'] if rows[r]['section'] else ''}"
                for r in rids
                if r in rows
            ]
            room = ", ".join(params.get("room_codes") or [])
            wk = _weeks_text(params.get("weeks") or [])
            if code == "locked_room_overlap":
                msg = (
                    f"{' ve '.join(names)} aynı anda {room} dersliğine kilitli ({wk}. hafta).",
                    f"{' and '.join(names)} are both locked to {room} at the same time (week(s) {wk}).",
                )
            elif code == "missing_tags":
                msg = (
                    f"{names[0] if names else '?'} PC dersliği istiyor ama kilitli dersliği {room} PC değil.",
                    f"{names[0] if names else '?'} needs a PC room but is locked to {room}, which is not one.",
                )
            else:
                msg = (
                    f"{names[0] if names else '?'} {room} dersliğine kilitli ama derslik {wk}. hafta(lar)da "
                    f"takvimde kapalı ({params.get('block')}).",
                    f"{names[0] if names else '?'} is locked to {room}, which the grid blocks in week(s) {wk} "
                    f"({params.get('block')}).",
                )
            out[code].append(_list_item(f"list_{code}", msg, rids, rows, params))
    return out


async def capacity_warnings(session: AsyncSession, term_id: int, kind: str = "COURSE") -> list[dict[str, Any]]:
    """Requests whose planner room (definitive, else requested) seats fewer than the enrolment —
    "A 206 has 92 seats, this class has 130" — straight from the data (no run needed; the studio's
    class list can use the same check).  Exams compare with the rooms' exam capacity."""
    exam = kind == "EXAM"
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    found: list[tuple[int, list[int], int, int]] = []  # request, rooms, seats, enrolment
    if exam:
        q = select(ExamRequest).where(ExamRequest.term_id == term_id, ExamRequest.archived.is_(False))
        for ex in (await session.execute(q)).scalars():
            ids = [int(r) for r in (ex.definitive_room_ids or ex.requested_room_ids or []) if int(r) in rooms]
            seats = sum(int(rooms[r].exam_capacity or rooms[r].capacity or 0) for r in ids)
            if ids and seats and int(ex.enrolment or 0) > seats:
                found.append((ex.id, ids, seats, int(ex.enrolment or 0)))
    else:
        qm = (
            select(MeetingRequest)
            .join(Section, Section.id == MeetingRequest.section_id)
            .where(Section.term_id == term_id, MeetingRequest.archived.is_(False), MeetingRequest.needs_room.is_(True))
            .options(selectinload(MeetingRequest.section))
        )
        for mr in (await session.execute(qm)).scalars():
            ids = [int(r) for r in (mr.definitive_room_ids or mr.requested_room_ids or []) if int(r) in rooms]
            seats = sum(int(rooms[r].capacity or 0) for r in ids)
            size = int(mr.section.enrolment or mr.requested_capacity or 0)
            if ids and seats and size > seats:
                found.append((mr.id, ids, seats, size))
    if not found:
        return []
    fake = ScheduleRun(term_id=term_id, kind=kind)
    rows = await _class_rows(session, fake, {f[0] for f in found})
    out: list[dict[str, Any]] = []
    for rid, ids, seats, size in found:
        row = rows.get(rid)
        if row is None:
            continue
        name = f"{row['course_code']}{' §' + row['section'] if row['section'] else ''}"
        codes = " / ".join(rooms[r].code for r in ids)
        what = "sınav koltuğu" if exam else "kişilik"
        out.append(
            {
                "diagnosis_index": -1,
                "code": "room_capacity",
                "severity": "warning",
                "message": f"{name}: {codes} has {seats} {'exam ' if exam else ''}seats, this class has {size}.",
                "message_tr": f"{name}: {codes} {seats} {what}, bu derste {size} öğrenci var.",
                "detail": "",
                "suggestions": ["check the enrolment or choose a bigger room"],
                "event_ids": [],
                "request_ids": [rid],
                "unplaced": False,
                "params": {"room_codes": [rooms[r].code for r in ids], "seats": seats, "size": size},
                "classes": [row],
            }
        )
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
    ctx = await text_context(session, run, [d for items in grouped.values() for _i, d in items])
    board = await board_vs_list(session, run)
    covered = {
        r
        for _i, d in grouped["locked_room_too_small"]
        for e in d.get("event_ids") or []
        for r in members.get(int(e), [int(e)])
    }
    capacity = [
        it for it in await capacity_warnings(session, run.term_id, run.kind) if it["request_ids"][0] not in covered
    ]
    from app.services.solver_bridge import run_mode

    # the list's own checks in every mode: with definitive rooms as hints the solver does not lock them, so
    # it reports no locked overlap / missing tag / blocked lock — the data still has them (orchestrator)
    from_list = await list_checks(session, run) if run_mode(run.params or {}, "definitive_rooms") != "lock" else {}
    # the published board's own errors (comparison §7.3 / §7.5); not part of the solver's input
    from_board = await board_checks(session, run)
    groups_out: list[dict[str, Any]] = []
    for spec in GROUPS:
        items: list[dict[str, Any]] = []
        for idx, d in grouped[spec.code]:
            req_ids = list(dict.fromkeys(r for e in d.get("event_ids") or [] for r in members.get(int(e), [int(e)])))
            text = planner_text(d, ctx)
            items.append(
                {
                    "diagnosis_index": idx,
                    "code": d.get("code") or "",
                    "severity": d.get("severity") or "",
                    "message": text["en"],
                    "message_tr": text["tr"],
                    "detail": d.get("message") or "",
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
        if spec.code == "board_vs_list":
            items = board
        if spec.code == "locked_room_too_small":
            items = items + capacity
        items = items + list(from_list.get(spec.code, [])) + list(from_board.get(spec.code, []))
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
    ("message", "Issue (EN) / Sorun (EN)"),
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
    ("board_rooms", "Panodaki derslik / Board room"),
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
    neutralize_workbook(wb)  # review M8
    wb.save(buf)
    return buf.getvalue()


__all__ = ["GROUPS", "build_data_issues", "classify", "message_tr", "to_xlsx"]
