"""PER-F09 (fix-h-2026-10-18): "Derslerim", an academician's own classes in one week, read-only.

``GET /me/classes/week?date=YYYY-MM-DD`` lists the published classes of the instructor record(s) linked to the
account (P19-L1 ``Instructor.user_id``) from Monday to Sunday of that date's week (today's week without one), from
the same snapshot the "Derslerim" calendar feed serves (``calendar_classes.select_classes``). Without a linked record
it answers ``linked: false`` with an empty list, never a 403, so the page can say what to do.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentAccess
from app.services import bookings as booking_svc
from app.services import calendar_classes as cc

router = APIRouter(prefix="/me", tags=["my-classes"])


@router.get("/classes/week")
async def my_classes_week(
    db: DB, access: CurrentAccess, day: date | None = Query(None, alias="date")
) -> dict[str, Any]:
    today = await booking_svc.today(db)
    anchor = day or today
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    out: dict[str, Any] = {
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "prev": (monday - timedelta(days=7)).isoformat(),
        "next": (monday + timedelta(days=7)).isoformat(),
        "today": today.isoformat(),
        "linked": False,
        "term_id": None,
        "classes": [],
    }
    ids = await cc.linked_instructor_ids(db, access.user_id)
    if not ids:
        return out
    out["linked"] = True
    sel = await cc.select_classes(db, cc.ScopeFilter(instructor_ids=frozenset(ids)), monday, sunday, grace_days=0)
    rows = sorted((o for o, _ in sel.live), key=lambda o: (o.start, o.codes))
    out["classes"] = [
        {
            "uid": o.uid,
            "date": o.start.date().isoformat(),
            "start": o.start.strftime("%H:%M"),
            "end": o.end.strftime("%H:%M"),
            "codes": list(o.codes),
            "section": o.section,
            "title": o.title,
            "rooms": list(o.rooms),
            "week": o.week,
        }
        for o in rows
    ]
    out["term_id"] = rows[0].term_id if rows else None
    return out
