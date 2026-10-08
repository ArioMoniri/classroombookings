"""Ingestion Council API: upload any files, watch the council per file and step, review, commit.

POST /council/jobs                  multipart files[] (+ mode, lang, year_hint, ai)  -> 202 job
GET  /council/jobs                  recent jobs
GET  /council/jobs/{id}             progress per file and step, plan, summary, usage
GET  /council/jobs/{id}/events      server-sent events (snapshot on every change) until done
GET  /council/jobs/{id}/review      review items (low confidence, merges, issues, rules, plan)
POST /council/jobs/{id}/review      decisions: accept / reject / edit
POST /council/jobs/{id}/commit      write into a term (planner group, existing term or new term)
POST /council/jobs/{id}/rerun       run the council again on the stored files (new attempt)
GET  /council/jobs/{id}/records     extracted records of one file (paged), with source references
GET  /council/jobs/{id}/artifacts   audit trail: artifact metadata (kind, file, step, time, size)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DB, Planner, Viewer
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.council import storage
from app.council.commit import CommitError, commit
from app.council.orchestrator import enqueue
from app.council.review import _threshold, apply_decisions, build_items, decisions, effective_plan
from app.models import CouncilArtifact, CouncilJob
from app.schemas.council import (
    CommitIn,
    CouncilFileOut,
    CouncilJobBrief,
    CouncilJobOut,
    CouncilStepOut,
    RerunIn,
    ReviewIn,
    ReviewOut,
)
from app.workers.queue import get_queue, worker_id

router = APIRouter(prefix="/council", tags=["council"])

TERMINAL = {"REVIEW", "READY", "COMMITTED", "FAILED"}


async def _job(db: DB, job_id: int) -> CouncilJob:
    job = await db.get(CouncilJob, job_id)
    if job is None:
        raise HTTPException(404, "council job not found")
    return job


async def job_out(db: DB, job: CouncilJob) -> CouncilJobOut:
    steps = await storage.steps(db, job.id)
    by_file: dict[int, list[CouncilStepOut]] = {}
    cross: list[CouncilStepOut] = []
    for s in steps:
        out = CouncilStepOut.model_validate(s)
        if s.file_index is None:
            cross.append(out)
        else:
            by_file.setdefault(s.file_index, []).append(out)
    st = get_queue().state(f"council:{job.id}")
    progress = 100 if job.status in TERMINAL else (st.progress if st else 0)
    files = [
        CouncilFileOut(
            **{k: v for k, v in f.items() if k in CouncilFileOut.model_fields}, steps=by_file.get(f["index"], [])
        )
        for f in job.files
    ]
    return CouncilJobOut(
        id=job.id,
        status=job.status,
        mode=job.mode,
        ai_mode=job.ai_mode,
        lang=job.lang,
        year_hint=job.year_hint,
        progress=progress,
        phase=st.phase if st and job.status not in TERMINAL else None,
        files=files,
        cross_steps=cross,
        plan=job.plan,
        summary=job.summary or {},
        usage=job.usage or {},
        commits=job.commits or [],
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.post("/jobs", response_model=CouncilJobOut, status_code=202)
async def create_job(
    db: DB,
    user: Planner,
    files: list[UploadFile] = File(..., description="any number of schedule files, any format"),
    mode: str = Form("auto", description="auto (fast path for known shapes) | general (council for every file)"),
    lang: str = Form("en"),
    year_hint: int | None = Form(None),
    ai: bool = Form(True, description="false = deterministic path only, even with a key"),
    review_threshold: float | None = Form(None, ge=0.0, le=1.0, description="default COUNCIL_REVIEW_THRESHOLD"),
) -> CouncilJobOut:
    st = get_settings()
    if mode not in ("auto", "general"):
        raise HTTPException(400, "mode must be auto or general")
    if not files:
        raise HTTPException(400, "upload at least one file")
    if len(files) > st.council_max_files:
        raise HTTPException(413, f"at most {st.council_max_files} files per job")
    blobs: list[tuple[str, bytes]] = []
    limit = st.council_max_file_mb * 1024 * 1024
    for f in files:
        data = await f.read()
        if len(data) > limit:
            raise HTTPException(413, f"{f.filename}: larger than {st.council_max_file_mb} MiB")
        if not data:
            raise HTTPException(400, f"{f.filename}: empty file")
        blobs.append((f.filename or f"upload-{len(blobs)}", data))
    job = CouncilJob(
        status="QUEUED",
        mode=mode,
        lang=lang[:8] or "en",
        year_hint=year_hint,
        files=[],
        settings={"ai": ai, "worker": worker_id(), "review_threshold": review_threshold},
        summary={},
        usage={},
        commits=[],
        created_by=user.id,
    )
    db.add(job)
    await db.flush()
    entries = []
    for i, (name, data) in enumerate(blobs):
        stored = storage.save_upload(job.id, i, name, data)
        entries.append(
            {
                "index": i,
                "filename": name,
                "stored": stored,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "status": "QUEUED",
            }
        )
    job.files = entries
    await db.commit()
    await db.refresh(job)
    enqueue(job.id)
    return await job_out(db, job)


@router.get("/jobs", response_model=list[CouncilJobBrief])
async def list_jobs(db: DB, _: Viewer, limit: int = 30) -> list[CouncilJobBrief]:
    rows = (await db.execute(select(CouncilJob).order_by(CouncilJob.id.desc()).limit(min(limit, 200)))).scalars()
    return [
        CouncilJobBrief(
            id=j.id,
            status=j.status,
            files=len(j.files),
            ai_mode=j.ai_mode,
            created_at=j.created_at,
            summary=j.summary or {},
        )
        for j in rows
    ]


@router.get("/jobs/{job_id}", response_model=CouncilJobOut)
async def get_job(job_id: int, db: DB, _: Viewer) -> CouncilJobOut:
    return await job_out(db, await _job(db, job_id))


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int, db: DB, _: Viewer) -> StreamingResponse:
    """SSE: ``event: snapshot`` with the full job (as ``GET /council/jobs/{id}``) whenever a step or file
    changes, ``: keep-alive`` comments in between, and ``event: done`` when the job stops running."""
    await _job(db, job_id)
    factory = get_session_factory()

    async def gen() -> Any:
        last = ""
        idle = 0
        while True:
            async with factory() as s:
                job = await s.get(CouncilJob, job_id)
                if job is None:
                    break
                out = (await job_out(s, job)).model_dump(mode="json")
            body = json.dumps(out, ensure_ascii=False)
            digest = hashlib.sha1(body.encode()).hexdigest()
            if digest != last:
                last, idle = digest, 0
                yield f"event: snapshot\ndata: {body}\n\n"
            else:
                idle += 1
                if idle % 8 == 0:
                    yield ": keep-alive\n\n"
            if out["status"] in TERMINAL:
                yield f"event: done\ndata: {json.dumps({'id': job_id, 'status': out['status']})}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


async def _review_out(db: DB, job: CouncilJob, **extra: Any) -> ReviewOut:
    items = await build_items(db, job)
    plan = effective_plan(job.plan or {}, await decisions(db, job.id)) if job.plan else None
    blocking = sum(1 for it in items if it["blocking"] and it["decision"] is None)
    return ReviewOut(
        job_id=job.id, status=job.status, blocking=blocking, items=items, plan=plan, threshold=_threshold(job), **extra
    )


@router.get("/jobs/{job_id}/review", response_model=ReviewOut)
async def get_review(job_id: int, db: DB, _: Viewer) -> ReviewOut:
    return await _review_out(db, await _job(db, job_id))


@router.post("/jobs/{job_id}/review", response_model=ReviewOut)
async def post_review(job_id: int, body: ReviewIn, db: DB, user: Planner) -> ReviewOut:
    job = await _job(db, job_id)
    if job.status not in ("REVIEW", "READY", "COMMITTED"):
        raise HTTPException(409, f"job is {job.status}; review opens when the council has finished")
    res = await apply_decisions(db, job, [d.model_dump() for d in body.decisions], user.id)
    await db.refresh(job)
    return await _review_out(db, job, saved=res["saved"], errors=res["errors"], rerun_files=res["rerun_files"])


@router.post("/jobs/{job_id}/commit")
async def post_commit(job_id: int, body: CommitIn, db: DB, user: Planner) -> dict[str, Any]:
    job = await _job(db, job_id)
    try:
        return await commit(
            db,
            job,
            group=body.group,
            term_id=body.term_id,
            term_spec=body.term.model_dump(mode="json", exclude_none=True) if body.term else None,
            files=body.files,
            include_rules=body.include_rules,
            allow_pending=body.allow_pending,
            user_id=user.id,
        )
    except CommitError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/jobs/{job_id}/rerun", response_model=CouncilJobOut, status_code=202)
async def rerun(job_id: int, db: DB, _: Planner, body: RerunIn | None = None) -> CouncilJobOut:
    job = await _job(db, job_id)
    if job.status in ("QUEUED", "RUNNING"):
        raise HTTPException(409, "the council is still running")
    if body and body.mode:
        job.mode = body.mode
    if body and body.ai is not None:
        job.settings = {**(job.settings or {}), "ai": body.ai}
    job.status = "QUEUED"
    job.files = [{**f, "status": "QUEUED"} for f in job.files]
    await db.commit()
    enqueue(job.id)
    await db.refresh(job)
    return await job_out(db, job)


@router.get("/jobs/{job_id}/records")
async def get_records(
    job_id: int, db: DB, _: Viewer, file: int, type: str | None = None, offset: int = 0, limit: int = 100
) -> dict[str, Any]:
    await _job(db, job_id)
    art = await storage.latest(db, job_id, "records", file)
    if art is None:
        raise HTTPException(404, "no records for this file yet")
    recs = [r for r in art.payload.get("records", []) if type is None or r["type"] == type]
    limit = max(1, min(limit, 500))
    return {"total": len(recs), "offset": offset, "limit": limit, "items": recs[offset : offset + limit],
            "counts": art.payload.get("counts", {}), "route": art.payload.get("route")}  # fmt: skip


@router.get("/jobs/{job_id}/artifacts")
async def get_artifacts(job_id: int, db: DB, _: Viewer, kind: str | None = None) -> list[dict[str, Any]]:
    await _job(db, job_id)
    q = select(CouncilArtifact).where(CouncilArtifact.job_id == job_id)
    if kind:
        q = q.where(CouncilArtifact.kind == kind)
    rows = (await db.execute(q.order_by(CouncilArtifact.id))).scalars()
    return [
        {
            "id": a.id,
            "kind": a.kind,
            "file_index": a.file_index,
            "step_id": a.step_id,
            "confidence": a.confidence,
            "created_at": a.created_at.isoformat(),
            "bytes": len(json.dumps(a.payload, ensure_ascii=False)),
            "payload": a.payload if a.kind in ("plan", "review", "commit", "rendered", "issues") else None,
        }
        for a in rows
    ]
