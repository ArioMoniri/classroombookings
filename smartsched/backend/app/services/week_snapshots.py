"""E2EA2-F06 (FIX-K): the values a board import gave each term week (``imported_snapshots`` entity ``week``), so a
week an admin set back to its file values is no longer "Elle değiştirildi" and the next board import updates it."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImportedSnapshot, Week

ENTITY = "week"
FIELDS = ("kind", "label", "start_date")


def _values(w: Week) -> dict[str, Any]:
    return {"kind": w.kind, "label": w.label, "start_date": w.start_date.isoformat() if w.start_date else None}


async def remember_imported_week(session: AsyncSession, w: Week) -> None:
    """Store (or refresh) the imported values of ``w``; it must have an id (flush first)."""
    row = (
        await session.execute(
            select(ImportedSnapshot).where(ImportedSnapshot.entity == ENTITY, ImportedSnapshot.entity_id == w.id)
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(ImportedSnapshot(entity=ENTITY, entity_id=w.id, values=_values(w)))
    else:
        row.values = _values(w)


async def matches_import(session: AsyncSession, w: Week) -> bool | None:
    """Whether ``w`` equals its imported values again; ``None`` when nothing was remembered."""
    row = (
        await session.execute(
            select(ImportedSnapshot).where(ImportedSnapshot.entity == ENTITY, ImportedSnapshot.entity_id == w.id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return all((row.values or {}).get(k) == v for k, v in _values(w).items())
