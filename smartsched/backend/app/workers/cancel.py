"""Cooperative cancellation of solver jobs (review M13), without touching ``app/solver`` internals.

The solver is a pure function that may call ``CpSolver.solve`` several times (main solve, canonical
stages, diagnosis, week segments). :func:`install_cpsat_hook` wraps ``CpSolver.solve`` / ``Solve`` once per
process: every solver created inside a thread bound to a :class:`CancelToken` (see :func:`bind`) is
registered on the token, and :func:`cancel` calls the thread-safe ``CpSolver.stop_search()`` on all of
them (CP-SAT's *StopSearch*); later solves of a cancelled token get a ~0 s time limit. After the solver
returns, the job checks :func:`is_cancelled` and stores ``CANCELLED`` instead of the (partial) result.
"""

from __future__ import annotations

import functools
import logging
import threading
import weakref
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

_local = threading.local()
_lock = threading.Lock()
_tokens: dict[int, CancelToken] = {}
_hooked = False


class CancelToken:
    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        self.event = threading.Event()
        self.done = threading.Event()  # set by release(): the job finished
        self._solvers: weakref.WeakSet[Any] = weakref.WeakSet()
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        return self.event.is_set()

    def register(self, solver: Any) -> None:
        with self._lock:
            self._solvers.add(solver)

    def stop_all(self) -> int:
        with self._lock:
            solvers = list(self._solvers)
        for s in solvers:
            try:
                s.stop_search()
            except Exception:  # noqa: BLE001
                log.debug("stop_search failed", exc_info=True)
        return len(solvers)


def token(run_id: int) -> CancelToken:
    with _lock:
        tok = _tokens.get(run_id)
        if tok is None:
            tok = _tokens[run_id] = CancelToken(run_id)
        return tok


def release(run_id: int) -> None:
    with _lock:
        tok = _tokens.pop(run_id, None)
    if tok is not None:
        tok.done.set()


def is_cancelled(run_id: int) -> bool:
    with _lock:
        tok = _tokens.get(run_id)
    return bool(tok and tok.cancelled)


def cancel(run_id: int) -> bool:
    """Flag ``run_id`` cancelled and stop its running CP-SAT searches. Returns True when a token existed
    (the job is or was running in this process)."""
    with _lock:
        tok = _tokens.get(run_id)
    if tok is None:
        tok = token(run_id)  # queued, not started yet: the job sees the flag when it starts
        tok.event.set()
        return False
    tok.event.set()
    tok.stop_all()

    def again() -> None:  # a search that was between "registered" and "started" when we stopped it
        for _ in range(25):
            if tok.done.wait(0.2):
                return
            tok.stop_all()

    threading.Thread(target=again, name=f"cancel-{run_id}", daemon=True).start()
    return True


def current() -> CancelToken | None:
    return getattr(_local, "token", None)


def bind[T](run_id: int, fn: Callable[..., T]) -> Callable[..., T]:
    """``fn`` running with ``run_id``'s token bound to the calling (worker) thread."""
    install_cpsat_hook()
    tok = token(run_id)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        prev = current()
        _local.token = tok
        try:
            return fn(*args, **kwargs)
        finally:
            _local.token = prev

    return wrapper


def install_cpsat_hook() -> None:
    global _hooked
    if _hooked:
        return
    try:
        from ortools.sat.python import cp_model
    except ImportError:  # pragma: no cover - OR-Tools is a dependency
        return
    with _lock:
        if _hooked:
            return
        cls = cp_model.CpSolver
        for name in ("solve", "Solve"):
            orig = getattr(cls, name, None)
            if orig is None or getattr(orig, "_smartsched_cancel", False):
                continue

            def make(orig: Any) -> Any:
                @functools.wraps(orig)
                def solve(self: Any, *args: Any, **kwargs: Any) -> Any:
                    tok = current()
                    if tok is not None:
                        tok.register(self)
                        if tok.cancelled:
                            self.parameters.max_time_in_seconds = 0.001
                    return orig(self, *args, **kwargs)

                solve._smartsched_cancel = True  # type: ignore[attr-defined]
                return solve

            setattr(cls, name, make(orig))
        _hooked = True


__all__ = ["CancelToken", "bind", "cancel", "install_cpsat_hook", "is_cancelled", "release", "token"]
