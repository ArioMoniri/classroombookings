"""V2 public read-only schedules (docs/product/booking-enhancements.md §V2; service:
:mod:`app.services.public_schedule`).

No sign-in:

* ``GET /public/schedule`` -- buildings and rooms;
* ``GET /public/schedule/rooms/{code}?date=`` -- one room's day (``A101``, ``a 101``; date ``YYYY-MM-DD`` or
  ``GG.AA.YYYY``, default today);
* ``GET /public/schedule/buildings/{code}?date=`` -- every room of a building that day.

Each answers 404 ``not found`` when the view is off, the room / building is unknown or the date is outside the window
(the same body), and 429 with ``Retry-After`` above the per-address limit.

Caching (backend asks batch 3, item 1): a 200 carries ``Cache-Control: public, max-age=0, must-revalidate`` and an
``ETag`` over the settings version (sign-off + ``show_bookings``) and the response data, so a kiosk revalidates on
every poll and gets an empty 304 when nothing changed (``If-None-Match``, weak tags accepted). Every 404 and 429 is
``Cache-Control: no-store``: switching the view off takes effect on the next poll, whatever a kiosk or proxy holds.

Administration (``setup.settings``): ``GET/PUT /public-schedule/admin/settings`` ``{enabled, show_bookings}``; switching
it on records the KVKK sign-off (audited ``public_schedule.settings``).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import DB, require_permission
from app.core import throttle
from app.models import User
from app.services import bookings as bsvc
from app.services import calendar_feeds as feeds
from app.services import public_schedule as svc

router = APIRouter(prefix="/public/schedule", tags=["public"])
admin_router = APIRouter(prefix="/public-schedule/admin", tags=["public"])
SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]


class PublicSettingsIn(BaseModel):
    enabled: bool | None = None
    show_bookings: str | None = None


#: a 200 is revalidated on every poll (ETag / 304); refusals are never stored
CACHE_OK = "public, max-age=0, must-revalidate"
NO_STORE = {"Cache-Control": "no-store"}


def _not_found() -> HTTPException:
    return HTTPException(404, "not found", headers=NO_STORE)


def _limit(request: Request) -> None:
    address = request.client.host if request.client else "?"
    key = f"ip:{address}"
    if throttle.PUBLIC_PER_ADDRESS.hit(key):
        raise HTTPException(
            429,
            "too many requests",
            headers={"Retry-After": str(throttle.PUBLIC_PER_ADDRESS.retry_after(key) or 1), **NO_STORE},
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


async def _cached(request: Request, db: DB, out: dict[str, Any]) -> Response:
    """200 with an ETag over the settings version and the data, or an empty 304 when the kiosk already has it."""
    version = await svc.settings_version(db)
    body = json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    etag = '"' + hashlib.sha256(f"{version}\n{body}".encode()).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": CACHE_OK}
    if feeds.etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(out, headers=headers)


async def _with_slot_labels(db: DB, out: dict[str, Any]) -> dict[str, Any]:
    """The label part of the administrator's slot display (W3-SLOT, slot-display.md §5): the kiosk is not signed in,
    so it cannot read GET /bookings/slot-display. Items are never hidden by the visible-period window here."""
    from app.api.v1.bookings import slot_display

    sd = await slot_display(db)
    return {**out, "slot_display": {k: sd[k] for k in ("label", "period_name", "time_format")}}


@router.get("")
async def public_index(request: Request, db: DB) -> Response:
    _limit(request)
    try:
        out = await svc.index(db)
    except svc.NotFound as exc:
        raise _not_found() from exc
    return await _cached(request, db, out)


@router.get("/rooms/{code}")
async def public_room(
    code: str, request: Request, db: DB, day: Annotated[str | None, Query(alias="date")] = None
) -> Response:
    _limit(request)
    d = await _day(db, day)
    try:
        out = await svc.room_day(db, code, d)
    except svc.NotFound as exc:
        raise _not_found() from exc
    return await _cached(request, db, await _with_slot_labels(db, out))


@router.get("/buildings/{code}")
async def public_building(
    code: str, request: Request, db: DB, day: Annotated[str | None, Query(alias="date")] = None
) -> Response:
    _limit(request)
    d = await _day(db, day)
    try:
        out = await svc.building_day(db, code, d)
    except svc.NotFound as exc:
        raise _not_found() from exc
    return await _cached(request, db, await _with_slot_labels(db, out))


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
