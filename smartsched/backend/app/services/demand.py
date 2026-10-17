"""Find-room / booking demand ledger (adaptive scheduling AS-05; docs/research/2026-10-17-adaptive-scheduling.md §2.4).

What is recorded, one ``demand_events`` row per find-room search (``outcome`` ``searched``, or ``none`` when no room
was free) and per booking created (``booked``): the term, the first asked date and its weekday, the period span, the
period kind of that date, a **headcount band** (never the number), the requested features, the building filter
and the number of free rooms found. **No user id and no free text** (KVKK Art. 7: aggregate data that cannot be
linked to a person); the search text, the person and the exact headcount are never stored.

Reads (``GET /analytics/demand``) aggregate the cells and suppress every count below :data:`MIN_CELL` (shown as
``"<5"``), so a single person's habit cannot be read off a rare cell. Rows older than ``demand.retention_days``
(default 400) are deleted by the daily KVKK purge (:func:`purge`, called from ``kvkk.purge_expired``).

Writing never breaks a search or a booking: it runs in its own short session and swallows errors.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting
from app.models.base import utcnow
from app.models.seasons import DemandEvent

log = logging.getLogger("smartsched.demand")

#: cells with fewer events than this are shown as "<5"
MIN_CELL = 5
RETENTION_SETTING = "demand.retention_days"
DEFAULT_RETENTION_DAYS = 400
#: headcount bands (inclusive upper bounds), the capacity bands of the heatmap (``utilisation.CAPACITY_BANDS``)
BANDS: tuple[tuple[int, str], ...] = ((30, "≤30"), (60, "31–60"), (100, "61–100"), (150, "101–150"))
TOP_BAND = "151+"
GROUPS = ("weekday_period", "period", "weekday", "headcount_band", "feature", "building", "period_kind")
_DAY_TR = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
_DAY_EN = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


def _t(tr: str, en: str) -> dict[str, str]:
    return {"tr": tr, "en": en}


def headcount_band(headcount: int | None) -> str | None:
    if not headcount or headcount <= 0:
        return None
    for upper, label in BANDS:
        if headcount <= upper:
            return label
    return TOP_BAND


def _clean_features(features: Iterable[Any]) -> list[str]:
    """Feature / tag codes only (short identifiers), never free text."""
    import re

    out = set()
    for f in features:
        code = str(f).strip()
        if re.fullmatch(r"[A-Za-z0-9_.:\-]{1,40}", code):
            out.add(code.upper() if len(code) <= 8 else code)
    return sorted(out)[:20]


async def _period_kind(session: AsyncSession, term_id: int | None, d: date | None) -> str | None:
    if term_id is None or d is None:
        return None
    from app.models import Term
    from app.services import seasons

    term = await session.get(Term, term_id)
    if term is None:
        return None
    weeks_rows, holidays, segs = await seasons.load_calendar(session, term)
    return seasons.period_kind_on(term, d, weeks_rows, holidays, segs)


async def record(
    *,
    term_id: int | None,
    d: date | None,
    start_period: int | None,
    end_period: int | None,
    headcount: int | None,
    features: Iterable[Any] = (),
    building: str | None = None,
    results_count: int = 0,
    outcome: str = "searched",
    source: str = "find_room",
) -> None:
    """Append one aggregate row in its own session (committed); never raises."""
    from app.core.db import get_session_factory

    try:
        async with get_session_factory()() as s:
            s.add(
                DemandEvent(
                    ts=utcnow(),
                    term_id=term_id,
                    date=d,
                    weekday=d.isoweekday() if d else None,
                    start_period=start_period,
                    end_period=end_period,
                    period_kind=await _period_kind(s, term_id, d),
                    headcount_band=headcount_band(headcount),
                    features=_clean_features(features),
                    building=(str(building).strip().upper()[:16] or None) if building else None,
                    results_count=max(0, int(results_count or 0)),
                    outcome=outcome if outcome in ("searched", "booked", "none") else "searched",
                    source=source if source in ("find_room", "booking") else "find_room",
                )
            )
            await s.commit()
    except Exception:  # noqa: BLE001 - the ledger never breaks a search or a booking
        log.warning("demand ledger write failed", exc_info=True)


async def record_search(
    term_id: int | None, dates: list[date], start: int, end: int, q: Any, free: int, tags: Iterable[str] = ()
) -> None:
    """Called by ``find_room.find_rooms`` with its resolved query (``tags``: the room tags the search asked for,
    from the chips and the text): one row per search."""
    feats = [*tags]
    for fr in getattr(q, "features", None) or []:
        feats.append(str(getattr(fr, "field", "")))
    buildings = getattr(q, "buildings", None) or []
    await record(
        term_id=term_id,
        d=min(dates) if dates else None,
        start_period=start,
        end_period=end,
        headcount=getattr(q, "headcount", None),
        features=feats,
        building=str(buildings[0]) if len(buildings) == 1 else None,
        results_count=free,
        outcome="searched" if free > 0 else "none",
    )


async def record_booking(b: Any) -> None:
    """Called by ``bookings.create_single`` after the commit (outcome ``booked``)."""
    await record(
        term_id=b.term_id,
        d=b.date,
        start_period=b.start_period,
        end_period=b.end_period,
        headcount=b.headcount,
        features=b.required_features or [],
        results_count=1,
        outcome="booked",
        source="booking",
    )


async def retention_days(session: AsyncSession) -> int:
    row = await session.get(Setting, RETENTION_SETTING)
    try:
        days = int(str(row.value)) if row is not None and row.value else DEFAULT_RETENTION_DAYS
    except ValueError:
        days = DEFAULT_RETENTION_DAYS
    return max(30, days)


async def purge(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Delete rows older than the retention (the daily KVKK purge hook)."""
    cutoff = (now or utcnow()) - timedelta(days=await retention_days(session))
    res = await session.execute(
        delete(DemandEvent).where(DemandEvent.ts < cutoff).execution_options(synchronize_session=False)
    )
    return {"demand_events": int(getattr(res, "rowcount", 0) or 0)}


