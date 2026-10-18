"""Periodic booking reminders (RF-11): every few minutes the owners of the bookings that start within the
organisation's lead time (``bookings.reminder_lead_hours``, default 24, 0 = off) get one ``booking.reminder``
notice (e-mail + bell, their preferences apply). Idempotent through the delivery ledger: a second sweep, a
restart or a second process sends nothing more (``app.services.mail_senders.send_due_reminders``)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.db import get_session_factory

log = logging.getLogger("smartsched.reminders")

INTERVAL_S = 300.0
_task: asyncio.Task[None] | None = None


async def sweep_once() -> int:
    """One sweep in its own transaction; the number of bookings reminded."""
    from app.services import mail_senders

    async with get_session_factory()() as session:
        sent = await mail_senders.send_due_reminders(session)
        await session.commit()
    return sent


async def _loop(interval: float) -> None:
    while True:
        try:
            sent = await sweep_once()
            if sent:
                log.info("booking reminders: %s sent", sent)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failing sweep must never stop the loop or the app
            log.exception("booking reminder sweep failed")
        await asyncio.sleep(interval)


def start(interval: float = INTERVAL_S) -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(interval), name="booking-reminders")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
