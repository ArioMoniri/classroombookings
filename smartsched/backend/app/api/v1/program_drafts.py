"""Program wizard drafts and wizard reads (P19-W-01..W-08 + backend gap 7; docs/design/v2/phase19-program-wizard.md).

=================================================================  ==============  ===================================
Route                                                              Permission      Notes
=================================================================  ==============  ===================================
``POST /program-drafts`` {term_id, payload?, step?}                planning.edit   201, a new draft (owner = caller)
``GET /program-drafts?mine=&term_id=&status=``                     planning.edit   resume list ("Taslaklar")
``GET /program-drafts/{id}``                                       planning.edit   payload + validation
``PATCH /program-drafts/{id}`` {path, value | ops | payload, ...}  planning.edit   autosave, per-field merge
``DELETE /program-drafts/{id}``                                    planning.edit   204; a committed draft is kept
``POST /program-drafts/{id}/validate?step=&precheck=``             planning.edit   field / step / pre-check issues
``POST /program-drafts/{id}/precheck``                             planning.edit   program-scoped Studio pre-check
``POST /program-drafts/{id}/paste`` {step, tsv}                    planning.edit   TSV preview, nothing stored
``POST /program-drafts/{id}/commit`` {solve: none | minimal}       planning.edit   one transaction, 30-day undo
``GET /program-drafts/{id}/undo``                                  planning.edit   can it be undone, and why not
``POST /program-drafts/{id}/undo``                                 planning.edit   archive what the commit created
``GET /terms/{id}/instructors/load?ids=&q=``                       planning.view   periods / week per instructor
``GET /terms/{id}/sections/search?q=&course_code=&program_id=``    planning.view   joint-teaching + cohort links
``GET /terms/{id}/rooms/fit?capacity=&tags=&building=``            planning.view   live "sığan odalar" line
=================================================================  ==============  ===================================

Nothing here writes live rows before ``commit``; the catalog_admin create endpoints stay for other callers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.api.deps import DB, Planner, Viewer
from app.importers import normalize as n
from app.models import Instructor, ProgramDraft, Room, Term
from app.schemas.program_drafts import CommitIn, DraftCreateIn, DraftPatchIn, PasteIn
from app.services import program_drafts as svc
from app.services.bookings_perms import load_access

router = APIRouter(tags=["program-drafts"])


def _raise(exc: svc.DraftError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


async def _draft(db: DB, draft_id: int) -> ProgramDraft:
    d = await db.get(ProgramDraft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    return d


async def _term(db: DB, term_id: int) -> Term:
    t = await db.get(Term, term_id)
    if t is None:
        raise HTTPException(404, "term not found")
    return t


@router.post("/program-drafts", status_code=201)
async def create_draft(body: DraftCreateIn, db: DB, user: Planner) -> dict[str, Any]:
    try:
        d = await svc.create(db, user, body.term_id, body.payload, body.step)
        return {**svc.draft_out(d), "validation": await svc.validate(db, d)}
    except svc.DraftError as exc:
        raise _raise(exc) from exc


@router.get("/program-drafts")
async def list_drafts(
    db: DB, user: Planner, mine: bool = True, term_id: int | None = None, status: str | None = "draft"
) -> dict[str, Any]:
    items = await svc.list_drafts(db, user, mine=mine, term_id=term_id, status=status or None)
    return {"items": items, "total": len(items)}


@router.get("/program-drafts/{draft_id}")
async def get_draft(draft_id: int, db: DB, _user: Planner) -> dict[str, Any]:
    d = await _draft(db, draft_id)
    return {**svc.draft_out(d), "validation": await svc.validate(db, d)}


@router.patch("/program-drafts/{draft_id}")
async def patch_draft(draft_id: int, body: DraftPatchIn, db: DB, user: Planner) -> dict[str, Any]:
    d = await _draft(db, draft_id)
    ops = [o.model_dump() for o in body.ops or []]
    if body.path:
        ops.append({"path": body.path, "value": body.value, "op": body.op})
    if not ops and body.payload is None and body.step is None:
        raise HTTPException(422, "send path + value, ops, payload or step")
    try:
        return await svc.patch(
            db, d, user, ops=ops, payload=body.payload, base_version=body.base_version, step=body.step
        )
    except svc.DraftError as exc:
        raise _raise(exc) from exc


@router.delete("/program-drafts/{draft_id}", status_code=204)
async def delete_draft(draft_id: int, db: DB, _user: Planner) -> Response:
    try:
        await svc.delete(db, await _draft(db, draft_id))
    except svc.DraftError as exc:
        raise _raise(exc) from exc
    return Response(status_code=204)


@router.post("/program-drafts/{draft_id}/validate")
async def validate_draft(
    draft_id: int, db: DB, _user: Planner, step: str | None = None, precheck: bool = False
) -> dict[str, Any]:
    try:
        return await svc.validate(db, await _draft(db, draft_id), step=step, precheck=precheck)
    except svc.DraftError as exc:
        raise _raise(exc) from exc


@router.post("/program-drafts/{draft_id}/precheck")
async def precheck_draft(draft_id: int, db: DB, _user: Planner) -> dict[str, Any]:
    """The Studio pre-check for the draft's classes in the term (written in a rolled-back session)."""
    d = await _draft(db, draft_id)
    try:
        return await svc.program_precheck(d)
    except svc.DraftError as exc:
        raise _raise(exc) from exc


