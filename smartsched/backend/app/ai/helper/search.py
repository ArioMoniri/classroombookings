"""``GET /helper/search`` (HB-02): pages, "Nerede?" answers and data hits in one call, with no AI and no metering.

* Index hits come from :mod:`app.ai.helper.index`, already permission-filtered: ``page`` / ``setting`` entries go to
  the palette group "Sayfalar ve ayarlar", ``tab`` / ``control`` entries to "Nerede?" (helper.md §2.3, ask A5).
* Data hits come from the palette's own sources through the person's own rights: bookable rooms they may view (the
  booking grid's ``visible_rooms``), and courses, instructors, programmes and sections through the same route
  functions as ``/courses`` ... (``planning.view``). A source the person may not read is **skipped and named**, never
  fatal and never a 403 for the whole search.
* ``question`` tells the client to put "Yardımcıya sor" first (helper.md §2.3 rule).
"""

from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.guardrails import fold
from app.ai.helper import cards
from app.ai.helper.index import get_index
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
    key = _key(q)
    if len(key) < 2:
        return []
    out = []
    for r in await bsvc.visible_rooms(session, access):
        hay = _key(f"{r.code} {r.display_name} {r.location or ''}")
        if key in hay:
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


async def _planning(session: AsyncSession, access: Access, q: str, limit: int, term_id: int | None) -> dict[str, Any]:
    """Courses, instructors, programmes (and sections of a term) through the ``/courses`` ... route functions."""
    from app.api.v1 import reference

    user = access.user
    courses = await reference.courses(session, user, search=q, limit=limit, offset=0)
    instructors = await reference.instructors(session, user, search=q, limit=limit, offset=0)
    programs = await reference.programs(session, user, search=q, faculty_id=None, limit=limit, offset=0)
    out: dict[str, Any] = {
        "courses": [
            {
                "kind": "course",
                "id": c.id,
                "label": cards.clean(c.display_code, 32),
                "sub": cards.txt(c.name or "").model_dump() if c.name else None,
                "feature_id": "requests",
            }
            for c in courses["items"]
        ],
        "instructors": [
            {"kind": "instructor", "id": i.id, "label": cards.clean(i.full_name, 80), "feature_id": "moderation"}
            for i in instructors["items"]
        ],
        "programs": [
            {"kind": "program", "id": p.id, "label": cards.clean(p.name, 120), "feature_id": "requests"}
            for p in programs["items"]
        ],
    }
    if term_id:
        sections = await reference.sections(
            session,
            user,
            term_id=term_id,
            search=q,
            program_id=None,
            include_archived=False,
            limit=limit,
            offset=0,
        )
        out["sections"] = [
            {
                "kind": "section",
                "id": x.id,
                "label": cards.clean(
                    f"{x.course.display_code if x.course else ''} {x.label or ''}".strip(), 64
                ),
                "feature_id": "timetable",
            }
            for x in sections["items"]
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
            data.update(await _planning(session, access, q, limit, term_id))
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
