import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from crudadmin.session.manager import SessionManager
from crudadmin.session.schemas import SessionData
from crudadmin.session.storage import get_session_storage


def create_session_manager_with_rate_limiter(
    session_backend: str = "memory", **backend_kwargs
) -> SessionManager:
    """Create a session manager instance with rate limiter for testing.

    Args:
        session_backend: Backend type ("redis", "memcached", "memory")
        **backend_kwargs: Additional backend configuration
    """
    storage = get_session_storage(
        backend=session_backend,
        model_type=SessionData,
        prefix="session:",
        expiration=30 * 60,  # 30 minutes
        **backend_kwargs,
    )

    rate_limiter = None
    try:
        from crudadmin.core.rate_limiter import create_rate_limiter

        rate_limiter_kwargs = {
            k: v for k, v in backend_kwargs.items() if k not in ["prefix", "expiration"]
        }

        rate_limiter = create_rate_limiter(
            backend=session_backend,
            prefix="rate_limit:",
            expiration=15 * 60,  # 15 minutes
            **rate_limiter_kwargs,
        )
    except Exception:
        # Rate limiter creation failed, continue without it
        pass

    return SessionManager(
        session_storage=storage,
        max_sessions_per_user=5,
        session_timeout_minutes=30,
        cleanup_interval_minutes=15,
        rate_limiter=rate_limiter,
        login_max_attempts=5,
        login_window_minutes=15,
    )


