from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, Planner, Viewer
from app.core.db import get_session_factory
from app.models import Assignment, ExamRequest, MeetingRequest, Room, ScheduleRun, Section, Term
from app.schemas.runs import AssignmentOut, MoveIn, MoveOut, RunCreate, RunCreated, RunOut
from app.services import settings_service as ss
from app.services.conflicts import check_room_conflicts
from app.services.exports import export_csv, export_ics, export_xlsx
from app.services.grid import assignment_labels, build_grid
from app.services.solver_bridge import run_schedule
from app.workers.queue import JobState, get_queue

router = APIRouter(prefix="/runs", tags=["runs"])

TERMINAL = {"FEASIBLE", "OPTIMAL", "INFEASIBLE", "TIMEOUT", "FAILED", "CANCELLED", "ERROR"}


async def _run(db: AsyncSession, run_id: int) -> ScheduleRun:
    run = await db.get(ScheduleRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


def _with_progress(run: ScheduleRun) -> ScheduleRun:
    st = get_queue().state(f"run:{run.id}")
    if st and run.status in {"QUEUED", "RUNNING"}:
        run.stats = {**(run.stats or {}), "progress": st.progress, "phase": st.phase}
    elif "progress" not in (run.stats or {}) and run.status in TERMINAL:
        run.stats = {**(run.stats or {}), "progress": 100}
    return run


@router.post("", response_model=RunCreated, status_code=202)
async def create_run(body: RunCreate, db: DB, user: Planner) -> RunCreated:
    term = await db.get(Term, body.term_id)
    if term is None:
        raise HTTPException(404, "term not found")
    params = {
        "time_limit_s": await ss.get_value(db, "solver_default_time_limit"),
        "workers": await ss.get_value(db, "solver_workers"),
        **body.params,
    }
    run = ScheduleRun(
        term_id=term.id,
        kind=body.kind,
        horizon=body.horizon,
        horizon_params=body.horizon_params,
        params=params,
        prompt_text=body.prompt,
        parent_run_id=body.parent_run_id,
        label=body.label,
        status="QUEUED",
        stats={"progress": 0, "phase": "queued"},
        created_by=user.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    factory = get_session_factory()
    run_id = run.id

    async def body_fn(progress: Any) -> dict[str, Any]:
        return await run_schedule(factory, run_id, progress)

    async def on_status(st: JobState) -> None:
        async with factory() as session:
            row = await session.get(ScheduleRun, run_id)
            if row is None:
                return
            if st.status == "FAILED":
                row.status = "FAILED"
                row.error = st.error
                row.finished_at = datetime.now(UTC).replace(tzinfo=None)
            row.stats = {**(row.stats or {}), "progress": st.progress, "phase": st.phase}
            await session.commit()

    get_queue().enqueue(f"run:{run_id}", body_fn, on_status=on_status)
    return RunCreated(run_id=run_id, status="QUEUED")


@router.get("", response_model=list[RunOut])
async def list_runs(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=500),
) -> list[ScheduleRun]:
    q = select(ScheduleRun).order_by(ScheduleRun.id.desc()).limit(limit)
    if term_id:
        q = q.where(ScheduleRun.term_id == term_id)
    if kind:
        q = q.where(ScheduleRun.kind == kind)
    if status:
        q = q.where(ScheduleRun.status == status)
    return [_with_progress(r) for r in (await db.execute(q)).scalars()]


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: int, db: DB, _: Viewer) -> ScheduleRun:
    return _with_progress(await _run(db, run_id))


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: int, db: DB, _: Planner) -> None:
    run = await _run(db, run_id)
    await db.delete(run)
    await db.commit()


