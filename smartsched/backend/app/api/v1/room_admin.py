"""Room administration for bookings (CRBS ``setup/rooms/{Groups,Rooms,Fields,Acl}``).

Room master data (code, capacity, tags) stays on ``/rooms``; this module adds groups and ordering, owner,
location, icon, notes, photo, custom fields and the room access-control list."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, func, select

from app.api.deps import DB, require_permission
from app.core.config import get_settings
from app.importers import normalize as n
from app.models import (
    Building,
    Permission,
    Program,
    Role,
    RoomAcl,
    RoomCustomField,
    RoomCustomFieldOption,
    RoomCustomFieldValue,
    RoomGroup,
    User,
)
from app.models.catalog import Room
from app.schemas.crbs import (
    AclIn,
    AclOut,
    AclUpdate,
    CustomFieldIn,
    CustomFieldOut,
    OrderIn,
    RoomAdminOut,
    RoomBookingUpdate,
    RoomGroupIn,
    RoomGroupOut,
    RoomGroupUpdate,
)
from app.services import rooms_features as features
from app.services.bookings_collation import tr_sort_key
from app.services.bookings_perms import BOOKING_SCOPE_GROUPS, perm_group

router = APIRouter(prefix="/room-admin", tags=["room-admin"])
RoomsAdmin = Annotated[User, Depends(require_permission("setup.rooms"))]
AclAdmin = Annotated[User, Depends(require_permission("setup.rooms_acl"))]


# --- groups ----------------------------------------------------------------------------------------


def room_order(r: Room) -> tuple[Any, ...]:
    """CRBS ``Rooms_model::get_in_group``: rooms.pos, then rooms.name in Turkish alphabetical order."""
    return (r.pos or 0, tr_sort_key(r.display_name or r.code), r.code)


def group_order(g: RoomGroup) -> tuple[Any, ...]:
    """CRBS ``Room_groups_model``: rg.pos, then rg.name in Turkish alphabetical order."""
    return (g.pos or 0, tr_sort_key(g.name), g.id)


async def _group_out(db: DB, g: RoomGroup) -> RoomGroupOut:
    members = sorted((await db.execute(select(Room).where(Room.room_group_id == g.id))).scalars(), key=room_order)
    ids = [r.id for r in members]
    return RoomGroupOut(id=g.id, name=g.name, description=g.description, pos=g.pos, room_count=len(ids), room_ids=ids)


async def _group(db: DB, gid: int) -> RoomGroup:
    g = await db.get(RoomGroup, gid)
    if g is None:
        raise HTTPException(404, "room group not found")
    return g


async def _assign(db: DB, g: RoomGroup, room_ids: list[int]) -> None:
    """``Groups::update_room_groups``: listed rooms join the group, other members leave it."""
    for r in (await db.execute(select(Room).where(Room.room_group_id == g.id))).scalars():
        if r.id not in room_ids:
            r.room_group_id = None
            r.room_group = None  # audit B14: no stale free-text group label
    for rid in room_ids:
        member = await db.get(Room, rid)
        if member is None:
            raise HTTPException(422, f"room {rid} not found")
        member.room_group_id = g.id
        member.room_group = g.name


@router.get("/groups", response_model=list[RoomGroupOut])
async def list_groups(db: DB, _: RoomsAdmin) -> list[RoomGroupOut]:
    groups = sorted((await db.execute(select(RoomGroup))).scalars(), key=group_order)
    return [await _group_out(db, g) for g in groups]


@router.post("/groups", response_model=RoomGroupOut, status_code=201)
async def create_group(body: RoomGroupIn, db: DB, _: RoomsAdmin) -> RoomGroupOut:
    pos = (await db.execute(select(func.max(RoomGroup.pos)))).scalar() or 0
    g = RoomGroup(name=body.name, description=body.description, pos=pos + 1)
    db.add(g)
    await db.flush()
    if body.room_ids is not None:
        await _assign(db, g, body.room_ids)
    await db.commit()
    return await _group_out(db, g)


@router.post("/groups/from-buildings", response_model=list[RoomGroupOut])
async def groups_from_buildings(db: DB, _: RoomsAdmin) -> list[RoomGroupOut]:
    """One group per building (A, B, C, D blocks) holding that building's ungrouped rooms."""
    out = []
    for b in (await db.execute(select(Building).order_by(Building.code))).scalars():
        rooms = list(
            (await db.execute(select(Room).where(Room.building_id == b.id, Room.room_group_id.is_(None)))).scalars()
        )
        if not rooms:
            continue
        name = (n.clean_text(b.name) or b.code)[:32]
        g = (await db.execute(select(RoomGroup).where(RoomGroup.name == name))).scalar_one_or_none()
        if g is None:
            pos = (await db.execute(select(func.max(RoomGroup.pos)))).scalar() or 0
            g = RoomGroup(name=name, pos=pos + 1)
            db.add(g)
            await db.flush()
        for r in rooms:
            r.room_group_id, r.room_group = g.id, g.name
        out.append(g)
    await db.commit()
    return [await _group_out(db, g) for g in out]


