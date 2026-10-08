"""How CRUDAdmin picks and builds its session backend on crudauth.

Sessions live in memory, Redis or the admin database. Memcached and the Redis +
database "hybrid" mode were removed in 0.6: asking for them must fail at startup
rather than fall back to memory, which would log admins out between workers.
"""

import warnings
from typing import Any

import pytest
from sqlalchemy.orm import DeclarativeBase

from crudadmin import CRUDAdmin, MemcachedConfig, RedisConfig
from crudadmin.core.db import DatabaseConfig

SECRET = "x" * 32


async def _get_session():
    yield None


def _admin(tmp_path, **kwargs) -> CRUDAdmin:
    class AdminBase(DeclarativeBase):
        pass

    return CRUDAdmin(
        session=_get_session,
        SECRET_KEY=SECRET,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=_get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        ),
        **kwargs,
    )


@pytest.mark.parametrize("backend", ["memory", "redis", "database"])
def test_supported_backends_are_used_as_given(tmp_path, backend):
    admin = _admin(tmp_path, session_backend=backend)

    assert admin.admin_authentication.session_transport._backend == backend


def test_database_backend_keeps_lockout_counters_in_the_database_too(tmp_path):
    from crudauth.ratelimit import DatabaseRateLimiterBackend

    admin = _admin(tmp_path, session_backend="database")

    limiter = admin.admin_authentication.auth.runtime.rate_limiter
    assert isinstance(limiter, DatabaseRateLimiterBackend)
    assert limiter.prefix == "crudadmin:rl:"


@pytest.mark.parametrize("backend", ["memcached", "MEMCACHED"])
def test_memcached_fails_with_the_replacements_named(tmp_path, backend):
    with pytest.raises(ValueError, match="'redis'.*'database'"):
        _admin(tmp_path, session_backend=backend)


def test_hybrid_warns_and_runs_on_redis(tmp_path):
    """Hybrid was Redis plus a copy of each session in the database."""
    with pytest.warns(DeprecationWarning, match="hybrid"):
        admin = _admin(tmp_path, session_backend="hybrid")

    assert admin._session_backend == "redis"
    assert admin.admin_authentication.session_transport._backend == "redis"


def test_memcached_config_fails_too(tmp_path):
    with pytest.raises(ValueError, match="no longer supported"):
        _admin(tmp_path, memcached_config=MemcachedConfig())


def test_unknown_backend_fails(tmp_path):
    with pytest.raises(ValueError, match="Unknown session_backend"):
        _admin(tmp_path, session_backend="postgres")


def test_track_sessions_in_db_warns_and_keeps_memory_users_on_a_shared_store(tmp_path):
    """Before 0.6, track_sessions_in_db with memory meant the database backend."""
    with pytest.warns(DeprecationWarning, match="track_sessions_in_db"):
        admin = _admin(tmp_path, track_sessions_in_db=True)

    assert admin._session_backend == "database"


def test_track_sessions_in_db_with_redis_stays_on_redis(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        admin = _admin(tmp_path, session_backend="redis", track_sessions_in_db=True)

    assert admin._session_backend == "redis"


def _redis(admin: CRUDAdmin) -> Any:
    assert admin._redis_client is not None
    return admin._redis_client


class TestRedisClient:
    """The client is built lazily (no connection here), so no Redis server is needed."""

    def test_defaults(self, tmp_path):
        admin = _admin(tmp_path, session_backend="redis")

        kwargs = _redis(admin).connection_pool.connection_kwargs
        assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("localhost", 6379, 0)

    def test_individual_parameters(self, tmp_path):
        config = RedisConfig(
            host="redis.internal",
            port=6380,
            db=2,
            username="admin",
            password="s3cret",
            pool_size=7,
            connect_timeout=3,
        )
        admin = _admin(tmp_path, session_backend="redis", redis_config=config)

        pool = _redis(admin).connection_pool
        kwargs = pool.connection_kwargs
        assert kwargs["host"] == "redis.internal"
        assert kwargs["port"] == 6380
        assert kwargs["db"] == 2
        assert kwargs["username"] == "admin"
        assert kwargs["password"] == "s3cret"
        assert kwargs["socket_connect_timeout"] == 3
        assert pool.max_connections == 7

    def test_url_keeps_tls(self, tmp_path):
        """A rediss:// URL is passed through whole, so TLS isn't silently dropped."""
        config = RedisConfig(url="rediss://user:pw@redis.example.com:6390/4")
        admin = _admin(tmp_path, session_backend="redis", redis_config=config)

        pool = _redis(admin).connection_pool
        assert pool.connection_class.__name__ == "SSLConnection"
        assert pool.connection_kwargs["host"] == "redis.example.com"
        assert pool.connection_kwargs["db"] == 4

    def test_dict_config(self, tmp_path):
        admin = _admin(
            tmp_path, session_backend="redis", redis_config={"host": "h", "db": 5}
        )

        kwargs = _redis(admin).connection_pool.connection_kwargs
        assert (kwargs["host"], kwargs["db"]) == ("h", 5)

    def test_other_backends_build_no_client(self, tmp_path):
        admin = _admin(tmp_path, session_backend="memory", redis_config=RedisConfig())

        assert admin._redis_client is None
