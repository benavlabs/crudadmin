"""Session storage backends for different storage systems."""

from .database import DatabaseSessionStorage
from .hybrid import HybridSessionStorage
from .memory import MemorySessionStorage


def __getattr__(name: str):
    """Lazy loading for optional session backends."""
    if name == "MemcachedSessionStorage":
        try:
            from .memcached import MemcachedSessionStorage

            return MemcachedSessionStorage
        except ImportError as e:
            raise ImportError(
                "MemcachedSessionStorage requires 'aiomcache' package. "
                "Install with: pip install 'crudadmin[memcached]'"
            ) from e
    elif name == "RedisSessionStorage":
        try:
            from .redis import RedisSessionStorage

            return RedisSessionStorage
        except ImportError as e:
            raise ImportError(
                "RedisSessionStorage requires 'redis' package. "
                "Install with: pip install 'crudadmin[redis]'"
            ) from e
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = (
    "MemorySessionStorage",
    "RedisSessionStorage",
    "MemcachedSessionStorage",
    "DatabaseSessionStorage",
    "HybridSessionStorage",
)
