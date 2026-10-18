"""``GET /helper/search`` (HB-02): pages, "Nerede?" answers and data hits in one call, with no AI and no metering.

* Index hits come from :mod:`app.ai.helper.index`, already permission-filtered: ``page`` / ``setting`` entries go to
  the palette group "Sayfalar ve ayarlar", ``tab`` / ``control`` entries to "Nerede?" (helper.md §2.3, ask A5).
* Data hits come from the palette's own sources through the person's own rights: bookable rooms they may view (the
  booking grid's rule), and courses, instructors, programmes and sections with the filters of ``/courses`` ...
  (``planning.view``, the guard of those routes). A source the person may not read is **skipped and named**, never
  fatal and never a 403 for the whole search.
* ``question`` tells the client to put "Yardımcıya sor" first (helper.md §2.3 rule).
"""

from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.guardrails import fold
from app.ai.helper import cards
from app.ai.helper.index import get_index
from app.importers import normalize as n
from app.models import Course, Instructor, Program, Section
from app.models.catalog import Room
from app.services import bookings as bsvc
from app.services.bookings_perms import Access

PER_GROUP = 6
TOTAL = 24
_QUESTION = re.compile(
    r"\?\s*$|^(nasil|nerede|nereden|neden|kim|ne zaman|hangi|how|where|why|can i|what|which)\b", re.IGNORECASE
)


def is_question(q: str) -> bool:
    text = (q or "").strip()
    return bool(_QUESTION.search(fold(text)) or _QUESTION.search(text) or len(text.split()) >= 5)


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(text or ""))


async def _rooms(session: AsyncSession, access: Access, q: str, limit: int) -> list[dict[str, Any]]:
    """Bookable rooms the person may view (the grid's rule: ``room.view`` by role or ACL, ungrouped rooms hidden
    when CRBS hides them) whose code or name contains the query; ``a102`` = ``A 102``. Filtered in SQL first."""
    key = _key(q)
    if len(key) < 2:
        return []
    like = f"%{key}%"
    stmt = (
        select(Room)
        .where(
            Room.is_bookable.is_(True),
            or_(
                func.lower(func.replace(Room.code, " ", "")).like(like),
                func.lower(func.replace(Room.display_name, " ", "")).like(like),
            ),
        )
        .order_by(Room.code)
        .limit(limit * 4)
    )
    hide_ungrouped = await bsvc.ungrouped_rooms_hidden(session)
    out = []
    for r in (await session.execute(stmt)).scalars():
        if not access.can_view_room(r) or (hide_ungrouped and r.room_group_id is None):
            continue
        out.append(
            {
                "kind": "room",
                "id": r.id,
                "label": cards.clean(r.display_name or r.code, 64),
                "sub": cards.txt(f"{r.capacity} kişilik", f"{r.capacity} seats").model_dump(),
                "feature_id": "bookings",
            }
        )
        if len(out) >= limit:
            break
    return out


async def _planning(session: AsyncSession, q: str, limit: int, term_id: int | None) -> dict[str, Any]:
    """Courses, instructors, programmes (and the sections of a term) with the filters of ``/courses``,
    ``/instructors``, ``/programs`` and ``/sections`` (``app/api/v1/reference.py``), without their page counts.
    The caller checked ``planning.view``, the guard of those routes."""
    folded, code = n.tr_casefold(q), n.tr_upper(q).replace(" ", "")
    courses = (
        await session.execute(
            select(Course).where(or_(Course.code.like(f"%{code}%"), Course.name.like(f"%{q}%")))
            .order_by(Course.code).limit(limit)
        )
    ).scalars()
    instructors = (
        await session.execute(
            select(Instructor).where(Instructor.canonical_name.like(f"%{folded}%"))
            .order_by(Instructor.full_name).limit(limit)
        )
    ).scalars()
    programs = (
        await session.execute(
            select(Program).where(Program.canonical_name.like(f"%{folded}%")).order_by(Program.name).limit(limit)
        )
    ).scalars()
    out: dict[str, Any] = {
        "courses": [
            {
                "kind": "course",
                "id": c.id,
                "label": cards.clean(c.display_code, 32),
                "sub": cards.txt(c.name).model_dump() if c.name else None,
                "feature_id": "requests",
            }
            for c in courses
        ],
        "instructors": [
            {"kind": "instructor", "id": i.id, "label": cards.clean(i.full_name, 80), "feature_id": "moderation"}
            for i in instructors
        ],
        "programs": [
            {"kind": "program", "id": p.id, "label": cards.clean(p.name, 120), "feature_id": "requests"}
            for p in programs
        ],
    }
    if term_id:
        rows = (
            await session.execute(
                select(Section, Course)
                .join(Course, Course.id == Section.course_id)
                .where(
                    Section.term_id == term_id,
                    Section.archived.is_(False),
                    or_(Course.code.like(f"%{code}%"), Course.name.like(f"%{q}%")),
                )
                .order_by(Section.id)
                .limit(limit)
            )
        ).all()
        out["sections"] = [
            {
                "kind": "section",
                "id": sec.id,
                "label": cards.clean(f"{course.display_code} {sec.label or ''}".strip(), 64),
                "feature_id": "timetable",
            }
            for sec, course in rows
        ]
    return out


async def search(
    session: AsyncSession,
    access: Access,
    q: str,
    *,
    limit: int = PER_GROUP,
    term_id: int | None = None,
    allowed_actions: list[str] | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    q = (q or "").strip()[:200]
    limit = max(1, min(limit, PER_GROUP))
    hits = get_index().search(q, access.perms, limit=limit * 2)
    allowed = allowed_actions or []
    pages = [cards.dump(cards.nav(h.entry, allowed)) for h in hits if h.entry.kind in ("page", "setting")][:limit]
    where = [cards.dump(cards.nav(h.entry, allowed)) for h in hits if h.entry.kind in ("tab", "control")][:limit]
    data: dict[str, list[dict[str, Any]]] = {}
    skipped: list[dict[str, str]] = []
    if len(q) >= 2:
        data["rooms"] = await _rooms(session, access, q, limit)
        if "planning.view" in access.perms:
            data.update(await _planning(session, q, limit, term_id))
        else:
            skipped += [
                {"source": src, "reason": "forbidden"}
                for src in ("courses", "instructors", "programs", *(("sections",) if term_id else ()))
            ]
    # the palette shows at most 24 rows
    budget = TOTAL - len(pages) - len(where)
    for k in list(data):
        data[k] = data[k][: max(0, budget)]
        budget -= len(data[k])
    return {
        "q": q,
        "question": is_question(q),
        "pages": pages,
        "where": where,
        "data": {k: v for k, v in data.items() if v},
        "skipped": skipped,
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


__all__ = ["PER_GROUP", "TOTAL", "is_question", "search"]
