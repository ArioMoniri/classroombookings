"""Holidays of a term (CRBS ``Holidays``, guarded by ``setup.sessions``). No bookings on holidays;
recurring instances skip them."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, require_permission
from app.models import Holiday, Term, User
from app.schemas.crbs import HolidayIn, HolidayOut, HolidayUpdate
from app.services.bookings_calendar import term_info

router = APIRouter(prefix="/holidays", tags=["holidays"])
SessionsAdmin = Annotated[User, Depends(require_permission("setup.sessions"))]


async def _check_range(db: DB, term_id: int, start: date, end: date) -> None:
    term = await db.get(Term, term_id)
    if term is None:
        raise HTTPException(404, "term not found")
    info = await term_info(db, term)
    if info is None:
        raise HTTPException(409, f"term {term.code} has no dates")
    if end < start:
        raise HTTPException(422, "date_end is before date_start")
    if start < info.start or end > info.end:
        raise HTTPException(422, f"holiday must be within the term ({info.start:%d.%m.%Y} - {info.end:%d.%m.%Y})")


@router.get("", response_model=list[HolidayOut])
async def list_holidays(db: DB, _: CurrentUser, term_id: int | None = None) -> list[Holiday]:
    q = select(Holiday).order_by(Holiday.date_start)
    if term_id is not None:
        q = q.where(Holiday.term_id == term_id)
    return list((await db.execute(q)).scalars())


@router.post("", response_model=HolidayOut, status_code=201)
async def create_holiday(body: HolidayIn, db: DB, _: SessionsAdmin) -> Holiday:
    await _check_range(db, body.term_id, body.date_start, body.date_end)
    h = Holiday(**body.model_dump())
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return h


@router.put("/{holiday_id}", response_model=HolidayOut)
async def update_holiday(holiday_id: int, body: HolidayUpdate, db: DB, _: SessionsAdmin) -> Holiday:
    h = await db.get(Holiday, holiday_id)
    if h is None:
        raise HTTPException(404, "holiday not found")
    data = body.model_dump(exclude_unset=True)
    start, end = data.get("date_start", h.date_start), data.get("date_end", h.date_end)
    await _check_range(db, h.term_id, start, end)
    for k, v in data.items():
        if v is not None:
            setattr(h, k, v)
    await db.commit()
    await db.refresh(h)
    return h


@router.delete("/{holiday_id}", status_code=204)
async def delete_holiday(holiday_id: int, db: DB, _: SessionsAdmin) -> None:
    h = await db.get(Holiday, holiday_id)
    if h is None:
        raise HTTPException(404, "holiday not found")
    await db.delete(h)
    await db.commit()
