"""Sliding-window rate limiter for per-IP and per-tenant request throttling."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from app.core.exceptions import RateLimitError


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter keyed by scope (IP or tenant ID)."""

    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int) -> None:
        if limit <= 0:
            raise RateLimitError(retry_after=self.window_seconds)
        now = time.monotonic()
        cutoff = now - self.window_seconds
        bucket = self._buckets[key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
            raise RateLimitError(
                message=f"Rate limit exceeded ({limit} requests per {self.window_seconds}s)",
                retry_after=retry_after,
            )
        bucket.append(now)

    def reset(self) -> None:
        self._buckets.clear()
