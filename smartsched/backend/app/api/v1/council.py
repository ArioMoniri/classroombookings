"""Ingestion Council API: upload any files, watch the council per file and step, review, commit.

POST /council/jobs                  multipart files[] (+ mode, lang, year_hint, ai)  -> 202 job
GET  /council/jobs                  recent jobs
GET  /council/jobs/{id}             progress per file and step, plan, summary, usage
GET  /council/jobs/{id}/events      server-sent events (snapshot on every change) until done
GET  /council/jobs/{id}/review      review items (low confidence, merges, issues, rules, plan)
POST /council/jobs/{id}/review      decisions: accept / reject / edit
POST /council/jobs/{id}/commit      write into a term (planner group, existing term or new term); dry_run = diff only
POST /council/jobs/{id}/rerun       run the council again on the stored files (new attempt)
GET  /council/jobs/{id}/records     extracted records of one file (paged), with source references
GET  /council/jobs/{id}/artifacts   audit trail: artifact metadata (kind, file, step, time, size)
GET  /council/memory                intake memory: remembered decisions, grouped by signature (TR / EN text)
DELETE /council/memory/{id}         forget one remembered decision (a learning reset of scope intake, undoable)
DELETE /council/memory?signature=   forget every remembered decision of one signature

Guards (app/api/deps.py, role permissions + token revocation): reading a job, its events and its review needs
``planning.view``; uploading, deciding, committing, re-running and reading the extracted records or artifact
payloads (file content) needs ``planning.edit`` - the same split as ``/imports`` (its file download is
``planning.edit`` too). The intake memory list needs ``planning.view`` (headers, merge names and rule texts for
``planning.edit`` only); forgetting needs ``planning.edit`` (the review's permission). Uploads follow
``app/core/safe_files.py`` (byte caps, OOXML inspection); a commit is one ``council.commit`` audit event
(``app/services/events.py``).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentAccess, Planner, Viewer
from app.api.v1.imports import locked_409
from app.core import safe_files
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.council import airows, formats, formats_mail, i18n, memory_admin, storage
from app.council import text as tx
from app.council.commit import CommitError, commit
from app.council.dryrun import dry_run
from app.council.orchestrator import enqueue
from app.council.render import RenderError
from app.council.review import _threshold, apply_decisions, build_items, decisions, effective_plan
from app.models import CouncilArtifact, CouncilJob, Term
from app.schemas.council import (
    CommitIn,
    CouncilFileOut,
    CouncilJobBrief,
    CouncilJobOut,
    CouncilStepOut,
    RerunIn,
    ReviewIn,
    ReviewOut,
    RowDecisionsIn,
)
from app.services import term_lock
from app.workers.queue import get_queue, worker_id

router = APIRouter(prefix="/council", tags=["council"])

TERMINAL = {"REVIEW", "READY", "COMMITTED", "FAILED"}


async def _job(db: DB, job_id: int) -> CouncilJob:
    job = await db.get(CouncilJob, job_id)
    if job is None:
        raise HTTPException(404, "council job not found")
    return job


def _lang(job: CouncilJob, lang: str | None) -> str:
    """The reader's language: ``?lang=`` or the language the job was started in (T-R1-23)."""
    return (lang or job.lang or "en")[:8]


