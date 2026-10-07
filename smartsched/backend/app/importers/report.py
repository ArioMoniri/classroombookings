"""Typed import report returned by every importer."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SkippedRow:
    row: int
    reason: str
    detail: str | None = None


@dataclass
class ImportReport:
    kind: str
    filename: str | None = None
    term_code: str | None = None
    rows_total: int = 0
    rows_imported: int = 0
    rows_skipped: list[SkippedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created: Counter[str] = field(default_factory=Counter)
    updated: Counter[str] = field(default_factory=Counter)
    extra: dict[str, Any] = field(default_factory=dict)

    def skip(self, row: int, reason: str, detail: str | None = None) -> None:
        self.rows_skipped.append(SkippedRow(row, reason, detail))

    def warn(self, message: str, row: int | None = None) -> None:
        self.warnings.append(f"row {row}: {message}" if row is not None else message)

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
        d["warnings_count"] = len(self.warnings)
        d["warnings"] = self.warnings[:500]
        d["rows_skipped"] = d["rows_skipped"][:500]
        d["warning_summary"] = [{"text": t, "count": c} for t, c in self.warning_summary()]
        return d