def _shown(n: int) -> int | str:
    return n if n >= MIN_CELL else f"<{MIN_CELL}"


def _key(e: DemandEvent, group: str) -> list[tuple[Any, ...]]:
    if group == "weekday_period":
        if e.weekday is None or e.start_period is None:
            return []
        return [(e.weekday, p) for p in range(e.start_period, (e.end_period or e.start_period) + 1)]
    if group == "period":
        if e.start_period is None:
            return []
        return [(p,) for p in range(e.start_period, (e.end_period or e.start_period) + 1)]
    if group == "weekday":
        return [(e.weekday,)] if e.weekday else []
    if group == "headcount_band":
        return [(e.headcount_band or "?",)]
    if group == "feature":
        return [(f,) for f in (e.features or [])] or [("-",)]
    if group == "building":
        return [(e.building or "*",)]
    return [(e.period_kind or "?",)]


def _label(group: str, key: tuple[Any, ...]) -> dict[str, str]:
    if group == "weekday_period":
        return _t(f"{_DAY_TR.get(key[0], key[0])} {key[1]}. ders", f"{_DAY_EN.get(key[0], key[0])} period {key[1]}")
    if group == "period":
        return _t(f"{key[0]}. ders", f"period {key[0]}")
    if group == "weekday":
        return _t(_DAY_TR.get(key[0], str(key[0])), _DAY_EN.get(key[0], str(key[0])))
    if group == "building":
        return (
            _t("Bina seçilmedi", "No building filter") if key[0] == "*" else _t(f"{key[0]} blok", f"Building {key[0]}")
        )
    if group == "headcount_band":
        return _t(f"{key[0]} kişi", f"{key[0]} people")
    return _t(str(key[0]), str(key[0]))


async def demand(
    session: AsyncSession,
    *,
    term_id: int | None = None,
    group_by: str = "weekday_period",
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Aggregate demand cells: searches, searches without a free room (``unmet``) and bookings, every count below
    :data:`MIN_CELL` shown as ``"<5"``. No row names a person."""
    if group_by not in GROUPS:
        raise ValueError(group_by)
    q = select(DemandEvent)
    if term_id is not None:
        q = q.where(DemandEvent.term_id == term_id)
    if date_from is not None:
        q = q.where(DemandEvent.date >= date_from)
    if date_to is not None:
        q = q.where(DemandEvent.date <= date_to)
    counts: dict[tuple[Any, ...], dict[str, int]] = defaultdict(lambda: {"searched": 0, "none": 0, "booked": 0})
    total = 0
    for e in (await session.execute(q)).scalars():
        total += 1
        for k in _key(e, group_by):
            counts[k][e.outcome] = counts[k].get(e.outcome, 0) + 1
    cells = []
    suppressed = 0
    for k in sorted(counts, key=lambda x: tuple(str(v) for v in x)):
        c = counts[k]
        searches = c["searched"] + c["none"]
        small = any(0 < v < MIN_CELL for v in (searches, c["none"], c["booked"]))
        suppressed += int(small)
        cells.append(
            {
                "key": list(k),
                "label": _label(group_by, k),
                "searches": _shown(searches),
                "unmet": _shown(c["none"]) if c["none"] else 0,
                "booked": _shown(c["booked"]) if c["booked"] else 0,
                "suppressed": small,
            }
        )
    needs = None
    if total == 0:
        needs = _t(
            "Henüz talep kaydı yok: oda arama ve rezervasyonlar kaydedildikçe dolar",
            "No demand recorded yet: it fills as people search for rooms and book",
        )
    return {
        "term_id": term_id,
        "group_by": group_by,
        "cells": cells,
        "events": _shown(total) if total else 0,
        "min_cell": MIN_CELL,
        "suppressed_cells": suppressed,
        "confidence": "none" if total == 0 else ("low" if total < 50 else "medium"),
        "needs": needs,
        "definitions": {
            "kvkk": _t(
                "Kişisel veri yok: kullanıcı, arama metni ve kesin kişi sayısı tutulmaz; 5'ten küçük hücreler gizlenir",
                "No personal data: no user, no search text and no exact headcount is kept; cells under 5 are hidden",
            ),
            "unmet": _t("Boş oda bulunamayan aramalar", "Searches that found no free room"),
        },
    }


__all__ = ["MIN_CELL", "demand", "headcount_band", "purge", "record", "record_booking", "record_search"]