@router.post("/{run_id}/activate", response_model=RunOut)
async def activate_run(run_id: int, db: DB, _: Planner) -> ScheduleRun:
    """Mark this run as the active/published schedule of its term+kind (used for undo of AI child runs)."""
    run = await _run(db, run_id)
    for other in (
        await db.execute(
            select(ScheduleRun).where(
                ScheduleRun.term_id == run.term_id, ScheduleRun.kind == run.kind, ScheduleRun.is_active.is_(True)
            )
        )
    ).scalars():
        other.is_active = False
    run.is_active = True
    await db.commit()
    await db.refresh(run)
    return _with_progress(run)


@router.get("/{run_id}/events")
async def run_events(run_id: int, db: DB, _: Viewer) -> StreamingResponse:
    """Server-sent events with solver phase/progress until the run reaches a terminal status."""
    run = await _run(db, run_id)
    queue = get_queue()
    factory = get_session_factory()

    async def gen() -> Any:
        key = f"run:{run_id}"
        q = queue.subscribe(key)
        try:
            first = {
                "run_id": run_id,
                "status": run.status,
                "progress": (run.stats or {}).get("progress", 0),
                "phase": (run.stats or {}).get("phase"),
            }
            yield f"event: status\ndata: {json.dumps(first)}\n\n"
            if run.status in TERMINAL:
                return
            while True:
                try:
                    snap = await asyncio.wait_for(q.get(), timeout=2.0)
                    yield f"event: progress\ndata: {json.dumps({'run_id': run_id, **snap})}\n\n"
                    if snap["status"] in {"DONE", "FAILED"}:
                        break
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    async with factory() as s:
                        row = await s.get(ScheduleRun, run_id)
                        if row is None or row.status in TERMINAL:
                            break
            async with factory() as s:
                row = await s.get(ScheduleRun, run_id)
                if row is not None:
                    done = {
                        "run_id": run_id,
                        "status": row.status,
                        "hard_score": row.hard_score,
                        "soft_score": row.soft_score,
                        "progress": 100,
                    }
                    yield f"event: done\ndata: {json.dumps(done)}\n\n"
        finally:
            queue.unsubscribe(key, q)

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


async def _assignment_out(db: AsyncSession, rows: list[Assignment]) -> list[AssignmentOut]:
    labels = await assignment_labels(db, rows)
    rooms = {r.id: r.display_name for r in (await db.execute(select(Room))).scalars()}
    out = []
    for a in rows:
        d = AssignmentOut.model_validate(a)
        d.display_label = labels[a.id]
        d.room_codes = [rooms.get(int(r), str(r)) for r in a.room_ids or []]
        out.append(d)
    return out


@router.get("/{run_id}/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    run_id: int,
    db: DB,
    _: Viewer,
    week: int | None = None,
    day: int | None = None,
    room: int | None = None,
    include_archived: bool = False,
) -> list[AssignmentOut]:
    await _run(db, run_id)
    q = (
        select(Assignment)
        .where(Assignment.run_id == run_id)
        .order_by(Assignment.week, Assignment.day, Assignment.start_period)
    )
    if day:
        q = q.where(Assignment.day == day)
    if not include_archived:
        q = q.where(Assignment.archived.is_(False))
    rows = list((await db.execute(q)).scalars())
    if week:
        rows = [
            a for a in rows if a.week == week or (a.week is None and (not a.weeks or week in [int(w) for w in a.weeks]))
        ]
    if room:
        rows = [a for a in rows if room in [int(r) for r in a.room_ids or []]]
    return await _assignment_out(db, rows)


@router.get("/{run_id}/grid")
async def run_grid(run_id: int, db: DB, _: Viewer, week: int | None = None, blocks: bool = True) -> dict[str, Any]:
    run = await _run(db, run_id)
    return await build_grid(db, run, week, include_blocks=blocks)


