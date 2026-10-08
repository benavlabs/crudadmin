import time
from typing import Awaitable, Callable

RECORD_COUNT_TTL_SECONDS = 60.0


class RecordCounts:
    """Record counts per model for the dashboard, kept for a while instead of recounted.

    ``COUNT(*)`` on a large table is slow on most databases, so each count is kept
    for ``ttl_seconds``. The admin forgets a model's count when it creates or
    deletes one of its records, so its own changes show at once; changes made
    outside the admin show once the count expires.

    Example:
        ```python
        counts = RecordCounts()
        total = await counts.get("Article", lambda: crud.count(db))
        counts.forget("Article")
        ```
    """

    def __init__(
        self,
        ttl_seconds: float = RECORD_COUNT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._counts: dict[str, tuple[int, float]] = {}

    async def get(self, model_name: str, count: Callable[[], Awaitable[int]]) -> int:
        """The model's count, from ``count()`` unless one younger than the TTL is kept."""
        kept = self._counts.get(model_name)
        now = self._clock()
        if kept is not None and now - kept[1] < self.ttl_seconds:
            return kept[0]
        total = await count()
        self._counts[model_name] = (total, now)
        return total

    def forget(self, model_name: str) -> None:
        self._counts.pop(model_name, None)
