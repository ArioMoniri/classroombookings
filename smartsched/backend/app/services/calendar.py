"""Week/date arithmetic shared by the bridge, grid and exports."""

from __future__ import annotations

from datetime import date, timedelta

from app.importers.normalize import DAY_LABELS_TR, PERIODS
from app.models import Term, Week


def term_monday(term: Term, weeks: list[Week] | None = None) -> date | None:
    if weeks:
        first = min((w for w in weeks if w.start_date), key=lambda w: w.index, default=None)
        if first and first.start_date:
            return first.start_date - timedelta(days=first.start_date.weekday()) - timedelta(weeks=first.index - 1)
    if term.start_date:
        return term.start_date - timedelta(days=term.start_date.weekday())
    return None


def week_index_for_date(term: Term, d: date, weeks: list[Week] | None = None) -> int | None:
    monday = term_monday(term, weeks)
    if monday is None:
        return None
    return (d - monday).days // 7 + 1


def date_for(term: Term, week: int, day: int, weeks: list[Week] | None = None) -> date | None:
    monday = term_monday(term, weeks)
    if monday is None:
        return None
    return monday + timedelta(weeks=week - 1, days=day - 1)


def day_label(day: int) -> str:
    return DAY_LABELS_TR.get(day, str(day))


def period_times(start_period: int, end_period: int) -> tuple[str, str]:
    s = PERIODS[max(start_period, 1) - 1].start
    e = PERIODS[min(end_period, len(PERIODS)) - 1].end
    return f"{s:%H:%M}", f"{e:%H:%M}"
