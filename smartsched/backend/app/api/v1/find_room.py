"""T1 "find me a room" (docs/product/wave1-api.md §2): ``POST /rooms/find``, ``GET /rooms/find/recent``.

Any signed-in user; results cover only the rooms the caller may view (``room.view`` by role or room ACL).
Rate limit: 30 searches per minute per user (429 with ``Retry-After``)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import DB, CurrentAccess
from app.core.throttle import Throttle
from app.schemas.find_room import FindIn, FindOut
from app.services import find_room as svc
from app.services.bookings_settings import get_user_value, set_user_value

router = APIRouter(prefix="/rooms/find", tags=["find-room"])
#: per user; per process like the other in-process limiters (app/core/throttle.py)
FIND_LIMIT = Throttle(window_s=60, limit=30)
RECENT_KEY = "find"
RECENT_MAX = 10


def to_query(body: FindIn) -> svc.FindQuery:
    dates = list(body.dates)
    if body.date is not None:
        dates.append(body.date)
    return svc.FindQuery(
        term_id=body.term_id,
        dates=dates,
        date_from=body.date_from,
        date_to=body.date_to,
        weekdays=body.weekdays,
        weekday=body.weekday,
        weeks=body.weeks,
        start=body.start,
        end=body.end,
        duration_periods=body.duration_periods,
        duration_min=body.duration_min,
        window_end=body.window_end,
        headcount=body.headcount,
        purpose=body.purpose,
        features=[svc.FeatureReq(f.field, f.op, f.value) for f in body.features],
        tags=body.tags,
        buildings=body.buildings,
        preferred_building=body.preferred_building,
        room_group_id=body.room_group_id,
        text=body.text,
        include_busy=body.include_busy,
        include_requestable=body.include_requestable,
        flex_periods=body.flex.periods,
        other_days=body.flex.other_days,
        limit=body.limit,
    )


@router.post("", response_model=FindOut)
async def find(body: FindIn, db: DB, access: CurrentAccess) -> dict[str, Any]:
    key = f"user:{access.user_id}"
    if FIND_LIMIT.hit(key):
        raise HTTPException(
            429,
            {
                "code": "rate_limited",
                "message": "too many searches; try again in a minute",
                "message_tr": "çok fazla arama; bir dakika sonra yeniden deneyin",
            },
            headers={"Retry-After": str(FIND_LIMIT.retry_after(key))},
        )
    try:
        out = await svc.find_rooms(db, access, to_query(body))
    except svc.FindError as exc:
        raise HTTPException(exc.status, exc.as_detail()) from exc
    # the user's last searches (settings ``user.{id}.find``), newest first, without duplicates
    raw = await get_user_value(db, access.user_id, RECENT_KEY)
    try:
        recent = json.loads(raw) if raw else []
    except ValueError:
        recent = []
    entry = body.model_dump(mode="json", exclude_defaults=True)
    recent = [entry, *[r for r in recent if r != entry]][:RECENT_MAX]
    await set_user_value(db, access.user_id, RECENT_KEY, json.dumps(recent, ensure_ascii=False))
    await db.commit()
    return out


@router.get("/recent")
async def recent(db: DB, access: CurrentAccess) -> list[dict[str, Any]]:
    """The caller's last 10 searches (request bodies, newest first) to re-run with one click."""
    raw = await get_user_value(db, access.user_id, RECENT_KEY)
    try:
        return list(json.loads(raw)) if raw else []
    except ValueError:
        return []
