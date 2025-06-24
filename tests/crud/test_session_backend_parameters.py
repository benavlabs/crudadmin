"""Comprehensive tests for session backend parameter handling improvements."""

import pytest

from crudadmin import CRUDAdmin
from crudadmin.session import backends as session_backends
from crudadmin.session.configs import MemcachedConfig, RedisConfig
from tests.crud.test_admin import create_test_db_config


class TestRedisSessionParameters:
    """Test Redis session backend parameter handling."""

    @pytest.mark.asyncio
    async def test_redis_url_configuration(self, async_session):
        """Test Redis configuration using URL."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        try:
            # Test basic URL
            redis_config = RedisConfig(url="redis://localhost:6379/0")
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test URL with password
            redis_config = RedisConfig(url="redis://user:pass@localhost:6379/1")
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test complex URL
            redis_config = RedisConfig(
                url="redis://admin:secret123@redis.example.com:6380/2"
            )
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
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

        try:
            # Test basic parameters
            redis_config = RedisConfig(host="localhost", port=6379, db=0)
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test with password
            redis_config = RedisConfig(
                host="localhost", port=6379, db=1, password="secret"
            )
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test partial parameters (others should use defaults)
            redis_config = RedisConfig(host="custom-host")
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            redis_config = RedisConfig(port=6380)
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            redis_config = RedisConfig(db=3)
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
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

        try:
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
            )
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

        try:
            # Test URL + host conflict - now this should work because URL takes precedence
            redis_config = RedisConfig(
                url="redis://localhost:6379", host="ignored-host"
            )
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test invalid port range
            with pytest.raises(ValueError):
                RedisConfig(port=70000)  # Port too high

            # Test invalid database number
            with pytest.raises(ValueError):
                RedisConfig(db=-1)  # Negative db number

        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_redis_additional_parameters(self, async_session):
        """Test Redis with additional parameters like pool_size, connect_timeout."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        try:
            # Test with additional parameters via URL
            redis_config = RedisConfig(url="redis://localhost:6379/0")
            admin_url = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )

            assert isinstance(
                admin_url.session_manager.storage, session_backends.RedisSessionStorage
            )

            # Test with additional parameters via individual params
            redis_config = RedisConfig(
                host="localhost", port=6379, db=0, pool_size=10, connect_timeout=5
            )
            admin_individual = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="redis",
                redis_config=redis_config,
            )
            assert isinstance(
                admin_individual.session_manager.storage,
                session_backends.RedisSessionStorage,
            )

        except ImportError:
            pytest.skip("Redis not available")

    @pytest.mark.asyncio
    async def test_use_redis_sessions_with_username_parameter(self, async_session):
        """Test Redis sessions configuration with username parameter."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        redis_config = RedisConfig(
            host="redis-server",
            port=6380,
            db=2,
            username="redis_user",
            password="redis_pass",
        )

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
            session_backend="redis",
            redis_config=redis_config,
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

        redis_config = RedisConfig(username="redis_user")

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
            session_backend="redis",
            redis_config=redis_config,
        )

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
        # Test URL with username and password using RedisConfig
        redis_config = RedisConfig(url="redis://myuser:mypass@localhost:6379/1")
        parsed = redis_config.to_dict()

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
        # Test URL with username but no password (unusual but valid)
        redis_config = RedisConfig(url="redis://myuser@localhost:6379/1")
        parsed = redis_config.to_dict()

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

        redis_config = RedisConfig(
            url="redis://admin_user:secret123@redis.example.com:6380/3"
        )
        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
            session_backend="redis",
            redis_config=redis_config,
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
        """Test that Redis config handles URL and individual parameters properly."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        # Test that URL takes precedence when both URL and individual params are set
        redis_config = RedisConfig(
            url="redis://localhost:6379/0", username="ignored_user"
        )
        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            initial_admin={"username": "admin", "password": "secure_password123"},
            secure_cookies=False,
            session_backend="redis",
            redis_config=redis_config,
        )

        # Should work fine, and URL should take precedence
        assert admin._session_backend == "redis"
        # Username from URL should be used, not the individual parameter
        assert admin._session_backend_kwargs["host"] == "localhost"


