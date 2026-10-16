"""V2 public read-only schedules (docs/product/booking-enhancements.md §V2; service:
:mod:`app.services.public_schedule`).

No sign-in:

* ``GET /public/schedule`` -- buildings and rooms;
* ``GET /public/schedule/rooms/{code}?date=`` -- one room's day (``A101``, ``a 101``; date ``YYYY-MM-DD`` or
  ``GG.AA.YYYY``, default today);
* ``GET /public/schedule/buildings/{code}?date=`` -- every room of a building that day.

Each answers 404 ``not found`` when the view is off, the room / building is unknown or the date is outside the window
(the same body), and 429 with ``Retry-After`` above the per-address limit.

Administration (``setup.settings``): ``GET/PUT /public-schedule/admin/settings`` ``{enabled, show_bookings}``; switching
it on records the KVKK sign-off (audited ``public_schedule.settings``).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.api.deps import DB, require_permission
from app.core import throttle
from app.models import User
from app.services import bookings as bsvc
from app.services import public_schedule as svc

router = APIRouter(prefix="/public/schedule", tags=["public"])
admin_router = APIRouter(prefix="/public-schedule/admin", tags=["public"])
SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]


class PublicSettingsIn(BaseModel):
    enabled: bool | None = None
    show_bookings: str | None = None


def _not_found() -> HTTPException:
    return HTTPException(404, "not found")


def _limit(request: Request) -> None:
    address = request.client.host if request.client else "?"
    key = f"ip:{address}"
    if throttle.PUBLIC_PER_ADDRESS.hit(key):
        raise HTTPException(
            429, "too many requests", headers={"Retry-After": str(throttle.PUBLIC_PER_ADDRESS.retry_after(key) or 1)}
        )


async def _day(db: DB, value: str | None) -> date:
    if not value:
        return await bsvc.today(db)
    text = value.strip()
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", text)
    try:
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return date.fromisoformat(text)
    except ValueError as exc:
        raise _not_found() from exc


def _cache(response: Response) -> None:
    response.headers["Cache-Control"] = "public, max-age=60"


@router.get("")
async def public_index(request: Request, response: Response, db: DB) -> dict[str, Any]:
    _limit(request)
    try:
        out = await svc.index(db)
    except svc.NotFound as exc:
        raise _not_found() from exc
    _cache(response)
    return out


@router.get("/rooms/{code}")
async def public_room(
    code: str, request: Request, response: Response, db: DB, day: Annotated[str | None, Query(alias="date")] = None
) -> dict[str, Any]:
    _limit(request)
    d = await _day(db, day)
    try:
        out = await svc.room_day(db, code, d)
    except svc.NotFound as exc:
        raise _not_found() from exc
    _cache(response)
    return out


@router.get("/buildings/{code}")
async def public_building(
    code: str, request: Request, response: Response, db: DB, day: Annotated[str | None, Query(alias="date")] = None
) -> dict[str, Any]:
    _limit(request)
    d = await _day(db, day)
    try:
        out = await svc.building_day(db, code, d)
    except svc.NotFound as exc:
        raise _not_found() from exc
    _cache(response)
    return out


@admin_router.get("/settings")
async def get_public_settings(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    return await svc.settings(db)


@admin_router.put("/settings")
async def put_public_settings(body: PublicSettingsIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    try:
        out = await svc.update_settings(db, admin, body.model_dump())
    except ValueError as exc:
        raise HTTPException(
            422, {"code": "show_bookings", "message": str(exc), "message_tr": "show_bookings: busy ya da hidden"}
        ) from exc
    await db.commit()
    return out
