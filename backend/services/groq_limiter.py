"""Shared Groq rate limiter — ≤30 req/min token bucket.

Interactive callers (evaluator, live reply) call groq_acquire(interactive=True).
Batch ingestion uses groq_acquire(interactive=False) — it waits when the bucket
is below BATCH_RESERVE so interactive calls always have headroom.
"""
import asyncio
import time

_CAPACITY = 30           # max tokens (= 30 req/min ceiling)
_REFILL_RATE = 30 / 60  # tokens per second (0.5)
_BATCH_RESERVE = 5       # batch callers pause below this watermark
_POLL_INTERVAL = 1.0     # seconds between retry checks when waiting


class _GroqRateLimiter:
    def __init__(self) -> None:
        self._tokens: float = float(_CAPACITY)
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(float(_CAPACITY), self._tokens + elapsed * _REFILL_RATE)
        self._last_refill = now

    async def acquire(self, interactive: bool = True) -> None:
        threshold = 1.0 if interactive else float(_BATCH_RESERVE) + 1.0
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= threshold:
                    self._tokens -= 1.0
                    return
            await asyncio.sleep(_POLL_INTERVAL)


_limiter = _GroqRateLimiter()


async def groq_acquire(interactive: bool = True) -> None:
    """Acquire one Groq request slot. Blocks until a token is available."""
    await _limiter.acquire(interactive=interactive)
