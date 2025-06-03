import time
from unittest.mock import AsyncMock, patch

import pytest

from crudadmin.core.rate_limiter import (
    RateLimitData,
    SimpleRateLimiter,
    create_rate_limiter,
)
from crudadmin.session.storage import get_session_storage


class TestRateLimitData:
    """Test the RateLimitData model."""

    def test_rate_limit_data_initialization(self):
        """Test RateLimitData initialization with default values."""
        data = RateLimitData(first_attempt=time.time())
        assert data.count == 0
        assert isinstance(data.first_attempt, float)

    def test_rate_limit_data_with_values(self):
        """Test RateLimitData initialization with custom values."""
        current_time = time.time()
        data = RateLimitData(count=5, first_attempt=current_time)
        assert data.count == 5
        assert data.first_attempt == current_time


class TestSimpleRateLimiter:
    """Test the SimpleRateLimiter class."""

    @pytest.fixture
    async def memory_storage(self):
        """Create a memory storage for testing."""
        storage = get_session_storage(
            backend="memory",
            model_type=RateLimitData,
            prefix="test_rate_limit:",
            expiration=60,  # 1 minute
        )
        yield storage
        await storage.close()

    @pytest.fixture
    async def rate_limiter(self, memory_storage):
        """Create a rate limiter instance for testing."""
        return SimpleRateLimiter(memory_storage)

    @pytest.mark.asyncio
    async def test_rate_limiter_initialization(self, memory_storage):
        """Test SimpleRateLimiter initialization."""
        rate_limiter = SimpleRateLimiter(memory_storage)
        assert rate_limiter.storage == memory_storage

    @pytest.mark.asyncio
    async def test_increment_first_attempt(self, rate_limiter):
        """Test incrementing a counter for the first time."""
        key = "test_key"
        result = await rate_limiter.increment(key, 1, 60)

        assert result == 1

        # Verify the data was stored
        count = await rate_limiter.get_count(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_increment_multiple_attempts(self, rate_limiter):
        """Test incrementing a counter multiple times."""
        key = "test_key"

        # First attempt
        result1 = await rate_limiter.increment(key, 1, 60)
        assert result1 == 1

        # Second attempt
        result2 = await rate_limiter.increment(key, 1, 60)
        assert result2 == 2

        # Third attempt
        result3 = await rate_limiter.increment(key, 1, 60)
        assert result3 == 3

        # Verify final count
        count = await rate_limiter.get_count(key)
        assert count == 3

    @pytest.mark.asyncio
    async def test_increment_custom_value(self, rate_limiter):
        """Test incrementing with custom increment value."""
        key = "test_key"

        # Increment by 5
        result1 = await rate_limiter.increment(key, 5, 60)
        assert result1 == 5

        # Increment by 3
        result2 = await rate_limiter.increment(key, 3, 60)
        assert result2 == 8

        # Verify final count
        count = await rate_limiter.get_count(key)
        assert count == 8

    @pytest.mark.asyncio
    async def test_increment_expired_window(self, rate_limiter):
        """Test incrementing after the time window has expired."""
        key = "test_key"

        # First attempt
        result1 = await rate_limiter.increment(key, 1, 1)  # 1-second window
        assert result1 == 1

        # Wait for window to expire
        import asyncio

        await asyncio.sleep(1.1)

        # Second attempt after expiry should reset counter
        result2 = await rate_limiter.increment(key, 1, 1)
        assert result2 == 1  # Counter should reset

        # Verify count
        count = await rate_limiter.get_count(key)
        assert count == 1

    @pytest.mark.asyncio
    async def test_delete_key(self, rate_limiter):
        """Test deleting a rate limit key."""
        key = "test_key"

        # Create some data
        await rate_limiter.increment(key, 1, 60)
        assert await rate_limiter.get_count(key) == 1

        # Delete the key
        await rate_limiter.delete(key)

        # Verify it's gone
        count = await rate_limiter.get_count(key)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_count_nonexistent_key(self, rate_limiter):
        """Test getting count for a non-existent key."""
        count = await rate_limiter.get_count("nonexistent_key")
        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_keys(self, rate_limiter):
        """Test rate limiting with multiple keys."""
        key1 = "user:1"
        key2 = "user:2"

        # Increment different keys
        await rate_limiter.increment(key1, 1, 60)
        await rate_limiter.increment(key1, 1, 60)
        await rate_limiter.increment(key2, 1, 60)

        # Verify counts are separate
        assert await rate_limiter.get_count(key1) == 2
        assert await rate_limiter.get_count(key2) == 1

    @pytest.mark.asyncio
    async def test_close(self, rate_limiter):
        """Test closing the rate limiter."""
        # This should not raise an exception
        await rate_limiter.close()


class TestCreateRateLimiter:
    """Test the create_rate_limiter factory function."""

    @pytest.mark.asyncio
    async def test_create_memory_rate_limiter(self):
        """Test creating a memory-based rate limiter."""
        rate_limiter = create_rate_limiter("memory", expiration=300)

        assert isinstance(rate_limiter, SimpleRateLimiter)
        assert rate_limiter.storage.prefix == "rate_limit:"
        assert rate_limiter.storage.expiration == 300

        await rate_limiter.close()

    @pytest.mark.asyncio
    async def test_create_rate_limiter_custom_prefix(self):
        """Test creating a rate limiter with custom prefix."""
        rate_limiter = create_rate_limiter("memory", prefix="custom:", expiration=300)

        assert isinstance(rate_limiter, SimpleRateLimiter)
        assert rate_limiter.storage.prefix == "custom:"

        await rate_limiter.close()

    @pytest.mark.asyncio
    async def test_create_rate_limiter_default_prefix(self):
        """Test creating a rate limiter with default prefix."""
        rate_limiter = create_rate_limiter("memory", expiration=300)

        assert isinstance(rate_limiter, SimpleRateLimiter)
        assert rate_limiter.storage.prefix == "rate_limit:"

        await rate_limiter.close()

    def test_create_rate_limiter_invalid_backend(self):
        """Test creating a rate limiter with invalid backend."""
        with pytest.raises(ValueError, match="Unknown backend"):
            create_rate_limiter("invalid_backend")


class TestRateLimiterIntegration:
    """Integration tests for rate limiter with different backends."""

    @pytest.mark.asyncio
    async def test_memory_backend_integration(self):
        """Test rate limiter with memory backend."""
        rate_limiter = create_rate_limiter("memory", expiration=60)

        try:
            # Test basic functionality
            key = "integration_test"

            result1 = await rate_limiter.increment(key, 1, 60)
            assert result1 == 1

            result2 = await rate_limiter.increment(key, 1, 60)
            assert result2 == 2

            count = await rate_limiter.get_count(key)
            assert count == 2

            await rate_limiter.delete(key)
            count = await rate_limiter.get_count(key)
            assert count == 0

        finally:
            await rate_limiter.close()

    @pytest.mark.asyncio
    async def test_redis_backend_fallback(self):
        """Test that Redis backend fails gracefully when Redis is unavailable."""
        # This test assumes Redis is not running
        with patch(
            "crudadmin.session.backends.redis.RedisSessionStorage"
        ) as mock_redis:
            # Mock Redis to raise connection error
            mock_storage = AsyncMock()
            mock_storage.get.side_effect = ConnectionError("Redis unavailable")
            mock_storage.create.side_effect = ConnectionError("Redis unavailable")
            mock_storage.update.side_effect = ConnectionError("Redis unavailable")
            mock_storage.delete.side_effect = ConnectionError("Redis unavailable")
            mock_redis.return_value = mock_storage

            rate_limiter = create_rate_limiter("redis", host="localhost", port=6379)

            try:
                # These operations should not raise exceptions
                # but they won't work properly due to connection issues
                key = "test_key"

                # The rate limiter should handle the exception gracefully
                # Note: The actual behavior depends on how the storage handles errors
                with pytest.raises(ConnectionError):
                    await rate_limiter.increment(key, 1, 60)

            finally:
                await rate_limiter.close()


class TestRateLimiterErrorHandling:
    """Test error handling in rate limiter."""

    @pytest.mark.asyncio
    async def test_storage_error_handling(self):
        """Test rate limiter behavior when storage operations fail."""
        # Create a mock storage that raises errors
        mock_storage = AsyncMock()
        mock_storage.get.side_effect = Exception("Storage error")
        mock_storage.create.side_effect = Exception("Storage error")
        mock_storage.update.side_effect = Exception("Storage error")
        mock_storage.delete.side_effect = Exception("Storage error")

        rate_limiter = SimpleRateLimiter(mock_storage)

        # These operations should raise exceptions
        with pytest.raises(Exception, match="Storage error"):
            await rate_limiter.increment("key", 1, 60)

        with pytest.raises(Exception, match="Storage error"):
            await rate_limiter.delete("key")

        with pytest.raises(Exception, match="Storage error"):
            await rate_limiter.get_count("key")

    @pytest.mark.asyncio
    async def test_partial_storage_failure(self):
        """Test rate limiter when some storage operations fail."""
        mock_storage = AsyncMock()

        # get() succeeds, returns None (no existing data)
        mock_storage.get.return_value = None

        # create() fails
        mock_storage.create.side_effect = Exception("Create failed")

        rate_limiter = SimpleRateLimiter(mock_storage)

        with pytest.raises(Exception, match="Create failed"):
            await rate_limiter.increment("key", 1, 60)


class TestRateLimiterPerformance:
    """Performance-related tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_concurrent_increments(self):
        """Test concurrent increments on the same key."""
        import asyncio

        rate_limiter = create_rate_limiter("memory", expiration=300)

        try:
            key = "concurrent_test"

            # Create multiple concurrent increment tasks
            tasks = []
            for _ in range(10):
                task = asyncio.create_task(rate_limiter.increment(key, 1, 300))
                tasks.append(task)

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks)

            # Verify all increments were processed
            # Note: Due to race conditions, the exact order might vary
            # but all increments should be unique values from 1 to 10
            assert len(results) == 10
            assert len(set(results)) == 10  # All results should be unique
            assert min(results) == 1
            assert max(results) == 10

            # Final count should be 10
            final_count = await rate_limiter.get_count(key)
            assert final_count == 10

        finally:
            await rate_limiter.close()

    @pytest.mark.asyncio
    async def test_many_keys_performance(self):
        """Test performance with many different keys."""
        rate_limiter = create_rate_limiter("memory", expiration=300)

        try:
            # Create many keys
            num_keys = 100
            keys = [f"key_{i}" for i in range(num_keys)]

            # Increment each key once
            for key in keys:
                result = await rate_limiter.increment(key, 1, 300)
                assert result == 1

            # Verify all keys have count 1
            for key in keys:
                count = await rate_limiter.get_count(key)
                assert count == 1

        finally:
            await rate_limiter.close()
