from importlib.metadata import version

from .admin_interface.crud_admin import CRUDAdmin
from .session.configs import MemcachedConfig, RedisConfig

__version__ = version("crudadmin")

__all__ = ["CRUDAdmin", "RedisConfig", "MemcachedConfig", "__version__"]
