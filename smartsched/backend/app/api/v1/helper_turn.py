"""``POST /helper/turn`` (HB-06): one helper question, answered as a ``text/event-stream`` of server-built cards.

Events: ``run_started`` {turn_id}, ``tool_start`` {name}, ``tool`` {name, ok}, ``text`` {text}, ``card`` {card}
(``helper.card.v1``, validated), ``run_finished`` {turn_id, mode, outcome, fallback, model_calls, cards}, or
``error`` {status, detail} on an unexpected failure. Index mode (the default until an admin routes ``helper``)
makes no model call; every AI failure falls back to index mode inside the stream (:mod:`app.ai.helper_turn`).

Body: ``{text 1..1000, lang tr|en, context?: {route ≤ 200, entity_kind?: room | booking | approval_request,
entity_id? ≥ 1}}`` (HB-D). A bad shape is a 422 before the stream; an unknown route or an unreadable entity is
dropped silently inside the turn.

The router is mounted next to ``app.api.v1.helper`` (``/api/v1/helper``), so ``GET /helper/status`` sees the route
and reports ``turn_available``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import traceback
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DB, CurrentAccess
from app.core.db import get_session_factory
from app.core.security import redact_keys

log = logging.getLogger(__name__)

router = APIRouter(prefix="/helper", tags=["helper"])


class PageContextIn(BaseModel):
    """The page the person has open (HB-D). Only its shape is checked here; :mod:`app.ai.helper.page_context` drops
    a route outside the feature index or the person's pages and an entity they cannot read. Never a permission."""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(min_length=1, max_length=200)
    entity_kind: Literal["room", "booking", "approval_request"] | None = None
    entity_id: int | None = Field(default=None, ge=1)


class TurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    lang: Literal["tr", "en"] = "tr"
    context: PageContextIn | None = None


_BACKEND = Path(__file__).resolve().parents[3]


def failure_site(exc: BaseException) -> str:
    """``app/ai/helper/guard.py:42 in check``: where ``exc`` was raised (the innermost frame), relative to the backend.
    File, line and function only: never the message or the source line (they can echo the prompt; HB-17 bug 5)."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    f = frames[-1]
    path = Path(f.filename)
    try:
        shown = path.resolve().relative_to(_BACKEND).as_posix()
    except ValueError:
        shown = path.name
    return f"{shown}:{f.lineno} in {f.name}"


def _sse(kind: str, data: dict[str, Any]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/turn")
async def post_turn(body: TurnIn, db: DB, access: CurrentAccess) -> StreamingResponse:
    """One helper turn, streamed. The turn runs on its own session (this request's session is released first)."""
    from app.ai.helper import telemetry
    from app.ai.helper_turn import run_turn
    from app.services.bookings_perms import load_access

    user_id = access.user_id
    await db.rollback()
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        data = dict(event)
        await queue.put((str(data.pop("type")), data))

    async def work() -> None:
        access_: Any = None
        t0 = time.monotonic()
        try:
            async with get_session_factory()() as s:
                from app.models import User

                user = await s.get(User, user_id)
                if user is None:
                    await queue.put(("error", {"status": 401, "detail": "not signed in"}))
                    return
                access_ = await load_access(s, user)
                t0 = time.monotonic()
                ctx = body.context.model_dump() if body.context is not None else None
                result = await run_turn(s, access_, body.text, body.lang, emit=emit, context=ctx)
                # HB-14: one query row + metrics + the GenAI log line; no prompt text (never raises)
                await telemetry.record_turn(s, access_, body.text, result, latency_s=time.monotonic() - t0)
                await s.commit()
        except Exception as exc:  # noqa: BLE001 - reported as an event, never with a key or the prompt
            log.warning("helper turn failed: %s at %s", redact_keys(type(exc).__name__), redact_keys(failure_site(exc)))
            await _record_failure(exc, access_, time.monotonic() - t0)
            await queue.put(("error", {"status": 500, "detail": "the helper failed; try again"}))
        finally:
            await queue.put(None)

    async def _record_failure(exc: Exception, access_: Any, latency_s: float) -> None:
        """HB-14 telemetry for the failed turn (``outcome: error``, the exception class as ``reason``), on a fresh
        session: the turn's own may be unusable. Never raises."""
        partial = getattr(exc, "turn_result", None)
        if partial is None or access_ is None:
            return
        try:
            partial.outcome = "error"
            partial.fallback = re.sub(r"[^a-z_]", "", type(exc).__name__.lower())[:48] or "error"
            async with get_session_factory()() as s2:
                await telemetry.record_turn(s2, access_, body.text, partial, latency_s=latency_s)
                await s2.commit()
        except Exception:  # noqa: BLE001 - telemetry must never break the error event
            log.warning("helper turn failure telemetry failed: %s", type(exc).__name__)

    async def events() -> AsyncIterator[str]:
        task = asyncio.create_task(work())
        try:
            while (item := await queue.get()) is not None:
                yield _sse(*item)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


__all__ = ["PageContextIn", "TurnIn", "router"]