@router.get("/{run_id}/export")
async def export_run(
    run_id: int,
    db: DB,
    _: Viewer,
    format: str = Query("xlsx", pattern="^(xlsx|csv|ics|crbs)$"),
    weeks: str | None = None,
) -> Response:
    run = await _run(db, run_id)
    name = f"smartsched-run{run.id}"
    if format == "xlsx":
        wk = [int(w) for w in weeks.split(",")] if weeks else None
        data = await export_xlsx(db, run, wk)
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
        )
    if format == "ics":
        return Response(
            await export_ics(db, run),
            media_type="text/calendar",
            headers={"Content-Disposition": f'attachment; filename="{name}.ics"'},
        )
    text = await export_csv(db, run)
    return Response(
        text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}{"-crbs" if format == "crbs" else ""}.csv"'},
    )


async def _assignment(db: AsyncSession, run_id: int, aid: int) -> Assignment:
    a = await db.get(Assignment, aid)
    if a is None or a.run_id != run_id:
        raise HTTPException(404, "assignment not found")
    return a


@router.post("/{run_id}/assignments/{aid}/move", response_model=MoveOut)
async def move_assignment(run_id: int, aid: int, body: MoveIn, db: DB, _: Planner) -> MoveOut:
    run = await _run(db, run_id)
    a = await _assignment(db, run_id, aid)
    day = body.day or a.day
    sp = body.start_period or a.start_period
    ep = body.end_period or (sp + (a.end_period - a.start_period) if body.start_period else a.end_period)
    room_ids = body.room_ids if body.room_ids is not None else [int(r) for r in a.room_ids or []]
    weeks = [body.week] if body.week else [int(w) for w in (a.weeks or ([a.week] if a.week else []))]
    conflicts = await check_room_conflicts(
        db,
        term_id=run.term_id,
        room_ids=room_ids,
        day=day,
        start_period=sp,
        end_period=ep,
        weeks=weeks,
        exclude_assignment_id=a.id,
        run_id=run.id,
    )
    if conflicts and not body.force:
        return MoveOut(ok=False, conflicts=conflicts)
    a.day, a.start_period, a.end_period, a.room_ids, a.origin = day, sp, ep, room_ids, "MANUAL"
    if body.week:
        a.week, a.weeks = body.week, [body.week]
    await db.commit()
    await db.refresh(a)
    return MoveOut(ok=True, assignment=(await _assignment_out(db, [a]))[0], conflicts=conflicts)


@router.post("/{run_id}/assignments/{aid}/lock", response_model=AssignmentOut)
async def lock_assignment(run_id: int, aid: int, db: DB, _: Planner, locked: bool = True) -> AssignmentOut:
    a = await _assignment(db, run_id, aid)
    a.is_locked = locked
    await db.commit()
    await db.refresh(a)
    return (await _assignment_out(db, [a]))[0]


@router.get("/{run_id}/summary")
async def run_summary(run_id: int, db: DB, _: Viewer) -> dict[str, Any]:
    run = await _run(db, run_id)
    rows = list(
        (
            await db.execute(select(Assignment).where(Assignment.run_id == run_id, Assignment.archived.is_(False)))
        ).scalars()
    )
    kind_counts: dict[str, int] = {}
    for a in rows:
        kind_counts[a.origin] = kind_counts.get(a.origin, 0) + 1
    unresolved = len(run.diagnosis or [])
    req_total = 0
    if run.kind == "COURSE":
        req_total = len(
            (
                await db.execute(
                    select(MeetingRequest.id)
                    .join(Section)
                    .where(
                        Section.term_id == run.term_id,
                        MeetingRequest.needs_room.is_(True),
                        MeetingRequest.archived.is_(False),
                    )
                )
            ).all()
        )
    else:
        req_total = len(
            (
                await db.execute(
                    select(ExamRequest.id).where(
                        ExamRequest.term_id == run.term_id,
                        ExamRequest.needs_room.is_(True),
                        ExamRequest.archived.is_(False),
                    )
                )
            ).all()
        )
    return {
        "run_id": run.id,
        "status": run.status,
        "assignments": len(rows),
        "by_origin": kind_counts,
        "diagnoses": unresolved,
        "requests_needing_room": req_total,
        "hard_score": run.hard_score,
        "soft_score": run.soft_score,
        "stats": run.stats,
    }