@router.put("/groups/order", response_model=list[RoomGroupOut])
async def order_groups(body: OrderIn, db: DB, _: RoomsAdmin) -> list[RoomGroupOut]:
    for pos, gid in enumerate(body.ids):
        (await _group(db, gid)).pos = pos
    await db.commit()
    return await list_groups(db, _)


@router.put("/groups/{gid}", response_model=RoomGroupOut)
async def update_group(gid: int, body: RoomGroupUpdate, db: DB, _: RoomsAdmin) -> RoomGroupOut:
    g = await _group(db, gid)
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        g.name = n.clean_text(data["name"]) or g.name
    if "description" in data:
        g.description = data["description"]
    if body.room_ids is not None:
        await _assign(db, g, body.room_ids)
    await db.commit()
    return await _group_out(db, g)


@router.delete("/groups/{gid}", status_code=204)
async def delete_group(gid: int, db: DB, _: RoomsAdmin) -> None:
    g = await _group(db, gid)
    for r in (await db.execute(select(Room).where(Room.room_group_id == g.id))).scalars():
        r.room_group_id = None
        r.room_group = None  # audit B14
    await db.execute(delete(RoomAcl).where(RoomAcl.entity_type == "room_group", RoomAcl.entity_id == g.id))
    await db.delete(g)
    await db.commit()


# --- rooms (booking properties) ---------------------------------------------------------------------


async def _field_values(db: DB, room_id: int) -> dict[str, Any]:
    """``{field_id: value}`` for every typed feature (P10, ``app.services.rooms_features``): CHECKBOX/BOOLEAN bool,
    SELECT option id, NUMBER number, MULTISELECT option ids, TEXT text."""
    room = await db.get(Room, room_id)
    return await features.legacy_values(db, room) if room is not None else {}


async def _room_out(db: DB, r: Room) -> RoomAdminOut:
    g = await db.get(RoomGroup, r.room_group_id) if r.room_group_id else None
    o = await db.get(User, r.owner_user_id) if r.owner_user_id else None
    return RoomAdminOut(
        id=r.id,
        code=r.code,
        display_name=r.display_name,
        capacity=r.capacity or 0,
        is_bookable=r.is_bookable,
        room_group_id=r.room_group_id,
        room_group=g.name if g else None,
        owner_user_id=r.owner_user_id,
        owner_name=(o.full_name or o.username or o.email) if o else None,
        location=r.location,
        icon=r.icon,
        notes=r.notes,
        photo_url=r.photo_url,
        pos=r.pos or 0,
        fields=await _field_values(db, r.id),
    )


async def _room(db: DB, room_id: int) -> Room:
    r = await db.get(Room, room_id)
    if r is None:
        raise HTTPException(404, "room not found")
    return r


@router.get("/rooms", response_model=list[RoomAdminOut])
async def list_rooms(db: DB, _: RoomsAdmin, room_group_id: int | None = None) -> list[RoomAdminOut]:
    q = select(Room)
    if room_group_id is not None:
        q = (
            q.where(Room.room_group_id == (room_group_id or None))
            if room_group_id
            else q.where(Room.room_group_id.is_(None))
        )
    # CRBS ``Rooms_model::get_all``: rg.pos, rooms.pos, rooms.name (ungrouped rooms first, MySQL NULLs first)
    groups = {g.id: group_order(g) for g in (await db.execute(select(RoomGroup))).scalars()}
    rooms = sorted(
        (await db.execute(q)).scalars(),
        key=lambda r: (r.room_group_id is not None, groups.get(r.room_group_id or 0, ()), room_order(r)),
    )
    return [await _room_out(db, r) for r in rooms]


