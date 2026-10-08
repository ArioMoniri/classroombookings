"""In-process login failure limiter (review MINOR 5): too many failed logins for one identifier from one
client address (or from one address overall) within a window answer 429 until the window passes. Per
process; behind several workers each keeps its own count (good enough against online guessing)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

WINDOW_S = 300.0
MAX_PER_IDENTIFIER = 10
MAX_PER_ADDRESS = 50

_lock = threading.Lock()
_fails: dict[str, deque[float]] = defaultdict(deque)


def _keys(address: str, identifier: str) -> tuple[str, str]:
    return f"id:{address}|{identifier.strip().casefold()}", f"ip:{address}"


def _prune(q: deque[float], now: float) -> None:
    while q and now - q[0] > WINDOW_S:
        q.popleft()


def retry_after(address: str, identifier: str) -> int:
    """Seconds until the next attempt is allowed (0 = allowed now)."""
    now = time.monotonic()
    k_id, k_ip = _keys(address, identifier)
    with _lock:
        waits = []
        for key, cap in ((k_id, MAX_PER_IDENTIFIER), (k_ip, MAX_PER_ADDRESS)):
            q = _fails.get(key)
            if q is None:
                continue
            _prune(q, now)
            if len(q) >= cap:
                waits.append(int(WINDOW_S - (now - q[0])) + 1)
        return max(waits, default=0)


def failure(address: str, identifier: str) -> None:
    now = time.monotonic()
    with _lock:
        for key in _keys(address, identifier):
            _fails[key].append(now)


def success(address: str, identifier: str) -> None:
    with _lock:
        _fails.pop(_keys(address, identifier)[0], None)


def reset() -> None:
    with _lock:
        _fails.clear()
