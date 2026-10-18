from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentAccess, Planner, forbidden, require_permission
from app.core import safe_files
from app.core.db import get_session_factory
from app.importers.detect import WrongFileError
from app.importers.report import ImportReport
from app.models import ImportJob, User
from app.schemas.messages import problem
from app.schemas.runs import ImportJobOut
from app.services import audit, import_jobs, term_lock
from app.workers.queue import JobState, get_queue, worker_id

router = APIRouter(prefix="/imports", tags=["imports"])


def _job_files(job_id: int) -> list[Path]:
    return import_jobs.job_files(job_id)


def _cleanup(job_id: int) -> None:
    """Remove the uploaded files of a job (failed or refused imports keep nothing on disk)."""
    import_jobs.remove_files(job_id)


async def _save_upload(db: DB, job: ImportJob, file: UploadFile, *, full_load: bool = False) -> Path:
    """Stream the upload to disk with the size cap and pre-inspect OOXML containers (review B1). A refused
    file is deleted, its job marked FAILED and the client gets 413 / 400."""
    target = import_jobs.file_target(job.id, file.filename)
    try:
        await safe_files.save_upload(file, target)
        await safe_files.precheck_upload(target, file.filename, full_load=full_load)
    except safe_files.UnsafeFileError as exc:
        _cleanup(job.id)
        job.status, job.error, job.finished_at = "FAILED", exc.message, utcnow()
        await db.commit()
        raise HTTPException(exc.status, exc.message) from exc
    return target


#: how long a queued import waits for another writer of its term (term_lock) before it fails
IMPORT_LOCK_WAIT_S = 900.0


def locked_409(exc: term_lock.TermLocked) -> HTTPException:
    """409 for a term another writer holds (P19-03): the holder and since when, in Turkish and English."""
    err = term_lock.http_error(exc)
    detail = dict(err.detail) if isinstance(err.detail, dict) else {"message": str(exc)}
    since = f" ({exc.since:%Y-%m-%d %H:%M} UTC'den beri)" if exc.since else ""
    term = exc.key.split(":", 1)[-1]
    detail["message_tr"] = (
        f"{term} dönemi şu anda kilitli: {exc.holder or 'başka bir işlem'}{since} bu dönemin verisini yazıyor. "
        "İşlem bitince yeniden deneyin."
    )
    return HTTPException(409, detail)


async def _refuse_if_locked(term_code: str) -> None:
    """A request handler's early 409 when the term is being written (the job itself also waits for the lock)."""
    try:
        await term_lock.assert_unlocked(term_lock.term_key(term_code))
    except term_lock.TermLocked as exc:
        raise locked_409(exc) from exc


async def _start_job(
    db: DB, job: ImportJob, run: Any, *, term_code: str | None = None, dry_run: bool = False
) -> ImportJob:
    """Queue the import. With ``term_code`` the job holds that term's write lock (``term_lock``) for the whole
    import - the API's early check and the worker share the one lock row, so two imports of a term never write
    at once; the lock's heartbeat extends it while a long workbook is parsed, and it is released in ``finally``
    (also when the import fails). ``dry_run`` (RF-06): the importer runs in a transaction that is rolled back and
    the job's summary carries the report and ``diff``; no lock (nothing is written), the file is kept for apply."""
    factory = get_session_factory()

    async def body(progress: Any) -> dict[str, Any]:
        progress("importing", 10)
        try:
            if dry_run:
                async with factory() as session:
                    return await import_jobs.run_preview(session, run)
            if term_code is None:
                async with factory() as session:
                    report: ImportReport = await run(session)
            else:
                progress("waiting for the term lock", 5)
                async with term_lock.term_write_lock(
                    term_lock.term_key(term_code), f"import:{job.id} {job.kind}", wait_s=IMPORT_LOCK_WAIT_S
                ):
                    progress("importing", 10)
                    async with factory() as session:
                        report = await run(session)
        except WrongFileError as exc:
            _cleanup(job.id)
            async with factory() as session:  # the "import it as ..." offer of the import screen (M-20)
                row = await session.get(ImportJob, job.id)
                if row is not None:
                    row.summary = {**(row.summary or {}), "detected_kind": exc.detected, "expected_kind": exc.expected}
                    await session.commit()
            raise ValueError(str(exc)) from exc
        except term_lock.TermLocked as exc:
            _cleanup(job.id)
            raise ValueError(locked_409(exc).detail["message"]) from exc  # type: ignore[index]
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
                row.summary = import_jobs.merged_summary(row.summary, st.result)
            if st.error:
                # short and path-free; the traceback is in the server log under the job key
                row.error = f"import job {job.id} failed: {st.error} (details in the server log)"
            if st.finished_at:
                row.finished_at = st.finished_at.replace(tzinfo=None)
            if row.status in {"DONE", "FAILED"}:
                await import_jobs.audit_run(session, row)  # RF-08: who imported what, and how it ended
            await session.commit()

    get_queue().enqueue(f"import:{job.id}", body, on_status=on_status)
    return job


