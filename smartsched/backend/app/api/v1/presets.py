"""Studio presets: university-wide snapshots of rules (names, not ids), scope and include/exclude filters.

Any PLANNER can list, create and apply presets; the author or an ADMIN can edit one; only an ADMIN can
delete one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import DB, Admin, Planner
from app.models import StudioPreset
from app.schemas.studio import PresetApplyIn, PresetApplyOut, PresetIn, PresetOut, PresetUpdate
from app.services import studio as st
from app.services import studio_rules as sr

router = APIRouter(prefix="/presets", tags=["studio"])


async def _preset(db: DB, preset_id: int) -> StudioPreset:
    p = await db.get(StudioPreset, preset_id)
    if p is None:
        raise HTTPException(404, "preset not found")
    return p


@router.get("", response_model=list[PresetOut])
async def list_presets(db: DB, _: Planner, kind: str | None = None) -> list[dict[str, Any]]:
    return [await sr.preset_out(db, p) for p in await sr.list_presets(db, kind)]


@router.get("/{preset_id}", response_model=PresetOut)
async def get_preset(preset_id: int, db: DB, _: Planner) -> dict[str, Any]:
    return await sr.preset_out(db, await _preset(db, preset_id))


@router.post("", response_model=PresetOut, status_code=201)
async def create_preset(body: PresetIn, db: DB, user: Planner) -> dict[str, Any]:
    """Explicit ``rules`` / ``scope`` / ``filters``, or ``from_term_id`` to save the caller's current draft
    and that term's rules ("Save current as preset")."""
    try:
        return await sr.preset_out(db, await sr.create_preset(db, body, user))
    except st.StudioError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.put("/{preset_id}", response_model=PresetOut)
async def update_preset(preset_id: int, body: PresetUpdate, db: DB, user: Planner) -> dict[str, Any]:
    p = await _preset(db, preset_id)
    if user.role != "ADMIN" and p.created_by != user.id:
        raise HTTPException(403, "only the author or an ADMIN can edit this preset")
    try:
        return await sr.preset_out(db, await sr.update_preset(db, p, body))
    except st.StudioError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(preset_id: int, db: DB, _: Admin) -> None:
    await db.delete(await _preset(db, preset_id))
    await db.commit()


@router.post("/{preset_id}/apply", response_model=PresetApplyOut)
async def apply_preset(preset_id: int, body: PresetApplyIn, db: DB, user: Planner) -> dict[str, Any]:
    """Diff (``add`` / ``change`` / ``turn_off``) against the term's rules; unless ``dry_run``, adds the new
    rules to the term, applies changes and turn-offs to the caller's draft only, and sets the draft's
    scope, left-out classes (from the preset's filters) and built-in switches (ADMIN)."""
    p = await _preset(db, preset_id)
    try:
        return await sr.apply_preset(db, p, body.term_id, body.dry_run, user)
    except st.StudioError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