async def job_out(db: DB, job: CouncilJob, lang: str | None = None) -> CouncilJobOut:
    """The job for a reader of ``lang`` (default: the job's): the council's messages in Turkish for ``tr``."""
    lg = _lang(job, lang)
    steps = await storage.steps(db, job.id)
    by_file: dict[int, list[CouncilStepOut]] = {}
    cross: list[CouncilStepOut] = []
    for s in steps:
        out = CouncilStepOut.model_validate(s)
        out.message = i18n.localize(out.message, lg)
        if s.file_index is None:
            cross.append(out)
        else:
            by_file.setdefault(s.file_index, []).append(out)
    st = get_queue().state(f"council:{job.id}")
    progress = 100 if job.status in TERMINAL else (st.progress if st else 0)
    files = [
        CouncilFileOut(
            **{k: v for k, v in f.items() if k in CouncilFileOut.model_fields and k != "message"},
            message=i18n.localize(f.get("message"), lg),
            steps=by_file.get(f["index"], []),
        )
        for f in job.files
    ]
    summary = dict(job.summary or {})
    if isinstance(summary.get("ai"), str):
        summary["ai"] = i18n.localize(summary["ai"], lg)
    return CouncilJobOut(
        id=job.id,
        status=job.status,
        mode=job.mode,
        ai_mode=job.ai_mode,
        lang=job.lang,
        year_hint=job.year_hint,
        progress=progress,
        phase=i18n.localize(st.phase, lg) if st and job.status not in TERMINAL else None,
        files=files,
        cross_steps=cross,
        plan=job.plan,
        summary=summary,
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
    # the same intake rules as /imports (app/core/safe_files.py): each upload streamed to disk with a byte cap,
    # a readable type, and OOXML containers (by extension or sniffed) inspected before any parser sees them
    limit = int(min(float(st.council_max_file_mb), float(st.upload_max_mb)) * safe_files.MiB)
    job_limit = int(float(st.council_max_job_mb) * safe_files.MiB)
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
    entries: list[dict[str, Any]] = []
    total = 0

    async def admit(name: str, stored: str, size: int, data: bytes, parent: int | None = None) -> str:
        """Precheck one stored file and add it to the job (attachments too); returns its format."""
        nonlocal total
        total += size
        if total > job_limit:
            raise HTTPException(413, f"the files of one job may total at most {st.council_max_job_mb} MiB")
        if len(entries) >= st.council_max_files:
            raise HTTPException(413, f"at most {st.council_max_files} files per job (attachments included)")
        try:
            # magic-byte detection + the format's caps (zip bombs, ODS repeat bombs, XML entities, JSON
            # depth, ICS expansion, image pixels) in the rlimit child, before a job exists (app/council/formats.py)
            fmt = await safe_files.run_isolated(formats.precheck, name, data)
        except RenderError as exc:
            raise HTTPException(400, f"{name}: {exc}") from exc
        except safe_files.UnsafeFileError as exc:
            raise HTTPException(exc.status, f"{name}: {exc.message}") from exc
        entries.append(
            {
                "index": len(entries),
                "filename": name,
                "stored": stored,
                "size": size,
                "sha256": hashlib.sha256(data).hexdigest(),
                "format": fmt,
                "route_kind": formats.route_of(fmt),
                "status": "QUEUED",
                **({"parent": parent} if parent is not None else {}),
            }
        )
        return fmt

    try:
        for i, f in enumerate(files):
            name = f.filename or f"upload-{i}"
            index = len(entries)
            stored = storage.stored_name(index, name)
            target = storage.job_dir(job.id) / stored
            try:
                size = await safe_files.save_upload(f, target, limit)
            except safe_files.UnsafeFileError as exc:
                raise HTTPException(exc.status, f"{name}: {exc.message}") from exc
            if not size:
                raise HTTPException(400, f"{name}: empty file")
            data = target.read_bytes()  # at most `limit` bytes
            fmt = await admit(name, stored, size, data)
            if fmt != "eml":
                continue
            # e-mail attachments re-enter the registry as files of this job (depth 1, at most 10; P19-A3)
            for att_name, att in await safe_files.run_isolated(formats_mail.attachments, data):
                if len(att) > limit:
                    raise HTTPException(413, f"{name}: attachment {att_name} is larger than the per-file limit")
                child = f"{name} - {att_name}"
                child_stored = storage.stored_name(len(entries), child)
                (storage.job_dir(job.id) / child_stored).write_bytes(att)
                await admit(child, child_stored, len(att), att, parent=index)
    except BaseException:
        await db.rollback()  # the job row was only flushed: a refused upload leaves no job and no file
        shutil.rmtree(storage.job_dir(job.id), ignore_errors=True)
        raise
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
async def get_job(job_id: int, db: DB, _: Viewer, lang: str | None = None) -> CouncilJobOut:
    return await job_out(db, await _job(db, job_id), lang)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int, db: DB, _: Viewer, lang: str | None = None) -> StreamingResponse:
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
                out = (await job_out(s, job, lang)).model_dump(mode="json")
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


#: review item keys that carry file content (cell values, rule texts, names in merges): planning.edit only
CONTENT_KEYS = ("samples", "text", "texts", "sources", "evidence", "source", "alternatives")


def _redact(item: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in item.items() if k not in CONTENT_KEYS}
    if item.get("kind") == "merge":  # the two spellings are names of people or rooms
        out["current"] = {k: v for k, v in (item.get("current") or {}).items() if k in ("kind", "score")}
        out["title"] = f"Same {(item.get('current') or {}).get('kind', 'entity')}?"
    if item.get("kind") in ("issue", "rule", "rule_text", "file"):
        out["title"] = {"issue": "Finding", "rule": "Rule proposal", "rule_text": "Rule-like texts", "file": "File"}[
            item["kind"]
        ]
        if item.get("kind") == "rule":
            out["current"] = {k: v for k, v in (item.get("current") or {}).items() if k != "nl_text"}
    if item.get("kind") == "mapping":
        out["title"] = f"column {item.get('column')} -> {(item.get('current') or {}).get('field') or '(not used)'}?"
    return out


