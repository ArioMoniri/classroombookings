"""Season profiles and the season calendar (adaptive scheduling AS-03; ``app/services/seasons.py``).

=============================================================  ==========  ===========================================
Route                                                          Who         Notes
=============================================================  ==========  ===========================================
``GET /seasons/profiles``                                      PLANNER     built-ins + every version, weight keys,
                                                                           ``can_activate`` (the caller is an admin)
``POST /seasons/profiles``                                     PLANNER     a new draft (audited season_profile.create)
``PUT /seasons/profiles/{id}``                                 PLANNER     draft: in place; active: new draft version
``POST /seasons/profiles/{id}/activate``                       ADMIN       approve; the key's previous version retires
``POST /seasons/profiles/{id}/revert``                         ADMIN       "Geri al": the parent version is active again
``DELETE /seasons/profiles/{id}``                              PLANNER /   a draft is deleted (planner or admin), an
                                                               ADMIN       active one retired (admin only)
``GET /seasons/terms/{term_id}/periods``                       ADMIN       dated segments (weeks, holidays, admin)
``POST /seasons/terms/{term_id}/segments``                     ADMIN       admin segment (add/drop, midterm ...)
``PUT /seasons/segments/{id}`` / ``DELETE``                    ADMIN       edit / remove; approve a draft with status
=============================================================  ==========  ===========================================

AS20-F09 (FIX-G, owner's recommended option): "planner drafts, admin approves". PLANNER = ``planning.edit`` (or
``planning.admin``); ADMIN = ``planning.admin``. A planner's draft changes nothing until an admin activates it.

A profile never applies by itself: drafts are inert, and every run records the profile and weights it used
(``run.stats.profile`` / ``weights_source``).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from app.api.deps import DB, Admin, CurrentAccess, forbidden, perm
from app.models import Term, User
from app.models.seasons import SeasonSegment
from app.services import seasons as svc

router = APIRouter(prefix="/seasons", tags=["seasons"])

#: AS20-F09: drafts are a planner's tool; approving (activate / revert / retire) stays with ``planning.admin``
Drafter = Annotated[User, perm("planning.edit", "planning.admin")]


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str | None = None
    name_tr: str | None = None
    name_en: str | None = None
    applies_to: list[dict[str, Any]] | None = None
    solver_weights: dict[str, Any] | None = None
    booking_overlays: list[dict[str, Any]] | None = None
    peak_threshold_pct: int | None = None
    explanation: dict[str, Any] | None = None


class SegmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    week_from: int | None = None
    week_to: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    label_tr: str | None = None
    label_en: str | None = None
    status: str | None = None


async def _do[T](db: DB, op: Awaitable[T]) -> T:
    try:
        out = await op
        await db.commit()
    except svc.SeasonError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.as_detail()) from exc
    return out


@router.get("/profiles")
async def list_profiles(db: DB, _: Drafter, access: CurrentAccess) -> dict[str, Any]:
    return {**await svc.list_profiles(db), "can_activate": "planning.admin" in access.perms}


@router.post("/profiles", status_code=201)
async def create_profile(body: ProfileIn, db: DB, user: Drafter) -> dict[str, Any]:
    row = await _do(db, svc.create_profile(db, body.model_dump(exclude_none=True), actor=user))
    return svc.profile_out(row)


@router.put("/profiles/{profile_id}")
async def update_profile(profile_id: int, body: ProfileIn, db: DB, user: Drafter) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    data.pop("key", None)
    row = await _do(db, svc.update_profile(db, profile_id, data, actor=user))
    return svc.profile_out(row)


@router.post("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: int, db: DB, user: Admin) -> dict[str, Any]:
    return svc.profile_out(await _do(db, svc.activate_profile(db, profile_id, actor=user)))


@router.post("/profiles/{profile_id}/revert")
async def revert_profile(profile_id: int, db: DB, user: Admin) -> dict[str, Any]:
    return svc.profile_out(await _do(db, svc.revert_profile(db, profile_id, actor=user)))


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: int, db: DB, user: Drafter, access: CurrentAccess) -> Response:
    # a planner throws away a draft; retiring an active (or retired) version is an admin's approval step
    try:
        row = await svc.get_profile(db, profile_id)
    except svc.SeasonError as exc:
        raise HTTPException(exc.status, exc.as_detail()) from exc
    if row.status != "draft" and "planning.admin" not in access.perms:
        raise forbidden("planning.admin")
    await _do(db, svc.retire_profile(db, profile_id, actor=user))
    return Response(status_code=204)


@router.get("/terms/{term_id}/periods")
async def term_periods(term_id: int, db: DB, _: Admin) -> dict[str, Any]:
    try:
        return await svc.term_periods(db, term_id)
    except svc.SeasonError as exc:
        raise HTTPException(exc.status, exc.as_detail()) from exc


async def _segment_audit(db: DB, action: str, sg: SeasonSegment, user: Any, before: dict[str, Any] | None) -> None:
    from app.services.events import publish_event

    await publish_event(
        db,
        action,
        "season_segment",
        sg.id,
        before=before,
        after=svc.segment_out(sg) if action != "season_segment.delete" else None,
        actor=user,
        term_id=sg.term_id,
    )


@router.post("/terms/{term_id}/segments", status_code=201)
async def create_segment(term_id: int, body: SegmentIn, db: DB, user: Admin) -> dict[str, Any]:
    if await db.get(Term, term_id) is None:
        raise HTTPException(
            404, {"code": "term_not_found", "message_tr": "dönem bulunamadı", "message_en": "term not found"}
        )

    async def op() -> SeasonSegment:
        fields = svc.validate_segment(body.model_dump(exclude_unset=True))
        sg = SeasonSegment(term_id=term_id, created_by=user.id, **fields)
        db.add(sg)
        await db.flush()
        await _segment_audit(db, "season_segment.create", sg, user, None)
        return sg

    return svc.segment_out(await _do(db, op()))


@router.put("/segments/{segment_id}")
async def update_segment(segment_id: int, body: SegmentIn, db: DB, user: Admin) -> dict[str, Any]:
    sg = await db.get(SeasonSegment, segment_id)
    if sg is None:
        raise HTTPException(
            404, {"code": "segment_not_found", "message_tr": "parça bulunamadı", "message_en": "segment not found"}
        )

    async def op() -> SeasonSegment:
        before = svc.segment_out(sg)
        for k, v in svc.validate_segment(body.model_dump(exclude_unset=True), base=sg).items():
            setattr(sg, k, v)
        await db.flush()
        await _segment_audit(db, "season_segment.update", sg, user, before)
        return sg

    return svc.segment_out(await _do(db, op()))


@router.delete("/segments/{segment_id}", status_code=204)
async def delete_segment(segment_id: int, db: DB, user: Admin) -> Response:
    sg = await db.get(SeasonSegment, segment_id)
    if sg is None:
        raise HTTPException(
            404, {"code": "segment_not_found", "message_tr": "parça bulunamadı", "message_en": "segment not found"}
        )
    before = svc.segment_out(sg)
    await _segment_audit(db, "season_segment.delete", sg, user, before)
    await db.delete(sg)
    await db.commit()
    return Response(status_code=204)