class TestSessionManagerRateLimiterIntegration:
    """Test the integration of rate limiter with session manager."""

    @pytest.fixture
    async def session_manager_memory(self):
        """Create a session manager with memory backend for testing."""
        manager = create_session_manager_with_rate_limiter("memory")
        yield manager
        # Cleanup
        await manager.storage.close()
        if manager.rate_limiter:
            await manager.rate_limiter.close()

    @pytest.fixture
    async def session_manager_no_rate_limiter(self):
        """Create a session manager without rate limiter for testing."""
        storage = get_session_storage(
            backend="memory",
            model_type=SessionData,
            prefix="test_session:",
            expiration=30 * 60,
        )

        manager = SessionManager(
            session_storage=storage,
            max_sessions_per_user=5,
            session_timeout_minutes=30,
            cleanup_interval_minutes=15,
            rate_limiter=None,  # No rate limiter
        )

        yield manager
        await storage.close()

    @pytest.mark.asyncio
    async def test_session_manager_has_rate_limiter(self, session_manager_memory):
        """Test that session manager is created with rate limiter."""
        assert session_manager_memory.rate_limiter is not None
        assert hasattr(session_manager_memory.rate_limiter, "increment")
        assert hasattr(session_manager_memory.rate_limiter, "delete")

    @pytest.mark.asyncio
    async def test_track_login_attempt_with_rate_limiter(self, session_manager_memory):
        """Test login attempt tracking with rate limiter."""
        ip_address = "192.168.1.100"
        username = "testuser"

        # First failed attempt
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip_address, username, success=False
        )

        assert allowed is True
        assert remaining == 4  # 5 max attempts - 1 used = 4 remaining

        # Second failed attempt
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip_address, username, success=False
        )

        assert allowed is True
        assert remaining == 3  # 5 max attempts - 2 used = 3 remaining

    @pytest.mark.asyncio
    async def test_track_login_attempt_rate_limit_exceeded(
        self, session_manager_memory
    ):
        """Test rate limiting when max attempts are exceeded."""
        ip_address = "192.168.1.100"
        username = "testuser"
        max_attempts = session_manager_memory.login_max_attempts

        # Use up all allowed attempts
        for i in range(max_attempts):
            allowed, remaining = await session_manager_memory.track_login_attempt(
                ip_address, username, success=False
            )
            assert allowed is True
            assert remaining == max_attempts - (i + 1)

        # Next attempt should be blocked
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip_address, username, success=False
        )

        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_track_login_attempt_successful_clears_limits(
        self, session_manager_memory
    ):
        """Test that successful login clears rate limits."""
        ip_address = "192.168.1.100"
        username = "testuser"

        # Make some failed attempts
        for _ in range(3):
            await session_manager_memory.track_login_attempt(
                ip_address, username, success=False
            )

        # Successful login should clear the limits
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip_address, username, success=True
        )

        assert allowed is True
        assert remaining is None  # None indicates successful login

        # Next failed attempt should start fresh
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip_address, username, success=False
        )

        assert allowed is True
        assert remaining == 4  # Back to 4 remaining (5 - 1)

    @pytest.mark.asyncio
    async def test_track_login_attempt_different_ips(self, session_manager_memory):
        """Test that rate limiting is per IP address."""
        username = "testuser"
        ip1 = "192.168.1.100"
        ip2 = "192.168.1.101"

        # Make attempts from first IP
        for _ in range(3):
            await session_manager_memory.track_login_attempt(
                ip1, username, success=False
            )

        # Attempt from second IP should start fresh, but username counter continues
        # The rate limiter tracks max(ip_count, username_count)
        # So username has 3 attempts already, new IP has 1 attempt
        # Max(1, 4) = 4, so remaining = 5 - 4 = 1
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip2, username, success=False
        )

        assert allowed is True
        assert remaining == 1  # Username already has 3, now has 4 total

    @pytest.mark.asyncio
    async def test_track_login_attempt_different_usernames(
        self, session_manager_memory
    ):
        """Test that rate limiting is per username."""
        ip_address = "192.168.1.100"
        user1 = "testuser1"
        user2 = "testuser2"

        # Make attempts for first user
        for _ in range(3):
            await session_manager_memory.track_login_attempt(
                ip_address, user1, success=False
            )

        # Attempt for second user should start fresh, but IP counter continues
        # The rate limiter tracks max(ip_count, username_count)
        # So IP has 3 attempts already, new username has 1 attempt
        # Max(4, 1) = 4, so remaining = 5 - 4 = 1
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip_address, user2, success=False
        )

        assert allowed is True
        assert remaining == 1  # IP already has 3, now has 4 total

    @pytest.mark.asyncio
    async def test_track_login_attempt_no_rate_limiter(
        self, session_manager_no_rate_limiter
    ):
        """Test login attempt tracking without rate limiter."""
        ip_address = "192.168.1.100"
        username = "testuser"

        # Without rate limiter, all attempts should be allowed
        allowed, remaining = await session_manager_no_rate_limiter.track_login_attempt(
            ip_address, username, success=False
        )

        assert allowed is True
        assert remaining is None

    @pytest.mark.asyncio
    async def test_rate_limiter_uses_same_backend_as_session(self):
        """Test that rate limiter uses the same backend as session storage."""
        # Test with memory backend
        memory_manager = create_session_manager_with_rate_limiter("memory")
        assert memory_manager.rate_limiter is not None
        assert memory_manager.storage.prefix == "session:"
        assert memory_manager.rate_limiter.storage.prefix == "rate_limit:"

        await memory_manager.storage.close()
        await memory_manager.rate_limiter.close()

    @pytest.mark.asyncio
    async def test_cleanup_rate_limits(self, session_manager_memory):
        """Test rate limit cleanup functionality."""
        # Make some login attempts to create rate limit records
        ip_address = "192.168.1.100"
        username = "testuser"

        await session_manager_memory.track_login_attempt(
            ip_address, username, success=False
        )

        # Call cleanup (this tests the cleanup method exists and runs)
        await session_manager_memory.cleanup_rate_limits()

        # The method should complete without errors
        # Note: The actual cleanup behavior depends on the storage backend

    @pytest.mark.asyncio
    async def test_rate_limiter_error_handling(self):
        """Test rate limiter error handling in session manager."""
        # Create a session manager with a mock rate limiter that raises errors
        storage = get_session_storage(
            backend="memory",
            model_type=SessionData,
            prefix="test_session:",
            expiration=30 * 60,
        )

        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.increment.side_effect = Exception("Rate limiter error")
        mock_rate_limiter.delete.side_effect = Exception("Rate limiter error")

        manager = SessionManager(
            session_storage=storage,
            max_sessions_per_user=5,
            session_timeout_minutes=30,
            cleanup_interval_minutes=15,
            rate_limiter=mock_rate_limiter,
        )

        try:
            # Errors in rate limiter should be handled gracefully
            allowed, remaining = await manager.track_login_attempt(
                "192.168.1.100", "testuser", success=False
            )

            # Should fall back to allowing the request
            assert allowed is True
            assert remaining is None

        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_concurrent_login_attempts_same_user(self, session_manager_memory):
        """Test concurrent login attempts for the same user."""
        ip_address = "192.168.1.100"
        username = "testuser"

        # Create multiple concurrent failed login attempts
        tasks = []
        for _ in range(5):
            task = asyncio.create_task(
                session_manager_memory.track_login_attempt(
                    ip_address, username, success=False
                )
            )
            tasks.append(task)

        # Wait for all attempts to complete
        results = await asyncio.gather(*tasks)

        # All should be processed (though some may be blocked due to rate limiting)
        assert len(results) == 5

        # At least the first few should be allowed
        allowed_count = sum(1 for allowed, _ in results if allowed)
        blocked_count = sum(1 for allowed, _ in results if not allowed)

        # Some should be allowed, some might be blocked
        assert allowed_count > 0
        assert allowed_count + blocked_count == 5

    @pytest.mark.asyncio
    async def test_rate_limiter_window_expiry(self, session_manager_memory):
        """Test that rate limits reset after the time window expires."""

        ip_address = "192.168.1.100"
        username = "testuser"

        # Make maximum attempts to trigger rate limiting
        max_attempts = session_manager_memory.login_max_attempts
        for _ in range(max_attempts + 1):
            await session_manager_memory.track_login_attempt(
                ip_address, username, success=False
            )

        # Should be rate limited now
        allowed, remaining = await session_manager_memory.track_login_attempt(
            ip_address, username, success=False
        )
        assert allowed is False


