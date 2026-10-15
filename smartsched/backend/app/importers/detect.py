"""Which of the university's files is this? (admin persona 2026-10-15, M-20)

A planning list, an exam list, a weekly room timetable or the room master uploaded into the wrong slot used to
fail with ``planning list is missing columns: [...]; headers=[...]``. :class:`WrongFileError` says what was
expected and what the headers look like, in Turkish and English, and carries ``detected`` so the import screen
can offer "import it as ...". Header signatures only - nothing is imported from the file.
"""

from __future__ import annotations

import re
from typing import Any

from app.importers import normalize as n

LABELS: dict[str, tuple[str, str, str]] = {
    # kind: (Turkish, English with article, English bare)
    "planning-list": ("planlama listesi", "a planning list", "planning list"),
    "exam-list": ("sınav listesi", "an exam list", "exam list"),
    "weekly-grid": ("haftalık derslik takvimi", "a weekly room timetable", "weekly room timetable"),
    "room-master": ("derslik ana listesi", "the room master", "room master"),
}
#: the columns an importer could not find, as the planner's workbook names them
COLUMN_LABELS: dict[str, tuple[str, str]] = {
    "code": ("Ders Kodu", "course code"),
    "day": ("Gün", "day"),
    "start": ("Başlangıç Saati", "start time"),
    "end": ("Bitiş Saati", "end time"),
    "date": ("Sınav Tarihi", "exam date"),
}
_GRID_DAY_RX = re.compile(r"^(?:\d{1,2}\s+[a-z]+\s+)?(pazartesi|sali|carsamba|persembe|cuma|cumartesi|pazar)$")


def detect_kind(headers: list[Any]) -> str | None:
    """The kind a header row looks like, or None. Order matters: an exam list also has a course code."""
    from app.importers import exam_list, planning_list
    from app.importers.xlsx import map_headers

    hs = [h if h is None else str(h) for h in headers]
    folded = [n.fold(h) for h in hs if h]
    if sum(1 for f in folded if _GRID_DAY_RX.match(f)) >= 1 and "ders kodu" not in folded:
        return "weekly-grid"  # day names (or "1 Haziran Pazartesi") across the top, no list columns
    if {"code", "capacity"} <= set(folded) or {"kod", "kapasite"} <= set(folded):
        return "room-master"
    exam = map_headers(hs, exam_list.HEADER_SPEC)
    if all(k in exam for k in ("code", "date", "start")):
        return "exam-list"
    plan = map_headers(hs, planning_list.HEADER_SPEC)
    if all(k in plan for k in ("code", "day", "start")):
        return "planning-list"
    return None


class WrongFileError(ValueError):
    """The file is not the kind the import slot expects."""

    def __init__(self, expected: str, detected: str | None, missing: list[str], message_tr: str, message_en: str):
        self.expected, self.detected, self.missing = expected, detected, missing
        self.message_tr, self.message_en = message_tr, message_en
        super().__init__(f"{message_tr} / {message_en}")

    def __reduce__(self) -> tuple[Any, ...]:
        # the list parsers run in an isolated child process (safe_files.run_isolated): the error must cross it
        return (type(self), (self.expected, self.detected, self.missing, self.message_tr, self.message_en))

    @classmethod
    def build(cls, expected: str, headers: list[Any], missing: list[str]) -> WrongFileError:
        detected = detect_kind(headers)
        exp_tr, exp_en, _ = LABELS[expected]
        if detected and detected != expected:
            det_tr, det_en, det_bare = LABELS[detected]
            return cls(
                expected,
                detected,
                missing,
                f"Bu dosya bir {det_tr} gibi görünüyor; {exp_tr} bekleniyordu. Dosyayı '{det_tr}' olarak içe aktarın.",
                f"This file looks like {det_en}; {exp_en} was expected. Import it as {det_bare}.",
            )
        cols_tr = ", ".join(COLUMN_LABELS.get(m, (m, m))[0] for m in missing)
        cols_en = ", ".join(COLUMN_LABELS.get(m, (m, m))[1] for m in missing)
        return cls(
            expected,
            None,
            missing,
            f"Bu dosya bir {exp_tr} gibi görünmüyor: {cols_tr} sütunları bulunamadı.",
            f"This file does not look like {exp_en}: no {cols_en} column.",
        )


__all__ = ["COLUMN_LABELS", "LABELS", "WrongFileError", "detect_kind"]