async def _new_job(
    db: DB,
    kind: str,
    filename: str | None,
    term_code: str | None,
    user: User | None = None,
    *,
    params: dict[str, Any] | None = None,
    dry_run: bool = False,
    preview_of: int | None = None,
) -> ImportJob:
    """The job row: who imports (RF-08: ``created_by_id`` + ``actor``), the importer's parameters (an apply of a
    preview reuses them) and, for a preview, ``dry_run`` / ``applied_job_id``."""
    summary: dict[str, Any] = {"worker": worker_id(), "source": "upload", "params": params or {}}
    if dry_run:
        summary |= {"dry_run": True, "applied_job_id": None}
    if preview_of is not None:
        summary["preview_of"] = preview_of
    job = ImportJob(
        kind=kind,
        filename=filename,
        term_code=term_code,
        status="QUEUED",
        summary=summary,
        created_by_id=user.id if user is not None else None,
        actor="user" if user is not None else "system",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def _runner(kind: str, path: Path, filename: str | None, term_code: str | None, params: dict[str, Any]) -> Any:
    """The importer call of one job kind (an upload and the apply of its preview run the same call)."""
    term = term_code or ""  # the term-scoped kinds always carry one (a Form field of their upload)
    if kind == "planning-list":
        from app.importers.planning_list import import_planning_list

        return lambda s: import_planning_list(
            s,
            path,
            term,
            filename=filename,
            week_count=int(params.get("week_count") or 14),
            on_conflict=str(params.get("on_conflict") or "keep"),
        )
    if kind == "exam-list":
        from app.importers.exam_list import import_exam_list

        return lambda s: import_exam_list(
            s, path, term, filename=filename, on_conflict=str(params.get("on_conflict") or "keep")
        )
    if kind == "weekly-grid":
        from app.importers.weekly_grid import import_weekly_grid

        return lambda s: import_weekly_grid(
            s, path, term, year=int(params["year"]), filename=filename, term_kind=params.get("term_kind")
        )
    if kind == "room-master":
        from app.importers.room_master import import_room_master

        return lambda s: import_room_master(s, path, filename=filename)
    raise HTTPException(400, f"{kind} imports have no preview")


async def _upload_job(
    db: DB,
    user: User,
    kind: str,
    file: UploadFile,
    term_code: str | None,
    params: dict[str, Any],
    *,
    dry_run: bool,
    full_load: bool = False,
) -> ImportJob:
    if term_code is not None and not dry_run:
        await _refuse_if_locked(term_code)
    job = await _new_job(db, kind, file.filename, term_code, user, params=params, dry_run=dry_run)
    path = await _save_upload(db, job, file, full_load=full_load)
    run = _runner(kind, path, file.filename, term_code, params)
    return await _start_job(db, job, run, term_code=term_code, dry_run=dry_run)


@router.post("/planning-list", response_model=ImportJobOut, status_code=202)
async def import_planning(
    db: DB,
    user: Planner,
    file: UploadFile = File(...),
    term_code: str = Form(...),
    week_count: int = Form(14),
    on_conflict: str = Form("keep", pattern="^(keep|take)$"),
    dry_run: bool = Form(False),
) -> ImportJob:
    """Re-imports keep planner edits of fields the file also changed (``on_conflict=keep``, reported in
    ``summary.extra.conflicts``) or apply the file (``take``).
    ``dry_run=true``: a preview (RF-06), see ``POST /imports/{id}/apply``."""
    params = {"week_count": week_count, "on_conflict": on_conflict}
    return await _upload_job(db, user, "planning-list", file, term_code, params, dry_run=dry_run)


@router.post("/exam-list", response_model=ImportJobOut, status_code=202)
async def import_exams(
    db: DB,
    user: Planner,
    file: UploadFile = File(...),
    term_code: str = Form(...),
    on_conflict: str = Form("keep", pattern="^(keep|take)$"),
    dry_run: bool = Form(False),
) -> ImportJob:
    """Re-imports keep admin edits and archived rows (RF-06); a field the file changed too is a conflict, kept
    (``on_conflict=keep``) or taken (``take``) and listed in ``summary.extra.conflicts``.
    ``dry_run=true``: a preview (RF-06), see ``POST /imports/{id}/apply``."""
    return await _upload_job(db, user, "exam-list", file, term_code, {"on_conflict": on_conflict}, dry_run=dry_run)


@router.post("/weekly-grid", response_model=ImportJobOut, status_code=202)
async def import_grid(
    db: DB,
    user: Planner,
    file: UploadFile = File(...),
    term_code: str = Form(...),
    year: int = Form(...),
    term_kind: str | None = Form(None),
    dry_run: bool = Form(False),
) -> ImportJob:
    """A term's room board; weeks an admin edited keep their kind and label (RF-06).
    ``dry_run=true``: a preview (RF-06), see ``POST /imports/{id}/apply``."""
    params = {"year": year, "term_kind": term_kind}
    return await _upload_job(db, user, "weekly-grid", file, term_code, params, dry_run=dry_run, full_load=True)


RoomsEditor = Annotated[User, Depends(require_permission("planning.edit", "setup.rooms"))]
_ROOM_MASTER_TYPES = (".csv", ".txt", ".xlsx", ".xlsm")


@router.post("/room-master", response_model=ImportJobOut, status_code=202)
async def import_room_master_endpoint(
    db: DB, user: RoomsEditor, file: UploadFile = File(...), dry_run: bool = Form(False)
) -> ImportJob:
    """The room master (``code, capacity, exam_capacity, tags, building, floor, bookable[, notes]``) as CSV
    (UTF-8 or Windows-1254, ``;`` or ``,``) or ``.xlsx`` (first sheet).  Values it sets are never overwritten
    by a later workbook import.  Needs ``planning.edit`` or ``setup.rooms``.
    ``dry_run=true``: a preview (RF-06), see ``POST /imports/{id}/apply``."""
    if not (file.filename or "").lower().endswith(_ROOM_MASTER_TYPES):
        raise HTTPException(400, "the room master must be a .csv or .xlsx file")
    return await _upload_job(db, user, "room-master", file, None, {}, dry_run=dry_run)


class ApplyIn(BaseModel):
    #: planning / exam lists: override the preview's choice (``keep`` the admins' edits or ``take`` the file)
    on_conflict: Literal["keep", "take"] | None = None


@router.post("/{job_id}/apply", response_model=ImportJobOut, status_code=202)
async def apply_preview(job_id: int, body: ApplyIn, db: DB, access: CurrentAccess) -> ImportJobOut:
    """RF-06: import the file of a finished preview (``dry_run``) with its parameters, once. The new job records
    ``summary.preview_of``; the preview records ``summary.applied_job_id``. Same permissions as the upload."""
    preview = await db.get(ImportJob, job_id)
    if preview is None:
        raise HTTPException(404, "import job not found")
    allowed = "planning.edit" in access.perms or (preview.kind == "room-master" and "setup.rooms" in access.perms)
    if not allowed:
        raise forbidden("planning.edit")
    summary = dict(preview.summary or {})
    if not summary.get("dry_run"):
        raise problem(409, "not_a_preview", "Bu içe aktarma bir önizleme değil.", "this import job is not a preview")
    if summary.get("applied_job_id"):
        raise problem(
            409,
            "preview_already_applied",
            "Bu önizleme zaten uygulandı.",
            "this preview was applied already",
            applied_job_id=summary["applied_job_id"],
        )
    if preview.status != "DONE":
        raise problem(409, "preview_not_ready", "Önizleme henüz hazır değil.", "the preview has not finished")
    files = _job_files(preview.id)
    if not files:
        raise problem(
            410,
            "preview_file_gone",
            "Önizlemenin dosyası artık yok; dosyayı yeniden yükleyin.",
            "the previewed file is no longer stored; upload it again",
        )
    params = dict(summary.get("params") or {})
    if body.on_conflict is not None:
        params["on_conflict"] = body.on_conflict
    if preview.term_code is not None:
        await _refuse_if_locked(preview.term_code)
    job = await _new_job(
        db, preview.kind, preview.filename, preview.term_code, access.user, params=params, preview_of=preview.id
    )
    path = import_jobs.keep_file(job.id, files[0], preview.filename)
    preview.summary = {**summary, "applied_job_id": job.id}
    await db.commit()
    run = _runner(job.kind, path, preview.filename, preview.term_code, params)
    await _start_job(db, job, run, term_code=preview.term_code)
    return _out(job, access, await _names(db, [job]))


@router.post("/crbs", response_model=ImportJobOut, status_code=202)
async def import_crbs_endpoint(
    db: DB, user: Planner, dsn: str | None = Form(None), files: list[UploadFile] = File(default=[])
) -> ImportJob:
    """Either a MySQL DSN (``mysql://user:pass@host/db``) or one or more SQL dump files. A live DSN is for
    planning admins and allow-listed hosts only (``crbs_dsn.check_dsn``, review D16); dumps never connect."""
    from app.importers.crbs_legacy import import_crbs
    from app.services import crbs_dsn

    if not dsn and not files:
        raise HTTPException(400, "provide a dsn or SQL dump files")
    if dsn:
        await crbs_dsn.check_dsn(db, dsn, user)  # 403 / 422 before any job or connection exists
    job = await _new_job(
        db,
        "crbs",
        ", ".join(f.filename or "?" for f in files) if files else dsn.split("@")[-1] if dsn else None,
        None,
        user,
    )
    paths = [await _save_upload(db, job, f) for f in files]
    source: Any = dsn if dsn else paths
    return await _start_job(db, job, lambda s: import_crbs(s, source, filename=job.filename))


#: summary keys a viewer may read: counts and job state, no parsed rows / warnings / notes (KVKK, council D13)
_COUNT_KEYS = frozenset(
    {
        "rows_total",
        "rows_imported",
        "rows_skipped_count",
        "warnings_count",
        "warnings_shown",
        "warnings_truncated",
        "created",
        "updated",
        "progress",
        "phase",
        "detected_kind",
        "expected_kind",
        "source",
        "dry_run",
        "applied_job_id",
        "preview_of",
    }
)


def _out(job: ImportJob, access: Any, names: dict[int, str] | None = None) -> ImportJobOut:
    """The job as the caller may see it: parsed rows, warnings and the report's ``extra`` (instructor names,
    notes, conflicts) need ``planning.edit`` - or ``setup.rooms`` for a room-master job; others get counts.
    ``actor`` / ``created_by_id`` / ``created_by_name`` / ``source`` say who imported (RF-08)."""
    out = ImportJobOut.model_validate(job)
    out.source = str((job.summary or {}).get("source") or ("upload" if job.created_by_id else "")) or None
    if job.created_by_id is not None:
        out.created_by_name = (names or {}).get(job.created_by_id)
    full = "planning.edit" in access.perms or (job.kind == "room-master" and "setup.rooms" in access.perms)
    if not full:
        out.summary = {k: v for k, v in out.summary.items() if k in _COUNT_KEYS} | {"redacted": True}
    return out


async def _names(db: DB, jobs: list[ImportJob]) -> dict[int, str]:
    ids = {j.created_by_id for j in jobs if j.created_by_id is not None}
    if not ids:
        return {}
    users = (await db.execute(select(User).where(User.id.in_(ids)))).scalars()
    return {u.id: audit.user_label(u) or f"#{u.id}" for u in users}


@router.get("", response_model=list[ImportJobOut])
async def list_jobs(
    db: DB,
    access: CurrentAccess,
    limit: int = 50,
    kind: Literal["planning-list", "exam-list", "weekly-grid", "room-master", "crbs"] | None = None,
) -> list[ImportJobOut]:
    """Newest first. ``kind`` filters (the room wizard lists ``room-master``). Planners (``planning.view``)
    list every kind; a room administrator (``setup.rooms``) lists the room-master imports only."""
    if "planning.view" not in access.perms and not (kind == "room-master" and "setup.rooms" in access.perms):
        raise HTTPException(403, "requires permission planning.view")
    q = select(ImportJob)
    if kind is not None:
        q = q.where(ImportJob.kind == kind)
    jobs = list((await db.execute(q.order_by(ImportJob.id.desc()).limit(max(1, min(limit, 500))))).scalars())
    names = await _names(db, jobs)
    return [_out(j, access, names) for j in jobs]


@router.get("/{job_id}", response_model=ImportJobOut)
async def get_job(job_id: int, db: DB, access: CurrentAccess) -> ImportJobOut:
    """Planners see every job; a room administrator (``setup.rooms``) sees the room-master imports."""
    job = await db.get(ImportJob, job_id)
    viewer = "planning.view" in access.perms
    if not viewer and not ("setup.rooms" in access.perms and job is not None and job.kind == "room-master"):
        if "setup.rooms" not in access.perms:
            raise HTTPException(403, "requires permission planning.view")
        raise HTTPException(404, "import job not found")
    if job is None:
        raise HTTPException(404, "import job not found")
    out = _out(job, access, await _names(db, [job]))
    st = get_queue().state(f"import:{job.id}")
    if st and job.status in {"QUEUED", "RUNNING"}:
        out.summary = {**out.summary, "progress": st.progress, "phase": st.phase}
    return out


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
    return import_jobs.utcnow()