async def _review_out(
    db: DB, job: CouncilJob, *, content: bool = True, lang: str | None = None, **extra: Any
) -> ReviewOut:
    items = await build_items(db, job)
    plan = effective_plan(job.plan or {}, await decisions(db, job.id)) if job.plan else None
    blocking = sum(1 for it in items if it["blocking"] and it["decision"] is None)
    if not content:
        items = [_redact(it) for it in items]
        if plan:
            plan = {**plan, "groups": [{**g, "evidence": []} for g in plan.get("groups", [])]}
    lg = _lang(job, lang)
    items = [i18n.localize_item(it, lg) for it in items]
    return ReviewOut(
        job_id=job.id,
        status=job.status,
        blocking=blocking,
        items=items,
        plan=plan,
        threshold=_threshold(job),
        content=content,
        **extra,
    )


@router.get("/jobs/{job_id}/review", response_model=ReviewOut)
async def get_review(job_id: int, db: DB, _: Viewer, access: CurrentAccess, lang: str | None = None) -> ReviewOut:
    """Review items. Sample cell values, rule texts, sources and the names of merge pairs are file content
    (names, notes): they are returned to planning.edit only, like ``/records``; viewers see the items' kinds,
    confidences and decisions."""
    return await _review_out(db, await _job(db, job_id), content=access.can("planning.edit"), lang=lang)


@router.post("/jobs/{job_id}/review", response_model=ReviewOut)
async def post_review(job_id: int, body: ReviewIn, db: DB, user: Planner, lang: str | None = None) -> ReviewOut:
    """Decide items (one ``council.review`` audit event). A mapping or classification change queues the
    deterministic re-read of its files (``rerun_queued``); the job is ``RUNNING`` until it has finished (watch
    ``GET /council/jobs/{id}/events``)."""
    job = await _job(db, job_id)
    if job.status not in ("REVIEW", "READY", "COMMITTED"):
        raise HTTPException(409, f"job is {job.status}; review opens when the council has finished")
    res = await apply_decisions(db, job, [d.model_dump() for d in body.decisions], user)
    await db.refresh(job)
    return await _review_out(
        db,
        job,
        lang=lang,
        saved=res["saved"],
        errors=res["errors"],
        rerun_files=res["rerun_files"],
        rerun_queued=res["rerun_queued"],
    )


async def _commit_term_code(db: DB, job: CouncilJob, body: CommitIn) -> str | None:
    """The code of the term a commit writes (for its write lock): the chosen term, the new term's code, or the
    planner group's (as reviewed)."""
    if body.term_id is not None:
        term = await db.get(Term, body.term_id)
        return term.code if term is not None else None
    if body.term is not None and body.term.code:
        return body.term.code
    groups = effective_plan(job.plan or {}, await decisions(db, job.id)).get("groups", [])
    if body.group is not None and 0 <= body.group < len(groups):
        return str(groups[body.group].get("code") or "") or None
    if body.group is None and not body.files and len(groups) == 1:
        return str(groups[0].get("code") or "") or None
    return None


@router.post("/jobs/{job_id}/commit")
async def post_commit(job_id: int, body: CommitIn, db: DB, user: Planner) -> dict[str, Any]:
    """Write the job into a term. ``dry_run`` runs the same importers and writer in a transaction that is
    rolled back and answers the per-entity create / update / unchanged / conflict counts with the row diffs
    (app/council/dryrun.py). A real commit holds the term's write lock (app/services/term_lock.py): while an
    import or another commit writes the same term, it answers 409 ``term_locked``."""
    job = await _job(db, job_id)
    kwargs: dict[str, Any] = dict(
        group=body.group,
        term_id=body.term_id,
        term_spec=body.term.model_dump(mode="json", exclude_none=True) if body.term else None,
        files=body.files,
        include_rules=body.include_rules,
        allow_pending=body.allow_pending,
        user_id=user.id,
        on_conflict=body.on_conflict,
        baseline=body.baseline.model_dump(),
    )
    try:
        if body.dry_run:
            return await dry_run(get_session_factory(), job.id, **kwargs)
        code = await _commit_term_code(db, job, body)
        if code is None:  # no term to lock: commit() refuses with the reason
            return await commit(db, job, actor=user, **kwargs)
        key = term_lock.term_key(code)
        async with term_lock.term_write_lock(key, f"council-commit:{job.id}"):
            return await commit(db, job, actor=user, **kwargs)
    except term_lock.TermLocked as exc:
        raise locked_409(exc) from exc  # the imports' 409: holder and since when, TR + EN
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


