"""Session store settings.

Sessions themselves are kept by crudauth since crudadmin 0.6; this package only
holds the configuration objects ``CRUDAdmin`` accepts.
"""

from .configs import MemcachedConfig, RedisConfig

__all__ = ["RedisConfig", "MemcachedConfig"]
