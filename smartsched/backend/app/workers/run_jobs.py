"""Shared plumbing of solver jobs (bridge runs, studio runs, chat repairs): review M6 / M7 / M13.

* :func:`solve_off_loop` runs the CPU-bound solve in a worker thread **with no DB session open** (callers
  commit and close theirs first, so SQLite writers are never blocked by a read transaction held for the
  whole solve), bound to the run's cancel token (CP-SAT ``StopSearch``) and to a wall-clock limit
  (``time_limit_s * RUN_WALL_CLOCK_FACTOR + RUN_WALL_CLOCK_MARGIN_S``).
* :func:`start_run` / :func:`finish_cancelled` implement ``CANCELLED`` for runs cancelled while queued or
  while solving (the partial result is discarded).
* :func:`check_user_limit`: at most ``MAX_ACTIVE_RUNS_PER_USER`` QUEUED/RUNNING runs per user (429).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.workers import cancel

log = logging.getLogger(__name__)

ACTIVE = ("QUEUED", "RUNNING")


class RunCancelled(Exception):
    """The run was cancelled; nothing is persisted."""


class RunWallClockExceeded(RuntimeError):
    """The solve exceeded the run's wall-clock limit (search stopped, run FAILED)."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def wall_clock_limit(time_limit_s: float) -> float:
    s = get_settings()
    return max(1.0, float(time_limit_s) * float(s.run_wall_clock_factor) + float(s.run_wall_clock_margin_s))


async def solve_off_loop[T](run_id: int, time_limit_s: float, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """``fn(*args, **kwargs)`` in a worker thread, cancellable and wall-clock limited (see module doc)."""
    if cancel.is_cancelled(run_id):
        raise RunCancelled()
    limit = wall_clock_limit(time_limit_s)
    task = asyncio.ensure_future(asyncio.to_thread(cancel.bind(run_id, fn), *args, **kwargs))
    try:
        result = await asyncio.wait_for(asyncio.shield(task), limit)
    except TimeoutError as exc:
        cancel.cancel(run_id)  # StopSearch; the thread returns soon after
        try:
            await asyncio.wait_for(task, float(get_settings().run_cancel_grace_s))
        except Exception:  # noqa: BLE001 - the result of a stopped search is discarded anyway
            pass
        raise RunWallClockExceeded(f"run exceeded its wall-clock limit of {limit:.0f} s") from exc
    if cancel.is_cancelled(run_id):
        raise RunCancelled()
    return result


async def start_run(session: Any, run: Any) -> bool:
    """Mark ``run`` RUNNING unless it was cancelled while queued (then False: the job ends)."""
    if run.status == "CANCELLED" or cancel.is_cancelled(run.id):
        return False
    run.status = "RUNNING"
    run.started_at = _now()
    run.heartbeat_at = _now()
    return True


async def finish_cancelled(session_factory: Any, run_id: int, reason: str = "cancelled") -> dict[str, Any]:
    from app.models import ScheduleRun

    async with session_factory() as session:
        run = await session.get(ScheduleRun, run_id)
        if run is not None:
            run.status = "CANCELLED"
            run.error = run.error or reason
            run.finished_at = run.finished_at or _now()
            run.stats = {**(run.stats or {}), "phase": "cancelled"}
            await session.commit()
    cancel.release(run_id)
    return {"status": "CANCELLED"}


async def check_user_limit(session: Any, user_id: int | None) -> None:
    """Raise ``HTTPException(429)`` when ``user_id`` already has the maximum of active runs."""
    from fastapi import HTTPException
    from sqlalchemy import func, select

    from app.models import ScheduleRun

    if user_id is None:
        return
    cap = int(get_settings().max_active_runs_per_user)
    n = (
        await session.execute(
            select(func.count(ScheduleRun.id)).where(ScheduleRun.created_by == user_id, ScheduleRun.status.in_(ACTIVE))
        )
    ).scalar_one()
    if n >= cap:
        raise HTTPException(429, f"you already have {n} runs queued or running (limit {cap}); wait or cancel one")


__all__ = [
    "RunCancelled",
    "RunWallClockExceeded",
    "check_user_limit",
    "finish_cancelled",
    "solve_off_loop",
    "start_run",
    "wall_clock_limit",
]
