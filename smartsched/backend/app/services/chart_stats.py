"""Read-only chart aggregates CH-07, CH-10, CH-11 (docs/design/v3/charts.md "CH-07 … CH-11 notes"; the frontend
parses exactly these shapes in ``smartsched/frontend/src/lib/api/stats.ts``). Nothing here writes, so the routes
have no audit rows; every query runs in the caller's request session, so PostgreSQL row-level security applies.

* :func:`weekly_bookings` (CH-07): one row per term week of the term calendar (``weeks`` rows, else the term's
  weekly arithmetic) with ``exam`` (an EXAM / MAKEUP week, or an active MIDTERM / EXAM / MAKEUP season segment over
  it), ``partial`` (the week holds today, or the term starts / ends inside it; ``start`` / ``end`` are then clipped
  to the term), ``bookings`` (live ``BOOKED`` booking rows dated in the week) and ``requests`` (booking approval
  requests by the Istanbul day they were submitted, current status; expired and withdrawn ones are not counted).
* :func:`daily_audit` (CH-10): audit events per Europe/Istanbul day, every day of the window present (0 for a quiet
  day). ``scope`` is the audit list's own scope condition, so the chart counts what the list shows.
* :func:`my_load` (CH-11): the caller's own instructor record (``Instructor.user_id``) on the term's published
  COURSE run, read through the timetable's own read model (``calendar_views.load_run_context``, imported boards
  matched to their meetings), so each weekday's number is what ``/timetable?subject=instructor:ID`` shows that
  day. ``periods`` are distinct (weekday, period) cells, so a joint lecture listed for several programmes and a
  board row repeated per teaching week count once; ``minutes`` add up those periods' clock lengths on the
  university's period grid.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import ApprovalRequest, AuditEvent, Booking, Instructor, Term, Week
from app.models.booking import BOOKED, PENDING, REJECTED
from app.models.seasons import SeasonSegment
from app.services import seasons
from app.services.terms import term_end

TZ = ZoneInfo("Europe/Istanbul")
APPROVED = "APPROVED"
#: week kinds of the term calendar that are exam weeks ("Sınav haftası" on the chart)
EXAM_WEEK_KINDS = frozenset({"EXAM", "MAKEUP"})
#: admin season segments that make a week an exam week (vize, final, bütünleme)
EXAM_SEGMENT_KINDS = frozenset({"MIDTERM", "EXAM", "MAKEUP"})
DAYS_MAX = 90


class StatsError(Exception):
    """A refused request: HTTP status, code and both sentences."""

    def __init__(self, status: int, code: str, message_tr: str, message_en: str) -> None:
        super().__init__(message_en)
        self.status, self.code, self.message_tr, self.message_en = status, code, message_tr, message_en

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message_tr": self.message_tr, "message_en": self.message_en}


def term_not_found() -> StatsError:
    return StatsError(404, "term_not_found", "Dönem bulunamadı.", "Term not found.")


def utcnow() -> datetime:
    """Aware UTC now (a module function, so tests can fix the clock)."""
    return datetime.now(UTC)


def local_day(ts: datetime) -> date:
    """The Europe/Istanbul day of a stored naive-UTC timestamp."""
    return (ts if ts.tzinfo else ts.replace(tzinfo=UTC)).astimezone(TZ).date()


def day_start_utc(d: date) -> datetime:
    """Naive UTC instant of 00:00 Europe/Istanbul on ``d`` (rows store naive UTC)."""
    return datetime.combine(d, time(), tzinfo=TZ).astimezone(UTC).replace(tzinfo=None)


# ------------------------------------------------------------------------------------------------ CH-07


def _exam_weeks(term: Term, rows: Sequence[Week], segments: Sequence[SeasonSegment]) -> set[int]:
    out = {int(w.index) for w in rows if (w.kind or "").upper() in EXAM_WEEK_KINDS}
    out.update(w for w, k in seasons.segment_kind_by_week(segments).items() if k in EXAM_SEGMENT_KINDS)
    for sg in segments:  # dated segments without week numbers
        if (sg.status or "active") != "active" or (sg.kind or "").upper() not in EXAM_SEGMENT_KINDS:
            continue
        if sg.week_from is None and sg.date_from and sg.date_to:
            d = sg.date_from
            while d <= sg.date_to:
                wk = seasons.week_of_date(term, d, rows)
                if wk is not None:
                    out.add(wk)
                d += timedelta(days=1)
    return out


def term_weeks(term: Term, rows: Sequence[Week]) -> list[tuple[int, date, date, bool]]:
    """(week, start, end, clipped) of every term week: the calendar's week rows, else 1..week_count. ``start`` is
    the week's Monday and ``end`` its Sunday, clipped to the term's first / last day (``clipped`` then)."""
    first = term.start_date
    last = term_end(term)
    numbers = sorted({int(w.index) for w in rows}) or list(range(1, int(term.week_count or 14) + 1))
    out: list[tuple[int, date, date, bool]] = []
    for wk in numbers:
        mon = seasons.week_start(term, wk, rows)
        if mon is None:
            continue
        start, end = mon, mon + timedelta(days=6)
        clipped = False
        if first is not None and start < first <= end:
            start, clipped = first, True
        if last is not None and start <= last < end:
            end, clipped = last, True
        if last is not None and start > last:
            continue  # a week row after the term's last day
        out.append((wk, start, end, clipped))
    return out


async def weekly_bookings(session: AsyncSession, term_id: int, today: date) -> dict[str, Any]:
    term = await session.get(Term, term_id)
    if term is None:
        raise term_not_found()
    rows, _holidays, segments = await seasons.load_calendar(session, term)
    weeks = term_weeks(term, rows)
    exam = _exam_weeks(term, rows, segments)
    lo = min((s for _, s, _, _ in weeks), default=None)
    hi = max((e for _, _, e, _ in weeks), default=None)

    booked: Counter[date] = Counter()
    submitted: dict[date, Counter[str]] = defaultdict(Counter)
    if lo is not None and hi is not None:
        for d in (
            await session.execute(
                select(Booking.date).where(
                    Booking.term_id == term.id, Booking.status == BOOKED, Booking.date >= lo, Booking.date <= hi
                )
            )
        ).scalars():
            booked[d] += 1
        reqs = await session.execute(
            select(ApprovalRequest.requested_at, ApprovalRequest.status).where(
                ApprovalRequest.term_id == term.id,
                ApprovalRequest.status.in_((APPROVED, REJECTED, PENDING)),
                ApprovalRequest.requested_at >= day_start_utc(lo),
                ApprovalRequest.requested_at < day_start_utc(hi + timedelta(days=1)),
            )
        )
        for at, status in reqs.all():
            if at is not None:
                submitted[local_day(at)][str(status)] += 1

    out = []
    for wk, start, end, clipped in weeks:
        span = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        cnt: Counter[str] = Counter()
        for d in span:
            cnt.update(submitted.get(d, Counter()))
        out.append(
            {
                "week": wk,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "exam": wk in exam,
                "partial": clipped or start <= today <= end,
                "bookings": sum(booked[d] for d in span),
                "requests": {"approved": cnt[APPROVED], "rejected": cnt[REJECTED], "pending": cnt[PENDING]},
            }
        )
    first = (lo or term.start_date or today).isoformat()
    return {
        "term_id": term.id,
        "from": first,
        "to": (hi or term_end(term) or today).isoformat(),
        "today": today.isoformat(),
        "weeks": out,
    }


# ------------------------------------------------------------------------------------------------ CH-10


async def daily_audit(session: AsyncSession, days: int, scope: Any = None) -> dict[str, Any]:
    """Audit events per Istanbul day over the last ``days`` days (today included), zero-filled."""
    days = max(1, min(int(days), DAYS_MAX))
    to = utcnow().astimezone(TZ).date()
    frm = to - timedelta(days=days - 1)
    q = select(AuditEvent.ts).where(
        AuditEvent.ts >= day_start_utc(frm), AuditEvent.ts < day_start_utc(to + timedelta(days=1))
    )
    if scope is not None:
        q = q.where(scope)
    cnt: Counter[date] = Counter(local_day(ts) for ts in (await session.execute(q)).scalars() if ts is not None)
    return {
        "from": frm.isoformat(),
        "to": to.isoformat(),
        "days": [
            {"day": (frm + timedelta(days=i)).isoformat(), "events": cnt[frm + timedelta(days=i)]} for i in range(days)
        ],
    }


# ------------------------------------------------------------------------------------------------ CH-11


def _period_minutes() -> dict[int, int]:
    """Clock length in minutes of P1..P18 on the university's current period grid."""
    out = {}
    for i, p in enumerate(n.PERIODS, start=1):
        a = p.start.hour * 60 + p.start.minute
        b = p.end.hour * 60 + p.end.minute
        out[i] = max(0, b - a)
    return out


