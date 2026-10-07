"""In-process asyncio background job runner with DB-backed status.

Jobs are coroutines keyed by a (table, id); status/progress live in the DB row so the API (and later a
Celery/RQ worker) can read them. Progress events are also fanned out in-memory for SSE streaming.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
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
    error: str | None = None
    result: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    listeners: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {"key": self.key, "status": self.status, "phase": self.phase, "progress": self.progress, "error": self.error}


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

                def progress(phase: str, pct: int) -> None:
                    st.phase, st.progress = phase, max(0, min(100, pct))
                    self._emit(st)

                try:
                    st.result = await fn(progress)
                    st.status, st.phase, st.progress = "DONE", "done", 100
                except Exception as exc:  # noqa: BLE001
                    log.exception("job %s failed", key)
                    st.status, st.phase = "FAILED", "failed"
                    st.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"
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


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue()
    return _queue


def reset_queue() -> None:
    global _queue
    _queue = None
