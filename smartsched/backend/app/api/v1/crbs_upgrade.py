"""Legacy classroombookings upgrade (P18-LEGACY): ``POST /crbs-upgrade`` -- dry run by default, commit on confirm.

Multipart form: ``files`` (one or more SQL dumps / CRBS install scripts) **or** ``dsn`` (a live ``mysql://``
DSN, read-only, admin + host allowlist), ``confirm`` (default false) and, with ``confirm``, the ``fingerprint``
of the reviewed dry run. ``planning.admin`` only. See :mod:`app.services.crbs_upgrade` for the report.

One upgrade at a time per process (HB-23d N6): the dumps are copied to a temporary directory under ``/tmp`` and
parsed into a temporary SQLite file there, and ``/tmp`` is a size-capped tmpfs in the container (``BACKEND_TMPFS``,
deploy/.env.example). A second request while one runs answers 409 ``crbs_upgrade_busy`` before it writes anything.
The database-wide ``crbs-upgrade`` write lock (:mod:`app.services.term_lock`) still serialises across processes.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.deps import DB, Admin
from app.core import safe_files
from app.schemas.messages import problem
from app.services import crbs_dsn, term_lock
from app.services import crbs_upgrade as up

router = APIRouter(prefix="/crbs-upgrade", tags=["crbs-upgrade"])
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_SQL_TYPES = (".sql", ".txt")
#: one upgrade at a time in this process: its temporary copies and SQLite file live on the /tmp tmpfs
_RUNNING = threading.Lock()


def _busy() -> HTTPException:
    return problem(
        409,
        "crbs_upgrade_busy",
        "Şu anda başka bir classroombookings yükseltmesi çalışıyor. O bitince yeniden deneyin.",
        "Another classroombookings upgrade is running. Try again when it has finished.",
    )


@router.post("")
async def crbs_upgrade(
    db: DB,
    user: Admin,
    files: list[UploadFile] = File(default=[]),
    dsn: str | None = Form(None),
    confirm: bool = Form(False),
    fingerprint: str | None = Form(None),
) -> dict[str, Any]:
    if bool(files) == bool(dsn):
        raise HTTPException(400, "provide either SQL dump files or a dsn")
    if confirm and not fingerprint:
        raise HTTPException(422, "confirm needs the fingerprint of the reviewed dry run")
    if not _RUNNING.acquire(blocking=False):
        raise _busy()
    try:
        return await _upgrade(db, user, files, dsn, confirm=confirm, fingerprint=fingerprint)
    finally:
        _RUNNING.release()


async def _upgrade(
    db: DB, user: Admin, files: list[UploadFile], dsn: str | None, *, confirm: bool, fingerprint: str | None
) -> dict[str, Any]:
    workdir: Path | None = None
    source: str | list[Path]
    if dsn:
        await crbs_dsn.check_dsn(db, dsn, user)
        source, label = dsn, (dsn.rsplit("@", 1)[-1] if "@" in dsn else dsn)
    else:
        workdir = Path(tempfile.mkdtemp(prefix="crbs-upgrade-"))
        paths: list[Path] = []
        try:
            for i, f in enumerate(files):
                if not (f.filename or "").lower().endswith(_SQL_TYPES):
                    raise HTTPException(400, f"{f.filename}: a CRBS dump is an .sql file")
                target = workdir / f"{i:02d}_{_SAFE.sub('_', f.filename or 'dump.sql')}"
                await safe_files.save_upload(f, target)
                paths.append(target)
        except safe_files.UnsafeFileError as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(exc.status, exc.message) from exc
        except HTTPException:
            shutil.rmtree(workdir, ignore_errors=True)
            raise
        source, label = paths, ", ".join(f.filename or "?" for f in files)
    await db.close()  # the upgrade uses its own sessions; do not hold this one open meanwhile
    try:
        if confirm:
            rep = await up.commit(source, expect=str(fingerprint), filename=label)
        else:
            rep = await up.dry_run(source, filename=label)
    except up.SourceChanged as exc:
        raise HTTPException(409, str(exc)) from exc
    except safe_files.UnsafeFileError as exc:  # the parse child refused the dump (memory / time limits)
        raise HTTPException(exc.status, exc.message) from exc
    except term_lock.TermLocked as exc:
        raise term_lock.http_error(exc) from exc
    except RuntimeError as exc:  # pymysql missing / connection refused
        raise HTTPException(422, str(exc)) from exc
    finally:
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)
    return rep.to_dict()
