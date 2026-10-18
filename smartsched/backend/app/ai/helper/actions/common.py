"""Shared argument types and resolvers of the helper actions (dates, rooms, periods)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Annotated

from pydantic import Field

from app.ai.guardrails import fold
from app.ai.helper.actions.registry import ActionRefused, Ctx
from app.models.catalog import Room
from app.services import bookings as bsvc

#: ``""`` (none), ``YYYY-MM-DD``, ``DD.MM.YYYY`` or a relative day word (bugün, yarın, today, tomorrow)
DayText = Annotated[
    str,
    Field(
        max_length=10,
        pattern=r"^(|\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|bugün|bugun|yarın|yarin|today|tomorrow)$",
        description="YYYY-MM-DD, or '' for none",
    ),
]
#: ``""`` or a clock time ``HH:MM``
ClockText = Annotated[str, Field(max_length=5, pattern=r"^(|\d{1,2}[:.]\d{2})$", description="HH:MM, or ''")]
WEEKDAYS_TR = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


async def resolve_day(ctx: Ctx, value: str) -> date | None:
    v = fold(value or "").strip()
    if not v:
        return None
    today = await bsvc.today(ctx.session)
    if v in ("bugun", "today"):
        return today
    if v in ("yarin", "tomorrow"):
        return today + timedelta(days=1)
    try:
        if "." in v:
            d, m, y = (int(x) for x in v.split("."))
            return date(y, m, d)
        return date.fromisoformat(v)
    except ValueError as exc:
        raise ActionRefused(422, "date", f"{value} geçerli bir tarih değil", f"{value} is not a valid date") from exc


def day_label(d: date) -> tuple[str, str]:
    return f"{d:%d.%m.%Y} {WEEKDAYS_TR[d.weekday()]}", f"{d:%d.%m.%Y} {WEEKDAYS_EN[d.weekday()]}"


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(text or ""))


async def resolve_rooms(ctx: Ctx, text: str | int) -> list[Room]:
    """Rooms the person may view whose id, code or name matches ``text`` exactly (``a204`` = ``A 204``); several
    matches → the caller asks with a ``choice`` card. Never a room the person cannot see."""
    rooms = await bsvc.visible_rooms(ctx.session, ctx.access)
    if isinstance(text, int) or str(text).strip().isdigit():
        rid = int(text)
        return [r for r in rooms if r.id == rid]
    key = _key(str(text))
    if not key:
        return []
    exact = [r for r in rooms if key in (_key(r.code), _key(r.display_name))]
    if exact:
        return exact
    return [r for r in rooms if key in _key(f"{r.code} {r.display_name}")][:6]


def now_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


__all__ = ["ClockText", "DayText", "WEEKDAYS_EN", "WEEKDAYS_TR", "day_label", "resolve_day", "resolve_rooms"]
