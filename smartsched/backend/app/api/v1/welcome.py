"""Welcome guide per role (WG-01…WG-03; docs/design/v3/welcome-guide.md §6.4; logic in ``app.services.welcome``).

Signed-in user (own state only):

* ``GET /welcome`` (``first_route``, ``kiosk``, ``embed``; ``preview=<audience>`` for administrators): audiences, the
  one automatic surface due now (``show``) and the sheet / tour / checklist / hints content;
* ``POST /welcome/events`` -> 204 (idempotent; unknown keys 422 with ``message_tr`` / ``message_en``);
* ``POST /welcome/restart``: sheet and tour back to ``shown``; the ``GET`` payload with the sheet as ``show``.

Administrators (``setup.settings`` or ``planning.admin``; every change audited):

* ``GET/PUT /welcome/settings`` (``welcome.settings_update``);
* ``GET/PUT /welcome/content/{audience}`` (``version`` -> 409 ``stale``; ``welcome.content_update``);
* ``POST /welcome/content/{audience}/reshow`` (``welcome.reshow``);
* ``GET /welcome/stats?days=7|30|90`` (aggregate; groups under ``min_cohort`` hidden; no per-person output).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentAccess, forbidden, require_permission
from app.models import User
from app.services import welcome as svc

router = APIRouter(prefix="/welcome", tags=["welcome"])

ADMIN_PERMS = ("setup.settings", "planning.admin")
WelcomeAdmin = Annotated[User, Depends(require_permission(*ADMIN_PERMS))]


def _http(exc: svc.WelcomeError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


class EventIn(BaseModel):
    guide_key: str = Field(max_length=64)
    event: str = Field(max_length=16)
    step: int | None = None
    item: str | None = Field(default=None, max_length=64)


class SettingsIn(BaseModel):
    enabled: bool | None = None
    sheet: bool | None = None
    tour: bool | None = None
    checklist: bool | None = None
    hints: bool | None = None
    hints_for_all: bool | None = None
    min_cohort: int | None = None


class ContentIn(BaseModel):
    version: int = Field(ge=0)
    #: locale -> field -> text (``null`` or empty = back to the product copy)
    fields: dict[str, dict[str, str | None]] = Field(default_factory=dict, max_length=2)
    #: "show again" to this audience after saving ("Güncellendi")
    reshow: bool = False


@router.get("")
async def get_welcome(
    db: DB,
    access: CurrentAccess,
    first_route: Annotated[str | None, Query(max_length=512)] = None,
    kiosk: bool = False,
    embed: bool = False,
    preview: Annotated[str | None, Query(max_length=32)] = None,
) -> dict[str, Any]:
    try:
        if preview is not None:
            if not any(p in access.perms for p in ADMIN_PERMS):
                raise forbidden(*ADMIN_PERMS)
            preview = svc.check_audience(preview)
        out = await svc.payload(
            db, access.user, access, first_route=first_route, kiosk=kiosk, embed=embed, preview=preview
        )
    except svc.WelcomeError as exc:
        raise _http(exc) from exc
    await db.commit()  # the checklist snapshot, when a new item got done
    return out


@router.post("/events", status_code=204)
async def post_event(body: EventIn, db: DB, access: CurrentAccess) -> Response:
    try:
        await svc.record_event(db, access.user, access, body.guide_key, body.event, step=body.step, item=body.item)
    except svc.WelcomeError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await db.commit()
    return Response(status_code=204)


@router.post("/restart")
async def post_restart(db: DB, access: CurrentAccess) -> dict[str, Any]:
    out = await svc.restart(db, access.user, access)
    await db.commit()
    return out


@router.get("/settings")
async def get_settings(db: DB, _: WelcomeAdmin) -> dict[str, Any]:
    return await svc.settings_out(db)


@router.put("/settings")
async def put_settings(body: SettingsIn, db: DB, user: WelcomeAdmin) -> dict[str, Any]:
    try:
        out = await svc.put_settings(db, user, body.model_dump(exclude_none=True))
    except svc.WelcomeError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await db.commit()
    return out


@router.get("/content/{audience}")
async def get_content(audience: str, db: DB, _: WelcomeAdmin) -> dict[str, Any]:
    try:
        return await svc.content_out(db, audience)
    except svc.WelcomeError as exc:
        raise _http(exc) from exc


@router.put("/content/{audience}")
async def put_content(audience: str, body: ContentIn, db: DB, user: WelcomeAdmin) -> dict[str, Any]:
    try:
        out = await svc.put_content(db, user, audience, body.version, body.fields, reshow_after=body.reshow)
    except svc.WelcomeError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await db.commit()
    return out


@router.post("/content/{audience}/reshow")
async def post_reshow(audience: str, db: DB, user: WelcomeAdmin) -> dict[str, Any]:
    try:
        out = await svc.reshow(db, user, audience)
    except svc.WelcomeError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await db.commit()
    return out


@router.get("/stats")
async def get_stats(db: DB, _: WelcomeAdmin, days: int = 30) -> dict[str, Any]:
    try:
        return await svc.stats(db, days)
    except svc.WelcomeError as exc:
        raise _http(exc) from exc
