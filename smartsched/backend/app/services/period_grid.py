"""The university's period grid, editable by admins (RF-09; audit Part B "Period grid").

The grid is the clock time of each of the 18 periods (P1 08:30-09:10 ... P18 22:10-22:50 by default,
``normalize.DEFAULT_PERIODS``). Admins change the times; the number of periods stays 18, because the solver, every
stored request (``start_period`` / ``end_period``) and the booking periods address P1-P18.

* stored in the settings row ``calendar.period_grid`` (``{"periods": [["08:30", "09:10"], ...]}``); no row = default;
* applied in place to ``normalize.PERIODS`` (every reader of the grid: importers, find-room, feeds, exports, the parse
  child through ``safe_files.run_isolated``); other API workers pick a change up within :data:`REFRESH_S`
  (:func:`start_refresh_job`, from ``app.main``) and at start-up;
* booking periods that were made from the grid (one period, same index, the old clock times) follow the change;
* audited: ``period_grid.update`` / ``period_grid.reset`` with the old and the new times.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Sequence
from datetime import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n
from app.models import BookingPeriod, Setting, User
from app.services.events import publish_event

log = logging.getLogger(__name__)

SETTING_KEY = "calendar.period_grid"
#: how often a worker re-reads the stored grid (another worker may have changed it)
REFRESH_S = 30.0


class GridError(Exception):
    """A refused grid: HTTP status, code and both sentences."""

    def __init__(self, code: str, tr: str, en: str, status: int = 422) -> None:
        super().__init__(en)
        self.code, self.tr, self.en, self.status = code, tr, en, status


Times = list[tuple[time, time]]


def parse(periods: Sequence[Any]) -> Times:
    """``[{"start": "08.30", "end": "09:10"}, ...]`` (or ``[start, end]`` pairs) -> validated ``(start, end)`` times.
    Turkish input is read (dotted times, NBSP). Refusals: ``period_grid_count``, ``period_grid_time``,
    ``period_grid_order``."""
    want = len(n.DEFAULT_PERIODS)
    if len(periods) != want:
        raise GridError(
            "period_grid_count",
            f"Ders saati çizelgesi {want} ders saatinden oluşur; {len(periods)} saat gönderildi.",
            f"the period grid has {want} periods; got {len(periods)}",
        )
    out: Times = []
    for i, p in enumerate(periods, 1):
        raw = (p.get("start"), p.get("end")) if isinstance(p, dict) else tuple(p)[:2]
        start, end = (n.parse_time(n.clean_text(v) if isinstance(v, str) else v) for v in raw)
        if start is None or end is None:
            bad = raw[0] if start is None else raw[1]
            raise GridError(
                "period_grid_time",
                f"P{i}: '{n.clean_text(bad) or ''}' saati okunamadı (örnek: 08:30).",
                f"P{i}: cannot read the time {bad!r} (e.g. 08:30)",
            )
        if end <= start:
            raise GridError(
                "period_grid_order",
                f"P{i}: bitiş saati ({end:%H:%M}) başlangıçtan ({start:%H:%M}) sonra olmalı.",
                f"P{i}: the end {end:%H:%M} must be after the start {start:%H:%M}",
            )
        if out and start < out[-1][1]:
            raise GridError(
                "period_grid_order",
                f"P{i} ({start:%H:%M}), P{i - 1} bitmeden ({out[-1][1]:%H:%M}) başlıyor; saatler sırayla ve "
                "çakışmadan gelmeli.",
                f"P{i} starts at {start:%H:%M} before P{i - 1} ends at {out[-1][1]:%H:%M}",
            )
        out.append((start, end))
    return out


def _pairs(times: Sequence[tuple[time, time]]) -> list[list[str]]:
    return [[f"{s:%H:%M}", f"{e:%H:%M}"] for s, e in times]


def current() -> Times:
    return [(p.start, p.end) for p in n.PERIODS]


async def stored(session: AsyncSession) -> Times | None:
    """The admins' grid from the settings row, or ``None`` (default; also for an unreadable row, logged)."""
    row = await session.get(Setting, SETTING_KEY)
    if row is None or not row.value:
        return None
    try:
        return parse(json.loads(row.value).get("periods") or [])
    except (ValueError, GridError, AttributeError) as exc:
        log.warning("ignoring the stored period grid (%s): %s", SETTING_KEY, exc)
        return None


