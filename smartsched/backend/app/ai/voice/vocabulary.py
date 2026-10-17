"""The recogniser's vocabulary hint (VO-03, ``ai.voice.vocabulary = catalog``): room display names ("A 206"),
building names and course codes ("PHAR 240"), so a spoken "a iki yüz altı" comes back as the code people type.

People's names are **never** included (instructors, students, staff): a hint is sent to the provider before the
person has reviewed anything, and names are personal data (KVKK; ``app/ai/personal.py``). A name that is spoken
stays in the transcript and is handled on send like typed text.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Building, Course, Room

LIMIT = 80


async def catalog_terms(session: AsyncSession, *, limit: int = LIMIT) -> list[str]:
    rooms = (
        await session.execute(
            select(Room.display_name).where(Room.is_bookable.is_(True)).order_by(Room.pos, Room.code).limit(limit // 2)
        )
    ).scalars()
    buildings = (await session.execute(select(Building.name).order_by(Building.code).limit(10))).scalars()
    courses = (
        await session.execute(
            select(Course.display_code).where(Course.archived.is_(False)).order_by(Course.code).limit(limit // 2)
        )
    ).scalars()
    out: list[str] = []
    for term in (*rooms, *buildings, *courses):
        t = " ".join(str(term or "").split())
        if t and t not in out:
            out.append(t)
    return out[:limit]


__all__ = ["LIMIT", "catalog_terms"]