class TestMemcachedSessionParameters:
    """Test Memcached session backend parameter handling."""

    @pytest.mark.asyncio
    async def test_memcached_servers_configuration(self, async_session):
        """Test Memcached configuration using servers list."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        try:
            # Test single server
            memcached_config = MemcachedConfig(servers=["localhost:11211"])
            admin_single = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_single.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

            # Test multiple servers (note: aiomcache only uses first server)
            memcached_config = MemcachedConfig(
                servers=["localhost:11211", "server2:11211"]
            )
            admin_multiple = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_multiple.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

            # Test custom ports
            memcached_config = MemcachedConfig(
                servers=["localhost:11212", "server2:11213"]
            )
            admin_custom_ports = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_custom_ports.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_individual_parameters(self, async_session):
        """Test Memcached configuration using individual parameters."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        try:
            # Test basic parameters
            memcached_config = MemcachedConfig(host="localhost", port=11211)
            admin_basic = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_basic.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

            # Test custom host
            memcached_config = MemcachedConfig(host="memcached.example.com", port=11211)
            admin_custom_host = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_custom_host.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

            # Test custom port
            memcached_config = MemcachedConfig(host="localhost", port=11212)
            admin_custom_port = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_custom_port.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

            # Test partial parameters - host only (uses default port)
            memcached_config = MemcachedConfig(host="custom-host")
            admin_host_only = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_host_only.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

            # Test partial parameters - port only (uses default host)
            memcached_config = MemcachedConfig(port=11213)
            admin_port_only = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_port_only.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_defaults(self, async_session):
        """Test Memcached configuration with all defaults."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        try:
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
            )
            assert isinstance(
                admin.session_manager.storage, session_backends.MemcachedSessionStorage
            )
        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_conflict_detection(self, async_session):
        """Test Memcached configuration handles servers and individual parameters properly."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        try:
            # Test that both servers and individual parameters can be specified
            # (servers take precedence)
            memcached_config = MemcachedConfig(
                servers=["localhost:11211"],
                host="ignored_host",  # Should be ignored
                port=9999,  # Should be ignored
            )
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )

            # Should work fine - config is valid
            assert admin._session_backend == "memcached"
            assert isinstance(
                admin.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

        except ImportError:
            pytest.skip("Memcached not available")

    @pytest.mark.asyncio
    async def test_memcached_additional_parameters(self, async_session):
        """Test Memcached with additional parameters like pool_size."""
        secret_key = "test-secret-key-for-testing-only-32-chars"
        db_config = create_test_db_config(async_session)

        try:
            # Test with additional parameters via servers
            memcached_config = MemcachedConfig(
                servers=["localhost:11211"],
                pool_size=10,  # Additional parameter
            )
            admin_servers = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_servers.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

            # Test with additional parameters via individual params
            memcached_config = MemcachedConfig(
                host="localhost",
                port=11211,
                pool_size=5,  # Additional parameter
            )
            admin_individual = CRUDAdmin(
                session=async_session,
                SECRET_KEY=secret_key,
                db_config=db_config,
                setup_on_initialization=False,
                session_backend="memcached",
                memcached_config=memcached_config,
            )
            assert isinstance(
                admin_individual.session_manager.storage,
                session_backends.MemcachedSessionStorage,
            )

        except ImportError:
            pytest.skip("Memcached not available")


class TestURLParsing:
    """Test URL parsing functionality."""

    @pytest.mark.asyncio
    async def test_redis_url_parsing(self, async_session):
        """Test Redis URL parsing edge cases."""
        # Test various URL formats using RedisConfig
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
            redis_config = RedisConfig(url=redis_url)
            parsed = redis_config.to_dict()
            assert parsed == expected, (
                f"Failed parsing {redis_url}, got {parsed}, expected {expected}"
            )

    @pytest.mark.asyncio
    async def test_memcached_servers_parsing(self, async_session):
        """Test Memcached servers parsing edge cases."""
        # Test various server formats using MemcachedConfig
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
            memcached_config = MemcachedConfig(servers=servers)
            parsed = memcached_config.to_dict()
            # Compare only host and port from parsed result
            extracted = {"host": parsed["host"], "port": parsed["port"]}
            assert extracted == expected, (
                f"Failed parsing {servers}, got {extracted}, expected {expected}"
            )

        # Test empty servers list (should use defaults)
        memcached_config = MemcachedConfig(servers=[])
        parsed = memcached_config.to_dict()
        extracted = {"host": parsed["host"], "port": parsed["port"]}
        assert extracted == {"host": "localhost", "port": 11211}
