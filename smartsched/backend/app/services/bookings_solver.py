"""Confirmed bookings as solver blocks (the only booking-related call in ``solver_bridge``).

A booking holds ``room_id`` on one date for grid periods ``start_period..end_period``; for a run of
``term`` it becomes ``Block(room_id, week, weekday, start, end)`` where ``week`` is the term's calendar
week of the date. Bookings outside the run's horizon weeks are skipped. Uses only the frozen
``app.solver.model.Block`` contract."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Term, Week
from app.models.booking import BOOKED
from app.services.calendar import week_index_for_date
from app.solver import model as sm


async def booking_blocks(
    session: AsyncSession, term: Term, weeks: Iterable[Week], week_set: set[int]
) -> list[sm.Block]:
    week_rows = list(weeks)
    out: list[sm.Block] = []
    rows = (await session.execute(select(Booking).where(Booking.status == BOOKED))).scalars()
    for b in rows:
        w = week_index_for_date(term, b.date, week_rows)
        if w is None or w not in week_set:
            continue
        out.append(sm.Block(b.room_id, w, b.date.isoweekday(), b.start_period, b.end_period))
    return out
