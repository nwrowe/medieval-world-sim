"""Small in-memory token-bucket limiter for the localhost HTTP bridge.

This is *not* a distributed/public reverse-proxy rate limiter. It prevents
accidental request floods and opportunistic abuse while the local multiplayer
backend remains single-process, without third-party dependencies.
"""
from __future__ import annotations

from threading import Lock
import time


class RateLimiter:
    def __init__(self, max_keys: int = 4096):
        self._lock = Lock()
        self._buckets: dict[tuple[str, ...], tuple[float, float]] = {}
        self._max_keys = max_keys

    def allow(self, key: tuple[str, ...], capacity: int, period: float) -> bool:
        """Spend one token; replenish capacity tokens per period.

        Keys are server-derived (never raw request bodies). A bounded map
        prevents a flood of distinct keys growing process memory indefinitely.
        """
        if capacity <= 0 or period <= 0:
            raise ValueError("Invalid token-bucket settings")
        now = time.monotonic()
        with self._lock:
            tokens, timestamp = self._buckets.get(key, (float(capacity), now))
            tokens = min(float(capacity),
                         tokens + max(0.0, now - timestamp) * capacity / period)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            if key not in self._buckets and len(self._buckets) >= self._max_keys:
                # Prune a bounded set of oldest buckets; deliberately prefer
                # existing active buckets over growing the key map.
                old = sorted(self._buckets, key=lambda k: self._buckets[k][1])
                for stale in old[:max(1, self._max_keys // 4)]:
                    self._buckets.pop(stale, None)
            self._buckets[key] = (tokens - 1.0, now)
            return True
