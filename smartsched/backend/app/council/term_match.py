"""Existing term of a planner group (FIX-A, orchestrator decision 2026-10-18).

The planner names a group from its files ("2026-2027-GUZ" for the Güz 2026/2027 workbooks); the database may already
hold that term under another key ("2026-GUZ", name "Güz 2026-27"). Before a term is created, the group is matched
against the existing terms:

* the same code wins;
* else a term whose code or name carries the same season in any language the planner reads (Güz / GUZ / Fall /
  Autumn ...; Turkish letters folded) **and** the same calendar year (the academic year written either way:
  "2026-2027", "2026/27", "2026") or, when both sides have dates, an overlapping date range. A date range that
  does not overlap rules a term out even when its year matches;
* exactly one such term: the group uses it; two or more: the review asks (the plan item is blocking and lists the
  candidates); none: the commit creates the planner's term as before.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.council import text as tx
from app.models import Term

#: season -> the term kinds a group of that season may land in
_KINDS = {
    "SPRING": {"REGULAR"},
    "FALL": {"REGULAR"},
    "SUMMER": {"SUMMER", "REGULAR"},
    "FINAL": {"FINAL"},
    "BUT": {"BUT"},
}
_EXTRA_WORDS = {"butunleme": "BUT", "but": "BUT", "guz": "FALL", "bahar": "SPRING"}


def term_season(*texts: str | None) -> str | None:
    """The season a term's code or name names ("2026-GUZ", "Güz 2026-27", "Fall 2026" -> ``FALL``)."""
    from app.council.planner import SEASONS

    words = [w for t in texts for w in tx.fold(str(t or "")).replace("_", " ").replace("-", " ").split()]
    found = [SEASONS.get(w, (None, ""))[0] or _EXTRA_WORDS.get(w) for w in words]
    seasons = [s for s in found if s]
    for s in seasons:
        if s in ("FINAL", "BUT"):  # an exam word wins, as in the planner
            return s
    return seasons[0] if seasons else None


def calendar_year(season: str | None, *texts: str | None) -> int | None:
    """The calendar year a term starts in: the first year written, but the second of a two-year spring
    ("2025-2026 Bahar" -> 2026)."""
    for t in texts:
        years = tx.years_in(str(t or ""))
        if years:
            return years[1] if season == "SPRING" and len(years) >= 2 else years[0]
    return None


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _overlap(a: tuple[date | None, date | None], b: tuple[date | None, date | None]) -> bool | None:
    """True / False when both ranges are known (an open end counts as the start), ``None`` otherwise."""
    if a[0] is None or b[0] is None:
        return None
    a_end, b_end = a[1] or a[0], b[1] or b[0]
    return a[0] <= b_end and b[0] <= a_end


def matches(group: dict[str, Any], term: Term) -> bool:
    key_season = str(group.get("key") or "").split(":", 1)[0]
    season = term_season(group.get("code"), group.get("name")) or (key_season if key_season in _KINDS else None)
    if season is None or term_season(term.code, term.name) != season:
        return False
    if (term.kind or "REGULAR").upper() not in _KINDS.get(season, {"REGULAR"}):
        return False
    overlap = _overlap((_date(group.get("start_date")), _date(group.get("end_date"))), (term.start_date, term.end_date))
    if overlap is False:
        return False
    if overlap is True:
        return True
    want = group.get("year") or calendar_year(season, group.get("code"), group.get("name"))
    have = calendar_year(season, term.code, term.name)
    return want is not None and have is not None and int(want) == int(have)


async def candidates(session: AsyncSession, group: dict[str, Any]) -> list[Term]:
    """The existing terms ``group`` may be: ``[the term]`` of the same code, else every term :func:`matches`."""
    code = str(group.get("code") or "").strip()
    if code:
        same = (await session.execute(select(Term).where(Term.code == code))).scalar_one_or_none()
        if same is not None:
            return [same]
    terms = (await session.execute(select(Term).order_by(Term.id))).scalars().all()
    return [t for t in terms if matches(group, t)]


async def resolve_groups(session: AsyncSession, plan: dict[str, Any]) -> None:
    """Point each planner group at its existing term (in place): one candidate -> the group takes that term's code
    (the planner's own code is kept as ``proposed_code``); several -> ``term_candidates`` for the review."""
    for g in plan.get("groups", []):
        g.pop("term_candidates", None)
        found = await candidates(session, g)
        if len(found) == 1:
            t = found[0]
            if t.code != g.get("code"):
                g["proposed_code"] = g.get("code")
                g["code"] = t.code
                g.setdefault("evidence", []).append(f"matched the existing term {t.code} ({t.name})")
            g["term_id"] = t.id
        elif len(found) > 1:
            g.pop("term_id", None)
            g["term_candidates"] = [{"id": t.id, "code": t.code, "name": t.name} for t in found]


__all__ = ["calendar_year", "candidates", "matches", "resolve_groups", "term_season"]
