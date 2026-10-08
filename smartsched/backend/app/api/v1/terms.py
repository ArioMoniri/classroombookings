from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, Planner, Viewer
from app.models import Term, Week
from app.schemas.catalog import TermIn, TermOut, TermUpdate, WeekIn, WeekOut

router = APIRouter(prefix="/terms", tags=["terms"])


@router.get("", response_model=list[TermOut])
async def list_terms(db: DB, _: Viewer) -> list[Term]:
    return list((await db.execute(select(Term).order_by(Term.id.desc()))).scalars())


@router.post("", response_model=TermOut, status_code=201)
async def create_term(body: TermIn, db: DB, _: Planner) -> Term:
    if (await db.execute(select(Term).where(Term.code == body.code))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "term code exists")
    data = body.model_dump()
    data["name"] = (data.get("name") or "").strip() or body.code
    term = Term(**data)
    db.add(term)
    if body.is_active:
        for other in (await db.execute(select(Term).where(Term.is_active.is_(True)))).scalars():
            other.is_active = False
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "term code exists") from exc
    await db.refresh(term)
    return term


async def _get(db: DB, term_id: int) -> Term:
    term = await db.get(Term, term_id)
    if term is None:
        raise HTTPException(404, "term not found")
    return term


@router.get("/{term_id}", response_model=TermOut)
async def get_term(term_id: int, db: DB, _: Viewer) -> Term:
    return await _get(db, term_id)


@router.put("/{term_id}", response_model=TermOut)
async def update_term(term_id: int, body: TermUpdate, db: DB, _: Planner) -> Term:
    term = await _get(db, term_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(term, k, v)
    if body.is_active:
        for other in (await db.execute(select(Term).where(Term.id != term.id, Term.is_active.is_(True)))).scalars():
            other.is_active = False
    await db.commit()
    await db.refresh(term)
    return term


@router.delete("/{term_id}", status_code=204)
async def delete_term(term_id: int, db: DB, _: Planner) -> None:
    term = await _get(db, term_id)
    await db.delete(term)
    await db.commit()


@router.get("/{term_id}/weeks", response_model=list[WeekOut])
async def list_weeks(term_id: int, db: DB, _: Viewer) -> list[Week]:
    await _get(db, term_id)
    return list((await db.execute(select(Week).where(Week.term_id == term_id).order_by(Week.index))).scalars())


@router.put("/{term_id}/weeks", response_model=list[WeekOut])
async def replace_weeks(term_id: int, body: list[WeekIn], db: DB, _: Planner) -> list[Week]:
    term = await _get(db, term_id)
    existing = {w.index: w for w in (await db.execute(select(Week).where(Week.term_id == term_id))).scalars()}
    seen = set()
    for w in body:
        seen.add(w.index)
        row = existing.get(w.index)
        if row is None:
            db.add(Week(term_id=term_id, **w.model_dump()))
        else:
            for k, v in w.model_dump().items():
                setattr(row, k, v)
    for idx, row in existing.items():
        if idx not in seen:
            await db.delete(row)
    if body:
        term.week_count = (
            max(w.index for w in body if w.kind != "EXAM") if any(w.kind != "EXAM" for w in body) else term.week_count
        )
    await db.commit()
    return list((await db.execute(select(Week).where(Week.term_id == term_id).order_by(Week.index))).scalars())
