"""In-process sliding-window rate limiting for the Agent endpoints."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

# Above this many tracked keys, a record() sweeps expired entries. Client IPs
# are attacker-chosen, so without a sweep a spoofed-source flood would grow the
# key map without bound.
_SWEEP_THRESHOLD = 1024


class SlidingWindowLimiter:
    """Allow at most ``limit`` events per ``window_seconds`` for each key.

    State is per-process and per-instance. The API runs under a single uvicorn
    worker, so a shared store would add a dependency without buying accuracy;
    under multiple workers each worker enforces its own quota and the effective
    limit multiplies by worker count.

    A non-positive ``limit`` disables the limiter entirely, which is how the
    settings turn it off.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._reported: dict[str, float] = {}
        # Sync FastAPI dependencies run in an anyio worker thread, so this
        # state is touched from more than one thread.
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._limit > 0 and self._window > 0

    def retry_after(self, key: str) -> float | None:
        """Seconds until ``key`` is under quota again, or None if it already is.

        Read-only — checking does not consume quota.
        """
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            events = self._events.get(key)
            if events is None:
                return None
            self._expire(events, now)
            if len(events) < self._limit:
                return None
            # events[0] is the oldest event still counted; quota frees up one
            # window after it. Callers must test the result with "is not None",
            # since a near-expired window legitimately returns 0.0.
            return max(events[0] + self._window - now, 0.0)

    def should_report(self, key: str) -> bool:
        """True at most once per window, on the first rejection of ``key``.

        Rejections are cheap by design; auditing every one would hand a flood
        an amplification vector, since each rejected request would cost a disk
        write. One row per key per window keeps the signal without the cost.
        """
        now = time.monotonic()
        with self._lock:
            last = self._reported.get(key)
            if last is not None and now - last < self._window:
                return False
            self._reported[key] = now
            return True

    def record(self, key: str) -> None:
        """Count one event against ``key``."""
        if not self.enabled:
            return
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(key, deque())
            self._expire(events, now)
            events.append(now)
            if len(self._events) > _SWEEP_THRESHOLD:
                self._sweep(now)

    def _expire(self, events: deque[float], now: float) -> None:
        cutoff = now - self._window
        while events and events[0] <= cutoff:
            events.popleft()

    def _sweep(self, now: float) -> None:
        """Drop keys whose events have all expired. Caller holds the lock."""
        cutoff = now - self._window
        stale = [key for key, events in self._events.items() if not events or events[-1] <= cutoff]
        for key in stale:
            del self._events[key]
            self._reported.pop(key, None)


@dataclass(frozen=True)
class AgentRateLimiters:
    """The two quotas guarding ``/agent/*``.

    They protect different things and so are counted separately: ``auth_failures``
    is keyed by client address and bounds token guessing, while ``requests`` is
    keyed by authenticated actor and bounds runaway agent loops (which cost
    real model spend).
    """

    auth_failures: SlidingWindowLimiter
    requests: SlidingWindowLimiter
