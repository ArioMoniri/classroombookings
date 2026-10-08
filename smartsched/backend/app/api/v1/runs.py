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
from app.schemas.runs import (
    TERMINAL_STATUSES,
    AssignmentOut,
    DiagnosisApplyIn,
    DiagnosisApplyOut,
    MoveIn,
    MoveOut,
    RunCreate,
    RunCreated,
    RunOut,
)
from app.services import settings_service as ss
from app.services.calendar import day_label
from app.services.conflicts import check_room_conflicts
from app.services.diagnosis_fixes import FixError, apply_option, structure_diagnosis
from app.services.exports import export_csv, export_ics, export_xlsx
from app.services.grid import assignment_labels, build_grid, enrich_assignments
from app.services.solver_bridge import PARTIAL_STATUS, run_schedule
from app.workers.queue import JobState, get_queue, worker_id

router = APIRouter(prefix="/runs", tags=["runs"])

TERMINAL = set(TERMINAL_STATUSES)  # includes FEASIBLE_PARTIAL (best-effort partial timetable)


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
    params = await _client_run_params(db, body, term.id)
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
        stats={"progress": 0, "phase": "queued", "worker": worker_id()},
        created_by=user.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    _enqueue(run.id)
    return RunCreated(run_id=run.id, status="QUEUED")


async def _client_run_params(db: AsyncSession, body: RunCreate, term_id: int) -> dict[str, Any]:
    """Whitelisted, bounded params of ``POST /runs`` (review B3/M13): reserved keys (``studio``...) and
    unknown keys answer 422; server defaults are clamped to the same bounds."""
    from app.services import run_params as rp

    try:
        client = rp.clean_client_params(dict(body.params or {}))
    except rp.ParamError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.parent_run_id is not None:
        parent = await db.get(ScheduleRun, body.parent_run_id)
        if parent is None or parent.term_id != term_id or parent.kind != body.kind:
            raise HTTPException(422, "parent_run_id must be a run of the same term and kind")
    defaults = {
        "time_limit_s": await ss.get_value(db, "solver_default_time_limit"),
        "workers": await ss.get_value(db, "solver_workers"),
    }
    return rp.clamp_server_params({**defaults, **client})


def _enqueue(run_id: int) -> None:
    """Hand a committed QUEUED run to the background queue (solve + persist)."""
    factory = get_session_factory()

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


async def _term_codes(db: AsyncSession, runs: list[ScheduleRun]) -> dict[int, str]:
    ids = {r.term_id for r in runs}
    if not ids:
        return {}
    return {tid: code for tid, code in (await db.execute(select(Term.id, Term.code).where(Term.id.in_(ids)))).all()}


def run_out(run: ScheduleRun, term_codes: dict[int, str]) -> RunOut:
    """API shape of a run: term code, top-level progress/objective breakdown, structured diagnoses."""
    run = _with_progress(run)
    out = RunOut.model_validate(run)
    stats = run.stats or {}
    out.term_code = term_codes.get(run.term_id)
    out.progress = int(stats.get("progress") or (100 if run.status in TERMINAL else 0))
    breakdown = stats.get("objective_breakdown") or {}
    out.objective_breakdown = {str(k): int(v) for k, v in breakdown.items() if isinstance(v, int | float)}
    out.diagnosis = [structure_diagnosis(d, i, run.kind) for i, d in enumerate(run.diagnosis or [])]
    out.placed, out.events_total, out.partial = placement(run)
    return out


def placement(run: ScheduleRun) -> tuple[int | None, int | None, bool]:
    """(placed, events_total, partial) of a run's stored timetable."""
    stats = run.stats or {}
    placed = stats.get("placed")
    total = stats.get("events_total")
    partial = run.status == PARTIAL_STATUS or (run.status == "INFEASIBLE" and bool(stats.get("partial")))
    return (
        int(placed) if isinstance(placed, int | float) else None,
        int(total) if isinstance(total, int | float) else None,
        partial,
    )


async def runs_out(db: AsyncSession, runs: list[ScheduleRun]) -> list[RunOut]:
    codes = await _term_codes(db, runs)
    return [run_out(r, codes) for r in runs]


