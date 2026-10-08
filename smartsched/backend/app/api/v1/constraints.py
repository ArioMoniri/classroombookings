from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, Planner, Viewer
from app.models import ConstraintRow, ScheduleRun, Term
from app.schemas.runs import ConstraintIn, ConstraintOut, ConstraintUpdate
from app.solver.model import CONSTRAINT_KINDS_V1

router = APIRouter(prefix="/constraints", tags=["constraints"])


@router.get("/kinds")
async def kinds(_: Viewer) -> list[str]:
    return list(CONSTRAINT_KINDS_V1)


@router.get("", response_model=list[ConstraintOut])
async def list_constraints(
    db: DB, _: Viewer, term_id: int | None = None, run_id: int | None = None, enabled: bool | None = None
) -> list[ConstraintRow]:
    # draft-scoped built-in switches are studio state, not term rules (review M10)
    q = select(ConstraintRow).where(ConstraintRow.source != "BUILTIN").order_by(ConstraintRow.id)
    if term_id is not None:
        q = q.where(ConstraintRow.term_id == term_id)
    if run_id is not None:
        q = q.where(ConstraintRow.run_id == run_id)
    if enabled is not None:
        q = q.where(ConstraintRow.enabled.is_(enabled))
    return list((await db.execute(q)).scalars())


@router.post("", response_model=ConstraintOut, status_code=201)
async def create_constraint(body: ConstraintIn, db: DB, user: Planner) -> ConstraintRow:
    if body.term_id is None and body.run_id is None:
        raise HTTPException(400, "term_id or run_id required")
    _validate(body.kind, body.params, body.hardness)
    if body.term_id is not None and await db.get(Term, body.term_id) is None:
        raise HTTPException(404, "term not found")
    if body.run_id is not None and await db.get(ScheduleRun, body.run_id) is None:
        raise HTTPException(404, "run not found")
    row = ConstraintRow(**body.model_dump(), created_by=user.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{cid}", response_model=ConstraintOut)
async def update_constraint(cid: int, body: ConstraintUpdate, db: DB, _: Planner) -> ConstraintRow:
    row = await _editable(db, cid)
    data = body.model_dump(exclude_unset=True)
    params = data.get("params") if data.get("params") is not None else dict(row.params or {})
    _validate(row.kind, params, data.get("hardness") or row.hardness)
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{cid}", status_code=204)
async def delete_constraint(cid: int, db: DB, _: Planner) -> None:
    row = await _editable(db, cid)
    await db.delete(row)
    await db.commit()


def _validate(kind: str, params: dict[str, Any], hardness: str | None) -> None:
    """Kind, params and hardness through the constraint catalogue (the same check as AI proposals)."""
    from app.ai.catalog import validate_params

    issues = validate_params(kind, dict(params or {}), hardness)
    if issues:
        raise HTTPException(422, {"message": "invalid constraint", "issues": issues[:20]})


async def _editable(db: DB, cid: int) -> ConstraintRow:
    row = await db.get(ConstraintRow, cid)
    if row is None or row.source == "BUILTIN":  # built-in switches belong to a studio draft (ADMIN only)
        if row is not None:
            raise HTTPException(403, "built-in rule switches are changed in the Generator Studio (ADMIN only)")
        raise HTTPException(404, "constraint not found")
    return row
