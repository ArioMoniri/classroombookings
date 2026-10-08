from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, Planner, Viewer, require_permission
from app.models import Term, User, Week
from app.schemas.catalog import TermIn, TermOut, TermUpdate, WeekIn, WeekOut

router = APIRouter(prefix="/terms", tags=["terms"])
#: CRBS ``Sessions`` controller: creating, editing and deleting sessions needs ``setup.sessions``; the
#: planning office keeps ``planning.edit`` (audit MISSING 6)
SessionsEditor = Annotated[User, Depends(require_permission("planning.edit", "setup.sessions"))]


class TermUpdateOut(TermOut):
    #: bookings cancelled because the new dates no longer contain them (CRBS ``check_session_dates``)
    cancelled_booking_ids: list[int] = []


@router.get("", response_model=list[TermOut])
async def list_terms(db: DB, _: Viewer) -> list[TermOut]:
    """The current term first (``is_current``), then by start date, newest first: a client that opens
    ``terms[0]`` lands on today's term, not the last imported one."""
    from app.services.terms import current_term

    terms = list((await db.execute(select(Term).order_by(Term.id.desc()))).scalars())
    cur = current_term(terms)
    rest = sorted(
        (t for t in terms if t is not cur), key=lambda t: (t.start_date is not None, t.start_date, t.id), reverse=True
    )
    return [
        TermOut.model_validate(t).model_copy(update={"is_current": t is cur}) for t in ([cur] if cur else []) + rest
    ]


@router.get("/current", response_model=TermOut)
async def get_current_term(db: DB, _: Viewer) -> TermOut:
    from app.services.terms import load_current_term

    t = await load_current_term(db)
    if t is None:
        raise HTTPException(404, "no terms yet")
    return TermOut.model_validate(t).model_copy(update={"is_current": True})


@router.post("", response_model=TermOut, status_code=201)
async def create_term(body: TermIn, db: DB, _: SessionsEditor) -> Term:
    if (await db.execute(select(Term).where(Term.code == body.code))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "term code exists")
    data = body.model_dump()
    data["name"] = (data.get("name") or "").strip() or body.code
    if body.is_active:
        # audit B3: deactivate the others *before* the new row exists (autoflush used to include it)
        for other in (await db.execute(select(Term).where(Term.is_active.is_(True)))).scalars():
            other.is_active = False
    term = Term(**data)
    db.add(term)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "term code exists") from exc
    await db.refresh(term)
    return term


async def _get(db: DB, term_id: int) -> Term:
    term = await db.get(Term, term_id)
    if term is None:
        raise HTTPException(404, "term not found")
    return term


@router.get("/{term_id}", response_model=TermOut)
async def get_term(term_id: int, db: DB, _: Viewer) -> Term:
    return await _get(db, term_id)


@router.put("/{term_id}", response_model=TermUpdateOut)
async def update_term(
    term_id: int, body: TermUpdate, db: DB, user: SessionsEditor, confirm: bool = False
) -> TermUpdateOut:
    """When the dates change, active bookings that fall outside the new range are cancelled with a reason
    (CRBS ``Bookings_model::check_session_dates`` deletes them). With ``bookings.term_date_change = confirm``
    the change is refused (409, the list of bookings) until it is sent again with ``?confirm=true``."""
    from app.services import bookings as booking_service
    from app.services.bookings_settings import get_value

    term = await _get(db, term_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(term, k, v)
    if body.is_active:
        for other in (await db.execute(select(Term).where(Term.id != term.id, Term.is_active.is_(True)))).scalars():
            other.is_active = False
    cancelled: list[int] = []
    if {"start_date", "end_date", "week_count"} & set(data):
        await db.flush()
        outside = await booking_service.bookings_outside_term(db, term)
        if outside:
            mode = await get_value(db, "bookings", "term_date_change")
            if mode == "confirm" and not confirm:
                listing = [await booking_service.booking_summary(db, b) for b in outside]
                await db.rollback()
                raise HTTPException(
                    409,
                    {
                        "code": "bookings_outside_term",
                        "message": f"{len(outside)} booking(s) fall outside the new dates; repeat with ?confirm=true "
                        "to cancel them",
                        "bookings": listing,
                    },
                )
            cancelled = await booking_service.cancel_outside_term(db, term, user, outside)
    await db.commit()
    await db.refresh(term)
    return TermUpdateOut.model_validate(term).model_copy(update={"cancelled_booking_ids": cancelled})


class TermUsageOut(BaseModel):
    """What ``DELETE /terms/{id}`` erases with the term (CRBS ``session.delete.warning``: its bookings go too)."""

    term_id: int
    bookings: int
    active_bookings: int
    series: int
    holidays: int
    runs: int
    #: SmartSched planning data that goes too (course sections of the term)
    sections: int


@router.get("/{term_id}/usage", response_model=TermUsageOut)
async def term_usage(term_id: int, db: DB, _: SessionsEditor) -> TermUsageOut:
    """Counts for the delete confirmation in Admin -> Sessions (UI gap audit 2026-10-08 #3)."""
    from app.models import Booking, BookingSeries, Holiday, ScheduleRun, Section

    await _get(db, term_id)

    async def count(model: Any, *where: ColumnElement[bool]) -> int:
        q = select(func.count()).select_from(model).where(model.term_id == term_id, *where)
        return int((await db.execute(q)).scalar_one())

    return TermUsageOut(
        term_id=term_id,
        bookings=await count(Booking),
        active_bookings=await count(Booking, Booking.status == "BOOKED"),
        series=await count(BookingSeries),
        holidays=await count(Holiday),
        runs=await count(ScheduleRun),
        sections=await count(Section),
    )


@router.delete("/{term_id}", status_code=204)
async def delete_term(term_id: int, db: DB, _: SessionsEditor) -> None:
    term = await _get(db, term_id)
    await db.delete(term)
    await db.commit()


@router.get("/{term_id}/weeks", response_model=list[WeekOut])
async def list_weeks(term_id: int, db: DB, _: Viewer) -> list[Week]:
    await _get(db, term_id)
    return list((await db.execute(select(Week).where(Week.term_id == term_id).order_by(Week.index))).scalars())


@router.put("/{term_id}/weeks", response_model=list[WeekOut])
async def replace_weeks(term_id: int, body: list[WeekIn], db: DB, _: Planner) -> list[Week]:
    term = await _get(db, term_id)
    existing = {w.index: w for w in (await db.execute(select(Week).where(Week.term_id == term_id))).scalars()}
    seen = set()
    for w in body:
        seen.add(w.index)
        row = existing.get(w.index)
        if row is None:
            db.add(Week(term_id=term_id, **w.model_dump()))
        else:
            for k, v in w.model_dump().items():
                setattr(row, k, v)
    for idx, row in existing.items():
        if idx not in seen:
            await db.delete(row)
    if body:
        term.week_count = (
            max(w.index for w in body if w.kind != "EXAM") if any(w.kind != "EXAM" for w in body) else term.week_count
        )
    await db.commit()
    return list((await db.execute(select(Week).where(Week.term_id == term_id).order_by(Week.index))).scalars())
