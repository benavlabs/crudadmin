"""Comprehensive tests for session backend parameter handling improvements."""

import pytest

from crudadmin import CRUDAdmin
from crudadmin.session import backends as session_backends
from tests.crud.test_admin import create_test_db_config


class TestRedisSessionParameters:
    """Test Redis session backend parameter handling."""

    @pytest.mark.asyncio
    async def test_redis_url_configuration(self, async_session):
        """Test Redis configuration using URL."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test basic URL
            admin.use_redis_sessions(redis_url="redis://localhost:6379/0")
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test URL with password
            admin.use_redis_sessions(redis_url="redis://user:pass@localhost:6379/1")
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test complex URL
            admin.use_redis_sessions(
                redis_url="redis://admin:secret123@redis.example.com:6380/2"
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_redis_individual_parameters(self, async_session):
        """Test Redis configuration using individual parameters."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test basic parameters
            admin.use_redis_sessions(host="localhost", port=6379, db=0)
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test with password
            admin.use_redis_sessions(
                host="localhost", port=6379, db=1, password="secret"
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test partial parameters (others should use defaults)
            admin.use_redis_sessions(host="custom-host")
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            admin.use_redis_sessions(port=6380)
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            admin.use_redis_sessions(db=3)
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_redis_defaults(self, async_session):
        """Test Redis configuration with all defaults."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            admin.use_redis_sessions()
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )
        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_redis_conflict_detection(self, async_session):
        """Test Redis parameter conflict detection."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test URL + host conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both redis_url and individual parameters",
            ):
                admin.use_redis_sessions(
                    redis_url="redis://localhost:6379", host="localhost"
                )

            # Test URL + port conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both redis_url and individual parameters",
            ):
                admin.use_redis_sessions(redis_url="redis://localhost:6379", port=6379)

            # Test URL + db conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both redis_url and individual parameters",
            ):
                admin.use_redis_sessions(redis_url="redis://localhost:6379", db=0)

            # Test URL + password conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both redis_url and individual parameters",
            ):
                admin.use_redis_sessions(
                    redis_url="redis://localhost:6379", password="secret"
                )

            # Test URL + multiple parameters conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both redis_url and individual parameters",
            ):
                admin.use_redis_sessions(
                    redis_url="redis://localhost:6379", host="localhost", port=6379
                )

        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_redis_additional_parameters(self, async_session):
        """Test Redis with additional parameters like pool_size, connect_timeout."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test with additional parameters via URL
            admin.use_redis_sessions(
                redis_url="redis://localhost:6379/0", pool_size=20, connect_timeout=10
            )

            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test with additional parameters via individual params
            admin.use_redis_sessions(
                host="localhost", port=6379, db=0, pool_size=15, connect_timeout=5
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_use_redis_sessions_with_username_parameter(self, async_session):
        """Test Redis sessions configuration with username parameter."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
        )

        admin.use_redis_sessions(
            host="redis-server",
            port=6380,
            db=2,
            username="redis_user",
            password="redis_pass",
        )

        # Check backend was set
        assert admin._session_backend == "redis"

        # Check all parameters including username were stored
        expected_kwargs = {
            "host": "redis-server",
            "port": 6380,
            "db": 2,
            "username": "redis_user",
            "password": "redis_pass",
        }

        for key, expected_value in expected_kwargs.items():
            assert admin._session_backend_kwargs[key] == expected_value

    @pytest.mark.asyncio
    async def test_use_redis_sessions_with_username_only(self, async_session):
        """Test Redis sessions configuration with username but no password."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
        )

        admin.use_redis_sessions(username="redis_user")

        # Check backend was set
        assert admin._session_backend == "redis"

        # Check username was included but not password
        assert admin._session_backend_kwargs["username"] == "redis_user"
        assert "password" not in admin._session_backend_kwargs

        # Check defaults were applied
        assert admin._session_backend_kwargs["host"] == "localhost"
        assert admin._session_backend_kwargs["port"] == 6379
        assert admin._session_backend_kwargs["db"] == 0

    @pytest.mark.asyncio
    async def test_redis_url_parsing_with_username(self, async_session):
        """Test Redis URL parsing extracts username correctly."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
        )

        # Test URL with username and password
        parsed = admin._parse_redis_url("redis://myuser:mypass@localhost:6379/1")

        expected = {
            "host": "localhost",
            "port": 6379,
            "db": 1,
            "username": "myuser",
            "password": "mypass",
        }

        assert parsed == expected

    @pytest.mark.asyncio
    async def test_redis_url_parsing_with_username_no_password(self, async_session):
        """Test Redis URL parsing with username but no password."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
        )

        # Test URL with username but no password (unusual but valid)
        parsed = admin._parse_redis_url("redis://myuser@localhost:6379/1")

        expected = {
            "host": "localhost",
            "port": 6379,
            "db": 1,
            "username": "myuser",
        }

        assert parsed == expected
        assert "password" not in parsed

    @pytest.mark.asyncio
    async def test_redis_url_with_username_full_example(self, async_session):
        """Test complete Redis sessions configuration with URL containing username."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
        )

        admin.use_redis_sessions(
            redis_url="redis://admin_user:secret123@redis.example.com:6380/3"
        )

        # Check backend was set
        assert admin._session_backend == "redis"

        # Check all parameters were extracted from URL
        expected_kwargs = {
            "host": "redis.example.com",
            "port": 6380,
            "db": 3,
            "username": "admin_user",
            "password": "secret123",
        }

        for key, expected_value in expected_kwargs.items():
            assert admin._session_backend_kwargs[key] == expected_value

    @pytest.mark.asyncio
    async def test_redis_conflict_detection_includes_username(self, async_session):
        """Test that username parameter is included in conflict detection."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
        )

        # Should raise ValueError when both URL and username parameter are provided
        with pytest.raises(
            ValueError, match="Cannot specify both redis_url and individual parameters"
        ):
            admin.use_redis_sessions(
                redis_url="redis://localhost:6379/0",
                username="user",  # This should cause conflict
            )


class TestMemcachedSessionParameters:
    """Test Memcached session backend parameter handling."""

    @pytest.mark.asyncio
    async def test_memcached_servers_configuration(self, async_session):
        """Test Memcached configuration using servers list."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test single server
            admin.use_memcached_sessions(servers=["localhost:11211"])
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

            # Test multiple servers
            admin.use_memcached_sessions(servers=["localhost:11211", "server2:11211"])
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

            # Test custom ports
            admin.use_memcached_sessions(servers=["localhost:11212", "server2:11213"])
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_individual_parameters(self, async_session):
        """Test Memcached configuration using individual parameters."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test basic parameters
            admin.use_memcached_sessions(host="localhost", port=11211)
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

            # Test custom host
            admin.use_memcached_sessions(host="memcached.example.com", port=11211)
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

            # Test custom port
            admin.use_memcached_sessions(host="localhost", port=11212)
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

            # Test partial parameters
            admin.use_memcached_sessions(host="custom-host")
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

            admin.use_memcached_sessions(port=11213)
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_defaults(self, async_session):
        """Test Memcached configuration with all defaults."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            admin.use_memcached_sessions()
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )
        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_conflict_detection(self, async_session):
        """Test Memcached parameter conflict detection."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test servers + host conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both servers and individual parameters",
            ):
                admin.use_memcached_sessions(
                    servers=["localhost:11211"], host="localhost"
                )

            # Test servers + port conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both servers and individual parameters",
            ):
                admin.use_memcached_sessions(servers=["localhost:11211"], port=11211)

            # Test servers + multiple parameters conflict
            with pytest.raises(
                ValueError,
                match="Cannot specify both servers and individual parameters",
            ):
                admin.use_memcached_sessions(
                    servers=["localhost:11211"], host="localhost", port=11211
                )

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_additional_parameters(self, async_session):
        """Test Memcached with additional parameters like pool_size."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Test with additional parameters via servers
            admin.use_memcached_sessions(servers=["localhost:11211"], pool_size=20)
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

            # Test with additional parameters via individual params
            admin.use_memcached_sessions(host="localhost", port=11211, pool_size=15)
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )

        except ImportError:
            pytest.skip("Memcached not available")


