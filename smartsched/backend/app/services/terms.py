"""The one "current term" rule (usability: the app opened on the last *imported* term, 2026-FINAL).

Order: the term an admin marked active; else the term whose dates contain today (its ``end_date`` or
``start_date + week_count`` weeks; the latest-starting one when terms overlap); else the next term to
start; else the most recently started one; else the newest row.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Term

TZ = ZoneInfo("Europe/Istanbul")


def today() -> date:
    return datetime.now(TZ).date()


def term_end(t: Term) -> date | None:
    if t.end_date:
        return t.end_date
    if t.start_date:
        return t.start_date + timedelta(weeks=int(t.week_count or 14), days=-1)
    return None


def current_term(terms: Sequence[Term], on: date | None = None) -> Term | None:
    if not terms:
        return None
    on = on or today()
    active = [t for t in terms if t.is_active]
    if active:
        return max(active, key=lambda t: t.id)
    dated = [t for t in terms if t.start_date]
    containing = [t for t in dated if t.start_date <= on <= (term_end(t) or t.start_date)]  # type: ignore[operator]
    if containing:
        return max(containing, key=lambda t: (t.start_date, t.id))
    upcoming = [t for t in dated if t.start_date > on]  # type: ignore[operator]
    if upcoming:
        return min(upcoming, key=lambda t: (t.start_date, t.id))
    if dated:
        return max(dated, key=lambda t: (t.start_date, t.id))
    return max(terms, key=lambda t: t.id)


async def load_current_term(session: AsyncSession, on: date | None = None) -> Term | None:
    return current_term(list((await session.execute(select(Term))).scalars()), on)