def out(source: str, **extra: Any) -> dict[str, Any]:
    return {
        "source": source,
        "count": len(n.PERIODS),
        "periods": [
            {"index": p.index, "start": f"{p.start:%H:%M}", "end": f"{p.end:%H:%M}", "label": p.label}
            for p in n.PERIODS
        ],
        "default": [
            {"index": p.index, "start": f"{p.start:%H:%M}", "end": f"{p.end:%H:%M}"} for p in n.DEFAULT_PERIODS
        ],
        **extra,
    }


async def describe(session: AsyncSession) -> dict[str, Any]:
    grid = await stored(session)
    if grid is not None and grid != current():
        n.set_period_grid(grid)
    return out("setting" if grid is not None else "default")


async def _follow(session: AsyncSession, old: Times, new: Times) -> int:
    """Booking periods made from the grid (one grid period, the old clock times) take the new times."""
    moved = 0
    for bp in (await session.execute(select(BookingPeriod))).scalars():
        i = bp.start_period
        if bp.end_period != i or not 1 <= i <= len(old) or old[i - 1] == new[i - 1]:
            continue
        if (bp.time_start, bp.time_end) == old[i - 1]:
            bp.time_start, bp.time_end = new[i - 1]
            moved += 1
    return moved


async def save(session: AsyncSession, times: Times, actor: User | None) -> dict[str, Any]:
    """Store and apply ``times`` (from :func:`parse`); audited ``period_grid.update``."""
    old = current()
    row = await session.get(Setting, SETTING_KEY)
    value = json.dumps({"periods": _pairs(times)})
    if row is None:
        session.add(Setting(key=SETTING_KEY, value=value, is_secret=False))
    else:
        row.value = value
    moved = await _follow(session, old, times)
    await publish_event(
        session,
        "period_grid.update",
        "period_grid",
        SETTING_KEY,
        before={"periods": _pairs(old)},
        after={"periods": _pairs(times), "booking_periods_updated": moved},
        actor=actor,
    )
    await session.commit()
    n.set_period_grid(times)
    return out("setting", booking_periods_updated=moved)


async def reset(session: AsyncSession, actor: User | None) -> dict[str, Any]:
    """Back to the default grid (the settings row goes); audited ``period_grid.reset``."""
    old = current()
    default = [(p.start, p.end) for p in n.DEFAULT_PERIODS]
    row = await session.get(Setting, SETTING_KEY)
    if row is not None:
        await session.delete(row)
    moved = await _follow(session, old, default)
    await publish_event(
        session,
        "period_grid.reset",
        "period_grid",
        SETTING_KEY,
        before={"periods": _pairs(old)},
        after={"periods": _pairs(default), "booking_periods_updated": moved},
        actor=actor,
    )
    await session.commit()
    n.set_period_grid(None)
    return out("default", booking_periods_updated=moved)


async def refresh(session: AsyncSession) -> bool:
    """Apply the stored grid in this process; True when the grid in use changed."""
    grid = await stored(session)
    target = grid if grid is not None else [(p.start, p.end) for p in n.DEFAULT_PERIODS]
    if target == current():
        return False
    n.set_period_grid(grid)
    return True


_task: asyncio.Task[None] | None = None


async def _loop() -> None:
    from app.core.db import get_session_factory

    while True:
        try:
            async with get_session_factory()() as session:
                if await refresh(session):
                    log.info("period grid changed by another worker; applied")
        except Exception:  # noqa: BLE001 - a database hiccup must not stop the loop
            log.exception("period grid refresh failed")
        await asyncio.sleep(REFRESH_S)


def start_refresh_job() -> None:
    """Started from ``app.main`` lifespan (not in the test environment)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="period-grid-refresh")


async def stop_refresh_job() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None


__all__ = ["GridError", "describe", "parse", "refresh", "reset", "save", "start_refresh_job", "stop_refresh_job"]
