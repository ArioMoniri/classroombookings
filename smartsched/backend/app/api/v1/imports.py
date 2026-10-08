from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import DB, Planner, Viewer
from app.core import safe_files
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.importers.report import ImportReport
from app.models import ImportJob
from app.schemas.runs import ImportJobOut
from app.workers.queue import JobState, get_queue, worker_id

router = APIRouter(prefix="/imports", tags=["imports"])

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _job_files(job_id: int) -> list[Path]:
    return sorted((Path(get_settings().upload_dir) / "imports").glob(f"{job_id}_*"))


def _cleanup(job_id: int) -> None:
    """Remove the uploaded files of a job (failed or refused imports keep nothing on disk)."""
    for f in _job_files(job_id):
        f.unlink(missing_ok=True)


async def _save_upload(db: DB, job: ImportJob, file: UploadFile, *, full_load: bool = False) -> Path:
    """Stream the upload to disk with the size cap and pre-inspect OOXML containers (review B1). A refused
    file is deleted, its job marked FAILED and the client gets 413 / 400."""
    target_dir = Path(get_settings().upload_dir) / "imports"
    name = _SAFE.sub("_", file.filename or "upload.bin")
    target = target_dir / f"{job.id}_{name}"
    try:
        await safe_files.save_upload(file, target)
        await safe_files.precheck_upload(target, file.filename, full_load=full_load)
    except safe_files.UnsafeFileError as exc:
        _cleanup(job.id)
        job.status, job.error, job.finished_at = "FAILED", exc.message, utcnow()
        await db.commit()
        raise HTTPException(exc.status, exc.message) from exc
    return target


async def _start_job(db: DB, job: ImportJob, run: Any) -> ImportJob:
    factory = get_session_factory()

    async def body(progress: Any) -> dict[str, Any]:
        progress("importing", 10)
        try:
            async with factory() as session:
                report: ImportReport = await run(session)
        except safe_files.UnsafeFileError as exc:
            _cleanup(job.id)
            raise ValueError(exc.message) from exc
        except Exception:
            _cleanup(job.id)  # failed imports keep no workbook on disk (review MINOR 1)
            raise
        return report.to_dict()

    async def on_status(st: JobState) -> None:
        async with factory() as session:
            row = await session.get(ImportJob, job.id)
            if row is None:
                return
            row.status = {"RUNNING": "RUNNING", "DONE": "DONE", "FAILED": "FAILED"}.get(st.status, st.status)
            if st.result:
                row.summary = st.result
            if st.error:
                # short and path-free; the traceback is in the server log under the job key
                row.error = f"import job {job.id} failed: {st.error} (details in the server log)"
            if st.finished_at:
                row.finished_at = st.finished_at.replace(tzinfo=None)
            await session.commit()

    get_queue().enqueue(f"import:{job.id}", body, on_status=on_status)
    return job


async def _new_job(db: DB, kind: str, filename: str | None, term_code: str | None) -> ImportJob:
    job = ImportJob(kind=kind, filename=filename, term_code=term_code, status="QUEUED", summary={"worker": worker_id()})
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/planning-list", response_model=ImportJobOut, status_code=202)
async def import_planning(
    db: DB,
    _: Planner,
    file: UploadFile = File(...),
    term_code: str = Form(...),
    week_count: int = Form(14),
    on_conflict: str = Form("keep", pattern="^(keep|take)$"),
) -> ImportJob:
    """Re-imports keep planner edits of fields the file also changed (``on_conflict=keep``, reported in
    ``summary.extra.conflicts``) or apply the file (``take``)."""
    from app.importers.planning_list import import_planning_list

    job = await _new_job(db, "planning-list", file.filename, term_code)
    path = await _save_upload(db, job, file)
    return await _start_job(
        db,
        job,
        lambda s: import_planning_list(
            s, path, term_code, filename=file.filename, week_count=week_count, on_conflict=on_conflict
        ),
    )


@router.post("/exam-list", response_model=ImportJobOut, status_code=202)
async def import_exams(db: DB, _: Planner, file: UploadFile = File(...), term_code: str = Form(...)) -> ImportJob:
    from app.importers.exam_list import import_exam_list

    job = await _new_job(db, "exam-list", file.filename, term_code)
    path = await _save_upload(db, job, file)
    return await _start_job(db, job, lambda s: import_exam_list(s, path, term_code, filename=file.filename))


@router.post("/weekly-grid", response_model=ImportJobOut, status_code=202)
async def import_grid(
    db: DB,
    _: Planner,
    file: UploadFile = File(...),
    term_code: str = Form(...),
    year: int = Form(...),
    term_kind: str | None = Form(None),
) -> ImportJob:
    from app.importers.weekly_grid import import_weekly_grid

    job = await _new_job(db, "weekly-grid", file.filename, term_code)
    path = await _save_upload(db, job, file, full_load=True)
    return await _start_job(
        db,
        job,
        lambda s: import_weekly_grid(s, path, term_code, year=year, filename=file.filename, term_kind=term_kind),
    )


@router.post("/crbs", response_model=ImportJobOut, status_code=202)
async def import_crbs_endpoint(
    db: DB, _: Planner, dsn: str | None = Form(None), files: list[UploadFile] = File(default=[])
) -> ImportJob:
    """Either a MySQL DSN (``mysql://user:pass@host/db``) or one or more SQL dump files."""
    from app.importers.crbs_legacy import import_crbs

    if not dsn and not files:
        raise HTTPException(400, "provide a dsn or SQL dump files")
    job = await _new_job(
        db, "crbs", ", ".join(f.filename or "?" for f in files) if files else dsn.split("@")[-1] if dsn else None, None
    )
    paths = [await _save_upload(db, job, f) for f in files]
    source: Any = dsn if dsn else paths
    return await _start_job(db, job, lambda s: import_crbs(s, source, filename=job.filename))


@router.get("", response_model=list[ImportJobOut])
async def list_jobs(db: DB, _: Viewer, limit: int = 50) -> list[ImportJob]:
    return list((await db.execute(select(ImportJob).order_by(ImportJob.id.desc()).limit(limit))).scalars())


@router.get("/{job_id}", response_model=ImportJobOut)
async def get_job(job_id: int, db: DB, _: Viewer) -> ImportJob:
    job = await db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(404, "import job not found")
    st = get_queue().state(f"import:{job.id}")
    if st and job.status in {"QUEUED", "RUNNING"}:
        job.summary = {**(job.summary or {}), "progress": st.progress, "phase": st.phase}
    return job


@router.get("/{job_id}/file")
async def get_job_file(job_id: int, db: DB, _: Planner, index: int = 0) -> FileResponse:
    """Download the workbook / dump uploaded for an import job (planners only; never public)."""
    job = await db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(404, "import job not found")
    files = _job_files(job_id)
    if not 0 <= index < len(files):
        raise HTTPException(404, "no uploaded file for this job")
    path = files[index]
    return FileResponse(path, filename=path.name.split("_", 1)[1], media_type="application/octet-stream")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
