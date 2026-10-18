"""PER-F05 (fix-h-2026-10-18): a code and a Turkish / English sentence for every importer warning.

The importers write their warnings as English strings ("row 11: weeks value 0; assuming all"); the import report
keeps those strings (old clients, the job history) and adds, per warning, a stable ``code`` with ``message_tr`` and
``message_en``, plus groups by code ("“UZEM” bir kişi değil · 37 satır"). The rules below cover every shape the
importers write (app/importers/normalize.py, planning_list.py, exam_list.py, weekly_grid.py, room_master.py,
catalog.py); an unknown shape keeps its text under the code ``other``.
"""

from __future__ import annotations

import re
from collections import Counter, OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

_WHY = {
    "mode": "öğretim biçimi",
    "placeholder": "yer tutucu",
    "department": "bölüm adı",
    "title_only": "yalnızca unvan",
    "note": "not",
}

#: a code's group title (what the rows of one code have in common)
CODE_LABELS: dict[str, tuple[str, str]] = {
    "instructor_not_person": ("Kişi olmayan öğretim elemanı değeri", "Instructor value that names no person"),
    "weeks_assumed_all": (
        "Hafta değeri anlaşılamadı; bütün haftalar alındı",
        "Weeks value not understood; all weeks assumed",
    ),
    "weeks_ambiguous": ("Belirsiz hafta değeri", "Ambiguous weeks value"),
    "weeks_too_long": ("Dönemden uzun hafta değeri", "Weeks beyond the term"),
    "weeks_until_midterm": ("“Vizeye kadar” 1–7. haftalar", "'Until midterm' as weeks 1-7"),
    "time_snapped": ("Ders saatine yuvarlanan saat", "Time snapped to the period grid"),
    "time_outside_grid": ("Ders saatlerinin dışında kalan saat", "Time outside the period grid"),
    "time_unreadable": ("Okunamayan saat", "Unreadable time"),
    "day_unreadable": ("Anlaşılamayan gün", "Day not understood"),
    "exam_date": ("Sınav tarihi notu", "Exam date note"),
    "room_tagged_pc": ("PC etiketi eklenen derslik", "Room tagged PC"),
    "room_master_kept": ("Derslik listesindeki değer korundu", "Room master value kept"),
    "room_duplicate": ("Tekrarlanan derslik", "Duplicate room"),
    "room_no_capacity": ("Kapasitesi olmayan derslik", "Room without capacity"),
    "no_room_needed": ("Derslik gerekmeyen mekân", "Not a classroom"),
    "course_code_unreadable": ("Anlaşılamayan ders kodu", "Course code not understood"),
    "course_code_placeholder": ("Numarası olmayan ders kodu", "Course code without a number"),
    "course_code_repaired": ("Düzeltilen ders kodu", "Course code repaired"),
    "enrolment_ignored": ("Kullanılmayan öğrenci sayısı", "Enrolment not used"),
    "other": ("Diğer uyarılar", "Other warnings"),
}


