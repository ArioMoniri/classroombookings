"""A4 KVKK (docs/product/booking-enhancements.md §4.7; service: :mod:`app.services.kvkk`).

Signed-in user:

* ``GET  /me/privacy`` -- current notice (my language, else Turkish), ``needs_ack``, my consents, my requests;
* ``POST /me/privacy/ack`` ``{notice_id}``;
* ``POST /me/consents/{purpose}`` / ``DELETE /me/consents/{purpose}`` (``sms``, ``photo``, ``calendar_sync``,
  ``ai_personal``);
* ``POST /me/data-requests`` ``{kind: export|erase|rectify|info, note}``; ``GET /me/data-requests``;
  ``GET /me/data-requests/{id}/download`` (the export zip, 7 days).

No sign-in: ``GET /public/privacy-notice?lang=`` (the notice the login page links to).

Administrators: ``setup.users`` for the request queue (``GET /admin/dsr?status=open|all|OPEN|IN_PROGRESS|DONE|REFUSED``,
default ``open`` = OPEN + IN_PROGRESS, ``all`` = every queued request; ``POST /admin/dsr/{id}/complete``,
``POST /admin/dsr/{id}/refuse``); ``setup.settings`` for ``GET/PUT /admin/retention``, ``POST /admin/retention/run``,
``/admin/privacy-notices`` (drafts, publish) and ``GET /admin/kvkk/inventory``.

``PUT /admin/retention/{data_class}`` 422s (backend asks batch 3): ``detail = {code, field, message, message_en,
message_tr, errors: [...], ...}``, every error in ``errors`` with the same keys, the first on top. Codes:
``unknown_class`` (field ``data_class``; ``allowed`` = the classes with a policy), ``retain_days`` (not a whole
number of days or over 36 500; ``floor_days``, ``max_days``), ``below_floor`` (field ``retain_days``;
``floor_days``), ``action`` (``allowed``), ``enabled``, ``legal_hold``, ``legal_hold_reason``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, require_permission
from app.importers import normalize as n
from app.models import User
from app.models.base import utcnow
from app.models.kvkk import PrivacyNotice
from app.services import audit
from app.services import kvkk as svc

me_router = APIRouter(prefix="/me", tags=["kvkk"])
public_router = APIRouter(prefix="/public", tags=["kvkk"])
admin_router = APIRouter(prefix="/admin", tags=["kvkk"])
SettingsAdmin = Annotated[User, Depends(require_permission("setup.settings"))]
UsersAdmin = Annotated[User, Depends(require_permission("setup.users"))]


def _err(exc: svc.KvkkError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


class AckIn(BaseModel):
    notice_id: int


class RequestIn(BaseModel):
    kind: str
    note: str | None = Field(default=None, max_length=2000)


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)


class RetentionIn(BaseModel):
    """Read by :func:`app.services.kvkk.update_policy` (not by pydantic), so a wrong value answers 422 with a stable
    ``code`` + ``field`` and TR/EN messages instead of a validation list: ``retain_days`` (365, "1.095", "365 gün"),
    ``action`` (delete / anonymise, "SİL", "Anonimleştir"), ``enabled`` / ``legal_hold`` (true / false, "evet" /
    "hayır"), ``legal_hold_reason`` (text)."""

    retain_days: Any = None
    action: Any = None
    enabled: Any = None
    legal_hold: Any = None
    legal_hold_reason: Any = None


class NoticeIn(BaseModel):
    language: str = "tr"
    title: str = Field(min_length=1, max_length=255)
    body_md: str = Field(min_length=1, max_length=100_000)
    version: int | None = None


# --------------------------------------------------------------------------------------------------- me


@me_router.get("/privacy")
async def my_privacy(db: DB, user: CurrentUser) -> dict[str, Any]:
    notice = await svc.current_notice(db, user.language)
    return {
        "notice": svc.notice_out(notice) if notice else None,
        "needs_ack": await svc.needs_ack(db, user),
        "consents": await svc.consents_of(db, user.id),
        "requests": [svc.dsr_out(r) for r in await svc.mine(db, user)],
        "due_days": svc.DUE_DAYS,
    }


@me_router.post("/privacy/ack")
async def ack_notice(body: AckIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    try:
        row = await svc.ack(db, user, body.notice_id)
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    await db.commit()
    return {"notice_id": row.notice_id, "acked_at": row.acked_at.isoformat()}


@me_router.post("/consents/{purpose}")
async def grant_consent(purpose: str, db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    try:
        await svc.grant(db, user, purpose)
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    await db.commit()
    return await svc.consents_of(db, user.id)


@me_router.delete("/consents/{purpose}")
async def withdraw_consent(purpose: str, db: DB, user: CurrentUser) -> dict[str, Any]:
    try:
        out = await svc.withdraw(db, user, purpose)
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    await db.commit()
    return {**out, "consents": await svc.consents_of(db, user.id)}


@me_router.post("/data-requests", status_code=201)
async def create_request(body: RequestIn, db: DB, user: CurrentUser) -> dict[str, Any]:
    try:
        r = await svc.create_request(db, user, body.kind, n.clean_text(body.note) if body.note else None)
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    await db.commit()
    return svc.dsr_out(r)


@me_router.get("/data-requests")
async def my_requests(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    return [svc.dsr_out(r) for r in await svc.mine(db, user)]


@me_router.get("/data-requests/{request_id}/download")
async def download(request_id: int, db: DB, user: CurrentUser) -> Response:
    try:
        data = await svc.export_zip(db, user, request_id)
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    await db.commit()
    stamp = utcnow().strftime("%Y%m%d")
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="smartsched-verilerim-{stamp}.zip"',
            "Cache-Control": "no-store",
        },
    )


# --------------------------------------------------------------------------------------------------- public


@public_router.get("/privacy-notice")
async def public_notice(db: DB, lang: str = "tr") -> dict[str, Any]:
    notice = await svc.current_notice(db, lang)
    if notice is None:
        raise HTTPException(404, "not found")
    return svc.notice_out(notice)


# --------------------------------------------------------------------------------------------------- admin


@admin_router.get("/dsr")
async def dsr_queue(
    db: DB,
    _: UsersAdmin,
    status: Annotated[
        str | None,
        Query(
            description="open (default: OPEN + IN_PROGRESS) | all | OPEN | IN_PROGRESS | DONE | REFUSED "
            "(statuses in any case); anything else answers 422 code=status with `allowed`"
        ),
    ] = "open",
) -> list[dict[str, Any]]:
    """The erase / rectify / info queue by due date (exports are self-service and never queued)."""
    now = utcnow()
    try:
        rows = await svc.queue(db, status)
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    return [svc.dsr_out(r, now, admin=True) for r in rows]


@admin_router.post("/dsr/{request_id}/complete")
async def dsr_complete(request_id: int, body: DecisionIn, db: DB, admin: UsersAdmin) -> dict[str, Any]:
    try:
        r = await svc.complete(db, admin, request_id, n.clean_text(body.note) if body.note else None)
    except svc.KvkkError as exc:
        await db.rollback()
        raise _err(exc) from exc
    await db.commit()
    return svc.dsr_out(r, admin=True)


@admin_router.post("/dsr/{request_id}/refuse")
async def dsr_refuse(request_id: int, body: DecisionIn, db: DB, admin: UsersAdmin) -> dict[str, Any]:
    try:
        r = await svc.refuse(db, admin, request_id, n.clean_text(body.reason) or "" if body.reason else "")
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    await db.commit()
    return svc.dsr_out(r, admin=True)


@admin_router.get("/retention")
async def get_retention(db: DB, _: SettingsAdmin) -> list[dict[str, Any]]:
    rows = await svc.ensure_policies(db)
    await db.commit()
    return [svc.policy_out(p) for p in rows]


@admin_router.put("/retention/{data_class}")
async def put_retention(data_class: str, body: RetentionIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    try:
        p = await svc.update_policy(db, admin, data_class, body.model_dump(exclude_unset=True))
    except svc.KvkkError as exc:
        raise _err(exc) from exc
    await db.commit()
    return svc.policy_out(p)


@admin_router.post("/retention/run")
async def run_retention(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    out = await svc.purge_expired(db)
    await db.commit()
    return out


@admin_router.get("/kvkk/inventory")
async def kvkk_inventory(db: DB, _: SettingsAdmin) -> dict[str, Any]:
    out = await svc.inventory(db)
    await db.commit()
    return out


async def _notice(db: DB, notice_id: int, *, draft: bool) -> PrivacyNotice:
    row = await db.get(PrivacyNotice, notice_id)
    if row is None:
        raise HTTPException(404, {"code": "not_found", "message": "notice not found", "message_tr": "metin bulunamadı"})
    if draft and row.published_at is not None:
        raise HTTPException(
            409,
            {
                "code": "published",
                "message": "a published notice is never edited; write a new version",
                "message_tr": "yayımlanmış metin değiştirilmez; yeni sürüm yazın",
            },
        )
    return row


@admin_router.get("/privacy-notices")
async def list_notices(db: DB, _: SettingsAdmin) -> list[dict[str, Any]]:
    q = select(PrivacyNotice).order_by(PrivacyNotice.version.desc(), PrivacyNotice.language)
    return [svc.notice_out(x) for x in (await db.execute(q)).scalars()]


@admin_router.post("/privacy-notices", status_code=201)
async def create_notice(body: NoticeIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    if body.language not in ("tr", "en"):
        raise HTTPException(
            422, {"code": "language", "message": "language: tr or en", "message_tr": "dil: tr ya da en"}
        )
    version = body.version
    if version is None:
        version = int((await db.execute(select(func.max(PrivacyNotice.version)))).scalar() or 0) + 1
    clash = (
        await db.execute(
            select(PrivacyNotice).where(PrivacyNotice.version == version, PrivacyNotice.language == body.language)
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(
            409, {"code": "exists", "message": "this version exists in this language", "message_tr": "bu sürüm var"}
        )
    row = PrivacyNotice(
        version=version,
        language=body.language,
        title=n.clean_text(body.title) or body.title,
        body_md=body.body_md,
        created_by=admin.id,
        created_at=utcnow(),
    )
    db.add(row)
    await db.flush()
    await audit.record(
        db,
        "kvkk.notice_create",
        "privacy_notice",
        row.id,
        after={"version": version, "language": body.language},
        actor=admin,
    )
    await db.commit()
    return svc.notice_out(row)


@admin_router.put("/privacy-notices/{notice_id}")
async def update_notice(notice_id: int, body: NoticeIn, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    row = await _notice(db, notice_id, draft=True)
    row.title, row.body_md, row.updated_at = n.clean_text(body.title) or body.title, body.body_md, utcnow()
    await audit.record(db, "kvkk.notice_update", "privacy_notice", row.id, after={"version": row.version}, actor=admin)
    await db.commit()
    return svc.notice_out(row)


@admin_router.post("/privacy-notices/{notice_id}/publish")
async def publish_notice(notice_id: int, db: DB, admin: SettingsAdmin) -> dict[str, Any]:
    row = await _notice(db, notice_id, draft=True)
    row.published_at = utcnow()
    await audit.record(
        db,
        "kvkk.notice_publish",
        "privacy_notice",
        row.id,
        after={"version": row.version, "language": row.language},
        actor=admin,
    )
    await db.commit()
    return svc.notice_out(row)


@admin_router.delete("/privacy-notices/{notice_id}", status_code=204)
async def delete_notice(notice_id: int, db: DB, admin: SettingsAdmin) -> None:
    row = await _notice(db, notice_id, draft=True)
    await db.delete(row)
    await audit.record(
        db, "kvkk.notice_delete", "privacy_notice", notice_id, before={"version": row.version}, actor=admin
    )
    await db.commit()
