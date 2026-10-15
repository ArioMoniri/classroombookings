"""Per-term write lock for imports and commits (review 2026-10-15 D8 / P19-03).

Two imports of one term used to run at once (the job queue runs two jobs in parallel, and several worker
processes may serve the API). Every writer of a term's planning data now holds the term's lock while it writes:

    from app.services import term_lock

    async with term_lock.term_write_lock(term_lock.term_key(term_code), f"import:{job.id} {job.kind}", wait_s=600):
        report = await run(session)

* The lock is one row of ``term_locks`` (primary key = the lock key), inserted and deleted in their own short
  transactions, so it is visible to every process and to Postgres and SQLite alike.
* A second writer waits up to ``wait_s`` (polling) and then gets :class:`TermLocked`, which names the holder;
  :func:`http_error` turns it into a 409 for request handlers (:func:`assert_unlocked` refuses a new import up front).
* A holder that dies leaves its row behind; after ``expires_at`` the next writer takes it over. A live holder keeps
  its lock: the context manager extends ``expires_at`` every ``ttl_s / 3`` seconds.

Keys are Turkish-insensitive (:func:`term_key`): ``2026-bahar``, `` 2026-BAHAR\\xa0`` and ``2026-FİNAL`` /
``2026-FINAL`` name the same term, as the importers resolve them.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_session_factory
from app.importers.normalize import tr_fold
from app.models import Term, TermLock
from app.models.base import utcnow

DEFAULT_TTL_S = 300.0


class TermLocked(Exception):
    """The term is being written by someone else."""

    def __init__(self, key: str, holder: str | None, since: datetime | None, expires_at: datetime | None) -> None:
        self.key, self.holder, self.since, self.expires_at = key, holder, since, expires_at
        when = f" since {since:%Y-%m-%d %H:%M:%S} UTC" if since else ""
        super().__init__(f"{key} is locked by {holder or 'another writer'}{when}; try again when it has finished")


@dataclass
class LockHandle:
    key: str
    holder: str
    token: str
    ttl_s: float


def term_key(term_code: str) -> str:
    """Lock key of a term code: Turkish casefold (dotted and dotless i together), NBSP and runs of spaces
    collapsed, shown upper case."""
    folded = tr_fold(str(term_code or ""))
    if not folded:
        raise ValueError("a term lock needs a term code")
    return f"term:{folded.upper()}"


async def term_key_for(term_id: int, session: AsyncSession | None = None) -> str:
    """Lock key of a term row (writers that know the id, e.g. commits)."""
    if session is not None:
        code = (await session.execute(select(Term.code).where(Term.id == term_id))).scalar_one_or_none()
    else:
        async with get_session_factory()() as s:
            code = (await s.execute(select(Term.code).where(Term.id == term_id))).scalar_one_or_none()
    if code is None:
        raise ValueError(f"term {term_id} not found")
    return term_key(code)


def _factory(factory: async_sessionmaker[AsyncSession] | None) -> async_sessionmaker[AsyncSession]:
    return factory if factory is not None else get_session_factory()


async def _try_acquire(
    factory: async_sessionmaker[AsyncSession], key: str, holder: str, token: str, ttl_s: float
) -> TermLock | None:
    """One attempt. None = acquired; else the current row (holder)."""
    now = utcnow()
    expires = now + timedelta(seconds=ttl_s)
    async with factory() as s:
        s.add(TermLock(key=key, holder=holder[:255], token=token, acquired_at=now, expires_at=expires))
        try:
            await s.commit()
            return None
        except IntegrityError:
            await s.rollback()
        # taken: take it over only when its holder stopped extending it
        res = await s.execute(
            update(TermLock)
            .where(TermLock.key == key, TermLock.expires_at < now)
            .values(holder=holder[:255], token=token, acquired_at=now, expires_at=expires)
            .execution_options(synchronize_session=False)
        )
        await s.commit()
        if getattr(res, "rowcount", 0):
            return None
        row = await s.get(TermLock, key)
        if row is None:  # released between the insert and the read: try again at once
            return TermLock(key=key, holder="", token="", acquired_at=now, expires_at=now)
        return row


async def acquire(
    key: str,
    holder: str,
    *,
    ttl_s: float = DEFAULT_TTL_S,
    wait_s: float = 0.0,
    poll_s: float = 0.5,
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> LockHandle:
    """Take the lock ``key`` for ``holder``; wait up to ``wait_s`` seconds, then raise :class:`TermLocked`."""
    f = _factory(factory)
    token = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, wait_s)
    while True:
        other = await _try_acquire(f, key, holder, token, ttl_s)
        if other is None:
            return LockHandle(key, holder, token, ttl_s)
        if other.holder and loop.time() >= deadline:
            raise TermLocked(key, other.holder, other.acquired_at, other.expires_at)
        if other.holder:
            await asyncio.sleep(min(poll_s, max(0.0, deadline - loop.time())) or poll_s)


async def extend(handle: LockHandle, factory: async_sessionmaker[AsyncSession] | None = None) -> bool:
    """Push the expiry of a held lock; False when it was lost (expired and taken over)."""
    async with _factory(factory)() as s:
        res = await s.execute(
            update(TermLock)
            .where(TermLock.key == handle.key, TermLock.token == handle.token)
            .values(expires_at=utcnow() + timedelta(seconds=handle.ttl_s))
            .execution_options(synchronize_session=False)
        )
        await s.commit()
        return bool(getattr(res, "rowcount", 0))


async def release(handle: LockHandle, factory: async_sessionmaker[AsyncSession] | None = None) -> None:
    async with _factory(factory)() as s:
        await s.execute(delete(TermLock).where(TermLock.key == handle.key, TermLock.token == handle.token))
        await s.commit()


async def current(key: str, factory: async_sessionmaker[AsyncSession] | None = None) -> TermLock | None:
    """The live lock on ``key`` (an expired row counts as free)."""
    async with _factory(factory)() as s:
        row = await s.get(TermLock, key)
    if row is None or row.expires_at < utcnow():
        return None
    return row


async def assert_unlocked(key: str, factory: async_sessionmaker[AsyncSession] | None = None) -> None:
    """Raise :class:`TermLocked` when ``key`` is held (a request handler's early 409)."""
    row = await current(key, factory)
    if row is not None:
        raise TermLocked(key, row.holder, row.acquired_at, row.expires_at)


@contextlib.asynccontextmanager
async def term_write_lock(
    key: str,
    holder: str,
    *,
    ttl_s: float = DEFAULT_TTL_S,
    wait_s: float = 0.0,
    poll_s: float = 0.5,
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[LockHandle]:
    """Hold ``key`` for the body; the expiry is extended every ``ttl_s / 3`` seconds while the body runs."""
    handle = await acquire(key, holder, ttl_s=ttl_s, wait_s=wait_s, poll_s=poll_s, factory=factory)

    async def beat() -> None:
        while True:
            await asyncio.sleep(max(0.05, ttl_s / 3))
            await extend(handle, factory)

    task = asyncio.create_task(beat())
    try:
        yield handle
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        await release(handle, factory)


def http_error(exc: TermLocked) -> HTTPException:
    detail: dict[str, Any] = {
        "message": str(exc),
        "code": "term_locked",
        "key": exc.key,
        "holder": exc.holder,
        "since": exc.since.isoformat() if exc.since else None,
    }
    return HTTPException(409, detail)


__all__ = [
    "DEFAULT_TTL_S",
    "LockHandle",
    "TermLocked",
    "acquire",
    "assert_unlocked",
    "current",
    "extend",
    "http_error",
    "release",
    "term_key",
    "term_key_for",
    "term_write_lock",
]
