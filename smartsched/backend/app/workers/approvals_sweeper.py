"""Periodic approvals sweep (wave 1 P1): expire overdue requests and release tentative holds that ran out, so
slots free up even when nobody opens the approvals inbox. The sweep itself is idempotent and also runs lazily
on every approvals call; this loop only bounds how long a held slot can stay blocked (one interval)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.db import get_session_factory

log = logging.getLogger("smartsched.approvals")

INTERVAL_S = 60.0
_task: asyncio.Task[None] | None = None


async def sweep_once() -> dict[str, int]:
    from app.services import approvals

    async with get_session_factory()() as session:
        out = await approvals.sweep(session)
        await session.commit()
    return out


async def _loop(interval: float) -> None:
    while True:
        try:
            out = await sweep_once()
            if any(out.values()):
                log.info("approvals sweep: %s", out)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failing sweep must never stop the loop or the app
            log.exception("approvals sweep failed")
        await asyncio.sleep(interval)


def start(interval: float = INTERVAL_S) -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(interval), name="approvals-sweeper")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
