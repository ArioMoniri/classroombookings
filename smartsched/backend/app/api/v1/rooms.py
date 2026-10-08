from __future__ import annotations

from pathlib import Path

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select

from app.api.deps import DB, Planner, Viewer, require_permission
from app.core.config import get_settings
from app.core.images import check_image
from app.core.safe_files import UnsafeFileError, read_upload
from app.importers import normalize as n
from app.models import Building, Room, RoomAcl, User
from app.schemas.catalog import BuildingIn, BuildingOut, RoomIn, RoomOut, RoomUpdate

PHOTO_MAX_BYTES = 10 * 1024 * 1024

router = APIRouter(tags=["rooms"])
#: CRBS ``setup/rooms/Rooms::add`` / ``delete``: a room administrator (``setup.rooms``) creates and deletes rooms
#: from Admin -> Rooms; the planning office keeps ``planning.edit`` (UI gap audit 2026-10-08 #4)
RoomsEditor = Annotated[User, Depends(require_permission("planning.edit", "setup.rooms"))]


@router.get("/buildings", response_model=list[BuildingOut])
async def list_buildings(db: DB, _: Viewer) -> list[Building]:
    return list((await db.execute(select(Building).order_by(Building.code))).scalars())


@router.post("/buildings", response_model=BuildingOut, status_code=201)
async def create_building(body: BuildingIn, db: DB, _: Planner) -> Building:
    b = Building(code=body.code.upper(), name=body.name)
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


@router.get("/rooms", response_model=list[RoomOut])
async def list_rooms(
    db: DB, _: Viewer, building: str | None = None, bookable: bool | None = None, search: str | None = None
) -> list[Room]:
    q = select(Room).order_by(Room.code)
    if building:
        q = q.where(Room.code.like(f"{building.upper()}%"))
    if bookable is not None:
        q = q.where(Room.is_bookable.is_(bookable))
    rooms = list((await db.execute(q)).scalars())
    if search:
        s = n.tr_casefold(search).replace(" ", "")
        rooms = [r for r in rooms if s in n.tr_casefold(r.code) or s in n.tr_casefold(r.display_name).replace(" ", "")]
    return rooms


@router.post("/rooms", response_model=RoomOut, status_code=201)
async def create_room(body: RoomIn, db: DB, _: RoomsEditor) -> Room:
    codes = n.parse_room_codes(body.code)
    code = codes[0] if codes else n.tr_upper(body.code).replace(" ", "")
    if (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "room code exists")
    data = body.model_dump()
    data["code"] = code
    data["display_name"] = body.display_name or n.display_room_code(code)
    if data.get("building_id") is None and code[:1].isalpha():
        b = (await db.execute(select(Building).where(Building.code == code[:1]))).scalar_one_or_none()
        if b is None:
            b = Building(code=code[:1], name=f"{code[:1]} Blok")
            db.add(b)
            await db.flush()
        data["building_id"] = b.id
    room = Room(**data)
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def _room(db: DB, room_id: int) -> Room:
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(404, "room not found")
    return room


@router.get("/rooms/{room_id}", response_model=RoomOut)
async def get_room(room_id: int, db: DB, _: Viewer) -> Room:
    return await _room(db, room_id)


@router.put("/rooms/{room_id}", response_model=RoomOut)
async def update_room(room_id: int, body: RoomUpdate, db: DB, _: Planner) -> Room:
    room = await _room(db, room_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(room, k, v)
    await db.commit()
    await db.refresh(room)
    return room


@router.delete("/rooms/{room_id}", status_code=204)
async def delete_room(room_id: int, db: DB, _: RoomsEditor) -> None:
    """Refused while bookings point at the room (audit B16: ``ON DELETE CASCADE`` would erase their history
    and nobody would be told); make the room not bookable instead, or cancel its bookings first."""
    from sqlalchemy import func

    from app.models import Booking

    room = await _room(db, room_id)
    rows = (
        await db.execute(
            select(Booking.status, func.count(Booking.id)).where(Booking.room_id == room.id).group_by(Booking.status)
        )
    ).all()
    counts = {st: int(c) for st, c in rows}
    if counts:
        active = counts.get("BOOKED", 0)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "room_has_bookings",
                "message": f"{room.display_name} has {sum(counts.values())} booking(s) ({active} active); "
                "set it not bookable instead of deleting it",
                "active_bookings": active,
                "bookings": sum(counts.values()),
            },
        )
    # CRBS ``Rooms_model::delete`` drops the room's ACL entries. SQLite gives the highest deleted id to the next
    # room, so a leftover row would hand this room's permissions to an unrelated new room.
    await db.execute(delete(RoomAcl).where(RoomAcl.entity_type == "room", RoomAcl.entity_id == room.id))
    await db.delete(room)
    await db.commit()


@router.post("/rooms/{room_id}/photo", response_model=RoomOut)
async def upload_photo(room_id: int, db: DB, _: Planner, file: UploadFile = File(...)) -> Room:
    room = await _room(db, room_id)
    ext = Path(file.filename or "photo.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise HTTPException(400, "unsupported image type")
    try:
        data = await read_upload(file, PHOTO_MAX_BYTES)
    except UnsafeFileError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    problem = check_image(data, ext, file.content_type)
    if problem:
        raise HTTPException(400, problem)
    target_dir = Path(get_settings().upload_dir) / "rooms"
    target_dir.mkdir(parents=True, exist_ok=True)
    for old in target_dir.glob(f"{room.id}.*"):
        old.unlink(missing_ok=True)
    target = target_dir / f"{room.id}{ext}"
    target.write_bytes(data)
    room.photo_url = f"/uploads/rooms/{room.id}{ext}"
    await db.commit()
    await db.refresh(room)
    return room
