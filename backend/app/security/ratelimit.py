"""In-process sliding-window rate limiting (per client key). Use a shared store (Redis) for multiple replicas."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return False, int(window_s - (now - q[0])) + 1
            q.append(now)
            return True, 0

    def count(self, key: str, window_s: float) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for t in self._hits.get(key, ()) if t > now - window_s)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


login_failures = SlidingWindow()
api_requests = SlidingWindow()
