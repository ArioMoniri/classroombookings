from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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
from app.services import audit
from app.services import settings_service as ss
from app.services.calendar import day_label
from app.services.conflicts import check_room_conflicts
from app.services.diagnosis_fixes import FixError, apply_option, structure_diagnosis
from app.services.events import publish_event
from app.services.exports import export_crbs, export_csv, export_ics, export_xlsx
from app.services.grid import assignment_labels, build_grid, enrich_assignments
from app.services.planning_audit import assignment_snapshot, forced_reason, record_assignments
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
    await _check_user_limit(db, user.id)
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
async def delete_run(run_id: int, db: DB, user: Planner) -> None:
    run = await _run(db, run_id)
    if run.is_active:  # review D4: the published timetable drives the booking grid
        raise HTTPException(409, f"run {run_id} is the published timetable; activate another run first")
    if run.status in {"QUEUED", "RUNNING"}:
        await _cancel(db, run, user)  # never leave a solver running for a deleted run
    before = audit.snapshot(run, RUN_AUDIT_FIELDS)
    await publish_event(db, "run.delete", "run", run.id, before=before, actor=user, term_id=run.term_id)
    await db.delete(run)
    await db.commit()


@router.post("/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: int, db: DB, user: Planner) -> RunOut:
    """Cancel a QUEUED or RUNNING run: status ``CANCELLED`` at once, the CP-SAT search is stopped
    (``StopSearch``) and its partial result discarded. 409 for a run that already finished."""
    run = await _run(db, run_id)
    if run.status not in {"QUEUED", "RUNNING"}:
        raise HTTPException(409, f"run {run_id} is {run.status}; only QUEUED or RUNNING runs can be cancelled")
    if not await _cancel(db, run, user):
        raise HTTPException(409, f"run {run_id} is {run.status}; it finished before the cancel")
    return (await runs_out(db, [run]))[0]


async def _cancel(db: AsyncSession, run: ScheduleRun, user: Any) -> bool:
    """Cancel a QUEUED / RUNNING run.  The status is written by one conditional UPDATE, so a result that
    was committed meanwhile is never overwritten (the run already finished: False)."""
    from sqlalchemy import update

    from app.workers import cancel

    res = await db.execute(
        update(ScheduleRun)
        .where(ScheduleRun.id == run.id, ScheduleRun.status.in_(("QUEUED", "RUNNING")))
        .values(
            status="CANCELLED",
            error=f"cancelled by {getattr(user, 'email', None) or 'a planner'}",
            finished_at=datetime.now(UTC).replace(tzinfo=None),
            stats={**(run.stats or {}), "phase": "cancelled"},
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    await db.refresh(run)
    if not getattr(res, "rowcount", 0):
        return False
    cancel.cancel(run.id)  # this process; other processes see CANCELLED on their next heartbeat
    return True


async def _check_user_limit(db: AsyncSession, user_id: int) -> None:
    from app.workers.run_jobs import check_user_limit

    await check_user_limit(db, user_id)


#: statuses of a finished run whose timetable may be published (a best-effort partial run places fewer classes,
#: every placed one holding the hard rules)
PUBLISHABLE = frozenset({"OPTIMAL", "FEASIBLE", PARTIAL_STATUS})
RUN_AUDIT_FIELDS = ("term_id", "kind", "status", "label", "hard_score", "soft_score", "is_active", "parent_run_id")


async def publish_blockers(db: AsyncSession, run: ScheduleRun) -> list[str]:
    """Why ``run`` may not become the published timetable (review D4, admin persona M-02); empty = publishable.

    A run edited by hand (moves, forced overrides) is checked again at planner level now: every hard-rule finding
    must be an accepted exception the run reports or a manual edit a recorded, reasoned override explains
    (:func:`app.services.publish_guard.integrity`). An unedited run needs its own hard 100."""
    from app.services import publish_guard
    from app.services.planner_check import check_run

    out: list[str] = []
    if run.status not in PUBLISHABLE:
        out.append(f"run {run.id} is {run.status}; only a finished run ({', '.join(sorted(PUBLISHABLE))}) is published")
        return out
    edited = bool((run.stats or {}).get("manual_edits")) or bool(publish_guard.overrides(run))
    if edited:
        integ = publish_guard.integrity(await check_run(db, run), run)
        out += [f"{f['rule']}: {f['message']}" for f in integ["blocking"][:20]]
        if len(integ["blocking"]) > 20:
            out.append(f"... and {len(integ['blocking']) - 20} more")
    elif run.hard_score != 100:
        out.append(f"run {run.id} breaks hard rules (hard score {run.hard_score}); fix or re-solve before publishing")
    return out


async def forced_breaks(db: AsyncSession, run: ScheduleRun) -> list[dict[str, Any]]:
    """The hard rules a run breaks on purpose: forced moves with a recorded reason (round-1 R1-S-01 / R1-M-05).
    Publishing such a run needs ``confirm_forced_breaks`` after the planner has seen this list."""
    from app.services import publish_guard
    from app.services.planner_check import check_run

    if not publish_guard.overrides(run):
        return []
    integ = publish_guard.integrity(await check_run(db, run), run)
    return [b for b in publish_guard.broken_rules(integ, run) if b.get("explained")]


class ActivateIn(BaseModel):
    #: admin persona M-04: publish a run that covers fewer weeks than the published one
    confirm_scope_reduction: bool = False
    #: round-1 R1-S-01: publish a run whose only hard-rule breaks are forced moves with a recorded reason (409
    #: ``forced_breaks`` lists them first)
    confirm_forced_breaks: bool = False
    #: P19-M-09: one digest per affected academician (their changed classes) through notify_dispatch
    notify_people: bool = False


class ActivateOut(RunOut):
    #: academicians that got the publish digest (``notify_people``; null when not asked)
    notified: int | None = None
    notify: dict[str, Any] | None = None


@router.post("/{run_id}/activate", response_model=ActivateOut)
async def activate_run(
    run_id: int, db: DB, user: Planner, body: Annotated[ActivateIn | None, Body()] = None
) -> ActivateOut:
    """Publish this run as the timetable of its term + kind (it drives the booking grid; also the undo of AI child
    runs). 409 unless the run finished with every hard rule held or explained (review D4, persona M-02), and 409
    ``scope_reduction`` when it covers fewer weeks than the published run unless ``confirm_scope_reduction``
    (M-04). Exactly one run per (term, kind) is active: the switch is two conditional UPDATEs in one transaction,
    and ``uq_schedule_runs_active`` (a partial unique index) makes a concurrent second activation fail instead of
    leaving two published runs."""
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    from app.services import publish_guard

    run = await _run(db, run_id)
    blockers = await publish_blockers(db, run)
    if blockers:
        raise HTTPException(409, {"message": "run cannot be published", "issues": blockers})
    if run.is_active:
        return ActivateOut(**(await runs_out(db, [run]))[0].model_dump())
    scope = (ScheduleRun.term_id == run.term_id, ScheduleRun.kind == run.kind)
    active = (
        (await db.execute(select(ScheduleRun).where(*scope, ScheduleRun.is_active.is_(True)).order_by(ScheduleRun.id)))
        .scalars()
        .first()
    )
    previous = active.id if active is not None else None
    if not (body and body.confirm_scope_reduction):
        reduction = await publish_guard.scope_reduction(db, run, active)
        if reduction is not None:
            raise HTTPException(409, reduction)
    if not (body and body.confirm_forced_breaks):
        forced = await forced_breaks(db, run)
        if forced:
            raise HTTPException(
                409,
                {
                    "code": "forced_breaks",
                    "message": f"run {run.id} breaks {len(forced)} hard rule(s) on purpose (forced moves with a "
                    "reason); send confirm_forced_breaks: true to publish it anyway",
                    "message_tr": f"#{run.id} {len(forced)} kesin kuralı gerekçeli zorunlu taşımayla bozuyor; "
                    "yayımlamak için bunları onaylayın",
                    "message_en": f"Run #{run.id} breaks {len(forced)} hard rule(s) through forced moves with a "
                    "reason; confirm them to publish",
                    "breaks": forced[:50],
                    "hard_score": run.hard_score,
                    "confirm_field": "confirm_forced_breaks",
                },
            )
    try:
        await db.execute(
            update(ScheduleRun)
            .where(*scope, ScheduleRun.is_active.is_(True), ScheduleRun.id != run.id)
            .values(is_active=False)
            .execution_options(synchronize_session=False)
        )
        res = await db.execute(
            update(ScheduleRun)
            .where(ScheduleRun.id == run.id, ScheduleRun.status.in_(PUBLISHABLE))
            .values(is_active=True)
            .execution_options(synchronize_session=False)
        )
        if not getattr(res, "rowcount", 0):  # cancelled or re-run meanwhile
            await db.rollback()
            raise HTTPException(409, f"run {run_id} changed while it was being published; try again")
        await publish_event(
            db,
            "run.activate",
            "run",
            run.id,
            before={"active_run_id": previous},
            after={"active_run_id": run.id, "status": run.status, "hard_score": run.hard_score, "label": run.label},
            actor=user,
            term_id=run.term_id,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "another run of this term was published at the same time; reload") from exc
    await db.refresh(run)
    notify = None
    if body is not None and body.notify_people and run.kind == "COURSE":
        from app.services.moderation import publish_digest

        notify = await publish_digest(db, run, previous)  # after the publish committed: a failed mail never undoes it
        await db.commit()
        await db.refresh(run)
    out = (await runs_out(db, [run]))[0]
    return ActivateOut(**out.model_dump(), notified=notify["notified"] if notify else None, notify=notify)


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
    """``xlsx`` (the weekly board; ``weeks`` = "3" / "4,6-8" picks the sheets), ``csv``, ``ics`` and ``crbs``
    (CRBS's booking export columns). Only xlsx honours ``weeks``; the other formats export the whole run."""
    run = await _run(db, run_id)
    name = f"smartsched-run{run.id}"
    # a week run's board / csv is named after its week(s) (R1-M-38: "smartsched-run7-hafta4.xlsx"); term runs,
    # ics and crbs keep the plain name
    week_name = name + _week_suffix(run)
    wk = await _export_weeks(db, run, weeks) if weeks else None
    if format == "xlsx":
        data = await export_xlsx(db, run, wk)
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{week_name}.xlsx"'},
        )
    if format == "ics":
        return Response(
            await export_ics(db, run),
            media_type="text/calendar",
            headers={"Content-Disposition": f'attachment; filename="{name}.ics"'},
        )
    if format == "crbs":  # CRBS's booking export columns, one row per class meeting date
        return Response(
            await export_crbs(db, run),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}-crbs.csv"'},
        )
    text = await export_csv(db, run)
    return Response(
        text, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{week_name}.csv"'}
    )


def _week_suffix(run: ScheduleRun) -> str:
    """``"-hafta4"`` for a WEEK run (``"-hafta4-6"`` when it spans several weeks), ``""`` for every other run."""
    if run.horizon != "WEEK":
        return ""
    raw = (run.horizon_params or {}).get("weeks") or [(run.horizon_params or {}).get("week")]
    weeks = sorted({int(w) for w in raw if isinstance(w, int | str) and str(w).isdigit()})
    if not weeks:
        return ""
    return f"-hafta{weeks[0]}" if len(weeks) == 1 else f"-hafta{weeks[0]}-{weeks[-1]}"


_WEEKS_RX = re.compile(r"^\s*\d+\s*(-\s*\d+\s*)?$")


async def _export_weeks(db: AsyncSession, run: ScheduleRun, raw: str) -> list[int]:
    """``"4"``, ``"4,6-8"`` -> sorted week numbers inside the run's term; 422 (TR/EN) otherwise."""
    from app.services import publish_guard

    def bad(en: str, tr: str) -> HTTPException:
        return HTTPException(422, {"code": "weeks", "message": en, "message_en": en, "message_tr": tr})

    out: set[int] = set()
    for part in raw.split(","):
        if not _WEEKS_RX.match(part):
            raise bad(
                f"weeks must be numbers or ranges like 4,6-8 (got {raw!r})",
                f"haftalar 4,6-8 gibi sayı veya aralık olmalı (gelen: {raw!r})",
            )
        lo, _, hi = part.partition("-")
        a, b = int(lo), int(hi or lo)
        if a > b:
            raise bad(f"week range {a}-{b} runs backwards", f"{a}-{b} hafta aralığı ters")
        out.update(range(a, b + 1))
    term_weeks = set(await publish_guard.run_weeks(db, ScheduleRun(term_id=run.term_id, horizon="TERM")))
    outside = sorted(out - term_weeks) if term_weeks else sorted(w for w in out if w < 1)
    if outside:
        last = max(term_weeks) if term_weeks else 0
        raise bad(
            f"week(s) {outside} are outside the term (weeks 1-{last})",
            f"{', '.join(map(str, outside))}. hafta dönemin dışında (1-{last}. haftalar)",
        )
    return sorted(out)


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
async def move_assignment(run_id: int, aid: int, body: MoveIn, db: DB, user: Planner) -> MoveOut:
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
    else:
        conflicts += await _capacity_conflict(db, run, a, room_ids)
    conflicts = await _conflict_messages(db, conflicts)
    # round-1 R1-M-05: the run's own hard-rule evaluation (planner level) on the moved row, e.g. a LOCKED class
    # leaving its definitive room; a check that passes here keeps the hard score
    from app.services import move_guard

    covered = {"room_overlap" if c.get("kind") == "assignment" else str(c.get("kind") or "") for c in conflicts}
    verdict = await move_guard.planner_issues(
        db,
        run,
        [move_guard.TrialMove(a.id, ((a.id, tuple(weeks)),), day, sp, ep, tuple(room_ids))],
        covered={a.id: covered},
    )
    conflicts += [
        {"kind": i.code, "message": i.text.tr, "message_tr": i.text.tr, "message_en": i.text.en}
        for i in verdict.for_base(a.id)
    ]
    if conflicts and not body.force:
        return MoveOut(ok=False, assignment=(await _assignment_out(db, run, [a]))[0], conflicts=conflicts)
    if conflicts:  # forcing a hard-rule break: administrators only, with a written reason (persona M-02 / M-09)
        await _check_force(db, user, body.reason, conflicts)
    original_id, before = a.id, assignment_snapshot(a)
    row_weeks = [int(w) for w in (a.weeks or ([a.week] if a.week else []))]
    if body.week and len(row_weeks) > 1:
        if body.week not in row_weeks:
            raise HTTPException(422, f"week {body.week} is not one of this assignment's weeks {row_weeks}")
        # a move "in week w" moves that week only: the row keeps its other weeks, a new row holds week w
        # (review M4: the 14-week assignment was cut to one week)
        rest = [w for w in row_weeks if w != body.week]
        a.weeks = rest
        a.week = rest[0] if len(rest) == 1 else None
        if len(rest) == 1 and run.kind != "EXAM":
            a.date = await _date_of(db, run, rest[0], a.day)
        moved = Assignment(
            run_id=run.id,
            meeting_request_id=a.meeting_request_id,
            exam_request_id=a.exam_request_id,
            label=a.label,
            course_codes=list(a.course_codes or []),
            tags=list(a.tags or []),
            notes=a.notes,
        )
        db.add(moved)
        a = moved
    a.day, a.start_period, a.end_period, a.room_ids = day, sp, ep, room_ids
    a.origin = "MANUAL"
    a.is_locked = True
    if body.week:
        a.week, a.weeks = body.week, [body.week]
        if run.kind != "EXAM":
            a.date = await _date_of(db, run, body.week, day)
    await db.flush()
    after = {**assignment_snapshot(a), "forced": bool(conflicts), "conflicts": [c.get("message") for c in conflicts]}
    if a.id != original_id:
        after["split_into"] = a.id  # this week moved to a new row; the original keeps its other weeks
    ev = await publish_event(
        db,
        "assignment.move",
        "assignment",
        original_id,
        before=before,
        after=after,
        actor=user,
        reason=f"{(body.reason or '').strip()} ({forced_reason(conflicts)})" if conflicts else None,
        term_id=run.term_id,
    )
    if conflicts:
        from app.services import publish_guard

        publish_guard.record_override(
            run,
            assignment_ids=sorted({original_id, a.id}),
            request_ids=[r for r in (a.meeting_request_id, a.exam_request_id) if r],
            rules=sorted({str(c.get("kind") or "conflict") for c in conflicts}),
            conflicts=[str(c.get("message") or "") for c in conflicts],
            reason=body.reason or "",
            actor=user,
            audit_id=ev.id if ev is not None else None,
            findings=verdict.findings.get(original_id, []),
            rows=[a],
        )
    check = await _rescore(db, run)  # after the override is recorded: it counts against the hard score
    await db.commit()
    await db.refresh(a)
    return MoveOut(
        ok=True,
        assignment=(await _assignment_out(db, run, [a]))[0],
        conflicts=conflicts,
        hard_score=run.hard_score,
        status=run.status,
        violations=[f.as_dict() for f in check.violations[:50]],
    )


async def _capacity_conflict(
    db: AsyncSession, run: ScheduleRun, a: Assignment, room_ids: list[int]
) -> list[dict[str, Any]]:
    """Persona M-09: a lecture moved into rooms that cannot seat it breaks a hard rule. Keeping the rooms the class
    already has stays allowed (the planner's own room is an accepted, reported exception)."""
    from app.services import calendar_views as cv
    from app.services.tr_grammar import dative

    if not room_ids or set(room_ids) <= {int(r) for r in a.room_ids or []}:
        return []
    ctx = await cv.load_run_context(db, run)
    size = ctx.size_of(a)
    seats = sum(ctx.cap(r) for r in room_ids)
    if not size or seats >= size:
        return []
    codes = " + ".join(ctx.code(r) for r in room_ids)
    return [{"kind": "capacity", "message": f"{size} öğrenci {seats} kişilik {dative(codes)} sığmaz"}]


async def _check_force(db: AsyncSession, user: Any, reason: str | None, conflicts: list[dict[str, Any]]) -> None:
    from app.services import publish_guard
    from app.services.bookings_perms import load_access

    rules = sorted({str(c.get("kind") or "conflict") for c in conflicts})
    if "planning.admin" not in (await load_access(db, user)).perms:
        raise HTTPException(403, {"message": "moving despite a conflict is admin-only", "rules": rules})
    if not publish_guard.valid_reason(reason):
        raise HTTPException(
            422,
            {
                "message": f"forcing a move that breaks {', '.join(rules)} needs a written reason",
                "rules": rules,
                "conflicts": [c.get("message") for c in conflicts],
            },
        )


async def _date_of(db: AsyncSession, run: ScheduleRun, week: int, day: int) -> Any:
    from app.models import Week
    from app.services.calendar import date_for

    term = await db.get(Term, run.term_id)
    if term is None:
        return None
    rows = list((await db.execute(select(Week).where(Week.term_id == term.id))).scalars())
    return date_for(term, week, day, rows)


async def _rescore(db: AsyncSession, run: ScheduleRun) -> Any:
    """Re-validate ``run`` at planner level after an edit: the hard score counts the placed requests that
    break a rule outside the reported exceptions (a manual placement is one); OPTIMAL is no longer proven;
    a run that now places every request is no longer partial (review M4)."""
    from app.services.planner_check import check_run
    from app.services.run_params import trusted_studio_snapshot

    check = await check_run(db, run)
    from app.services import publish_guard

    await publish_guard.refresh_overrides(db, run)  # a forced placement that was undone no longer counts
    integ = publish_guard.integrity(check, run)
    before_hard = run.hard_score
    # manual hard-rule breaks count, explained (forced with a reason) or not (persona M-02)
    run.hard_score = integ["hard_score"]
    if run.status == "OPTIMAL":
        run.status = "FEASIBLE"
    if run.status in ("FEASIBLE", PARTIAL_STATUS) and trusted_studio_snapshot(run) is None:
        # (a studio run leaves the draft's excluded classes out on purpose: its placement status stays)
        run.status = PARTIAL_STATUS if check.requests_placed < check.requests_total else "FEASIBLE"
    run.stats = {
        **(run.stats or {}),
        "planner_check": check.summary(),
        "integrity": {k: integ[k] for k in ("hard_score", "overrides")}
        | {
            "blocking": len(integ["blocking"]),
            "explained": len(integ["explained"]),
            # round-1 R1-M-05: the broken hard rules themselves, never only a lower number
            "broken": publish_guard.broken_rules(integ, run),
        },
        "manual_edits": int((run.stats or {}).get("manual_edits") or 0) + 1,
    }
    from app.services import run_truth

    run.stats = {**run.stats, "truth": run_truth.build(run, check)}
    if before_hard != run.hard_score:
        # the score change is an audited fact with its cause (published or not)
        await audit.record(
            db,
            "run.hard_score",
            "schedule_run",
            run.id,
            before={"hard_score": before_hard},
            after={
                "hard_score": run.hard_score,
                "is_active": bool(run.is_active),
                "broken": run.stats["integrity"]["broken"][:20],
            },
            term_id=run.term_id,
        )
    return check


@router.post("/{run_id}/assignments/{aid}/lock", response_model=AssignmentOut)
async def lock_assignment(run_id: int, aid: int, db: DB, user: Planner, locked: bool = True) -> AssignmentOut:
    run = await _run(db, run_id)
    a = await _assignment(db, run_id, aid)
    was = bool(a.is_locked)
    a.is_locked = locked
    if was != locked:
        await record_assignments(
            db,
            "assignment.lock" if locked else "assignment.unlock",
            run,
            [(a.id, {"is_locked": was}, {"is_locked": locked})],
            actor=user,
        )
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
    # audit coverage: a fix button changes requests / rules / locks of the term
    await publish_event(
        db,
        "run.fix",
        "run",
        run.id,
        after={
            "diagnosis": idx,
            "option": body.option_index,
            "action": res.action,
            "message": res.message,
            "details": res.details,
            "constraint_id": res.constraint_id,
            "re_solve": body.re_solve,
        },
        actor=user,
        term_id=run.term_id,
    )
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
    # round-1 R1-M-04: the verdict comes from the planner-level check of the stored rows (``run_truth``), the same
    # object the run card and GET /runs/{id} (``stats.truth``) show
    from app.services import run_truth

    truth = await run_truth.run_truth(db, run)
    if truth["verdict"] == "none":
        headline = {"tr": f"Durum: {run.status}", "en": f"Status: {run.status}"}
    else:
        headline = dict(truth["headline"])
        stored = (run.stats or {}).get("truth")
        if not isinstance(stored, dict) or stored.get("verdict") != truth["verdict"]:
            run.stats = {**(run.stats or {}), "truth": truth}
            await db.commit()
    # persona M-07: the summary counts the planner's data issues (an imported board said "Sorunlar 0" while the
    # data-issues report listed its too-small locked rooms)
    from app.services.data_issues import build_data_issues

    issues = (await build_data_issues(db, run)).get("totals") or {}
    n_issues = int(issues.get("issues") or 0)
    if n_issues:
        headline = {
            "tr": f"{headline['tr']} · {n_issues} veri sorunu",
            "en": f"{headline['en']} · {n_issues} data issues",
        }
    overrides = (run.stats or {}).get("forced_overrides") or []
    if overrides:
        headline = {
            "tr": f"{headline['tr']} · {len(overrides)} gerekçeli zorunlu taşıma",
            "en": f"{headline['en']} · {len(overrides)} forced move(s) with a reason",
        }
    return {
        "truth": truth,
        "data_issues": {"issues": n_issues, "by_group": issues.get("by_group") or {}},
        "forced_overrides": overrides,
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
