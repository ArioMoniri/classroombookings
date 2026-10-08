"""Blackboard access: uploads on disk, jobs, steps and append-only artifacts in the database."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import CouncilArtifact, CouncilJob, CouncilStep

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def job_dir(job_id: int) -> Path:
    base: str = get_settings().upload_dir
    return Path(base) / "council" / str(job_id)


def stored_name(index: int, filename: str) -> str:
    return f"{index}_{_SAFE.sub('_', filename or 'upload')[:120]}"


def file_path(job_id: int, entry: dict[str, Any]) -> Path:
    return job_dir(job_id) / str(entry["stored"])


def save_upload(job_id: int, index: int, filename: str, data: bytes) -> str:
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    name = stored_name(index, filename)
    (d / name).write_bytes(data)
    return name


async def add_artifact(
    session: AsyncSession,
    job_id: int,
    kind: str,
    payload: dict[str, Any],
    *,
    file_index: int | None = None,
    step_id: int | None = None,
    confidence: float | None = None,
) -> CouncilArtifact:
    art = CouncilArtifact(
        job_id=job_id, kind=kind, payload=payload, file_index=file_index, step_id=step_id, confidence=confidence
    )
    session.add(art)
    await session.flush()
    return art


async def latest(
    session: AsyncSession, job_id: int, kind: str, file_index: int | None = None
) -> CouncilArtifact | None:
    q = select(CouncilArtifact).where(CouncilArtifact.job_id == job_id, CouncilArtifact.kind == kind)
    q = q.where(
        CouncilArtifact.file_index.is_(None) if file_index is None else CouncilArtifact.file_index == file_index
    )
    return (await session.execute(q.order_by(CouncilArtifact.id.desc()).limit(1))).scalar_one_or_none()


async def latest_by_file(session: AsyncSession, job_id: int, kind: str) -> dict[int, CouncilArtifact]:
    rows = (
        await session.execute(
            select(CouncilArtifact)
            .where(
                CouncilArtifact.job_id == job_id, CouncilArtifact.kind == kind, CouncilArtifact.file_index.is_not(None)
            )
            .order_by(CouncilArtifact.id)
        )
    ).scalars()
    out: dict[int, CouncilArtifact] = {}
    for a in rows:
        if a.file_index is not None:
            out[a.file_index] = a
    return out


async def all_of(session: AsyncSession, job_id: int, kind: str) -> list[CouncilArtifact]:
    q = select(CouncilArtifact).where(CouncilArtifact.job_id == job_id, CouncilArtifact.kind == kind)
    return list((await session.execute(q.order_by(CouncilArtifact.id))).scalars())


async def steps(session: AsyncSession, job_id: int) -> list[CouncilStep]:
    q = select(CouncilStep).where(CouncilStep.job_id == job_id).order_by(CouncilStep.id)
    return list((await session.execute(q)).scalars())


async def records_by_file(session: AsyncSession, job: CouncilJob) -> dict[int, list[dict[str, Any]]]:
    arts = await latest_by_file(session, job.id, "records")
    return {fi: list(a.payload.get("records", [])) for fi, a in arts.items()}


__all__ = [
    "add_artifact",
    "all_of",
    "file_path",
    "job_dir",
    "latest",
    "latest_by_file",
    "records_by_file",
    "save_upload",
    "steps",
    "stored_name",
]
