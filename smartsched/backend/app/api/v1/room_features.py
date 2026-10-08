"""P10 typed room features (docs/product/wave1-api.md §1).

* ``/room-admin/features``: the feature catalogue (``rooms.features`` or ``setup.rooms``), its impact on the
  solver tags, adopting the existing room tags, the optional template and the bulk CSV editor.
* ``/room-admin/rooms/{id}/features``: one room's typed values.
* ``GET /rooms/facets``: filterable features with counts over the rooms the caller may view (any signed-in user).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select

from app.api.deps import DB, CurrentAccess, require_permission
from app.models import RoomCustomField, User
from app.models.catalog import Room
from app.schemas.features import BulkReport, FeatureDeleteOut, FeatureIn, FeatureOut, RoomFeaturesOut
from app.services import bookings as booking_svc
from app.services import rooms_features as feat

router = APIRouter(prefix="/room-admin", tags=["room-features"])
facets_router = APIRouter(tags=["room-features"])
FeaturesAdmin = Annotated[User, Depends(require_permission("rooms.features", "setup.rooms"))]
CSV_MAX_BYTES = 2 * 1024 * 1024


def _err(exc: feat.FeatureError) -> HTTPException:
    return HTTPException(exc.status, exc.as_detail())


def _spec(body: FeatureIn) -> feat.FieldSpec:
    return feat.FieldSpec(**body.model_dump())


async def _field(db: DB, fid: int) -> RoomCustomField:
    f = await db.get(RoomCustomField, fid)
    if f is None:
        raise HTTPException(404, "feature not found")
    return f


async def _room(db: DB, room_id: int) -> Room:
    r = await db.get(Room, room_id)
    if r is None:
        raise HTTPException(404, "room not found")
    return r


async def _room_out(db: DB, room: Room) -> RoomFeaturesOut:
    fields = await feat.catalogue(db)
    vals = (await feat.room_values(db, [room], fields))[room.id]
    return RoomFeaturesOut(
        room_id=room.id,
        code=room.code,
        tags=list(room.tags or []),
        values={str(fid): v for fid, v in vals.items()},
        display={f.name: feat.display(f, vals[f.id]) for f in fields},
    )


@router.get("/features", response_model=list[FeatureOut])
async def list_features(db: DB, _: FeaturesAdmin) -> list[dict[str, Any]]:
    return [feat.field_out(f) for f in await feat.catalogue(db)]


@router.post("/features", response_model=FeatureOut, status_code=201)
async def create_feature(body: FeatureIn, db: DB, me: FeaturesAdmin) -> dict[str, Any]:
    try:
        f = await feat.create_field(db, _spec(body), me)
    except feat.FeatureError as exc:
        raise _err(exc) from exc
    await db.commit()
    await db.refresh(f)
    return feat.field_out(f)


@router.post("/features/adopt-tags", response_model=list[FeatureOut])
async def adopt_tags(db: DB, me: FeaturesAdmin) -> list[dict[str, Any]]:
    """One yes/no feature per room tag (PC, TIP, ...) that no feature maps yet; the solver keeps its tags."""
    created = await feat.adopt_tags(db, me)
    await db.commit()
    return [feat.field_out(f) for f in created]


@router.post("/features/template", response_model=list[FeatureOut])
async def apply_template(db: DB, me: FeaturesAdmin) -> list[dict[str, Any]]:
    """The suggested catalogue (projeksiyon, akıllı tahta, PC sayısı, ...), only on request; existing names skipped."""
    created = await feat.apply_template(db, me)
    await db.commit()
    return [feat.field_out(f) for f in created]


@router.post("/features/bulk-values", response_model=BulkReport)
async def bulk_values(
    db: DB,
    me: FeaturesAdmin,
    file: UploadFile = File(...),
    dry_run: bool = Query(default=True),
    skip_errors: bool = Query(default=False),
) -> dict[str, Any]:
    """CSV (UTF-8 or Windows-1254, ``;`` or ``,``): room code, then one column per feature name."""
    data = await file.read(CSV_MAX_BYTES + 1)
    if len(data) > CSV_MAX_BYTES:
        raise HTTPException(413, "CSV larger than 2 MB")
    try:
        out = await feat.bulk_values(db, data, me, dry_run=dry_run, skip_errors=skip_errors)
    except feat.FeatureError as exc:
        await db.rollback()
        raise _err(exc) from exc
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return out


@router.get("/features/{fid}/impact")
async def feature_impact(fid: int, db: DB, _: FeaturesAdmin) -> dict[str, Any]:
    f = await _field(db, fid)
    if not f.solver_tag:
        return {"tag": None, "rooms": [], "room_count": 0, "requests_needing": 0}
    return await feat.impact(db, f.solver_tag, exclude_field_id=f.id)


@router.put("/features/{fid}", response_model=FeatureOut)
async def update_feature(fid: int, body: FeatureIn, db: DB, me: FeaturesAdmin, confirm: bool = False) -> dict[str, Any]:
    f = await _field(db, fid)
    try:
        await feat.update_field(db, f, _spec(body), me, confirm=confirm)
    except feat.FeatureError as exc:
        await db.rollback()
        raise _err(exc) from exc
    await db.commit()
    f = await _field(db, fid)
    await db.refresh(f)
    return feat.field_out(f)


@router.delete("/features/{fid}", response_model=FeatureDeleteOut)
async def delete_feature(fid: int, db: DB, me: FeaturesAdmin, confirm: bool = False) -> dict[str, Any]:
    f = await _field(db, fid)
    try:
        out = await feat.delete_field(db, f, me, confirm=confirm)
    except feat.FeatureError as exc:
        await db.rollback()
        raise _err(exc) from exc
    await db.commit()
    return out


@router.get("/rooms/{room_id}/features", response_model=RoomFeaturesOut)
async def get_room_features(room_id: int, db: DB, _: FeaturesAdmin) -> RoomFeaturesOut:
    return await _room_out(db, await _room(db, room_id))


@router.put("/rooms/{room_id}/features", response_model=RoomFeaturesOut)
async def put_room_features(room_id: int, body: dict[str, Any], db: DB, me: FeaturesAdmin) -> RoomFeaturesOut:
    """``{field id or name: value}``; yes/no accepts evet/hayır/var/yok, numbers accept ``4,5``, options their
    text (Turkish-case-insensitive). All or nothing."""
    room = await _room(db, room_id)
    try:
        await feat.set_values(db, room, body, me)
    except feat.FeatureError as exc:
        await db.rollback()
        raise _err(exc) from exc
    await db.commit()
    return await _room_out(db, await _room(db, room_id))


@facets_router.get("/rooms/facets", response_model=list[FeatureOut])
async def facets(db: DB, access: CurrentAccess) -> list[dict[str, Any]]:
    """Filterable features with value counts over the rooms the caller may view (role or room ACL ``room.view``);
    non-public features only for feature administrators."""
    rooms = [r for r in (await db.execute(select(Room))).scalars() if access.can_view_room(r)]
    hide_ungrouped = await booking_svc.ungrouped_rooms_hidden(db)
    rooms = [r for r in rooms if r.is_bookable and not (hide_ungrouped and r.room_group_id is None)]
    admin = access.can("rooms.features") or access.can("setup.rooms")
    return await feat.facets(db, rooms, include_private=admin)