async def _owner_acl(db: DB, room: Room, owner_id: int | None, previous: int | None) -> None:
    """CRBS migration 2025-04 ``migrate_room_owners``: an owner may cancel others' single bookings in the room."""
    if previous and previous != owner_id:
        for acl in (
            await db.execute(
                select(RoomAcl).where(
                    RoomAcl.entity_type == "room",
                    RoomAcl.entity_id == room.id,
                    RoomAcl.context_type == "user",
                    RoomAcl.context_id == previous,
                )
            )
        ).scalars():
            if [p.name for p in acl.permissions] == ["book_single.cancel_other_booking"]:
                await db.delete(acl)
    if owner_id and owner_id != previous:
        perm = (
            await db.execute(select(Permission).where(Permission.name == "book_single.cancel_other_booking"))
        ).scalar_one()
        acl = RoomAcl(entity_type="room", entity_id=room.id, context_type="user", context_id=owner_id)
        acl.permissions = [perm]
        db.add(acl)


@router.put("/rooms/order", response_model=list[RoomAdminOut])
async def order_rooms(body: OrderIn, db: DB, _: RoomsAdmin) -> list[RoomAdminOut]:
    rooms = []
    for pos, rid in enumerate(body.ids):
        r = await _room(db, rid)
        r.pos = pos
        rooms.append(r)
    await db.commit()
    return [await _room_out(db, r) for r in rooms]


