"""PER-F04 (fix-h-2026-10-18): which term an uploaded workbook belongs to, read on the server during the preview.

The importer writes into the target term the person picked (the current term by default). A Bahar workbook previewed
onto Güz would change 1,900 Güz rows on one "Uygula". The preview now says what the file itself names: the season and
year in its file name, else in its sheet titles (``Bahar 2026``, ``GÜZ 2026-2027``), matched with the council's term
matcher (Güz / GUZ / Fall ..., Turkish letters folded). The summary carries ``term_check`` (and
``suggested_term_id`` at the top) so the wizard warns above the counts and keeps "Uygula" waiting for a confirm.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.council.term_match import calendar_year, term_season
from app.models import Term


def _sheet_titles(src: Path | bytes, filename: str | None = None) -> list[str]:
    """The sheet titles of a workbook on disk or in memory (HB-23b: the helper file router never writes a plain
    file, so it passes the bytes; their type comes from ``filename``)."""
    suffix = src.suffix if isinstance(src, Path) else Path(filename or "").suffix
    if suffix.lower() not in {".xlsx", ".xlsm"}:
        return []
    try:
        from app.core.safe_files import open_workbook

        wb = open_workbook(src, read_only=True, data_only=True, max_cols=1)
    except Exception:  # a file the importer itself refuses says so in its own report
        return []
    try:
        return [str(ws.title) for ws in wb.worksheets]
    finally:
        wb.close()


def file_term(filename: str | None, path: Path | bytes | None) -> tuple[str | None, int | None, str | None]:
    """(season, calendar year, source) the file names: ``source`` is ``file_name`` or ``sheet_title``. ``path`` may
    be the file's bytes (the workbook is opened in memory, read-only, after the same zip pre-inspection)."""
    stem = Path(filename or "").stem
    season = term_season(stem)
    if season:
        return season, calendar_year(season, stem), "file_name"
    for title in _sheet_titles(path, filename) if path is not None else []:
        season = term_season(title)
        if season:
            return season, calendar_year(season, title, stem), "sheet_title"
    return None, None, None


async def term_check(
    session: AsyncSession, *, term_code: str | None, filename: str | None, path: Path | None
) -> dict[str, Any]:
    """``{"term_check": {...}, "suggested_term_id": id | None}``; empty when there is no target term."""
    if not term_code:
        return {}
    target = (await session.execute(select(Term).where(Term.code == term_code))).scalar_one_or_none()
    if target is None:
        return {}
    season, year, source = file_term(filename, path)
    want = term_season(target.code, target.name)
    want_year = calendar_year(want, target.code, target.name)
    mismatch = bool(
        season and want and (season != want or (year is not None and want_year is not None and year != want_year))
    )
    suggested: Term | None = None
    if mismatch:
        terms = (
            (await session.execute(select(Term).order_by(Term.start_date.desc().nulls_last(), Term.id.desc())))
            .scalars()
            .all()
        )
        same = [t for t in terms if term_season(t.code, t.name) == season]
        exact = [t for t in same if year is None or calendar_year(season, t.code, t.name) == year]
        pick = exact or same
        suggested = pick[0] if pick else None
    check = {
        "target_id": target.id,
        "target_name": target.name,
        "file_season": season,
        "file_year": year,
        "source": source,
        "mismatch": mismatch,
        "suggested_term_id": suggested.id if suggested else None,
        "suggested_term_name": suggested.name if suggested else None,
    }
    return {"term_check": check, "suggested_term_id": check["suggested_term_id"]}