async def my_load(session: AsyncSession, user_id: int, term_id: int | None, today: date) -> dict[str, Any]:
    from app.services import terms as terms_svc
    from app.services.calendar_views import load_run_context
    from app.services.moderation import published_run

    if term_id is not None:
        term = await session.get(Term, term_id)
        if term is None:
            raise term_not_found()
    else:
        term = await terms_svc.load_current_term(session, today)
    inst = (await session.execute(select(Instructor).where(Instructor.user_id == user_id))).scalars().first()
    out: dict[str, Any] = {
        "linked": inst is not None,
        "instructor_id": inst.id if inst is not None else None,
        "term_id": term.id if term is not None else None,
        "run_id": None,
        "days": [],
        "total_periods": 0,
    }
    if inst is None or term is None:
        return out
    run = await published_run(session, term.id, "COURSE")
    if run is None:
        return out
    ctx = await load_run_context(session, run, with_bookings=False)
    cells: dict[int, set[int]] = defaultdict(set)
    for a in ctx.rows:
        m = ctx.meeting_of(a)
        if m is None or inst.id not in m.instr_ids or not 1 <= int(a.day) <= 7:
            continue
        cells[int(a.day)].update(range(int(a.start_period), int(a.end_period) + 1))
    mins = _period_minutes()
    out["run_id"] = run.id
    out["days"] = [
        {"day": d, "periods": len(cells[d]), "minutes": sum(mins.get(p, 0) for p in cells[d])} for d in range(1, 8)
    ]
    out["total_periods"] = sum(len(v) for v in cells.values())
    return out
