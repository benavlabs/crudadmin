import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, Type, TypeVar, cast
from uuid import uuid4

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class AbstractSessionStorage(Generic[T], ABC):
    """Abstract base class for session storage implementations."""

    def __init__(
        self,
        prefix: str = "session:",
        expiration: int = 1800,
    ):
        """Initialize the session storage.

        Args:
            prefix: Prefix for all session keys
            expiration: Default session expiration in seconds
        """
        self.prefix = prefix
        self.expiration = expiration

    def generate_session_id(self) -> str:
        """Generate a unique session ID.

        Returns:
            A unique session ID string
        """
        return str(uuid4())

    def get_key(self, session_id: str) -> str:
        """Generate the full key for a session ID.

        Args:
            session_id: The session ID

        Returns:
            The full storage key
        """
        return f"{self.prefix}{session_id}"

    @abstractmethod
    async def create(
        self,
        data: T,
        session_id: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> str:
        """Create a new session.

        Args:
            data: Session data (must be a Pydantic model)
            session_id: Optional session ID. If not provided, one will be generated
            expiration: Optional custom expiration in seconds

        Returns:
            The session ID
        """
        pass

    @abstractmethod
    async def get(self, session_id: str, model_class: Type[T]) -> Optional[T]:
        """Get session data.

        Args:
            session_id: The session ID
            model_class: The Pydantic model class to decode the data into

        Returns:
            The session data or None if session doesn't exist
        """
        pass

    @abstractmethod
    async def update(
        self,
        session_id: str,
        data: T,
        reset_expiration: bool = True,
        expiration: Optional[int] = None,
    ) -> bool:
        """Update session data.

        Args:
            session_id: The session ID
            data: New session data
            reset_expiration: Whether to reset the expiration
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was updated, False if it didn't exist
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: The session ID

        Returns:
            True if the session was deleted, False if it didn't exist
        """
        pass

    @abstractmethod
    async def extend(self, session_id: str, expiration: Optional[int] = None) -> bool:
        """Extend the expiration of a session.

        Args:
            session_id: The session ID
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was extended, False if it didn't exist
        """
        pass

    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: The session ID

        Returns:
            True if the session exists, False otherwise
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the storage connection."""
        pass


class SessionStorage(AbstractSessionStorage[T], Generic[T]):
    def __new__(cls, backend: str = "memory", **kwargs: Any) -> "SessionStorage[T]":
        """Factory method to create the appropriate session storage backend.

        Args:
            backend: The backend to use ("redis", "memcached", "memory", "database", "hybrid")
            **kwargs: Additional arguments to pass to the backend

        Returns:
            An initialized storage backend
        """
        storage: AbstractSessionStorage[T] = get_session_storage(
            backend, cast(Type[T], BaseModel), **kwargs
        )
        return cast("SessionStorage[T]", storage)


def get_session_storage(
    backend: str, model_type: Type[BaseModel], **kwargs: Any
) -> AbstractSessionStorage[T]:
    """Get the appropriate session storage backend.

    Args:
        backend: The backend to use ("redis", "memcached", "memory", "database", "hybrid")
        model_type: The pydantic model type for type checking
        **kwargs: Additional arguments to pass to the backend

    Returns:
        An initialized storage backend
    """
    if backend == "redis":
        from .backends.redis import RedisSessionStorage

        # Filter kwargs for Redis backend
        redis_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            in [
                "prefix",
                "expiration",
                "host",
                "port",
                "db",
                "username",
                "password",
                "pool_size",
                "connect_timeout",
            ]
        }
        return RedisSessionStorage(**redis_kwargs)

    elif backend == "memcached":
        from .backends.memcached import MemcachedSessionStorage

        # Filter kwargs for Memcached backend
        memcached_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k in ["prefix", "expiration", "host", "port", "pool_size"]
        }
        return MemcachedSessionStorage(**memcached_kwargs)

    elif backend == "memory":
        from .backends.memory import MemorySessionStorage

        # Filter kwargs for Memory backend
        memory_kwargs = {
            k: v for k, v in kwargs.items() if k in ["prefix", "expiration"]
        }
        return MemorySessionStorage(**memory_kwargs)

    elif backend == "database":
        from .backends.database import DatabaseSessionStorage

        # Filter kwargs for Database backend
        database_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k in ["prefix", "expiration", "db_config"]
        }
        return DatabaseSessionStorage(**database_kwargs)

    elif backend == "hybrid":
        from .backends.hybrid import HybridSessionStorage

        db_config = kwargs.pop("db_config", None)
        if not db_config:
            raise ValueError("db_config is required for hybrid backend")

        redis_params = ["db", "username", "password"]

        has_redis_params = any(param in kwargs for param in redis_params)

        use_redis = has_redis_params or kwargs.pop("_cache_backend", "redis") == "redis"

        cache_storage: AbstractSessionStorage[T]
        if use_redis:
            cache_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k
                in [
                    "prefix",
                    "expiration",
                    "host",
                    "port",
                    "db",
                    "username",
                    "password",
                    "pool_size",
                    "connect_timeout",
                ]
            }

            from .backends.redis import RedisSessionStorage

            cache_storage = RedisSessionStorage(**cache_kwargs)
        else:
            cache_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k in ["prefix", "expiration", "host", "port", "pool_size"]
            }

            from .backends.memcached import MemcachedSessionStorage

            cache_storage = MemcachedSessionStorage(**cache_kwargs)

        database_kwargs = {
            k: v for k, v in kwargs.items() if k in ["prefix", "expiration"]
        }
        database_kwargs["db_config"] = db_config

        hybrid_kwargs = {
            k: v for k, v in kwargs.items() if k in ["prefix", "expiration"]
        }

        from .backends.database import DatabaseSessionStorage

        database_storage: DatabaseSessionStorage[T] = DatabaseSessionStorage(
            **database_kwargs
        )

        return HybridSessionStorage(
            redis_storage=cache_storage,
            database_storage=database_storage,
            **hybrid_kwargs,
        )
    else:
        raise ValueError(f"Unknown backend: {backend}")
