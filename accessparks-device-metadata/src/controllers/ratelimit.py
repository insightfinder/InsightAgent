"""Shared token-bucket limiter for vendor APIs with a hard requests/window quota
(Baicells: 20/min, NetExperience: 180/10s). One instance per controller — the
quota is per-account, not global — shared across every call path (list, detail,
enrichment) that hits the same API.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Evenly spaces calls at per_seconds/max_requests apart (a leaky bucket)
    rather than counting requests in a sliding window. Each acquire() reserves
    its own slot atomically and sleeps exactly once for its own precomputed
    duration — under contention from many threads (e.g. NetExperience's bounded
    thread pool), a windowed-count design has every blocked thread wake near
    the same instant to re-fight over the lock and recompute; this design gives
    each caller a distinct wake time up front, so there's nothing to re-fight.
    """

    def __init__(self, max_requests: int, per_seconds: float) -> None:
        self.interval = per_seconds / max_requests
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        """Block until a request is allowed under the limit, then record it."""
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self.interval
        wait = slot - now
        if wait > 0:
            time.sleep(wait)
