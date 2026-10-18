"""P8 booking policies and exam-period mode (docs/product/booking-enhancements.md §P8; service:
:mod:`app.services.booking_policies`).

* ``GET /booking-policies`` -- every rule plus the exam-period setting (``setup.settings``);
* ``POST /booking-policies``, ``PUT /booking-policies/{id}``, ``DELETE /booking-policies/{id}`` (``setup.settings``,
  audited ``booking_policy.create|update|delete``);
* ``PUT /booking-policies/exam-period`` -- ``{mode: off|request|closed|slots, from_exam_timetable, room_ids,
  buffer_periods, slots_effect}``
  (``setup.settings``, audited ``booking_policy.exam_period``);
* ``GET /booking-policies/effective?room_id=&date=&period_id=`` -- any signed-in user: the rules that bind the caller
  in that room and, for a slot, the verdict ``book | request | refuse`` with the reasons ("Neden?").
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, CurrentAccess, require_permission
from app.models import BookingPeriod, User
from app.models.base import utcnow
from app.models.catalog import Room
from app.models.policies import BookingPolicy
from app.services import audit
from app.services import booking_policies as svc
from app.services.bookings_calendar import CalendarError, resolve_term

router = APIRouter(prefix="/booking-policies", tags=["booking-policies"])
SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]


class QuietWindow(BaseModel):
    weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])
    start: str
    end: str


class Blackout(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from")
    to: str | None = None
    label: str | None = None


class PolicyIn(BaseModel):
    name: str
    enabled: bool = True
    term_id: int | None = None
    scope_type: str = "all"
    scope_id: int | None = None
    tag: str | None = None
    role_codes: list[str] = Field(default_factory=list)
    effect: str = "refuse"
    min_notice_workdays: int | None = None
    max_advance_days: int | None = None
    max_duration_minutes: int | None = None
    max_active_bookings: int | None = None
    buffer_minutes: int | None = None
    quiet_hours: list[QuietWindow] = Field(default_factory=list)
    blackouts: list[Blackout] = Field(default_factory=list)
    note: str | None = None


class ExamPeriodIn(BaseModel):
    mode: str | None = None
    from_exam_timetable: bool | None = None
    room_ids: list[int] | None = None
    #: AS-04 ``slots``: periods held before and after each exam (0..4) and what a held slot does
    buffer_periods: int | None = None
    slots_effect: str | None = None


def _err(exc: svc.PolicyError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


def _payload(body: PolicyIn) -> dict[str, Any]:
    data = body.model_dump()
    data["blackouts"] = [b.model_dump(by_alias=True) for b in body.blackouts]
    return data


async def _get(db: DB, policy_id: int) -> BookingPolicy:
    p = await db.get(BookingPolicy, policy_id)
    if p is None:
        raise HTTPException(404, {"code": "not_found", "message": "policy not found", "message_tr": "kural bulunamadı"})
    return p


@router.get("")
async def list_policies(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    rows = (await db.execute(select(BookingPolicy).order_by(BookingPolicy.id))).scalars()
    return {"policies": [svc.policy_out(p) for p in rows], "exam_period": await svc.exam_settings(db)}


@router.post("", status_code=201)
async def create_policy(body: PolicyIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    try:
        values = await svc.validate(db, _payload(body))
    except svc.PolicyError as exc:
        raise _err(exc) from exc
    p = BookingPolicy(**values, created_by=admin.id, created_at=utcnow())
    db.add(p)
    await db.flush()
    await audit.record(db, "booking_policy.create", "booking_policy", p.id, after=svc.policy_out(p), actor=admin)
    await db.commit()
    await db.refresh(p)
    return svc.policy_out(p)


@router.put("/exam-period")
async def put_exam_period(body: ExamPeriodIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    before = await svc.exam_settings(db)
    try:
        after = await svc.set_exam_settings(db, body.model_dump(exclude_none=True))
    except svc.PolicyError as exc:
        raise _err(exc) from exc
    await audit.record(
        db, "booking_policy.exam_period", "setting", "policies.exam_period", before=before, after=after, actor=admin
    )
    await db.commit()
    return after


@router.put("/{policy_id}")
async def update_policy(policy_id: int, body: PolicyIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    p = await _get(db, policy_id)
    before = svc.policy_out(p)
    try:
        values = await svc.validate(db, _payload(body))
    except svc.PolicyError as exc:
        raise _err(exc) from exc
    for k, v in values.items():
        setattr(p, k, v)
    p.updated_by, p.updated_at = admin.id, utcnow()
    await db.flush()
    await audit.record(
        db, "booking_policy.update", "booking_policy", p.id, before=before, after=svc.policy_out(p), actor=admin
    )
    await db.commit()
    await db.refresh(p)
    return svc.policy_out(p)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(policy_id: int, db: DB, admin: SettingsAdmin) -> None:
    p = await _get(db, policy_id)
    before = svc.policy_out(p)
    await db.delete(p)
    await audit.record(db, "booking_policy.delete", "booking_policy", policy_id, before=before, actor=admin)
    await db.commit()


@router.get("/effective")
async def effective(
    db: DB,
    access: CurrentAccess,
    room_id: int,
    day: Annotated[date | None, Query(alias="date")] = None,
    period_id: int | None = None,
    term_id: int | None = None,
) -> dict[str, Any]:
    room = await db.get(Room, room_id)
    if room is None or not access.can_view_room(room):
        raise HTTPException(
            404, {"code": "room_not_found", "message": "room not found", "message_tr": "oda bulunamadı"}
        )
    period = await db.get(BookingPeriod, period_id) if period_id is not None else None
    if period_id is not None and period is None:
        raise HTTPException(
            422, {"code": "period", "message": "period not found", "message_tr": "ders saati bulunamadı"}
        )
    tid = term_id
    if day is not None:
        try:
            info = await resolve_term(db, day, term_id, view_all=True)
        except CalendarError as exc:
            raise HTTPException(
                409, {"code": "calendar", "message": str(exc), "message_tr": "bu tarih için dönem yok"}
            ) from exc
        tid = info.term.id
    if tid is None:
        raise HTTPException(
            422, {"code": "term", "message": "give a date or a term", "message_tr": "tarih ya da dönem gerekli"}
        )
    return await svc.effective(db, access, room, tid, day, period)