@router.post("/program-drafts/{draft_id}/paste")
async def paste(draft_id: int, body: PasteIn, db: DB, _user: Planner) -> dict[str, Any]:
    await _draft(db, draft_id)
    return svc.paste_preview(body.tsv)


@router.post("/program-drafts/{draft_id}/commit", status_code=201)
async def commit_draft(draft_id: int, body: CommitIn, db: DB, user: Planner) -> dict[str, Any]:
    d = await _draft(db, draft_id)
    try:
        return await svc.commit(db, d, user, solve=body.solve)
    except svc.DraftError as exc:
        raise _raise(exc) from exc


async def _may_undo(db: DB, d: ProgramDraft, user: Any) -> None:
    access = await load_access(db, user)
    if d.owner_id != user.id and "planning.admin" not in access.perms:
        raise HTTPException(403, "only the coordinator who created the programme or a planning administrator undoes it")


@router.get("/program-drafts/{draft_id}/undo")
async def undo_check(draft_id: int, db: DB, user: Planner) -> dict[str, Any]:
    d = await _draft(db, draft_id)
    try:
        return await svc.undo(db, d, user, dry=True)
    except svc.DraftError as exc:
        raise _raise(exc) from exc


@router.post("/program-drafts/{draft_id}/undo")
async def undo_commit(draft_id: int, db: DB, user: Planner) -> dict[str, Any]:
    d = await _draft(db, draft_id)
    await _may_undo(db, d, user)
    try:
        return await svc.undo(db, d, user)
    except svc.DraftError as exc:
        raise _raise(exc) from exc


# --------------------------------------------------------------------------- wizard reads (gap 7)


@router.get("/terms/{term_id}/instructors/load")
async def instructor_load(
    term_id: int,
    db: DB,
    _user: Viewer,
    ids: str | None = Query(default=None, description="comma separated instructor ids"),
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Teaching load per instructor in the term (periods a week over live meetings; a joint lecture listed once per
    programme counts once) and the warning limit (setting ``planning.instructor_load_limit``, default 20)."""
    from app.services.calendar_views import tr_fold

    await _term(db, term_id)
    wanted: list[int] | None = None
    if ids:
        try:
            wanted = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(422, "ids must be integers") from exc
    people: list[Instructor]
    stmt = select(Instructor).where(Instructor.archived.is_(False)).order_by(Instructor.full_name)
    if wanted is not None:
        stmt = stmt.where(Instructor.id.in_(wanted))
    people = list((await db.execute(stmt)).scalars())
    if q and n.clean_text(q):
        needle = tr_fold(q)
        people = [p for p in people if needle in tr_fold(p.full_name)]
    people = people[:limit]
    loads = await svc.instructor_loads(db, term_id, [p.id for p in people])
    lim = await svc.load_limit(db)
    items = []
    for p in people:
        row = loads.get(p.id, {"periods_per_week": 0, "meetings": 0, "sections": 0})
        items.append(
            {
                "instructor_id": p.id,
                "full_name": p.full_name,
                "title": p.title,
                "periods_per_week": row["periods_per_week"],
                "meetings": row["meetings"],
                "sections": row["sections"],
                "over_limit": row["periods_per_week"] > lim,
            }
        )
    return {"term_id": term_id, "limit": lim, "items": items}


@router.get("/terms/{term_id}/sections/search")
async def sections_search(
    term_id: int,
    db: DB,
    _user: Viewer,
    q: str | None = None,
    course_code: str | None = None,
    program_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    term = await _term(db, term_id)
    return await svc.search_sections(db, term, q=q, course_code=course_code, program_id=program_id, limit=limit)


@router.get("/terms/{term_id}/rooms/fit")
async def rooms_fit(
    term_id: int,
    db: DB,
    _user: Viewer,
    capacity: int = Query(ge=1, le=5000),
    tags: str | None = None,
    building: str | None = None,
) -> dict[str, Any]:
    """Bookable rooms seating ``capacity`` with every tag, smallest first (TIP rooms only when asked)."""
    await _term(db, term_id)
    rooms = list((await db.execute(select(Room))).scalars())
    fit = svc.rooms_fit(rooms, capacity, [t.strip() for t in (tags or "").split(",") if t.strip()], building)
    return {"capacity": capacity, "count": len(fit), "items": [svc.room_brief(r) for r in fit]}