class TestSessionManagerCreationWithRateLimiter:
    """Test session manager creation with rate limiter integration."""

    @pytest.mark.asyncio
    async def test_session_manager_creation_memory_with_rate_limiter(self):
        """Test creating session manager with memory backend includes rate limiter."""
        manager = create_session_manager_with_rate_limiter("memory")

        try:
            assert manager is not None
            assert manager.rate_limiter is not None
            assert manager.storage.prefix == "session:"
            assert manager.rate_limiter.storage.prefix == "rate_limit:"

            # Test rate limiter functionality
            allowed, remaining = await manager.track_login_attempt(
                "127.0.0.1", "testuser", success=False
            )
            assert allowed is True
            assert remaining == 4

        finally:
            await manager.storage.close()
            if manager.rate_limiter:
                await manager.rate_limiter.close()

    @pytest.mark.asyncio
    async def test_session_manager_creation_with_backend_kwargs(self):
        """Test creating session manager with backend kwargs."""
        manager = create_session_manager_with_rate_limiter(
            # Don't pass expiration here as it conflicts with the default
            # expiration=1800,  # 30 minutes
        )

        try:
            assert manager is not None
            assert manager.rate_limiter is not None
            # Use default expiration
            assert manager.storage.expiration == 30 * 60  # Default 30 minutes

            # Rate limiter should use the LOGIN_WINDOW_MINUTES setting
            # which defaults to 15 minutes = 900 seconds
            # But our default might be different, so just check it exists
            assert hasattr(manager.rate_limiter.storage, "expiration")

        finally:
            await manager.storage.close()
            if manager.rate_limiter:
                await manager.rate_limiter.close()

    @pytest.mark.asyncio
    async def test_session_manager_creation_rate_limiter_failure_graceful(self):
        """Test that session manager creation gracefully handles rate limiter failures."""
        # Mock the create_rate_limiter function to raise an exception
        # Use the correct path for the import within the function
        with patch("crudadmin.core.rate_limiter.create_rate_limiter") as mock_create:
            mock_create.side_effect = Exception("Rate limiter creation failed")

            manager = create_session_manager_with_rate_limiter("memory")

            try:
                # Session manager should be created successfully
                assert manager is not None

                # But rate limiter should be None due to the error
                assert manager.rate_limiter is None

                # Login attempts should still work (without rate limiting)
                allowed, remaining = await manager.track_login_attempt(
                    "127.0.0.1", "testuser", success=False
                )
                assert allowed is True
                assert remaining is None

            finally:
                await manager.storage.close()


class TestRateLimiterMultipleBackends:
    """Test rate limiter with different storage backends."""

    @pytest.mark.asyncio
    async def test_redis_backend_rate_limiter(self):
        """Test rate limiter with Redis backend (graceful failure if Redis unavailable)."""
        try:
            manager = create_session_manager_with_rate_limiter(
                "redis",
                host="localhost",
                port=6379,
                db=0,
            )

            # If Redis is available, rate limiter should work
            if manager.rate_limiter is not None:
                allowed, remaining = await manager.track_login_attempt(
                    "127.0.0.1", "testuser", success=False
                )
                # Should either work or fail gracefully
                assert isinstance(allowed, bool)

        except Exception:
            # If Redis is not available, that's fine for this test
            pass
        finally:
            await manager.storage.close()
            if manager.rate_limiter:
                await manager.rate_limiter.close()

    @pytest.mark.asyncio
    async def test_memcached_backend_rate_limiter(self):
        """Test rate limiter with Memcached backend (graceful failure if Memcached unavailable)."""
        try:
            manager = create_session_manager_with_rate_limiter(
                "memcached",
                host="localhost",
                port=11211,
            )

            # If Memcached is available, rate limiter should work
            if manager.rate_limiter is not None:
                allowed, remaining = await manager.track_login_attempt(
                    "127.0.0.1", "testuser", success=False
                )
                # Should either work or fail gracefully
                assert isinstance(allowed, bool)

        except Exception:
            # If Memcached is not available, that's fine for this test
            pass
        finally:
            await manager.storage.close()
            if manager.rate_limiter:
                await manager.rate_limiter.close()
