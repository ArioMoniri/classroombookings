"""In-process event hooks (CRBS ``libraries/Events.php``: ``register`` / ``trigger``).

Handlers are ``async def handler(session, payload) -> None``; they run in the caller's DB session after
the change is flushed, and a failing handler is logged, never propagated (a broken hook must not undo a
booking). The notification module subscribes to the booking and password events."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]

EVENT_TYPES: dict[str, str] = {
    "user.logged_in": "a user signed in (payload: user_id, auth_method)",
    "booking.created": "a single booking was created (payload: booking_id, actor_id)",
    "booking.updated": "a booking was edited (payload: booking_ids, actor_id, scope)",
    "booking.cancelled": "bookings were cancelled (payload: booking_ids, actor_id, reason)",
    "series.created": "a recurring series was created (payload: series_id, booking_ids, actor_id)",
    "password.reset_requested": "a password reset token was issued (payload: user_id, token?, expires_at)",
}

_handlers: dict[str, list[Handler]] = {}


def on(event: str, handler: Handler) -> Handler:
    if event not in EVENT_TYPES:
        raise ValueError(f"unknown event {event!r}")
    _handlers.setdefault(event, [])
    if handler not in _handlers[event]:
        _handlers[event].append(handler)
    return handler


def off(event: str, handler: Handler) -> None:
    if handler in _handlers.get(event, []):
        _handlers[event].remove(handler)


def listeners() -> dict[str, list[str]]:
    return {e: [f"{h.__module__}.{h.__qualname__}" for h in _handlers.get(e, [])] for e in EVENT_TYPES}


async def emit(session: AsyncSession, event: str, payload: dict[str, Any]) -> None:
    for handler in list(_handlers.get(event, [])):
        try:
            await handler(session, payload)
        except Exception:  # noqa: BLE001 - hooks never break the action that triggered them
            log.exception("event handler %s for %s failed", handler, event)
