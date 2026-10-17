"""Audit rows for the Generator Studio and presets (review 2026-10-15 D5 / P19-02).

The studio's writes - draft edits, class edits and reverts, pre-check fixes, rule copies, accepted proposals and
presets - each write one ``audit_events`` row through :func:`app.services.events.publish_event` after the
change succeeded (a dry run is not audited). The payload names what changed, never the whole draft.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.audit import jsonable
from app.services.events import publish_event

#: list values longer than this are stored as their length (a draft can exclude 1 000+ classes)
_MAX_LIST = 50


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _compact(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        items = list(value)
        return {"count": len(items)} if len(items) > _MAX_LIST else [_compact(v) for v in items]
    return jsonable(value)


async def record(
    session: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: Any,
    actor: User,
    *,
    term_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Write the event and commit it (the studio services commit their own change first)."""
    await publish_event(
        session,
        action,
        entity_type,
        entity_id,
        before=_compact(before) if before is not None else None,
        after=_compact(after) if after is not None else None,
        actor=actor,
        term_id=term_id,
    )
    await session.commit()


__all__ = ["record"]
