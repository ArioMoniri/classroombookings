from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, Planner, Viewer
from app.models import ConstraintRow
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
    q = select(ConstraintRow).order_by(ConstraintRow.id)
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
    row = ConstraintRow(**body.model_dump(), created_by=user.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{cid}", response_model=ConstraintOut)
async def update_constraint(cid: int, body: ConstraintUpdate, db: DB, _: Planner) -> ConstraintRow:
    row = await db.get(ConstraintRow, cid)
    if row is None:
        raise HTTPException(404, "constraint not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{cid}", status_code=204)
async def delete_constraint(cid: int, db: DB, _: Planner) -> None:
    row = await db.get(ConstraintRow, cid)
    if row is None:
        raise HTTPException(404, "constraint not found")
    await db.delete(row)
    await db.commit()
