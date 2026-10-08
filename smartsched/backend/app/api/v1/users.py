"""User management for admins. Hashes never leave the server; passwords are write-only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, update

from app.api.deps import DB, Admin
from app.core.security import hash_password
from app.models import ConstraintRow, ScheduleRun, User
from app.schemas.users import PasswordIn, UserAdminOut, UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _out(u: User) -> UserAdminOut:
    d = UserAdminOut.model_validate(u)
    d.has_password = bool(u.password_hash)
    return d


async def _user(db: DB, user_id: int) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    return u


async def _other_active_admins(db: DB, user_id: int) -> int:
    q = select(func.count(User.id)).where(User.role == "ADMIN", User.is_active.is_(True), User.id != user_id)
    return int((await db.execute(q)).scalar_one())


@router.get("", response_model=list[UserAdminOut])
async def list_users(db: DB, _: Admin) -> list[UserAdminOut]:
    return [_out(u) for u in (await db.execute(select(User).order_by(User.id))).scalars()]


@router.post("", response_model=UserAdminOut, status_code=201)
async def create_user(body: UserCreate, db: DB, _: Admin) -> UserAdminOut:
    if (await db.execute(select(User.id).where(User.email == body.email))).scalar_one_or_none() is not None:
        raise HTTPException(409, f"a user with e-mail {body.email} already exists")
    u = User(
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        is_active=body.is_active,
        password_hash=hash_password(body.password),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return _out(u)


@router.get("/{user_id}", response_model=UserAdminOut)
async def get_user(user_id: int, db: DB, _: Admin) -> UserAdminOut:
    return _out(await _user(db, user_id))


@router.put("/{user_id}", response_model=UserAdminOut)
async def update_user(user_id: int, body: UserUpdate, db: DB, me: Admin) -> UserAdminOut:
    u = await _user(db, user_id)
    data = body.model_dump(exclude_unset=True)
    demote = data.get("role") not in (None, "ADMIN") or data.get("is_active") is False
    if u.role == "ADMIN" and demote and not await _other_active_admins(db, u.id):
        raise HTTPException(409, "cannot demote or deactivate the last active admin")
    if "email" in data and data["email"] != u.email:
        clash = (await db.execute(select(User.id).where(User.email == data["email"]))).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(409, f"a user with e-mail {data['email']} already exists")
    password = data.pop("password", None)
    for k, v in data.items():
        if v is not None or k == "full_name":
            setattr(u, k, v)
    if password:
        u.password_hash = hash_password(password)
    await db.commit()
    await db.refresh(u)
    return _out(u)


@router.post("/{user_id}/password", response_model=UserAdminOut)
async def set_password(user_id: int, body: PasswordIn, db: DB, _: Admin) -> UserAdminOut:
    """Set / reset a user's password (admin action; the old password is not needed)."""
    u = await _user(db, user_id)
    u.password_hash = hash_password(body.password)
    await db.commit()
    await db.refresh(u)
    return _out(u)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: DB, me: Admin) -> None:
    u = await _user(db, user_id)
    if u.id == me.id:
        raise HTTPException(409, "you cannot delete your own account")
    if u.role == "ADMIN" and u.is_active and not await _other_active_admins(db, u.id):
        raise HTTPException(409, "cannot delete the last active admin")
    # keep the user's runs and rules; only drop the authorship link (FKs have no ON DELETE)
    await db.execute(update(ScheduleRun).where(ScheduleRun.created_by == u.id).values(created_by=None))
    await db.execute(update(ConstraintRow).where(ConstraintRow.created_by == u.id).values(created_by=None))
    await db.delete(u)
    await db.commit()
