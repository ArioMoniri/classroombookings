"""Calendar v2 and all-classes endpoints (docs/design/v2/calendar.md §17, all-classes.md §16).

Read models: ``GET /runs/{id}/calendar-index``, ``GET /runs/{id}/heat``, ``GET /runs/{id}/free-rooms``,
``GET /terms/{id}/classes`` (+ ``/{class_id}`` detail and ``/export``).
Edits: ``POST /runs/{id}/assignments/{aid}/move-preview`` (dry run), ``POST /runs/{id}/assignments/bulk-move``
(scoped, atomic, with an undo token), ``POST /runs/{id}/assignments/restore`` (undo),
``POST /runs/{id}/assignments/bulk-lock``, ``POST /runs/{id}/assignments/{aid}/explain``.
Saved views: ``GET/POST /views``, ``PUT/DELETE /views/{id}``.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.api.deps import DB, Planner, Viewer
from app.models import Assignment, ScheduleRun, Term
from app.schemas.calendar import (
    AssignmentExplainOut,
    BulkLockIn,
    BulkMoveIn,
    BulkMoveOut,
    CalendarIndexOut,
    ClassDetailOut,
    ClassesOut,
    ExplainAssignmentIn,
    FreeRoomsOut,
    HeatOut,
    IndexAssignment,
    MoveItemIn,
    MovePreviewIn,
    RestoreIn,
    SavedViewIn,
    SavedViewOut,
    SavedViewUpdate,
)
from app.services import calendar_views as cv
from app.services.bookings_perms import load_access

log = logging.getLogger(__name__)

router = APIRouter(tags=["calendar"])


async def _run(db: DB, run_id: int) -> ScheduleRun:
    run = await db.get(ScheduleRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


async def _term(db: DB, term_id: int) -> Term:
    term = await db.get(Term, term_id)
    if term is None:
        raise HTTPException(404, "term not found")
    return term


def _http(exc: cv.CalendarError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _week_list(text: str | None) -> list[int]:
    out: list[int] = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


# ------------------------------------------------------------------ read models


@router.get("/runs/{run_id}/calendar-index", response_model=CalendarIndexOut)
async def calendar_index(run_id: int, db: DB, _: Viewer) -> CalendarIndexOut:
    """The whole term of one run in one compact payload: the client builds every lens from it."""
    return await cv.calendar_index(db, await _run(db, run_id))


@router.get("/runs/{run_id}/heat", response_model=HeatOut)
async def run_heat(
    run_id: int,
    db: DB,
    _: Viewer,
    scale: Literal["term", "month"] = "term",
    month: str | None = None,
    room_id: int | None = None,
) -> HeatOut:
    """Occupancy (assignments + pre-occupied blocks over bookable rooms × 18 periods) and conflicts per
    (week, day) for the Term lens, or per date of a month grid for the Month lens."""
    try:
        return await cv.heat(db, await _run(db, run_id), scale=scale, month=month, room_id=room_id)
    except cv.CalendarError as exc:
        raise _http(exc) from exc


@router.get("/runs/{run_id}/free-rooms", response_model=FreeRoomsOut)
async def run_free_rooms(
    run_id: int,
    db: DB,
    _: Viewer,
    day: int = Query(ge=1, le=7),
    start_period: int = Query(ge=1, le=18),
    end_period: int = Query(ge=1, le=18),
    weeks: str | None = None,
    min_capacity: int = 0,
    tags: str | None = None,
    exclude_assignment_id: int | None = None,
) -> FreeRoomsOut:
    """Every room for one slot: free (best fit first), too small, busy (with whom), blocked. Pass
    ``exclude_assignment_id`` to ignore the class being moved (its whole weekly series)."""
    run = await _run(db, run_id)
    ctx = await cv.load_run_context(db, run)
    exclude: set[int] = set()
    meeting = None
    size = min_capacity
    week_list = _week_list(weeks)
    if exclude_assignment_id:
        base = next((a for a in ctx.rows if a.id == exclude_assignment_id), None)
        if base is None:
            raise HTTPException(404, "assignment not found")
        exclude = {a.id for a in cv.weekly_series(ctx, base)}
        meeting = ctx.meeting_of(base)
        size = size or ctx.size_of(base)
        week_list = week_list or sorted({w for a in cv.weekly_series(ctx, base) for w in ctx.weeks_of(a)})
    return cv.free_rooms(
        ctx,
        day=day,
        sp=start_period,
        ep=max(start_period, end_period),
        weeks=week_list or ctx.all_weeks(),
        size=size,
        exclude=exclude,
        meeting=meeting,
        tags=[t for t in (tags or "").split(",") if t],
    )


@router.get("/terms/{term_id}/classes", response_model=ClassesOut, response_model_by_alias=True)
async def term_classes(
    term_id: int,
    db: DB,
    _: Viewer,
    kind: Literal["meetings", "exams"] = "meetings",
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> ClassesOut:
    """Every class (or exam) of the term: request + placement in ``run_id`` + issues + provenance."""
    term = await _term(db, term_id)
    run = await _run(db, run_id) if run_id else None
    compare = await _run(db, compare_run_id) if compare_run_id else None
    if run is not None and run.term_id != term.id:
        raise HTTPException(422, "run belongs to another term")
    return await cv.classes(db, term, kind=kind, run=run, compare=compare)


@router.get("/terms/{term_id}/classes/export")
async def term_classes_export(
    term_id: int,
    db: DB,
    _: Viewer,
    format: Literal["planning-list", "csv"] = "planning-list",
    kind: Literal["meetings", "exams"] = "meetings",
    run_id: int | None = None,
) -> Response:
    """``planning-list``: the planner's own workbook shape with a **SmartSched Derslik** column next to
    *Kesinleşen Derslik* (never overwritten). ``csv``: UTF-8 with BOM."""
    term = await _term(db, term_id)
    run = await _run(db, run_id) if run_id else None
    data = await cv.classes(db, term, kind=kind, run=run)
    name = f"{term.code}-{'run' + str(run.id) if run else 'talepler'}"
    if format == "csv":
        return Response(
            cv.export_csv_rows(data),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    if kind == "exams":
        raise HTTPException(422, "the planning-list export is for classes (meetings)")
    return Response(
        await cv.export_planning_list(db, term, data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}-planlama-listesi.xlsx"'},
    )


@router.get("/terms/{term_id}/classes/{class_id}", response_model=ClassDetailOut, response_model_by_alias=True)
async def term_class_detail(
    term_id: int,
    class_id: int,
    db: DB,
    _: Viewer,
    kind: Literal["meetings", "exams"] = "meetings",
    run_id: int | None = None,
) -> ClassDetailOut:
    """Inspector payload: the row, the raw Excel row (original Turkish headers), checks and placements per run."""
    term = await _term(db, term_id)
    run = await _run(db, run_id) if run_id else None
    try:
        return await cv.class_detail(db, term, class_id, kind=kind, run=run)
    except cv.CalendarError as exc:
        raise _http(exc) from exc


# ------------------------------------------------------------------ moves


async def _bulk(db: DB, user: object, run: ScheduleRun, body: BulkMoveIn) -> BulkMoveOut:
    if body.force:
        access = await load_access(db, user)  # type: ignore[arg-type]
        if "planning.admin" not in access.perms:
            # orchestrator decision 4: forcing a move despite a conflict is admin-only
            raise HTTPException(403, "moving despite a conflict is admin-only")
    ctx = await cv.load_run_context(db, run)
    try:
        plans = cv.plan_moves(ctx, body.moves)
    except cv.CalendarError as exc:
        raise _http(exc) from exc
    bad = [p for p in plans if p.hard]
    can_apply = not body.dry_run and (body.force or not bad or not body.atomic)
    to_apply = plans if body.force else [p for p in plans if not p.hard]
    if not can_apply or not to_apply:
        items = [cv.plan_item_out(ctx, p) for p in plans]
        return BulkMoveOut(
            ok=not bad,
            applied=False,
            dry_run=body.dry_run,
            items=items,
            ok_count=len(plans) - len(bad),
            conflict_count=len(bad),
        )
    rows, undo, per_base = await cv.apply_plans(db, ctx, to_apply)
    applied_ids = {p.base.id for p in to_apply}
    items = [
        cv.plan_item_out(ctx, p, *(per_base.get(p.base.id, ([], []))))
        if p.base.id in applied_ids
        else cv.plan_item_out(ctx, p)
        for p in plans
    ]
    compact: list[IndexAssignment] = await cv.compact_rows(db, ctx, rows)
    return BulkMoveOut(
        ok=not bad,
        applied=True,
        dry_run=False,
        items=items,
        ok_count=len(plans) - len(bad),
        conflict_count=len(bad),
        assignments=compact,
        undo=undo,
    )


@router.post("/runs/{run_id}/assignments/bulk-move", response_model=BulkMoveOut)
async def bulk_move(run_id: int, body: BulkMoveIn, db: DB, user: Planner) -> BulkMoveOut:
    """Move one or many classes. ``scope``: ``all`` weeks of the weekly series, one ``week``, or ``from`` a week
    on (the series is split; earlier weeks stay). ``atomic`` (default): nothing is applied if any move has a
    hard conflict. ``dry_run``: validate only. Moved rows become ``MANUAL`` and locked. ``undo`` restores the
    exact previous state through ``POST …/assignments/restore``."""
    return await _bulk(db, user, await _run(db, run_id), body)


@router.post("/runs/{run_id}/assignments/{aid}/move-preview", response_model=BulkMoveOut)
async def move_preview(run_id: int, aid: int, body: MovePreviewIn, db: DB, _: Viewer) -> BulkMoveOut:
    """Server-confirmed dry run of one move (the Move popover/dialog), with planner-facing TR/EN reasons."""
    run = await _run(db, run_id)
    item = MoveItemIn(aid=aid, **body.model_dump())
    return await _bulk(db, None, run, BulkMoveIn(moves=[item], dry_run=True))


@router.post("/runs/{run_id}/assignments/restore")
async def restore(run_id: int, body: RestoreIn, db: DB, _: Planner) -> dict[str, list[int]]:
    """Undo of a bulk move: put every snapshot back and delete the rows a ``from``/``week`` split created."""
    run = await _run(db, run_id)
    return {"restored": await cv.restore(db, run, body.snapshots, body.delete_ids), "deleted": body.delete_ids}


@router.post("/runs/{run_id}/assignments/bulk-lock")
async def bulk_lock(run_id: int, body: BulkLockIn, db: DB, _: Planner) -> dict[str, list[int]]:
    run = await _run(db, run_id)
    rows = list(
        (await db.execute(select(Assignment).where(Assignment.run_id == run.id, Assignment.id.in_(body.ids)))).scalars()
    )
    for a in rows:
        a.is_locked = body.locked
    await db.commit()
    found = {a.id for a in rows}
    return {"updated": sorted(found), "missing": sorted(set(body.ids) - found)}


# ------------------------------------------------------------------ explain


@router.post("/runs/{run_id}/assignments/{aid}/explain", response_model=AssignmentExplainOut)
async def explain_assignment(
    run_id: int, aid: int, body: ExplainAssignmentIn, db: DB, _: Viewer
) -> AssignmentExplainOut:
    """ "Why is this class here": checks, alternatives considered and the impact of moving it. Deterministic
    template; when an Anthropic key is configured the prose is paraphrased by the model and kept only if every
    number in it is grounded in the facts (``source`` tells which)."""
    run = await _run(db, run_id)
    ctx = await cv.load_run_context(db, run)
    client = None
    if body.use_model:
        try:
            from app.ai.client import AIConfigError, get_client

            try:
                client = await get_client(db)
            except AIConfigError:
                client = None
        except ImportError:  # pragma: no cover - AI layer not installed
            client = None
    try:
        return await cv.explain_assignment(db, ctx, aid, body.lang, client)
    except cv.CalendarError as exc:
        raise _http(exc) from exc


# ------------------------------------------------------------------ saved views


@router.get("/views", response_model=list[SavedViewOut])
async def list_views(db: DB, user: Viewer, surface: Literal["classes", "calendar"] = "classes") -> list[SavedViewOut]:
    """The caller's views plus views shared with everyone."""
    return await cv.list_views(db, surface, user)


@router.post("/views", response_model=SavedViewOut, status_code=201)
async def create_view(body: SavedViewIn, db: DB, user: Viewer) -> SavedViewOut:
    access = await load_access(db, user)
    try:
        return await cv.create_view(db, body, user, can_share="planning.edit" in access.perms)
    except cv.CalendarError as exc:
        raise _http(exc) from exc


@router.put("/views/{view_id}", response_model=SavedViewOut)
async def update_view(view_id: str, body: SavedViewUpdate, db: DB, user: Viewer) -> SavedViewOut:
    access = await load_access(db, user)
    try:
        return await cv.update_view(
            db,
            view_id,
            body,
            user,
            can_share="planning.edit" in access.perms,
            is_admin="planning.admin" in access.perms,
        )
    except cv.CalendarError as exc:
        raise _http(exc) from exc


@router.delete("/views/{view_id}", status_code=204)
async def delete_view(view_id: str, db: DB, user: Viewer) -> Response:
    access = await load_access(db, user)
    try:
        await cv.delete_view(db, view_id, user, is_admin="planning.admin" in access.perms)
    except cv.CalendarError as exc:
        raise _http(exc) from exc
    return Response(status_code=204)