@router.put("/rooms/{room_id}", response_model=RoomAdminOut)
async def update_room(room_id: int, body: RoomBookingUpdate, db: DB, _: RoomsAdmin) -> RoomAdminOut:
    r = await _room(db, room_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("room_group_id") is not None:
        g = await _group(db, data["room_group_id"])
        r.room_group = g.name
    elif "room_group_id" in data:  # audit B14: clearing the group clears the legacy free-text label too
        r.room_group = None
    if "owner_user_id" in data:
        if data["owner_user_id"] is not None and await db.get(User, data["owner_user_id"]) is None:
            raise HTTPException(422, f"user {data['owner_user_id']} not found")
        await _owner_acl(db, r, data["owner_user_id"], r.owner_user_id)
    for k in ("location", "icon", "notes", "display_name"):
        if k in data:
            data[k] = n.clean_text(data[k]) if data[k] is not None else None
    for k, v in data.items():
        if k == "display_name" and not v:
            continue
        if k == "is_bookable" and v is None:
            continue
        setattr(r, k, v)
    await db.commit()
    await db.refresh(r)
    return await _room_out(db, r)


@router.post("/rooms/{room_id}/photo", response_model=RoomAdminOut)
async def upload_photo(room_id: int, db: DB, _: RoomsAdmin, file: UploadFile = File(...)) -> RoomAdminOut:
    r = await _room(db, room_id)
    ext = Path(file.filename or "photo.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".gif"}:  # CRBS setup/rooms/Rooms: jpg|jpeg|png|gif
        raise HTTPException(400, "unsupported image type (jpg, png, gif)")
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "image larger than 10 MB")
    from app.core.images import ImageError, check_image, sanitize_image

    problem = check_image(data, ext, file.content_type)  # review MINOR 14: the bytes must be that image
    if problem:
        raise HTTPException(400, problem)
    try:  # audit B2: decoded and re-encoded (≤ 1600 px), so only real pixels are ever served
        data, ext = sanitize_image(data)
    except ImageError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    target = Path(get_settings().upload_dir) / "rooms"
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob(f"{r.id}.*"):
        old.unlink(missing_ok=True)
    (target / f"{r.id}{ext}").write_bytes(data)
    r.photo_url = f"/uploads/rooms/{r.id}{ext}"
    await db.commit()
    return await _room_out(db, r)


@router.delete("/rooms/{room_id}/photo", response_model=RoomAdminOut)
async def delete_photo(room_id: int, db: DB, _: RoomsAdmin) -> RoomAdminOut:
    r = await _room(db, room_id)
    for old in (Path(get_settings().upload_dir) / "rooms").glob(f"{r.id}.*"):
        old.unlink(missing_ok=True)
    r.photo_url = None
    await db.commit()
    return await _room_out(db, r)


# --- custom fields ------------------------------------------------------------------------------------


def _field_out(f: RoomCustomField) -> CustomFieldOut:
    return CustomFieldOut(
        id=f.id, name=f.name, type=f.type, options=[{"id": o.id, "value": o.value} for o in f.options]
    )


async def _field(db: DB, fid: int) -> RoomCustomField:
    f = await db.get(RoomCustomField, fid)
    if f is None:
        raise HTTPException(404, "field not found")
    return f


async def _mirror(db: DB, room_id: int) -> None:
    """``rooms.custom_fields`` (by field name) and the solver tags of typed features (``rooms.tags``)."""
    r = await db.get(Room, room_id)
    if r is not None:
        await features.mirror(db, r)


@router.get("/fields", response_model=list[CustomFieldOut])
async def list_fields(db: DB, _: RoomsAdmin) -> list[CustomFieldOut]:
    rows = (await db.execute(select(RoomCustomField).order_by(RoomCustomField.pos, RoomCustomField.name))).scalars()
    return [_field_out(f) for f in rows]


@router.post("/fields", response_model=CustomFieldOut, status_code=201)
async def create_field(body: CustomFieldIn, db: DB, _: RoomsAdmin) -> CustomFieldOut:
    f = RoomCustomField(name=body.name, type=body.type)
    f.options = (
        [RoomCustomFieldOption(value=v[:64], pos=i) for i, v in enumerate(body.options)]
        if body.type == "SELECT"
        else []
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return _field_out(f)


@router.put("/fields/{fid}", response_model=CustomFieldOut)
async def update_field(fid: int, body: CustomFieldIn, db: DB, _: RoomsAdmin) -> CustomFieldOut:
    """Options are matched by text so existing SELECT values survive a rename of other options."""
    f = await _field(db, fid)
    old_name = f.name
    old_by_value = {o.value: o for o in f.options}
    f.name, f.type = body.name, body.type
    new_opts = []
    if body.type == "SELECT":
        for i, v in enumerate(body.options):
            o = old_by_value.pop(v, None) or RoomCustomFieldOption(value=v[:64])
            o.pos = i
            new_opts.append(o)
    removed = {str(o.id) for o in old_by_value.values()}
    f.options = new_opts
    if removed or body.type != "SELECT":
        for fv in (
            await db.execute(select(RoomCustomFieldValue).where(RoomCustomFieldValue.field_id == f.id))
        ).scalars():
            if body.type == "SELECT" and fv.value in removed:
                fv.value = None
    await db.flush()
    room_ids = (
        await db.execute(select(RoomCustomFieldValue.room_id).where(RoomCustomFieldValue.field_id == f.id))
    ).scalars()
    for rid in set(room_ids):
        r = await db.get(Room, rid)
        if r is not None and old_name != f.name:
            r.custom_fields = {k: v for k, v in (r.custom_fields or {}).items() if k != old_name}
        await _mirror(db, rid)
    await db.commit()
    await db.refresh(f)
    return _field_out(f)


@router.delete("/fields/{fid}", status_code=204)
async def delete_field(fid: int, db: DB, _: RoomsAdmin) -> None:
    f = await _field(db, fid)
    room_ids = list(
        (await db.execute(select(RoomCustomFieldValue.room_id).where(RoomCustomFieldValue.field_id == f.id))).scalars()
    )
    name = f.name
    await db.delete(f)
    await db.flush()
    for rid in room_ids:
        r = await db.get(Room, rid)
        if r is not None and name in (r.custom_fields or {}):
            r.custom_fields = {k: v for k, v in r.custom_fields.items() if k != name}
    await db.commit()


@router.get("/rooms/{room_id}/fields")
async def get_room_fields(room_id: int, db: DB, _: RoomsAdmin) -> dict[str, Any]:
    await _room(db, room_id)
    return await _field_values(db, room_id)


@router.put("/rooms/{room_id}/fields")
async def put_room_fields(room_id: int, body: dict[str, Any], db: DB, me: RoomsAdmin) -> dict[str, Any]:
    """``{field_id: value}``: TEXT -> text, CHECKBOX -> bool, SELECT -> option id (or null); the typed features
    (P10) accept their values too. Written through ``rooms_features.set_values`` (tags mirrored, audited)."""
    room = await _room(db, room_id)
    for key in body:
        try:
            int(key)
        except ValueError as exc:
            raise HTTPException(422, f"field id {key!r} is not a number") from exc
        await _field(db, int(key))
    try:
        await features.set_values(db, room, body, me)
    except features.FeatureError as exc:
        await db.rollback()
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return await _field_values(db, room_id)


# --- ACL -----------------------------------------------------------------------------------------------


async def _acl_out(db: DB, a: RoomAcl) -> AclOut:
    entity: Any = await db.get(Room if a.entity_type == "room" else RoomGroup, a.entity_id)
    ctx: Any = await db.get({"user": User, "role": Role, "department": Program}[a.context_type], a.context_id)
    if a.context_type == "user" and ctx is not None:
        label = ctx.username or ctx.email
        if ctx.full_name:
            label = f"{label} ({ctx.full_name})"
    else:
        label = getattr(ctx, "name", None)
    return AclOut(
        id=a.id,
        entity_type=a.entity_type,
        entity_id=a.entity_id,
        entity_label=(entity.display_name if a.entity_type == "room" else entity.name) if entity else None,
        context_type=a.context_type,
        context_id=a.context_id,
        context_label=label,
        permissions=sorted(p.name for p in a.permissions),
    )


async def _acl_perms(db: DB, names: list[str]) -> list[Permission]:
    bad = [x for x in names if perm_group(x) not in BOOKING_SCOPE_GROUPS]
    if bad:
        raise HTTPException(422, f"only room/booking permissions can be granted on rooms: {', '.join(bad)}")
    rows = list((await db.execute(select(Permission).where(Permission.name.in_(names)))).scalars()) if names else []
    if len(rows) != len(set(names)):
        raise HTTPException(422, "unknown permission in list")
    return rows


@router.get("/acl", response_model=list[AclOut])
async def list_acl(db: DB, _: AclAdmin, entity_type: str | None = None, entity_id: int | None = None) -> list[AclOut]:
    q = select(RoomAcl).order_by(RoomAcl.id)
    if entity_type:
        q = q.where(RoomAcl.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(RoomAcl.entity_id == entity_id)
    return [await _acl_out(db, a) for a in (await db.execute(q)).scalars()]


@router.post("/acl", response_model=AclOut, status_code=201)
async def create_acl(body: AclIn, db: DB, _: AclAdmin) -> AclOut:
    if await db.get(Room if body.entity_type == "room" else RoomGroup, body.entity_id) is None:
        raise HTTPException(422, f"{body.entity_type} {body.entity_id} not found")
    if await db.get({"user": User, "role": Role, "department": Program}[body.context_type], body.context_id) is None:
        raise HTTPException(422, f"{body.context_type} {body.context_id} not found")
    a = RoomAcl(**body.model_dump(exclude={"permissions"}))
    a.permissions = await _acl_perms(db, body.permissions)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return await _acl_out(db, a)


@router.put("/acl/{acl_id}", response_model=AclOut)
async def update_acl(acl_id: int, body: AclUpdate, db: DB, _: AclAdmin) -> AclOut:
    a = await db.get(RoomAcl, acl_id)
    if a is None:
        raise HTTPException(404, "ACL entry not found")
    a.permissions = await _acl_perms(db, body.permissions)
    await db.commit()
    await db.refresh(a)
    return await _acl_out(db, a)


@router.delete("/acl/{acl_id}", status_code=204)
async def delete_acl(acl_id: int, db: DB, _: AclAdmin) -> None:
    a = await db.get(RoomAcl, acl_id)
    if a is None:
        raise HTTPException(404, "ACL entry not found")
    await db.delete(a)
    await db.commit()
