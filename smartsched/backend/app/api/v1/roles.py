"""Roles and permissions (``setup.roles``), per-user booking constraints, user CSV import, user search and
one-time password reset tokens (``setup.users``). CRBS: ``Roles``, ``Users::{import,edit}``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, func, select

from app.api.deps import DB, UsersAdmin, require_permission
from app.api.v1.users import guard_privileged
from app.models import Permission, Program, Role, RoomAcl, User, UserConstraint
from app.schemas.crbs import ConstraintsIO, ConstraintValue, RoleIn, RoleOut, RoleUpdate
from app.services.bookings_perms import (
    LIMIT_KEYS,
    PERMISSION_NAMES,
    forget_access,
    grouped_permissions,
    missing_permissions,
    role_permission_names,
)
from app.services.bookings_users import ImportDefaults, import_users_csv, issue_reset_token

router = APIRouter(tags=["roles"])
RolesAdmin = Annotated[User, Depends(require_permission("setup.roles"))]


async def _no_escalation(db: DB, me: User, names: Iterable[str], what: str = "grant these permissions") -> None:
    """403 unless ``me`` holds every permission in ``names`` (no-escalation rule, user decision 2026-10-08)."""
    missing = await missing_permissions(db, me, names)
    if missing:
        raise HTTPException(403, f"to {what} you need permissions you do not hold: {', '.join(missing)}")


async def _perms_by_name(db: DB, names: list[str]) -> list[Permission]:
    unknown = sorted(set(names) - PERMISSION_NAMES)
    if unknown:
        raise HTTPException(422, f"unknown permissions: {', '.join(unknown)}")
    if not names:
        return []
    return list((await db.execute(select(Permission).where(Permission.name.in_(names)))).scalars())


async def _role_out(db: DB, role: Role, with_users: bool = False) -> RoleOut:
    count = (await db.execute(select(func.count(User.id)).where(User.role_id == role.id))).scalar_one()
    out = RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        max_active_bookings=role.max_active_bookings,
        range_min=role.range_min,
        range_max=role.range_max,
        recur_max_instances=role.recur_max_instances,
        permissions=sorted(p.name for p in role.permissions),
        user_count=int(count),
    )
    if with_users:
        rows = (
            await db.execute(select(User).where(User.role_id == role.id).order_by(User.username, User.email))
        ).scalars()
        out.users = [{"id": u.id, "username": u.username, "email": u.email, "displayname": u.full_name} for u in rows]
    return out


async def _role(db: DB, role_id: int) -> Role:
    role = await db.get(Role, role_id)
    if role is None:
        raise HTTPException(404, "role not found")
    return role


@router.get("/permissions")
async def list_permissions(db: DB, _: RolesAdmin) -> dict[str, Any]:
    return grouped_permissions(list((await db.execute(select(Permission))).scalars()))


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(db: DB, _: RolesAdmin) -> list[RoleOut]:
    return [await _role_out(db, r) for r in (await db.execute(select(Role).order_by(Role.name))).scalars()]


@router.post("/roles", response_model=RoleOut, status_code=201)
async def create_role(body: RoleIn, db: DB, me: RolesAdmin) -> RoleOut:
    if (await db.execute(select(Role.id).where(Role.name == body.name))).scalar_one_or_none() is not None:
        raise HTTPException(409, f"a role named {body.name} already exists")
    role = Role(**body.model_dump(exclude={"permissions"}))
    perms = await _perms_by_name(db, body.permissions)  # 422 on unknown names first
    await _no_escalation(db, me, body.permissions)
    role.permissions = perms
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return await _role_out(db, role)


@router.get("/roles/{role_id}", response_model=RoleOut)
async def get_role(role_id: int, db: DB, _: RolesAdmin) -> RoleOut:
    return await _role_out(db, await _role(db, role_id), with_users=True)


@router.put("/roles/{role_id}", response_model=RoleOut)
async def update_role(role_id: int, body: RoleUpdate, db: DB, me: RolesAdmin) -> RoleOut:
    role = await _role(db, role_id)
    await _no_escalation(db, me, role_permission_names(role), what="edit this role")
    data = body.model_dump(exclude_unset=True)
    perms = data.pop("permissions", None)
    if perms is not None:
        if role.code == "ADMIN" and set(perms) != PERMISSION_NAMES:
            raise HTTPException(409, "the Administrator role keeps every permission (lock-out guard)")
        new_perms = await _perms_by_name(db, perms)  # 422 on unknown names first
        await _no_escalation(db, me, perms)
        role.permissions = new_perms
    if "name" in data and data["name"] != role.name:
        clash = (await db.execute(select(Role.id).where(Role.name == data["name"], Role.id != role.id))).scalar()
        if clash is not None:
            raise HTTPException(409, f"a role named {data['name']} already exists")
    for k, v in data.items():
        if k == "name" and v is None:
            continue
        setattr(role, k, v)
    await db.commit()
    await db.refresh(role)
    return await _role_out(db, role)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(role_id: int, db: DB, me: RolesAdmin) -> None:
    """CRBS ``Roles_model::delete``: members lose the role, the role's ACL entries go."""
    role = await _role(db, role_id)
    if role.code == "ADMIN":
        raise HTTPException(409, "the Administrator role cannot be deleted")
    await _no_escalation(db, me, role_permission_names(role), what="delete this role")
    for u in (await db.execute(select(User).where(User.role_id == role.id))).scalars():
        u.role_id = None
        u.role = "NONE"
        forget_access(u)
    await db.execute(delete(RoomAcl).where(RoomAcl.context_type == "role", RoomAcl.context_id == role.id))
    await db.delete(role)
    await db.commit()