@router.get("", response_model=list[RunOut])
async def list_runs(
    db: DB,
    _: Viewer,
    term_id: int | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=500),
) -> list[RunOut]:
    q = select(ScheduleRun).order_by(ScheduleRun.id.desc()).limit(limit)
    if term_id:
        q = q.where(ScheduleRun.term_id == term_id)
    if kind:
        q = q.where(ScheduleRun.kind == kind)
    if status:
        q = q.where(ScheduleRun.status == status)
    return await runs_out(db, list((await db.execute(q)).scalars()))


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: int, db: DB, _: Viewer) -> RunOut:
    return (await runs_out(db, [await _run(db, run_id)]))[0]


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: int, db: DB, _: Planner) -> None:
    run = await _run(db, run_id)
    await db.delete(run)
    await db.commit()


@router.post("/{run_id}/activate", response_model=RunOut)
async def activate_run(run_id: int, db: DB, _: Planner) -> RunOut:
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
    return (await runs_out(db, [run]))[0]


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


async def _assignment_out(db: AsyncSession, run: ScheduleRun, rows: list[Assignment]) -> list[AssignmentOut]:
    enrich = await enrich_assignments(db, run, rows)
    out = []
    for a in rows:
        d = AssignmentOut.model_validate(a)
        for k, v in enrich[a.id].as_dict().items():
            setattr(d, k, v)
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
    run = await _run(db, run_id)
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
    return await _assignment_out(db, run, rows)


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


