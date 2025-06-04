"""Simple rate limiter implementation using session storage backends."""

import logging

from pydantic import BaseModel

from ..session.storage import AbstractSessionStorage, get_session_storage

logger = logging.getLogger(__name__)


class RateLimitData(BaseModel):
    """Data model for rate limit counters."""

    count: int = 0
    first_attempt: float


class SimpleRateLimiter:
    """Simple rate limiter using session storage backends."""

    def __init__(self, storage: AbstractSessionStorage[RateLimitData]):
        """Initialize the rate limiter.

        Args:
            storage: The storage backend to use for rate limiting
        """
        self.storage = storage

    async def increment(
        self, key: str, increment_value: int, expiry_seconds: int
    ) -> int:
        """Increment the counter for a key and return current count.

        Args:
            key: The rate limit key
            increment_value: Amount to increment (typically 1)
            expiry_seconds: Expiry time in seconds

        Returns:
            Current count for the key after increment
        """
        import time

        current_time = time.time()

        existing = await self.storage.get(key, RateLimitData)

        if existing is None:
            new_data = RateLimitData(count=increment_value, first_attempt=current_time)
            await self.storage.create(
                new_data, session_id=key, expiration=expiry_seconds
            )
            return increment_value

        if current_time - existing.first_attempt > expiry_seconds:
            new_data = RateLimitData(count=increment_value, first_attempt=current_time)
            await self.storage.update(key, new_data, expiration=expiry_seconds)
            return increment_value

        existing.count += increment_value
        await self.storage.update(key, existing, reset_expiration=False)
        return existing.count

    async def delete(self, key: str) -> None:
        """Delete a rate limit key.

        Args:
            key: The rate limit key to delete
        """
        await self.storage.delete(key)

    async def get_count(self, key: str) -> int:
        """Get current count for a key.

        Args:
            key: The rate limit key

        Returns:
            Current count (0 if key doesn't exist)
        """
        data = await self.storage.get(key, RateLimitData)
        return data.count if data else 0

    async def close(self) -> None:
        """Close the storage connection."""
        await self.storage.close()


def create_rate_limiter(backend: str, **backend_kwargs) -> SimpleRateLimiter:
    """Create a rate limiter using the specified backend.

    Args:
        backend: Backend type ("redis", "memcached", "memory")
        **backend_kwargs: Additional backend configuration

    Returns:
        Configured rate limiter instance
    """
    if "prefix" not in backend_kwargs:
        backend_kwargs["prefix"] = "rate_limit:"

    storage: AbstractSessionStorage[RateLimitData] = get_session_storage(
        backend=backend, model_type=RateLimitData, **backend_kwargs
    )

    return SimpleRateLimiter(storage)
