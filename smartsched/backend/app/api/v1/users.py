"""User management (``setup.users``). Hashes never leave the server; passwords are write-only.

CRBS parity extras (username, role_id, department, constraints, CSV import, reset tokens) are documented
in docs/CRBS_PARITY.md §2.2; import / constraints / reset tokens live in ``app/api/v1/roles.py``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, func, select, update

from app.api.deps import DB, UsersAdmin
from app.core.security import hash_password
from app.importers import normalize as n
from app.models import ConstraintRow, Program, Role, RoomAcl, ScheduleRun, User, UserConstraint
from app.models.catalog import Room
from app.schemas.users import PasswordIn, UserAdminOut, UserCreate, UserUpdate
from app.services.bookings_perms import set_user_role

router = APIRouter(prefix="/users", tags=["users"])


async def user_out(db: DB, u: User) -> UserAdminOut:
    d = UserAdminOut.model_validate(u)
    d.has_password = bool(u.password_hash)
    d.displayname = u.full_name
    if u.role_id is not None:
        role = await db.get(Role, u.role_id)
        d.role_name = role.name if role else None
    if u.department_id is not None:
        dep = await db.get(Program, u.department_id)
        d.department_name = dep.name if dep else None
    return d


async def _user(db: DB, user_id: int) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    return u


async def _other_active_admins(db: DB, user_id: int) -> int:
    q = select(func.count(User.id)).where(User.role == "ADMIN", User.is_active.is_(True), User.id != user_id)
    return int((await db.execute(q)).scalar_one())


async def resolve_role(db: DB, role_id: int | None, code: str | None) -> Role:
    if role_id is not None:
        role = await db.get(Role, role_id)
    else:
        role = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
    if role is None:
        raise HTTPException(422, f"unknown role {role_id or code}")
    return role


async def check_department(db: DB, department_id: int | None) -> None:
    if department_id is not None and await db.get(Program, department_id) is None:
        raise HTTPException(422, f"unknown department {department_id}")


async def _check_unique(db: DB, user_id: int | None, email: str | None, username: str | None) -> None:
    if email:
        q = select(User.id).where(User.email == email)
        if user_id is not None:
            q = q.where(User.id != user_id)
        if (await db.execute(q)).scalar_one_or_none() is not None:
            raise HTTPException(409, f"a user with e-mail {email} already exists")
    if username:
        q = select(User.id).where(User.username == username)
        if user_id is not None:
            q = q.where(User.id != user_id)
        if (await db.execute(q)).scalar_one_or_none() is not None:
            raise HTTPException(409, f"a user with username {username} already exists")


@router.get("", response_model=list[UserAdminOut])
async def list_users(db: DB, _: UsersAdmin) -> list[UserAdminOut]:
    return [await user_out(db, u) for u in (await db.execute(select(User).order_by(User.id))).scalars()]


@router.get("/search")
async def search_users(
    db: DB,
    _: UsersAdmin,
    q: str | None = None,
    role_id: int | None = None,
    department_id: int | None = None,
    enabled: bool | None = None,
    sort: str = "username",
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """CRBS ``Users::index`` filters: search over username/names/e-mail (Turkish-insensitive), role,
    department; sort by username, displayname, lastlogin, enabled, role or department."""
    query = select(User)
    if role_id is not None:
        query = query.where(User.role_id == role_id)
    if department_id is not None:
        query = query.where(User.department_id == department_id)
    if enabled is not None:
        query = query.where(User.is_active.is_(enabled))
    users = list((await db.execute(query)).scalars())
    if q and q.strip():
        needle = n.tr_casefold(q)
        users = [
            u
            for u in users
            if any(needle in n.tr_casefold(x) for x in (u.username, u.email, u.firstname, u.lastname, u.full_name) if x)
        ]
    keys = {
        "username": lambda u: n.tr_casefold(u.username or u.email or ""),
        "displayname": lambda u: n.tr_casefold(u.full_name or ""),
        "lastlogin": lambda u: (u.last_login_at is None, u.last_login_at or 0),
        "enabled": lambda u: (not u.is_active,),
        "role": lambda u: u.role or "",
        "department": lambda u: u.department_id or 0,
    }
    desc = sort.startswith("-")
    users.sort(key=keys.get(sort.lstrip("-"), keys["username"]), reverse=desc)  # type: ignore[arg-type]
    page = users[offset : offset + max(1, min(limit, 500))]
    return {"total": len(users), "limit": limit, "offset": offset, "items": [await user_out(db, u) for u in page]}


@router.post("", response_model=UserAdminOut, status_code=201)
async def create_user(body: UserCreate, db: DB, _: UsersAdmin) -> UserAdminOut:
    await _check_unique(db, None, body.email, body.username)
    await check_department(db, body.department_id)
    role = await resolve_role(db, body.role_id, body.role)
    u = User(
        email=body.email,
        username=body.username,
        full_name=body.displayname or body.full_name,
        firstname=body.firstname,
        lastname=body.lastname,
        ext=body.ext,
        department_id=body.department_id,
        is_active=body.is_active,
        force_password_reset=bool(body.force_password_reset),
        password_hash=hash_password(body.password) if body.password else None,
    )
    set_user_role(u, role)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return await user_out(db, u)


@router.get("/{user_id}", response_model=UserAdminOut)
async def get_user(user_id: int, db: DB, _: UsersAdmin) -> UserAdminOut:
    return await user_out(db, await _user(db, user_id))


@router.put("/{user_id}", response_model=UserAdminOut)
async def update_user(user_id: int, body: UserUpdate, db: DB, me: UsersAdmin) -> UserAdminOut:
    u = await _user(db, user_id)
    data = body.model_dump(exclude_unset=True)
    new_role: Role | None = None
    if data.get("role_id") is not None or data.get("role") is not None:
        new_role = await resolve_role(db, data.get("role_id"), data.get("role"))
    demote = (new_role is not None and new_role.code != "ADMIN") or data.get("is_active") is False
    if u.role == "ADMIN" and demote and not await _other_active_admins(db, u.id):
        raise HTTPException(409, "cannot demote or deactivate the last active admin")
    await _check_unique(db, u.id, data.get("email"), data.get("username"))
    if "department_id" in data:
        await check_department(db, data["department_id"])
    password = data.pop("password", None)
    data.pop("role", None)
    data.pop("role_id", None)
    if "displayname" in data:
        data["full_name"] = data.pop("displayname")
    for k, v in data.items():
        if v is not None or k in {"full_name", "firstname", "lastname", "ext", "department_id", "username"}:
            setattr(u, k, v)
    if new_role is not None:
        set_user_role(u, new_role)
    if password:
        u.password_hash = hash_password(password)
    await db.commit()
    await db.refresh(u)
    return await user_out(db, u)


@router.post("/{user_id}/password", response_model=UserAdminOut)
async def set_password(user_id: int, body: PasswordIn, db: DB, _: UsersAdmin) -> UserAdminOut:
    """Set / reset a user's password (admin action; the old password is not needed)."""
    u = await _user(db, user_id)
    u.password_hash = hash_password(body.password)
    await db.commit()
    await db.refresh(u)
    return await user_out(db, u)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: DB, me: UsersAdmin) -> None:
    u = await _user(db, user_id)
    if u.id == me.id:
        raise HTTPException(409, "you cannot delete your own account")
    if u.role == "ADMIN" and u.is_active and not await _other_active_admins(db, u.id):
        raise HTTPException(409, "cannot delete the last active admin")
    # keep the user's runs and rules; only drop the authorship link (FKs have no ON DELETE)
    await db.execute(update(ScheduleRun).where(ScheduleRun.created_by == u.id).values(created_by=None))
    await db.execute(update(ConstraintRow).where(ConstraintRow.created_by == u.id).values(created_by=None))
    # CRBS Users_model::Delete: ACL entries, constraints and room ownership go; bookings keep their history
    await db.execute(delete(RoomAcl).where(RoomAcl.context_type == "user", RoomAcl.context_id == u.id))
    await db.execute(delete(UserConstraint).where(UserConstraint.user_id == u.id))
    await db.execute(update(Room).where(Room.owner_user_id == u.id).values(owner_user_id=None))
    await db.delete(u)
    await db.commit()
