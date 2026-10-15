"""Learned suggestions with resettable memory (Phase 19 P19-L2..L4; docs/design/v2/phase19-suggestions.md).

==============================================================  ===============  ======================================
Route                                                           Permission       Notes
==============================================================  ===============  ======================================
``POST /learning/refresh`` {term_id?}                           planning.edit    extractors (idempotent) + priors
``GET /learning/suggestions?term_id=&person_id=&course_id=``    planning.view    ``state`` open (default) / accepted /
                                                                                 dismissed / snoozed / hidden / all
``GET /learning/priors?term_id=&subject_type=&subject_id=``     planning.view    every prior with its evidence
``POST /learning/suggestions/{id}/accept`` {weight?, kind?}     planning.edit    one soft targeted LEARNED rule
``POST /learning/suggestions/{id}/reject`` {reason?}            planning.edit    -3 and hidden for the scope + term
``POST /learning/suggestions/{id}/snooze`` {until}              planning.edit    next_solve / P7D / next_term
``GET /learning/memory/summary?term_id=``                       planning.view    counts for Ayarlar › Öğrenme
``POST /learning/reset`` {scope, value, reason}                 planning.admin   person / term / all; audited
``GET /learning/resets``                                        planning.admin   "Son sıfırlamalar"
``POST /learning/resets/{id}/undo``                             planning.admin   within 30 days
``POST /learning/purge``                                        planning.admin   the daily purge, on demand
``POST /learning/erase`` {instructor_id, reason}                planning.admin   KVKK erasure: immediate, no undo
==============================================================  ===============  ======================================

Nothing here applies a suggestion by itself; a memory reset removes learned memory only, never requests, runs,
bookings or accepted rules (and it is not a KVKK erasure: use ``/learning/erase``).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import DB, require_permission
from app.models import User
from app.schemas.learning import AcceptIn, EraseIn, RefreshIn, RejectIn, ResetIn, SnoozeIn
from app.services import learning as svc

router = APIRouter(prefix="/learning", tags=["learning"])

Reader = Annotated[User, Depends(require_permission("planning.view"))]
Editor = Annotated[User, Depends(require_permission("planning.edit"))]
AdminUser = Annotated[User, Depends(require_permission("planning.admin"))]
State = Literal["open", "accepted", "dismissed", "snoozed", "hidden", "all"]
SubjectType = Literal["instructor", "course", "section", "program", "user"]


async def _run[T](db: DB, op: Awaitable[T], *, commit: bool = True) -> T:
    try:
        out = await op
        if commit:
            await db.commit()
    except svc.LearningError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.detail) from exc
    return out


@router.post("/refresh")
async def refresh(body: RefreshIn, db: DB, _user: Editor) -> dict[str, Any]:
    return await _run(db, svc.refresh(db, body.term_id))


@router.get("/suggestions")
async def list_suggestions(
    db: DB,
    _user: Reader,
    term_id: int,
    person_id: int | None = None,
    course_id: int | None = None,
    state: State = "open",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict[str, Any]]:
    # priors are (re)computed on read when the evidence changed: committed so the ids stay stable
    return await _run(
        db, svc.suggestions(db, term_id, person_id=person_id, course_id=course_id, state=state, limit=limit)
    )


@router.get("/priors")
async def list_priors(
    db: DB,
    _user: Reader,
    term_id: int,
    subject_type: SubjectType | None = None,
    subject_id: int | None = None,
) -> list[dict[str, Any]]:
    key = str(subject_id) if subject_id is not None else None
    return await _run(db, svc.priors_for(db, term_id, subject_type, key))


@router.post("/suggestions/{prior_id}/accept", status_code=201)
async def accept(prior_id: int, body: AcceptIn, db: DB, user: Editor) -> dict[str, Any]:
    return await _run(db, svc.accept(db, prior_id, user, weight=body.weight, kind=body.kind))


@router.post("/suggestions/{prior_id}/reject")
async def reject(prior_id: int, body: RejectIn, db: DB, user: Editor) -> dict[str, Any]:
    return await _run(db, svc.reject(db, prior_id, user, reason=body.reason))


@router.post("/suggestions/{prior_id}/snooze")
async def snooze(prior_id: int, body: SnoozeIn, db: DB, user: Editor) -> dict[str, Any]:
    return await _run(db, svc.snooze(db, prior_id, user, until=body.until))


@router.get("/memory/summary")
async def memory_summary(db: DB, _user: Reader, term_id: int | None = None) -> dict[str, Any]:
    return await _run(db, svc.memory_summary(db, term_id))


@router.post("/reset", status_code=201)
async def reset(body: ResetIn, db: DB, user: AdminUser) -> dict[str, Any]:
    return await _run(db, svc.reset(db, user, scope=body.scope, value=body.value, reason=body.reason))


@router.get("/resets")
async def list_resets(db: DB, _user: AdminUser) -> list[dict[str, Any]]:
    return await _run(db, svc.list_resets(db), commit=False)


@router.post("/resets/{reset_id}/undo")
async def undo_reset(reset_id: int, db: DB, user: AdminUser) -> dict[str, Any]:
    return await _run(db, svc.undo_reset(db, reset_id, user))


@router.post("/purge")
async def purge(db: DB, _user: AdminUser) -> dict[str, int]:
    return await _run(db, svc.purge_expired(db))


@router.post("/erase", status_code=201)
async def erase(body: EraseIn, db: DB, user: AdminUser) -> dict[str, Any]:
    return await _run(db, svc.erase_person(db, user, instructor_id=body.instructor_id, reason=body.reason))
