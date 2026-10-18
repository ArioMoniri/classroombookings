"""Voice input (VO-03): ``POST /ai/voice/transcribe`` and ``GET /ai/voice/status``.

The clip is the **raw request body** (``Content-Type: audio/webm;codecs=opus`` and the like), not multipart: a
multipart upload over 1 MB is spooled to a temporary file by the form parser, while the raw body is read here in
chunks into memory with a hard cap and dropped with the request. Query: ``feature`` (``chat`` | ``rules`` |
``guard``, the field the person dictates into) and ``lang`` (``tr`` | ``en``). The answer is the transcript for
the person to review; it is sent later through that field's own endpoint, where the text guardrails run.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.ai import gateway as gw
from app.ai.voice import run
from app.ai.voice.errors import VoiceError
from app.api.deps import DB, CurrentAccess

router = APIRouter(tags=["ai-voice"])


async def _read_capped(request: Request, cap: int) -> bytes:
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > cap:
            raise VoiceError("too_large", max_bytes=cap)
    return bytes(buf)


@router.get("/ai/voice/status")
async def voice_status(db: DB, access: CurrentAccess) -> dict[str, Any]:
    return await run.status(db, access.user, access.perms)


@router.post("/ai/voice/transcribe")
async def voice_transcribe(
    request: Request,
    db: DB,
    access: CurrentAccess,
    feature: str = Query("chat", max_length=16),
    lang: str | None = Query(None, max_length=8),
) -> dict[str, Any]:
    cap = int(gw.DEFAULT_CAPS["voice_stt"]["max_bytes"])
    data = await _read_capped(request, cap)
    return await run.transcribe(
        db, access.user, access.perms, data, request.headers.get("content-type"), target=feature, lang=lang
    )


__all__ = ["router"]
