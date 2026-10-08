import warnings
from typing import Any, Dict, Optional, Union

from ..session.configs import MemcachedConfig, RedisConfig


def resolve_session_backend(
    session_backend: str,
    track_sessions_in_db: bool,
    memcached_config: Optional[Union[MemcachedConfig, Dict[str, Any]]],
) -> str:
    """Map the ``session_backend`` setting onto the backends crudadmin supports.

    crudadmin 0.6 keeps sessions with crudauth, in memory, Redis or the admin
    database. Memcached is gone and fails here rather than silently falling back
    to memory, which would log admins out between workers. "hybrid" was Redis
    with a copy in the database; it now means Redis, with a deprecation warning.
    """
    backend = (session_backend or "memory").lower()
    if backend == "memcached" or memcached_config is not None:
        raise ValueError(
            "session_backend='memcached' is no longer supported. Use 'redis' for "
            "a shared session store, or 'database' to keep sessions in the admin "
            "database without extra infrastructure."
        )
    if backend == "hybrid":
        warnings.warn(
            "session_backend='hybrid' is deprecated and will be removed: it now "
            "means 'redis'. Sessions are listed on the Sessions page and logins "
            "are recorded in the event log (track_events=True).",
            DeprecationWarning,
            stacklevel=3,
        )
        backend = "redis"
    if track_sessions_in_db:
        warnings.warn(
            "track_sessions_in_db is deprecated and will be removed: sessions are "
            "listed on the Sessions page and logins are recorded in the event log "
            "(track_events=True). Use session_backend='database' to keep sessions "
            "in the admin database.",
            DeprecationWarning,
            stacklevel=3,
        )
        if backend == "memory":
            backend = "database"
    if backend not in ("memory", "redis", "database"):
        raise ValueError(
            f"Unknown session_backend {backend!r}: use 'memory', 'redis' or 'database'."
        )
    return backend


def build_redis_client(
    redis_config: Optional[Union[RedisConfig, Dict[str, Any]]],
) -> Any:
    """An async Redis client for the ``redis`` session backend."""
    try:
        from redis.asyncio import Redis
    except ImportError as error:
        raise ImportError(
            "session_backend='redis' needs the redis package: "
            "pip install 'crudadmin[redis]'"
        ) from error

    if redis_config is None:
        config = RedisConfig()
    elif isinstance(redis_config, RedisConfig):
        config = redis_config
    elif isinstance(redis_config, dict):
        config = RedisConfig(**redis_config)
    else:
        raise ValueError("redis_config must be RedisConfig instance or dict")

    options: Dict[str, Any] = {}
    if config.pool_size is not None:
        options["max_connections"] = config.pool_size
    if config.connect_timeout is not None:
        options["socket_connect_timeout"] = config.connect_timeout
    if config.url is not None:
        return Redis.from_url(config.url, **options)
    return Redis(
        host=config.host,
        port=config.port,
        db=config.db,
        username=config.username,
        password=config.password,
        **options,
    )