@router.get("/jobs/{job_id}/rows")
async def get_rows(
    job_id: int,
    db: DB,
    _: Planner,
    state: str | None = None,
    method: str | None = None,
    file: int | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Cross-file review rows (P19-I-01 / P19-A2): state pending | ready | accepted | edited | rejected, method
    direct | ai, confidence, provenance and values. File content: planners only, like ``/records``."""
    job = await _job(db, job_id)
    all_rows = await airows.rows(db, job)
    sel = [
        r
        for r in all_rows
        if (state is None or r["state"] == state)
        and (method is None or r["method"] == method)
        and (file is None or r["file_index"] == file)
        and (not q or tx.fold(q) in tx.fold(json.dumps(r["values"], ensure_ascii=False)))
    ]
    limit = max(1, min(limit, 500))
    return {
        "total": len(sel),
        "offset": offset,
        "limit": limit,
        "items": sel[offset : offset + limit],
        "counts": airows.counts(all_rows),
        "bulk_max": airows.BULK_MAX,
    }


@router.post("/jobs/{job_id}/rows/decisions")
async def post_row_decisions(job_id: int, body: RowDecisionsIn, db: DB, user: Planner) -> dict[str, Any]:
    """Accept / edit / reject rows. Rows read by the AI model: at most 50 in one call and only with
    ``confirm=true``; a low-confidence AI row is decided on its own (owner decision 2026-10-15)."""
    job = await _job(db, job_id)
    if job.status not in ("REVIEW", "READY", "COMMITTED"):
        raise HTTPException(409, f"job is {job.status}; rows can be decided when the council has finished")
    try:
        res = await airows.decide(db, job, [d.model_dump() for d in body.decisions], user, confirm=body.confirm)
    except airows.RowDecisionError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.refresh(job)
    all_rows = await airows.rows(db, job)
    return {**res, "status": job.status, "counts": airows.counts(all_rows)}


@router.get("/jobs/{job_id}/records")
async def get_records(
    job_id: int, db: DB, _: Planner, file: int, type: str | None = None, offset: int = 0, limit: int = 100
) -> dict[str, Any]:
    """The extracted rows (names, e-mails, rooms as written in the file): planners only, like an import's file."""
    await _job(db, job_id)
    art = await storage.latest(db, job_id, "records", file)
    if art is None:
        raise HTTPException(404, "no records for this file yet")
    recs = [r for r in art.payload.get("records", []) if type is None or r["type"] == type]
    limit = max(1, min(limit, 500))
    return {"total": len(recs), "offset": offset, "limit": limit, "items": recs[offset : offset + limit],
            "counts": art.payload.get("counts", {}), "route": art.payload.get("route")}  # fmt: skip


@router.get("/jobs/{job_id}/artifacts")
async def get_artifacts(job_id: int, db: DB, _: Planner, kind: str | None = None) -> list[dict[str, Any]]:
    """Payloads hold file content (rendered sheets): planners only."""
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


# --------------------------------------------------------------------------- intake memory


def _memory_error(exc: memory_admin.IntakeMemoryError) -> HTTPException:
    return HTTPException(exc.status, exc.detail)


@router.get("/memory")
async def list_memory(
    db: DB,
    _: Viewer,
    access: CurrentAccess,
    signature: str | None = None,
    kind: str | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    """What the intake remembers (app/council/memory_admin.py): rows with a TR / EN description and the groups,
    one per signature; ``effective`` marks the row the next matching upload is offered."""
    from app.council import memory

    if await memory.scrub_legacy(db):  # merge rows written before T-R1-22 held the two names in their item id
        await db.commit()
    try:
        return await memory_admin.listing(
            db, signature=signature, kind=kind, job_id=job_id, content=access.can("planning.edit")
        )
    except memory_admin.IntakeMemoryError as exc:
        raise _memory_error(exc) from exc


@router.delete("/memory/{row_id}")
async def forget_memory_row(row_id: int, db: DB, user: Planner, reason: str | None = None) -> dict[str, Any]:
    """Forget one remembered decision: a learning reset of scope ``intake`` (undo for 30 days, audited)."""
    try:
        out = await memory_admin.forget_one(db, user, row_id, reason)
    except memory_admin.IntakeMemoryError as exc:
        raise _memory_error(exc) from exc
    await db.commit()
    return out


@router.delete("/memory")
async def forget_memory_signature(db: DB, user: Planner, signature: str, reason: str | None = None) -> dict[str, Any]:
    """Forget every remembered decision of one signature (one reset, one audit event)."""
    try:
        out = await memory_admin.forget_signature(db, user, signature, reason)
    except memory_admin.IntakeMemoryError as exc:
        raise _memory_error(exc) from exc
    await db.commit()
    return out
