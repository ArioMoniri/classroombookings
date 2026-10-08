"""Departments (CRBS ``Departments``). A department is a ``programs`` row (docs/CRBS_PARITY.md §2.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select, update

from app.api.deps import DB, CurrentUser, require_permission
from app.importers import normalize as n
from app.models import Booking, BookingSeries, ExamRequest, Program, RoomAcl, Section, User
from app.schemas.crbs import DepartmentIn, DepartmentOut, DepartmentUpdate

router = APIRouter(prefix="/departments", tags=["departments"])
DeptAdmin = Annotated[User, Depends(require_permission("setup.departments"))]


async def _out(db: DB, p: Program) -> DepartmentOut:
    d = DepartmentOut.model_validate(p)
    d.user_count = int((await db.execute(select(func.count(User.id)).where(User.department_id == p.id))).scalar_one())
    return d


async def _get(db: DB, dep_id: int) -> Program:
    p = await db.get(Program, dep_id)
    if p is None:
        raise HTTPException(404, "department not found")
    return p


def _canonical(name: str) -> str:
    parsed = n.canon_program(name)
    if parsed is None:
        raise HTTPException(422, "department name is empty")
    return parsed.canonical


@router.get("", response_model=list[DepartmentOut])
async def list_departments(db: DB, _: CurrentUser, q: str | None = None) -> list[DepartmentOut]:
    rows = list((await db.execute(select(Program))).scalars())
    if q:
        needle = n.tr_casefold(q)
        rows = [p for p in rows if needle in n.tr_casefold(p.name)]
    rows.sort(key=lambda p: n.tr_casefold(p.name))
    return [await _out(db, p) for p in rows]


@router.post("", response_model=DepartmentOut, status_code=201)
async def create_department(body: DepartmentIn, db: DB, _: DeptAdmin) -> DepartmentOut:
    canon = _canonical(body.name)
    if (await db.execute(select(Program.id).where(Program.canonical_name == canon))).scalar_one_or_none():
        raise HTTPException(409, f"department {body.name} already exists")
    parsed = n.canon_program(body.name)
    p = Program(
        name=body.name,
        canonical_name=canon,
        description=body.description,
        icon=body.icon,
        is_evening=bool(parsed and parsed.is_evening),
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return await _out(db, p)


@router.put("/{dep_id}", response_model=DepartmentOut)
async def update_department(dep_id: int, body: DepartmentUpdate, db: DB, _: DeptAdmin) -> DepartmentOut:
    p = await _get(db, dep_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        canon = _canonical(data["name"])
        clash = (
            await db.execute(select(Program.id).where(Program.canonical_name == canon, Program.id != p.id))
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(409, f"department {data['name']} already exists")
        p.name, p.canonical_name = data["name"], canon
    for k in ("description", "icon"):
        if k in data:
            setattr(p, k, data[k])
    await db.commit()
    await db.refresh(p)
    return await _out(db, p)


@router.delete("/{dep_id}", status_code=204)
async def delete_department(dep_id: int, db: DB, _: DeptAdmin) -> None:
    """CRBS: members lose the department, department ACLs go. Programmes used by imported sections or exam
    requests are kept (a re-import would recreate them)."""
    p = await _get(db, dep_id)
    used = (await db.execute(select(func.count(Section.id)).where(Section.program_id == p.id))).scalar_one()
    used += (await db.execute(select(func.count(ExamRequest.id)).where(ExamRequest.program_id == p.id))).scalar_one()
    if used:
        raise HTTPException(409, f"{p.name} is used by {used} imported section(s)/exam request(s)")
    await db.execute(update(User).where(User.department_id == p.id).values(department_id=None))
    await db.execute(update(Booking).where(Booking.department_id == p.id).values(department_id=None))
    await db.execute(update(BookingSeries).where(BookingSeries.department_id == p.id).values(department_id=None))
    await db.execute(delete(RoomAcl).where(RoomAcl.context_type == "department", RoomAcl.context_id == p.id))
    await db.delete(p)
    await db.commit()
