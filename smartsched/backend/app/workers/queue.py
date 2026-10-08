"""In-process asyncio background job runner with DB-backed status.

Jobs are coroutines keyed by a (table, id); status/progress live in the DB row so the API (and later a
Celery/RQ worker) can read them. Progress events are also fanned out in-memory for SSE streaming.

* CPU-bound work (the CP-SAT solve) runs in a worker thread (``asyncio.to_thread`` in the job body);
  the ``progress`` callback handed to jobs is thread-safe (it hops onto the loop when called from
  another thread), so ``/health`` and every other request keep being served during a solve.
* ``JobState.error`` is a short, path-free message safe to show to clients; the traceback is only
  logged server-side.
* Jobs live in this process only: :func:`recover_interrupted` (called on startup) marks runs and
  import jobs that a dead process left QUEUED/RUNNING as FAILED.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int], None]
JobFn = Callable[[ProgressCallback], Awaitable[dict[str, Any] | None]]


@dataclass
class JobState:
    key: str
    status: str = "QUEUED"
    phase: str = "queued"
    progress: int = 0
    error: str | None = None  # short, client-safe
    result: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    listeners: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "error": self.error,
        }


class JobQueue:
    def __init__(self, max_concurrency: int = 2):
        self._jobs: dict[str, JobState] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._sem = asyncio.Semaphore(max_concurrency)

    def state(self, key: str) -> JobState | None:
        return self._jobs.get(key)

    def subscribe(self, key: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        st = self._jobs.setdefault(key, JobState(key))
        st.listeners.append(q)
        q.put_nowait(st.snapshot())
        return q

    def unsubscribe(self, key: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        st = self._jobs.get(key)
        if st and q in st.listeners:
            st.listeners.remove(q)

    def _emit(self, st: JobState) -> None:
        snap = st.snapshot()
        for q in list(st.listeners):
            q.put_nowait(snap)

    def enqueue(
        self,
        key: str,
        fn: JobFn,
        *,
        on_status: Callable[[JobState], Awaitable[None]] | None = None,
    ) -> JobState:
        st = self._jobs.get(key) or JobState(key)
        st.status, st.phase, st.progress, st.error = "QUEUED", "queued", 0, None
        self._jobs[key] = st

        async def runner() -> None:
            async with self._sem:
                st.status, st.phase, st.started_at = "RUNNING", "starting", datetime.now(UTC)
                self._emit(st)
                if on_status:
                    await on_status(st)

                loop = asyncio.get_running_loop()
                loop_thread = threading.get_ident()

                def apply(phase: str, pct: int) -> None:
                    st.phase, st.progress = phase, max(0, min(100, int(pct)))
                    self._emit(st)

                def progress(phase: str, pct: int) -> None:
                    # solver threads report through here: asyncio.Queue is not thread-safe
                    if threading.get_ident() == loop_thread:
                        apply(phase, pct)
                    elif not loop.is_closed():
                        loop.call_soon_threadsafe(apply, phase, pct)

                try:
                    st.result = await fn(progress)
                    st.status, st.phase, st.progress = "DONE", "done", 100
                except Exception as exc:  # noqa: BLE001
                    log.exception("job %s failed", key)  # full traceback stays in the server log
                    st.status, st.phase = "FAILED", "failed"
                    st.error = public_error(exc)
                finally:
                    st.finished_at = datetime.now(UTC)
                    self._emit(st)
                    if on_status:
                        try:
                            await on_status(st)
                        except Exception:  # noqa: BLE001
                            log.exception("on_status failed for %s", key)

        task = asyncio.create_task(runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return st

    async def wait_idle(self, timeout: float = 120.0) -> None:
        if self._tasks:
            await asyncio.wait_for(asyncio.gather(*list(self._tasks), return_exceptions=True), timeout)

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][^\s'\"\\/:]+){2,}")


def public_error(exc: BaseException, limit: int = 300) -> str:
    """``Type: message`` without server paths (``/srv/uploads/imports/12_x.xlsx`` -> ``12_x.xlsx``) or
    tracebacks, for API responses."""
    msg = _PATH.sub(lambda m: re.split(r"[\\/]", m.group(0))[-1], str(exc)).strip()
    text = f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__
    return text if len(text) <= limit else text[: limit - 1] + "…"


def worker_id() -> dict[str, Any]:
    """Identity of this process, stored on runs/import jobs so a restart can tell its own orphans."""
    return {"host": socket.gethostname(), "pid": os.getpid()}


def _alive(owner: Any) -> bool:
    """True when ``owner`` (a :func:`worker_id`) is another live process on this host. Owners on other
    hosts are assumed alive (they recover their own jobs); unknown owners are treated as dead."""
    if not isinstance(owner, dict) or "pid" not in owner:
        return False
    if owner.get("host") != socket.gethostname():
        return True
    pid = int(owner["pid"])
    if pid == os.getpid():
        return False  # we just started: nothing of ours can be running yet
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def recover_interrupted(session: Any) -> dict[str, int]:
    """Mark runs / import jobs left QUEUED or RUNNING by a dead process as FAILED (startup hook)."""
    from sqlalchemy import select

    from app.models import ImportJob, ScheduleRun

    now = datetime.now(UTC).replace(tzinfo=None)
    msg = "interrupted by restart"
    runs = imports = 0
    for run in (
        await session.execute(select(ScheduleRun).where(ScheduleRun.status.in_(("QUEUED", "RUNNING"))))
    ).scalars():
        if _alive((run.stats or {}).get("worker")):
            continue
        run.status, run.error, run.finished_at = "FAILED", msg, now
        run.stats = {**(run.stats or {}), "error": msg, "phase": "failed"}
        runs += 1
    for job in (await session.execute(select(ImportJob).where(ImportJob.status.in_(("QUEUED", "RUNNING"))))).scalars():
        if _alive((job.summary or {}).get("worker")):
            continue
        job.status, job.error, job.finished_at = "FAILED", msg, now
        imports += 1
    from app.models import CouncilJob

    for cj in (await session.execute(select(CouncilJob).where(CouncilJob.status.in_(("QUEUED", "RUNNING"))))).scalars():
        if _alive((cj.settings or {}).get("worker")):
            continue
        cj.status, cj.error, cj.finished_at = "FAILED", f"{msg}; re-run the job", now
        imports += 1
    await session.commit()
    if runs or imports:
        log.warning("marked %d run(s) and %d import job(s) FAILED (%s)", runs, imports, msg)
    return {"runs": runs, "imports": imports}


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue()
    return _queue


def reset_queue() -> None:
    global _queue
    _queue = None