class TestSessionManagerRecreation:
    """Test session manager recreation functionality."""

    @pytest.mark.asyncio
    async def test_session_manager_settings_preserved(self, async_session):
        """Test that session manager settings are preserved during backend switches."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            max_sessions_per_user=3,
            session_timeout_minutes=45,
            cleanup_interval_minutes=20,
        )

        # Store original settings
        original_max_sessions = admin.session_manager.max_sessions
        original_timeout = admin.session_manager.session_timeout
        original_cleanup_interval = admin.session_manager.cleanup_interval

        # Switch backends and verify settings are preserved
        admin.use_memory_sessions()
        assert admin.session_manager.max_sessions == original_max_sessions
        assert admin.session_manager.session_timeout == original_timeout
        assert admin.session_manager.cleanup_interval == original_cleanup_interval

        admin.use_database_sessions()
        assert admin.session_manager.max_sessions == original_max_sessions
        assert admin.session_manager.session_timeout == original_timeout
        assert admin.session_manager.cleanup_interval == original_cleanup_interval

    @pytest.mark.asyncio
    async def test_admin_authentication_reference_updated(self, async_session):
        """Test that AdminAuthentication gets updated session manager reference."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        original_session_manager = admin.session_manager
        original_auth_session_manager = admin.admin_authentication.session_manager

        # Verify they're initially the same
        assert original_session_manager is original_auth_session_manager

        # Switch backend
        admin.use_database_sessions()

        # Verify session manager was recreated
        assert admin.session_manager is not original_session_manager

        # Verify admin authentication got the new reference
        assert admin.admin_authentication.session_manager is admin.session_manager

    @pytest.mark.asyncio
    async def test_track_sessions_in_db_flag_management(self, async_session):
        """Test proper management of track_sessions_in_db flag."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        # Initially should be False
        assert admin.track_sessions_in_db is False

        # Switch to database sessions
        admin.use_database_sessions()
        assert admin.track_sessions_in_db is True
        assert isinstance(
            admin.session_manager.storage, session_backends.DatabaseSessionStorage
        )

        # Switch to memory sessions (should reset flag)
        admin.use_memory_sessions()
        assert admin.track_sessions_in_db is False
        assert isinstance(
            admin.session_manager.storage, session_backends.MemorySessionStorage
        )

        # Switch to Redis with explicit tracking
        try:
            admin.use_redis_sessions(host="localhost", track_sessions_in_db=True)
            assert admin.track_sessions_in_db is True
            # Should be HybridSessionStorage when Redis + DB tracking
            storage_name = type(admin.session_manager.storage)
            assert storage_name in [
                session_backends.HybridSessionStorage,
                session_backends.RedisSessionStorage,
            ]
        except ImportError:
            pytest.skip("Redis not available")


class TestBackwardCompatibility:
    """Test backward compatibility of session backend methods."""

    @pytest.mark.asyncio
    async def test_redis_positional_argument(self, async_session):
        """Test that old Redis positional argument still works."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Old way should still work
            admin.use_redis_sessions("redis://localhost:6379/0")
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )
        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_memcached_positional_argument(self, async_session):
        """Test that old Memcached positional argument still works."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        try:
            # Old way should still work
            admin.use_memcached_sessions(["localhost:11211"])
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )
        except ImportError:
            pytest.skip("Memcached not available")


class TestURLParsing:
    """Test URL parsing functionality."""

    @pytest.mark.asyncio
    async def test_redis_url_parsing(self, async_session):
        """Test Redis URL parsing edge cases."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        # Test various URL formats
        test_cases = [
            ("redis://localhost", {"host": "localhost", "port": 6379, "db": 0}),
            ("redis://localhost:6379", {"host": "localhost", "port": 6379, "db": 0}),
            ("redis://localhost/1", {"host": "localhost", "port": 6379, "db": 1}),
            ("redis://localhost:6380/2", {"host": "localhost", "port": 6380, "db": 2}),
            (
                "redis://user:pass@localhost:6379/1",
                {
                    "host": "localhost",
                    "port": 6379,
                    "db": 1,
                    "username": "user",
                    "password": "pass",
                },
            ),
            (
                "redis://:pass@localhost:6379",
                {"host": "localhost", "port": 6379, "db": 0, "password": "pass"},
            ),
        ]

        for redis_url, expected in test_cases:
            parsed = admin._parse_redis_url(redis_url)
            assert parsed == expected, (
                f"Failed parsing {redis_url}, got {parsed}, expected {expected}"
            )

    @pytest.mark.asyncio
    async def test_memcached_servers_parsing(self, async_session):
        """Test Memcached servers parsing edge cases."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        # Test various server formats
        test_cases = [
            (["localhost"], {"host": "localhost", "port": 11211}),
            (["localhost:11211"], {"host": "localhost", "port": 11211}),
            (["localhost:11212"], {"host": "localhost", "port": 11212}),
            (["custom-host:11213"], {"host": "custom-host", "port": 11213}),
            (
                ["server.example.com:11214"],
                {"host": "server.example.com", "port": 11214},
            ),
            # Only first server is used (aiomcache limitation)
            (
                ["localhost:11211", "server2:11212"],
                {"host": "localhost", "port": 11211},
            ),
        ]

        for servers, expected in test_cases:
            parsed = admin._parse_memcached_servers(servers)
            assert parsed == expected, (
                f"Failed parsing {servers}, got {parsed}, expected {expected}"
            )

        # Test empty servers list
        parsed = admin._parse_memcached_servers([])
        assert parsed == {"host": "localhost", "port": 11211}