def _q(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


Rule = tuple[re.Pattern[str], str, Callable[[re.Match[str]], str]]

_RULES: list[Rule] = [
    (
        re.compile(r"^instructor value (.+) names no person \((\w+)\); not used as an instructor$"),
        "instructor_not_person",
        lambda m: f"“{_q(m[1])}” bir kişi değil ({_WHY.get(m[2], m[2])}); öğretim elemanı sayılmadı",
    ),
    (
        re.compile(r"^weeks value (\d+); assuming all$"),
        "weeks_assumed_all",
        lambda m: f"Hafta değeri {m[1]}; bütün haftalar varsayıldı",
    ),
    (
        re.compile(r"^(?:boolean|fractional|non-week) weeks? value (.+); assuming all$"),
        "weeks_assumed_all",
        lambda m: f"Hafta değeri anlaşılamadı ({_q(m[1])}); bütün haftalar varsayıldı",
    ),
    (
        re.compile(r"^non-week value (.+); assuming all$"),
        "weeks_assumed_all",
        lambda m: f"Hafta değeri anlaşılamadı ({_q(m[1])}); bütün haftalar varsayıldı",
    ),
    (
        re.compile(r"^unparsed weeks text (.+); assuming all$"),
        "weeks_assumed_all",
        lambda m: f"Hafta metni anlaşılamadı ({_q(m[1])}); bütün haftalar varsayıldı",
    ),
    (
        re.compile(r"^ambiguous weeks value (\d+); assuming first \d+ weeks$"),
        "weeks_ambiguous",
        lambda m: f"Hafta değeri {m[1]} belirsiz; ilk {m[1]} hafta varsayıldı",
    ),
    (
        re.compile(r"^weeks value (\d+) exceeds term length (\d+)$"),
        "weeks_too_long",
        lambda m: f"Hafta değeri {m[1]}, dönemin {m[2]} haftasından uzun",
    ),
    (
        re.compile(r"^weeks (.+) exceed term length (\d+); capped$"),
        "weeks_too_long",
        lambda m: f"{m[1]}. haftalar dönemin {m[2]} haftasını aşıyor; kırpıldı",
    ),
    (
        re.compile(r"^'until midterm' approximated as weeks 1-7$"),
        "weeks_until_midterm",
        lambda m: "“Vizeye kadar” 1–7. haftalar olarak alındı",
    ),
    (
        re.compile(r"^time (\d\d:\d\d)-(\d\d:\d\d) snapped to P(\d+)-P(\d+) \((\d\d:\d\d)-(\d\d:\d\d)\)(?:: .+)?$"),
        "time_snapped",
        lambda m: f"{m[1]}–{m[2]} saati P{m[3]}–P{m[4]} ders saatlerine ({m[5]}–{m[6]}) yuvarlandı",
    ),
    (
        re.compile(r"^time (\d\d:\d\d)-(\d\d:\d\d) is outside the period grid$"),
        "time_outside_grid",
        lambda m: f"{m[1]}–{m[2]} saati ders saatlerinin dışında",
    ),
    (re.compile(r"^time range outside grid$"), "time_outside_grid", lambda m: "Saat aralığı ders saatlerinin dışında"),
    (
        re.compile(
            r"^start time (\d\d:\d\d) (?:not on the grid|falls in a break|is before the grid); snapped to P(\d+).*$"
        ),
        "time_snapped",
        lambda m: f"Başlangıç {m[1]}, P{m[2]} ders saatine yuvarlandı",
    ),
    (
        re.compile(r"^end time (\d\d:\d\d) snapped to P(\d+).*$"),
        "time_snapped",
        lambda m: f"Bitiş {m[1]}, P{m[2]} ders saatine yuvarlandı",
    ),
    (
        re.compile(r"^start time (\d\d:\d\d) is after the last period$"),
        "time_outside_grid",
        lambda m: f"Başlangıç {m[1]}, son ders saatinden sonra",
    ),
    (
        re.compile(r"^end time (\d\d:\d\d) is before the first period$"),
        "time_outside_grid",
        lambda m: f"Bitiş {m[1]}, ilk ders saatinden önce",
    ),
    (
        re.compile(r"^end time (\d\d:\d\d) is not after start (\d\d:\d\d)$"),
        "time_unreadable",
        lambda m: f"Bitiş {m[1]}, başlangıçtan ({m[2]}) sonra değil",
    ),
    (re.compile(r"^missing start or end time$"), "time_unreadable", lambda m: "Başlangıç ya da bitiş saati yok"),
    (
        re.compile(r"^unparseable start time (.+)$"),
        "time_unreadable",
        lambda m: f"Başlangıç saati okunamadı ({_q(m[1])})",
    ),
    (re.compile(r"^unrecognised day: (.+)$"), "day_unreadable", lambda m: f"Gün anlaşılamadı ({_q(m[1])})"),
    (
        re.compile(r"^day cell contains a time value: (.+)$"),
        "day_unreadable",
        lambda m: f"Gün hücresinde saat var ({_q(m[1])})",
    ),
    (re.compile(r"^unparseable exam date (.+)$"), "exam_date", lambda m: f"Sınav tarihi okunamadı ({_q(m[1])})"),
    (
        re.compile(r"^exam date range (\S+)\.\.(\S+); using first day$"),
        "exam_date",
        lambda m: f"Sınav tarihi aralığı {m[1]}–{m[2]}; ilk gün alındı",
    ),
    (
        re.compile(r"^rooms tagged PC because a row calls them a computer lab: (.+)$"),
        "room_tagged_pc",
        lambda m: f"Bir satır bilgisayar laboratuvarı dediği için PC etiketi eklenen derslikler: {m[1]}",
    ),
    (
        re.compile(r"^room (\S+): (.+) says (\w+) (\S+), room master keeps (\S+)$"),
        "room_master_kept",
        lambda m: f"{m[1]}: dosya {m[3]} {m[4]} diyor; derslik listesindeki {m[5]} korundu",
    ),
    (
        re.compile(r"^line (\d+): duplicate room (\S+); last one wins$"),
        "room_duplicate",
        lambda m: f"{m[1]}. satır: {m[2]} iki kez var; sonuncusu alındı",
    ),
    (
        re.compile(r"^(\d+) room\(s\) in the master still have no capacity: (.+)$"),
        "room_no_capacity",
        lambda m: f"Derslik listesinde {m[1]} dersliğin kapasitesi yok: {m[2]}",
    ),
    (
        re.compile(r"^definitive place (.+) is not a classroom \((.+)\): no room needed$"),
        "no_room_needed",
        lambda m: f"Kesin yer “{_q(m[1])}” bir derslik değil; derslik gerekmez",
    ),
    (
        re.compile(r"^course code (.+) has no number; placeholder (\S+) derived from name (.+)$"),
        "course_code_placeholder",
        lambda m: f"“{_q(m[1])}” ders kodunda numara yok; “{_q(m[3])}” adından {m[2]} kodu üretildi",
    ),
    (
        re.compile(r"^course code (.+) repaired to (\S+)$"),
        "course_code_repaired",
        lambda m: f"“{_q(m[1])}” ders kodu {m[2]} olarak düzeltildi",
    ),
    (
        re.compile(r"^unparseable enrolment (.+)$"),
        "enrolment_ignored",
        lambda m: f"Öğrenci sayısı okunamadı ({_q(m[1])})",
    ),
    (
        re.compile(r"^enrolment (.+) is a time value \(shifted row\?\); ignored$"),
        "enrolment_ignored",
        lambda m: f"Öğrenci sayısı bir saat değeri ({_q(m[1])}); satır kaymış olabilir, kullanılmadı",
    ),
    (
        re.compile(r"^enrolment (.+) is negative; ignored$"),
        "enrolment_ignored",
        lambda m: f"Öğrenci sayısı eksi ({_q(m[1])}); kullanılmadı",
    ),
    (
        re.compile(r"^enrolment (.+) is out of range \(0-(\d+)\); ignored$"),
        "enrolment_ignored",
        lambda m: f"Öğrenci sayısı {_q(m[1])} 0–{m[2]} aralığının dışında; kullanılmadı",
    ),
    (
        re.compile(r"^unrecognised course code (.+)$"),
        "course_code_unreadable",
        lambda m: f"Ders kodu anlaşılamadı ({_q(m[1])})",
    ),
]

_ROW = re.compile(r"^row (\d+):\s*(.*)$", re.S)


@dataclass(frozen=True)
class WarningText:
    row: int | None
    code: str
    message_tr: str
    message_en: str


def classify(raw: str) -> WarningText:
    """One stored warning ("row 11: weeks value 0; assuming all") as a code and its two sentences."""
    text = str(raw).strip()
    row: int | None = None
    m = _ROW.match(text)
    if m:
        row, text = int(m[1]), m[2].strip()
    for rx, code, tr in _RULES:
        hit = rx.match(text)
        if hit:
            return WarningText(row, code, tr(hit), text)
    return WarningText(row, "other", text, text)


def warning_items(warnings: Iterable[str]) -> list[dict[str, Any]]:
    return [
        {"row": w.row, "code": w.code, "message_tr": w.message_tr, "message_en": w.message_en}
        for w in map(classify, warnings)
    ]


def warning_groups(warnings: Iterable[str], *, variants: int = 5, rows: int = 12) -> list[dict[str, Any]]:
    """Warnings grouped by code, the biggest group first; each group lists its most frequent sentences with the row
    numbers they came from (the first ``rows`` of each)."""
    by_code: OrderedDict[str, list[WarningText]] = OrderedDict()
    for w in map(classify, warnings):
        by_code.setdefault(w.code, []).append(w)
    out: list[dict[str, Any]] = []
    for code, items in by_code.items():
        counts = Counter(w.message_tr for w in items)
        first_en = {w.message_tr: w.message_en for w in reversed(items)}
        texts = []
        for message_tr, n in counts.most_common(variants):
            at = [w.row for w in items if w.message_tr == message_tr and w.row is not None]
            texts.append({"message_tr": message_tr, "message_en": first_en[message_tr], "count": n, "rows": at[:rows]})
        label_tr, label_en = CODE_LABELS.get(code, CODE_LABELS["other"])
        out.append(
            {
                "code": code,
                "label_tr": label_tr,
                "label_en": label_en,
                "count": len(items),
                "variants": len(counts),
                "items": texts,
            }
        )
    out.sort(key=lambda g: (g["code"] == "other", -g["count"]))
    return out
