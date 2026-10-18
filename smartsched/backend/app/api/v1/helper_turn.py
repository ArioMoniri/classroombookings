"""``POST /helper/turn`` (HB-06): one helper question, answered as a ``text/event-stream`` of server-built cards.

Events: ``run_started`` {turn_id}, ``tool_start`` {name}, ``tool`` {name, ok}, ``text`` {text}, ``card`` {card}
(``helper.card.v1``, validated), ``run_finished`` {turn_id, mode, outcome, fallback, model_calls, cards}, or
``error`` {status, detail} on an unexpected failure. Index mode (the default until an admin routes ``helper``)
makes no model call; every AI failure falls back to index mode inside the stream (:mod:`app.ai.helper_turn`).

The router is mounted next to ``app.api.v1.helper`` (``/api/v1/helper``), so ``GET /helper/status`` sees the route
and reports ``turn_available``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DB, CurrentAccess
from app.core.db import get_session_factory
from app.core.security import redact_keys

log = logging.getLogger(__name__)

router = APIRouter(prefix="/helper", tags=["helper"])


class TurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    lang: Literal["tr", "en"] = "tr"


def _sse(kind: str, data: dict[str, Any]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/turn")
async def post_turn(body: TurnIn, db: DB, access: CurrentAccess) -> StreamingResponse:
    """One helper turn, streamed. The turn runs on its own session (this request's session is released first)."""
    from app.ai.helper_turn import run_turn
    from app.services.bookings_perms import load_access

    user_id = access.user_id
    await db.rollback()
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        data = dict(event)
        await queue.put((str(data.pop("type")), data))

    async def work() -> None:
        try:
            async with get_session_factory()() as s:
                from app.models import User

                user = await s.get(User, user_id)
                if user is None:
                    await queue.put(("error", {"status": 401, "detail": "not signed in"}))
                    return
                await run_turn(s, await load_access(s, user), body.text, body.lang, emit=emit)
                await s.commit()
        except Exception as exc:  # noqa: BLE001 - reported as an event, never with a key or the prompt
            log.warning("helper turn failed: %s", redact_keys(type(exc).__name__))
            await queue.put(("error", {"status": 500, "detail": "the helper failed; try again"}))
        finally:
            await queue.put(None)

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


__all__ = ["TurnIn", "router"]
