"""Learned suggestions with resettable memory (Phase 19 P19-L2..L4; docs/design/v2/phase19-suggestions.md).

==============================================================  ===============  ======================================
Route                                                           Permission       Notes
==============================================================  ===============  ======================================
``POST /learning/refresh`` {term_id?}                           planning.edit    extract + priors (audited)
``GET /learning/suggestions?term_id=&person_id=&course_id=``    planning.view    ``state`` open (default) / accepted /
                                                                                 dismissed / snoozed / hidden / all
``GET /learning/priors?term_id=&subject_type=&subject_id=``     planning.view    every prior with its evidence
``POST /learning/suggestions/{id}/accept`` {weight?, kind?,     planning.edit    one soft targeted LEARNED rule;
scope: term | persistent}                                                        persistent needs planning.admin
``POST /learning/suggestions/{id}/restore``                     planning.edit    undo reject / snooze / accept
``POST /learning/suggestions/{id}/reject`` {reason?}            planning.edit    -3 and hidden for the scope + term
``POST /learning/suggestions/{id}/snooze`` {until}              planning.edit    next_solve / P7D / next_term
``GET /learning/memory/summary?term_id=``                       planning.view    counts for Ayarlar › Öğrenme
``POST /learning/reset`` {scope, value, reason}                 planning.admin   person / term / all; audited
``GET /learning/resets``                                        planning.admin   "Son sıfırlamalar"
``POST /learning/resets/{id}/undo``                             planning.admin   within 30 days
``POST /learning/purge``                                        planning.admin   the daily purge, on demand; audited
``POST /learning/erase`` {instructor_id, reason}                planning.admin   KVKK erasure: immediate, no undo
``GET /learning/versions?term_id=``                             planning.view    AS-13 versions, diff, pin
``POST /learning/versions/{id}/revert``                         planning.admin   "Bu sürüme dön" (rules untouched)
``GET /learning/calibration``                                   planning.admin   Beta posterior per class + drafts
``POST /learning/calibration/apply`` {attribute, min_confidence} planning.admin  apply / clear a draft
``GET /learning/habits``                                        planning.view    RF-07 per-habit overrides
``PUT /learning/priors/{id}/habit`` {state, reason, value, weight} planning.admin disable / correct / tune / clear
``GET|PUT /learning/settings`` {nightly_refresh}                planning.admin   nightly refresh 03:15 on/off
==============================================================  ===============  ======================================

Nothing here applies a suggestion by itself; a memory reset removes learned memory only, never requests, runs,
bookings or accepted rules (and it is not a KVKK erasure: use ``/learning/erase``).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DB, require_permission
from app.models import User
from app.schemas.learning import AcceptIn, EraseIn, RefreshIn, RejectIn, ResetIn, SnoozeIn
from app.services import learning as svc
from app.services.audit import jsonable
from app.services.events import publish_event

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
async def refresh(body: RefreshIn, db: DB, user: Editor) -> dict[str, Any]:
    async def op() -> dict[str, Any]:
        if body.term_id is not None:  # AS-13: a term refresh records a learning version (and lifts a revert's pin)
            from app.services import learning_versions as lv

            out = await lv.refresh_term(db, body.term_id, actor=user)
        else:
            out = await svc.refresh(db, body.term_id)
        # who re-ran the extraction and what it produced (derived rows only: counts, no personal content)
        await publish_event(
            db, "learning.refresh", "learning", body.term_id, after=jsonable(out), actor=user, term_id=body.term_id
        )
        return out

    return await _run(db, op())


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
    if body.scope == "persistent":
        from app.services.bookings_perms import load_access

        if "planning.admin" not in (await load_access(db, user)).perms:
            raise HTTPException(403, "a persistent (Kalıcı) acceptance requires permission planning.admin")
    return await _run(db, svc.accept(db, prior_id, user, weight=body.weight, kind=body.kind, scope=body.scope))


@router.post("/suggestions/{prior_id}/restore")
async def restore(prior_id: int, db: DB, user: Editor) -> dict[str, Any]:
    """Undo the last decision: a dismissal or snooze, or an acceptance (its LEARNED rule is switched off)."""
    return await _run(db, svc.restore(db, prior_id, user))


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
async def purge(db: DB, user: AdminUser) -> dict[str, int]:
    async def op() -> dict[str, int]:
        totals = await svc.purge_expired(db)  # one learning.purge row per purged reset (no actor: the daily job)
        await publish_event(db, "learning.purge_run", "learning", None, after=dict(totals), actor=user)
        return totals

    return await _run(db, op())


@router.post("/erase", status_code=201)
async def erase(body: EraseIn, db: DB, user: AdminUser) -> dict[str, Any]:
    return await _run(db, svc.erase_person(db, user, instructor_id=body.instructor_id, reason=body.reason))


# ------------------------------------------------------------------------------------------------ AS-13 / RF-07


class HabitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: disabled | corrected | tuned; null clears the override
    state: Literal["disabled", "corrected", "tuned"] | None = None
    reason: str | None = Field(default=None, max_length=500)
    #: corrected: the right value (room id, building code, day, band ... in the habit's attribute)
    value: str | None = Field(default=None, max_length=64)
    #: tuned: the weight a later accept uses (1..5)
    weight: int | None = Field(default=None, ge=1, le=10)


class CalibrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute: str = Field(max_length=16)
    min_confidence: float | None = None


class LearningSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nightly_refresh: bool


async def _lv[T](db: DB, op: Awaitable[T]) -> T:
    from app.services import learning_versions as lv

    try:
        out = await op
        await db.commit()
    except (lv.VersionError, svc.LearningError) as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.detail) from exc
    return out


@router.get("/versions")
async def list_versions(db: DB, _user: Reader, term_id: int) -> dict[str, Any]:
    from app.services import learning_versions as lv

    return await lv.list_versions(db, term_id)


@router.post("/versions/{version_id}/revert")
async def revert_version(version_id: int, db: DB, user: AdminUser) -> dict[str, Any]:
    from app.services import learning_versions as lv

    return await _lv(db, lv.revert(db, version_id, user))


@router.get("/calibration")
async def calibration(db: DB, _user: AdminUser) -> dict[str, Any]:
    from app.services import learning_versions as lv

    return await lv.calibration(db)


@router.post("/calibration/apply")
async def apply_calibration(body: CalibrationIn, db: DB, user: AdminUser) -> dict[str, Any]:
    from app.services import learning_versions as lv

    return await _lv(db, lv.apply_calibration(db, body.attribute, body.min_confidence, user))


@router.get("/habits")
async def list_habits(db: DB, _user: Reader) -> list[dict[str, Any]]:
    from app.services import learning_versions as lv

    return await lv.list_habits(db)


@router.put("/priors/{prior_id}/habit")
async def set_habit(prior_id: int, body: HabitIn, db: DB, user: AdminUser) -> dict[str, Any]:
    from app.services import learning_versions as lv

    return await _lv(
        db,
        lv.set_habit(
            db, prior_id, state=body.state, actor=user, reason=body.reason, value=body.value, weight=body.weight
        ),
    )


@router.get("/settings")
async def get_learning_settings(db: DB, _user: AdminUser) -> dict[str, Any]:
    from app.services import learning_versions as lv

    return {"nightly_refresh": await lv.nightly_enabled(db), "nightly_at": "03:15 Europe/Istanbul"}


@router.put("/settings")
async def put_learning_settings(body: LearningSettingsIn, db: DB, user: AdminUser) -> dict[str, Any]:
    from app.models import Setting
    from app.services import learning_versions as lv

    before = await lv.nightly_enabled(db)
    row = await db.get(Setting, lv.NIGHTLY_KEY)
    if row is None:
        db.add(Setting(key=lv.NIGHTLY_KEY, value=str(body.nightly_refresh).lower(), is_secret=False))
    else:
        row.value = str(body.nightly_refresh).lower()
    await publish_event(
        db,
        "learning.settings",
        "setting",
        lv.NIGHTLY_KEY,
        before={"nightly_refresh": before},
        after={"nightly_refresh": body.nightly_refresh},
        actor=user,
    )
    await db.commit()
    return {"nightly_refresh": body.nightly_refresh, "nightly_at": "03:15 Europe/Istanbul"}
