"""Faculty-owned rooms (owner report 2026-11-02 item 2): academicians outside the Tıp (Medicine) faculty may not
reserve Tıp's classrooms; Tıp academicians may reserve rooms anywhere.

Design (the conventional "restricted to" field, generalised to any faculty):

* a room has an optional owner faculty (``rooms.owner_faculty_id``, alembic 0049). The room master's
  ``owner_faculty`` column and the room admin panel (``PUT /room-admin/rooms/{id}``) set it; the 2026 room master
  gives A 201, A 202 and A 203 (the ``TIP`` rooms of the weekly-grid headers) to the Tıp Fakültesi;
* a user's faculty is their department's faculty (``users.department_id`` -> ``programs.faculty_id``), which
  administrators set in Kullanıcılar / Bölümler;
* a room without an owner is open to every faculty; a room with an owner can be booked (or requested) only by
  members of that faculty. Administrators (the Administrator role, or any role holding ``setup.roles``) keep full
  access, also when they book for someone else;
* the booking API refuses with 403 ``room_faculty`` and a Turkish / English message; the free-room search leaves
  such rooms out for the user and the booking grid shows their slots as not permitted.

Rooms owned by another faculty than Tıp follow the same rule (none exist in the 2026 data).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Program
from app.models.catalog import Faculty, Room
from app.services.bookings_perms import Access, is_privileged_role

#: the canonical name (``normalize.canon_faculty``) of the medicine faculty the room master names
TIP_FACULTY_NAME = "Tıp Fakültesi"


def is_admin(access: Access) -> bool:
    """Administrators keep full access to faculty-owned rooms."""
    if is_privileged_role(access.role):
        return True
    return access.role is None and access.user.role == "ADMIN"


async def user_faculty_id(session: AsyncSession, access: Access) -> int | None:
    """The caller's faculty (their department's faculty), cached on the access object for the request."""
    cache = access.__dict__.get("_faculty_id", ...)
    if cache is not ...:
        return cache  # type: ignore[no-any-return]
    out: int | None = None
    dep_id = access.user.department_id
    if dep_id is not None:
        out = (await session.execute(select(Program.faculty_id).where(Program.id == dep_id))).scalar_one_or_none()
    access.__dict__["_faculty_id"] = out
    return out


async def allowed(session: AsyncSession, access: Access, room: Room) -> bool:
    """Whether the caller may book (or request) ``room`` as far as its owner faculty goes."""
    owner = room.owner_faculty_id
    if owner is None or is_admin(access):
        return True
    return await user_faculty_id(session, access) == owner


async def restricted_room_ids(session: AsyncSession, access: Access, rooms: list[Room]) -> set[int]:
    """The rooms of ``rooms`` the caller may not book because another faculty owns them."""
    if is_admin(access) or not any(r.owner_faculty_id for r in rooms):
        return set()
    mine = await user_faculty_id(session, access)
    return {r.id for r in rooms if r.owner_faculty_id is not None and r.owner_faculty_id != mine}


async def faculty_name(session: AsyncSession, faculty_id: int | None) -> str | None:
    if faculty_id is None:
        return None
    f = await session.get(Faculty, faculty_id)
    return f.name if f is not None else None


async def refusal(session: AsyncSession, access: Access, room: Room) -> dict[str, Any] | None:
    """``None`` when allowed, else the 403 detail (``code``, ``message``, ``message_tr``, ``message_en``)."""
    if await allowed(session, access, room):
        return None
    name = await faculty_name(session, room.owner_faculty_id) or "başka bir fakülte"
    tr = (
        f"{room.display_name} dersliği {name} dersliğidir; yalnızca {name} öğretim elemanları rezerve edebilir. "
        "Başka bir derslik seçin ya da yöneticinize başvurun."
    )
    en = (
        f"{room.display_name} belongs to {name}; only {name} academicians can reserve it. "
        "Choose another room or contact an administrator."
    )
    return {
        "code": "room_faculty",
        "message": en,
        "message_tr": tr,
        "message_en": en,
        "owner_faculty_id": room.owner_faculty_id,
        "owner_faculty": name,
    }


__all__ = [
    "TIP_FACULTY_NAME",
    "allowed",
    "faculty_name",
    "is_admin",
    "refusal",
    "restricted_room_ids",
    "user_faculty_id",
]