# --- users: constraints, search, import, reset token ---------------------------------------------


async def _user(db: DB, user_id: int) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    return u


def _constraints_out(row: UserConstraint | None) -> ConstraintsIO:
    out: dict[str, ConstraintValue] = {}
    for k in LIMIT_KEYS:
        kind = getattr(row, f"{k}_type") if row is not None else "R"
        value = getattr(row, f"{k}_value") if row else None
        out[k] = ConstraintValue.model_construct(type=cast(Any, kind), value=value)
    return ConstraintsIO(**out)


@router.get("/users/{user_id}/constraints", response_model=ConstraintsIO)
async def get_constraints(user_id: int, db: DB, _: UsersAdmin) -> ConstraintsIO:
    await _user(db, user_id)
    return _constraints_out(await db.get(UserConstraint, user_id))


@router.put("/users/{user_id}/constraints", response_model=ConstraintsIO)
async def put_constraints(user_id: int, body: ConstraintsIO, db: DB, _: UsersAdmin) -> ConstraintsIO:
    await _user(db, user_id)
    row = await db.get(UserConstraint, user_id)
    if row is None:
        row = UserConstraint(user_id=user_id)
        db.add(row)
    sent = body.model_dump(exclude_unset=True)
    for k in LIMIT_KEYS:
        if k not in sent:
            continue
        v: ConstraintValue = getattr(body, k)
        setattr(row, f"{k}_type", v.type)
        setattr(row, f"{k}_value", v.value if v.type == "U" else None)
    await db.commit()
    return _constraints_out(row)


@router.post("/users/import")
async def import_users(
    db: DB,
    me: UsersAdmin,
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    role_id: int | None = Form(default=None),
    department_id: int | None = Form(default=None),
    enabled: bool = Form(default=True),
    force_password_reset: bool = Form(default=False),
) -> dict[str, Any]:
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV larger than 5 MB")
    default_role = await db.get(Role, role_id) if role_id is not None else None
    if role_id is not None and default_role is None:
        raise HTTPException(422, f"unknown role {role_id}")
    await guard_privileged(db, me, default_role)
    if department_id is not None and await db.get(Program, department_id) is None:
        raise HTTPException(422, f"unknown department {department_id}")
    res = await import_users_csv(
        db,
        data,
        ImportDefaults(
            password=password or None,
            role_id=role_id,
            department_id=department_id,
            enabled=enabled,
            force_password_reset=force_password_reset,
        ),
        actor=me,
    )
    await db.commit()
    return {"created": res.created, "results": res.results}


@router.post("/users/{user_id}/reset-token")
async def reset_token(user_id: int, db: DB, me: UsersAdmin) -> dict[str, Any]:
    """One-time reset code. Shown here when it could not be e-mailed (no SMTP / no address), never both."""
    u = await _user(db, user_id)
    await guard_privileged(db, me, target=u)
    issued = await issue_reset_token(db, u, me)
    await db.commit()
    return {
        "user_id": u.id,
        "expires_at": issued.expires_at,
        "emailed": issued.emailed,
        "token": None if issued.emailed else issued.token,
    }
