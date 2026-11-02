"""Typed import report returned by every importer."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from app.importers.warning_text import warning_groups, warning_items

#: how many warning texts a job summary lists (the count is always complete)
WARNINGS_LISTED = 500


#: skip reasons that are not a problem in the file (owner report 2026-11-02 item 5): a row without any course code
#: is a meeting, a UZEM / staj note or an exam without a course (``4.SINIF STAJ PLANLAMA TOPLANTISI``), so it is
#: listed as info; an unreadable code (``c``) stays a warning. Everything else skipped is an error.
SKIP_SEVERITY = {"no course code": "info", "unreadable course code": "warning"}


@dataclass
class SkippedRow:
    row: int
    reason: str
    detail: str | None = None
    severity: str = "error"


@dataclass
class ImportReport:
    kind: str
    filename: str | None = None
    term_code: str | None = None
    rows_total: int = 0
    rows_imported: int = 0
    rows_skipped: list[SkippedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: expected, informational findings (exam times that do not align with the period grid, a grid header that
    #: repeats a room with another number): listed apart so that the warnings are the rows to look at
    info: list[str] = field(default_factory=list)
    created: Counter[str] = field(default_factory=Counter)
    updated: Counter[str] = field(default_factory=Counter)
    extra: dict[str, Any] = field(default_factory=dict)

    def skip(self, row: int, reason: str, detail: str | None = None) -> None:
        self.rows_skipped.append(SkippedRow(row, reason, detail, SKIP_SEVERITY.get(reason, "error")))

    def warn(self, message: str, row: int | None = None) -> None:
        self.warnings.append(f"row {row}: {message}" if row is not None else message)

    def note(self, message: str, row: int | None = None) -> None:
        """An informational finding (not a warning): listed under ``info``."""
        self.info.append(f"row {row}: {message}" if row is not None else message)

    @property
    def rows_skipped_count(self) -> int:
        return len(self.rows_skipped)

    def skip_reasons(self) -> dict[str, int]:
        return dict(Counter(s.reason for s in self.rows_skipped))

    def warning_summary(self, top: int = 15) -> list[tuple[str, int]]:
        """Group warnings by their text after the row prefix."""
        c: Counter[str] = Counter()
        for w in self.warnings:
            text = w.split(": ", 1)[1] if w.startswith("row ") and ": " in w else w
            # collapse numbers so similar warnings group together
            key = "".join("#" if ch.isdigit() else ch for ch in text)
            c[key] += 1
        return c.most_common(top)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created"] = dict(self.created)
        d["updated"] = dict(self.updated)
        d["rows_skipped_count"] = self.rows_skipped_count
        d["skip_reasons"] = self.skip_reasons()
        # M-21: the summary lists the first WARNINGS_LISTED warnings and says how many there are in all, so the
        # import report can say "507 uyarı, ilk 500 gösteriliyor"
        d["warnings_count"] = len(self.warnings)
        d["warnings"] = self.warnings[:WARNINGS_LISTED]
        d["warnings_shown"] = len(d["warnings"])
        d["warnings_truncated"] = d["warnings_count"] > d["warnings_shown"]
        d["rows_skipped"] = d["rows_skipped"][:500]
        d["warning_summary"] = [{"text": t, "count": c} for t, c in self.warning_summary()]
        # PER-F05 (fix-h-2026-10-18): per listed warning a code + Turkish / English sentence, and all warnings
        # grouped by code (the strings above stay for older clients and the job history)
        d["warning_items"] = warning_items(d["warnings"])
        d["warning_groups"] = warning_groups(self.warnings)
        d["info_count"] = len(self.info)
        d["info"] = self.info[:WARNINGS_LISTED]
        d["info_items"] = warning_items(d["info"])
        d["info_groups"] = warning_groups(self.info)
        d["skip_severity"] = dict(Counter(s.severity for s in self.rows_skipped))
        return d
