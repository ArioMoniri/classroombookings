"""Small in-process sliding-window counters (CRBS parity audit B10: public password-reset requests).

Per process, like :mod:`app.core.ratelimit` (the login limiter); behind several workers each keeps its own
count, which is enough against a single client flooding an account with reset e-mails.

    RESET = Throttle(window_s=900, limit=3)
    if RESET.hit("acct:42"): ...   # True = over the limit (the hit is not recorded then)
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class Throttle:
    def __init__(self, window_s: float, limit: int) -> None:
        self.window_s = window_s
        self.limit = limit
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, q: deque[float], now: float) -> None:
        while q and now - q[0] > self.window_s:
            q.popleft()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                return False
            self._prune(q, now)
            return len(q) >= self.limit

    def hit(self, key: str) -> bool:
        """Record one event for ``key``; ``True`` (and nothing recorded) when the limit is already reached."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            if len(q) >= self.limit:
                return True
            q.append(now)
            return False

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            self._prune(q, now)
            return int(self.window_s - (now - q[0])) + 1 if len(q) >= self.limit else 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


#: public ``POST /auth/password-reset/request``: per account (silently ignored above it) and per address (429)
RESET_PER_ACCOUNT = Throttle(window_s=900, limit=3)
RESET_PER_ADDRESS = Throttle(window_s=900, limit=20)

#: calendar subscription feeds (``/calendar/feeds/{token}/…``, ``/ics/{token}/…``): per link (token hash) and per
#: client address; calendar apps poll every few minutes to hours, so these only stop runaway clients and guessing
FEED_PER_TOKEN = Throttle(window_s=300, limit=60)
FEED_PER_ADDRESS = Throttle(window_s=300, limit=600)


def reset_all() -> None:
    RESET_PER_ACCOUNT.reset()
    RESET_PER_ADDRESS.reset()
    FEED_PER_TOKEN.reset()
    FEED_PER_ADDRESS.reset()
