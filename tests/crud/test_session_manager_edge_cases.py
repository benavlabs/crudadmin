"""Tests for edge cases and error conditions in session manager recreation."""

import pytest

from crudadmin import CRUDAdmin
from tests.crud.test_admin import create_test_db_config


class TestSessionManagerEdgeCases:
    """Test edge cases in session manager recreation."""

    @pytest.mark.asyncio
    async def test_multiple_backend_switches(self, async_session):
        """Test switching between multiple backends rapidly."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        # Rapid switches between backends
        admin.use_memory_sessions()
        assert "MemorySessionStorage" in str(type(admin.session_manager.storage))

        admin.use_database_sessions()
        assert "DatabaseSessionStorage" in str(type(admin.session_manager.storage))

        admin.use_memory_sessions()
        assert "MemorySessionStorage" in str(type(admin.session_manager.storage))

        admin.use_database_sessions()
        assert "DatabaseSessionStorage" in str(type(admin.session_manager.storage))

    @pytest.mark.asyncio
    async def test_session_manager_with_custom_settings(self, async_session):
        """Test that custom session settings are preserved across backend switches."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            max_sessions_per_user=5,
            session_timeout_minutes=120,
            cleanup_interval_minutes=30,
        )

        # Verify initial settings
        assert admin.session_manager.max_sessions == 5
        assert admin.session_manager.session_timeout.total_seconds() == 120 * 60
        assert admin.session_manager.cleanup_interval.total_seconds() == 30 * 60

        # Switch backends and verify settings preserved
        admin.use_database_sessions()
        assert admin.session_manager.max_sessions == 5
        assert admin.session_manager.session_timeout.total_seconds() == 120 * 60
        assert admin.session_manager.cleanup_interval.total_seconds() == 30 * 60

        admin.use_memory_sessions()
        assert admin.session_manager.max_sessions == 5
        assert admin.session_manager.session_timeout.total_seconds() == 120 * 60
        assert admin.session_manager.cleanup_interval.total_seconds() == 30 * 60

    @pytest.mark.asyncio
    async def test_hybrid_mode_settings(self, async_session):
        """Test hybrid mode settings with Redis + database tracking."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Enable Redis with database tracking
            admin.use_redis_sessions(host="localhost", track_sessions_in_db=True)

            # Should be hybrid mode
            storage_name = type(admin.session_manager.storage).__name__
            assert storage_name in ["HybridSessionStorage", "RedisSessionStorage"]
            assert admin.track_sessions_in_db is True

            # Switch to Memcached with database tracking
            admin.use_memcached_sessions(host="localhost", track_sessions_in_db=True)
            storage_name = type(admin.session_manager.storage).__name__
            assert storage_name in ["HybridSessionStorage", "MemcachedSessionStorage"]
            assert admin.track_sessions_in_db is True

        except ImportError:
            pytest.skip("Redis or Memcached not available")

    @pytest.mark.asyncio
    async def test_invalid_redis_urls(self, async_session):
        """Test handling of invalid Redis URLs."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        # Test invalid URL schemes
        invalid_urls = [
            "http://localhost:6379",
            "ftp://localhost:6379",
            "invalid://localhost:6379",
            "redis://",
            "",
        ]

        for url in invalid_urls:
            try:
                # Should not raise during setup but might during actual Redis connection
                admin.use_redis_sessions(redis_url=url)
                # If we get here, URL was accepted (might fail on actual connection)
            except ImportError:
                pytest.skip("Redis not available")
            except Exception:
                # Other exceptions are fine (invalid URL format, etc.)
                pass

    @pytest.mark.asyncio
    async def test_invalid_memcached_servers(self, async_session):
        """Test handling of invalid Memcached server configurations."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test empty servers list (should use defaults)
            admin.use_memcached_sessions(servers=[])
            assert "MemcachedSessionStorage" in str(type(admin.session_manager.storage))

            # Test invalid port formats
            invalid_servers = [
                ["localhost:invalid"],
                ["localhost:99999"],  # Too high port
                [":11211"],  # Empty host
                [""],  # Empty string
            ]

            for servers in invalid_servers:
                try:
                    admin.use_memcached_sessions(servers=servers)
                    # If we get here, servers were accepted (might fail on actual connection)
                except ImportError:
                    pytest.skip("Memcached not available")
                except Exception:
                    # Other exceptions are fine (invalid server format, etc.)
                    pass

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_session_manager_state_consistency(self, async_session):
        """Test that session manager state remains consistent during backend switches."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        # Store references to verify they get updated
        initial_session_manager = admin.session_manager
        initial_auth_manager = admin.admin_authentication.session_manager

        # Verify initial state
        assert initial_session_manager is initial_auth_manager
        assert admin.track_sessions_in_db is False

        # Switch to database backend
        admin.use_database_sessions()

        # Verify state changes
        assert admin.session_manager is not initial_session_manager
        assert admin.admin_authentication.session_manager is admin.session_manager
        assert admin.track_sessions_in_db is True

        # Store new references
        db_session_manager = admin.session_manager

        # Switch to memory backend
        admin.use_memory_sessions()

        # Verify state changes again
        assert admin.session_manager is not db_session_manager
        assert admin.admin_authentication.session_manager is admin.session_manager
        assert admin.track_sessions_in_db is False


class TestParameterValidation:
    """Test parameter validation in session backend methods."""

    @pytest.mark.asyncio
    async def test_redis_parameter_types(self, async_session):
        """Test Redis parameter type validation."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test valid types
            admin.use_redis_sessions(
                host="localhost", port=6379, db=0, password="secret"
            )

            # Test string port (should be converted)
            admin.use_redis_sessions(host="localhost", port="6379", db=0)

            # Test string db (should be converted)
            admin.use_redis_sessions(host="localhost", port=6379, db="1")

        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_memcached_parameter_types(self, async_session):
        """Test Memcached parameter type validation."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test valid types
            admin.use_memcached_sessions(host="localhost", port=11211)

            # Test string port (should be converted)
            admin.use_memcached_sessions(host="localhost", port="11211")

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_track_sessions_in_db_parameter(self, async_session):
        """Test track_sessions_in_db parameter handling."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        # Test with memory sessions (should ignore track_sessions_in_db)
        admin.use_memory_sessions(track_sessions_in_db=True)
        assert admin.track_sessions_in_db is False  # Memory sessions can't track in DB

        # Test with database sessions (should always track in DB)
        admin.use_database_sessions(track_sessions_in_db=False)
        assert (
            admin.track_sessions_in_db is True
        )  # Database sessions always track in DB

        try:
            # Test with Redis sessions
            admin.use_redis_sessions(host="localhost", track_sessions_in_db=True)
            assert admin.track_sessions_in_db is True

            admin.use_redis_sessions(host="localhost", track_sessions_in_db=False)
            assert admin.track_sessions_in_db is False

        except ImportError:
            pytest.skip("Redis not available")