async def _conflict_messages(db: AsyncSession, conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add a human-readable ``message`` (and the other assignment's label) to every conflict."""
    ids = [int(c["id"]) for c in conflicts if c.get("kind") == "assignment"]
    labels: dict[int, str] = {}
    if ids:
        others = list((await db.execute(select(Assignment).where(Assignment.id.in_(ids)))).scalars())
        labels = await assignment_labels(db, others)
    room_ids = {int(c["room_id"]) for c in conflicts if c.get("room_id")}
    names: dict[int, str] = {}
    if room_ids:
        names = {r.id: r.display_name for r in (await db.execute(select(Room).where(Room.id.in_(room_ids)))).scalars()}
    out = []
    for c in conflicts:
        when = f"{day_label(int(c.get('day') or 0))} P{c.get('start_period')}-P{c.get('end_period')}"
        rid = int(c["room_id"]) if c.get("room_id") else None
        room = c.get("room") or (names.get(rid, f"#{rid}") if rid else "room")
        if c.get("kind") == "assignment":
            label = labels.get(int(c["id"]), c.get("label") or f"#{c['id']}")
            msg = f"{room} is taken by {label} ({when})"
            out.append(
                {**c, "room": room, "label": label, "with_assignment_id": c["id"], "with_label": label, "message": msg}
            )
        elif c.get("kind") == "block":
            out.append({**c, "message": f"{room} is blocked: {c.get('label')} ({when})"})
        else:
            out.append({**c, "message": c.get("message") or str(c.get("kind"))})
    return out


@router.post("/{run_id}/assignments/{aid}/move", response_model=MoveOut)
async def move_assignment(run_id: int, aid: int, body: MoveIn, db: DB, _: Planner) -> MoveOut:
    """Manual drag-drop edit. A successful move marks the assignment ``MANUAL`` and **locked** so that
    re-solves (child runs) keep it where the planner put it (``Event.locked`` overrides the request's
    fixed day/time). Conflicts are returned with ``ok=false`` unless ``force``."""
    run = await _run(db, run_id)
    a = await _assignment(db, run_id, aid)
    day = body.day or a.day
    sp = body.start_period or a.start_period
    ep = body.end_period or (sp + (a.end_period - a.start_period) if body.start_period else a.end_period)
    if not (1 <= day <= 7 and 1 <= sp <= ep <= 18):
        raise HTTPException(422, f"invalid target: day {day}, P{sp}-P{ep}")
    room_ids = body.room_ids if body.room_ids is not None else [int(r) for r in a.room_ids or []]
    known = set((await db.execute(select(Room.id).where(Room.id.in_(room_ids)))).scalars()) if room_ids else set()
    if set(room_ids) - known:
        raise HTTPException(422, f"unknown room id(s) {sorted(set(room_ids) - known)}")
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
    if run.kind == "EXAM":
        # exams may share a room: only a seat-budget overflow is a conflict (blocks always are)
        preview = Assignment(
            id=a.id,
            run_id=run.id,
            meeting_request_id=a.meeting_request_id,
            exam_request_id=a.exam_request_id,
            week=body.week or a.week,
            weeks=weeks,
            day=day,
            date=a.date,
            start_period=sp,
            end_period=ep,
            room_ids=room_ids,
        )
        reasons = (await enrich_assignments(db, run, [preview]))[a.id].conflict_reasons
        seat = [r for r in reasons if r.startswith("seats:") or r.startswith("capacity:")]
        conflicts = [c for c in conflicts if c.get("kind") != "assignment"]
        conflicts += [{"kind": "seats", "message": r} for r in seat]
    conflicts = await _conflict_messages(db, conflicts)
    if conflicts and not body.force:
        return MoveOut(ok=False, assignment=(await _assignment_out(db, run, [a]))[0], conflicts=conflicts)
    a.day, a.start_period, a.end_period, a.room_ids = day, sp, ep, room_ids
    a.origin = "MANUAL"
    a.is_locked = True
    if body.week:
        a.week, a.weeks = body.week, [body.week]
    await db.commit()
    await db.refresh(a)
    return MoveOut(ok=True, assignment=(await _assignment_out(db, run, [a]))[0], conflicts=conflicts)


@router.post("/{run_id}/assignments/{aid}/lock", response_model=AssignmentOut)
async def lock_assignment(run_id: int, aid: int, db: DB, _: Planner, locked: bool = True) -> AssignmentOut:
    run = await _run(db, run_id)
    a = await _assignment(db, run_id, aid)
    a.is_locked = locked
    await db.commit()
    await db.refresh(a)
    return (await _assignment_out(db, run, [a]))[0]


@router.post("/{run_id}/diagnoses/{idx}/apply", response_model=DiagnosisApplyOut)
async def apply_diagnosis(run_id: int, idx: int, body: DiagnosisApplyIn, db: DB, user: Planner) -> DiagnosisApplyOut:
    """Apply one structured suggestion of diagnosis ``idx`` (see ``GET /runs/{id}`` ->
    ``diagnosis[idx].suggestions[option_index]`` with ``applicable=true``).

    Supported: ``move`` (place + lock the event at the suggested room/time), ``release_room`` (also
    unlocks the holders), ``unlock`` (reset LOCKED requests / locked assignments), ``relax`` (soften the
    term's hard constraint rows of that kind), ``split`` (exams: allow up to 3 rooms). Anything else
    answers 422. With ``re_solve`` (default) a child run is queued with ``parent_run_id`` = this run.
    """
    run = await _run(db, run_id)
    diags = list(run.diagnosis or [])
    if not 0 <= idx < len(diags):
        raise HTTPException(404, f"diagnosis {idx} not found (run has {len(diags)})")
    diag = diags[idx] if isinstance(diags[idx], dict) else {"suggestions": [], "event_ids": []}
    try:
        res = await apply_option(db, run, diag, body.option_index)
    except FixError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc)) from exc
    child_id: int | None = None
    if body.re_solve:
        child = ScheduleRun(
            term_id=run.term_id,
            kind=run.kind,
            horizon=run.horizon,
            horizon_params=dict(run.horizon_params or {}),
            params=dict(run.params or {}),
            parent_run_id=run.id,
            prompt_text=f"fix: diagnosis {idx} option {body.option_index}: {res.message}",
            label=body.label or f"fix #{run.id}.{idx}",
            status="QUEUED",
            stats={
                "progress": 0,
                "phase": "queued",
                "fix": {"diagnosis": idx, "option": body.option_index},
                "worker": worker_id(),
            },
            created_by=user.id,
        )
        db.add(child)
        await db.commit()
        await db.refresh(child)
        child_id = child.id
        _enqueue(child.id)
    else:
        await db.commit()
    return DiagnosisApplyOut(
        run_id=run.id,
        child_run_id=child_id,
        action=res.action,
        message=res.message,
        details=res.details,
        constraint_id=res.constraint_id,
    )


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
    placed, total, partial = placement(run)
    if partial:
        headline = {
            "tr": f"{placed}/{total} ders yerleşti · hiçbir kural bozulmadı",
            "en": f"{placed}/{total} placed · no rule broken",
        }
    elif run.status in ("OPTIMAL", "FEASIBLE"):
        headline = {
            "tr": f"Tüm dersler yerleşti ({total or len(rows)})",
            "en": f"Everything placed ({total or len(rows)})",
        }
    else:
        headline = {"tr": f"Durum: {run.status}", "en": f"Status: {run.status}"}
    return {
        "run_id": run.id,
        "status": run.status,
        "partial": partial,
        "placed": placed,
        "events_total": total,
        "headline": headline,
        "shared_room_overflows": (run.stats or {}).get("shared_room_overflows") or [],
        "assignments": len(rows),
        "by_origin": kind_counts,
        "diagnoses": unresolved,
        "requests_needing_room": req_total,
        "hard_score": run.hard_score,
        "soft_score": run.soft_score,
        "stats": run.stats,
    }
