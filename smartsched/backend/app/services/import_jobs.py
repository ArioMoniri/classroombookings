"""Import history bookkeeping shared by ``POST /imports/*`` and the CLI (RF-06 / RF-08; audit Part B fix list 8).

* every import is an ``import_jobs`` row with its actor: the uploading person (``actor = user``,
  ``created_by_id``) or ``system`` for a CLI import (``summary.source``: ``seed`` for the deploy seed, ``cli``
  otherwise; ``upload`` for the API);
* the original file is kept next to the job (``<upload_dir>/imports/<job id>_<name>``) so ``GET /imports/{id}/file``
  downloads it; a failed import keeps none;
* a finished import writes an ``import.run`` audit event (kind, file, term, status, counts);
* a preview (``dry_run``) runs the importer in a transaction that is rolled back and stores the diff
  (``app.council.dryrun.summarize``: per entity create / update / unchanged / conflict and the row diffs).
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.importers.report import ImportReport
from app.models import ImportJob, User
from app.services import audit

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
#: summary keys the job keeps when the importer's report arrives (the report replaces the rest)
BOOKKEEPING = ("source", "params", "dry_run", "applied_job_id", "preview_of", "worker")
#: CLI ``--source`` values (the API records ``upload``)
CLI_SOURCES = ("cli", "seed")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def job_dir() -> Path:
    return Path(get_settings().upload_dir) / "imports"


def job_files(job_id: int) -> list[Path]:
    return sorted(job_dir().glob(f"{job_id}_*"))


def remove_files(job_id: int) -> None:
    for f in job_files(job_id):
        f.unlink(missing_ok=True)


def file_target(job_id: int, filename: str | None) -> Path:
    return job_dir() / f"{job_id}_{_SAFE.sub('_', filename or 'upload.bin')}"


def keep_file(job_id: int, source: Path, filename: str | None = None) -> Path:
    """Copy ``source`` next to the job (the CLI's file, or a preview's file for the import that applies it)."""
    target = file_target(job_id, filename or source.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def merged_summary(previous: dict[str, Any] | None, result: dict[str, Any]) -> dict[str, Any]:
    keep = {k: v for k, v in (previous or {}).items() if k in BOOKKEEPING}
    return {**result, **keep}


async def audit_run(session: AsyncSession, job: ImportJob) -> None:
    """``import.run`` for a finished (DONE / FAILED) import - not for a preview, which writes nothing."""
    summary = job.summary or {}
    if summary.get("dry_run"):
        return
    actor = await session.get(User, job.created_by_id) if job.created_by_id else None
    if actor is None and audit.context(session) is None:
        audit.set_context(session, audit.AuditContext(actor_type="system", actor_label=str(summary.get("source") or "cli")))
    await audit.record(
        session,
        "import.run",
        "import_job",
        job.id,
        after={
            "kind": job.kind,
            "filename": job.filename,
            "term_code": job.term_code,
            "status": job.status,
            "source": summary.get("source"),
            "rows_imported": summary.get("rows_imported"),
            "created": summary.get("created"),
            "updated": summary.get("updated"),
            "warnings_count": summary.get("warnings_count"),
            "preview_of": summary.get("preview_of"),
            "error": job.error,
        },
        actor=actor,
    )


async def run_preview(
    session: AsyncSession, run: Callable[[AsyncSession], Awaitable[ImportReport]]
) -> dict[str, Any]:
    """The import in a transaction that is rolled back: its report plus ``diff`` (``dryrun.summarize``)."""
    from app.council.dryrun import ChangeRecorder, summarize

    rec = ChangeRecorder().attach(session)
    session.commit = session.flush  # type: ignore[method-assign]  # one transaction, rolled back below
    try:
        report = await run(session)
        diff = summarize(rec, report.extra, str(report.extra.get("on_conflict") or "keep"))
        rec.detach(session)
    finally:
        await session.rollback()
    return {**report.to_dict(), "diff": diff}


async def open_cli_job(
    session: AsyncSession, *, kind: str, filename: str | None, term_code: str | None, source: str, files: list[Path]
) -> int:
    """RF-08: the ``import_jobs`` row of a CLI import (actor ``system``), with its files kept for download."""
    job = ImportJob(
        kind=kind,
        filename=filename,
        term_code=term_code,
        status="RUNNING",
        actor="system",
        summary={"source": source},
    )
    session.add(job)
    await session.commit()
    for f in files:
        keep_file(job.id, f)
    return int(job.id)


async def finish_cli_job(
    session: AsyncSession, job_id: int, *, result: dict[str, Any] | None = None, error: str | None = None
) -> None:
    job = await session.get(ImportJob, job_id)
    if job is None:
        return
    job.finished_at = utcnow()
    if error is not None:
        job.status, job.error = "FAILED", error[:2000]
        remove_files(job_id)
    else:
        job.status = "DONE"
        job.summary = merged_summary(job.summary, result or {})
    await audit_run(session, job)
    await session.commit()


__all__ = [
    "BOOKKEEPING",
    "CLI_SOURCES",
    "audit_run",
    "file_target",
    "finish_cli_job",
    "job_files",
    "keep_file",
    "merged_summary",
    "open_cli_job",
    "remove_files",
    "run_preview",
]
