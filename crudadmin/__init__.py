from importlib.metadata import version

from .admin_interface.crud_admin import CRUDAdmin
from .config import AccessConfig, SessionConfig
from .session.configs import MemcachedConfig, RedisConfig

__version__ = version("crudadmin")

__all__ = [
    "CRUDAdmin",
    "SessionConfig",
    "AccessConfig",
    "RedisConfig",
    "MemcachedConfig",
    "__version__",
]
